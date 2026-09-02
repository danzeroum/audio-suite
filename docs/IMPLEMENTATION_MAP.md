# Matriz de Rastreabilidade — audio-suite v0.2.0-beta

> Mapeamento item → arquivo implementado → testes que o cobrem.

Legenda: ✅ = implementado | 🧪 = coberto por teste | 📄 = apenas doc/contrato

## Fase 1 — Fundação Executável

| Item | Descrição | Implementação | Testes |
|------|-----------|---------------|--------|
| F1.1 | CI/CD completo (lint/type/test/audit/build/smoke) | `.github/workflows/ci.yml` | CI executa em PR |
| F1.2 | `audio-suite inspect <arquivo>` | `engine/cli.py::inspect` | `tests/test_cli_inspect.py` |
| F1.3 | Analyzer `phase` (correlação inter-canal) | `analyzers/phase.py` | `tests/test_analyzer_phase.py` |
| F1.4 | Analyzer `provenance` (DAG validation) | `analyzers/provenance.py` | `tests/test_analyzer_provenance.py` |
| F1.5 | Rights manifest validator | `analyzers/rights_manifest.py` + `registry/license-declarations/rights-manifest.schema.yaml` | `tests/test_rights_manifest.py` |
| F1.6 | Dockerfile reprodutível | `Dockerfile` (raiz) | `tests/test_dockerfile.py` (valida sintaxe + build simulated) |
| F1.7 | Workflow consumidor exemplo | `.github/workflows/consumer-example.yml` | 📄 apenas workflow |

## Fase 2 — Qualidade e Integração

| Item | Descrição | Implementação | Testes |
|------|-----------|---------------|--------|
| F2.1 | SARIF output (`--format sarif`) | `engine/cli_formats/sarif.py` | `tests/test_format_sarif.py` |
| F2.2 | Assinatura Ed25519 (3 modos) | `engine/bundle/signer.py` + `engine/cli.py::verify` | `tests/test_signer.py` |
| F2.3 | Upload de artefatos na Action | `.github/workflows/consumer-example.yml` | 📄 |
| F2.4 | Cobertura de testes ≥ 70% | `pyproject.toml [tool.pytest]` + `tests/` | `pytest --cov` |
| F2.5 | CONTRIBUTING.md + CODEOWNERS | `CONTRIBUTING.md` + `.github/CODEOWNERS` | 📄 |
| F2.6 | Docs analyzers | `docs/analyzers.md` | 📄 |
| F2.7 | README v2 quickstart visual | `README.md` | 📄 |

## Adendo Técnico (A1–A10)

| Item | Descrição | Implementação | Testes |
|------|-----------|---------------|--------|
| A1 | Beta ≠ GA | `docs/beta-vs-ga.md` | 📄 |
| A2 | Reprodutibilidade ≠ bundle idêntico | `engine/bundle/fingerprint.py` | `tests/test_fingerprint.py` |
| A3 | Provenance incompleto ≠ fail universal | `analyzers/provenance.py` (status: valid/gap/invalid/not_provided) | `tests/test_analyzer_provenance.py` |
| A4 | Phase analyzer contextual | `analyzers/phase.py` (sem `reliability: high` hardcoded) | `tests/test_analyzer_phase.py` |
| A5 | Inspect com níveis de custo | `engine/cli.py::inspect` (`--analysis header/basic/full`) | `tests/test_cli_inspect.py` |
| A6 | Assinatura com verify + key_id | `engine/bundle/signer.py::verify_bundle` + `engine/cli.py::verify` | `tests/test_signer.py` |
| A7 | CI alinhado ao backend do projeto | `.github/workflows/ci.yml` (sem poetry, usa `pip install -e .[dev]`) | 📄 |
| A8 | Docker e Action distintos | `Dockerfile` + `integrations/github-action/action.yml` (composite action) | 📄 |
| A9 | SARIF não promete comentários automáticos | `docs/sarif-integration.md` | 📄 |
| A10 | Fixtures como supply chain | `fixtures/<hash>/` + `expected.json` com hash do áudio | `tests/test_fixtures_integrity.py` |

## Adendo Estratégico (S1–S6)

| Item | Descrição | Implementação | Testes |
|------|-----------|---------------|--------|
| S1 | Versionamento semântico do bundle | `engine/bundle/schema_version.py` + `contracts/registry.json` | `tests/test_schema_version.py` |
| S2 | Imutabilidade de fixtures | `fixtures/<sha256_short>/` com `expected.json` versionado | `tests/test_fixtures_integrity.py` |
| S3 | Fallback decoder | `engine/normalization.py::decode_pcm_canonical` (fallback audioread/soundfile) | `tests/test_normalization_fallback.py` |
| S4 | Limitations como metadado obrigatório | `engine/bundle/limitations.py` (lista fixa, auto-preenchida) | `tests/test_limitations.py` |
| S5 | Gerenciamento de chaves CI | `engine/bundle/signer.py::generate_key` + `audio-suite key generate` CLI | `tests/test_signer.py` |
| S6 | Tipagem estrita + Python 3.12+ | `pyproject.toml [tool.mypy] strict=true`, `typing.Protocol` para analyzers | CI mypy |

## Adendo Operacional (O1–O10)

| Item | Descrição | Implementação | Testes |
|------|-----------|---------------|--------|
| O1 | TOCTOU protection | `engine/execution.py::run_validation` (hash antes + depois) | `tests/test_toctou.py` |
| O2 | Timeout por analyzer | `engine/execution.py` (`concurrent.futures` + timeout por analyzer) | `tests/test_analyzer_timeout.py` |
| O3 | Validar bundle contra schema | `engine/evidence.py::save_bundle` (valida via `jsonschema`) | `tests/test_evidence_schema.py` |
| O4 | Escrita atômica | `engine/evidence.py::save_bundle` (tmp + os.replace + fsync) | `tests/test_atomic_write.py` |
| O5 | Determinismo float (epsilon) | `engine/bundle/fingerprint.py::quantize_findings` | `tests/test_fingerprint.py` |
| O6 | Profile versioning + lockfile | `registry/profiles.lock.yaml` + `engine/policy.py::load_policy_profile` | `tests/test_policy_lockfile.py` |
| O7 | Schema URN resolvível | `contracts/registry.json` (URN → path + sha256) | `tests/test_schema_registry.py` |
| O8 | Entradas degeneradas | `engine/normalization.py::decode_pcm_canonical` (NaN/Inf/0 amostras → indeterminate) | `tests/test_degenerate_inputs.py` |
| O9 | Redação de PII | `engine/discovery.py::redact_pii_in_findings` | `tests/test_pii_redaction.py` |
| O10 | Truncagem de findings | `engine/bundle/truncate.py` (máx N/analyzer, agregação) | `tests/test_truncation.py` |

## Sumário de Cobertura

| Módulo | Arquivo | Teste |
|--------|---------|-------|
| CLI inspect | `engine/cli.py` | `tests/test_cli_inspect.py` |
| CLI validate | `engine/cli.py` | `tests/test_cli_validate.py` |
| CLI verify | `engine/cli.py` | `tests/test_cli_verify.py` |
| CLI key | `engine/cli.py` | `tests/test_cli_key.py` |
| Discovery | `engine/discovery.py` | `tests/test_discovery.py` |
| Normalization | `engine/normalization.py` | `tests/test_normalization.py` |
| Policy | `engine/policy.py` | `tests/test_policy.py` |
| Execution | `engine/execution.py` | `tests/test_execution.py` |
| Evidence | `engine/evidence.py` | `tests/test_evidence.py` |
| Bundle Fingerprint | `engine/bundle/fingerprint.py` | `tests/test_fingerprint.py` |
| Bundle Signer | `engine/bundle/signer.py` | `tests/test_signer.py` |
| Bundle Limitations | `engine/bundle/limitations.py` | `tests/test_limitations.py` |
| Bundle Truncate | `engine/bundle/truncate.py` | `tests/test_truncation.py` |
| Schema Version | `engine/bundle/schema_version.py` | `tests/test_schema_version.py` |
| SARIF Format | `engine/cli_formats/sarif.py` | `tests/test_format_sarif.py` |
| Analyzer: loudness | `analyzers/loudness.py` | `tests/test_analyzer_loudness.py` |
| Analyzer: signal | `analyzers/signal.py` | `tests/test_analyzer_signal.py` |
| Analyzer: phase | `analyzers/phase.py` | `tests/test_analyzer_phase.py` |
| Analyzer: metadata | `analyzers/metadata.py` | `tests/test_analyzer_metadata.py` |
| Analyzer: provenance | `analyzers/provenance.py` | `tests/test_analyzer_provenance.py` |
| Analyzer: rights_manifest | `analyzers/rights_manifest.py` | `tests/test_rights_manifest.py` |
| Fixtures integrity | `fixtures/*/expected.json` | `tests/test_fixtures_integrity.py` |
| End-to-end | todo o pipeline | `tests/test_e2e.py` |

**Meta de cobertura:** ≥ 70% por módulo, ≥ 75% global.
