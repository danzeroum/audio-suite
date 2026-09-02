import hashlib
import json
import sys
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .execution import run_validation
from .evidence import build_bundle, save_bundle
from .policy import load_policy_profile

app = typer.Typer(
    help="audio-suite — Assurance engine for audio artifacts\n"
         "Mede propriedades acústicas, aplica políticas versionadas e emite evidência verificável."
)

console = Console()

@app.command()
def validate(
    input_audio: Path = typer.Argument(..., exists=True, file_okay=True, dir_okay=False,
        help="Caminho do arquivo de áudio (WAV ou FLAC)"),
    profile: Path = typer.Option(..., exists=True, file_okay=True,
        help="Caminho do profile YAML de política"),
    output: Path = typer.Option(..., "--output", "-o",
        help="Caminho do bundle JSON de evidência"),
    dry_run: bool = typer.Option(False, "--dry-run",
        help="Executa sem gerar assinatura; útil para desenvolvimento"),
    verbose: bool = typer.Option(False, "--verbose", "-v",
        help="Mostra logs detalhados")
):
    """
    Valida um artefato de áudio contra um profile de política e emite um bundle de evidência.
    """
    if verbose:
        console.print(f"🔍 Carregando profile: {profile}")
    try:
        policy = load_policy_profile(profile)
    except Exception as e:
        console.print(f"[red]❌ Falha ao carregar profile: {e}[/red]")
        sys.exit(3)

    if verbose:
        console.print(f"📁 Input: {input_audio} | Profile: {policy['name']}")

    # Executa a validação
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Executando validação...", total=None)
        try:
            findings, provenance, pcm_hash, decoder_info = run_validation(
                input_audio, policy, dry_run=dry_run, verbose=verbose
            )
            progress.update(task, completed=True, description="✅ Validação concluída")
        except Exception as e:
            console.print(f"[red]❌ Erro durante validação: {e}[/red]")
            sys.exit(3)

    # Decisão
    severity_map = {"error": 1, "warning": 0, "info": 0}
    has_fail = any(f["severity"] == "error" for f in findings)
    has_indeterminate = any(f["status"] == "indeterminate" for f in findings)

    if has_fail:
        decision = "fail"
        exit_code = 1
    elif has_indeterminate:
        decision = "indeterminate"
        exit_code = 2
    else:
        decision = "pass"
        exit_code = 0

    # Gera bundle
    try:
        bundle = build_bundle(
            input_audio=input_audio,
            policy=policy,
            findings=findings,
            provenance=provenance,
            pcm_canonical_sha256=pcm_hash,
            decoder_info=decoder_info,
            decision=decision,
            dry_run=dry_run
        )
        save_bundle(bundle, output)
        console.print(f"[green]✅ Bundle salvo em:[/green] {output}")

        # Tabela de resultados
        table = Table(title="Resultados da validação")
        table.add_column("ID", style="cyan")
        table.add_column("Métrica", style="magenta")
        table.add_column("Valor", style="yellow")
        table.add_column("Limite", style="blue")
        table.add_column("Status", style="bold")
        for f in findings:
            status_style = {
                "pass": "green",
                "fail": "red",
                "warning": "yellow",
                "indeterminate": "orange3"
            }.get(f["status"], "white")
            table.add_row(
                f.get("id", "-"),
                f.get("name", "-"),
                str(f.get("value", "-")) + (" " + str(f.get("unit", "")) if f.get("unit") else ""),
                str(f.get("threshold", "-")),
                f"[{status_style}]{f['status'].upper()}[/]"
            )
        console.print(table)

        if decision == "fail":
            console.print("[red]❌ Validação reprovada: existem findings com severidade ERROR.[/red]")
        elif decision == "indeterminate":
            console.print("[orange3]⚠️ Validação indeterminada: revisão humana recomendada.[/orange3]")
        else:
            console.print("[green]✅ Validação aprovada.[/green]")

    except Exception as e:
        console.print(f"[red]❌ Falha ao gerar bundle: {e}[/red]")
        sys.exit(3)

    sys.exit(exit_code)


@app.command(hidden=True)
def version():
    """Mostra a versão."""
    console.print(f"[bold]audio-suite v0.1.0-alpha[/bold]")


if __name__ == "__main__":
    app()
