# Changelog

All notable changes to audio-suite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
