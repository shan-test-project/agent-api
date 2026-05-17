FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget ffmpeg nodejs npm \
    build-essential libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g ts-node typescript

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create necessary directories
RUN mkdir -p sandbox uploads chroma_db

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose WebApp port
EXPOSE 8080

# Start both the bot and webapp server
CMD ["sh", "-c", "python webapp/server.py & python main.py"]
