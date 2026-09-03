"""audio-suite command-line interface.

Commands:
  audio-suite --version
  audio-suite inspect <file>                          # quick metadata
  audio-suite validate <profile.yaml>                 # validate profile
  audio-suite analyze <file> [--profile p.yaml] [--format json|sarif|html]
                              [--strict] [--output path] [--jobs N]
                              [--only a,b] [--skip a,b]
                              [--sign --signing-key keyfile]

Exit codes (CLI-01..CLI-20):
  0 OK                  analysis ran, no fail-level findings
  1 FINDING             analysis ran, at least one fail-level finding
  2 INVALID_PROFILE     profile YAML failed validation
  3 INVALID_INPUT       input audio could not be decoded / missing
  64 USAGE              CLI usage error (sysexits.h EX_USAGE)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .bundle import build_bundle, bundle_to_json
from .decode import DecodeError, decode
from .engine import run_analyzers
from .models import ExitCode, Status
from .output import bundle_to_html, bundle_to_json_file, bundle_to_sarif
from .policy import ProfileError, load_profile


def _print_json(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, sort_keys=True, indent=2, default=str) + "\n")


def _emit_error(msg: str, code: int) -> int:
    sys.stderr.write(f"audio-suite: error: {msg}\n")
    return code


def cmd_version(args: argparse.Namespace) -> int:
    sys.stdout.write(f"audio-suite {__version__}\n")
    return ExitCode.OK


def cmd_inspect(args: argparse.Namespace) -> int:
    """Quick metadata extraction — runs only the inspect analyzer."""
    try:
        audio = decode(args.file)
    except DecodeError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)
    except FileNotFoundError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)

    info = {
        "file": args.file,
        "sha256": audio.file_sha256,
        "sample_rate_hz": audio.sample_rate,
        "channels": audio.channels,
        "channel_layout": audio.channel_layout,
        "frames": audio.n_frames,
        "duration_s": round(audio.duration_s, 4),
        "provenance": audio.provenance,
    }
    _print_json(info)
    return ExitCode.OK


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        profile = load_profile(args.profile, strict=args.strict)
    except ProfileError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_PROFILE)
    _print_json(
        {
            "valid": True,
            "name": profile.name,
            "version": profile.version,
            "analyzers": sorted(profile.analyzers.keys()),
            "data_classification": profile.data_classification,
            "strict": profile.is_strict(),
        }
    )
    return ExitCode.OK


def cmd_analyze(args: argparse.Namespace) -> int:
    # 1. Load profile (may exit 2)
    default_profile = Path(__file__).parent / "default_profile.yaml"
    profile_path = args.profile or str(default_profile)
    try:
        profile = load_profile(profile_path, strict=args.strict)
    except ProfileError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_PROFILE)

    # 2. Decode audio (may exit 3)
    try:
        audio = decode(args.file, target_sr=args.resample)
    except DecodeError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)
    except FileNotFoundError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)

    # 3. Run analyzers
    only = args.only.split(",") if args.only else None
    skip = args.skip.split(",") if args.skip else None

    findings = run_analyzers(audio, profile, only=only, skip=skip)

    # 4. Build bundle (deterministic, optionally signed)
    bundle = build_bundle(
        audio,
        profile,
        findings,
        sign=args.sign,
        signing_key_path=args.signing_key,
    )

    # 5. Emit in requested format
    fmt = args.format
    out_path = args.output

    if fmt == "json":
        if out_path:
            bundle_to_json_file(bundle, out_path)
        else:
            sys.stdout.write(bundle_to_json(bundle) + "\n")
    elif fmt == "sarif":
        sarif = bundle_to_sarif(bundle, output_path=out_path)
        if not out_path:
            sys.stdout.write(json.dumps(sarif, indent=2) + "\n")
    elif fmt == "html":
        bundle_to_html(bundle, output_path=out_path or "audio_suite_report.html")
        if out_path:
            sys.stdout.write(f"report written to {out_path}\n")
    elif fmt == "csv":
        from .output.csv_out import bundle_to_csv

        csv_str = bundle_to_csv(bundle, output_path=out_path)
        if not out_path:
            sys.stdout.write(csv_str)
    else:
        return _emit_error(f"unknown format: {fmt}", ExitCode.USAGE)

    # 6. Exit code based on aggregate status
    agg = Status(bundle.aggregate_status)
    if agg in (Status.FAIL, Status.ERROR):
        return ExitCode.FINDING
    return ExitCode.OK


def cmd_compliance(args: argparse.Namespace) -> int:
    """PROF-07: check delivery compliance for a target platform."""
    TARGETS = {
        "ebu": {"name": "EBU R128", "lufs_target": -23.0, "lufs_tolerance": 0.5, "max_dbtp": -1.0},
        "spotify": {"name": "Spotify", "lufs_target": -14.0, "lufs_tolerance": 1.0, "max_dbtp": -1.0},
        "podcast": {"name": "Podcast", "lufs_target": -16.0, "lufs_tolerance": 1.0, "max_dbtp": -1.0},
        "atsc": {"name": "ATSC A/85", "lufs_target": -24.0, "lufs_tolerance": 2.0, "max_dbtp": -2.0},
        "cine": {"name": "Cinema", "lufs_target": -27.0, "lufs_tolerance": 2.0, "max_dbtp": -2.0},
    }
    spec = TARGETS.get(args.target)
    if not spec:
        return _emit_error(f"unknown target: {args.target}", ExitCode.USAGE)
    try:
        audio = decode(args.file)
    except DecodeError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)
    from .analyzers.loudness import compute_loudness_lufs
    from .analyzers.truepeak import compute_true_peak_dbtp

    lufs = compute_loudness_lufs(audio)
    tp_dbtp, sp_dbfs = compute_true_peak_dbtp(audio)
    lufs_ok = abs(lufs - spec["lufs_target"]) <= spec["lufs_tolerance"]
    tp_ok = tp_dbtp <= spec["max_dbtp"]
    matrix = {
        "target": args.target,
        "spec_name": spec["name"],
        "measurements": {"integrated_lufs": round(lufs, 2), "true_peak_dbtp": round(tp_dbtp, 3)},
        "requirements": {
            "lufs_target": spec["lufs_target"],
            "lufs_tolerance": spec["lufs_tolerance"],
            "max_dbtp": spec["max_dbtp"],
        },
        "compliance": {
            "lufs": "pass" if lufs_ok else "fail",
            "true_peak": "pass" if tp_ok else "fail",
            "overall": "pass" if (lufs_ok and tp_ok) else "fail",
        },
        "delta": {
            "lufs_delta": round(lufs - spec["lufs_target"], 2),
            "true_peak_margin": round(spec["max_dbtp"] - tp_dbtp, 3),
        },
    }
    out = json.dumps(matrix, indent=2)
    if args.output:
        Path(args.output).write_text(out)
    else:
        sys.stdout.write(out + "\n")
    return ExitCode.OK if (lufs_ok and tp_ok) else ExitCode.FINDING


def cmd_self_check(args: argparse.Namespace) -> int:
    """Fase 3.5: verify installation integrity."""
    from .audit import self_check

    results = self_check()
    _print_json(results)
    return ExitCode.OK if results.get("overall") else ExitCode.FINDING


def cmd_audit(args: argparse.Namespace) -> int:
    """Fase 3.5: manage audit log."""
    from .audit import AuditLog

    log = AuditLog(args.log, actor=args.actor)
    if args.verify:
        valid, errors = log.verify_chain()
        _print_json({"valid": valid, "errors": errors, "log_path": args.log})
        return ExitCode.OK if valid else ExitCode.FINDING
    else:
        entry = log.append(args.action, args.subject)
        _print_json(
            {
                "entry_hash": entry.entry_hash,
                "prev_hash": entry.prev_hash,
                "timestamp": entry.timestamp,
            }
        )
        return ExitCode.OK


def cmd_compare(args: argparse.Namespace) -> int:
    """ENG-13: objective acoustic diff between two files."""
    from .compare import compare_files

    try:
        profile = (
            load_profile(args.profile, strict=args.strict)
            if args.profile
            else load_profile(Path(__file__).parent / "default_profile.yaml")
        )
    except ProfileError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_PROFILE)

    try:
        diff = compare_files(args.a, args.b, profile=profile)
    except DecodeError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)
    except FileNotFoundError as exc:
        return _emit_error(str(exc), ExitCode.INVALID_INPUT)

    out = json.dumps(diff, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out + "\n")

    if args.fail_on_regression and diff["regression_detected"]:
        return ExitCode.FINDING
    return ExitCode.OK


def cmd_golden(args: argparse.Namespace) -> int:
    """CORP-04/CORP-04.r: Golden Master de processo.

    audio-suite golden freeze  — regenera tests/golden/expected/*.json
    audio-suite golden verify  — compara contra os esperados; em violação,
                                 escreve gm-diff.json + gm-diff.html e sai 1.
    """
    from .golden import (
        DEFAULT_EXPECTED_DIR,
        DEFAULT_MANIFEST,
        freeze_expected,
        verify_golden,
    )

    manifest = args.manifest or str(DEFAULT_MANIFEST)
    expected_dir = args.expected_dir or str(DEFAULT_EXPECTED_DIR)

    if args.action == "freeze":
        out_dir = freeze_expected(manifest_path=manifest, expected_dir=expected_dir)
        _print_json(
            {
                "action": "freeze",
                "expected_dir": str(out_dir),
                "note": (
                    "golden files regenerados — o PR precisa da label 'golden-regen' "
                    "e de justificativa no CHANGELOG (CORP-04.r)"
                ),
            }
        )
        return ExitCode.OK

    violations, summary = verify_golden(
        manifest_path=manifest,
        expected_dir=expected_dir,
        diff_dir=args.diff_dir,
    )
    payload = {
        "action": "verify",
        "summary": summary,
        "violations": [v.as_row() for v in violations],
    }
    if args.diff_dir:
        payload["diff_dir"] = str(args.diff_dir)
    _print_json(payload)
    return ExitCode.OK if not violations else ExitCode.FINDING


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audio-suite",
        description="Acoustic analysis CLI for objective defect detection and perceptual quality.",
    )
    p.add_argument("--version", action="store_true", help="print version and exit")
    sub = p.add_subparsers(dest="command", required=False)

    # inspect
    p_inspect = sub.add_parser("inspect", help="extract technical metadata")
    p_inspect.add_argument("file", help="audio file path")
    p_inspect.set_defaults(func=cmd_inspect)

    # validate
    p_validate = sub.add_parser("validate", help="validate a profile YAML")
    p_validate.add_argument("profile", help="profile YAML path")
    p_validate.add_argument("--strict", action="store_true", help="apply strict overlay")
    p_validate.set_defaults(func=cmd_validate)

    # analyze
    p_analyze = sub.add_parser("analyze", help="run analysis")
    p_analyze.add_argument("file", help="audio file path")
    p_analyze.add_argument("--profile", help="profile YAML path (default: built-in)")
    p_analyze.add_argument("--format", choices=["json", "sarif", "html", "csv"], default="json")
    p_analyze.add_argument("--output", "-o", help="output file path")
    p_analyze.add_argument("--strict", action="store_true", help="apply strict overlay")
    p_analyze.add_argument("--jobs", "-j", type=int, default=1, help="parallel jobs (placeholder)")
    p_analyze.add_argument("--only", help="comma-separated analyzer IDs to run")
    p_analyze.add_argument("--skip", help="comma-separated analyzer IDs to skip")
    p_analyze.add_argument("--resample", type=int, help="explicit resample target Hz")
    p_analyze.add_argument("--sign", action="store_true", help="sign the evidence bundle")
    p_analyze.add_argument("--signing-key", help="path to Ed25519 private key")
    p_analyze.set_defaults(func=cmd_analyze)

    # self-check (Fase 3.5)
    p_selfcheck = sub.add_parser("self-check", help="verify installation integrity")
    p_selfcheck.set_defaults(func=cmd_self_check)

    # audit (Fase 3.5)
    p_audit = sub.add_parser("audit", help="manage audit log")
    p_audit.add_argument("--log", default="audit.log", help="audit log path")
    p_audit.add_argument("--action", required=True, help="action to record")
    p_audit.add_argument("--subject", required=True, help="subject of the action")
    p_audit.add_argument("--actor", default="anonymous", help="who performed the action")
    p_audit.add_argument("--verify", action="store_true", help="verify chain integrity")
    p_audit.set_defaults(func=cmd_audit)

    # compare (ENG-13)
    p_compare = sub.add_parser("compare", help="objective acoustic diff between two files")
    p_compare.add_argument("a", help="reference file A")
    p_compare.add_argument("b", help="candidate file B")
    p_compare.add_argument("--profile", help="profile YAML path (default: built-in)")
    p_compare.add_argument("--strict", action="store_true", help="apply strict overlay")
    p_compare.add_argument("--output", "-o", help="write diff.json to path")
    p_compare.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit 1 when regression_detected is true (CI gate)",
    )
    p_compare.set_defaults(func=cmd_compare)

    # golden (CORP-04/CORP-04.r)
    p_golden = sub.add_parser("golden", help="Golden Master de processo (freeze/verify)")
    p_golden.add_argument("action", choices=["freeze", "verify"])
    p_golden.add_argument(
        "--manifest", default=None, help="manifest GM (default: tests/golden/manifest.yaml)"
    )
    p_golden.add_argument(
        "--expected-dir", default=None, help="diretório dos esperados (default: tests/golden/expected)"
    )
    p_golden.add_argument("--diff-dir", default=None, help="diretório para gm-diff artifacts no verify")
    p_golden.set_defaults(func=cmd_golden)

    # compliance (PROF-07)
    p_compliance = sub.add_parser("compliance", help="check delivery compliance")
    p_compliance.add_argument("file", help="audio file path")
    p_compliance.add_argument(
        "--target", required=True, choices=["ebu", "spotify", "podcast", "atsc", "cine"]
    )
    p_compliance.add_argument("--output", "-o")
    p_compliance.set_defaults(func=cmd_compliance)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        return cmd_version(args)

    if not getattr(args, "command", None):
        parser.print_help()
        return ExitCode.USAGE

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
