# Contributing

Obrigado por contribuir com a `audio-suite`! Este documento descreve o fluxo de contribuição.

## Antes de contribuir

1. **Abra uma issue** descrevendo o problema ou proposta antes de enviar PR.
2. Verifique se sua ideia está alinhada com a [`docs/IMPLEMENTATION_MAP.md`](IMPLEMENTATION_MAP.md).
3. Confirme que não introduz ASR/fingerprint no Beta (fora de escopo — veja adendos).

## Fluxo de PR

1. Fork + branch: `feat/<nome>` ou `fix/<nome>`.
2. Implemente + adicione testes.
3. Garanta:
   - `ruff check engine analyzers tests` sem warnings.
   - `pytest tests --cov` com cobertura ≥ 70%.
   - `mypy engine analyzers` sem erros (ou justifique exceções).
4. Atualize `CHANGELOG.md` se aplicável.
5. Abra PR preenchendo o template.

## Convenção de commits

Usamos [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: adiciona analyzer de DC offset`
- `fix: corrige cálculo de true peak para mono`
- `docs: atualiza README com quickstart`
- `refactor: extrai signer para engine/bundle/`
- `test: cobre casos degenerados em normalization`
- `chore: bump cryptography para 42.0.0`

## Labels

- `bug`, `feature`, `enhancement`
- `analyzer`, `engine`, `contracts`, `cli`, `ci`
- `breaking`
- `needs-review`

## Codeowners

Veja [`.github/CODEOWNERS`](../.github/CODEOWNERS). Cada área tem responsável técnico:

- `engine/` — arquitetura e orquestração
- `analyzers/` — medições acústicas
- `contracts/` — schemas e versionamento
- `registry/` — profiles e rights manifest
- `tests/` — cobertura e fixtures
- `.github/` — CI e Actions

## Adição de novo analyzer

1. Crie `analyzers/<nome>.py` com `def run_analyzer(pcm, media_info, params, verbose) -> list[finding]`.
2. NÃO hardcode limites — tudo vem do profile.
3. Declare a função no `engine/execution.py::ANALYZER_PATHS`.
4. Adicione testes em `tests/test_analyzer_<nome>.py`.
5. Documente em [`docs/analyzers.md`](analyzers.md).
6. Adicione um fixture que dispare o analyzer.

## Adição de novo profile

1. Crie `registry/policy-profiles/<nome>_vN.yaml`.
2. **Obrigatório:** sufixo `_vN` (ex.: `_v1`, `_v2`).
3. Rode `python -c "from engine.policy import register_profile_in_lockfile; register_profile_in_lockfile(Path('registry/policy-profiles/<nome>_vN.yaml'))"`.
4. Commit o `registry/profiles.lock.yaml` atualizado.

## Reportar vulnerabilidade

NÃO abra issue pública. Veja [`docs/security.md`](security.md) para canal de disclosure.
