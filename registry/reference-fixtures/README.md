# Reference Fixtures

Este diretório contém (ou produz via `scripts/generate_fixtures.py`) áudios de referência
usados como "mordida" para validar a suíte contra casos conhecidos.

## Como gerar

```bash
python scripts/generate_fixtures.py
```

Gera 5 WAVs em `fixture-output/`:

| Arquivo | Problema esperado |
|---|---|
| `clipping.wav` | Amostras em full scale (clipping) |
| `loudness_high.wav` | LUFS acima do target EBU R 128 |
| `true_peak_high.wav` | True peak > -1 dBTP |
| `phase_inverted.wav` | Canal direito com fase invertida |
| `clean_pass.wav` | Sem problemas — deve passar |

Cada fixture é gerado deterministicamente a partir de senoides sintéticas — não usa
áudio de terceiros, evitando questões de licenciamento.
