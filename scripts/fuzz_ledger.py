#!/usr/bin/env python3
"""Ledger de fuzz do ADR-0003 (monitoramento da janela fail-open → fail-closed).

Lista cada commit do `main` desde a abertura da janela de observação
(`dd513ef`, 2026-09-03 16:50 UTC) com a conclusão do job de CI
"Fuzz decoder (TEST-03.r)". Produz a evidência exigida pelo PR de transição
fail-closed do ADR-0003 (SHAs dos runs verdes) e é a base do registro no
ADR-0005 (avaliação de gatilhos de itens arquivados).

Uso:
    GITHUB_TOKEN=... python3 scripts/fuzz_ledger.py [--repo OWNER/NAME]

Token fine-grained mínimo: Contents: read (o repositório público também
funciona sem token, sujeito a rate limit). Sem dependências externas
(stdlib pura).
"""

import argparse
import json
import os
import sys
import urllib.request

# Abertura da janela de observação do ADR-0003 (merge do TEST-03.r)
WINDOW_SINCE = "2026-09-03T16:50:00Z"
FUZZ_JOB = "Fuzz decoder (TEST-03.r)"
DATA_ALVO = "2026-09-14"


def api(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "audio-suite-fuzz-ledger",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="danzeroum/audio-suite")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    commits = api(
        f"https://api.github.com/repos/{args.repo}/commits?sha=main&since={WINDOW_SINCE}&per_page=100",
        token,
    )
    print(f"ADR-0003 — janela {WINDOW_SINCE[:10]} → +7 dias (data-alvo {DATA_ALVO})")
    print(f"{'commit':10} | {'data (UTC)':19} | fuzz | msg")
    print("-" * 95)
    green = crash = pending = 0
    green_shas: list[str] = []
    for c in commits:
        sha = c["sha"]
        date = c["commit"]["committer"]["date"][:19]
        msg = c["commit"]["message"].splitlines()[0][:40]
        runs = api(
            f"https://api.github.com/repos/{args.repo}/commits/{sha}/check-runs?per_page=100",
            token,
        ).get("check_runs", [])
        fuzz = [r for r in runs if r["name"] == FUZZ_JOB]
        concl = fuzz[0]["conclusion"] or fuzz[0]["status"] if fuzz else "AUSENTE"
        mark = {"success": "OK", "skipped": "SKIP"}.get(concl, concl.upper())
        if concl == "success":
            green += 1
            green_shas.append(sha)
        elif concl in ("failure", "timed_out", "action_required"):
            crash += 1
        else:
            pending += 1
        print(f"{sha[:8]:10} | {date:19} | {mark:8} | {msg}")
    print("-" * 95)
    print(f"runs verdes: {green} | falhas: {crash} | pendentes/ausentes: {pending}")
    if crash:
        print(
            "RESULTADO: crash na janela — pelo ADR-0003, fail-closed antecipado "
            "(crash vira bloqueante com issue rastreando)."
        )
        return 1
    if green >= 7:
        print(
            f"RESULTADO: {green} runs verdes (≥7) — PR de transição fail-closed "
            "pode citar os SHAs abaixo como ledger."
        )
        print("\n".join(green_shas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
