

# Crawl Papers – Daily Scheduler (Unified Cronjob)

## Flow

![Crawl Papers architecture](https://res.cloudinary.com/dptjhpkmv/image/upload/v1781624195/project_crawl_vgoskv.png)

Run all crawlers from one entrypoint: `crawl_with_cronjob.py`

| Job | Script |
|-----|--------|
| `arxiv` | `crawl_arxiv/crawl_arxiv.py` |
| `yt` | `crawl_yt_video_audio/main.py` |
| `unsplash` | `crawl_unsplash_image/main.py` |
| `all` | runs all three in order |

## Prerequisites

- Python env with dependencies installed (e.g. conda env `crawl_vnexpress`)
- API keys in `.env` files:
  - `crawl_yt_video_audio/.env` → YouTube Data API key (`key=...`)
  - `crawl_unsplash_image/.env` → Unsplash access key (`ACCESS_KEY=...`)

## Manual Run

From repo root:

```powershell
cd D:\STA-Tasks\crawl_papers
conda activate crawl_vnexpress
python crawl_with_cronjob.py --job all
```

Run a single job:

```powershell
python crawl_with_cronjob.py --job arxiv
python crawl_with_cronjob.py --job yt
python crawl_with_cronjob.py --job unsplash
```

## Setup Windows Task Scheduler (Auto-run daily)

### Using Command Line (PowerShell)

Open PowerShell as Administrator and run:

```powershell
$python = "C:\Users\Admin\miniconda3\envs\crawl_vnexpress\python.exe"
$workDir = "D:\STA-Tasks\crawl_papers"

$action = New-ScheduledTaskAction `
  -Execute $python `
  -Argument "crawl_with_cronjob.py --job all" `
  -WorkingDirectory $workDir

$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask `
  -TaskName "Crawl Papers Daily" `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Run arxiv + yt + unsplash crawlers daily"
```

> Adjust `-At 8:00AM` to your preferred time.  
> Update `$python` if your conda env path is different.

#### Alternative: activate conda via cmd

```powershell
$action = New-ScheduledTaskAction `
  -Execute "cmd" `
  -Argument "/c C:\Users\Admin\miniconda3\condabin\conda.bat activate crawl_vnexpress && python crawl_with_cronjob.py --job all" `
  -WorkingDirectory "D:\STA-Tasks\crawl_papers"
```

### Check if task was created

```powershell
Get-ScheduledTask -TaskName "Crawl Papers Daily"
```

### Run task immediately (test)

```powershell
Start-ScheduledTask -TaskName "Crawl Papers Daily"
```

### Delete task

```powershell
Unregister-ScheduledTask -TaskName "Crawl Papers Daily" -Confirm:$false
```

## Directory Structure

```
crawl_papers/
├── crawl_with_cronjob.py       # Unified entrypoint (use this for scheduler)
├── crawl_arxiv/
│   ├── crawl_arxiv.py
│   ├── config.yaml
│   ├── data/papers_YYYY-MM-DD.csv
│   └── logs/crawl_YYYY-MM-DD.log
├── crawl_yt_video_audio/
│   ├── main.py
│   ├── config.yaml
│   └── downloads/YYYY-MM-DD/{video,audio,subs,info}/
└── crawl_unsplash_image/
    ├── main.py
    └── downloads/YYYY-MM-DD/*.jpg
```

## Per-module docs

- arXiv: `crawl_arxiv/README.md`
- YouTube: `crawl_yt_video_audio/README.md`
- Unsplash: `crawl_unsplash_image/README.md`
