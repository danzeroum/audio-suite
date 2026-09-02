# Plano Consolidado de Desenvolvimento — `audio-suite`

> **Versão:** 1.0 · **Data:** 2026-09-02 · **Status:** Aprovado para execução
>
> **Fontes:** Compilação das análises R1, R2, R4 (R3 descartado por inaplicabilidade — ver BACKLOG-06). Anexos 5/6 não receberam conteúdo e ficam de fora; se reenviados, entram como itens novos.

---

## 1. Princípios Invioláveis (o agente NÃO pode quebrar)

Estas regras são **hard constraints** em toda implementação. Qualquer PR que as viole deve ser rejeitado.

| ID | Regra | Aplicação prática |
|----|-------|-------------------|
| **R1** | Descritores subjetivos **nunca** causam falha automática | `spectral_health`, `lra`, `timbre_distance`, `harmonic_tension`, `spectral_irregularity`, `inharmonicity`, `fatigue_index`, `rhythmic_grid_alignment`, `melodic_contour`, `goniometer` retornam sempre `PASS` ou `NOT_APPLICABLE` |
| **R2** | Sem referência = sem métrica full-reference | `ref_quality`, `stem_sep` retornam `INDETERMINATE` quando não há referência declarada; **nunca** chamar um fallback no-reference de "ViSQOL/STOI/SI-SDR" |
| **R4** | ML pesado é sempre **opt-in** | `deepfake`, `enf_phase` exigem `enabled: true` + `model_name` no profile |
| **R8** | Nunca concluir autenticidade | `enf_phase`, `deepfake` retornam sempre `NEEDS_REVIEW`, mesmo quando não detectam nada. Mensagens não podem conter "is authentic" ou "is deepfake" |
| **C6** | Contrato de 6 status | `PASS / WARNING / FAIL / NEEDS_REVIEW / NOT_APPLICABLE / INDETERMINATE / ERROR` — não adicionar novos |
| **EC** | Exit codes fixos | `0=OK · 1=FINDING · 2=INVALID_PROFILE · 3=INVALID_INPUT · 64=USAGE` |

---

## 2. Conflitos Resolvidos

| Tema | Decisão | Justificativa |
|------|---------|---------------|
| Versão do release | `0.1.0` (pyproject) → `0.2.0` após Onda 0 → semver | pyproject é fonte da verdade; CHANGELOG documenta |
| Alvo streaming | Dois perfis: `streaming-music` (−14 LUFS) e `broadcast-streaming` (R128 s2: −18 interim / −16 música, PLR ≤ 15) | Resolve conflito R1 vs R2/R4 |
| Padrão loudness | Atualizar BS.1770-**4** → BS.1770-**5** (11/2023) | Manter golden vectors do −4 como regressão |
| Gate cobertura | 70% na Onda 0 → **80%** a partir da Onda 2 | Permite velocidade inicial, exige rigor depois |
| Itens R3 (VST3, GUI, tempo real) | **Descartar formalmente** com justificativa em `docs/decisions/0001-scope.md` | CLI de análise, não DAW/plugin |
| `mypy \|\| true` | Remover na Onda 0 — mypy bloqueante | Red flag de qualidade |

---

## 3. Backlog Consolidado por Categoria

### CAT-1 · GOV — Governança e Higiene de Repositório

| ID | Melhoria | Prio |
|----|----------|------|
| GOV-01 | Adicionar `LICENSE` (MIT, alinhado ao pyproject) | P0 |
| GOV-02 | Remover `.env` versionado; garantir `.gitignore` | P0 |
| GOV-03 | Remover `download/` de rascunho | P0 |
| GOV-04 | Restaurar `CONTRIBUTING.md`, `CODEOWNERS`, `docs/` | P0 |
| GOV-05 | Branch protection no main (PRs + checks) | P0 |
| GOV-06 | `CHANGELOG.md` + política semver | P1 |
| GOV-07 | Restaurar workflow `consumer-example.yml` | P1 |
| GOV-08 | Badges no README (CI, cobertura, PyPI, licença) | P1 |
| GOV-09 | Posicionamento README: "evidence-grade audio QC" | P1 |
| GOV-10 | Teste de regressão do `analyzers/__init__.py` (já existe TEST-11) | P1 |

**Testes:** `tests/architecture/test_repo_hygiene.py`, `test_analyzer_registry.py`, `test_ci_config.py`

---

### CAT-2 · DIST — Distribuição e Releases

| ID | Melhoria | Prio |
|----|----------|------|
| DIST-01 | Tag + GitHub Release com wheel/sdist | P0 |
| DIST-02 | Publicar no PyPI; remover `--skip-editable` do pip-audit | P0 |
| DIST-03 | SBOM (CycloneDX) + provenance SLSA + sigstore | P2 |
| DIST-04 | Imagem Docker no ghcr com tag de versão | P2 |
| DIST-05 | Badges/link de conformidade no README | P1 |

**Testes:** `tests/packaging/test_build_install.py`, `tests/e2e/test_consumer_pypi.py`

---

### CAT-3 · CONF — Conformidade Metrológica

| ID | Melhoria | Prio |
|----|----------|------|
| CONF-01 | Loudness BS.1770-**5** (manter golden vectors do −4) | P1 |
| CONF-02 | Suite conformance EBU Tech 3341/3342 (~70 arquivos) ±0,1 LU | P1 |
| CONF-03 | Matriz validação cruzada vs libebur128/pyloudnorm/ffmpeg + tabela de desvios no README | P1 |
| CONF-04 | Job CI `conformance` publicando relatório assinável | P1 |
| CONF-05 | Golden vectors versionados com manifest sha256 | P1 |
| CONF-06 | Benchmark deepfake vs ASVspoof 5 (EER/min-tDCF documentado, `needs_review`) | P2 |
| CONF-07 | STOI/ESTOI real via `pystoi` (feature flag, degradação elegante) | P2 |
| CONF-08 | Fingerprint compatível Chromaprint/AcoustID | P2 |
| CONF-09 | ViSQOL v3 (MOS-LQO 1–5) como analyzer opcional | P3 |

**Testes:** `tests/conformance/test_ebu_loudness.py`, `test_true_peak.py`, `test_lra.py`, `tests/crosscheck/test_oracle_matrix.py`, `tests/benchmarks/deepfake/test_asvspoof_eer.py`, `tests/unit/test_stoi_fallback.py`

---

### CAT-4 · PROF — Perfis de Delivery

| ID | Melhoria | Prio |
|----|----------|------|
| PROF-01 | Perfil `broadcast` — EBU R128: −23 LUFS ±0,5, teto −1 dBTP | P1 |
| PROF-02 | Perfis `streaming-music` (−14) e `broadcast-streaming` (R128 s2) | P1 |
| PROF-03 | Perfil `podcast` (−16 estéreo / −19 mono) | P1 |
| PROF-04 | Perfil `ATSC A/85` (−24 LKFS) | P2 |
| PROF-05 | Perfil `cine` (R128 s4) | P2 |
| PROF-06 | Perfis `voice-ai`, `music-master`, `forensic-triage`, `call-center` | P2 |
| PROF-07 | Comando `audio-suite compliance --target ebu\|spotify\|podcast` | P1 |
| PROF-08 | **Restrição:** descritores nunca viram falha automática em nenhum perfil | Estrutural |

**Testes:** `tests/unit/policy/test_profile_*.py`, `tests/contracts/test_profile_catalog.py`, `tests/integration/test_compliance_command.py`, `tests/golden/test_delivery_matrix.py`, testes metamórficos

---

### CAT-5 · CONTR — Contrato Versionado de Saída

| ID | Melhoria | Prio |
|----|----------|------|
| CONTR-01 | JSON Schema v1 versionado e publicado (URN resolvível) | P0 |
| CONTR-02 | IDs de regras estáveis (`AS-LOUD-001`, `AS-CLIP-001`…) | P0 |
| CONTR-03 | Taxonomia severidade `info/warning/error/critical` + exit codes | P0 |
| CONTR-04 | Campos de remediação: `recommendation`, `why_it_matters`, `autofix.available` | P1 |
| CONTR-05 | Campos de incerteza: `confidence`, `evidence_strength`, `method_version`, `calibration_status`, `requires_human_review` | P1 |
| CONTR-06 | Fraseamento probabilístico obrigatório em classificadores | P1 |
| CONTR-07 | Scorecard agregado opcional | P2 |

**Testes:** `tests/contracts/test_schema_v1.py`, `test_rule_ids.py`, `test_severity_exit_codes.py`, `test_remediation_fields.py`, `test_uncertainty_fields.py`, `tests/property/test_no_authenticity_claim.py`, `test_schema_backcompat.py`

---

### CAT-6 · ENG — Engine, Formatos e Plugins

| ID | Melhoria | Prio |
|----|----------|------|
| ENG-01 | **Timeout por analyzer** (analyzer travado → ERROR, não hang) | P0 |
| ENG-02 | Streaming/blocos para arquivos grandes | P1 |
| ENG-03 | Batch/glob + watch-folder | P2 |
| ENG-04 | Saída JSON Lines | P2 |
| ENG-05 | API Python estável documentada | P2 |
| ENG-06 | API de plugins/cartridge formalizada | P2 |
| ENG-07 | Ampliar formatos (FLAC/OGG/MP3/AAC-MP4) — validar matriz | P1 |
| ENG-08 | Metadados BWF/BEXT/iXML | P2 |
| ENG-09 | P.56 active speech level | P3 |
| ENG-10 | HTML com timeline de loudness + goniometer plot (WCAG) | P2 |
| ENG-11 | Cartridges ASVspoof externos (opt-in) | P3 |

**Testes:** `tests/unit/engine/test_timeout.py`, `test_isolation.py`, `tests/integration/formats/test_matrix.py`, `tests/performance/test_large_file_streaming.py`, `tests/unit/cli/test_batch_watch.py`, `tests/unit/output/test_jsonl.py`, `tests/contracts/test_plugin_api.py`, `tests/unit/metadata/test_bwf_bext.py`, `tests/integration/test_html_report.py`

---

### CAT-7 · CORP — Corpus de Referência

| ID | Melhoria | Prio |
|----|----------|------|
| CORP-01 | Corpus versionado por categorias (sintéticos, defeitos, voz, canais, contêineres, PII, evidência) | P0 |
| CORP-02 | Manifest YAML por fixture com sha256 | P0 |
| CORP-03 | 40–60 fixtures cobrindo principais analyzers | P0 |
| CORP-04 | Golden-file regression por analyzer | P1 |
| CORP-05 | Testes metamórficos | P1 |
| CORP-06 | Property tests (hypothesis) ampliados | P1 |

**Testes:** `tests/golden/test_<analyzer>_golden.py`, `tests/metamorphic/test_time_duplication.py`, `test_channel_swap.py`, `test_gain_6db.py`, `test_stereo_mono.py`, `test_silence_padding.py`, `test_lossy_roundtrip.py`, `tests/property/`

---

### CAT-8 · TEST — Camadas de Teste e Gates de CI

| ID | Melhoria | Prio |
|----|----------|------|
| TEST-01 | Preencher esqueletos vazios (`tests/e2e`, `tests/fuzz`, `tests/performance`) | P0 |
| TEST-02 | E2E: CLI → JSON/HTML/SARIF → exit codes; bundle assinado; Docker; Action | P0 |
| TEST-03 | Fuzz do decoder (truncado, malformado, NaN/Inf, zip bombs) | P1 |
| TEST-04 | Fuzz de profiles YAML (hypothesis) | P1 |
| TEST-05 | Benchmarks com orçamento (pytest-benchmark) + gate de regressão | P1 |
| TEST-06 | Mutation testing (mutmut) — noturno | P2 |
| TEST-07 | Determinismo em matriz OS × Python | P2 |
| TEST-08 | WCAG check com axe-core no CI | P2 |
| TEST-09 | CI em 3 camadas (PR / main / noturno) | P1 |
| TEST-10 | mypy bloqueante; gate cobertura ≥80% (Onda 2+); pip-audit sem `--skip-editable` | P0 |
| TEST-11 | Teste de arquitetura (arquivos esperados presentes) | P1 |
| TEST-12 | ruff strict, bandit, pip-audit, mypy strict nos módulos críticos | P1 |

**Arquivos:** `tests/e2e/test_cli_end_to_end.py`, `test_evidence_flow.py`, `test_docker_run.py`, `tests/fuzz/test_decode_fuzz.py`, `test_policy_fuzz.py`, `tests/performance/test_budgets.py`, `tests/architecture/test_expected_files.py`, `.github/workflows/ci.yml`, `ci-main.yml`, `nightly.yml`

---

### CAT-9 · EVID — Evidência, Forense e Reprodutibilidade

| ID | Melhoria | Prio |
|----|----------|------|
| EVID-01 | Comando de pacote de evidência verificável (`--bundle evidence.asb --sign-key key.pem`) | P1 |
| EVID-02 | Expandir bundle: hash original, versão motor, ambiente, perfil, parâmetros, timestamps, logs | P1 |
| EVID-03 | Métrica de reprodutibilidade por release | P2 |
| EVID-04 | Fixtures e testes de PII em metadados | P1 |
| EVID-05 | JSON Schema do bundle como URN resolvível | P2 |

**Testes:** `tests/integration/evidence/test_full_chain.py`, `tests/unit/security/test_signature_determinism.py`, `test_audit_hashchain.py`, `tests/property/test_bundle_reproducibility.py`, `tests/security/test_pii_redaction.py`

---

### CAT-10 · DOCS — Documentação

| ID | Melhoria | Prio |
|----|----------|------|
| DOCS-01 | Site mkdocs-material + API Sphinx + JSON Schemas como URN | P1 |
| DOCS-02 | Garantias e limitações por analyzer | P1 |
| DOCS-03 | Arquitetura, modelo de ameaça, política de versões | P2 |
| DOCS-04 | Exemplos CI: podcast, transcodificação, TTS, evidência | P2 |
| DOCS-05 | Tutoriais por segmento | P3 |

**Testes:** `tests/docs/test_analyzer_docs.py`, link checker, `test_readme_examples.py`

---

### CAT-11 · BACKLOG — Agendado / Descartado

| ID | Item | Status |
|----|------|--------|
| BACKLOG-01 | ViSQOL v3 full-reference | Agendado (pós CONF-07) |
| BACKLOG-02 | ADM/BWF completo, Atmos | Agendado (pós ENG-08) |
| BACKLOG-03 | Dashboard/SaaS | Reavaliar pós-Onda 4 |
| BACKLOG-04 | Benchmark público comparativo | Após CONF-02/03 |
| BACKLOG-05 | Repositório de perfis assinados da comunidade | Após ENG-06 |
| BACKLOG-06 | **Descartar:** VST3/AU/AAX, tempo real/lock-free, oversampling em efeitos, pitch-shift/time-stretch, GUI undo/redo | Descartado — justificar em `docs/decisions/0001-scope.md` |

---

## 4. Plano de Execução em Ondas

### Onda 0 — Higiene (1–2 dias)
**Escopo:** GOV-01…06, DIST-01/02, TEST-10
**Critério de done:** Testes de arquitetura/higiene verdes; `pip install` funcional; mypy bloqueante; LICENSE presente; CHANGELOG criado; tag v0.2.0.

### Onda 1 — Confiança no Núcleo (2 semanas)
**Escopo:** CONTR-01…03, CORP-01…03, ENG-01, TEST-01/02/11
**Critério de done:** JSON Schema v1 publicado; 40–60 fixtures com manifests; E2E CLI/Docker/Action; timeout por analyzer implementado.

### Onda 2 — Conformidade (2 semanas)
**Escopo:** CONF-01…05, PROF-01…03/07, TEST-05/09, gate cobertura ≥80%
**Critério de done:** BS.1770-5; tabela de desvios no README; relatório de conformidade assinado no CI; perfis broadcast/streaming/podcast.

### Onda 3 — Robustez (2 semanas)
**Escopo:** TEST-03/04/06/07/08/12, CORP-04…06, ENG-02/07
**Critério de done:** Fuzz noturno rodando; benchmarks com gate; metamórficos verdes; streaming para arquivos grandes.

### Onda 4 — Produto Acionável (2 semanas)
**Escopo:** CONTR-04…07, EVID-01…04, ENG-03/04/06/08/10, DOCS-01/02, DIST-03, GOV-07…10
**Critério de done:** Remediação + incerteza nos findings; bundle verificável E2E; plugin API; docs site; SBOM nos releases.

### Onda 5 — Autoridade (contínuo)
**Escopo:** CONF-06…09, PROF-04…06, ENG-09/11, DOCS-03…05, BACKLOG
**Critério de done:** Benchmark ASVspoof documentado; exemplos de CI por segmento; ViSQOL v3; ADM/Atmos.

---

## 5. Definição Global de "Done" (aplica a TODOS os itens)

Para um item ser marcado como concluído, **todos** os critérios abaixo devem ser satisfeitos:

1. ✅ Implementado e funcionando
2. ✅ Bateria de testes da sua categoria passando
3. ✅ CI verde (todos os jobs)
4. ✅ Cobertura não regrediu (e ≥80% a partir da Onda 2)
5. ✅ Nenhuma Regra Inviolável (R1/R2/R4/R8) violada
6. ✅ Contrato de saída retrocompatível (schema N+1 valida output da versão N)
7. ✅ CHANGELOG atualizado
8. ✅ Documentação atualizada (se aplicável)

---

## 6. Métricas de Maturidade por Release

| Métrica | Como medir | Alvo |
|---------|------------|------|
| Taxa de aprovação no corpus golden | `% de fixtures com resultado esperado dentro da tolerância` | ≥ 95% |
| Regressões capturadas pré-release | `nº de bugs encontrados por testes antes do merge` | Crescente |
| Cobertura por módulo crítico | `codecov por diretório` | ≥ 80% (engine, policy, bundle, security) |
| Precisão/recall dos classificatórios | `F1 no corpus anotado` | F1 ≥ 0.85 (defeitos objetivos) |
| s de áudio / s de CPU | `pytest-benchmark` | loudness ≥ 50× realtime |
| Memória de pico | `pytest-benchmark --mem` | < 500 MB para 60 min de áudio |
| % de bundles verificáveis | `bundles com assinatura válida / total` | 100% (quando `--sign`) |
| % de findings com remediação | `findings com recommendation / total de warning+error+critical` | ≥ 80% |
| Breaking changes de schema | `diff de schema entre releases` | 0 (apenas aditivo) |

---

## 7. Estrutura de Diretórios de Teste (alvo final)

```
tests/
├── architecture/        # TEST-11, GOV-10 — invariantes estruturais
├── contracts/           # CONTR-01..07 — schema, IDs, severidade
├── conformance/         # CONF-02/05 — EBU test set, golden vectors
├── crosscheck/          # CONF-03 — matriz vs libebur128/pyloudnorm/ffmpeg
├── docs/                # DOCS-02 — garantias por analyzer
├── e2e/                 # TEST-02 — CLI, bundle, Docker, Action
├── fuzz/                # TEST-03/04 — decoder, profiles
├── golden/              # CORP-04 — regression por analyzer
├── integration/         # fluxos completos, formatos
├── metamorphic/         # CORP-05 — relações entre transformações
├── packaging/           # DIST-01/02 — build, install
├── performance/         # TEST-05 — benchmarks com orçamento
├── property/            # CORP-06 — hypothesis invariâncias
├── security/            # EVID-04 — PII, tamper, audit
└── unit/                # testes isolados por analyzer/módulo
```

---

## 8. Política de Versionamento

- **SemVer estrito:** `MAJOR.MINOR.PATCH`
- **0.x.x:** qualquer mudança pode quebrar (fase de desenvolvimento)
- **1.0.0:** após Onda 4 (contrato estável, API documentada, conformidade publicada)
- **CHANGELOG.md** atualizado em todo PR que afeta comportamento
- **Tags:** `v0.2.0`, `v0.3.0`... com GitHub Release + artefatos

---

## 9. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Corpus EBU não disponível publicamente | Média | Alto | Usar subset + gerar sintéticos calibrados; documentar limitação |
| ViSQOL oficial tem licença restritiva | Alta | Médio | Implementar proxy documentado; deixar hook para integração futura |
| mypy estrito revela muitos erros | Alta | Baixo | Corrigir incrementalmente; não bloquear Onda 0 |
| Fuzz encontra crashes no decoder | Média | Médio | Transformar em testes de regressão (TEST-03) |
| Conflito de merges em `__init__.py` | Alta (recorrente) | Baixo | Implementar auto-descoberta via `pkgutil` (pós-Onda 1) |

---

**Fim do plano.** Próximo passo: executar Onda 0 imediatamente.
