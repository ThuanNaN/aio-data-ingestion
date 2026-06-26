# AIO Data Ingestion

Daily crawler pipeline for AI-related content → local data lake (Bronze / Silver / Gold).

## Sources

| Job | Content | Output |
|-----|---------|--------|
| `arxiv` | ML/CV papers from arXiv API | Silver Parquet (metadata) |
| `yt` | AI videos via YouTube Data API + yt-dlp | Bronze media files + Silver catalog Parquet |
| `unsplash` | Tech images via Unsplash API | Bronze images + Silver metadata Parquet |

## Setup

```bash
pip install -r requirements.txt
```

API keys (create these files before running):

```
ingestion/youtube/.env   →  YOUTUBE_API_KEY=YOUR_YOUTUBE_DATA_API_KEY
ingestion/unsplash/.env  →  ACCESS_KEY=YOUR_UNSPLASH_ACCESS_KEY
```

## Run

```bash
python run.py --job all
python run.py --job arxiv
python run.py --job yt
python run.py --job unsplash
```

## Data lake layout

```
data-lake/
├── bronze/<source>/year=YYYY/month=MM/day=DD/   raw, immutable
├── silver/<source>/year=YYYY/month=MM/day=DD/   cleaned Parquet
├── gold/run_summary/YYYY-MM-DD.json             daily summary (appends each run)
└── _state/<source>_ids.parquet                  dedup checkpoint
```

Query Silver with DuckDB (no server required):

```python
import duckdb
duckdb.sql("SELECT * FROM read_parquet('data-lake/silver/arxiv/**/*.parquet', hive_partitioning=true)")
```

## Schedule (Windows Task Scheduler)

```powershell
$python  = "C:\Users\Admin\miniconda3\envs\crawl_vnexpress\python.exe"
$workDir = "D:\path\to\aio-data-ingestion"

$action   = New-ScheduledTaskAction -Execute $python -Argument "run.py --job all" -WorkingDirectory $workDir
$trigger  = New-ScheduledTaskTrigger -Daily -At 8:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "AIO Ingestion Daily" -Action $action -Trigger $trigger -Settings $settings
```

## Subtitle → text

```bash
python ingestion/youtube/script_to_text.py
python ingestion/youtube/script_to_text.py --input data-lake/bronze/youtube/year=.../subs
python ingestion/youtube/script_to_text.py --input path/to/file.vtt --output path/to/out.txt
```
