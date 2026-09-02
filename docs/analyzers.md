# Analyzers

Documentação técnica de cada analyzer disponível na audio-suite.

Cada analyzer implementa:
```python
def run_analyzer(pcm, media_info, params, verbose) -> list[finding]
```

**Regra obrigatória (A4):** nenhum analyzer hardcode limites — tudo vem do profile YAML via `params`.

---

## loudness

| Campo | Valor |
|-------|-------|
| **Métrica** | Integrated Loudness (LUFS) |
| **Unidade** | LUFS |
| **Método** | EBU R 128-B via pyloudnorm |
| **Params** | `target_integrated_lufs` (float, default -23.0), `tolerance_lufs` (float, default 0.5) |
| **Limitações** | Requer áudio ≥ 0.5s; sensível a silêncio no início/fim |
| **Reliability** | high (para duração ≥ 3s) |

---

## signal

| Campo | Valor |
|-------|-------|
| **Métricas** | True peak (dBTP), sample peak (dBFS), clipping detection, DC offset |
| **Unidade** | dBTP / dBFS / linear |
| **Método** | Oversampling ×4 via scipy.signal.resample_poly (kaiser window) |
| **Params** | `max_true_peak_dbtp` (float, default -1.0), `allow_clipping` (bool, default false) |
| **Limitações** | True peak é estimativa; precisão depende do oversampling |
| **Reliability** | high |

---

## phase

| Campo | Valor |
|-------|-------|
| **Métrica** | Correlação inter-canal (Pearson) |
| **Unidade** | correlation (-1..+1) |
| **Método** | Pearson entre canais L e R |
| **Params** | `min_correlation` (default 0.9), `min_energy` (default 1e-5), `min_duration_s` (default 0.5) |
| **Limitações** | Requer estéreo; decorrelação pode ser criativa (A4) |
| **Reliability** | contextual (high/medium/low baseado em duração + energia) |

**Importante (A4):** correlação ≈ -1 é **sinal**, não **prova** de inversão de polaridade. Conteúdo estéreo amplo, ambient mics e material decorrelacionado intencionalmente podem ter correlação baixa.

---

## metadata

| Campo | Valor |
|-------|-------|
| **Métrica** | Tags ID3/RIFF + detecção de PII |
| **Unidade** | count |
| **Método** | ffmpeg probe + regex (email/telefone/CPF) |
| **Params** | (nenhum) |
| **Limitações** | PII só em tags; não cobre PII em waveform (ASR futuro) |
| **Reliability** | high |

**Redação (O9):** valores de PII são redigidos no bundle (`***@***.**`), preservando hash curto para correlação.

---

## provenance

| Campo | Valor |
|-------|-------|
| **Métrica** | Status da cadeia de eventos |
| **Unidade** | enum: valid / gap / invalid / not_provided |
| **Método** | Validação de hash encadeado + assinatura opcional |
| **Params** | `require_signature` (bool, default false) |
| **Limitações** | Não reconstrói provenance; apenas valida (A3) |
| **Reliability** | high |

**Importante (A3):** gap não é fail universal — a policy decide se vira `warning`, `fail`, `indeterminate` ou `needs_review`.

---

## rights_manifest

| Campo | Valor |
|-------|-------|
| **Métrica** | Conflitos de licença vs. propósito do projeto |
| **Unidade** | enum: valid / fail / needs_review |
| **Método** | YAML parsing + regras declarativas |
| **Params** | (nenhum) |
| **Limitações** | Não valida licença do áudio em si, apenas a declaração |
| **Reliability** | high |

Regras:
- `commercial_use_allowed=false` + `purpose=commercial_campaign` → fail
- `attribution_required=true` + `attribution_text` vazio → fail
- Licença não reconhecida → needs_review

---

## Stubs (não implementados no Beta)

| Analyzer | Estado |
|----------|--------|
| `regression` | Stub — golden master diff adiando para F4 |
| `similarity` | Stub — fingerprint não é prova de titularidade |
| `speech` | Stub — PESQ/POLQA/ViSQOL adiados |

Todos retornam finding `indeterminate` com descrição explicando o que falta.

---

## Adicionando um novo analyzer

Veja [`CONTRIBUTING.md`](../CONTRIBUTING.md).
