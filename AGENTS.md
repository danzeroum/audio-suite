# AGENTS.md — Handoff para agentes de IA

Guia operacional para agentes de código (Claude Code, OpenCode, etc.)
trabalhando no `audio-suite`. Leia por completo antes do primeiro commit.

> **Fonte de verdade:** `docs/desenvolvimento/documento-mestre-v1.2.md`.
> Este arquivo operacionaliza; o Documento Mestre decide.

## Regra do SHA de validação

**Todo PR, toda análise, toda afirmação sobre o estado do repositório deve
citar o SHA do commit que inspecionou.** Validações sem SHA discutem estados
diferentes do mundo. Formato no corpo do PR:

```
**SHA inspecionado:** `<sha completo>` (main pós <referência curta>)
```

Se o código divergir do prompt/docs: **o estado do código vence para fatos,
o Documento Mestre vence para decisões** — registre a divergência num
comentário do PR antes de prosseguir (nunca contorne).

## Comandos essenciais

```bash
# Ambiente
pip install -e ".[dev]"                       # numpy é a ÚNICA dependência runtime
python scripts/gen_fixtures.py                # gera fixtures seed-based (obrigatório antes dos testes)

# Testes
pytest tests/unit tests/property tests/architecture tests/contracts \
       tests/e2e tests/conformance tests/metamorphic tests/corpus tests/golden -q
pytest tests/fuzz -q                          # política: docs/adr/ADR-0003
pytest tests/golden -q                        # Golden Master (< 90 s de budget)

# Qualidade
ruff check audio_suite tests scripts && ruff format --check audio_suite tests
mypy audio_suite --ignore-missing-imports || true

# Golden Master (CORP-04)
audio-suite golden verify --diff-dir /tmp/gm   # verificar (publica gm-diff.json/html)
audio-suite golden freeze                      # REGENERA esperados → exige label golden-regen

# Corpus de detectores (CORP-08)
python scripts/detector_score.py               # precisão/recall por detector

# Políticas
python scripts/check_no_large_binaries.py      # anti-binários (CORP-01.r)
python scripts/lint_rule_registry.py           # linter R1 (PROF-08.r) — CI + .githooks/pre-commit
```

Um PR por item, pequeno, com testes novos passando e CHANGELOG atualizado.
Título: `W<N>: <ID> — <resumo>`.

## Invariantes (Documento Mestre §2 — verifique a cada PR)

| Regra | Enunciado operacional |
|---|---|
| **R1** | Métricas **descritivas** (centroid, BPM, tonalidade, irregularity, família `descriptors`, LRA) produzem apenas `pass`/`observation`/`baseline`/`needs_review` — **nunca** `fail`/`error`/exit code de falha. O linter (PROF-08.r) verifica; até lá, você é o lint. |
| **R2** | Sem referência, sem métrica full-reference. Proxies são explícitos e marcados. |
| **R2+** | **Runtime core é numpy-only** (scipy/soundfile são dependências de análise declaradas; nada além). Qualquer sugestão de dependência nova no caminho core é rejeitada. |
| **R4** | ML sempre opt-in. Nenhum modelo bundled no core. |
| **R8** | **Nunca conclua autenticidade.** deepfake/ENF terminam sempre em `needs_review`. |

Contrato estrutural: 6 status (`PASS/WARNING/FAIL/NEEDS_REVIEW/NOT_APPLICABLE/INDETERMINATE`)
+ exit codes (`0/1/2/3/64` + `65` para frozen-manifest mismatch).

## NUNCA fazer (lista explícita)

1. **Portar kernels para Rust / criar crate / adicionar dependência de build**
   — o eixo Rust está ARQUIVADO com gatilho (VI.2): TEST-05 violado em ≥2
   analyzers OU demanda real via ENG-03. Sem o gatilho, recuse citando VI.2.
2. **Implementar HMAC** (nem "opcional") — assinatura é Ed25519, verificação
   pública por terceiros (ADR-0004).
3. **Fazer métrica descritiva falhar** — viola R1; o linter reprova o commit.
4. **Commitar binário de áudio** (`*.wav`/`*.flac`/`*.mp3`/… > 1 MB ou
   qualquer fixture binária) — fixtures são seed-based em
   `tests/fixtures/generators.py`; só `manifest.json` é versionado.
5. **Regenerar golden files sem label `golden-regen` + justificativa no
   CHANGELOG** — o guard `golden-guard.yml` reprova o PR.
6. **Comparar floats cross-language bit a bit** — tolerâncias empíricas ±2σ
   (`tests/golden/calibration.json`, ADR-0002).
7. **Importar código de `au3/` (Audacity, GPL)** — proibido, bloqueante
   (ADR-0001 / regra 6). Código de `danzeroum/mixlirous` exige ADR de
   proveniência ANTES do port.
8. **Usar RNG global** (`np.random.seed`, `random.*`) em geradores/analyzers —
   use `make_rng(seed)` (numpy.random.Generator local).
9. **Adicionar timestamps/caminhos locais ao payload determinístico** —
   findings não descrevem o filesystem; campos declarados não-determinísticos
   estão em `audio_suite/frozen.py`.
10. **Reabrir decisões arquivadas** (Rust, HMAC, pydantic, bit-for-bit) sem
    passar pelo protocolo de triagem do Documento Mestre §10.

## State real — onde olhar antes de assumir

| Caminho | Estado |
|---|---|
| `tests/fixtures/generators.py` | fonte primária de todo fixture (CORP-01.r) |
| `tests/golden/` | manifest + expected/*.json + calibration.json (CORP-04) |
| `tests/corpus/defects.py` | corpus de defeito injetado com ground truth (CORP-08) |
| `docs/adr/` | decisões arquiteturais (GOV-11) — leia antes de propor mudanças |
| `audio_suite/environment.py` | snapshot de ambiente + reproduction_command (EVID-02.r+/07) |
| `audio_suite/frozen.py` | campos declarados não-determinísticos (EVID-08) |

## Tolerâncias e métricas: derive, não escolha

Toda constante de tolerância deriva empiricamente (±2σ do corpus de
calibração) com os números mostrados no PR. Escolher constante "de cabeça"
viola o protocolo de execução (item 4) e o ADR-0002.
