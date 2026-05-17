#!/bin/bash
# ReplitAI startup script

set -e

cd "$(dirname "$0")"

echo "⚡ Starting ReplitAI..."

# Create dirs
mkdir -p sandbox uploads chroma_db

# Check required env vars
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
  echo "❌ TELEGRAM_BOT_TOKEN is not set. Add it to your environment secrets."
  exit 1
fi

if [ -z "$GROQ_API_KEY" ]; then
  echo "❌ GROQ_API_KEY is not set. Get a free key at console.groq.com"
  exit 1
fi

echo "✅ Credentials found"

# Start WebApp server in background (if WEBAPP_URL is set or always for WebApp)
echo "🌐 Starting WebApp server on port ${WEBAPP_PORT:-8080}..."
python webapp/server.py &
WEBAPP_PID=$!

# Small delay
sleep 2

# Start the bot
echo "🤖 Starting Telegram bot..."
python main.py

# Cleanup on exit
trap "kill $WEBAPP_PID 2>/dev/null; exit" SIGTERM SIGINT
wait
