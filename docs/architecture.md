# Architecture

## Visão geral

A `audio-suite` segue uma arquitetura de pipeline com 5 etapas:

1. **Discovery** — Identifica o arquivo de entrada e extrai metadados via `ffmpeg probe`
2. **Normalization** — Decodifica para PCM float32 canônico @ 48 kHz; computa SHA-256 do PCM
3. **Execution** — Carrega e executa cada analyzer declarado no profile YAML
4. **Policy** — Avalia findings contra thresholds do profile; decide `pass / warning / fail / indeterminate`
5. **Evidence** — Empacota tudo em um bundle JSON assinável (`unsigned` no Alpha)

## Componentes

### engine/

Núcleo orquestrador. Contém:
- `cli.py` — entrypoint Typer
- `discovery.py` — probe + PII detection
- `normalization.py` — decode PCM canônico
- `execution.py` — pipeline principal
- `policy.py` — carregamento de profiles YAML
- `evidence.py` — construção do bundle JSON
- `rights_validator.py` — valida rights manifest contra propósito do projeto

### analyzers/

Cada analyzer implementa `run_analyzer(pcm, media_info, params, verbose) -> List[finding]`.
Importante: nenhum analyzer hardcode limites — todos vêm do profile YAML via `params`.

### registry/

Profiles versionados (YAML) + rights manifest declarativo.
Profiles são imutáveis e identificados por `name + sha256`.

### contracts/

JSON Schema v7+ para:
- `audio-run-1.0.json` — bundle de evidência
- `audio-finding-1.0.json` — finding individual
- `provenance-statement-1.0.json` — declaração de cadeia de transformações

### integrations/

GitHub Action (Docker) e adapter para PSE (stub no Alpha).

## Decisões de design

### Por que YAML e não SQLite no Alpha?

Profiles versionados em YAML são diff-friendly e auditáveis via git.
SQLite adicionaria complexidade de schema e migração desnecessária nesta fase.

### Por que assinatura `unsigned`?

Assinatura requer chave privada protegida — não apropriado para Alpha público.
A estrutura está pronta; v1.0 adicionará suporte a chaves via env vars ou KMS.

### Por que nenhum analyzer hardcode limites?

Toda política deve ser auditável e versionada no git. Se um analyzer tivesse
limites hardcoded, uma mudança de regra exigiria mudança de código — frágil.
Profiles YAML permitem evolução sem deploy de código.
