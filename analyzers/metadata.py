"""Analyzer: metadados e rights manifest."""
from typing import Any


def run_analyzer(
    pcm: None,  # Não usa PCM
    media_info: dict[str, Any],
    params: dict[str, Any],
    verbose: bool = False
) -> list[dict]:
    """Extrai metadados e valida rights manifest se presente."""
    findings = []

    # Extrai tags via mutagen (WAV/FLAC)
    try:
        # media_info já tem tags do ffmpeg probe
        tags = media_info.get("tags", {})
        if tags:
            findings.append({
                "name": "Metadados ID3/RIFF",
                "value": f"{len(tags)} tags encontradas",
                "status": "info",
                "severity": "info"
            })
            # Lista tags como info
            for k, v in tags.items():
                findings.append({
                    "name": f"Tag: {k}",
                    "value": str(v),
                    "status": "info",
                    "severity": "info"
                })
        else:
            findings.append({
                "name": "Metadados",
                "value": "Nenhuma tag encontrada",
                "status": "info",
                "severity": "info"
            })

        # Rights manifest validation (se policy passou path)
        # O CLI não passa rights manifest aqui; deixar stub
        # O validator será chamado no CLI como etapa separada

    except Exception as e:
        findings.append({
            "name": "Metadata Analyzer",
            "value": str(e),
            "status": "indeterminate",
            "severity": "error"
        })

    return findings
