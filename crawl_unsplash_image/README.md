# `crawl_unsplash_image` – Unsplash Image Crawler

This module downloads images from **Unsplash** using the official **Unsplash API**.

## What it does

- Searches photos by a keyword (`SEARCH_QUERY`)
- Optionally restricts results to **photos created today** (local timezone)
- Downloads image files into a local “data lake” folder partitioned by crawl date
- Keeps a local state file to **avoid downloading the same photo twice**
- Stores a metadata index for each downloaded photo

## Requirements

- Python + dependencies:
  - `requests`
- An Unsplash API access key (**Access Key**, not Secret Key)

## Setup

Create a `.env` file in `crawl_unsplash_image/`:

```env
ACCESS_KEY=YOUR_UNSPLASH_ACCESS_KEY
```

The script will read `ACCESS_KEY` (or `UNSPLASH_ACCESS_KEY`) from `.env`.

## Configuration (edit `crawl_unsplash_image/main.py`)

At the top of `main.py`, adjust these constants:

- **`SEARCH_QUERY`**: keyword to search (default: `technology`)
- **`TODAY_ONLY`**: `True` to download only photos created “today” (local date)
- **`ORDER_BY`**: recommended `latest` when `TODAY_ONLY=True`
- **`MAX_RESULTS`**: how many photos to download per run
- **`IMAGE_QUALITY`**: one of `raw|full|regular|small|thumb`
- **`ORIENTATION`**: `landscape|portrait|squarish` (optional)
- **`COLOR`**: optional color filter (e.g. `black_and_white`, `blue`, ...)
- **Retry/Rate settings**: `REQUEST_DELAY`, `MAX_RETRIES`, `RETRY_BACKOFF`, `DOWNLOAD_TIMEOUT`

## Run

From repo root:

```powershell
python crawl_unsplash_image/main.py
```

## Outputs

All outputs are written under `crawl_unsplash_image/downloads/`:

- **Images** (partitioned by crawl date):
  - `downloads/YYYY-MM-DD/<photo_id>.<ext>` (usually `.jpg`)
- **Dedup state**:
  - `downloads/downloaded_ids.json`
  - Contains a minimal record per downloaded `photo_id` (title, file path, url, downloaded_at)
- **Metadata index**:
  - `downloads/metadata.json`
  - Contains a richer JSON record per `photo_id` (dimensions, user info, urls, links, etc.)

## Deduplication logic

- Before downloading, the script loads `downloads/downloaded_ids.json` and skips any `photo_id` already present.
- After a successful download, it updates both:
  - `downloaded_ids.json` (small state)
  - `metadata.json` (full metadata index)

## Notes / caveats

- **“Today only”** uses the photo `created_at` field converted to your **local timezone**.
- Unsplash API may rate-limit (HTTP 429). The script retries with backoff and honors `Retry-After` when present.
- Unsplash requests a download “trigger” call (`download_location`) for tracking. The script attempts it and continues even if it fails.

