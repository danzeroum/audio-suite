# audio-suite

> **Mede. Decide. Prova.**
> Assurance engine for audio artifacts: medição acústica, política versionada e evidência verificável.

**Status:** v0.2.0-beta — CLI funcional, analyzers de loudness/signal/phase/metadata/provenance/rights_manifest, profiles EBU R 128, GitHub Action, assinatura Ed25519, SARIF output.

⚠️ **Beta ≠ GA** — veja [`docs/beta-vs-ga.md`](docs/beta-vs-ga.md).

---

## 🚀 Quickstart (3 comandos)

```bash
# 1. Instale
pip install -e ".[dev]"
sudo apt-get install -y ffmpeg  # ou: brew install ffmpeg

# 2. Gere fixtures de teste (10 casos de mordida)
python scripts/generate_fixtures.py

# 3. Valide um áudio
audio-suite validate fixtures/clipped_sine/audio.wav \
  --profile registry/policy-profiles/broadcast_ebu_r128_v1.yaml \
  --output bundle.json --format sarif
```

---

## 📋 Comandos da CLI

| Comando | Descrição |
|---------|-----------|
| `audio-suite inspect <file>` | Metadados + medidas (sem policy) |
| `audio-suite inspect <file> --analysis basic` | + PCM hash, sample peak |
| `audio-suite inspect <file> --analysis full` | + loudness, true peak |
| `audio-suite validate <file> --profile <yaml> -o <bundle.json>` | Validação completa |
| `audio-suite validate ... --format sarif` | + SARIF 2.1.0 output |
| `audio-suite validate ... --signature-mode local-key` | Assina bundle com Ed25519 |
| `audio-suite verify <bundle.json>` | Verifica assinatura |
| `audio-suite key generate` | Gera chave Ed25519 local |

---

## 🧩 Estrutura

```
audio-suite/
├── contracts/          # JSON Schemas + registry.json (S1, O7)
├── engine/             # CLI + motor de execução
│   ├── bundle/         # fingerprint, signer, limitations, truncate, schema_version
│   └── cli_formats/    # SARIF output
├── analyzers/          # loudness, signal, phase, metadata, provenance, rights_manifest
├── integrations/       # GitHub Action (composite) + adapter PSE
├── registry/           # Profiles + rights manifest + lockfile (O6)
├── fixtures/           # 10 fixtures de mordida com expected.json (S2)
├── scripts/            # generate_fixtures.py
├── tests/              # pytest (≥70% coverage)
├── .github/workflows/  # CI + consumer example
├── Dockerfile          # Container reprodutível
└── docs/               # Documentação
```

---

## 🛡️ Modelo de decisão

| Estado | Significado |
|--------|-------------|
| `pass` | Check aplicável e policy satisfeita |
| `warning` | Risco abaixo do limiar de bloqueio |
| `fail` | Policy violada |
| `not_applicable` | Check não se aplica ao artefato |
| `indeterminate` | Evidência insuficiente |
| `needs_review` | Revisão humana necessária |

**Separação obrigatória:** analyzer mede → profile define thresholds → engine decide → bundle prova.

---

## 🔐 Assinatura Ed25519

3 modos (F2.2 + A6):

| Modo | Uso | Como |
|------|-----|------|
| `unsigned` | Dev local (default) | `--signature-mode unsigned` |
| `local-key` | Laboratório | `audio-suite key generate` → `--signature-mode local-key` |
| `ci-key` | CI controlada | Env `AUDIO_SUITE_CI_KEY` (base64 PEM) → `--signature-mode ci-key` |

Verificação: `audio-suite verify bundle.json`

Veja [`docs/security.md`](docs/security.md) para gestão de chaves.

---

## 🧪 Testes

```bash
pytest tests --cov=engine --cov=analyzers --cov-report=term
```

Meta: ≥70% global, ≥60% por módulo. Veja [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md).

---

## 📄 Licença

MIT — veja [LICENSE](LICENSE).
