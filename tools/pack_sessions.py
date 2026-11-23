"""Pack your Claude Code transcripts for hand-in, and check them for API keys.

    python tools/pack_sessions.py                # finds this repo's transcripts automatically
    python tools/pack_sessions.py --from DIR     # if it can't find them, point it at the folder

Claude Code keeps every session's full transcript (including the parts it compacted) as
.jsonl files in ~/.claude/projects/<this folder's path, with every non-letter/digit
replaced by "-">/. This script zips all of them into claude-sessions/transcripts.zip.

It refuses to run if anything in the repo (your /export files included) looks like an
Anthropic API key. If a key shows up inside a transcript, it is replaced with
sk-ant-REDACTED in the zip (your originals aren't touched), and you should tell us.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "claude-sessions"
OUT_ZIP = OUT_DIR / "transcripts.zip"
KEY = re.compile(rb"sk-ant-[A-Za-z0-9_\-]{20,}")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def find_transcript_dir() -> Path | None:
    projects = claude_home() / "projects"
    name = re.sub(r"[^A-Za-z0-9]", "-", str(REPO))
    exact = projects / name
    if exact.is_dir():
        return exact
    # Very long paths are shortened by Claude Code; fall back to a prefix match.
    if projects.is_dir():
        matches = [d for d in projects.iterdir() if d.is_dir() and d.name.startswith(name[:120])]
        if len(matches) == 1:
            return matches[0]
    return None


def key_hits(path: Path) -> list[str]:
    hits = []
    try:
        data = path.read_bytes()
    except OSError:
        return hits
    for m in KEY.finditer(data):
        line = data.count(b"\n", 0, m.start()) + 1
        hits.append(f"{path}:{line}: {m.group()[:14].decode()}...")
    return hits


def repo_files() -> list[Path]:
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = Path(root) / f
            if p != OUT_ZIP and p.name != ".env":
                out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", type=Path, help="folder holding this repo's .jsonl transcripts")
    args = ap.parse_args()

    src = args.src or find_transcript_dir()
    if not src or not src.is_dir():
        print("Couldn't find your Claude Code transcripts for this folder.")
        print(f"Look in {claude_home() / 'projects'} for the folder named after this repo's path,")
        print("then run: python tools/pack_sessions.py --from <that folder>")
        print("(Did you always start Claude Code from the repo root?)")
        return 1

    transcripts = sorted(src.rglob("*.jsonl"))
    if not transcripts:
        print(f"No .jsonl transcripts in {src}.")
        return 1

    hits = [h for p in repo_files() for h in key_hits(p)]
    if hits:
        print("Found what looks like an API key in the repo. Nothing was written.")
        print("Remove it from these files (and from git history if it was committed), then run this again:")
        for h in hits:
            print("  " + h)
        return 1

    exports = sorted(OUT_DIR.glob("*.txt")) if OUT_DIR.is_dir() else []
    OUT_DIR.mkdir(exist_ok=True)
    redacted = 0
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in transcripts:
            data, n = KEY.subn(b"sk-ant-REDACTED", p.read_bytes())
            redacted += n
            z.writestr(p.relative_to(src).as_posix(), data)

    raw = sum(p.stat().st_size for p in transcripts)
    print(f"Packed {len(transcripts)} transcript file(s) from {src}")
    print(f"  {raw / 1e6:.1f} MB -> {OUT_ZIP.relative_to(REPO)} ({OUT_ZIP.stat().st_size / 1e6:.1f} MB)")
    print(f"  /export files in claude-sessions/: {len(exports)}")
    if not exports:
        print("  Warning: no /export .txt files yet. Export each session too (see README).")
    if redacted:
        print(f"  Your API key appeared {redacted} time(s) in the transcripts. It was replaced with")
        print("  sk-ant-REDACTED inside the zip. Tell us, so we can switch that key off and send a new one.")
    print("Done. Commit claude-sessions/ and push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
