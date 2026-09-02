FROM python:3.12-slim

# System audio dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsndfile1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY audio_suite ./audio_suite
COPY tests ./tests
COPY scripts ./scripts
COPY profiles ./profiles

# Install
RUN pip install --no-cache-dir -e ".[dev]"

# Generate fixtures at build time (deterministic)
RUN python scripts/gen_fixtures.py

# Run as non-root (UID 1000 is the default non-root user in python:slim)
USER 1000

ENTRYPOINT ["python", "-m", "audio_suite"]
CMD ["--version"]
