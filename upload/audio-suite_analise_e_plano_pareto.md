# audio-suite — Análise Técnica e Plano de Ação (Pareto)

Repositório analisado: `danzeroum/audio-suite` (branch `main`, commit `b2b5f72a`)

## 1. O que o projeto já é hoje

**Proposta:** CLI Python de análise acústica objetiva ("Acoustic analysis CLI for objective defect detection and perceptual quality assessment"), `pyproject.toml` v0.1.0, dependência única em runtime declarada (`numpy>=1.26`).

**Princípio de design (documentado no README):** o suite nunca transforma descritores subjetivos em falhas automáticas — há uma separação explícita de três classes:
- Métricas descritivas (centróide, BPM, tonalidade) → `observation`
- Defeitos objetivos (clipping, glitch, cancelamento mono) → `warning`/`fail` via profile
- Inferências semânticas (emoção, autoria, deepfake) → sempre `needs_review`, nunca conclusão

Isso é um diferencial de governança raro no setor — a maioria das ferramentas de áudio (iZotope RX, Auphonic, Dolby) não expõe essa distinção epistemológica de forma explícita.

**35 analisadores registrados**, cada um com contrato padronizado (`ID`, `NAME`, `VERSION`, `METHOD`, `DEFAULT_LIMITATIONS`), cobrindo:
- Loudness/broadcast: `loudness` (BS.1770-4), `true_peak`, `lra` (EBU R128)
- Defeitos objetivos: `clipping`, `glitch`, `mono_compat`, `channel_balance`, `loop`, `transient`, `resampling`
- Espectral/timbre: `spectral_health`, `timbre_distance`, `harmonic_tension`, `spectral_irregularity`, `inharmonicity`, `fatigue_index`
- Espacial/multicanal: `multichannel_layout` (5.1/7.1), `binaural_compat`, `spatial_coherence`, `goniometer`
- Voz/fala: `voice_artifacts`, `speech_intelligibility`, `speech_rate`, `pitch_stab`
- Forense/experimental (opt-in, sempre `needs_review`): `enf_phase`, `deepfake`
- Música/estrutura: `stem_sep` (SI-SDR + leakage), `rhythmic_grid_alignment`, `melodic_contour`
- Metadados/proveniência: `inspect`, `codec_conf`, `acoustic_fingerprint`, `metadata_schema_validator` (EBUCore/Dublin Core)
- Contexto: `acoustic_context` (RT60, scene change, noise floor), `ref_quality` (full-ref/no-ref)

**Infraestrutura de evidência (o ponto mais forte do projeto):**
- Bundles de evidência assinados com Ed25519, hash canônico SHA-256 dos findings
- `AuditLog` append-only, encadeado por hash (tamper-evident), estilo chain-of-custody
- Redação de PII (`security/pii.py`)
- Saídas em JSON, SARIF 2.1.0 (integração nativa com GitHub Code Scanning) e HTML (WCAG)
- `action.yml` — GitHub Action própria para rodar análise em CI e publicar SARIF
- `cartridge.py` — API de plugins para analisadores externos em `.py`

**Testes:** ~203 testes, cobertura declarada de 86%, organizados por fase numerada (T01–T110, CT01–CT15 cross-cutting, EV01–EV12 evidence bundle, SG01–SG12 signing, IN01–IN15 integration). CI com `ruff`, `mypy`, `pip-audit`, matriz pytest 3.11/3.12/3.13, build Docker, 23 fixtures determinísticas com manifest SHA-256.

**Maturidade do repositório:** o histórico de commits mostra que **todo o projeto foi construído e mesclado no mesmo dia** (várias fases/PRs sequenciais concluídas hoje), sem tags, sem releases publicados e sem presença no PyPI. Isso é normal para um projeto recém-nascido, mas significa que hoje ele é tecnicamente denso e ainda invisível externamente.

## 2. Lacunas identificadas (gaps reais)

| Categoria | Situação encontrada |
|---|---|
| Testes de integração/e2e/fuzz/performance | Diretórios `tests/e2e`, `tests/fuzz`, `tests/performance`, `tests/integration/{cli,evidence,formats,github_action}` existem mas contêm **apenas `__init__.py`** — é andaime vazio, sem teste real |
| Governança de repositório | Sem `LICENSE`, sem `CONTRIBUTING.md`, sem `SECURITY.md`, sem `CODE_OF_CONDUCT.md`, sem `CHANGELOG.md` |
| Segredo exposto | Há um arquivo `.env` de 50 bytes **commitado na raiz do repositório** — risco de exposição de credencial e sinal ruim de higiene de segurança para um projeto que se vende por rigor forense |
| Distribuição | Sem tag/release no GitHub, sem publicação no PyPI — `pip install audio-suite` não funciona para ninguém fora do clone local |
| Validação externa | Nenhuma comparação publicada contra implementações de referência (ex.: `ffmpeg loudnorm`, `libebur128`, `sox`) para provar acurácia numérica dos analisadores de loudness/true peak |
| Fuzzing de parsers de áudio | Parsers de contêiner/decodificação (`decode.py`) sem testes de fuzzing — é justamente a superfície mais explorada em CVEs de ferramentas de áudio |
| Documentação de uso | README cobre instalação e princípio, mas não há site de documentação, catálogo navegável dos 35 analisadores, nem guia de autoria de profiles (`profiles/strict.yaml` é o único perfil existente) |
| Marketing técnico | Sem badges de build/coverage/license, sem benchmark de performance publicado, sem exemplos de SARIF integrado em PR real |
| Machine learning real | `deepfake.py` é heurístico "no ML model bundled"; correto pela política de não-inferência, mas limita uso prático em forense sério |

## 3. Plano de Pareto (80/20) — onde atacar primeiro

O critério de priorização é: **impacto na credibilidade/posicionamento como referência dividido pelo esforço de implementação**, dado que a base técnica já é sólida (35 analisadores, engine, assinatura, SARIF).

### Tier 1 — Baixo esforço, alto impacto (fazer nesta semana)

| # | Ação | Por quê é Pareto |
|---|---|---|
| 1 | Remover `.env` do histórico (`git filter-repo`/BFG) e adicionar `.env.example` | Corrige o único risco de segurança visível; crítico para um projeto que vende "chain-of-custody" |
| 2 | Adicionar `LICENSE` (MIT ou Apache-2.0) | Sem licença, empresas juridicamente não podem adotar a ferramenta — bloqueio total de adoção corporativa |
| 3 | Criar tag `v0.1.0` + GitHub Release com changelog do que já foi implementado | Transforma 12 commits dispersos em uma versão citável e instalável |
| 4 | Publicar no PyPI (`pip install audio-suite`) | Reduz fricção de adoção de "clonar repo" para "um comando" |
| 5 | Badges no README (CI, coverage, license, PyPI, SARIF) | Sinal de maturidade percebida imediata para quem visita o repo |
| 6 | `SECURITY.md` + `CONTRIBUTING.md` | Ferramenta forense/assinada precisa de canal de disclosure responsável; abre a porta para contribuintes externos |

### Tier 2 — Esforço médio, impacto alto (próximas 2–4 semanas)

| # | Ação | Por quê é Pareto |
|---|---|---|
| 7 | Preencher `tests/fuzz` com fuzzing real dos parsers (Atheris ou Hypothesis + arquivos WAV/MP3 malformados) | Maior ganho de robustez por linha de código escrita — decoders de áudio são alvo clássico de crash/CVE |
| 8 | Preencher `tests/performance` com benchmarks reais (áudio de N minutos → tempo/analyzer) e publicar no README | Prova a viabilidade em produção/CI, argumento comercial concreto |
| 9 | Validação cruzada dos analisadores BS.1770-4/EBU R128 contra `ffmpeg`/`libebur128` em corpus público, publicando delta numérico | É a prova de acurácia que falta para reivindicar "referência técnica" — sem isso, os métodos são só declarações |
| 10 | Preencher `tests/e2e` e `tests/integration/{cli,evidence,formats,github_action}` com cenários reais (CLI ponta a ponta, verificação de assinatura, roundtrip SARIF em um PR real) | Estrutura já existe — é o preenchimento mais barato possível para eliminar o "andaime vazio" |

### Tier 3 — Maior investimento, diferenciação de longo prazo

| # | Ação | Por quê importa |
|---|---|---|
| 11 | Site de documentação (MkDocs Material) com catálogo dos 35 analisadores, exemplos de profile e API de plugin (`cartridge.py`) | Necessário para adoção autoguiada, sem isso o produto só é usável por quem já leu o código |
| 12 | Suporte a ADM/BWF e Atmos 9.1.6 (hoje explicitamente "deferred" no roadmap interno) | Fecha a lacuna para o mercado de broadcast/streaming imersivo |
| 13 | Publicação de comparação técnica vs. iZotope RX / Auphonic / Dolby.io em post/benchmark aberto | Movimento de posicionamento público — só vale depois que Tier 1/2 estiverem prontos, senão expõe as lacunas antes da hora |
| 14 | Modelo de ML real (ou parceria) para `deepfake`/`enf_phase`, mantendo a política de nunca concluir sozinho | Transforma um stub honesto em capacidade forense real, sem violar o princípio de governança do projeto |

## 4. Ordem de execução recomendada

1. Tier 1 completo (itens 1–6) — nenhum requer decisão de arquitetura, tudo é higiene/distribuição.
2. Item 9 (validação cruzada de acurácia) antes de qualquer divulgação pública — é o que sustenta a palavra "referência".
3. Itens 7, 8, 10 em paralelo — reaproveitam a estrutura de testes já criada.
4. Tier 3 como roadmap trimestral, começando pela documentação (11), que amplifica o retorno de tudo que já foi feito.
