# 🎛️ audio-suite — Assurance engine for audio artifacts

> **Mede. Decide. Prova.**
> Validação acústica + governança para pipelines de áudio, com evidência verificável.

---

## ✅ Visão

A `audio-suite` é uma ferramenta de linha de comando que:

1. **Mede** propriedades acústicas de um áudio (LUFS, true peak, clipping, metadados)
2. **Aplica** uma política versionada (profile YAML)
3. **Emite** um bundle de evidência JSON que prova o que ocorreu

---

## 🚀 Quickstart

```bash
# 1. Clone e instale dependências
pip install -r requirements.txt

# 2. Gere fixtures de teste (áudios deliberadamente ruins)
python scripts/generate_fixtures.py

# 3. Valide um áudio contra o profile broadcast
python -m engine.cli validate fixture-output/clipping.wav \
  --profile registry/policy-profiles/broadcast_ebu_r128_v1.yaml \
  --output bundle.json

# 4. Veja o resultado
cat bundle.json
```

---

## 📋 Recorte Alpha (v0.1.0-alpha)

| Componente | Status |
|---|---|
| CLI | ✅ |
| Loudness (LUFS) | ✅ |
| True peak (dBTP) | ✅ |
| Clipping detection | ✅ |
| Metadados + PII em tags | ✅ |
| Profiles YAML versionados | ✅ |
| Evidence bundle JSON | ✅ |
| Rights manifest validator | ✅ |
| GitHub Action | ✅ |
| Adapter PSE (stub) | 🟡 |
| Regression / Golden master | 🔴 Adiado |
| Fingerprint / Similarity | 🔴 Adiado |
| A/B perceptual web | 🔴 Adiado |

---

## 🧩 Estrutura de diretórios

```
audio-suite/
├── contracts/          # JSON Schemas
├── engine/             # CLI + motor de execução
├── analyzers/          # Loudness, signal, metadata...
├── integrations/       # GitHub Action + adapter PSE
├── registry/           # Profiles + rights manifest
├── scripts/            # Fixture generator
├── tests/              # Pytest
└── docs/               # Documentação
```

---

## 🛠️ Desenvolvimento

```bash
# Instalar dev deps
pip install -r requirements.txt

# Rodar testes
pytest

# Gerar fixtures
python scripts/generate_fixtures.py
```

---

## 📄 Licença

MIT
