import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIG ---
SEARCH_QUERY = 'technology'
ORDER_BY = 'latest'          # use latest + created_at filter for today's photos
TODAY_ONLY = True            # only download images published on the current day
ORIENTATION = None           # landscape | portrait | squarish
COLOR = None                 # e.g. black_and_white, blue, ...
MAX_RESULTS = 20
PER_PAGE = 30
IMAGE_QUALITY = 'regular'    # raw | full | regular | small | thumb
OUTPUT_DIR = './downloads'
STATE_FILE = './downloads/downloaded_ids.json'
METADATA_FILE = './downloads/metadata.json'
REQUEST_DELAY = 1.0
MAX_RETRIES = 6
RETRY_BACKOFF = 15.0
DOWNLOAD_TIMEOUT = 60

API_BASE = 'https://api.unsplash.com'
SCRIPT_DIR = Path(__file__).parent
OUTPUT_PATH = SCRIPT_DIR / OUTPUT_DIR
STATE_PATH = SCRIPT_DIR / STATE_FILE
METADATA_PATH = SCRIPT_DIR / METADATA_FILE


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


load_dotenv()
ACCESS_KEY = os.getenv('ACCESS_KEY') or os.getenv('UNSPLASH_ACCESS_KEY')


def api_headers():
    if not ACCESS_KEY:
        raise ValueError(
            'Missing Unsplash access key. Set ACCESS_KEY in .env.'
        )
    return {
        'Authorization': f'Client-ID {ACCESS_KEY}',
        'Accept-Version': 'v1',
    }


def load_downloaded_ids():
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_downloaded_ids(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_metadata_index():
    if not METADATA_PATH.exists():
        return {}
    with open(METADATA_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_metadata_index(index):
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def request_with_retry(method, url, label='Unsplash API', **kwargs):
    retryable_status = {429, 500, 502, 503, 504}
    headers = kwargs.pop('headers', {})
    headers = {**api_headers(), **headers}

    for attempt in range(1, MAX_RETRIES + 1):
        if REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)

        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=DOWNLOAD_TIMEOUT,
            **kwargs,
        )

        if response.status_code in retryable_status and attempt < MAX_RETRIES:
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                wait = float(retry_after)
            elif response.status_code == 429:
                wait = max(60.0, RETRY_BACKOFF * attempt)
            else:
                wait = RETRY_BACKOFF * attempt

            print(
                f'  {label}: HTTP {response.status_code} '
                f'(attempt {attempt}/{MAX_RETRIES}), retry in {wait:.0f}s'
            )
            time.sleep(wait)
            continue

        response.raise_for_status()
        return response

    raise RuntimeError(f'{label}: max retries exceeded')


def append_client_id(url):
    """Ensure client_id is present when calling download_location URLs."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if 'client_id' not in query:
        query['client_id'] = [ACCESS_KEY]
    new_query = urlencode({k: v[0] for k, v in query.items()})
    return urlunparse(parsed._replace(query=new_query))


def today_local():
    return datetime.now().astimezone().date()


def photo_created_date(photo):
    """Return the photo's created_at date in local timezone."""
    created_at = photo.get('created_at')
    if not created_at:
        return None
    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    return dt.astimezone().date()


def is_published_today(photo):
    created_date = photo_created_date(photo)
    if created_date is None:
        return False
    return created_date == today_local()


def search_photos(query, max_results, skip_ids=None):
    skip_ids = skip_ids or set()
    photos = []
    page = 1

    target_day = today_local()
    print(
        f"Searching Unsplash photos: '{query}' "
        f"(order={ORDER_BY}, date={target_day})..."
    )

    while len(photos) < max_results:
        params = {
            'query': query,
            'page': page,
            'per_page': PER_PAGE,
            'order_by': ORDER_BY,
        }
        if ORIENTATION:
            params['orientation'] = ORIENTATION
        if COLOR:
            params['color'] = COLOR

        response = request_with_retry(
            'GET',
            f'{API_BASE}/search/photos',
            params=params,
            label='search/photos',
        )
        payload = response.json()
        results = payload.get('results', [])

        if not results:
            break

        page_all_older_than_today = True

        for photo in results:
            photo_id = photo['id']
            title = photo.get('alt_description') or photo.get('description') or photo_id
            created_date = photo_created_date(photo)

            if created_date is None or created_date >= target_day:
                page_all_older_than_today = False

            if TODAY_ONLY and not is_published_today(photo):
                if created_date and created_date < target_day:
                    print(f'Skip (published {created_date}): {title} ({photo_id})')
                else:
                    print(f'Skip (not today): {title} ({photo_id})')
                continue

            if photo_id in skip_ids or photo_id in {p['id'] for p in photos}:
                continue

            photos.append(photo)
            print(f'Found ({created_date}): {title} ({photo_id})')

            if len(photos) >= max_results:
                break

        if TODAY_ONLY and page_all_older_than_today:
            print('No more photos from today in search results.')
            break

        if page >= payload.get('total_pages', page):
            break
        page += 1

    return photos


def trigger_download_event(photo):
    """Required by Unsplash API when saving an image."""
    download_location = photo.get('links', {}).get('download_location')
    if not download_location:
        return None

    response = request_with_retry(
        'GET',
        append_client_id(download_location),
        label='download_location',
    )
    return response.json().get('url')


def pick_image_url(photo):
    urls = photo.get('urls', {})
    url = urls.get(IMAGE_QUALITY)
    if url:
        return url

    for quality in ('regular', 'full', 'small', 'thumb'):
        if urls.get(quality):
            return urls[quality]
    return None


def guess_extension(url, content_type):
    if 'jpeg' in content_type or 'jpg' in content_type:
        return '.jpg'
    if 'png' in content_type:
        return '.png'
    if 'webp' in content_type:
        return '.webp'

    path = urlparse(url).path.lower()
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        if path.endswith(ext):
            return ext
    return '.jpg'


def download_image(url, save_path):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF * attempt
            print(f'  Download error (attempt {attempt}/{MAX_RETRIES}): {exc}')
            time.sleep(wait)
            continue

        if response.status_code == 200:
            ext = guess_extension(url, response.headers.get('Content-Type', ''))
            final_path = save_path if save_path.suffix else save_path.with_suffix(ext)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            with open(final_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return str(final_path.relative_to(SCRIPT_DIR))

        if response.status_code in {429, 500, 502, 503, 504} and attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF * attempt
            print(f'  HTTP {response.status_code}, retry in {wait:.0f}s')
            time.sleep(wait)
            continue

        response.raise_for_status()

    return None


def build_photo_record(photo, file_path):
    user = photo.get('user', {})
    return {
        'id': photo['id'],
        'created_at': photo.get('created_at'),
        'description': photo.get('description'),
        'alt_description': photo.get('alt_description'),
        'width': photo.get('width'),
        'height': photo.get('height'),
        'color': photo.get('color'),
        'urls': photo.get('urls', {}),
        'links': photo.get('links', {}),
        'user': {
            'name': user.get('name'),
            'username': user.get('username'),
            'profile_url': user.get('links', {}).get('html'),
        },
        'unsplash_url': photo.get('links', {}).get('html'),
        'file': file_path,
        'downloaded_at': datetime.now(timezone.utc).isoformat(),
    }


def download_photos(photos, save_dir, state):
    if not photos:
        print('No new photos to download.')
        return state

    metadata_index = load_metadata_index()
    print(f'\nDownloading {len(photos)} image(s) into {save_dir}...')

    for photo in photos:
        photo_id = photo['id']
        title = photo.get('alt_description') or photo.get('description') or photo_id
        print(f'\n-> {photo_id}: {title}')

        image_url = pick_image_url(photo)
        if not image_url:
            print('  Skip: no image URL in API response')
            continue

        try:
            trigger_download_event(photo)
        except Exception as exc:
            print(f'  Warning: download_location failed: {exc}')

        try:
            file_path = download_image(image_url, save_dir / photo_id)
            if not file_path:
                print('  Failed to download image')
                continue

            record = build_photo_record(photo, file_path)
            state[photo_id] = {
                'title': title,
                'file': file_path,
                'unsplash_url': record['unsplash_url'],
                'downloaded_at': record['downloaded_at'],
            }
            metadata_index[photo_id] = record
            save_downloaded_ids(state)
            save_metadata_index(metadata_index)
            print(f'  Saved: {Path(file_path).name}')
        except Exception as exc:
            print(f'  Error: {exc}')

    return state


if __name__ == '__main__':
    try:
        state = load_downloaded_ids()
        skip_ids = set(state.keys())
        if skip_ids:
            print(f'Skip list: {len(skip_ids)} image(s) already downloaded.')

        today_dir = OUTPUT_PATH / datetime.now().strftime('%Y-%m-%d')
        photos = search_photos(SEARCH_QUERY, MAX_RESULTS, skip_ids=skip_ids)
        download_photos(photos, today_dir, state)
        print('\nDone.')

    except requests.HTTPError as exc:
        print(f'Unsplash API error: HTTP {exc.response.status_code} - {exc}')
    except Exception as exc:
        print(f'Error: {exc}')
