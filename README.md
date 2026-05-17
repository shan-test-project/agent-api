# ⚡ ReplitAI — Powerful AI Coding Assistant Telegram Bot

A fully autonomous AI coding agent for Telegram, built with multi-agent architecture, long-term memory, and full developer tooling.

## Features

### 🤖 Multi-Agent System
- **Planner** — Architecture, project design, multi-step task decomposition
- **Coder** — Code generation in 10+ languages, complete implementations
- **Tester** — Unit/integration test writing, auto-fix failing tests
- **Reviewer** — Security, performance, and code quality analysis
- **Deployer** — Dockerfile, CI/CD, multi-platform deployment
- **Researcher** — Web search, documentation lookup, GitHub search
- **Self-Improvement** — Agent reviews its own code and applies fixes

### 💻 Full Developer Tooling
- Sandboxed code execution (Python, JS/TS, Go, Rust, Bash, Java)
- Terminal access via WebApp with real-time WebSocket output
- Multi-file project management with context switching
- GitHub: clone, commit, push, PRs, create repos, list issues

### 🧠 Long-Term Memory
- ChromaDB vector store for persistent memory
- Learns your coding style and preferences
- Remembers past projects and decisions
- Semantic search across memories

### 📸 Vision & Media
- Code screenshot analysis (extracts code, spots errors)
- Error screenshot diagnosis with step-by-step fixes
- Architecture diagram interpretation → code generation
- UI mockup → HTML/CSS generation
- Voice message transcription (Whisper via Groq)

### 🚀 Deployment Support
- Auto-generate Dockerfile + docker-compose + GitHub Actions
- One-command deploy to Railway, Fly.io, Render, HuggingFace, Vercel
- Security scanning with Bandit + Safety

### 🌐 Telegram WebApp
- Full chat interface with markdown rendering
- Real-time terminal emulator (xterm.js)
- File browser with syntax highlighting
- Project switcher
- Quick action buttons

---

## Quick Start

### 1. Get your API keys

| Key | Where to get |
|-----|-------------|
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram → /newbot |
| `GROQ_API_KEY` | console.groq.com → API Keys (free!) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT (repo scope) |

### 2. Install

```bash
cd telegram-bot
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your keys
```

### 4. Run

```bash
python main.py
```

Or run both bot + webapp:
```bash
python webapp/server.py &
python main.py
```

---

## Docker Deploy

```bash
docker-compose up -d
```

---

## Deploy to Railway (recommended, free tier)

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Set environment variables in Railway dashboard.

---

## Deploy to Fly.io

```bash
curl -L https://fly.io/install.sh | sh
flyctl auth login
flyctl launch
flyctl deploy
```

---

## Deploy to Render

1. Push to GitHub
2. render.com → New → Web Service → Connect repo
3. Build: `pip install -r requirements.txt`
4. Start: `python main.py`
5. Add environment variables

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + quick actions |
| `/help` | Full command reference |
| `/new <name>` | Create a new project |
| `/projects` | List all projects |
| `/switch <name>` | Switch active project |
| `/run` | Run the current project |
| `/test` | Run tests + show results |
| `/review` | AI code review |
| `/deploy` | Deploy menu |
| `/docker` | Generate Dockerfile |
| `/security` | Security scan |
| `/repos` | List GitHub repos |
| `/clone <url>` | Clone a repository |
| `/push <msg>` | Commit and push |
| `/memory` | View AI memory |
| `/history` | Chat history |
| `/reset` | Clear conversation |
| `/improve` | AI self-improvement (admin) |
| `/status` | System status |
| `/webapp` | Open WebApp |

---

## Architecture

```
telegram-bot/
├── main.py              # Telegram bot + all handlers
├── config.py            # Configuration & constants
├── model_router.py      # Smart AI routing (Groq)
├── agent/
│   ├── core.py          # Multi-agent orchestrator (LangGraph-style)
│   ├── prompts.py       # System prompts for each agent
│   └── agents/
│       └── base.py      # Agent base class with tool execution
├── tools/
│   ├── terminal.py      # Sandboxed code execution
│   ├── file_manager.py  # File operations (path-safe)
│   ├── git_tools.py     # GitHub integration (PyGithub)
│   ├── web_search.py    # DuckDuckGo + GitHub search
│   ├── vision.py        # Image analysis (Groq vision)
│   └── deploy_tools.py  # Multi-platform deployment
├── memory/
│   └── vector_store.py  # ChromaDB persistent memory
├── database/
│   └── models.py        # SQLAlchemy async models
└── webapp/
    ├── server.py        # FastAPI backend
    ├── index.html       # WebApp UI
    └── static/          # CSS + JS
```

## AI Models Used (All Free via Groq)

| Model | Task |
|-------|------|
| `llama-3.3-70b-versatile` | Code generation, complex reasoning |
| `llama-3.2-90b-vision-preview` | Image/screenshot analysis |
| `llama-3.2-11b-vision-preview` | Fast vision tasks |
| `llama-3.1-8b-instant` | Quick questions, routing |
| `whisper-large-v3` | Voice transcription |

All models are **completely free** on Groq's API with generous rate limits.

## Security

- All code execution is sandboxed in isolated temp files
- Path traversal protection in file operations
- No execution of untrusted system commands without explicit user request
- GitHub tokens stored as env vars, never in code
- Rate limiting via Telegram's built-in throttling

## Environment Variables

See `.env.example` for full reference.
