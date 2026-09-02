# scripts/

Scripts utilitários do projeto.

## generate_fixtures.py

Gera 5 WAVs de teste em `fixture-output/`:

```bash
python scripts/generate_fixtures.py
```

Os fixtures cobrem casos de:
- Clipping intencional
- Loudness acima do target EBU R 128
- True peak acima de -1 dBTP
- Fase invertida (stereo)
- Caso de sucesso (clean pass)
