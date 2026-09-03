# ADR-0004: Rejeição do HMAC para assinatura de laudos (Ed25519 permanece)

- **Status:** Aceito (reafirmação formal; origem: R9 N-19 e MX-VF-04)
- **Data:** 2026-09-03
- **Decide:** time audio-suite (Documento Mestre v1.2, Parte IV §10 e Adendo B VI.3)
- **SHA inspecionado na redação:** `1062d2cd78f2dcc703e46718e4aec47f6433be79`

## Contexto

A assinatura de laudos (evidence bundles) usa **Ed25519** desde a v0.1.0.
Duas análises externas independentes (R9, item N-19; plano MX, item MX-VF-04)
levantaram HMAC como alternativa "mais simples" (segredo compartilhado, sem
par de chaves). O Documento Mestre v1.2 já registrava a rejeição (Parte IV
§10, "HMAC seal (Ed25519 é superior)"), mas sem ADR que tornasse a decisão
pesquisável e definitiva.

## Decisão

**HMAC é rejeitado** para assinatura de laudos, em qualquer variante
("opcional com esforço alocado" incluído — a rejeição é da abordagem, não do
escopo). Ed25519 permanece o único mecanismo de assinatura.

Motivação central: **verificação pública por terceiros**. Um laudo
evidence-grade precisa ser verificável por quem NÃO confia no emissor e não
pode receber segredo compartilhado:

| Critério | Ed25519 (escolhido) | HMAC (rejeitado) |
|---|---|---|
| Verificação por terceiros | pública (chave pública distribuída) | exige distribuir o segredo → qualquer detentor pode FORJAR laudos |
| Não-repúdio | sim (só o detentor da chave privada assina) | não (detentores do segredo indistinguíveis) |
| Superfície de chave | chave privada em um lugar | segredo em todo verificador |
| Rotação/revogação | troca de par de chaves, verificação pública continua | rotação exige redistribuir segredo a todos |

## Mecanismo

- Implementação atual: `audio_suite/security/signing.py` (Ed25519 via
  pynacl; payload canônico cobre tool, subject, profile, findings, fingerprint
  e, desde EVID-02.r+, o snapshot de ambiente).
- `pynacl` é a única dependência criptográfica (extra de segurança do runtime).
- Regra inviolável 4 (Ondas 3–5): não implementar HMAC nem como opcional.

## Consequências

- **Positivas:** laudos verificáveis publicamente; não-repúdio; decisão
  registrada e pesquisável — futuras sugestões de HMAC são respondidas por
  este ADR sem reabrir debate (protocolo §10).
- **Negativas/custos:** gestão de par de chaves pelo operador (vs. um segredo);
  aceito — problema resolvido e bem documentado (keyfile + `--sign`).
- **Alternativas descartadas:** HMAC (esta decisão); certificados X.509
  (peso operacional desnecessário para o escopo atual, reavaliável em modo
  serviço — BACKLOG-14).

## Relação com outros itens

Regra inviolável 4 (HMAC rejeitado) · EVID-01/02 (bundle assinado) ·
EVID-02.r+ (assinatura cobre environment) · BACKLOG-14 (gatilho modo serviço).
