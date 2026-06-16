# `crawl_yt_video_audio` – Current Pipeline Logic

This module crawls recent YouTube videos using the **YouTube Data API** for discovery and **yt-dlp** for downloading assets (video/audio/subtitles/metadata).

## 1) Discovery (YouTube Data API, not `ytsearch`)

- Reads configuration from `crawl_yt_video_audio/config.yaml`
- Computes a UTC time window:
  - `days_back: 1` → fetch videos published in roughly the last 24 hours (`now - 1 day` → `now`)
- Calls **YouTube Data API** `search.list` with:
  - `q = search.query`
  - `type = video`
  - `order = date`
  - `publishedAfter / publishedBefore`
  - (no `regionCode` by default → global search)
- Extracts `videoId` from results, then calls `videos.list(part=snippet,contentDetails)` to fetch:
  - language fields (`defaultAudioLanguage` / `defaultLanguage`)
  - duration (`contentDetails.duration`, ISO-8601 like `PT3M15S`)

## 2) Filtering (target selection)

A video is kept only if it matches:

- **English**: `require_english: true`
  - uses language metadata and a simple title heuristic
- **Duration window**: **2–12 minutes**
  - `min_duration_seconds: 120`
  - `max_duration_seconds: 720`

Notes:
- Shorts are not excluded at the API step, but most Shorts are filtered out by the **minimum duration** rule.

The output of this step is a list of URLs like:

- `https://www.youtube.com/watch?v=<id>`

## 3) Download assets (yt-dlp Python library)

For each selected URL that is not already present in `downloads/downloaded_ids.json`:

1. **Metadata + subtitles first** (`skip_download=True`):
   - Writes `downloads/YYYY-MM-DD/info/<id>.info.json`
   - Downloads **English subtitles** (and **auto-subs** if available) into `downloads/YYYY-MM-DD/subs/`
   - Checks whether `webpage_url` contains `'/shorts/'`:
     - if yes → skip entirely (do not download video/audio; do not write state)
2. Downloads **video stream** into `downloads/YYYY-MM-DD/video/`
3. Downloads **audio stream** into `downloads/YYYY-MM-DD/audio/`
4. Writes/updates state in `downloads/downloaded_ids.json` to avoid re-downloading on future runs

## 4) When the program stops (pagination / timeout)

Discovery paginates until one of these conditions is met:

- collected enough items (`max_results`)
- the API returns no `nextPageToken` (no more results)
- reached the time limit `search_timeout_seconds` (default: 3600 seconds)

## Outputs (what you get after a successful run)

After the crawler finishes, the main outputs live under:

- `crawl_yt_video_audio/downloads/YYYY-MM-DD/`

Expected folders/files:

- **Video files**: `video/`
  - e.g. `video/<id>.mp4`
- **Audio files**: `audio/`
  - e.g. `audio/<id>.m4a`
- **Subtitles**: `subs/`
  - e.g. `subs/<id>.<lang>.vtt` (or `.srt` depending on availability)
- **Per-video metadata**: `info/`
  - e.g. `info/<id>.info.json`
- **Deduplication state** (global, across days):
  - `downloads/downloaded_ids.json`

Notes:
- If a download is interrupted, you may see temporary `.part` files. Re-running the crawler usually resumes; otherwise delete the `.part` file and re-run.
- Some videos will not have subtitles; in that case you will still get `info.json` + media files.