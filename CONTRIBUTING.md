# Contributing to audio-suite

Thank you for your interest in contributing to audio-suite! This document outlines the process for contributing to the project.

## Quick Start

```bash
# Clone and install
git clone https://github.com/danzeroum/audio-suite.git
cd audio-suite
pip install -e ".[dev]"

# Generate test fixtures
python scripts/gen_fixtures.py

# Run tests
pytest tests/ -v --cov=audio_suite

# Lint
ruff check audio_suite tests
ruff format --check audio_suite tests
```

## Development Workflow

1. **Fork** the repository
2. **Create a branch** from `main`: `feat/<category>-<id>-<description>` (e.g., `feat/gov-01-license`)
3. **Implement** following the code style (ruff, type hints, frozen dataclasses)
4. **Test** — all tests must pass, coverage must not regress
5. **Commit** using [conventional commits](https://www.conventionalcommits.org/):
   - `feat(gov-01): add MIT license`
   - `fix(eng-01): timeout per analyzer`
   - `docs(conf-02): EBU conformance suite`
6. **Push** and open a Pull Request
7. **CI must pass** before merge

## Code Style

- **Python:** 3.11+, type hints required, `from __future__ import annotations`
- **Formatter:** ruff format (line-length 110)
- **Linter:** ruff check
- **Type checker:** mypy (strict on critical modules)
- **Dataclasses:** `frozen=True` for immutable models (PCM, Finding, Bundle, Profile)

## Inviolable Rules

Every contribution MUST respect these rules:

1. **R1:** Descriptive metrics (centroid, LRA, etc.) never cause `FAIL`
2. **R2:** No reference → full-reference metrics return `INDETERMINATE`
3. **R4:** ML analyzers are opt-in (`enabled: true` in profile)
4. **R8:** Never conclude authenticity — always `NEEDS_REVIEW`
5. **6-status contract:** `PASS / WARNING / FAIL / NEEDS_REVIEW / NOT_APPLICABLE / INDETERMINATE / ERROR`
6. **Exit codes:** `0=OK · 1=FINDING · 2=INVALID_PROFILE · 3=INVALID_INPUT · 64=USAGE`

## Testing

- **Unit tests:** `tests/unit/` — isolated analyzer/engine tests
- **Integration:** `tests/integration/` — end-to-end flows
- **Contracts:** `tests/contracts/` — schema, rule IDs, severity
- **Conformance:** `tests/conformance/` — EBU test set, golden vectors
- **Property:** `tests/property/` — hypothesis-based invariants
- **Architecture:** `tests/architecture/` — structural invariants

## Pull Request Checklist

- [ ] Code follows style (ruff check + format pass)
- [ ] All tests pass (`pytest tests/ -q`)
- [ ] Coverage did not regress
- [ ] No inviolable rule violated
- [ ] CHANGELOG.md updated
- [ ] Commit messages follow conventional commits

## Reporting Issues

Use [GitHub Issues](https://github.com/danzeroum/audio-suite/issues) with:
- Description of the problem
- Steps to reproduce
- Expected vs actual behavior
- audio-suite version (`audio-suite --version`)
- Sample audio file (if possible)
