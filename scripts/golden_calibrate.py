#!/usr/bin/env python3
"""CORP-04: calibração empírica de tolerâncias do Golden Master (±2σ).

Método (ver ADR-0002): para cada fixture do GM, mede cada métrica no sinal
limpo e em K cópias com jitter float32 de última casa (ε = 2^-20, simulando
variação aritmética entre plataformas/máquinas). σ por (analyzer, metric) =
máximo entre fixtures; tolerância = round-up(2σ, 3 casas), piso 1e-4.
Nenhuma constante é escolhida "de cabeça" — os σ medidos ficam registrados
em tests/golden/calibration.json.

Uso:
    python scripts/golden_calibrate.py            # escreve calibration.json
    python scripts/golden_calibrate.py --apply    # também injeta tolerances
                                                  # no manifest.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audio_suite.golden import calibrate_tolerances  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="substitui o bloco `tolerances:` do manifest.yaml pelos valores calibrados",
    )
    args = parser.parse_args()

    result = calibrate_tolerances(trials=args.trials, seed=args.seed)
    n_metrics = sum(len(v) for v in result["tolerances"].values())

    payload = {
        "schema": "audio-suite/gm-calibration@1",
        "date": date.today().isoformat(),
        "method": (
            f"±2σ empírico: K={args.trials} cópias por fixture com jitter RELATIVO "
            "de 1 ulp float32 (x'=x·(1+u), u~U(-2^-23, 2^-23); zeros preservados "
            "— silêncio não vira ruído); σ máximo entre fixtures por "
            "(analyzer, metric); tolerância = ceil(2σ, 3 casas), piso 1e-4"
        ),
        "seed": args.seed,
        "trials": args.trials,
        "sigma": result["sigma"],
        "tolerances": result["tolerances"],
    }
    out = ROOT / "tests" / "golden" / "calibration.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"Calibração concluída: {n_metrics} métricas → {out}")

    if args.apply:
        manifest_path = ROOT / "tests" / "golden" / "manifest.yaml"
        text = manifest_path.read_text()
        lines = ["tolerances:"]
        for aid in sorted(result["tolerances"]):
            lines.append(f"  {aid}:")
            for metric in sorted(result["tolerances"][aid]):
                lines.append(f"    {metric}: {result['tolerances'][aid][metric]}")
        block = "\n".join(lines)
        text = re.sub(r"tolerances: \{\}", block, text)
        manifest_path.write_text(text)
        print(f"tolerances injetadas em {manifest_path}")

    # resumo legível
    print("\nTolerâncias derivadas (2σ):")
    for aid in sorted(result["tolerances"]):
        for metric in sorted(result["tolerances"][aid]):
            print(f"  {aid:26s} {metric:26s} tol={result['tolerances'][aid][metric]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
