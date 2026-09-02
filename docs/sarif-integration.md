# SARIF Integration — Limites (A9)

## O que SARIF oferece

- `audio-suite validate ... --format sarif` produz `bundle.sarif` compatível com SARIF 2.1.0.
- Pode ser consumido por ferramentas que suportam SARIF: GitHub Code Scanning, Azure DevOps, Visual Studio Code.

## O que SARIF NÃO oferece automaticamente

> ⚠️ **Aviso (A9):** A presença do arquivo `.sarif` **não** cria comentários automáticos em PRs.

Para que comentários apareçam no GitHub, é necessário:

1. **Upload via action oficial:**
   ```yaml
   - uses: github/codeql-action/upload-sarif@v3
     with:
       sarif_file: bundle.sarif
   ```

2. **Permissões adequadas:**
   ```yaml
   permissions:
     security-events: write
   ```

3. **Tipo de repositório compatível:**
   - Público: funciona por padrão.
   - Privado: requer GitHub Advanced Security.
   - Forks: requer aprovação do maintainer.

4. **Evento elegível:**
   - `push`, `pull_request`, `workflow_dispatch` funcionam.
   - Outros eventos podem ser ignorados.

## Contrato primário

O **JSON bundle** (`bundle.json`) é o contrato primário e sempre confiável:
- Contém todos os findings, decisão, limitations, assinatura.
- Não depende de permissões do GitHub.
- Pode ser consumido por qualquer ferramenta externa.

SARIF é **integração opcional** para visualização no GitHub.

## Exemplo de workflow

Veja [`.github/workflows/consumer-example.yml`](../.github/workflows/consumer-example.yml) para exemplo completo com upload condicional.
