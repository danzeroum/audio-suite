# Security Policy

## Supported Versions

audio-suite is in active development (0.x). Security fixes are applied to the latest `main` branch.

## Reporting a Vulnerability

If you discover a security vulnerability in audio-suite:

1. **DO NOT** open a public GitHub issue
2. Email: danzeroum@users.noreply.github.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

You will receive a response within 48 hours. If the vulnerability is confirmed, a fix will be released within 7 days for critical issues.

## Security Features

audio-suite provides:

- **Ed25519 signed evidence bundles** — tamper-evident, publicly verifiable
- **PII redaction** — email, phone, user paths automatically redacted
- **Audit log** — hash-chained JSON Lines, tamper detection
- **Non-root Docker** — runs as UID 1000
- **No network access required** — all analysis is local

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Bundle tampering | Ed25519 signature verification |
| PII leakage | Automatic redaction in evidence bundles |
| Malicious audio files | Decoder fuzz tests, timeout per analyzer |
| Supply chain | pip-audit in CI, SBOM planned (DIST-03) |
| Unauthorized access | Audit log records all `analyze`/`inspect` calls |
