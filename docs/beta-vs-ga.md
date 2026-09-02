# Beta vs GA — O que significa "Beta"?

> **Adendo A1:** o ciclo de 4 semanas entrega `v0.2.0-beta`, **não GA**.

## Diferença

| Aspecto | Beta (atual) | GA (futuro) |
|---------|--------------|-------------|
| Cobertura de testes | ≥ 70% | ≥ 85% + suite E2E completa |
| Reprodutibilidade | measurement_fingerprint determinístico | Bundle idêntico entre arquiteturas |
| Assinatura | Ed25519 local/CI | + RFC 3161 timestamp trusted |
| CI | Lint + tests + build | + performance regression + compatibility matrix |
| Documentação | Mínima essencial | + API reference + cookbook |
| Suporte | Best-effort via issues | SLA definido |
| Processo de release | Manual | Automated com changelog |
| Política de suporte | Não definida | Definida por versão |
| Validação externa | Nenhuma | Pelo menos 2 pipelines reais |

## Critérios para GA

Antes de rotular como GA (v1.0.0), todos devem ser verdadeiros:

1. ✅ F1 + F2 + adendos técnico/estratégico/operacional completos.
2. CI verde e reprodutível por ≥ 30 dias consecutivos.
3. Uso validado em ≥ 2 pipelines reais independentes (case studies publicados).
4. Sem defeitos críticos abertos em: contracts, decision model, hashing, signing.
5. Versionamento e compatibilidade de schemas documentados.
6. Processo de release, changelog e política de suporte definidos.
7. Cobertura de testes ≥ 85%.
8. Performance benchmark documentado (`docs/performance.md`).
9. Auditoria de segurança externa concluída (ou justificativa para pular).

## O que NÃO fazer no Beta

- ❌ Rotular builds como "production-ready" ou "GA".
- ❌ Prometer compatibilidade com versões futuras de schema.
- ❌ Garantir reprodutibilidade bitwise entre arquiteturas.
- ❌ Garantir comentários automáticos em PR via SARIF (depende de permissões do repo).
