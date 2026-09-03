"""Golden Master de processo (CORP-04 + CORP-04.r).

Um Golden Master captura, para um conjunto fixo de fixtures seed-based e um
conjunto fixo de analyzers-core, as métricas numéricas esperadas por fixture.
Qualquer mudança de comportamento (ex.: off-by-one no oversampling do true
peak) produz um diff legível e reprova o PR.

Política (resumo; ver ADR-0002):
  - Tolerâncias POR ANALYZER, derivadas empiricamente (±2σ do corpus de
    calibração via jitter float32 — `scripts/golden_calibrate.py`).
    Nunca hard-code "0.05".
  - `audio-suite golden freeze` regenera os esperados; PRs que regenerem
    golden files exigem label `golden-regen` + justificativa no CHANGELOG
    (revisão humana; guard em .github/workflows/golden-guard.yml).
  - Diffs são publicados como artifacts: gm-diff.json + gm-diff.html.
  - Golden files não são bit-a-bit entre linguagens: a comparação é numérica
    com tolerância (nunca igualdade exata de floats cross-language).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .analyzers import all_analyzers
from .decode import decode
from .models import PCM, Finding
from .policy import load_profile
from .rule_ids import get_rule_id

# Os 10 analyzers-core do Golden Master (descriptors = família de descritores)
GM_ANALYZER_IDS: list[str] = [
    "loudness",
    "true_peak",
    "clipping",
    "glitch",
    "lra",
    "spectral_health",
    "transient",
    "mono_compat",
    # família descriptors (conta como o grupo "descriptors"):
    "timbre_distance",
    "harmonic_tension",
    "spectral_irregularity",
    "inharmonicity",
    "fatigue_index",
    "rhythmic_grid_alignment",
    "melodic_contour",
    # metadados:
    "inspect",
]

GM_PROFILE_PATH = "tests/golden/gm_profile.yaml"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "tests" / "golden" / "manifest.yaml"
DEFAULT_EXPECTED_DIR = REPO_ROOT / "tests" / "golden" / "expected"


# ---------------------------------------------------------------------------
# Execução do conjunto GM
# ---------------------------------------------------------------------------
def gm_analyzers() -> dict[str, Any]:
    """Registered analyzers that participate in the Golden Master."""
    registry = all_analyzers()
    missing = [aid for aid in GM_ANALYZER_IDS if aid not in registry]
    if missing:
        raise RuntimeError(f"GM analyzers not registered: {missing}")
    return {aid: registry[aid] for aid in GM_ANALYZER_IDS}


def load_gm_profile(profile_path: str | Path | None = None):
    """Load the pinned GM profile (params come from this file, not defaults)."""
    p = Path(profile_path) if profile_path else REPO_ROOT / GM_PROFILE_PATH
    return load_profile(p)


def run_gm_fixture(audio: PCM, profile) -> dict[str, list[dict[str, Any]]]:
    """Run every GM analyzer over one fixture; return canonical findings.

    Returns: {analyzer_id: [canonical_finding_dict, ...]} (sorted, rounded).
    """
    out: dict[str, list[dict[str, Any]]] = {}
    registry = gm_analyzers()
    for aid in GM_ANALYZER_IDS:
        analyzer = registry[aid]
        params = profile.analyzer_params(aid)
        if not analyzer.applicable(audio, profile):
            out[aid] = []
            continue
        findings = analyzer.analyze(audio, params)
        out[aid] = sorted(
            (_canonical_finding(f) for f in findings),
            key=lambda d: (d["check_id"], d["metric"], d["value"] or 0.0),
        )
    return out


def _canonical_finding(f: Finding) -> dict[str, Any]:
    rule_id = get_rule_id(f.analyzer, f.metric)
    return {
        "check_id": f.check_id,
        "metric": f.metric,
        "value": round(float(f.value), 6) if f.value is not None else None,
        "unit": f.unit,
        "status": f.status.value,
        "rule_id": rule_id,
        # message is stored for human readability but NOT compared by the GM
        "message": f.message,
    }


# Campos comparados pelo GM (message é documental apenas)
GM_COMPARED_KEYS = ("check_id", "metric", "value", "unit", "status", "rule_id")


# ---------------------------------------------------------------------------
# Expected files (freeze) e comparação (verify)
# ---------------------------------------------------------------------------
def freeze_expected(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    expected_dir: str | Path = DEFAULT_EXPECTED_DIR,
) -> Path:
    """Regenerate tests/golden/expected/<analyzer>.json from current code."""
    manifest = load_golden_manifest(manifest_path)
    profile = load_gm_profile(manifest.get("profile", GM_PROFILE_PATH))
    fixtures_dir = Path(manifest.get("fixtures_dir", "tests/fixtures/generated"))
    if not Path(fixtures_dir).is_absolute():
        fixtures_dir = REPO_ROOT / fixtures_dir

    per_analyzer: dict[str, dict[str, Any]] = {
        aid: {"analyzer": aid, "version": gm_analyzers()[aid].VERSION, "fixtures": {}}
        for aid in GM_ANALYZER_IDS
    }
    corpus_hashes: dict[str, str] = {}
    for name in manifest["fixtures"]:
        path = fixtures_dir / name
        audio = decode(path)
        corpus_hashes[name] = audio.file_sha256
        results = run_gm_fixture(audio, profile)
        for aid, findings in results.items():
            per_analyzer[aid]["fixtures"][name] = findings

    corpus_hash = hashlib.sha256(json.dumps(corpus_hashes, sort_keys=True).encode()).hexdigest()
    for aid, payload in per_analyzer.items():
        payload["provenance"] = {
            "manifest_sha256": _sha256_of_file(manifest_path),
            "corpus_sha256": corpus_hash,
            "profile": manifest.get("profile", GM_PROFILE_PATH),
            "note": "regenerated by 'audio-suite golden freeze' — requires label golden-regen",
        }
        out_path = Path(expected_dir) / f"{aid}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return Path(expected_dir)


def _sha256_of_file(p: str | Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_golden_manifest(path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "fixtures" not in raw:
        raise ValueError(f"golden manifest inválido: {path}")
    return raw


@dataclass
class GMViolation:
    """One human-readable Golden Master violation."""

    fixture: str
    analyzer: str
    kind: str  # missing_finding | extra_finding | value_drift | status_change | rule_id_change
    check_id: str = ""
    metric: str = ""
    detail: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture,
            "analyzer": self.analyzer,
            "kind": self.kind,
            "check_id": self.check_id,
            "metric": self.metric,
            "detail": self.detail,
        }


def compare_fixture(
    fixture: str,
    expected_by_analyzer: dict[str, list[dict[str, Any]]],
    actual_by_analyzer: dict[str, list[dict[str, Any]]],
    tolerances: dict[str, dict[str, float]],
) -> list[GMViolation]:
    """Compare one fixture's actual GM results against expected, per analyzer."""
    violations: list[GMViolation] = []
    for aid in GM_ANALYZER_IDS:
        expected_list = expected_by_analyzer.get(aid, [])
        actual_list = actual_by_analyzer.get(aid, [])
        tol_map = tolerances.get(aid, {})
        tol_default = float(tol_map.get("*", 0.0))

        def key(d: dict[str, Any]) -> tuple[str, str]:
            return (d.get("check_id", ""), d.get("metric", ""))

        exp_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for d in expected_list:
            exp_by_key.setdefault(key(d), []).append(d)
        act_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for d in actual_list:
            act_by_key.setdefault(key(d), []).append(d)

        for k in sorted(set(exp_by_key) | set(act_by_key)):
            exp_items = exp_by_key.get(k, [])
            act_items = act_by_key.get(k, [])
            if not act_items:
                violations.append(
                    GMViolation(fixture, aid, "missing_finding", k[0], k[1], "finding sumiu do output atual")
                )
                continue
            if not exp_items:
                violations.append(
                    GMViolation(
                        fixture, aid, "extra_finding", k[0], k[1], "finding novo não presente no golden"
                    )
                )
                continue
            if len(exp_items) != len(act_items):
                violations.append(
                    GMViolation(
                        fixture,
                        aid,
                        "value_drift",
                        k[0],
                        k[1],
                        f"multiplicidade {len(exp_items)} → {len(act_items)}",
                    )
                )
                continue
            for e, a in zip(exp_items, act_items):
                tol = float(tol_map.get(e.get("metric", ""), tol_default))
                ev, av = e.get("value"), a.get("value")
                if (ev is None) != (av is None):
                    violations.append(
                        GMViolation(
                            fixture,
                            aid,
                            "value_drift",
                            k[0],
                            k[1],
                            f"value None↔número: expected={ev} actual={av} (tol={tol})",
                        )
                    )
                elif ev is not None and math.isfinite(ev) and math.isfinite(av):
                    delta = abs(av - ev)
                    if delta > tol:
                        violations.append(
                            GMViolation(
                                fixture,
                                aid,
                                "value_drift",
                                k[0],
                                k[1],
                                f"expected={ev} actual={av} |Δ|={delta:.6g} > tol={tol}",
                            )
                        )
                if e.get("status") != a.get("status"):
                    violations.append(
                        GMViolation(
                            fixture,
                            aid,
                            "status_change",
                            k[0],
                            k[1],
                            f"status {e.get('status')} → {a.get('status')}",
                        )
                    )
                if e.get("rule_id") != a.get("rule_id"):
                    violations.append(
                        GMViolation(
                            fixture,
                            aid,
                            "rule_id_change",
                            k[0],
                            k[1],
                            f"rule_id {e.get('rule_id')} → {a.get('rule_id')} (CONTR-02)",
                        )
                    )
    return violations


def verify_golden(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    expected_dir: str | Path = DEFAULT_EXPECTED_DIR,
    diff_dir: str | Path | None = None,
) -> tuple[list[GMViolation], dict[str, Any]]:
    """Run the full GM suite; return (violations, summary). Writes diff artifacts."""
    manifest = load_golden_manifest(manifest_path)
    profile = load_gm_profile(manifest.get("profile", GM_PROFILE_PATH))
    fixtures_dir = Path(manifest.get("fixtures_dir", "tests/fixtures/generated"))
    if not Path(fixtures_dir).is_absolute():
        fixtures_dir = REPO_ROOT / fixtures_dir
    tolerances = manifest.get("tolerances", {})

    all_violations: list[GMViolation] = []
    per_fixture_status: dict[str, str] = {}
    for name in manifest["fixtures"]:
        audio = decode(fixtures_dir / name)
        actual = run_gm_fixture(audio, profile)
        expected_by_analyzer: dict[str, list[dict[str, Any]]] = {}
        for aid in GM_ANALYZER_IDS:
            efile = Path(expected_dir) / f"{aid}.json"
            payload = json.loads(efile.read_text())
            expected_by_analyzer[aid] = payload.get("fixtures", {}).get(name, [])
        violations = compare_fixture(name, expected_by_analyzer, actual, tolerances)
        all_violations.extend(violations)
        per_fixture_status[name] = "FAIL" if violations else "PASS"

    summary = {
        "fixtures": per_fixture_status,
        "total_violations": len(all_violations),
        "passed": len(all_violations) == 0,
    }
    if diff_dir is not None and all_violations:
        write_diff_artifacts(Path(diff_dir), all_violations, summary)
    return all_violations, summary


# ---------------------------------------------------------------------------
# Artifacts de diff (gm-diff.json + gm-diff.html)
# ---------------------------------------------------------------------------
def write_diff_artifacts(
    diff_dir: Path,
    violations: list[GMViolation],
    summary: dict[str, Any],
) -> tuple[Path, Path]:
    diff_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "audio-suite/gm-diff@1",
        "summary": summary,
        "violations": [v.as_row() for v in violations],
    }
    json_path = diff_dir / "gm-diff.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    html_path = diff_dir / "gm-diff.html"
    html_path.write_text(_diff_to_html(payload))
    return json_path, html_path


def _diff_to_html(payload: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{v['fixture']}</td><td>{v['analyzer']}</td>"
        f"<td><code>{v['kind']}</code></td>"
        f"<td><code>{v['check_id']}</code></td><td><code>{v['metric']}</code></td>"
        f"<td>{v['detail']}</td>"
        "</tr>"
        for v in payload["violations"]
    )
    passed = payload["summary"]["passed"]
    badge = (
        '<span class="ok">PASS — Golden Master íntegro</span>'
        if passed
        else f"<span class='bad'>FAIL — {payload['summary']['total_violations']} violação(ões)</span>"
    )
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>audio-suite · Golden Master diff</title>
<style>
 body {{ font-family: -apple-system, 'Segoe UI', sans-serif; margin: 2rem; color: #1a1a2e; }}
 h1 {{ font-size: 1.3rem; }} table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
 th, td {{ border: 1px solid #d0d0e0; padding: 6px 10px; font-size: 0.85rem; text-align: left; }}
 th {{ background: #f0f0fa; }} code {{ background: #f6f6fc; padding: 1px 4px; }}
 .ok {{ color: #0a7d28; font-weight: 600; }} .bad {{ color: #b3261e; font-weight: 600; }}
</style></head><body>
<h1>Golden Master diff — audio-suite (CORP-04.r)</h1>
<p>{badge}</p>
<table><thead><tr><th>fixture</th><th>analyzer</th><th>tipo</th><th>check_id</th><th>metric</th><th>detalhe</th></tr></thead>
<tbody>{rows}</tbody></table>
<p><small>Diferenças numéricas são toleradas apenas dentro dos limites empíricos (±2σ)
definidos em <code>tests/golden/manifest.yaml</code>. Toda violação requer
regeneração com <code>audio-suite golden freeze</code>, label <code>golden-regen</code>
e justificativa no CHANGELOG.</small></p>
</body></html>"""


# ---------------------------------------------------------------------------
# Calibração empírica de tolerâncias (±2σ por jitter float32)
# ---------------------------------------------------------------------------
def calibrate_tolerances(
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    trials: int = 8,
    epsilon_rel: float = 2.0**-23,
    sigma_multiplier: float = 2.0,
    rounding_decimals: int = 3,
    floor: float = 1e-4,
    seed: int = 20260903,
) -> dict[str, Any]:
    """Derive per-analyzer tolerances empirically.

    Método (documentado em ADR-0002): para cada fixture do GM, gera K cópias
    do sinal decodificado com jitter RELATIVO de 1 ulp float32
    (x' = x·(1+u), u ~ U(-ε_rel, ε_rel); zeros permanecem zeros — silêncio
    digital não vira ruído), simulando variação aritmética entre plataformas.
    σ por (analyzer, metric) = desvio-padrão máximo entre fixtures;
    tolerância = round-up(2σ, 3 casas) com piso ε_floor.
    """
    manifest = load_golden_manifest(manifest_path)
    profile = load_gm_profile(manifest.get("profile", GM_PROFILE_PATH))
    fixtures_dir = Path(manifest.get("fixtures_dir", "tests/fixtures/generated"))
    if not Path(fixtures_dir).is_absolute():
        fixtures_dir = REPO_ROOT / fixtures_dir
    registry = gm_analyzers()

    sigma: dict[str, dict[str, float]] = {}
    for name in manifest["fixtures"]:
        audio = decode(fixtures_dir / name)
        rng = np.random.Generator(np.random.PCG64(seed))
        base: dict[tuple[str, str], list[float]] = {}
        for aid in GM_ANALYZER_IDS:
            analyzer = registry[aid]
            if not analyzer.applicable(audio, profile):
                continue
            for f in analyzer.analyze(audio, profile.analyzer_params(aid)):
                if f.value is not None:
                    base.setdefault((aid, f.metric), []).append(float(f.value))
        for t in range(trials):
            jittered = _jitter_pcm(audio, epsilon_rel, rng)
            for aid in GM_ANALYZER_IDS:
                analyzer = registry[aid]
                if not analyzer.applicable(jittered, profile):
                    continue
                for f in analyzer.analyze(jittered, profile.analyzer_params(aid)):
                    if f.value is None:
                        continue
                    base.setdefault((aid, f.metric), []).append(float(f.value))
        # σ por métrica deste fixture = desvio sobre [base] + trials (aprox por amostra)
        for (aid, metric), values in base.items():
            if len(values) < trials:  # métrica não medida em todos os trials
                continue
            s = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
            sigma.setdefault(aid, {})[metric] = max(sigma.get(aid, {}).get(metric, 0.0), s)

    tolerances: dict[str, dict[str, float]] = {}
    factor = 10**rounding_decimals
    for aid, metrics in sigma.items():
        tolerances[aid] = {}
        for metric, s in metrics.items():
            tol = max(sigma_multiplier * s, floor)
            tolerances[aid][metric] = math.ceil(tol * factor) / factor
    return {"sigma": sigma, "tolerances": tolerances}


def _jitter_pcm(audio: PCM, epsilon_rel: float, rng: np.random.Generator) -> PCM:
    """Relative 1-ulp float32 jitter: x' = x·(1+u), u ~ U(-ε, ε).

    Exact zeros stay zero (digital silence is preserved) — an absolute jitter
    would fabricate noise on silence and corrupt σ for floor metrics
    (true_peak of silence, glitch counts, spectral centroid).
    """
    u = rng.uniform(-epsilon_rel, epsilon_rel, size=audio.samples.shape).astype(np.float32)
    return PCM(
        samples=audio.samples * (np.float32(1.0) + u),
        sample_rate=audio.sample_rate,
        channel_layout=audio.channel_layout,
        file_sha256=audio.file_sha256,
        source_path=audio.source_path,
        provenance=dict(audio.provenance),
    )
