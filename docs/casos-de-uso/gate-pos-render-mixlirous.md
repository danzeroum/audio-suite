# Caso de uso — Gate pós-render do mixlirous com o audio-suite

**ID:** DOCS-04.r (Documento Mestre v1.2, Adendo B) · **Onda:** 5 · **Status:** aprovado
**SHA inspecionado:** `e5d518e7cfee0d4a5ae0659c1a91258be2ff8f06`

## 1. Objetivo

Fechar o loop de QC entre o **mixlirous** (que renderiza/masteriza) e o
**audio-suite** (que audita de forma independente e evidence-grade): todo WAV
renderizado passa por um gate objetivo no CI antes de virar entrega. O gate
responde duas perguntas com evidência assinável:

1. **O render viola o limiar de plataforma?** (perfil `music-master/streaming`
   — loudness/true peak/defeitos objetivos)
2. **O render regrediu em relação à referência?** (comando `compare`, ENG-13)

## 2. Padrão de uso

No pipeline do mixlirous, após cada render:

```yaml
# .github/workflows/mixlirous-qc.yml (no repo do mixlirous)
jobs:
  gate-pos-render:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: sudo apt-get install -y --no-install-recommends libsndfile1
      - name: Instalar audio-suite
        run: pip install git+https://github.com/danzeroum/audio-suite.git@main

      - name: Render (mixlirous)
        run: mixlirous render track.json --out render.wav

      - name: Gate de plataforma (music-master/streaming)
        run: |
          audio-suite analyze render.wav \
            --profile profiles/music-master/streaming.yaml \
            --strict \
            --format json --out bundle-render.json
          # exit 1 = algum limiar objetivo violado (fail-level finding)

      - name: Diff contra a referência (ENG-13)
        run: |
          audio-suite compare reference/render_ref.wav render.wav \
            --profile profiles/music-master/streaming.yaml \
            --fail-on-regression \
            -o diff.json
          # exit 1 = regression_detected (defeito objetivo novo)

      - name: Publicar laudo
        uses: actions/upload-artifact@v4
        with:
          name: laudo-qc
          path: |
            bundle-render.json
            diff.json
```

O `bundle-render.json` sai com `environment_hash`, `reproduction_command` e
(com `--frozen-manifest`) identidade byte a byte entre re-execuções — o laudo
é reproduzível, não uma impressão descartável.

## 3. Mapeamento status ↔ limiares de Golden Master do mixlirous

O mixlirous mantém seus próprios Golden Masters de render (desvio esperado
por parâmetro de mix). O gate converte o desvio medido pelo audio-suite nos
três estados de decisão — **os limiares são do Golden Master do mixlirous
(0,05 / 0,15 / 0,35), aplicados sobre a métrica de desvio** (Δ do parâmetro
auditado vs. seu valor de referência):

| Desvio medido (Δ vs. GM do mixlirous) | Status do gate | Ação no pipeline |
|---|---|---|
| Δ ≤ **0,05** | `pass` | segue para entrega; laudo anexado |
| **0,05 < Δ ≤ 0,15** | `needs_review` | humano aprova/analisa (bloqueia auto-merge) |
| **0,15 < Δ ≤ 0,35** | `needs_review` (forte) | investigação obrigatória + re-render sugerido |
| Δ > **0,35** | `fail` | pipeline **para**; re-render obrigatório; issue automática |

Regras que o gate NÃO viola (invariantes do audio-suite):

- **R1:** métricas descritivas (timbre, fadiga, irregularidade…) entram no
  `diff.json` como `observations` e **nunca** disparam `fail` — o gate é
  acionado só por defeito objetivo (`regression_detected: true`) ou limiar de
  plataforma.
- **R8:** nada no gate conclui autenticidade de áudio forense; se algum
  analyzer forense estiver no perfil, o resultado é `needs_review` sempre.
- **Tolerâncias:** qualquer limiar numérico do audio-suite vem de calibração
  empírica (±2σ, ADR-0002) — nunca de constante "de cabeça".

## 4. Implementação do mapeamento (trecho pronto para uso)

```python
# gate_mixlirous.py — consome o diff.json do audio-suite
import json, sys

GM_LIMIARES = {"pass": 0.05, "review": 0.15, "fail": 0.35}  # GM do mixlirous

diff = json.load(open(sys.argv[1]))
desvios = [abs(v) for v in diff.get("deltas", {}).values()]
desvio_max = max(desvios, default=0.0)

if diff.get("regression_detected"):
    print("GATE: fail —", "; ".join(diff["regression_reasons"]))
    sys.exit(1)
if desvio_max > GM_LIMIARES["fail"]:
    print(f"GATE: fail — desvio {desvio_max:.3f} > 0.35")
    sys.exit(1)
if desvio_max > GM_LIMIARES["review"]:
    print(f"GATE: needs_review — desvio {desvio_max:.3f} (0.15 < Δ ≤ 0.35)")
    sys.exit(2)  # bloqueia auto-merge, não falha o job
print(f"GATE: pass — desvio {desvio_max:.3f} ≤ 0.05")
```

Saídas do script: `0` = pass · `1` = fail (bloqueante) · `2` = needs_review
(bloqueia auto-merge). O desvio máximo é calculado apenas sobre os deltas
objetivos do `diff.json` — as `observations` são anexadas ao relatório para
contexto, sem poder de bloqueio.

## 5. O que constitui evidência no fim do pipeline

| Artefato | Conteúdo | Garantia |
|---|---|---|
| `bundle-render.json` | laudo completo com findings + `environment` | assinável (Ed25519); `reproduction_command` embutido |
| `diff.json` | Δs objetivos + `regression_detected` + observations | schema `compare-v1` (CONTR-01); rule_ids estáveis (CONTR-02) |
| matriz de oráculos | loudness Python vs. mixlirous Rust (CONF-03.r) | divergência = `needs_investigation`, nunca silêncio |
| Golden Master do audio-suite | métricas dos analyzers-core congeladas (CORP-04) | mudança de comportamento do medidor é visível e auditada |

## 6. Falhas comuns e o que significam

- **exit 1 no `analyze`**: violação de plataforma (true peak acima do teto,
  clipping, glitch) — o render está objetivamente ruim; re-render.
- **exit 1 no `compare --fail-on-regression`**: regressão objetivo-nova vs.
  referência (glitch novo, clipping novo) — investigar a cadeia do mixlirous.
- **exit 65 (`frozen-manifest mismatch`)**: o ambiente do medidor divergiu do
  laudo congelado — o gate não pode comparar estados diferentes do mundo;
  congelar novamente com justificativa (label `golden-regen` no audio-suite).
- **`needs_investigation` na matriz de oráculos**: os dois medidores de
  loudness divergem > 0,5 LU — investigar antes de confiar em qualquer um.
