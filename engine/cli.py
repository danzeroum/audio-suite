"""audio-suite CLI — inspect, validate, verify, key.

Comandos:
- inspect <file> [--analysis header|basic|full] [--format json|text]
- validate <file> --profile <yaml> --output <bundle.json> [--format json|sarif]
                 [--signature-mode unsigned|local-key|ci-key]
                 [--rights-manifest <yaml>] [--provenance-events <json>]
                 [--analyzer-timeout <s>]
- verify <bundle.json> [--trusted-keys-dir <dir>]
- key generate [--output <path>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .bundle.signer import (
    generate_key,
    key_id_from_private,
    verify_bundle,
)
from .cli_formats.sarif import bundle_to_sarif, save_sarif
from .discovery import probe_media, probe_media_fallback
from .evidence import build_bundle, save_bundle
from .execution import run_validation
from .normalization import compute_file_hash, compute_pcm_hash, decode_pcm_canonical
from .policy import apply_policy, load_policy_profile

app = typer.Typer(
    help="audio-suite — Assurance engine for audio artifacts\n"
         "Mede, decide e prova. v0.2.0-beta.",
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# inspect — F1.2 + A5
# ---------------------------------------------------------------------------

@app.command()
def inspect(
    input_audio: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False,
        help="Arquivo de áudio (WAV/FLAC/etc)"),
    analysis: str = typer.Option("header", "--analysis",
        help="Nível: header | basic | full (A5)"),
    output_format: str = typer.Option("json", "--format",
        help="Saída: json | text"),
):
    """Inspeção sem policy — extrai metadados e (opcional) medidas acústicas."""
    # Header (sempre): codec, sample rate, canais, duração, tags, file hash
    try:
        media_info = probe_media(input_audio)
        decoder_used = "ffmpeg"
    except Exception:
        try:
            media_info = probe_media_fallback(input_audio)
            decoder_used = "fallback"
        except Exception as exc:
            console.print(f"[red]❌ Probe falhou: {exc}[/red]")
            sys.exit(3)

    file_hash = compute_file_hash(input_audio)

    result: dict[str, Any] = {
        "path": str(input_audio),
        "file_sha256": file_hash,
        "decoder_used": decoder_used,
        "format": media_info.get("format"),
        "audio_codec": media_info.get("audio_codec"),
        "sample_rate_hz": media_info.get("sample_rate_hz"),
        "channels": media_info.get("channels"),
        "channel_layout": media_info.get("channel_layout"),
        "bits_per_sample": media_info.get("bits_per_sample"),
        "duration_s": media_info.get("duration_s"),
        "size_bytes": media_info.get("size_bytes"),
        "bit_rate_bps": media_info.get("bit_rate_bps"),
        "tags": media_info.get("tags", {}),
    }

    if analysis in ("basic", "full"):
        try:
            pcm, _sr, _ch, meta = decode_pcm_canonical(input_audio, sample_rate=48000)
            result["pcm_canonical_sha256"] = compute_pcm_hash(pcm) if pcm.size > 0 else None
            result["pcm_meta"] = {
                "decoder_used": meta.get("decoder_used"),
                "nan_sanitized": meta.get("nan_sanitized"),
                "empty": meta.get("empty"),
            }
            # Sample peak básico
            if pcm.size > 0:
                import numpy as np
                sample_peak = float(np.max(np.abs(pcm)))
                result["sample_peak_linear"] = sample_peak
                result["sample_peak_dbfs"] = (
                    20.0 * float(np.log10(sample_peak)) if sample_peak > 0 else -140.0
                )
        except Exception as exc:
            result["pcm_error"] = str(exc)

    if analysis == "full":
        # Loudness requer análise completa
        try:
            from analyzers.loudness import run_analyzer as loudness_analyzer
            lfindings = loudness_analyzer(
                pcm=pcm,
                media_info=media_info,
                params={"target_integrated_lufs": -23.0, "tolerance_lufs": 0.5},
                verbose=False,
            )
            result["loudness_findings"] = lfindings
        except Exception as exc:
            result["loudness_error"] = str(exc)

        try:
            from analyzers.signal import run_analyzer as signal_analyzer
            sfindings = signal_analyzer(
                pcm=pcm,
                media_info=media_info,
                params={"max_true_peak_dbtp": -1.0, "allow_clipping": False},
                verbose=False,
            )
            result["signal_findings"] = sfindings
        except Exception as exc:
            result["signal_error"] = str(exc)

    # Identifica campos não disponíveis (A5: não omitir silenciosamente)
    na_fields = [k for k, v in result.items() if v is None and k not in ("tags",)]
    if na_fields:
        result["_not_available"] = na_fields

    if output_format == "text":
        _print_inspect_text(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _print_inspect_text(result: dict[str, Any]) -> None:
    table = Table(title=f"Inspect: {result.get('path')}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="yellow")
    for k, v in result.items():
        if k.startswith("_"):
            continue
        table.add_row(k, str(v))
    console.print(table)


# ---------------------------------------------------------------------------
# validate — F1 + F2 + todos adendos
# ---------------------------------------------------------------------------

@app.command()
def validate(
    input_audio: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False),
    profile: Path = typer.Option(..., exists=True, file_okay=True,
        help="Profile YAML de política"),
    output: Path = typer.Option(..., "--output", "-o",
        help="Caminho do bundle JSON"),
    output_format: str = typer.Option("json", "--format",
        help="json | sarif"),
    signature_mode: str = typer.Option("unsigned", "--signature-mode",
        help="unsigned | local-key | ci-key"),
    signature_key: Path = typer.Option(None, "--signature-key",
        help="Caminho da chave (default ~/.audio-suite/ed25519.pem)"),
    rights_manifest: Path = typer.Option(None, "--rights-manifest",
        help="Rights manifest YAML"),
    provenance_events: Path = typer.Option(None, "--provenance-events",
        help="JSON com eventos de provenance"),
    analyzer_timeout: float = typer.Option(60.0, "--analyzer-timeout",
        help="Timeout por analyzer (s) — O2"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Valida áudio contra profile e emite bundle de evidência."""
    try:
        policy = load_policy_profile(profile)
    except Exception as e:
        console.print(f"[red]❌ Profile inválido: {e}[/red]")
        sys.exit(3)

    findings, provenance, pcm_hash, decoder_info, exec_result = run_validation(
        input_audio=input_audio,
        policy=policy,
        dry_run=dry_run,
        verbose=verbose,
        analyzer_timeout_s=analyzer_timeout,
        rights_manifest_path=rights_manifest,
        provenance_events_path=provenance_events,
    )

    # Decisão via policy
    decision = apply_policy(findings, policy)

    # Exit code
    exit_code = {
        "pass": 0,
        "warning": 0,
        "fail": 1,
        "indeterminate": 2,
        "needs_review": 2,
    }.get(decision, 3)

    try:
        bundle = build_bundle(
            input_audio=input_audio,
            policy=policy,
            findings=findings,
            provenance=provenance,
            pcm_canonical_sha256=pcm_hash,
            decoder_info=decoder_info,
            decision=decision,
            decoder_used=exec_result.decoder_used,
            has_nan_sanitized=exec_result.has_nan_sanitized,
            is_empty=exec_result.is_empty,
            toctou_detected=exec_result.toctou_detected,
            had_timeout=exec_result.had_timeout,
            truncated_analyzers=exec_result.truncated_analyzers,
            phase_skipped_mono=exec_result.phase_skipped_mono,
            rights_manifest_missing=not rights_manifest or not rights_manifest.exists(),
            provenance_partial=bool(provenance_events and not provenance_events.exists()),
            dry_run=dry_run,
            signature_mode=signature_mode,
            signature_key_path=signature_key,
        )
        save_bundle(bundle, output)
        console.print(f"[green]✅ Bundle salvo em:[/green] {output}")

        if output_format == "sarif":
            sarif_path = output.with_suffix(".sarif")
            sarif = bundle_to_sarif(bundle)
            save_sarif(sarif, sarif_path)
            console.print(f"[green]📄 SARIF salvo em:[/green] {sarif_path}")

        _print_findings_table(findings)

        decision_color = {
            "pass": "green",
            "warning": "yellow",
            "fail": "red",
            "indeterminate": "orange3",
            "needs_review": "orange3",
        }.get(decision, "white")
        console.print(f"\n[{decision_color}]Decision: {decision.upper()}[/{decision_color}]")

        if bundle.get("limitations"):
            console.print(f"[blue]Limitations:[/blue] {', '.join(bundle['limitations'])}")

    except Exception as e:
        console.print(f"[red]❌ Falha ao gerar bundle: {e}[/red]")
        sys.exit(3)

    sys.exit(exit_code)


def _print_findings_table(findings):
    table = Table(title="Findings")
    table.add_column("ID", style="cyan")
    table.add_column("Métrica", style="magenta")
    table.add_column("Valor", style="yellow")
    table.add_column("Status", style="bold")
    for f in findings:
        status_style = {
            "pass": "green",
            "fail": "red",
            "warning": "yellow",
            "indeterminate": "orange3",
            "needs_review": "orange3",
            "not_applicable": "white",
        }.get(f.get("status", ""), "white")
        value = f.get("value", "-")
        unit = f.get("unit", "")
        if unit:
            value = f"{value} {unit}"
        table.add_row(
            str(f.get("id", "-")),
            str(f.get("name", "-")),
            str(value),
            f"[{status_style}]{str(f.get('status', '-')).upper()}[/]",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# verify — A6
# ---------------------------------------------------------------------------

@app.command()
def verify(
    bundle_path: Path = typer.Argument(..., exists=True, file_okay=True),
    trusted_keys_dir: Path = typer.Option(
        None, "--trusted-keys-dir",
        help="Diretório com chaves públicas confiáveis (.pub)",
    ),
):
    """Verifica assinatura de um bundle."""
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]❌ Bundle inválido: {e}[/red]")
        sys.exit(3)

    result = verify_bundle(bundle, trusted_keys_dir=trusted_keys_dir)

    color = {
        "valid": "green",
        "invalid": "red",
        "key_unknown": "yellow",
        "unsigned": "blue",
    }.get(result, "white")
    console.print(f"[{color}]Signature: {result.upper()}[/{color}]")

    if result == "valid":
        sys.exit(0)
    elif result == "unsigned":
        sys.exit(0)  # não-erro: apenas informação
    else:
        sys.exit(1)


# ---------------------------------------------------------------------------
# key — S5
# ---------------------------------------------------------------------------

@app.command()
def key(
    action: str = typer.Argument(..., help="generate | export-public | id"),
    output: Path = typer.Option(None, "--output", "-o",
        help="Caminho de saída (default ~/.audio-suite/ed25519.pem)"),
    private_key: Path = typer.Option(None, "--private-key",
        help="Caminho da chave privada (para export-public e id)"),
):
    """Gestão de chaves Ed25519."""
    if action == "generate":
        out = output or (Path.home() / ".audio-suite" / "ed25519.pem")
        path = generate_key(out)
        console.print(f"[green]✅ Chave gerada em:[/green] {path}")
        key_id = key_id_from_private(path)
        console.print(f"[blue]key_id:[/blue] {key_id}")
        console.print("[yellow]⚠️ Exporte a chave pública para o diretório de chaves confiáveis antes de verificar bundles.[/yellow]")
    elif action == "export-public":
        from .bundle.signer import export_public_key
        priv = private_key or (Path.home() / ".audio-suite" / "ed25519.pem")
        if not priv.exists():
            console.print(f"[red]❌ Chave privada não encontrada: {priv}[/red]")
            sys.exit(3)
        trusted_dir = Path.home() / ".audio-suite" / "trusted-keys"
        key_id = key_id_from_private(priv)
        fingerprint = key_id.split(":")[-1]
        pub_path = trusted_dir / f"{fingerprint}.pub"
        export_public_key(priv, pub_path)
        console.print(f"[green]✅ Chave pública exportada em:[/green] {pub_path}")
    elif action == "id":
        priv = private_key or (Path.home() / ".audio-suite" / "ed25519.pem")
        if not priv.exists():
            console.print(f"[red]❌ Chave privada não encontrada: {priv}[/red]")
            sys.exit(3)
        console.print(key_id_from_private(priv))
    else:
        console.print(f"[red]❌ Ação desconhecida: {action}[/red]")
        sys.exit(64)


@app.command(hidden=True)
def version():
    """Mostra a versão."""
    console.print("[bold]audio-suite v0.2.0-beta[/bold]")


if __name__ == "__main__":
    app()
