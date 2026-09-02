"""
Stub — Adapter que converte o bundle audio-suite para o formato de evidência da pse-suite.
Implementação real depende do schema `laudo-pse-1.0`.
"""
def convert_to_pse_bundle(audio_bundle: dict) -> dict:
    """
    Converte o bundle da audio-suite para o formato consumível pela pse-suite.
    No Alpha, retorna um stub com status NEEDS_REVIEW.
    """
    return {
        "schema": "pse-evidence-adapter/stub-1.0",
        "audio_suite_bundle": audio_bundle,
        "pse_compatibility": {
            "status": "needs_review",
            "reason": "Adapter não implementado no Alpha; integrar após definição do schema laudo-pse-1.0"
        }
    }
