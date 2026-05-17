import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
SANDBOX_DIR = BASE_DIR / "sandbox"
SANDBOX_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_DIR.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./replitai.db")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

GROQ_MODELS = {
    "fast": "llama-3.1-8b-instant",
    "balanced": "llama-3.3-70b-versatile",
    "powerful": "llama-3.3-70b-versatile",
    "vision": "llama-3.2-11b-vision-preview",
    "vision_large": "llama-3.2-90b-vision-preview",
}

MODEL_FALLBACK_CHAIN = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "llama-3.1-8b-instant",
]

TASK_MODEL_ROUTING = {
    "quick_question": "fast",
    "code_generation": "powerful",
    "code_review": "powerful",
    "debugging": "powerful",
    "planning": "powerful",
    "testing": "balanced",
    "deployment": "balanced",
    "vision": "vision",
    "general": "balanced",
}

MAX_TOOL_ITERATIONS = 20
MAX_CONTEXT_MESSAGES = 50
CODE_EXECUTION_TIMEOUT = 60
MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = {
    "code": [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".cpp", ".c", ".h",
             ".cs", ".php", ".rb", ".swift", ".kt", ".sh", ".bash", ".sql", ".html", ".css",
             ".json", ".yaml", ".yml", ".toml", ".env", ".md", ".txt", ".xml"],
    "images": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"],
    "archives": [".zip", ".tar", ".gz", ".tar.gz", ".rar", ".7z"],
    "docs": [".pdf", ".docx", ".xlsx", ".csv"],
}

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

SANDBOX_LANGUAGES = {
    "python": {"cmd": "python3", "ext": ".py", "image": "python:3.11-slim"},
    "javascript": {"cmd": "node", "ext": ".js", "image": "node:20-slim"},
    "typescript": {"cmd": "npx ts-node", "ext": ".ts", "image": "node:20-slim"},
    "bash": {"cmd": "bash", "ext": ".sh", "image": "ubuntu:22.04"},
    "go": {"cmd": "go run", "ext": ".go", "image": "golang:1.21-slim"},
    "rust": {"cmd": "rustc -o /tmp/out && /tmp/out", "ext": ".rs", "image": "rust:slim"},
}

DEPLOY_PLATFORMS = {
    "railway": {"url": "https://railway.app", "cli": "railway"},
    "fly": {"url": "https://fly.io", "cli": "flyctl"},
    "render": {"url": "https://render.com", "api": "https://api.render.com/v1"},
    "huggingface": {"url": "https://huggingface.co/spaces", "cli": "huggingface-cli"},
    "vercel": {"url": "https://vercel.com", "cli": "vercel"},
    "replit": {"url": "https://replit.com", "cli": None},
}

BOT_COMMANDS = [
    ("start", "Start the bot and show welcome"),
    ("help", "Show all commands and features"),
    ("new", "Create a new project workspace"),
    ("projects", "List all your projects"),
    ("switch", "Switch between projects"),
    ("run", "Run current project"),
    ("test", "Run tests"),
    ("deploy", "Deploy project"),
    ("review", "AI code review"),
    ("history", "Show chat history"),
    ("memory", "Show/clear AI memory"),
    ("upload", "Upload a file"),
    ("github", "GitHub operations"),
    ("reset", "Reset current conversation"),
    ("webapp", "Open the WebApp interface"),
    ("status", "Show system status"),
    ("settings", "Configure bot settings"),
]
