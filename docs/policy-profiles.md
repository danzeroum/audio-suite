# Policy Profiles

Profiles são arquivos YAML versionados que definem:
- Quais analyzers executar
- Quais parâmetros passar para cada analyzer
- Severidade de cada check (error/warning/info)
- Política de decisão (fail_on, warning_on, unknown_on)

## Schema

```yaml
name: <string, identificador único>
owner: <string>
reference: <string, URL ou doc de referência>
description: <string>
checks:
  - id: <string>
    analyzer: <loudness|signal|metadata|...>
    params:
      <chave: valor, específico do analyzer>
    severity: <error|warning|info>
decision_policy:
  fail_on: error
  warning_on: warning
  unknown_on: indeterminate
```

## Profiles disponíveis

### broadcast_ebu_r128_v1

Para produção broadcast linear conforme EBU R 128.
- Target LUFS: -23.0 ± 0.5
- Max true peak: -1.0 dBTP
- Sem clipping permitido

### speech_pipeline_v1 (stub)

Para pipelines de fala (ASR/TTS). Métricas de inteligibilidade (PESQ, POLQA, ViSQOL)
adiadas para v0.2+ por questões de licenciamento.

## Criando um profile customizado

1. Copie `broadcast_ebu_r128_v1.yaml` para um novo arquivo
2. Edite `name`, `checks` e `decision_policy`
3. Versione no git — o hash SHA-256 do profile entra no bundle de evidência
4. Use via `--profile meu_profile.yaml`

## Boas práticas

- NUNCA edite um profile em produção sem bump de versão no nome
- Documente a racional em `description`
- Referencie padrões externos em `reference` (URL quando possível)
