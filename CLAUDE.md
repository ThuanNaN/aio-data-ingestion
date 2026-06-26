# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A daily data ingestion pipeline that crawls AI-related content from arXiv, YouTube, and Unsplash into a local data lake (Bronze → Silver → Gold zones). Run from repo root; the `ingestion/` package is the production path.

## Commands

Install dependencies:
```bash
pip install -r requirements.txt
```

Run all crawlers:
```bash
python run.py --job all
```

Run individual crawlers:
```bash
python run.py --job arxiv
python run.py --job yt
python run.py --job unsplash
```

Convert downloaded subtitles to plain text (default input: `data-lake/bronze/youtube/`, searches recursively):
```bash
python ingestion/youtube/script_to_text.py
python ingestion/youtube/script_to_text.py --input data-lake/bronze/youtube/year=.../subs
python ingestion/youtube/script_to_text.py --input path/to/file.vtt --output path/to/out.txt
```

Query Silver layer with DuckDB (no server required):
```python
import duckdb
duckdb.sql("SELECT * FROM read_parquet('data-lake/silver/arxiv/**/*.parquet', hive_partitioning=true)")
```

Schedule daily run (Windows Task Scheduler):
```powershell
$action   = New-ScheduledTaskAction -Execute "python" -Argument "run.py --job all" -WorkingDirectory "D:\path\to\aio-data-ingestion"
$trigger  = New-ScheduledTaskTrigger -Daily -At 8:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd
Register-ScheduledTask -TaskName "AIO Ingestion Daily" -Action $action -Trigger $trigger -Settings $settings
```

## Architecture

### Data lake zones

```
data-lake/
├── bronze/<source>/year=YYYY/month=MM/day=DD/   raw, immutable (never modify)
├── silver/<source>/year=YYYY/month=MM/day=DD/   cleaned, typed Parquet
├── gold/run_summary/YYYY-MM-DD.json             daily summary — {"date", "runs": [...]} appended each run
└── _state/<source>_ids.parquet                  ingestion checkpoint (tracked in git)
```

`_state/` Parquet files are the deduplication source of truth — columns: `item_id`, `ingested_at`, `status`. All writes to these files are atomic (write to `.tmp`, then `os.replace()`). Bronze and Silver partitions are gitignored; `_state/` is tracked.

### Package structure

```
ingestion/
├── utils/
│   ├── dotenv.py    load_dotenv(path)
│   ├── log.py       get_logger(name) → structured file+stream logging
│   ├── retry.py     retry_call(fn, ...) — works with both googleapiclient and requests exceptions
│   └── lake.py      bronze_partition / write_bronze_json / write_silver_parquet
│                    load_ingested_ids / save_ingested_ids
├── arxiv/
│   ├── config.yaml  categories, days_back, max_results_per_category, api settings
│   └── crawler.py   main() → {"source", "status", "count", "errors"}
├── youtube/
│   ├── config.yaml       search + download + api settings
│   ├── crawler.py        main() → same shape
│   └── script_to_text.py convert .vtt/.srt → .txt (default input: data-lake/bronze/youtube/)
└── unsplash/
    ├── config.yaml  search + download + api settings
    └── crawler.py   main() → same shape
```

Each `main()` returns a result dict; `run.py` collects them and appends to `data-lake/gold/run_summary/YYYY-MM-DD.json` (re-runs the same day append to `runs[]` rather than overwrite). Logs are written to `logs/<source>_YYYY-MM-DD.log` at the repo root (gitignored).

### Per-source data flow

**arXiv**
- Fetch via arXiv Atom API (`feedparser` + `requests`)
- Bronze: `entries.json` (raw feedparser entries)
- Silver: typed Parquet — `published`/`updated` as `datetime64[UTC]`, `crawled_at` ISO string

**YouTube**
- Discover via YouTube Data API (`search.list` → `videos.list` for duration/language)
- Download via `yt-dlp` in three separate passes per video: (1) metadata + subtitles, (2) video mp4, (3) audio m4a — each pass is independent, so partial failures don't abort the others
- Bronze: media files + `search_results.json`
- Silver: metadata catalog Parquet — one row per video with paths to bronze files, `duration_s`/`view_count`/`like_count` as `Int64`

**Unsplash**
- Search via Unsplash REST API; triggers required `download_location` call per ToS
- Bronze: `search_results.json` + `images/<photo_id>.<ext>`
- Silver: typed Parquet — `created_at` as `datetime64[UTC]`, `width`/`height` as `Int64`

### API keys

| Crawler | File | Variable |
|---------|------|----------|
| YouTube | `ingestion/youtube/.env` | `YOUTUBE_API_KEY=YOUR_KEY` |
| Unsplash | `ingestion/unsplash/.env` | `ACCESS_KEY=YOUR_KEY` |

`dotenv.py` uses `os.environ.setdefault`, so an env var already set in the shell takes precedence over `.env` files.
