# Security — Gestão de chaves e disclosure

## Visão geral

A audio-suite v0.2.0-beta suporta 3 modos de assinatura Ed25519 para o bundle de evidência:

| Modo | Status no bundle | Uso |
|------|------------------|-----|
| `unsigned` | `unsigned` | Dev local |
| `local-key` | `signed-local` | Laboratório |
| `ci-key` | `signed-ci` | CI controlada |

## Geração de chaves

### Local (dev/lab)

```bash
audio-suite key generate
# → cria ~/.audio-suite/ed25519.pem (chmod 600)
# → imprime key_id (ex.: ed25519:local:abc123def456...)

audio-suite key export-public
# → cria ~/.audio-suite/trusted-keys/<fingerprint>.pub
```

### CI

```bash
# 1. Gere localmente em ambiente seguro:
audio-suite key generate --output /tmp/ci-key.pem

# 2. Codifique em base64:
base64 -w0 /tmp/ci-key.pem

# 3. Adicione como secret do repositório:
#    Settings → Secrets and variables → Actions → AUDIO_SUITE_CI_KEY

# 4. Use no workflow:
#    audio-suite validate ... --signature-mode ci-key
```

## Verificação

```bash
audio-suite verify bundle.json
# → "VALID" | "INVALID" | "KEY_UNKNOWN" | "UNSIGNED"
```

Para verificar bundles assinados por chaves CI em outra máquina:
1. Exporte a chave pública correspondente.
2. Coloque em `~/.audio-suite/trusted-keys/<fingerprint>.pub`.
3. Rode `audio-suite verify bundle.json`.

## Rotação de chaves (S5)

- **Local:** quando desejar; gere nova chave com `audio-suite key generate`.
- **CI:** a cada release major, ou se houver suspeita de vazamento.
- `key_id` no bundle inclui contexto (`ed25519:ci:<repo>/<workflow>`) para rastreabilidade.

## Limitações (Beta)

- **Sem timestamp trusted (RFC 3161):** adiada para F3.
- **Sem revogação automática:** chaves vazadas devem ser removidas manualmente do diretório de chaves confiáveis.
- **Sem suporte a HSM:** chaves são arquivos PEM no filesystem.

## Proibições (A6)

- ❌ Nunca logar, persistir em artifacts, ou expor secrets de CI.
- ❌ Nunca criar chave automática em runner efêmero — `ci-key` requer secret explícito.
- ❌ Nunca commitar chaves privadas no repositório.

## Disclosure de vulnerabilidades

**NÃO abra issue pública** para vulnerabilidades.

1. Envie email para `danzeroum@proton.me` com assunto `audio-suite security disclosure`.
2. Inclua: descrição, reprodução, impacto, sugestão de mitigação.
3. Resposta esperada em até 72h.
4. Após correção, creditaremos o reportador no `CHANGELOG.md` (a menos que prefira anonimato).

## Escopo do suporte

| Versão | Suporte |
|--------|---------|
| 0.2.0-beta | Apenas correções críticas |
| 0.3.x | Beta + melhorias |
| 1.0.x (futuro) | GA com SLA definido |
