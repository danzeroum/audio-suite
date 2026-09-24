# Caso de uso — Gate pós-render do mixlirous com o audio-suite

**ID:** DOCS-04.r (Documento Mestre v1.2, Adendo B) · **Onda:** 5 · **Status:** aprovado — **forma CLI pendente** (ver §2.3)
**SHA inspecionado (audio-suite):** `296226eb803adbe380f1473c25c5a22ebb857029`
**SHA inspecionado (mixlirous):** `5048a107a28524fc515bd7bd26805514a37187d9`

> **Revisão (2026-09-24).** A versão anterior deste documento, escrita contra
> o audio-suite `e5d518e`, chamava `mixlirous render track.json --out render.wav`.
> **Esse comando não existe** no mixlirous: o workspace
> (`Cargo.toml` → `crates/audio_core`, `crates/audio_agent`, `crates/audio_api`)
> declara um único binário, o servidor HTTP `audio_api`, e o mixlirous não
> tem conceito de `track.json`. Ele recebe um WAV, cria uma *track* e roda
> um *job* de remix que produz `remix.wav`. Este documento passa a descrever
> o que existe (§2.2, via HTTP) e marca a forma CLI como **pendente**,
> com o contrato pedido ao mixlirous em issue própria (§2.3). Regra do
> AGENTS.md: o código vence para fatos.

## 1. Objetivo

Fechar o loop de QC entre o **mixlirous** (que renderiza/remixa) e o
**audio-suite** (que audita de forma independente e evidence-grade): todo WAV
renderizado passa por um gate objetivo antes de virar entrega. O gate
responde duas perguntas com evidência assinável:

1. **O render viola o limiar de plataforma?** (perfil `music-master/streaming`
   — loudness/true peak/defeitos objetivos)
2. **O render regrediu em relação à referência?** (comando `compare`, ENG-13)

## 2. Padrão de uso

### 2.1 O lado audio-suite (existe e está validado)

Dado um `render.wav` e uma referência `reference/render_ref.wav`:

```bash
pip install git+https://github.com/danzeroum/audio-suite.git@main

# Gate de plataforma (music-master/streaming)
audio-suite analyze render.wav \
  --profile profiles/music-master/streaming.yaml \
  --strict --format json --output bundle-render.json
# exit 1 = algum limiar objetivo violado (finding de nível fail)

# Diff contra a referência (ENG-13)
audio-suite compare reference/render_ref.wav render.wav \
  --profile profiles/music-master/streaming.yaml \
  --fail-on-regression --output diff.json
# exit 1 = regression_detected (defeito objetivo novo em B)
```

O `bundle-render.json` sai com `environment_hash` e `reproduction_command`.
Com `--frozen-manifest`, as re-execuções saem idênticas byte a byte. O laudo
é reproduzível, não uma impressão descartável.

### 2.2 O lado mixlirous hoje: render via API HTTP (existe)

O único caminho de render no SHA inspecionado é o servidor `audio_api`
(Axum, porta 8080, rotas sob `/api/v1`). Em modo local
(`CONFIG_ENV=local`), `GET /api/v1/auth/local-session` emite o JWT de
sessão. Fora do modo local, essa rota devolve 404 de propósito, e o token vem do
provedor de identidade do deploy. O pipeline de remix é **mono**
(`worker.rs`: downmix antes do DSP).

```bash
# no checkout do mixlirous
CONFIG_ENV=local cargo run --release --bin audio_api &   # escuta em 0.0.0.0:8080
API=http://localhost:8080/api/v1
until curl -fsS http://localhost:8080/healthz >/dev/null; do sleep 1; done

TOKEN=$(curl -fsS "$API/auth/local-session" | jq -r .token)
AUTH="Authorization: Bearer $TOKEN"

# 1. presign + upload do WAV de entrada
TAM=$(stat -c %s entrada.wav)
PRE=$(curl -fsS -X POST "$API/uploads/presign" -H "$AUTH" -H 'Content-Type: application/json' \
      -d "{\"filename\":\"entrada.wav\",\"size_bytes\":$TAM,\"content_type\":\"audio/wav\"}")
curl -fsS -X PUT "http://localhost:8080$(jq -r .upload_url <<<"$PRE")" -H "$AUTH" \
     -H 'Content-Type: audio/wav' --data-binary @entrada.wav

# 2. track
TRACK=$(curl -fsS -X POST "$API/tracks" -H "$AUTH" -H 'Content-Type: application/json' \
        -d "{\"object_key\":\"$(jq -r .object_key <<<"$PRE")\",\"display_name\":\"entrada\"}" | jq -r .track_id)

# 3. job de remix (modo manual, receita default)
JOB=$(curl -fsS -X POST "$API/jobs" -H "$AUTH" -H 'Content-Type: application/json' \
      -d "{\"track_id\":\"$TRACK\",\"mode\":\"manual\"}" | jq -r .job_id)

# 4. esperar estado terminal
until S=$(curl -fsS "$API/jobs/$JOB" -H "$AUTH" | jq -r .status); \
      [ "$S" = completed ] || [ "$S" = failed ] || [ "$S" = cancelled ]; do sleep 1; done
[ "$S" = completed ] || { echo "job $JOB terminou em $S"; exit 1; }

# 5. artefato
curl -fsS "$API/jobs/$JOB/artifact" -H "$AUTH" -o render.wav
```

A partir daqui, `render.wav` entra no §2.1.

**Limites honestos deste caminho.** Ele exige um servidor de pé no job de CI.
O `track_id`/`job_id` é UUIDv4, novo a cada execução. A receita (`pipeline_config`)
é opcional no corpo do `POST /jobs` e, sem ela, vale o default do
`PipelineConfig`. No modo `assisted`, o job passa pelo agente e por propostas
com aprovação humana (HITL), e portanto **não serve para gate automático**:
use `manual`. Para CI, a forma certa é uma CLI (§2.3).

### 2.3 Pendente de CLI no mixlirous

Não há comando de linha para render nem para a distância de fingerprint do
Golden Master do mixlirous (`AudioFingerprint::distance` existe só como
biblioteca em `crates/audio_core/src/domain/fingerprint.rs`). O contrato de
que este caso de uso precisa está pedido em
**ISSUE_MIXLIROUS**. Enquanto ela não for implementada, **nenhum** exemplo
deste documento invoca `mixlirous <subcomando>`.

## 3. Mapeamento status ↔ limiares de Golden Master do mixlirous

Os limiares **0,05 / 0,15 / 0,35** do mixlirous (`docs/09-MLOPS-GOLDEN-MASTER.md`,
"Limiares") são limiares de **distância de fingerprint**
(`AudioFingerprint::distance`, adimensional, ≈ [0, 1]: MFCC + centroide +
RMS + contraste espectral + pico + duração, ponderados). Eles **não** se
aplicam aos deltas do `diff.json` do audio-suite, que têm unidade física
(LU, dB, dBTP). A versão anterior deste documento aplicava 0,05/0,15/0,35
sobre `deltas`, o que misturava escalas.

O mapeamento fiel à tabela do mixlirous, na linguagem de status do audio-suite:

| Distância de fingerprint (mixlirous) | Leitura no mixlirous | Status do gate |
|---|---|---|
| d < **0,05** | indistinguível — passa | `pass` |
| **0,05 ≤ d < 0,15** | diferença sutil — passa com aviso no PR | `warning` |
| **0,15 ≤ d ≤ 0,35** | mudança audível — falha, exige aprovação humana | `needs_review` (bloqueia merge até aprovação) |
| d > **0,35** | som diferente — falha, bloqueia merge | `fail` |

**Quem calcula a distância:** o mixlirous, não o audio-suite. Hoje, só
dentro dos testes Rust do próprio mixlirous. Quando a CLI do §2.3 existir,
o gate a lê de um JSON. Até lá, **este mapeamento não tem como ser
executado no pipeline de CI** e fica documentado como contrato.

Invariantes que o gate respeita:

- **R1:** métricas descritivas (timbre, fadiga, irregularidade…) entram no
  `diff.json` como `observations` e **nunca** disparam `fail`. O lado
  audio-suite do gate é acionado só por defeito objetivo
  (`regression_detected: true`) ou limiar de plataforma.
- **R8:** nada no gate conclui autenticidade de áudio forense. Se algum
  analyzer forense estiver no perfil, o resultado é sempre `needs_review`.
- **Tolerâncias:** qualquer limiar numérico **do audio-suite** vem de
  calibração empírica (±2σ, ADR-0002). Os limiares de fingerprint são do
  mixlirous e citados, não recalibrados aqui.

## 4. Implementação do gate (o que roda hoje)

```python
# gate_mixlirous.py — consome o diff.json do audio-suite (e, quando houver
# a CLI do mixlirous, o JSON da distância de fingerprint)
import json, sys

diff = json.load(open(sys.argv[1]))
if diff.get("regression_detected"):
    print("GATE: fail —", "; ".join(diff["regression_reasons"]))
    sys.exit(1)

if len(sys.argv) > 2:  # opcional: {"distance": <float>} da CLI pendente (§2.3)
    d = float(json.load(open(sys.argv[2]))["distance"])
    if d > 0.35:
        print(f"GATE: fail — distância de fingerprint {d:.3f} > 0,35"); sys.exit(1)
    if d >= 0.15:
        print(f"GATE: needs_review — distância {d:.3f} (mudança audível)"); sys.exit(2)
    if d >= 0.05:
        print(f"GATE: warning — distância {d:.3f} (diferença sutil)")

print("GATE: pass — sem regressão objetiva")
```

Saídas do script: `0` = pass/warning · `1` = fail (bloqueante) · `2` =
needs_review (bloqueia auto-merge). Os `deltas` e as `observations` do
`diff.json` vão anexados ao laudo como contexto, sem poder de bloqueio além
do que o `compare` já decidiu em `regression_detected`.

## 5. O que constitui evidência no fim do pipeline

| Artefato | Conteúdo | Garantia |
|---|---|---|
| `bundle-render.json` | laudo completo com findings + `environment` | assinável (Ed25519); `reproduction_command` embutido |
| `diff.json` | Δs objetivos + `regression_detected` + observations | schema `compare-v1` (CONTR-01); rule_ids estáveis (CONTR-02) |
| matriz de oráculos | loudness Python vs. mixlirous Rust (CONF-03.r) | divergência = `needs_investigation`, nunca silêncio. **Também depende de CLI do mixlirous** (`MIXLIROUS_CLI`); hoje fica em skip |
| Golden Master do audio-suite | métricas dos analyzers-core congeladas (CORP-04) | mudança de comportamento do medidor é visível e auditada |

## 6. Falhas comuns e o que significam

- **exit 1 no `analyze`**: violação de plataforma (true peak acima do teto,
  clipping, glitch). O render está objetivamente ruim: re-render.
- **exit 1 no `compare --fail-on-regression`**: regressão nova e objetiva contra
  a referência (glitch novo, clipping novo). Investigar a cadeia do mixlirous.
- **job em `failed` no §2.2**: o render não aconteceu, e não há o que auditar.
  O gate falha antes do audio-suite, com o `job_id` no log.
- **exit 65 (`frozen-manifest mismatch`)**: o ambiente do medidor divergiu do
  laudo congelado. O gate não pode comparar estados diferentes do mundo:
  é preciso congelar de novo, com justificativa (label `golden-regen` no audio-suite).
- **`needs_investigation` na matriz de oráculos**: os dois medidores de
  loudness divergem > 0,5 LU. Investigar antes de confiar em qualquer um.
