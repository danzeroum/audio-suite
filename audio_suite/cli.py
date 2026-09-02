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
    _print_json({
        "valid": True,
        "name": profile.name,
        "version": profile.version,
        "analyzers": sorted(profile.analyzers.keys()),
        "data_classification": profile.data_classification,
        "strict": profile.is_strict(),
    })
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
    else:
        return _emit_error(f"unknown format: {fmt}", ExitCode.USAGE)

    # 6. Exit code based on aggregate status
    agg = Status(bundle.aggregate_status)
    if agg in (Status.FAIL, Status.ERROR):
        return ExitCode.FINDING
    return ExitCode.OK


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
    p_analyze.add_argument("--format", choices=["json", "sarif", "html"], default="json")
    p_analyze.add_argument("--output", "-o", help="output file path")
    p_analyze.add_argument("--strict", action="store_true", help="apply strict overlay")
    p_analyze.add_argument("--jobs", "-j", type=int, default=1, help="parallel jobs (placeholder)")
    p_analyze.add_argument("--only", help="comma-separated analyzer IDs to run")
    p_analyze.add_argument("--skip", help="comma-separated analyzer IDs to skip")
    p_analyze.add_argument("--resample", type=int, help="explicit resample target Hz")
    p_analyze.add_argument("--sign", action="store_true", help="sign the evidence bundle")
    p_analyze.add_argument("--signing-key", help="path to Ed25519 private key")
    p_analyze.set_defaults(func=cmd_analyze)

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
