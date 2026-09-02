FROM python:3.11-slim

# Instalar ffmpeg (para decodificação)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o pacote audio-suite
COPY . /app
WORKDIR /app

# Entrypoint
ENTRYPOINT ["python", "-m", "engine.cli"]
