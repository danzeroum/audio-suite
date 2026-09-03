#!/usr/bin/env python3
"""CORP-04.r — guard de regeneração de golden files.

Regra: um PR que altere `tests/golden/expected/**` (ou as tolerâncias do
manifest GM) precisa:
  1. da label `golden-regen` (revisão humana), e
  2. de justificativa no CHANGELOG (patch do CHANGELOG menciona "golden").

Em GitHub Actions (variáveis GITHUB_*+PR_NUMBER presentes) a checagem é
bloqueante via API. Fora do Actions (uso local/pre-commit), avalia o diff
contra origin/main e apenas avisa sobre a label.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request

GOLDEN_PATHS = ("tests/golden/expected/", "tests/golden/manifest.yaml", "tests/golden/gm_profile.yaml")


def _api(url: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {os.environ['GITHUB_TOKEN']}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _changed_files_ci() -> list[dict]:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = os.environ["PR_NUMBER"]
    files = []
    page = 1
    while True:
        chunk = _api(f"https://api.github.com/repos/{repo}/pulls/{pr}/files?per_page=100&page={page}")
        files.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return files


def _changed_files_local() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        return []
    return [line for line in out.stdout.splitlines() if line]


def main() -> int:
    ci = bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("PR_NUMBER"))

    if ci:
        files = _changed_files_ci()
        golden_files = [f["filename"] for f in files if f["filename"].startswith(GOLDEN_PATHS)]
        changelog_patch = next((f.get("patch", "") for f in files if f["filename"] == "CHANGELOG.md"), "")
        repo = os.environ["GITHUB_REPOSITORY"]
        pr = os.environ["PR_NUMBER"]
        labels = [lb["name"] for lb in _api(f"https://api.github.com/repos/{repo}/pulls/{pr}")["labels"]]
    else:
        names = _changed_files_local()
        golden_files = [n for n in names if n.startswith(GOLDEN_PATHS)]
        changelog_patch = ""
        if "CHANGELOG.md" in names:
            patch = subprocess.run(
                ["git", "diff", "origin/main...HEAD", "--", "CHANGELOG.md"],
                capture_output=True,
                text=True,
            )
            changelog_patch = patch.stdout
        labels = []

    if not golden_files:
        print("golden-guard: nenhum golden file alterado — OK")
        return 0

    errors: list[str] = []
    if "golden-regen" not in labels:
        errors.append(
            "PR altera golden files sem a label 'golden-regen' — regeneração exige revisão humana (CORP-04.r)"
        )
    if not re.search(r"golden", changelog_patch, re.IGNORECASE):
        errors.append(
            "PR altera golden files sem justificativa no CHANGELOG (mencione 'golden' com a justificativa)"
        )

    if errors:
        for e in errors:
            sys.stderr.write(f"golden-guard: FALHA — {e}\n")
        sys.stderr.write(
            "Se a mudança é intencional: rode `audio-suite golden freeze`, adicione a label "
            "'golden-regen' e justifique a regeneração no CHANGELOG.\n"
        )
        return 1

    print(f"golden-guard: {len(golden_files)} golden file(s) alterados com label + CHANGELOG — OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
