# Changelog

All notable changes to audio-suite will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
