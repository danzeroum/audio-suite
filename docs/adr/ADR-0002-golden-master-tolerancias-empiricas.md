# ADR-0002: Golden Master — tolerâncias empíricas (±2σ) e política de regeneração

- **Status:** Aceito
- **Data:** 2026-09-03
- **Decide:** time audio-suite (Documento Mestre v1.2, CORP-04 + CORP-04.r)
- **SHA inspecionado na redação:** `1062d2cd78f2dcc703e46718e4aec47f6433be79`

## Contexto

O Golden Master de processo congela as métricas dos 10 analyzers-core sobre 12
fixtures seed-based. Duas perguntas precisavam de resposta verificável:

1. **Quanta tolerância numérica é legítima?** Comparação bit a bit entre
   linguagens/plataformas é proibida (regra inviolável 5); escolher "0.05" de
   cabeça é arbitrário — grande demais para deixar de mascarar off-by-ones
   reais, pequeno demais para absorver variação aritmética legítima entre
   plataformas.
2. **Quando alguém pode regenerar os esperados?** Sem política, golden files
   viram "aperte o botão até passar".

Evidência empírica que motivou o método: a primeira tentativa de calibração
usou jitter **absoluto** (ε = 2⁻²⁰) e fabricou ruído sobre silêncio digital —
σ explode para métricas de piso (true peak de silêncio saltava ~120 dB entre
trials; glitch contava milhares de eventos de repetição). Método corrigido.

## Decisão

1. **Tolerâncias por (analyzer, metric), derivadas empiricamente**: para cada
   fixture do GM, mede-se cada métrica no sinal limpo e em K=8 cópias com
   **jitter relativo de 1 ulp float32** (x' = x·(1+u), u ~ U(-2⁻²³, 2⁻²³);
   zeros preservados — silêncio não vira ruído). σ por métrica = máximo entre
   fixtures; **tolerância = ceil(2σ, 3 casas), piso 1e-4**.
2. Proveniência completa (σ por métrica, método, semente, data) fica em
   `tests/golden/calibration.json`; as tolerâncias vigentes ficam em
   `tests/golden/manifest.yaml`. **Nenhuma constante hard-coded** — o teste
   `test_golden_tolerances_are_empirical_not_hardcoded` bloqueia o anti-pattern.
3. **Política de regeneração (CORP-04.r)**: `audio-suite golden freeze`
   regenera os esperados; o CI (`golden-guard.yml`) exige, para PR que altere
   `tests/golden/expected/**` ou o manifest: label `golden-regen` (revisão
   humana) **e** justificativa no CHANGELOG (patch menciona "golden").
4. Valores derivados na calibração de 2026-09-03: todas as métricas com
   tolerância 0.001, exceto `rhythmic_grid_alignment` = 0.009 — ver
   `calibration.json` para os σ brutos.

## Mecanismo

- `scripts/golden_calibrate.py --apply` — recalibra e injeta no manifest.
- `audio-suite golden freeze | golden verify` — regenerar/verificar.
- `gm-diff.json` + `gm-diff.html` publicados como artifacts em violação.
- Suíte GM < 90 s (roda em ~9 s; budget verificado por teste).

## Consequências

- **Positivas:** off-by-ones reais são pegos (demonstrado: fator de
  oversampling 4→3 do true peak reprovado com |Δ| até 0,137 dB > 0,001);
  nenhuma constante mágica; regeneração com fricção auditável.
- **Negativas/custos:** recalibração obrigatória em mudanças intencionais de
  comportamento (fricção desejada); σ derivado no mesmo SO — variação
  inter-plataforma maior que 2σ exigirá recalibração documentada.
- **Alternativas descartadas:** tolerância fixa 0.05 (arbitrária, proibida);
  comparação bit-a-bit (proibida pela regra 5); golden por hash de bytes
  (idem).

## Relação com outros itens

CORP-04/CORP-04.r · CORP-01.r (fixtures seed-based) · regra 5 (não bit-a-bit) ·
GOV-11 (este diretório) · TEST-05 (budgets).
