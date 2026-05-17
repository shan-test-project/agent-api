import asyncio
import logging
from pathlib import Path
from typing import Optional
from tools.terminal import execute_shell
from tools.file_manager import write_file

logger = logging.getLogger(__name__)

DOCKERFILE_TEMPLATES = {
    "python": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "main.py"]
""",
    "node": """FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "index.js"]
""",
    "fastapi": """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
    "nextjs": """FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
""",
    "go": """FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
""",
}

DOCKER_COMPOSE_TEMPLATE = """version: '3.8'
services:
  app:
    build: .
    ports:
      - "{port}:{port}"
    environment:
      - NODE_ENV=production
    env_file:
      - .env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{port}/health"]
      interval: 30s
      timeout: 10s
      retries: 3
"""

GITHUB_ACTIONS_TEMPLATE = """name: CI/CD

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: python -m pytest tests/ -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Railway
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          npm install -g @railway/cli
          railway up
"""

RAILWAY_TOML = """[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
"""

FLY_TOML_TEMPLATE = """app = "{app_name}"
primary_region = "iad"

[build]

[http_service]
  internal_port = {port}
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
"""


async def generate_dockerfile(
    language: str = "python",
    project_dir: str = None,
    port: int = 8080,
    custom_config: dict = None,
) -> dict:
    template = DOCKERFILE_TEMPLATES.get(language, DOCKERFILE_TEMPLATES["python"])
    if custom_config:
        for k, v in custom_config.items():
            template = template.replace(f"{{{k}}}", str(v))

    compose = DOCKER_COMPOSE_TEMPLATE.format(port=port)
    actions = GITHUB_ACTIONS_TEMPLATE

    results = {}
    for fname, content in [
        ("Dockerfile", template),
        ("docker-compose.yml", compose),
        (".github/workflows/ci.yml", actions),
        ("railway.toml", RAILWAY_TOML),
    ]:
        r = await write_file(fname, content, project_dir)
        results[fname] = r["success"]

    return {
        "success": True,
        "dockerfile": template,
        "docker_compose": compose,
        "files_created": results,
        "message": f"Docker + CI/CD files created for {language} app on port {port}",
    }


async def deploy_to_platform(platform: str, project_dir: str, app_name: str = "myapp") -> dict:
    platform = platform.lower().strip()
    instructions = {
        "railway": (
            "**Deploy to Railway:**\n"
            "```bash\n"
            "npm install -g @railway/cli\n"
            "railway login\n"
            "railway init\n"
            "railway up\n"
            "```\n"
            "Or connect your GitHub repo at railway.app for auto-deploys."
        ),
        "fly": (
            "**Deploy to Fly.io:**\n"
            "```bash\n"
            "curl -L https://fly.io/install.sh | sh\n"
            "flyctl auth login\n"
            f"flyctl launch --name {app_name}\n"
            "flyctl deploy\n"
            "```"
        ),
        "render": (
            "**Deploy to Render:**\n"
            "1. Push your code to GitHub\n"
            "2. Go to render.com → New + → Web Service\n"
            "3. Connect your GitHub repo\n"
            "4. Set build command: `pip install -r requirements.txt`\n"
            "5. Set start command: `python main.py`\n"
            "6. Add environment variables\n"
            "Free tier available!"
        ),
        "huggingface": (
            "**Deploy to Hugging Face Spaces:**\n"
            "```bash\n"
            "pip install huggingface_hub\n"
            "huggingface-cli login\n"
            "git remote add hf https://huggingface.co/spaces/<username>/{app_name}\n"
            "git push hf main\n"
            "```\n"
            "Free GPU/CPU spaces available!"
        ),
        "vercel": (
            "**Deploy to Vercel:**\n"
            "```bash\n"
            "npm install -g vercel\n"
            "vercel login\n"
            "vercel --prod\n"
            "```\n"
            "Best for Next.js/static sites."
        ),
        "replit": (
            "**Deploy to Replit:**\n"
            "1. Import your GitHub repo at replit.com/new\n"
            "2. Replit auto-detects language and sets up environment\n"
            "3. Click 'Deploy' for always-on hosting\n"
            "4. Or use the Replit CLI: `npm install -g @replit/cli`"
        ),
    }

    if platform not in instructions:
        return {
            "success": False,
            "output": f"Unknown platform: {platform}. Available: {list(instructions.keys())}",
        }

    fly_toml = FLY_TOML_TEMPLATE.format(app_name=app_name, port=8080)
    if platform == "fly":
        await write_file("fly.toml", fly_toml, project_dir)

    return {
        "success": True,
        "platform": platform,
        "instructions": instructions[platform],
        "output": instructions[platform],
    }


async def scan_security(project_dir: str) -> dict:
    checks = []
    from tools.terminal import execute_shell
    result = await execute_shell(
        "pip install bandit safety --quiet && bandit -r . -f json -q 2>/dev/null || echo '{}'; "
        "safety check --output json 2>/dev/null || echo '[]'",
        cwd=project_dir,
        timeout=60,
    )
    return {
        "success": True,
        "output": result.get("output", ""),
        "message": "Security scan complete. Review findings above.",
    }
