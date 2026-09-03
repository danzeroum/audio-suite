# ADR-0003: Transição do fuzzing de decode de fail-open para fail-closed

- **Status:** Aceito (fail-open vigente; transição declarada com janela e data-alvo)
- **Data:** 2026-09-03
- **Decide:** time audio-suite (via Documento Mestre v1.2, TEST-03.r / Adendo B)
- **SHA inspecionado na redação:** `1b0df428460c0102b7042488655df8607e3ccb14`

## Contexto

O decoder (`audio_suite/decode.py`, libsndfile + fallback ffmpeg) é a maior
superfície de ataque do audio-suite: processa arquivos não confiáveis em
pipelines de QC e perícia. A suíte de fuzzing (`tests/fuzz/`) existe desde a
Onda 2, mas:

1. **Não rodava no CI** (o job de testes excluía `tests/fuzz` por instabilidade
   de ambiente) — a base existia só localmente;
2. A política vigente era implícita e informal: um crash do decoder em fuzz era
   tratado como bug a registrar, **não** bloqueava merge (**fail-open**).

TEST-03.r (Documento Mestre v1.2, Adendo B) determina o endurecimento do fuzz
com transição **fail-open → fail-closed** documentada em ADR — janela declarada,
não "zero crashes" retórico.

## Decisão

1. **Hoje (fail-open):** qualquer crash (exceção que não seja `DecodeError`,
   hang ou timeout) encontrado pela suíte de fuzz é bug com prioridade alta,
   registrado em issue, mas **não bloqueia merge** de PRs não relacionados.
2. **Janela de observação (declarada):** de **2026-09-03** (merge deste ADR,
   que inclui o job `fuzz` no CI e os casos adversariais novos FUZZ-05..08) até
   **2026-09-10** (7 dias corridos de execução do job `fuzz` em `main`).
3. **Transição (fail-closed):** ao completar 7 dias consecutivos de job `fuzz`
   **sem crash** (apenas `DecodeError` esperado, sem exceção inesperada),
   o PR de transição torna a falha de fuzz **bloqueante** no CI. O PR de
   transição deve citar os SHAs dos 7 runs verdes (ledger público do CI).
4. **Data-alvo (deadline):** se até **2026-09-14** a janela não puder ser
   completada sem crash, o crash pendente vira bloqueante imediato (correção
   prioritária obrigatória) — fail-closed é alcançado pela data-alvo de qualquer
   forma, com issue aberta rastreando o crash.

## Mecanismo

- Job `fuzz` no `.github/workflows/ci.yml` roda `pytest tests/fuzz` a cada PR
  e push em `main` (a partir deste ADR).
- "Crash" = qualquer exceção não-`DecodeError`, hang > deadline do Hypothesis,
  ou timeout do job.
- Fail-closed = remover qualquer tolerância: o job `fuzz` vermelho **bloqueia**
  o merge (branch protection + required check quando GOV-05 estiver ativo).

## Consequências

- **Positivas:** superfície de decoder sob execução contínua; transição com
  critério objetivo e auditável; cobertura adversarial ampliada (payload
  corrompido, chunk sizes mentirosos, bit depths exóticos, NaN/Inf).
- **Negativas/custos:** janela de ~1 semana com política de leniência conhecida;
  risco residual de crash desconhecido até a data-alvo — aceito e monitorado.
- **Alternativas descartadas:** fail-closed imediato (sem base de observação,
  bloquearia PRs por instabilidade de ambiente já vivida); fuzz manual sem CI
  (não auditável, já demonstrado insuficiente).

## Relação com outros itens

- Este ADR antecipa a criação de `docs/adr/` (GOV-11, Onda 4), que formaliza o
  diretório e o template. ADR-0001 (proveniência de código externo) permanece
  **reservado** e bloqueante para qualquer acionamento do eixo Rust (VI.2).
