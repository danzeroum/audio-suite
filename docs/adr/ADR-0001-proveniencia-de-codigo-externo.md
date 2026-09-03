# ADR-0001: Proveniência de código externo (verificação GPL bloqueante antes de qualquer port)

- **Status:** Reservado (Documento Mestre v1.2, GOV-11 / VI.2) — acionamento condicionado ao gatilho do eixo Rust
- **Data:** 2026-09-03
- **Decide:** time audio-suite, por mandato do Documento Mestre v1.2 (Parte IV §10 e Adendo B VI.2)
- **SHA inspecionado na redação:** `1062d2cd78f2dcc703e46718e4aec47f6433be79`

## Contexto

O eixo Rust está **ARQUIVADO com gatilho** (VI.2): TEST-05 evidenciar violação
de orçamento em ≥2 analyzers OU demanda real de throughput (ENG-03). Caso
acionado, o port naturalmente consideraria código de `danzeroum/mixlirous`
(dual MIT/Apache) e de outras fontes. O audio-suite é **MIT**; o repositório
`au3/` (Audacity, **GPL**) é **proibido** — verificação bloqueante.

Sem um registro formal, a decisão de importar código externo poderia ser
tomada ad hoc num PR, sem a devida análise de compatibilidade de licença e
proveniência — exatamente o tipo de decisão que exige ADR.

## Decisão

1. Este ADR fica **RESERVADO**. Não implementa nada hoje (nenhum port, nenhuma
   dependência de build, nenhuma crate — regra inviolável 3).
2. Quando (e somente quando) o gatilho do VI.2 for acionado, este ADR deve ser
   **completado e aprovado ANTES de qualquer port** — é pré-condição
   bloqueante. Nenhum código externo entra sem:
   a. levantamento da licença de cada arquivo importado (MIT/Apache/BSD ok;
      GPL/AGPL **proibido**);
   b. registro de proveniência (origem, commit, autor, licença) em
      `docs/adr/` e no cabeçalho do arquivo importado;
   c. verificação automatizada no CI (grep por headers de licença + lista de
      permissão de origens).
3. Código de `au3/` (Audacity, GPL) é **proibido em qualquer circunstância** —
   verificação bloqueante em todo PR que tocar código DSP.

## Mecanismo (a implementar no acionamento)

- Script CI `check_provenance.py`: nenhum arquivo novo sob `audio_suite/`
  sem header de licença reconhecido; blacklist de origem GPL.
- Ordem obrigatória do VI.2: ADR-0001 (bloqueante) → port → paridade via
  CORP-04 como oráculo (±2σ, nunca bit-a-bit) → extra `[dsp-rust]` opcional
  (numpy-only permanece default) → fallback registrado em audit log com
  reason code.

## Consequências

- **Positivas:** risco jurídico contido; proveniência auditável; MIT preservado.
- **Negativas/custos:** atrito deliberado no acionamento do Rust — intencional.
- **Alternativas descartadas:** importação ad hoc por PR (inauditável);
  relicenciamento do audio-suite (inaceitável).

## Relação com outros itens

VI.2 (eixo Rust arquivado com gatilho) · regra inviolável 6 (licenças) ·
GOV-11 (este diretório) · ADR-0002 (paridade via tolerâncias ±2σ).
