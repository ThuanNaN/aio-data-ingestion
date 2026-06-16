# arXiv Daily Crawler

Automatically crawl new papers from arXiv API based on configured topics.
## Installation

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Configuration

Edit `config.yaml` to change:
- `categories`: List of categories to crawl (e.g., cs.LG, cs.CV, cs.AI)
- `max_results_per_category`: Max papers per category
- `days_back`: Number of days back to fetch papers

Reference category list: https://arxiv.org/category_taxonomy

## Usage

### Manual Run

From this folder:

```bash
python crawl_arxiv.py
```

From repo root (unified cronjob):

```bash
python crawl_with_cronjob.py --job arxiv
```

### Setup Windows Task Scheduler (Auto-run daily)

For **all crawlers** (arxiv + yt + unsplash), see the root guide: `../README.md`

#### arXiv only (PowerShell)

Open PowerShell as Administrator and run:

```powershell
$python = "C:\Users\Admin\miniconda3\envs\crawl_vnexpress\python.exe"
$workDir = "D:\STA-Tasks\crawl_papers"

$action = New-ScheduledTaskAction `
  -Execute $python `
  -Argument "crawl_with_cronjob.py --job arxiv" `
  -WorkingDirectory $workDir

$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask `
  -TaskName "arXiv Daily Crawler" `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Description "Crawl new papers from arXiv daily"
```

#### Check if task was created

```powershell
Get-ScheduledTask -TaskName "arXiv Daily Crawler"
```

#### Run task immediately (test)

```powershell
Start-ScheduledTask -TaskName "arXiv Daily Crawler"
```

#### Delete task

```powershell
Unregister-ScheduledTask -TaskName "arXiv Daily Crawler" -Confirm:$false
```

## Directory Structure

```
crawl_arxiv/
├── crawl_arxiv.py        # Main script
├── config.yaml             # Configuration
├── README.md               # This guide
├── data/                   # Output CSV files
│   └── papers_YYYY-MM-DD.csv
└── logs/                   # Log files
    └── crawl_YYYY-MM-DD.log
```

## Output

A new CSV file is created daily in `data/` folder with format: `papers_YYYY-MM-DD.csv`

CSV columns:
- `arxiv_id`: Paper ID on arXiv
- `title`: Title
- `authors`: List of authors
- `abstract`: Abstract
- `categories`: Paper categories
- `published`: Publication date
- `updated`: Last update date
- `pdf_url`: PDF download link
- `primary_category`: Primary queried category

## Logs

Logs are saved in `logs/` folder with format: `crawl_YYYY-MM-DD.log`
