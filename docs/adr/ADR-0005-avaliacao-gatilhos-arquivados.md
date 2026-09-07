# ADR-0005: Avaliação dos gatilhos de itens arquivados (VI.2, BACKLOG-13/14) — nenhum acionado

- **Status:** Aceito (registra avaliação com dados; itens permanecem arquivados com gatilho)
- **Data:** 2026-09-07
- **Decide:** danzeroum (solicitação direta de execução dos itens arquivados) + agente de implementação (medição dos gatilhos), sob o Documento Mestre v1.2 (VI.2 e `backlog.yaml`)
- **SHA inspecionado na redação:** `12cb5d3a7ba2113ea9a7226284c0158ee4b1ad54`

## Contexto

Foi solicitada a execução dos itens arquivados com gatilho: eixo Rust (VI.2),
BACKLOG-13 (wrapper HTTP) e BACKLOG-14 (pacote OPS), além do acompanhamento da
janela de transição do fuzzing (ADR-0003, alvo 2026-09-14). O Documento Mestre
v1.2 é explícito: itens arquivados **não entram em execução sem gatilho
objetivo** (VI.2: "NÃO implementar sem o gatilho"; AGENTS.md lista "portar Rust
sem gatilho" entre os nunca-fazer). A solicitação, portanto, dispara o
procedimento correto: **medir os gatilhos** e acioná-los apenas se satisfeitos.
Se nada fosse decidido, o pedido ficaria sem resposta auditável e os itens
arquivados correriam risco de implementação ad hoc.

## Decisão

1. **Eixo Rust (VI.2): NÃO acionado.** Medições de 2026-09-07:
   - **TEST-05** (`tests/performance/test_PERF01_06_budgets.py`): no CI
     (ambiente canônico), o job `Performance Baseline` está verde em **19/19
     commits** do main desde 2026-09-03 (inclusive nos commits com o job
     `Lint & Security` vermelho — a falha era de formatação, não de
     performance). Localmente (sandbox mais lento), 5/6 benchmarks passam;
     o único sinalizado (PERF-01, loudness) excedeu o orçamento **apenas no
     cold-start** (1ª chamada 1,165 s > 1,0 s; steady-state 0,021 s →
     **475× realtime**, margem de 9,5× sobre os 50× exigidos). Violações:
     **0 no CI, 1 no pior caso local (artefato de cold-start, não de
     throughput)** — o gatilho exige **≥2 analyzers** → não satisfeito.
   - **ENG-03** (batch/glob + watch-folder, P2): nenhuma demanda real
     registrada (nenhuma issue, consumidor ou discussão pedindo throughput) →
     não satisfeito.
   - Se um dia acionado: sequência obrigatória VI.2 — ADR-0001 (proveniência
     GPL, **bloqueante**) → port → paridade via CORP-04 (±2σ, nunca bit-a-bit)
     → fallback no audit log com reason code → extra `[dsp-rust]`; Python
     permanece reference implementation.
2. **BACKLOG-13 (wrapper HTTP): NÃO acionado.** Consumidores programáticos
   conhecidos: **1** (padrão documentado de gate pós-render do mixlirous,
   DOCS-04.r). O gatilho exige **≥2** → não satisfeito.
3. **BACKLOG-14 (pacote OPS): NÃO acionado.** Não há modo serviço: nenhum
   servidor, deployment ou pedido de tenancy/observabilidade; o Dockerfile
   empacota o CLI. Gatilho ("modo serviço") → não satisfeito.
4. **ADR-0003 (janela de fuzz): em curso, monitorada.** Ledger de 2026-09-07:
   **14/14 runs verdes** do job `Fuzz decoder (TEST-03.r)` no main desde a
   abertura da janela (`dd513ef`, 2026-09-03 16:50 UTC), **zero crashes**. A
   transição fail-closed **não é executada hoje** — o PR de transição será
   aberto após o fechamento da janela (**2026-09-10**) e até a data-alvo
   (**2026-09-14**), citando os SHAs dos ≥7 runs verdes. Monitoramento
   operacionalizado por `scripts/fuzz_ledger.py` (re-executável, stdlib pura).

## Mecanismo

- Este ADR é o registro pesquisável da recusa fundamentada; qualquer pedido
  futuro de Rust/BACKLOG-13/14 sem gatilho recebe este ADR como resposta.
- `scripts/fuzz_ledger.py`: lista cada commit do main desde a abertura da
  janela com a conclusão do job de fuzz; produz a evidência (SHAs dos runs
  verdes) exigida pelo PR de transição do ADR-0003. Uso:
  `GITHUB_TOKEN=... python3 scripts/fuzz_ledger.py`.
- Reavaliação dos gatilhos: a cada violação real de orçamento de performance
  (em qualquer ambiente) ou a cada novo consumidor programático proposto.

## Consequências

- **Positivas:** recusa com números (não com opinião); ledger de fuzz pronto
  para o PR de transição; critério objetivo e auditável preservado.
- **Negativas/custos:** os benchmarks pytest de TEST-05 não são gate de CI
  (o job de performance executa um smoke script) — a evidência de orçamento
  depende de execução fora do CI; observação registrada: PERF-01 tem margem
  fina sob cold-start (1,165 s vs 1,0 s) — recomenda-se, como item futuro
  distinto, warm-up no conftest ou revisão do orçamento.
- **Alternativas descartadas:** acionar o eixo Rust sem gatilho (viola VI.2 e
  o "nunca fazer" do AGENTS.md); flip fail-closed imediato (viola a janela
  declarada do ADR-0003); ignnorar o pedido sem registro (deixaria a decisão
  sem trilha de auditoria).

## Relação com outros itens

- VI.2 (eixo Rust condicionado), BACKLOG-13/14, ENG-03, TEST-05 (ADR-0002 —
  tolerâncias/orçamentos), ADR-0001 (**permanece reservado**, bloqueante para
  o eixo Rust), ADR-0003 (janela de fuzz), DOCS-04.r (consumidor mixlirous),
  AGENTS.md (lista de nunca-fazer, item 1).
