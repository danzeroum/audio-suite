#!/usr/bin/env python3
"""GOV-13 — sync do backlog ↔ GitHub Issues (idempotente).

Materializa os IDs do Documento Mestre (backlog.yaml) como issues, com labels
`onda/<N>` e `prio/<pN>`.

Idempotência: cada issue carrega um marker oculto no corpo —
`<!-- audio-suite-backlog: <ID> -->` — que é a chave de busca. Reexecutar o
script não cria duplicatas; muda título/labels apenas se divergirem.

Requisitos do token (fine-grained): Issues: **read+write** (criar e editar)
e Labels: read+write. Com token somente-leitura, o script detecta as issues
existentes, reporta o que precisaria mudar e segue em frente (aviso por issue).

Uso:
    GITHUB_TOKEN=... python scripts/sync_issues.py [--repo danzeroum/audio-suite] [--dry-run]

Nota: itens "archived_with_trigger" NÃO viram issues por padrão (são
arquivados com gatilho; virar issue sugere que há trabalho a fazer). Use
--include-archived para materializá-los com label `archived/trigger`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MARKER_FMT = "<!-- audio-suite-backlog: {id} -->"


def _api(method: str, url: str, payload: dict | None = None, token: str = "", retries: int = 3) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "audio-suite-backlog-sync")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}  # recurso inexistente (ex.: label ainda não criada)
        if exc.code == 403 and retries > 0:
            # rate limit secundário: respeita Retry-After e tenta de novo
            wait = int(exc.headers.get("Retry-After", "10")) or 10
            time.sleep(min(wait, 30))
            return _api(method, url, payload, token, retries - 1)
        detail = ""
        try:
            detail = exc.read().decode()[:400]
        except Exception:  # noqa: BLE001
            pass
        sys.stderr.write(f"API {method} {url} → HTTP {exc.code}: {detail}\n")
        raise


def _ensure_label(repo: str, token: str, name: str, color: str, description: str, dry: bool) -> None:
    if not token:
        if dry:
            print(f"[dry-run] criaria label (se não existir): {name}")
        return
    res = _api("GET", f"https://api.github.com/repos/{repo}/labels/{name}", token=token)
    if res.get("name"):
        return
    if dry:
        print(f"[dry-run] criaria label: {name}")
        return
    try:
        _api(
            "POST",
            f"https://api.github.com/repos/{repo}/labels",
            {"name": name, "color": color, "description": description},
            token,
        )
        print(f"label criada: {name}")
    except Exception as exc:  # noqa: BLE001
        print(f"aviso: não criei label {name}: {exc}")


def _find_issue_by_marker(repo: str, token: str, marker: str) -> dict | None:
    """Procura o marker listando as issues do repo (evita quirks da search API)."""
    page = 1
    while True:
        res = _api(
            "GET",
            f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100&page={page}",
            token=token,
        )
        if not res:
            return None
        for it in res:
            if marker in (it.get("body") or ""):
                return it
        if len(res) < 100:
            return None
        page += 1


def _body_for(item: dict, marker: str) -> str:
    note = f"\n\n> {item['note']}" if item.get("note") else ""
    return (
        f"Item do backlog do Documento Mestre v1.2 (Adendo B, Parte VI).{note}\n\n"
        f"**Onda:** {item['onda']} · **Prioridade:** {item['prio']}\n\n"
        f"Regras aplicáveis: ver `AGENTS.md` e `docs/adr/`.\n\n{marker}\n"
    )


def sync(repo: str, token: str, dry_run: bool, include_archived: bool) -> int:
    backlog = yaml.safe_load((ROOT / "backlog.yaml").read_text(encoding="utf-8"))
    labels_cfg = backlog.get("labels", {})

    # garante labels onda/1..5 e prio/p0..p3
    for onda in (3, 4, 5):
        _ensure_label(
            repo,
            token,
            f"onda/{onda}",
            labels_cfg.get("onda", {}).get("color", "1d76db"),
            labels_cfg.get("onda", {}).get("description", ""),
            dry_run,
        )
    for prio in ("p0", "p1", "p2", "p3"):
        _ensure_label(
            repo,
            token,
            f"prio/{prio}",
            labels_cfg.get("prio", {}).get("color", "d93f0b"),
            labels_cfg.get("prio", {}).get("description", ""),
            dry_run,
        )

    items = list(backlog.get("items", []))
    if include_archived:
        items += list(backlog.get("archived_with_trigger", []))

    created = updated = unchanged = denied = 0
    for item in items:
        marker = MARKER_FMT.format(id=item["id"])
        wanted_labels = [f"onda/{item['onda']}", f"prio/{item['prio']}"]
        if include_archived and item.get("note"):
            wanted_labels.append("archived/trigger")

        existing = _find_issue_by_marker(repo, token, marker)
        time.sleep(0.3)  # cortesia com a API (rate limit secundário)
        if existing is None:
            if dry_run:
                print(f"[dry-run] criaria issue: {item['id']} — {item['title']}")
                created += 1
                continue
            issue = _api(
                "POST",
                f"https://api.github.com/repos/{repo}/issues",
                {"title": item["title"], "body": _body_for(item, marker), "labels": wanted_labels},
                token,
            )
            print(f"criada: #{issue['number']} {item['id']}")
            created += 1
        else:
            changes: dict = {}
            if existing["title"] != item["title"]:
                changes["title"] = item["title"]
            current_labels = {lb["name"] for lb in existing.get("labels", [])}
            if not set(wanted_labels).issubset(current_labels):
                changes["labels"] = sorted(current_labels | set(wanted_labels))
            if not changes:
                unchanged += 1
                continue
            if dry_run:
                print(f"[dry-run] atualizaria #{existing['number']} {item['id']}: {list(changes)}")
                updated += 1
                continue
            try:
                _api(
                    "PATCH",
                    f"https://api.github.com/repos/{repo}/issues/{existing['number']}",
                    changes,
                    token,
                )
                print(f"atualizada: #{existing['number']} {item['id']} ({list(changes)})")
                updated += 1
            except Exception as exc:  # noqa: BLE001
                denied += 1
                print(
                    f"aviso: #{existing['number']} {item['id']} não atualizada "
                    f"(permissão do token insuficiente): {exc}"
                )

    print(
        f"\nresumo: {created} criada(s), {updated} atualizada(s), "
        f"{unchanged} inalterada(s), {denied} sem permissão"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "danzeroum/audio-suite"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="materializa também os itens arquivados com gatilho (label archived/trigger)",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token and not args.dry_run:
        sys.stderr.write("GITHUB_TOKEN ausente (ou use --dry-run)\n")
        return 64
    return sync(args.repo, token, args.dry_run, args.include_archived)


if __name__ == "__main__":
    sys.exit(main())
