# DOCUMENTO MESTRE — audio-suite v1.2
## Especificação de Melhorias, Backlog Consolidado e Plano de Execução

> **Versão:** 1.2 (v1.1 + Adendo B) · **Status:** Aprovado para implementação · **Escopo:** consolidação validada de 6 análises externas (R1–R4, R7, R8, R9, R10, R11) contra o backlog interno + plano MX triado (Adendo B)
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

# PARTE VI — ADENDO B: Ecossistema mixlirous, Golden Master de processo e Reprodutibilidade Forte

**Documento Mestre v1.1 → v1.2** · Origem: plano MX + validação intermediária, triados contra v1.1 · Status: aprovado

## VI.1 Novos IDs

| ID | Item | Onda |
|---|---|---|
| **CORP-04.r** | Processo de golden: comando `audio-suite golden freeze` regenera esperados **só com justificativa + revisão humana**; diff do GM publicado como artifact (JSON + HTML) por PR | 3 |
| **CORP-01.r** | Geradores **seed-based** (`numpy.random.Generator`) como fonte primária de todo fixture; política anti-binários (CI rejeita `.wav` >1 MB em `git ls-files`); `expected_findings` opcional no manifest | 3 |
| **CORP-08** | Corpus de **defeito injetado com ground truth** (`expected_findings: list[rule_id]`) → cálculo de precisão/recall por detector, publicado nas métricas de release | 3 |
| **TEST-03.r** | Fuzz com transição **fail-open → fail-closed** documentada em ADR | 3 |
| **ENG-13** | Comando `audio-suite compare A.wav B.wav` — diff acústico objetivo (ΔLUFS, ΔdBTP, ΔLRA, novos glitches, Δfase), saída `diff.json` com `regression_detected` | 4 |
| **EVID-07** | `reproduction_command` + `environment_hash` no bundle/SARIF | 4 |
| **EVID-08** | `--frozen-manifest` (+`--strict`): recusa execução se versão de qualquer analyzer ou hash de profile divergir do manifesto — reprodutibilidade forte de laudo | 4 |
| **EVID-02.r+** | Ampliado: SHA-256 do profile YAML resolvido + backend DSP usado, no snapshot de ambiente | 4 |
| **GOV-11** | `docs/adr/` com template; ADR-0001 reservado para proveniência de código externo (verificação GPL bloqueante) | 4 |
| **GOV-12** | Handoff para agentes de IA (`AGENTS.md`): comandos, invariantes R1/R2/R4/R8, lista de "nunca fazer" | 4 |
| **GOV-13** | Sync backlog ↔ GitHub Issues (P2) | 4 |
| **PROF-08.r** | Mecanismo: **linter do registry de rule_ids** (CI + pre-commit) — analyzer não pode declarar fail sobre métrica da classe descritiva | 4 |
| **PROF-06.r** | Sub-variantes de `music-master` por plataforma (streaming/TikTok/club) | 5 |
| **DOCS-04.r** | Caso de uso: gate pós-render do mixlirous; mapeamento status ↔ limiares GM (0,05 / 0,15 / 0,35) | 5 |
| **CONF-03.r** | Loudness Rust do mixlirous como oráculo adicional na matriz de validação cruzada (depende de CONF-02) | 5 |
| **BACKLOG-13** | Wrapper HTTP do CLI (compose QA) | Gatilho: ≥2 consumidores |
| **BACKLOG-14** | Pacote OPS do MX (trace_id UUIDv7, audit_events multi-tenant, observabilidade) | Gatilho: modo serviço |

## VI.2 Eixo Rust — condicionado, com gate explícito

Não entra em nenhuma onda. **Pré-condição de acionamento:** TEST-05 evidenciar violação de orçamento em ≥2 analyzers OU demanda real de throughput (ENG-03). Se acionado: GOV-11/ADR-0001 (proveniência GPL — bloqueante) → port → **paridade via CORP-04 como oráculo (±2σ do corpus, nunca bit-a-bit)** → fallback registrado no audit log com reason code → extra `[dsp-rust]`; Python permanece reference implementation; backend integra EVID-02.r. Casos de paridade Rust↔Python herdam o padrão CONS (divergência é investigação, não erro automático).

## VI.3 Registro de validação (atualiza PARTE IV/§8)

**Fontes adicionais:** MX (30 itens triados: 9 genuínos, 8 refinamentos, 8 redundantes, 5 condicionados, 1 rejeitado) · V-MX (validação intermediária: acertos incorporados — tolerâncias empíricas, fallback auditado, métricas realistas; falhas registradas — ausência de triagem item a item e de gate Rust). **Rejeição reafirmada:** HMAC (MX-VF-04) — idêntica ao N-19 do R9. **Estado: 14 categorias, ~125 IDs.**

**Verificação de estado (2026-09-03, HEAD `551dd97`):** `tests/fuzz/test_FUZZ01_04_decode.py` e `tests/conformance/test_CONF02_05_loudness.py` já existem (TEST-03.r é endurecimento sobre base existente; CONF-02 parcialmente implementado — CONF-03.r pode antecipar); `tests/golden/` vazio (CORP-04/.r pendente); `docs/decisions/` inexistente (GOV-11 o cria). Todo PR e toda validação deve citar o SHA do commit inspecionado.

---

**Fim do documento v1.2.** O agente inicia pela Onda 0 com ordem interna obrigatória (GOV-02 → demais → tag). Este documento é a única fonte de verdade — sugestões futuras passam pelo mesmo protocolo de triagem (§10) antes de ganhar ID.


---

# PARTE VII — REGISTRO DE EXECUÇÃO (Ondas 3–5)

> **Nota de protocolo:** este registro é ADITIVO — nenhuma seção aprovada
> (Partes I–VI) foi reescrita. Cada linha cita o SHA squash do merge do PR.
> Execução: 2026-09-03, agente de implementação, SHA inspecionado de partida
> `8bf82bc98a090d7d830fe6f8d5bef43a1925f3bc`.

## Onda 3 — Robustez + Golden Master de processo

| ID | Entrega | PR | SHA do merge |
|---|---|---|---|
| CORP-01.r | Geradores seed-based primários (`tests/fixtures/generators.py`), política anti-binários (script + job CI), `expected_findings` no manifest; fix: float WAV determinístico (libsndfile embutia wall-clock no PEAK) e high_bw_96k de fato a 96 kHz | [#9](https://github.com/danzeroum/audio-suite/pull/9) | `6f522768a9d71110d22704095f6e6abd650ab449` |
| CORP-04 + CORP-04.r | Golden Master de processo: expected por analyzer (10 grupos × 12 fixtures), tolerâncias ±2σ empíricas (jitter relativo 1 ulp; `calibration.json`), `golden freeze/verify`, gm-diff.json/html, guard CI (`golden-regen` + CHANGELOG); glitch vetorizado bit-a-bit equivalente (GM 9,3 s < 90 s) | [#10](https://github.com/danzeroum/audio-suite/pull/10) | `a961d96adcd9a9831c420a312d24923fce1f3487` |
| — | Demonstração DoD: PR aberto com off-by-one no oversampling do true peak (4→3) — rejeitado com diff legível (não mesclar) | [#11](https://github.com/danzeroum/audio-suite/pull/11) | aberto (evidência) |
| CORP-08 | Corpus de defeito injetado com ground truth (6 tipos), `detector_score.py` (precisão/recall por detector e rule_id), tabela no README + artifact CI; gap dc_offset documentado | [#12](https://github.com/danzeroum/audio-suite/pull/12) | `1b0df428460c0102b7042488655df8607e3ccb14` |
| TEST-03.r | Fuzz endurecido (FUZZ-05..08: payload corrompido, chunks mentirosos, bit depths exóticos, NaN/Inf); health checks do Hypothesis corrigidos (divergência registrada); ADR-0003 com janela 2026-09-03→2026-09-10 e data-alvo 2026-09-14; job fuzz no CI | [#13](https://github.com/danzeroum/audio-suite/pull/13) | `dd513ef580fa488d6d6981ae5f1c998905040997` |

## Onda 4 — Produto + reprodutibilidade + governança

| ID | Entrega | PR | SHA do merge |
|---|---|---|---|
| ENG-13 | `audio-suite compare A.wav B.wav`: Δs objetivos, only_in_b por rule_id, descritores como observation (R1), `regression_detected`, schema `compare-v1.json` (CONTR-01), `--fail-on-regression` | [#14](https://github.com/danzeroum/audio-suite/pull/14) | `f4964cebd21a35430da325aa768cd8e35060ea49` |
| EVID-02.r+ | Snapshot de ambiente (profile resolvido SHA-256, `environment_hash`, versões de analyzers, `dsp_backend: python`); assinatura Ed25519 cobre environment (quebra declarada) | [#15](https://github.com/danzeroum/audio-suite/pull/15) | `6a3b62c0c92e1d93ad9e0f326063a750d1494b49` |
| EVID-07 | `reproduction_command` no bundle JSON e SARIF (determinístico, ordem fixa) | [#16](https://github.com/danzeroum/audio-suite/pull/16) | `53d9b724cceef5018554ecc4c60d42ef60798538` |
| EVID-08 | `--frozen-manifest` (+`--strict`): pré-checks com erro nomeado, identidade byte a byte exceto campos declarados; exit 65 | [#17](https://github.com/danzeroum/audio-suite/pull/17) | `1062d2cd78f2dcc703e46718e4aec47f6433be79` |
| GOV-11 | `docs/adr/` formalizado: TEMPLATE + ADR-0001 (reservado, proveniência/GPL bloqueante) + ADR-0002 (tolerâncias ±2σ) + ADR-0004 (HMAC rejeitado); ADR-0003 veio no TEST-03.r | [#18](https://github.com/danzeroum/audio-suite/pull/18) | `dd453e4f3734c5bc81dec91f2f58c98d1b8800e0` |
| GOV-12 | `AGENTS.md`: comandos, invariantes R1/R2/R4/R8, regra do SHA, 10 "nunca fazer" | [#19](https://github.com/danzeroum/audio-suite/pull/19) | `817771aef4151f57ae50299c6abaee18fdf3bfe3` |
| GOV-13 | Sync backlog ↔ Issues idempotente (`scripts/sync_issues.py` + `backlog.yaml`); 16 issues (#20–#35), labels `onda/N`/`prio/N`; re-execução: 0 duplicatas | [#36](https://github.com/danzeroum/audio-suite/pull/36) | `b23dec91868d7405d3cbe6f775bcbef78957d4e8` |
| PROF-08.r | Linter do registry (3 camadas: perfis, probe dinâmico, scan AST); CI `rule-registry-lint` + `.githooks/pre-commit`; DoD: descritivo em fail rejeitado (5 violações, exit 1) | [#37](https://github.com/danzeroum/audio-suite/pull/37) | `2240e2973ef655c5f359190637c3e321d634d22b` |

## Onda 5 — Ecossistema mixlirous

| ID | Entrega | PR | SHA do merge |
|---|---|---|---|
| CONF-03.r | mixlirous Rust como oráculo adicional (CLI/subprocess, sem dependência de código); padrão CONS (divergência = `needs_investigation`, limiar 0,5 LU); matriz `oracle-matrix.json` como artifact; skip sem `MIXLIROUS_CLI`; adapter provado com binário fake | [#38](https://github.com/danzeroum/audio-suite/pull/38) | `85ffda02430e5f46a85c3f8f5ac86e56fd535f28` |
| PROF-06.r | Herança de profiles (`extends:` com deep-merge e cadeia) + `music-master/{streaming,shortform,club}.yaml`; `rule_id_class()` no registry; R1-clean pelo linter | [#39](https://github.com/danzeroum/audio-suite/pull/39) | `e5d518e7cfee0d4a5ae0659c1a91258be2ff8f06` |
| DOCS-04.r | Caso de uso: gate pós-render do mixlirous; mapeamento GM 0,05/0,15/0,35 → pass/needs_review/fail; script de gate validado contra o código real | [#40](https://github.com/danzeroum/audio-suite/pull/40) | `1bc8656455309b0827abccbed401d245d5421cb6` |

## Estado ao fim da execução (SHA `1bc8656455309b0827abccbed401d245d5421cb6`)

- Suíte: **381 passed, 1 skipped** (oráculo Rust ausente — por design), 0 falhas (fuzz incluído).
- Critérios de sucesso da missão: todos atendidos (ver PRs acima). Zero Rust, zero HMAC, zero binário > 1 MB commitado — como exigido.
- Divergências registradas nos PRs conforme protocolo ("código vence para fatos, prompt vence para decisões"): health checks de fuzz quebrados desde a Onda 2 (TEST-03.r #13); jitter absoluto vs. relativo na calibração GM (#10); `--output`/`--strict` fora do `reproduction_command` (EVID-08 #17); high_bw_96k gravado a 44,1 kHz com label errada (CORP-01.r #9).
- Pendências herdam gatilho, não escopo: BACKLOG-13/14 e eixo Rust (VI.2) permanecem arquivados; transição fuzz fail-closed observa janela do ADR-0003 (2026-09-10, data-alvo 2026-09-14).
