import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).parent


def load_config(config_path='config.yaml') -> dict:
    config_file = SCRIPT_DIR / config_path
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_dotenv(path='.env'):
    env_path = SCRIPT_DIR / path
    if not env_path.exists():
        return
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


CFG = load_config()
load_dotenv()
API_KEY = os.getenv('key')

SEARCH = CFG['search']
DOWNLOAD = CFG['download']
API = CFG['api']
EJS = CFG.get('ejs', {}) or {}

DOWNLOAD_PATH = SCRIPT_DIR / DOWNLOAD['output_dir']
STATE_PATH = SCRIPT_DIR / DOWNLOAD['state_file']


def load_downloaded_ids():
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_downloaded_ids(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def execute_with_retry(request, label='YouTube API'):
    """Retry on quota/rate-limit (429) and transient server errors."""
    retryable_status = {429, 500, 502, 503, 504}
    max_retries = API['max_retries']
    request_delay = API['request_delay']
    retry_backoff = API['retry_backoff']

    for attempt in range(1, max_retries + 1):
        if request_delay > 0:
            time.sleep(request_delay)

        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status
            if status not in retryable_status or attempt == max_retries:
                raise

            retry_after = exc.resp.get('retry-after')
            if retry_after:
                wait = float(retry_after)
            elif status == 429:
                wait = max(60.0, retry_backoff * attempt)
            else:
                wait = retry_backoff * attempt

            print(
                f'  {label}: HTTP {status} '
                f'(attempt {attempt}/{max_retries}), retry in {wait:.0f}s'
            )
            time.sleep(wait)

    raise RuntimeError(f'{label}: max retries exceeded')


def is_likely_english(snippet):
    """
    YouTube search has no language filter. relevanceLanguage only affects ranking.
    We filter after search using metadata + a simple title heuristic.
    """
    for field in ('defaultAudioLanguage', 'defaultLanguage'):
        lang = snippet.get(field) or ''
        if lang.lower().startswith('en'):
            return True
        if lang and not lang.lower().startswith('en'):
            return False

    title = snippet.get('title', '')
    if not title:
        return False

    latin_chars = len(re.findall(r'[A-Za-z]', title))
    non_latin_letters = len(re.findall(r'[^\x00-\x7F\s\d\W]', title))
    return latin_chars >= 8 and latin_chars >= non_latin_letters


_ISO8601_RE = re.compile(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$')


def parse_iso8601_duration_to_seconds(s: str):
    if not s:
        return None
    m = _ISO8601_RE.match(s.strip())
    if not m:
        return None
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    sec = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + sec


def fetch_video_details(youtube, video_ids):
    if not video_ids:
        return {}

    request = youtube.videos().list(
        part='snippet,contentDetails',
        id=','.join(video_ids),
    )
    response = execute_with_retry(request, label='videos.list')

    return {
        item['id']: item
        for item in response.get('items', [])
    }


def get_recent_ai_videos(api_key, skip_ids=None):
    youtube = build('youtube', 'v3', developerKey=api_key)
    skip_ids = skip_ids or set()
    max_results = SEARCH['max_results']
    days_back = SEARCH['days_back']
    min_duration_seconds = int(SEARCH.get('min_duration_seconds', 0))
    max_duration_seconds = int(SEARCH.get('max_duration_seconds', 180))
    search_timeout_seconds = int(SEARCH.get('search_timeout_seconds', 3600))
    deadline = time.time() + max(1, search_timeout_seconds)

    now = datetime.now(timezone.utc)
    if days_back <= 0:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=days_back)
    published_after = start.strftime('%Y-%m-%dT%H:%M:%SZ')
    published_before = now.strftime('%Y-%m-%dT%H:%M:%SZ')

    print(f'Searching AI videos published after: {published_after}...')
    print(
        f"Note: relevanceLanguage={SEARCH['relevance_language']!r} "
        f"and regionCode={SEARCH.get('region_code')!r} "
        'only bias ranking — they do not block non-English videos.'
    )
    if SEARCH['require_english']:
        print('Post-filter: keeping videos with English metadata or Latin-script titles.')

    video_urls = []
    next_page_token = None
    page_size = min(max(max_results * 4, 20), 50)
    page = 0

    while len(video_urls) < max_results and time.time() < deadline:
        page += 1
        remaining_s = int(max(0, deadline - time.time()))
        print(f'\n[search] page={page} collected={len(video_urls)}/{max_results} remaining_timeout_s={remaining_s}')
        search_params = {
            'part': 'id,snippet',
            'q': SEARCH['query'],
            'type': 'video',
            'publishedAfter': published_after,
            'publishedBefore': published_before,
            'relevanceLanguage': SEARCH['relevance_language'],
            'maxResults': page_size,
            'order': 'date',
        }
        if SEARCH.get('video_duration'):
            search_params['videoDuration'] = SEARCH['video_duration']
        region_code = SEARCH.get('region_code')
        if region_code:
            search_params['regionCode'] = region_code

        request = youtube.search().list(**search_params, pageToken=next_page_token)
        response = execute_with_retry(request, label='search.list')
        items = response.get('items', [])
        print(f'[search] items_returned={len(items)} nextPageToken_present={bool(response.get("nextPageToken"))}')

        if not items:
            print('[search] no items returned; stopping pagination')
            break

        candidate_ids = [
            item['id']['videoId']
            for item in items
            if item['id']['videoId'] not in skip_ids
            and item['id']['videoId'] not in {url.split('v=')[-1] for url in video_urls}
        ]

        details = fetch_video_details(youtube, candidate_ids)

        for video_id in candidate_ids:
            item = details.get(video_id)
            if not item:
                continue
            snippet = item.get('snippet') or {}
            content = item.get('contentDetails') or {}

            title = snippet.get('title', '')
            url = f'https://www.youtube.com/watch?v={video_id}'

            if video_id in skip_ids:
                print(f'Skip (already downloaded): {title}')
                continue

            if SEARCH['require_english'] and not is_likely_english(snippet):
                lang = snippet.get('defaultAudioLanguage') or snippet.get('defaultLanguage') or 'unknown'
                print(f'Skip (not English): [{lang}] {title}')
                continue

            dur_s = parse_iso8601_duration_to_seconds(content.get('duration', ''))
            if dur_s is None or dur_s < min_duration_seconds or dur_s > max_duration_seconds:
                print(f'Skip (duration {dur_s}s not in [{min_duration_seconds},{max_duration_seconds}]): {title}')
                continue

            video_urls.append(url)
            print(f'Found: {title} - {url}')

            if len(video_urls) >= max_results:
                break

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            print('[search] no nextPageToken; stopping pagination')
            break

    if len(video_urls) < max_results and time.time() >= deadline:
        print(
            f"Search timeout reached ({search_timeout_seconds}s). "
            f"Collected {len(video_urls)}/{max_results} matching video(s)."
        )

    return video_urls


def download_video_stream(url, video_dir):
    """Download video-only stream (no ffmpeg merge required)."""
    ydl_opts = {
        'format': DOWNLOAD['video_format'],
        'outtmpl': str(video_dir / '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get('ext', 'mp4')
        video_id = info.get('id')
        file_path = video_dir / f'{video_id}.{ext}'
        if file_path.exists():
            return str(file_path.relative_to(SCRIPT_DIR)), info
    return None, None


def download_audio_stream(url, audio_dir):
    """Download audio-only stream (no ffmpeg merge required)."""
    ydl_opts = {
        'format': DOWNLOAD['audio_format'],
        'outtmpl': str(audio_dir / '%(id)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get('ext', 'm4a')
        video_id = info.get('id')
        file_path = audio_dir / f'{video_id}.{ext}'
        if file_path.exists():
            return str(file_path.relative_to(SCRIPT_DIR)), info
    return None, None


def write_info_and_subs(url, info_dir, subs_dir):
    subs_cfg = DOWNLOAD.get('subtitles') or {}
    subs_enabled = bool(subs_cfg.get('enabled', True))
    subs_langs = subs_cfg.get('languages') or ['en']
    subs_formats = subs_cfg.get('formats', 'vtt/srt')
    write_auto = bool(subs_cfg.get('write_auto_subs', True))

    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': {
            # Note: for "infojson" template, %(ext)s is typically "info.json".
            # So don't hardcode ".info.json" to avoid "....info.json.info.json".
            'infojson': str(info_dir / '%(id)s.%(ext)s'),
            'subtitle': str(subs_dir / '%(id)s.%(language)s.%(ext)s'),
        },
        'writeinfojson': bool(DOWNLOAD.get('write_info_json', True)),
        'writesubtitles': subs_enabled,
        'writeautomaticsub': subs_enabled and write_auto,
        'subtitleslangs': subs_langs,
        'subtitlesformat': subs_formats,
    }

    if EJS.get('js_runtimes'):
        ydl_opts['js_runtimes'] = EJS.get('js_runtimes')
    if EJS.get('remote_components'):
        ydl_opts['remote_components'] = EJS.get('remote_components')

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        vid = info.get('id')
        info_path = info_dir / f'{vid}.info.json'
        webpage_url = info.get('webpage_url') or info.get('original_url') or ''
        is_shorts = '/shorts/' in str(webpage_url)
        title = info.get('title') or ''
        return (
            str(info_path.relative_to(SCRIPT_DIR)) if info_path.exists() else None,
            is_shorts,
            title,
        )


def download_assets(urls, base_dir, state):
    if not urls:
        print('No new videos to download.')
        return state

    video_dir = base_dir / 'video'
    audio_dir = base_dir / 'audio'
    info_dir = base_dir / 'info'
    subs_dir = base_dir / 'subs'
    for folder in (video_dir, audio_dir, info_dir, subs_dir):
        folder.mkdir(parents=True, exist_ok=True)

    print(f'\nDownloading {len(urls)} item(s) into {base_dir}...')

    for url in urls:
        video_id = url.split('v=')[-1]
        print(f'\n-> {video_id}')

        record = {
            'url': url,
            'title': '',
            'video': None,
            'audio': None,
            'infojson': None,
            'downloaded_at': datetime.now(timezone.utc).isoformat(),
        }

        try:
            print('  [meta/subs] writing info.json + subtitles...')
            info_path, is_shorts, meta_title = write_info_and_subs(url, info_dir, subs_dir)
            if meta_title:
                record['title'] = meta_title
            if SEARCH.get('exclude_shorts', True) and is_shorts:
                print('  [skip] detected YouTube Shorts via webpage_url; skipping downloads')
                # Don't write to state (so if later you disable exclude_shorts, it can be downloaded)
                continue
            if info_path:
                record['infojson'] = info_path
        except Exception as exc:
            print(f'  [meta/subs] error: {exc}')

        try:
            print('  [video] downloading...')
            video_path, info = download_video_stream(url, video_dir)
            if video_path:
                record['video'] = video_path
                record['title'] = record['title'] or (info or {}).get('title', '')
                print(f'    saved: {Path(video_path).name}')
        except Exception as exc:
            print(f'  [video] error: {exc}')

        try:
            print('  [audio] downloading...')
            audio_path, info = download_audio_stream(url, audio_dir)
            if audio_path:
                record['audio'] = audio_path
                if not record['title']:
                    record['title'] = (info or {}).get('title', '')
                print(f'    saved: {Path(audio_path).name}')
        except Exception as exc:
            print(f'  [audio] error: {exc}')

        if record['video'] or record['audio'] or record['infojson']:
            state[video_id] = record
            save_downloaded_ids(state)

    print('Download complete.')
    return state


if __name__ == '__main__':
    try:
        if not API_KEY:
            raise ValueError(
                "Missing YouTube API key. Set the 'key' env var or add it to .env."
            )

        state = load_downloaded_ids()
        skip_ids = set(state.keys())
        if skip_ids:
            print(f'Skip list: {len(skip_ids)} video(s) already downloaded.')

        today_dir = DOWNLOAD_PATH / datetime.now().strftime('%Y-%m-%d')
        video_urls = get_recent_ai_videos(API_KEY, skip_ids=skip_ids)
        download_assets(video_urls, today_dir, state)

    except HttpError as exc:
        print(f'YouTube API error: HTTP {exc.resp.status} - {exc}')
    except Exception as exc:
        print(f'Error: {exc}')
