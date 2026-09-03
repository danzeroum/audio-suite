#!/usr/bin/env python3
"""CORP-01.r — anti-binary policy: no audio binary > 1 MB may be committed.

Checks every audio file tracked by git (``git ls-files``) and fails if any
exceeds the size limit. Fixtures are ALWAYS seed-generated at install/CI time
(``tests/fixtures/generators.py``); only ``manifest.json`` is versioned.

Usage:
    python scripts/check_no_large_binaries.py [--max-bytes 1048576]

Exit codes:
    0  policy satisfied
    1  policy violated (lists offending files)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_BYTES = 1024 * 1024  # 1 MB

AUDIO_GLOBS = ["*.wav", "*.flac", "*.mp3", "*.ogg", "*.aiff", "*.aif", "*.aifc"]


def tracked_audio_files() -> list[str]:
    files: list[str] = []
    for pattern in AUDIO_GLOBS:
        out = subprocess.run(
            ["git", "ls-files", pattern],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        files.extend(line for line in out.splitlines() if line)
    return sorted(set(files))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"maximum allowed size per audio binary (default {DEFAULT_MAX_BYTES})",
    )
    args = parser.parse_args()

    offenders: list[tuple[str, int]] = []
    checked = 0
    for name in tracked_audio_files():
        p = Path(name)
        if not p.exists():
            continue  # staged deletion; nothing to enforce
        size = p.stat().st_size
        checked += 1
        if size > args.max_bytes:
            offenders.append((name, size))

    if offenders:
        sys.stderr.write("CORP-01.r violation — audio binaries above the size limit:\n")
        for name, size in sorted(offenders, key=lambda t: -t[1]):
            sys.stderr.write(f"  {name}: {size} bytes > {args.max_bytes}\n")
        sys.stderr.write(
            "Fixtures must be seed-generated (tests/fixtures/generators.py), never committed as binaries.\n"
        )
        return 1

    print(f"OK: {checked} tracked audio file(s), all <= {args.max_bytes} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
