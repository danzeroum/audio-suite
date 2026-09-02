# Prompt para Agente de IA — Implementação do Plano Consolidado

## Contexto

Você é um agente de desenvolvimento autônomo encarregado de implementar o **Plano Consolidado de Desenvolvimento** do projeto `audio-suite`, um CLI Python para análise acústica com governança forense.

O plano completo está em `docs/desenvolvimento/plano-consolidado.md`. Leia-o **integralmente** antes de começar.

## Repositório

- **GitHub:** `danzeroum/audio-suite`
- **Branch padrão:** `main`
- **Token de acesso:** será fornecido separadamente (variável de ambiente `GH_TOKEN`)
- **Python:** 3.12 (venv em `/home/z/.venv/bin/python3`)
- **Dependências já instaladas:** numpy, scipy, soundfile, PyYAML, jsonschema, pynacl, hypothesis, pytest, pytest-cov, ruff

## Regras Invioláveis (NUNCA quebre)

1. **R1:** Descritores subjetivos (centroid, LRA, timbre, etc.) **nunca** causam `FAIL`. Status deve ser `PASS` ou `NOT_APPLICABLE`.
2. **R2:** Sem referência declarada → métricas full-reference retornam `INDETERMINATE`. Nunca chame um fallback no-reference de "ViSQOL/STOI/SI-SDR".
3. **R4:** ML pesado (deepfake, ENF) é **opt-in** — exige `enabled: true` + `model_name` no profile.
4. **R8:** Nunca concluir autenticidade. `enf_phase` e `deepfake` retornam **sempre** `NEEDS_REVIEW`, mesmo sem achados. Mensagens não podem conter "is authentic" ou "is deepfake".
5. **Contrato de 6 status:** `PASS / WARNING / FAIL / NEEDS_REVIEW / NOT_APPLICABLE / INDETERMINATE / ERROR`. Não adicionar novos.
6. **Exit codes fixos:** `0=OK · 1=FINDING · 2=INVALID_PROFILE · 3=INVALID_INPUT · 64=USAGE`.

## Workflow de Execução

Para **cada item** do backlog (ex: GOV-01, CONTR-01, CONF-02...):

### Passo 1 — Preparação
```bash
cd /home/z/my-project
git checkout main
git pull origin main
git checkout -b feat/<onda>-<categoria>-<id>  # ex: feat/onda0-gov-gov01
```

### Passo 2 — Implementação
- Escreva o código seguindo o estilo existente (ruff format)
- Siga os padrões do código atual (dataclasses frozen, type hints, docstrings)
- Consulte `docs/desenvolvimento/plano-consolidado.md` para detalhes de cada item

### Passo 3 — Testes
- Escreva os testes especificados na seção "Testes" de cada categoria
- Rode localmente:
```bash
/home/z/.venv/bin/python3 scripts/gen_fixtures.py  # regenera fixtures se necessário
/home/z/.venv/bin/python3 -m pytest tests/ -q --tb=short
/home/z/.venv/bin/python3 -m ruff check audio_suite tests
/home/z/.venv/bin/python3 -m ruff format --check audio_suite tests
```
- **Todos os testes devem passar** antes de commitar

### Passo 4 — Commit
```bash
git add -A
git commit -m "feat(<categoria>-<id>): <descrição curta>

<descrição detalhada do que foi implementado>

Refs: <ID do item no plano> (docs/desenvolvimento/plano-consolidado.md)"
```

### Passo 5 — Push e PR
```bash
git push -u origin feat/<onda>-<categoria>-<id>
```
Criar PR via API:
```bash
curl -s -X POST \
    -H "Authorization: Bearer $GH_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -d '{"title":"feat(<id>): <desc>","head":"feat/<onda>-<categoria>-<id>","base":"main","body":"<descrição>"}' \
    https://api.github.com/repos/danzeroum/audio-suite/pulls
```

### Passo 6 — Monitorar CI
```bash
# Poll até CI completar (verificar a cada 30s, timeout 10min)
SHA=$(git rev-parse HEAD)
# ... curl check-runs ...
```
- Se CI falhar, **leia os logs**, corrija, faça novo commit e push
- Se CI passar, aguarde o merge manual do usuário

### Passo 7 — Após merge do usuário
```bash
git checkout main
git pull origin main
# Avançar para o próximo item
```

## Ordem de Execução (Ondas)

Execute **estritamente nesta ordem**. Não pule itens. Não misture ondas.

### ONDA 0 — Higiene (1–2 dias)
1. **GOV-01:** Adicionar `LICENSE` (MIT)
2. **GOV-02:** Remover `.env` versionado; garantir `.gitignore`
3. **GOV-03:** Remover `download/` de rascunho
4. **GOV-04:** Restaurar `CONTRIBUTING.md`, `CODEOWNERS`, `docs/`
5. **GOV-05:** Documentar branch protection (não configura via API — criar `docs/governance/branch-protection.md`)
6. **GOV-06:** Criar `CHANGELOG.md` + política semver em `docs/governance/versioning.md`
7. **DIST-01:** Criar tag `v0.2.0` + GitHub Release com artefatos
8. **DIST-02:** Preparar publish no PyPI (criar `docs/governance/publishing.md` com steps; não publicar de fato sem credenciais)
9. **TEST-10:** Remover `|| true` do mypy no CI; tornar mypy bloqueante (corrigir erros existentes incrementalmente); gate cobertura mantém 70% nesta onda

**Critério de conclusão da Onda 0:**
- `tests/architecture/test_repo_hygiene.py` passa
- `tests/architecture/test_analyzer_registry.py` passa (regressão dos 4 imports)
- `tests/architecture/test_ci_config.py` passa
- `pip install -e .` funciona em venv limpo
- CI verde com mypy bloqueante
- Tag `v0.2.0` criada

### ONDA 1 — Confiança no Núcleo (2 semanas)
1. **CONTR-01:** JSON Schema v1 (`schemas/bundle-v1.json`) + validação em todos os outputs
2. **CONTR-02:** IDs de regras estáveis (`AS-LOUD-001` etc.) — mapear cada analyzer
3. **CONTR-03:** Taxonomia severidade + mapeamento exit codes
4. **CORP-01:** Corpus versionado por categorias (estender `scripts/gen_fixtures.py`)
5. **CORP-02:** Manifest YAML por fixture com sha256
6. **CORP-03:** 40–60 fixtures cobrindo principais analyzers
7. **ENG-01:** Timeout por analyzer (configurável, default 60s; analyzer em timeout → `ERROR`)
8. **TEST-01:** Preencher `tests/e2e/`, `tests/fuzz/` (esqueletos), `tests/performance/` (esqueletos)
9. **TEST-02:** E2E completo (CLI → JSON/HTML/SARIF → exit codes; bundle assinado → verify; Docker; Action)
10. **TEST-11:** Teste de arquitetura (arquivos esperados presentes)

### ONDA 2 — Conformidade (2 semanas)
1. **CONF-01:** BS.1770-5 (manter golden vectors do −4)
2. **CONF-02:** Suite conformance EBU Tech 3341/3342
3. **CONF-03:** Matriz validação cruzada + tabela de desvios no README
4. **CONF-04:** Job CI `conformance` com relatório assinável
5. **CONF-05:** Golden vectors versionados
6. **PROF-01:** Perfil `broadcast` (R128)
7. **PROF-02:** Perfis `streaming-music` e `broadcast-streaming`
8. **PROF-03:** Perfil `podcast`
9. **PROF-07:** Comando `audio-suite compliance --target`
10. **TEST-05:** Benchmarks com pytest-benchmark + gate
11. **TEST-09:** CI em 3 camadas (PR / main / noturno)
12. **Gate cobertura ≥80%**

### ONDA 3 — Robustez (2 semanas)
1. **TEST-03:** Fuzz do decoder
2. **TEST-04:** Fuzz de profiles YAML
3. **TEST-06:** Mutation testing (noturno)
4. **TEST-07:** Determinismo OS × Python
5. **TEST-08:** WCAG check com axe-core
6. **TEST-12:** ruff strict, bandit, pip-audit, mypy strict nos críticos
7. **CORP-04:** Golden-file regression por analyzer
8. **CORP-05:** Testes metamórficos
9. **CORP-06:** Property tests ampliados
10. **ENG-02:** Streaming para arquivos grandes
11. **ENG-07:** Ampliar formatos (validar matriz FLAC/OGG/MP3/AAC-MP4)

### ONDA 4 — Produto Acionável (2 semanas)
1. **CONTR-04:** Campos de remediação
2. **CONTR-05:** Campos de incerteza
3. **CONTR-06:** Fraseamento probabilístico obrigatório
4. **CONTR-07:** Scorecard agregado
5. **EVID-01:** Comando de pacote de evidência
6. **EVID-02:** Expandir bundle
7. **EVID-04:** Fixtures e testes de PII
8. **ENG-03:** Batch/glob + watch-folder
9. **ENG-04:** Saída JSON Lines
10. **ENG-06:** API de plugins formalizada
11. **ENG-08:** Metadados BWF/BEXT/iXML
12. **ENG-10:** HTML com timeline + goniometer
13. **DOCS-01:** Site mkdocs-material
14. **DOCS-02:** Garantias por analyzer
15. **DIST-03:** SBOM + provenance SLSA
16. **GOV-07:** Restaurar `consumer-example.yml`
17. **GOV-08:** Badges no README
18. **GOV-09:** Posicionamento README
19. **GOV-10:** Teste de regressão do registry

### ONDA 5 — Autoridade (contínuo)
1. **CONF-06:** Benchmark ASVspoof
2. **CONF-07:** STOI/ESTOI real via pystoi
3. **CONF-08:** Fingerprint Chromaprint
4. **CONF-09:** ViSQOL v3
5. **PROF-04:** ATSC A/85
6. **PROF-05:** Cine (R128 s4)
7. **PROF-06:** Perfis voice-ai, music-master, forensic-triage, call-center
8. **ENG-09:** P.56 active speech level
9. **ENG-11:** Cartridges ASVspoof
10. **DOCS-03:** Arquitetura, modelo de ameaça
11. **DOCS-04:** Exemplos CI por segmento
12. **DOCS-05:** Tutoriais por segmento

## Convenções de Código

- **Python:** 3.11+ (target), type hints obrigatórios, `from __future__ import annotations`
- **Style:** ruff (line-length 110), ruff format
- **Dataclasses:** `frozen=True` para modelos imutáveis (PCM, Finding, Bundle, Profile)
- **Testes:** pytest, nomes `test_<ID>_<descrição>.py` (ex: `test_GOV01_license.py`)
- **Commits:** conventional commits (`feat(gov-01): ...`, `fix(eng-01): ...`, `docs(conf-02): ...`)
- **Branches:** `feat/onda<N>-<cat>-<id>` (ex: `feat/onda0-gov-gov01`)

## Convenções de Teste

- **Nomes de arquivo:** `test_<ID>_<descrição>.py` (ex: `test_GOV01_license.py`)
- **Nomes de função:** `test_<ID>_<cenário>` (ex: `test_GOV01_license_exists`)
- **Marcadores:** usar `@pytest.mark.slow` para testes longos, `@pytest.mark.property` para property-based
- **Fixtures:** usar `conftest.py` para fixtures compartilhadas
- **Cobertura:** não regredir; ≥80% a partir da Onda 2

## Tratamento de Falhas de CI

Se o CI falhar:
1. **Leia os logs** do job que falhou (via API ou interface web)
2. **Identifique a causa raiz** (não faça patches cegos)
3. **Corrija localmente** rodando o teste/cobertura/lint que falhou
4. **Commit + push** da correção
5. **Repita** até CI verde

Erros comuns e soluções:
- `ruff check` falha → `ruff check --fix` + `ruff format`
- `mypy` falha → corrigir type hints incrementalmente (não usar `# type: ignore` sem justificativa)
- `pytest` falha → ler traceback, corrigir o teste OU o código
- `pip-audit` falha → atualizar dependência vulnerável
- Docker falha → verificar Dockerfile (USER non-root, paths corretos)

## Decisões de Escopo

**NÃO implemente** (fora de escopo, justificado em `docs/decisions/0001-scope.md`):
- VST3/AU/AAX plugins
- Tempo real / processamento lock-free
- Oversampling em efeitos de áudio
- Pitch-shift / time-stretch
- GUI com undo/redo

Se surgir dúvida sobre escopo, **crie um ADR** (Architecture Decision Record) em `docs/decisions/` e siga.

## Comunicação com o Usuário

- Após concluir cada onda, reporte: itens implementados, testes adicionados, cobertura, PRs mergeados
- Se encontrar bloqueio que exija decisão do usuário (ex: licença de dependência, escolha de padrão), **pare e pergunte**
- Mantenha `worklog.md` atualizado com o progresso

## Início Imediato

Comece pela **Onda 0, item GOV-01** (adicionar LICENSE). Siga a ordem exata. Não avance para a Onda 1 até a Onda 0 estar 100% concluída e mergeada.

Boa sorte. O plano está pronto para execução.
