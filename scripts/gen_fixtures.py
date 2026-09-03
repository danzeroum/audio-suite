"""Deterministic fixture generator for audio-suite tests (CORP-01.r).

Thin wrapper: the canonical, seed-based generators live in
``tests/fixtures/generators.py`` — this script only materializes the corpus
on disk (WAV files + manifest.json).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.generators import write_fixtures  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "generated"


def main() -> None:
    manifest_path = write_fixtures(FIXTURE_DIR)
    n = len(list(FIXTURE_DIR.glob("*.wav"))) + len(list(FIXTURE_DIR.glob("*.txt")))
    print(f"Generated {n} fixtures in {FIXTURE_DIR}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
