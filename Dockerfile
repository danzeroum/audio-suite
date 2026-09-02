# Dockerfile reprodutível para audio-suite v0.2.0-beta (F1.6 + A8)
#
# NOTA (A8): Este Dockerfile NÃO é uma GitHub Action por si só. A Action
# consumível está em `integrations/github-action/` (composite action que
# instala o pacote via pip no runner). Este Dockerfile é para ambientes
# que preferem rodar via container.

FROM python:3.11-slim-bookworm AS base

# Versão fixa do ffmpeg (não é "static" — apt fornece build dinâmico;
# para binário estático, baixar de johnvansickle.com/ffmpeg/)
ARG FFMPEG_VERSION=5.1.6
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -version | head -1

# Camada de dependências (cache)
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -r requirements.txt

# Camada de código
COPY . .

# Sanity check
RUN python -c "import engine; import analyzers; print(engine.__version__)"

# Default entrypoint
ENTRYPOINT ["python", "-m", "engine.cli"]
CMD ["--help"]
