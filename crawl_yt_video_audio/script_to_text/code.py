"""
Convert subtitle files (.vtt / .srt) to plain text (.txt).

Default layout (from crawl_yt_video_audio/main.py):
  downloads/YYYY-MM-DD/subs/<video_id>.<lang>.vtt
  -> downloads/YYYY-MM-DD/text/<video_id>.txt

Usage:
  python script_to_text/code.py
  python script_to_text/code.py --input downloads/2026-06-16/subs
  python script_to_text/code.py --input path/to/file.vtt --output path/to/out.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOADS = SCRIPT_DIR / "downloads"

_INLINE_TS = re.compile(r"<\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?>")
_HTML_TAG = re.compile(r"<[^>]+>")


def _clean_caption_line(line: str) -> str:
    line = _INLINE_TS.sub("", line)
    line = _HTML_TAG.sub("", line)
    return " ".join(line.split()).strip()


def _is_timestamp_line(line: str) -> bool:
    return "-->" in line


def _is_header_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s == "WEBVTT":
        return True
    if s.startswith("Kind:") or s.startswith("Language:"):
        return True
    if s.startswith("NOTE"):
        return True
    return False


def parse_subtitle_text(content: str) -> list[str]:
    """Extract readable caption lines from VTT or SRT content."""
    lines_out: list[str] = []
    prev: str | None = None

    for raw in content.splitlines():
        s = raw.strip()
        if _is_header_line(s) or _is_timestamp_line(s):
            continue
        if s.isdigit():
            continue

        text = _clean_caption_line(s)
        if not text:
            continue
        if text == prev:
            continue

        lines_out.append(text)
        prev = text

    return lines_out


def subtitle_to_txt(content: str) -> str:
    return "\n".join(parse_subtitle_text(content))


def video_id_from_sub_path(path: Path) -> str:
    # e.g. 1r5fBgzpKOI.en.en.vtt -> 1r5fBgzpKOI
    return path.name.split(".", 1)[0]


def default_output_path(sub_path: Path) -> Path:
    # .../downloads/YYYY-MM-DD/subs/foo.vtt -> .../downloads/YYYY-MM-DD/text/foo.txt
    day_dir = sub_path.parent.parent
    text_dir = day_dir / "text"
    return text_dir / f"{video_id_from_sub_path(sub_path)}.txt"


def iter_subtitle_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in {".vtt", ".srt"} else []
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in {".vtt", ".srt"}
    )


def convert_file(sub_path: Path, output_path: Path | None = None) -> Path:
    out = output_path or default_output_path(sub_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    text = subtitle_to_txt(sub_path.read_text(encoding="utf-8", errors="replace"))
    out.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return out


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    under_script = (SCRIPT_DIR / path).resolve()
    if under_script.exists():
        return under_script
    return (Path.cwd() / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert subtitle files to plain .txt")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_DOWNLOADS,
        help="Subtitle file or directory (default: downloads/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .txt file (only when --input is a single file)",
    )
    args = parser.parse_args()

    input_path: Path = resolve_path(args.input)

    if args.output and input_path.is_dir():
        print("Error: --output only applies when --input is a single subtitle file.")
        return 2

    files = iter_subtitle_files(input_path)
    if not files:
        print(f"No .vtt/.srt files found under: {input_path}")
        return 1

    for sub_path in files:
        out_path = convert_file(sub_path, args.output if input_path.is_file() else None)
        print(f"Wrote: {out_path.relative_to(SCRIPT_DIR)}")

    print(f"Done. Converted {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
