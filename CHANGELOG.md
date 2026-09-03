# Changelog

All notable changes to audio-suite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — PROF-08.r (Onda 4)
- **Linter do registry de rule_ids** (`scripts/lint_rule_registry.py`): a R1 deixa de ser promessa e vira teste executável em três camadas — (1) perfis shipped: nenhum strict_overlay mapeia métrica descritiva/forense (AS-DESC-*/AS-FORE-*) para fail; (2) probe dinâmico: todos os analyzers rodam sobre 5 sinais sintéticos canônicos — nenhum finding never-fail termina em fail/error; (3) scan estático AST: módulos com regras never-fail (descriptors.py, lra.py) não podem conter literais `Status.FAIL/Status.ERROR`.
- CI (job `rule-registry-lint`) + hook `.githooks/pre-commit` (linter + anti-binários; ativar com `git config core.hooksPath .githooks`).
- **DoD demonstrado**: `Status.FAIL` injetado no `timbre_distance` → linter rejeita com 5 violações (exit 1); revertido → exit 0. Teste de unidade reproduz a violação via analyzer renegado no registry sandbox.

### Added — GOV-13 (Onda 4)
- **Sync backlog ↔ GitHub Issues** (`scripts/sync_issues.py` + `backlog.yaml`): materializa os 16 IDs das Ondas 3–5 como issues com labels `onda/<N>` e `prio/<pN>`, idempotente por marker oculto no corpo (`<!-- audio-suite-backlog: <ID> -->`). Itens arquivados com gatilho (VI.2, BACKLOG-13/14) não viram issue por padrão (opt-in `--include-archived`). Resiliente a token sem permissão de edição (avisa e continua). Labels `onda/3..5` + `prio/p0..p3` criadas no repo; 16 issues materializadas (#20–#35); re-execução: 0 duplicatas.

### Added — GOV-12 (Onda 4)
- **`AGENTS.md`** (handoff para agentes de IA): comandos de build/teste/lint, invariantes R1/R2/R4/R8, regra do SHA de validação e lista explícita de "nunca fazer" (port Rust sem gatilho, HMAC, fail em descritivo, binário no repo, regenerar golden sem label, RNG global, timestamps no payload determinístico, reabrir decisões arquivadas).

### Added — GOV-11 (Onda 4)
- **`docs/adr/`** formalizado (diretório antecipado no TEST-03.r): `TEMPLATE.md` + ADR-0001 (**reservado** — proveniência de código externo, verificação GPL bloqueante, pré-condição do eixo Rust arquivado VI.2), ADR-0002 (tolerâncias empíricas ±2σ e política de regeneração do Golden Master), ADR-0003 (fuzz fail-open→fail-closed, via TEST-03.r), ADR-0004 (rejeição do HMAC, remetendo a N-19/Ed25519).

### Added — EVID-08 (Onda 4)
- **`--frozen-manifest` (+ `--strict`)**: reprodutibilidade forte de laudo. Pré-check recusa execução se versão da tool, de qualquer analyzer, hash do profile resolvido ou `environment_hash` divergirem do bundle congelado — **erro nomeia o campo divergente**. `--strict` (com `--frozen-manifest`) exige ainda identidade byte a byte pós-run, exceto campos declarados não-determinísticos (`subject.source_path`, `signature`, `reproduction_command` — todos embutem identidade local do filesystem).
- **Novo exit code 65** (`FROZEN_MANIFEST_MISMATCH`, sysexits `EX_DATAERR`) — quebra declarada (SemVer 0.x), contrato de exit codes estendido.
- **Refinamento EVID-07 declarado:** `reproduction_command` não inclui mais `--output` (destino não é semântica da análise) nem `--strict` (dupla semântica: overlay + verificação; o estado do overlay fica em `profile.strict` no bundle) — pré-requisito para a identidade byte a byte.
- **Determinismo de findings:** `evidence.source_path` (local) é removido do payload canônico dos findings — findings descrevem o áudio, não o filesystem; `measurement_fingerprint` fica estável entre caminhos/máquinas.

### Added — EVID-07 (Onda 4)
- **`reproduction_command`** no bundle JSON e no SARIF: comando exato para re-executar a análise (ordem fixa de flags; `--output` incluído só quando usado). Com o `environment_hash` (EVID-02.r+), ambiente igual + comando igual → bundle byte a byte (ver EVID-08).

### Added — EVID-02.r+ (Onda 4)
- **Snapshot de ambiente ampliado** no bundle e no SARIF (`audio_suite/environment.py`): versões (python/numpy/scipy/soundfile), plataforma, **SHA-256 do profile YAML resolvido** (com defaults dos schemas aplicados, canônico), **versão de cada analyzer**, e **`dsp_backend`** (`python` — reference implementation; campo existe para o futuro backend gated, VI.2).
- **`environment_hash`**: SHA-256 do JSON canônico do snapshot.
- **Quebra de contrato declarada (SemVer 0.x):** a assinatura Ed25519 agora cobre também o bloco `environment` — laudos assinados antes de 2026-09-03 não verificam com a nova versão sem re-verificação pelo payload antigo. `schemas/bundle-v1.json` atualizado (campos opcionais).

### Added — ENG-13 (Onda 4)
- **`audio-suite compare A.wav B.wav`** (maior valor do plano): diff acústico objetivo — ΔLUFS, ΔdBTP, ΔLRA, Δmono band loss; achados novos por rule_id (CONTR-02) em `findings.only_in_b`; descritores **sempre** como `observations` (R1 — nunca geram regressão).
- Saída `diff.json` com `regression_detected: bool` — true **somente** para defeito objetivo novo (rule_id flagado em B e não em A). Validação CONTR-01 contra `schemas/compare-v1.json` (nova). Flag `--fail-on-regression` para gate de CI.

### Added — CORP-08 (Onda 3)
- **Corpus de defeito injetado com ground truth** (`tests/corpus/defects.py`): 6 tipos (click, dropout, repetição/buffer stutter, clipping sustentado, DC offset, gap), todos seed-based e byte-determinísticos, anotados com `expected_findings: list[rule_id]` validados contra CONTR-02.
- **`scripts/detector_score.py`**: precisão/recall por detector e por rule_id sobre o corpus; tabela publicada no README, artifact JSON/MD no CI (job `detector-score`).
- **Gap de cobertura documentado**: `dc_offset` não tem detector registrado — recall N/A publicado explicitamente (não escondido).
- Testes do corpus funcionam como gate de qualidade: detector que regridir (recall < 1.0 no corpus) quebra o CI.

### Added — CORP-04 + CORP-04.r (Onda 3)
- **Golden Master de processo**: `tests/golden/expected/<analyzer>.json` para os 10 analyzers-core (loudness, true_peak, clipping, glitch, lra, spectral, transient, mono_compat, descriptors×7, inspect) sobre 12 fixtures seed-based.
- Tolerâncias **por analyzer** (`tolerances` no `tests/golden/manifest.yaml`), **derivadas empiricamente** (±2σ via jitter relativo de 1 ulp float32; proveniência completa em `tests/golden/calibration.json`) — nunca hard-code "0,05".
- Comando **`audio-suite golden freeze`** (regenera esperados) e **`audio-suite golden verify`** (compara; publicações `gm-diff.json` + `gm-diff.html` legíveis).
- Workflow **golden-guard.yml**: suíte GM no CI (< 90 s; roda em ~9 s) + bloqueio de PR que regenere golden files sem label `golden-regen` + justificativa no CHANGELOG.
- Profile GM fixado (`tests/golden/gm_profile.yaml`) — GM congela comportamento, não configuração do default_profile.

### Changed — CORP-04
- `glitch._detect_repetition` vetorizado com **equivalência bit a bit comprovada** (teste de referência incluído): o scan O(n×L) em loop Python custava ~4,6 s por fixture de 3 s e estourava o orçamento GM; agora ~19 ms (soma deslizante de igualdades elementares). Nenhum resultado muda — o GM congela comportamento, não o algoritmo.

### Evidência DoD (CORP-04)
- Off-by-one no fator de oversampling do true peak (4→3) injetado em branch de demonstração: **rejeitado** com 4 violações legíveis (|Δ| até 0,137 dB > tol 0,001) e `gm-diff.html` gerado.
- Suíte GM completa: 9,3 s (< 90 s).

### Added — CORP-01.r (Onda 3)
- Geradores **seed-based** como fonte primária de todo fixture: módulo canônico `tests/fixtures/generators.py` com `FixtureSpec` + `FIXTURE_SPECS` (38 fixtures), RNG sempre `numpy.random.Generator(PCG64(seed))` local — API global (`np.random.seed`/`random.*`) proibida e verificada por teste.
- Política **anti-binários**: `scripts/check_no_large_binaries.py` + job CI `policy-binaries` — falha se qualquer `.wav`/`.flac`/`.mp3`/… rastreado exceder 1 MB (CORP-01.r / regra 7).
- Manifest de fixtures com schema estendido: `seed`, `generator` e `expected_findings` (opcional, `list[rule_id]` validado contra o registro CONTR-02).

### Changed — CORP-01.r
- **Quebra declarada (SemVer 0.x):** `sine_1k_float32.wav` agora é serializado por writer WAV float32 determinístico (numpy-only, sem chunk PEAK). O libsndfile embutia um timestamp de wall-clock no chunk PEAK de WAVs float — o fixture nunca foi byte-reprodutível; hashes canônicos mudaram.
- `high_bw_96k.wav` é gravado a 96 kHz de fato (antes o gerador antigo gravava a 44,1 kHz apesar do manifest declarar 96000).

### Added
- Plano consolidado de desenvolvimento (`docs/desenvolvimento/plano-consolidado.md`)
- Prompt para agente de implementação (`docs/desenvolvimento/prompt-agente-implementacao.md`)

### Changed
- Onda 0: higiene de repositório (LICENSE, CHANGELOG, CONTRIBUTING, CODEOWNERS)

## [0.1.0] - 2026-09-02

### Added
- 35 analyzers across Phases 1-5.5
- CLI with exit codes 0/1/2/3/64
- JSON, SARIF 2.1.0, HTML, CSV output formats
- Ed25519 signed evidence bundles
- Audit log with hash chaining
- Self-check command
- Cartridge API for external plugins
- 203 unit tests, 86% coverage
- CI: ruff + mypy + pip-audit, pytest 3.11/3.12/3.13, Docker, release
