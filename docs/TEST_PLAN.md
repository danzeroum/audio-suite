# Plano de Testes — audio-suite v0.2.0-beta

## 1. Estratégia

Pirâmide de testes:
- **Unitários (~70%)**: por módulo, isolados, rápidos (<100ms cada).
- **Integração (~20%)**: entre 2-3 módulos (ex.: CLI → execution → evidence).
- **End-to-end (~10%)**: fixtures de mordida, saída completa do bundle.

Ferramentas:
- `pytest` + `pytest-cov` (cobertura).
- `pytest-timeout` (proteção contra hangs em testes que envolvem subprocess).
- `tmp_path` para isolamento de filesystem.
- `mypy --strict` para verificação de tipos estáticos.
- `ruff` para lint.

## 2. Categorias de Teste

### 2.1 Unitários por módulo

Cada módulo deve ter:
- **Happy path**: entrada válida → saída esperada.
- **Edge cases**: entradas degeneradas (vazio, mínimo, máximo).
- **Error cases**: entrada inválida → exceção correta ou status `indeterminate`.
- **Determinismo**: mesma entrada → mesma saída (com epsilon para floats).

### 2.2 Integração

- CLI `validate` gera bundle válido contra `contracts/audio-run-1.0.json`.
- CLI `inspect` produz JSON compatível com schema de inspect.
- CLI `verify` rejeita bundle adulterado.
- Analyzer failure → finding `indeterminate` no bundle (não crash).

### 2.3 End-to-end com fixtures

Para cada fixture:
1. Carregar `expected.json`.
2. Rodar `audio-suite validate fixture.wav --profile <yaml> --output bundle.json`.
3. Verificar `bundle.decision == expected.decision`.
4. Verificar que pelo menos um finding tem `status == "fail"` para o analyzer esperado.
5. Verificar `measurement_fingerprint` é determinístico entre execuções.

## 3. Fixtures de Mordida (10 casos)

| Fixture | Profile | Decision esperada | Analyzer que falha |
|---------|---------|-------------------|--------------------|
| `clean_pass.wav` | broadcast_ebu_r128_v1 | `pass` | nenhum |
| `clipped_sine.wav` | broadcast_ebu_r128_v1 | `fail` | signal (clipping) |
| `true_peak_over.wav` | broadcast_ebu_r128_v1 | `fail` | signal (TP > -1) |
| `lufs_too_hot.wav` | broadcast_ebu_r128_v1 | `fail` | loudness |
| `inverted_polarity.wav` | broadcast_ebu_r128_v1 | `fail` | phase |
| `mono_when_stereo_req.wav` | broadcast_ebu_r128_v1 | `fail` | signal (channels) |
| `metadata_with_email.wav` | broadcast_ebu_r128_v1 | `fail` | metadata (PII) |
| `silence_5s.wav` | broadcast_ebu_r128_v1 | `indeterminate` | signal (silence) |
| `rights_nc_commercial.yaml` | (rights) | `fail` | rights_manifest |
| `provenance_gap.json` | (provenance) | `indeterminate` | provenance |

Cada fixture tem:
- Arquivo de áudio (ou YAML/JSON para casos não-áudio).
- `expected.json` com: `decision`, `failed_analyzers[]`, `expected_findings[]`, `fixture_sha256`.
- Gerador determinístico (script Python) — não usar áudio de terceiros.

## 4. Casos de Teste Especiais (Adendos)

### A2/O5 — Reprodutibilidade
- Rodar `validate` 2x no mesmo arquivo → `bundle_sha256` diferente (timestamps), mas `measurement_fingerprint` idêntico.

### A3 — Provenance
- Provenance com gap → finding `gap`, decisão controlada por policy (não hardcoded fail).

### A4 — Phase
- Áudio mono → analyzer `not_applicable`.
- Áudio estéreo decorrelacionado intencionalmente → correlação baixa, mas `reliability` não hardcoded.

### A6 — Assinatura
- Bundle assinado em modo `local-key` → `verify` retorna `valid`.
- Bundle com 1 byte alterado → `verify` retorna `invalid`.
- Bundle sem assinatura → `verify` retorna `unsigned`.
- Bundle com `key_id` desconhecido → `verify` retorna `key_unknown`.

### O1 — TOCTOU
- Modificar arquivo entre probe e decode → finding `TOCTOU-01`, decisão `indeterminate`.

### O2 — Timeout
- Configurar analyzer com timeout = 0.001s em áudio longo → finding `indeterminate` com `limitations: ["analyzer_timeout:X"]`.

### O3 — Schema validation
- Construir bundle inválido (manual) → `save_bundle` levanta exceção.

### O4 — Escrita atômica
- Simular falha durante escrita (mock `open`) → arquivo `.tmp` removido, arquivo final não existe.

### O8 — Entradas degeneradas
- WAV com 0 amostras → `indeterminate`, `limitations: ["empty_audio"]`.
- WAV com NaN → sanitizado, `limitations: ["nan_samples_sanitized"]`.

### O9 — PII redaction
- Tag com email `foo@bar.com` → bundle contém `***@***.**` (não o email original).

### O10 — Truncagem
- Gerar 200 findings de clipping → bundle tem 100 + 1 agregado `{"name": "Clipping (additional)", "count": 100}`.

## 5. Critérios de Aceite da Suíte

- [ ] Cobertura global ≥ 70%.
- [ ] Cobertura por módulo ≥ 60%.
- [ ] Todos os 10 fixtures passam em expected.json.
- [ ] mypy --strict sem erros.
- [ ] ruff sem warnings.
- [ ] Tempo total de execução da suíte < 60s.
- [ ] Testes são determinísticos (rodar 3x, mesmo resultado).

## 6. Ordem de Execução no CI

1. Lint (`ruff check .`)
2. Type-check (`mypy engine analyzers`)
3. Unit tests + coverage (`pytest tests/unit --cov`)
4. Integration tests (`pytest tests/integration`)
5. E2E tests com fixtures (`pytest tests/e2e`)
6. Schema validation (`pytest tests/contracts`)
7. Build do pacote (`python -m build`)
8. Smoke test em venv limpo

## 7. Matriz de Cobertura Esperada

| Módulo | Cobertura alvo |
|--------|---------------|
| engine/cli.py | ≥ 75% |
| engine/execution.py | ≥ 80% |
| engine/evidence.py | ≥ 80% |
| engine/normalization.py | ≥ 70% |
| engine/policy.py | ≥ 85% |
| engine/discovery.py | ≥ 75% |
| engine/bundle/*.py | ≥ 80% |
| analyzers/*.py | ≥ 70% cada |
| engine/cli_formats/*.py | ≥ 80% |
| **Global** | **≥ 75%** |
