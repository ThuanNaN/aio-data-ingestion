#!/usr/bin/env python3
"""
Unified cronjob entrypoint for the repo.

Runs one or more crawlers:
  - arxiv:     crawl_arxiv/crawl_arxiv.py
  - yt:        crawl_yt_video_audio/main.py
  - unsplash:  crawl_unsplash_image/main.py

Examples:
  python crawl_with_cronjob.py --job all
  python crawl_with_cronjob.py --job arxiv
  python crawl_with_cronjob.py --job yt --job unsplash

Notes:
  - This script uses the current Python interpreter (sys.executable).
  - Activate your conda/venv in the scheduler before running.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def run_python(rel_path: str) -> int:
    script = (REPO_ROOT / rel_path).resolve()
    cmd = [sys.executable, str(script)]
    print(f"[cronjob] Running: {cmd}")
    p = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    return int(p.returncode or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified cronjob entrypoint")
    parser.add_argument(
        "--job",
        action="append",
        default=[],
        help="Which job(s) to run: arxiv | yt | unsplash | all. Can be repeated.",
    )
    args = parser.parse_args(argv)

    jobs = [j.strip().lower() for j in (args.job or []) if str(j).strip()]
    if not jobs:
        jobs = ["all"]

    if "all" in jobs:
        jobs = ["arxiv", "yt", "unsplash"]

    rc = 0
    for job in jobs:
        if job == "arxiv":
            r = run_python("crawl_arxiv/crawl_arxiv.py")
        elif job == "yt":
            r = run_python("crawl_yt_video_audio/main.py")
        elif job == "unsplash":
            r = run_python("crawl_unsplash_image/main.py")
        else:
            print(f"[cronjob] Unknown job: {job!r} (skip)")
            r = 0

        if r != 0 and rc == 0:
            rc = r

    return rc


if __name__ == "__main__":
    raise SystemExit(main())

