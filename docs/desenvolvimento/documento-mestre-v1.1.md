# DOCUMENTO MESTRE — audio-suite v1.1
## Especificação de Melhorias, Backlog Consolidado e Plano de Execução

> **Versão:** 1.1 · **Status:** Aprovado para implementação · **Escopo:** consolidação validada de 6 análises externas (R1–R4, R7, R8, R9, R10, R11) contra o backlog interno
>
> **Instrução inicial ao agente:** antes de qualquer implementação, audite o estado atual do repositório contra este documento — os itens podem estar parcialmente implementados. Marque o status de cada ID (`pendente` / `em andamento` / `concluído`) como primeira atividade.

---

# PARTE I — CONTEXTO E REGRAS

## 1. Identidade do projeto

**audio-suite** (`github.com/danzeroum/audio-suite`, branch `main`) é uma CLI Python de análise acústica objetiva para QC de áudio *evidence-grade* — broadcast, MAM/DAM, perícia, pipelines de IA de voz.

| Camada | Estado atual |
|---|---|
| Analyzers | **35 registrados** — cada um com contrato `ID/NAME/VERSION/METHOD/DEFAULT_LIMITATIONS` |
| Motor | `engine.py`, `policy.py`, `cartridge.py` |
| Evidência | `bundle.py`, `security/`, `audit.py` (hash-chain + self-check) |
| Outputs | JSON, SARIF 2.1.0, HTML (WCAG), CSV |
| Testes | ~304 passando, cobertura 86%, 38 fixtures determinísticas |
| Dependências runtime | **numpy ≥ 1.26 — única. Ativo de adoção, não destruir** |

## 2. Regras invioláveis

| Regra | Enunciado |
|---|---|
| **R1** | Descritores subjetivos nunca causam falha automática — apenas `observation`/`needs_review` |
| **R2** | Sem referência, sem métrica full-reference — proxies são explícitos |
| **R4** | ML sempre opt-in — nada de modelo bundled no core |
| **R8** | Nunca concluir autenticidade — deepfake/ENF terminam sempre em `needs_review` |

**Contrato estrutural:** 6 status (`PASS/WARNING/FAIL/NEEDS_REVIEW/NOT_APPLICABLE/INDETERMINATE`) + exit codes (`0/1/2/3/64`).

## 3. Política de dependências

- **Runtime core:** apenas numpy. Outras libs → extra opcional, cartridge, ou geração offline de fixtures.
- Se houver caminho numpy puro, é obrigatório.

---

# PARTE II — BACKLOG MESTRE (14 categorias, ~113 IDs)

## CAT-1 · GOV — Governança
- GOV-01: LICENSE (MIT) — P0
- GOV-02: Remover .env versionado + .gitignore — P0
- GOV-03: Remover download/ — P0
- GOV-04: CONTRIBUTING, CODEOWNERS, SECURITY.md, CODE_OF_CONDUCT — P0
- GOV-05: Branch protection — P0
- GOV-06: CHANGELOG + semver — P1
- GOV-07: consumer-example.yml — P1
- GOV-08: Badges README — P1
- GOV-09: Posicionamento README — P1
- GOV-10: Proteção registry — P1

## CAT-2 · DIST — Distribuição
- DIST-01: Tag v0.1.0 + Release — P0
- DIST-02: PyPI — P0
- DIST-03: SBOM + SLSA + sigstore — P2
- DIST-04: Docker ghcr — P2
- DIST-05: Badge conformidade — P1

## CAT-3 · CONF — Conformidade metrológica
- CONF-01: BS.1770-5 — P1
- CONF-02: EBU test set ±0,1 LU — P1
- CONF-03: Matriz validação cruzada — P1
- CONF-04: Job CI conformance assinável — P1
- CONF-05: Golden vectors versionados — P1
- CONF-06: Benchmark ASVspoof — P2
- CONF-07: STOI/PESQ via extras — P2
- CONF-08: Chromaprint — P2
- CONF-09: ViSQOL v3 — P3

## CAT-4 · PROF — Perfis de delivery
- PROF-01: broadcast (R128) — P1
- PROF-02: streaming-music + broadcast-streaming — P1
- PROF-03: podcast — P1
- PROF-04: ATSC A/85 — P2
- PROF-05: cine — P2
- PROF-06: voice-ai, music-master, forensic-triage, call-center — P2
- PROF-07: compliance command — P1
- PROF-08: Descritores nunca fail — estrutural
- PROF-09: Gates de saneamento — P1
- PROF-10: Regras compostas com guardas — P2
- PROF-11: Validador estrutural de policy — P4 (Onda 4)

## CAT-5 · CONTR — Contrato versionado
- CONTR-01: JSON Schema v1 — P0
- CONTR-02: Rule IDs estáveis — P0
- CONTR-03: Severidade + exit codes — P0
- CONTR-04: Campos de remediação — P1
- CONTR-05: Campos de incerteza — P1
- CONTR-06: Fraseamento probabilístico — P1
- CONTR-07: Scorecard — P2
- CONTR-08: Anti-falha-silenciosa — P1
- CONTR-09: delta_to_threshold + near_limit — P4 (Onda 4)

## CAT-6 · ENG — Engine, formatos, API
- ENG-01: Timeout por analyzer — P0
- ENG-01.r: Attack-time profile — P2
- ENG-02: Streaming para arquivos grandes — P1
- ENG-03: Batch/glob + watch-folder — P2
- ENG-04: JSON Lines — P2
- ENG-05: API Python estável — P2
- ENG-06: API de plugins formalizada — P2
- ENG-07: Ampliar formatos — P1
- ENG-08: BWF/BEXT/iXML — P2
- ENG-09: P.56 + silence detector — P3
- ENG-10: HTML com timeline + goniometer — P2
- ENG-11: Cartridges ASVspoof — P3
- ENG-11.r: DNSMOS/NISQA — P3
- ENG-12: DRn meter (numpy puro) — P2

## CAT-7 · CORP — Corpus de referência
- CORP-01: Corpus por categorias — P0
- CORP-02: Manifest YAML por fixture — P0
- CORP-03: 40–60 fixtures — P0
- CORP-04: Golden-file regression — P1
- CORP-05: Testes metamórficos — P1
- CORP-05.r: Extensão metamórfica — P1
- CORP-06: Property tests — P1
- CORP-07: Calibração fingerprint — P3

## CAT-8 · TEST — Camadas de teste
- TEST-01: Preencher esqueletos — P0
- TEST-02: E2E — P0
- TEST-03: Fuzz decoder — P1
- TEST-04: Fuzz profiles YAML — P1
- TEST-05: Benchmarks com orçamento — P1
- TEST-06: Mutation testing — P2
- TEST-07: Determinismo — P2
- TEST-08: WCAG check — P2
- TEST-09: CI 3 camadas — P1
- TEST-10: mypy bloqueante + cobertura 80% — P0
- TEST-11: Teste de arquitetura — P1
- TEST-12: Sanitizers Python — P1

## CAT-9 · EVID — Evidência e reprodutibilidade
- EVID-01: Comando pacote evidência — P1
- EVID-02: Bundle expandido — P1
- EVID-02.r: Provenance — P2
- EVID-03: Métrica reprodutibilidade — P2
- EVID-04: Fixtures PII — P1
- EVID-05: JSON Schema URN — P2
- EVID-06: Pipeline provenance manifest — P5 (Onda 5)

## CAT-10 · DOCS — Documentação
- DOCS-01: MkDocs Material + catálogo analyzers — P1
- DOCS-02: Garantias e limitações por analyzer — P1
- DOCS-03: Arquitetura, modelo de ameaça — P2
- DOCS-04: Exemplos CI — P2
- DOCS-05: Tutoriais por segmento — P3

## CAT-12 · LIST — Listening Test Harness
- LIST-01: ABX CLI — P2
- LIST-02: Commit/reveal protocol — P2
- LIST-03: Pipeline calibração — P3
- LIST-04: Anonimização — P2

## CAT-13 · CONS — Consistência entre analyzers
- CONS-01: Matriz correlação — P3
- CONS-02: Continuidade temporal — P3

## CAT-14 · AUD — LLM-Auditor (Onda 5, gated)
- AUD-01: Cartridge opt-in + CLI `explain`
- AUD-02: Provenance do relatório
- AUD-03: Citation verification programática
- AUD-04: Output schema fechado (likelihood ordinal)
- AUD-05: Patterns library versionada (match_strength determinístico)
- AUD-06: Guardrails R1/R2/R4/R8
- AUD-07: PII scrubbing
- AUD-08: Cost control
- AUD-09: CI não-bloqueante
- AUD-10: Template canônico de relatório

---

# PARTE III — EXECUÇÃO

## 4. Ondas de implementação

| Onda | Escopo | Critério de done |
|---|---|---|
| **0 — Higiene** | GOV-02→01/03/04/05, TEST-10, GOV-06, DIST-01/02 | Higiene verde; pip install; mypy bloqueante; tag |
| **1 — Confiança** | CONTR-01/02/03, CORP-01/02/03, ENG-01, TEST-01/02/11 | Schema v1; 40-60 fixtures; e2e; timeout |
| **2 — Conformidade** | CONF-01..05, PROF-01/02/03/07/09, TEST-05/09, cobertura 80% | Tabela desvios; relatório assinado; perfis |
| **3 — Robustez** | TEST-03/04/06/07/08/12, CORP-04/05/06, ENG-02/07, CONTR-08 | Fuzz; benchmarks; metamórficos; anti-falha |
| **4 — Produto** | CONTR-04/05/06/07/09, EVID-01/02/02.r/04, ENG-03/04/06/08/10/12, DOCS-01/02, DIST-03, GOV-07..10, PROF-10/11, CORP-05.r, LIST-01/02 | Remediação; bundle e2e; plugins; docs; regras compostas |
| **5 — Autoridade** | CONS-01/02, CORP-05.r/07, LIST-03/04, ENG-09/11, PROF-04/05/06, DOCS-03/04/05, CONF-06/07/08, EVID-03/05/06, DIST-04/05, AUD-01..10 | Benchmark ASVspoof; CONS; exemplos CI; LLM-Auditor gated |

## 5. Definição de "done"
✅ Implementado + testes passando + CI verde + cobertura não regrediu + Regras respeitadas + contrato retrocompatível + numpy-only intacto.

---

# PARTE IV — REGISTRO DE VALIDAÇÃO

## 8. Fontes
- R1, R2, R4, R7: leitura real do repo (alta confiabilidade)
- R3: genérica sem acesso (descartada)
- R8, R9: externas sem conhecimento do estado (mista)
- R10, R11: ciclo LLM-Auditor (absorvidas com correções)

## 9. Conflitos resolvidos
- Versão: 0.1.0 (pyproject) + semver
- Streaming: dois perfis (PROF-02)
- BS.1770: upgrade para -5
- Cobertura: 80% direto
- R3: descartado formalmente

## 10. Itens rejeitados
- HMAC seal (Ed25519 é superior)
- Genre-timbre como WARNING (viola R1)
- "Bit-for-bit" (bundles têm timestamps)
- pydantic (conflita com dataclasses)
- librosa/pesq/sklearn no core (destrói numpy-only)
- VST3/GUI/tempo real (escopo: CLI, não DAW)

---

# PARTE V — ADENDO A: Camada de Interpretação

## V.1 Princípio — Determinize-then-Narrate
> *"O bundle prova o que o áudio **é**; o relatório LLM interpreta o que isso **significa**."*

## V.2 Gate do LLM-Auditor (Onda 5)
Pré-requisitos: ENG-06 → CONTR-04/05 → EVID-06 → Ondas 0-2 fechadas.

## V.3 Extensões determinísticas (independentes do LLM)
- CONTR-09: `delta_to_threshold` + `near_limit` (Onda 4)
- PROF-11: Validador estrutural de policy (Onda 4)
- EVID-06: Pipeline provenance manifest (Onda 5)

---

**Fim do documento v1.1.** O agente inicia pela Onda 0 com ordem interna obrigatória (GOV-02 → demais → tag).
