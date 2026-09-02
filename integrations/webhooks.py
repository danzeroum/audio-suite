"""
Stub — Webhooks para integração futura com sistemas externos.

Implementar após v0.1.0:
- Callback HTTP para notificar conclusão de validação
- Integração com sistemas de fila (RabbitMQ / SQS)
- Schema webhook-payload-1.0
"""
def send_webhook(bundle: dict, endpoint: str) -> bool:
    """Stub. Implementar quando houver requisito real de integração."""
    raise NotImplementedError("Webhooks adiados para v0.2+")
