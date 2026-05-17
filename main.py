#!/usr/bin/env python3
"""ReplitAI — Powerful AI Coding Assistant Telegram Bot"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, MenuButtonWebApp, WebAppInfo, ReplyKeyboardMarkup,
    KeyboardButton, InputFile,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

from config import (
    TELEGRAM_BOT_TOKEN, WEBAPP_URL, WEBAPP_PORT, BOT_COMMANDS,
    SANDBOX_DIR, UPLOADS_DIR, ADMIN_IDS,
)
from database.models import (
    init_db, get_chat_history, save_message,
    get_or_create_settings, get_user_projects,
)
from agent.core import run_agent, self_improve
from tools.vision import analyze_image, analyze_code_screenshot, analyze_error_screenshot
from tools.git_tools import git_list_repos, git_clone, git_push_project_to_github
from tools.deploy_tools import deploy_to_platform, scan_security
from memory.vector_store import memory_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

THINKING_EMOJI = "🧠"
CODING_EMOJI = "💻"

TOOL_LABELS = {
    "execute_code":          "⚙️ Running code...",
    "execute_shell":         "🖥️ Running shell command...",
    "install_package":       "📦 Installing packages...",
    "write_file":            "📝 Writing file...",
    "read_file":             "📖 Reading file...",
    "list_files":            "📂 Listing files...",
    "search_code":           "🔍 Searching codebase...",
    "run_tests":             "🧪 Running tests...",
    "web_search":            "🌐 Searching the web...",
    "fetch_url":             "🌐 Fetching page...",
    "git_clone":             "📥 Cloning repository...",
    "git_commit_push":       "📤 Pushing to GitHub...",
    "git_create_repo":       "🗂️ Creating GitHub repo...",
    "git_list_repos":        "📋 Listing repos...",
    "generate_dockerfile":   "🐳 Generating Dockerfile...",
    "deploy_to_platform":    "🚀 Preparing deployment...",
    "save_memory":           "💾 Saving to memory...",
    "create_project_structure": "🏗️ Creating project structure...",
}


async def _send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)


async def _continuous_typing(chat_id: int, context: ContextTypes.DEFAULT_TYPE, stop_event: asyncio.Event):
    """Keep sending TYPING action every 4s so Telegram shows it next to the bot name."""
    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=4)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return parts


async def _reply(update: Update, text: str, parse_mode: str = ParseMode.MARKDOWN,
                 keyboard=None, reply_to: bool = False):
    parts = _split_message(text)
    reply_markup = keyboard
    for i, part in enumerate(parts):
        try:
            if reply_to and i == 0:
                await update.message.reply_text(part, parse_mode=parse_mode, reply_markup=reply_markup)
            else:
                await update.effective_chat.send_message(part, parse_mode=parse_mode,
                                                         reply_markup=reply_markup)
        except Exception:
            try:
                await update.effective_chat.send_message(part, parse_mode=None, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Send message error: {e}")


def _action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Run", callback_data="action:run"),
            InlineKeyboardButton("🧪 Test", callback_data="action:test"),
            InlineKeyboardButton("🔍 Review", callback_data="action:review"),
        ],
        [
            InlineKeyboardButton("🚀 Deploy", callback_data="action:deploy"),
            InlineKeyboardButton("📁 Files", callback_data="action:files"),
            InlineKeyboardButton("🔒 Security", callback_data="action:security"),
        ],
        [
            InlineKeyboardButton("💾 Save to GitHub", callback_data="action:github_push"),
            InlineKeyboardButton("🧹 Clear History", callback_data="action:clear"),
        ],
    ])


def _deploy_keyboard() -> InlineKeyboardMarkup:
    platforms = ["railway", "fly", "render", "huggingface", "vercel", "replit"]
    rows = []
    for i in range(0, len(platforms), 3):
        row = [InlineKeyboardButton(p.capitalize(), callback_data=f"deploy:{p}") for p in platforms[i:i+3]]
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await get_or_create_settings(user.id, user.username or "")
    text = (
        f"👋 Welcome to **ReplitAI**, {user.first_name}!\n\n"
        "I'm your AI coding agent — think of me as a senior dev, DevOps engineer, "
        "and AI researcher in your pocket.\n\n"
        "**What I can do:**\n"
        "• 💻 Write, run, test & debug code in any language\n"
        "• 🔧 Full terminal access with sandboxed execution\n"
        "• 🐙 GitHub: clone, commit, push, create PRs\n"
        "• 📸 Analyze code screenshots, error messages, diagrams\n"
        "• 🚀 Deploy to Railway, Fly.io, Render, HuggingFace, Vercel\n"
        "• 🧠 Long-term memory — I learn your style\n"
        "• 🤖 Multi-agent system: Planner→Coder→Tester→Reviewer→Deployer\n"
        "• 📦 Upload any file (code, zip, PDF, images)\n"
        "• 🎙️ Voice messages supported\n\n"
        "**Quick start:**\n"
        "`Build a FastAPI REST API with PostgreSQL`\n"
        "`Clone github.com/user/repo and add authentication`\n"
        "`Debug this error: [paste screenshot]`\n\n"
        "Use /help to see all commands."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Help", callback_data="show:help"),
         InlineKeyboardButton("📁 My Projects", callback_data="show:projects")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="show:settings"),
         InlineKeyboardButton("📊 Status", callback_data="show:status")],
    ])
    if WEBAPP_URL:
        keyboard.inline_keyboard.insert(0, [
            InlineKeyboardButton("🌐 Open WebApp", web_app=WebAppInfo(url=WEBAPP_URL))
        ])
    await _reply(update, text, keyboard=keyboard)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "**🤖 ReplitAI — Command Reference**\n\n"
        "**Project Management:**\n"
        "/new `<name>` — Create a new project\n"
        "/projects — List all your projects\n"
        "/switch `<name>` — Switch active project\n"
        "/status — Current project status\n\n"
        "**Coding:**\n"
        "/run — Run the current project\n"
        "/test — Run tests\n"
        "/review — AI code review\n"
        "/fix — Auto-fix last error\n\n"
        "**GitHub:**\n"
        "/github — GitHub operations menu\n"
        "/clone `<url>` — Clone a repo\n"
        "/push `<message>` — Commit and push\n"
        "/repos — List your repos\n\n"
        "**Deploy:**\n"
        "/deploy — Deploy your project\n"
        "/docker — Generate Dockerfile\n"
        "/security — Security scan\n\n"
        "**Memory & Settings:**\n"
        "/memory — View/clear AI memory\n"
        "/history — Chat history\n"
        "/reset — Reset conversation\n"
        "/settings — Configure preferences\n\n"
        "**Self-Improvement:**\n"
        "/improve — AI reviews its own code\n\n"
        "**Send me any message to start coding!**\n"
        "Also accepts: photos, voice messages, files (zip, code, docs)"
    )
    await _reply(update, text)


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await _reply(update, "Usage: /new `<project-name>`\nExample: /new my-fastapi-app")
        return

    project_name = args[0].lower().replace(" ", "-")
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / project_name)
    Path(project_dir).mkdir(parents=True, exist_ok=True)

    from database.models import AsyncSessionLocal, Project
    async with AsyncSessionLocal() as session:
        proj = Project(user_id=user_id, name=project_name, local_path=project_dir)
        session.add(proj)
        await session.commit()

    settings = await get_or_create_settings(user_id)
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(
                __import__("database.models", fromlist=["UserSettings"]).UserSettings
            ).where(__import__("database.models", fromlist=["UserSettings"]).UserSettings.user_id == user_id)
        )
        s = result.scalar_one_or_none()
        if s:
            s.active_project = project_name
            await session.commit()

    await _reply(update, f"✅ Project **{project_name}** created!\nDirectory: `{project_dir}`\n\nNow tell me what to build!")


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    projects = await get_user_projects(user_id)
    if not projects:
        await _reply(update, "No projects yet. Use /new `<name>` to create one!")
        return
    lines = ["**📁 Your Projects:**\n"]
    buttons = []
    for p in projects[:10]:
        lines.append(f"• **{p.name}** — {p.language} — {p.updated_at.strftime('%Y-%m-%d')}")
        buttons.append([InlineKeyboardButton(f"▶️ {p.name}", callback_data=f"switch:{p.name}")])
    await _reply(update, "\n".join(lines), keyboard=InlineKeyboardMarkup(buttons))


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    await _send_typing(update, context)
    history = await get_chat_history(user_id, settings.active_project, 10)
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    status_msg = await update.effective_chat.send_message("▶️ Running your project...")

    async def status_cb(msg: str):
        try:
            await status_msg.edit_text(msg)
        except Exception:
            pass

    response = await run_agent(
        "Run the project. Show the output.",
        user_id, history, project_dir, settings.active_project,
        status_callback=status_cb,
    )
    await status_msg.delete()
    await _reply(update, response, keyboard=_action_keyboard())
    await save_message(user_id, "user", "/run", settings.active_project)
    await save_message(user_id, "assistant", response, settings.active_project)


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    await _send_typing(update, context)
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    history = await get_chat_history(user_id, settings.active_project, 10)
    status_msg = await update.effective_chat.send_message("🧪 Running tests...")

    async def status_cb(msg):
        try:
            await status_msg.edit_text(msg)
        except Exception:
            pass

    response = await run_agent(
        "Run the test suite. Show results, coverage, and fix any failures.",
        user_id, history, project_dir, settings.active_project,
        force_agent="TESTER", status_callback=status_cb,
    )
    await status_msg.delete()
    await _reply(update, response, keyboard=_action_keyboard())


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    await _send_typing(update, context)
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    history = await get_chat_history(user_id, settings.active_project, 5)
    status_msg = await update.effective_chat.send_message("🔍 Reviewing your code...")

    async def status_cb(msg):
        try:
            await status_msg.edit_text(msg)
        except Exception:
            pass

    response = await run_agent(
        "Do a comprehensive code review of the project. Check quality, security, performance, and best practices.",
        user_id, history, project_dir, settings.active_project,
        force_agent="REVIEWER", status_callback=status_cb,
    )
    await status_msg.delete()
    await _reply(update, response, keyboard=_action_keyboard())


async def cmd_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update,
        "🚀 **Deploy your project**\nChoose a platform:",
        keyboard=_deploy_keyboard(),
    )


async def cmd_docker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    from tools.deploy_tools import generate_dockerfile
    result = await generate_dockerfile("python", project_dir)
    await _reply(update, f"🐳 Docker files generated!\n\n```\n{result['dockerfile']}\n```")


async def cmd_security(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    await _send_typing(update, context)
    msg = await update.effective_chat.send_message("🔒 Running security scan...")
    result = await scan_security(project_dir)
    await msg.delete()
    await _reply(update, f"🔒 **Security Scan Results:**\n\n```\n{result['output'][:3000]}\n```")


async def cmd_repos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_typing(update, context)
    result = await git_list_repos(15)
    if not result["success"] or not result["repos"]:
        await _reply(update, "No repos found or GITHUB_TOKEN not set.")
        return
    lines = ["**🐙 Your GitHub Repos:**\n"]
    buttons = []
    for r in result["repos"]:
        lang = f" [{r['language']}]" if r.get("language") else ""
        lines.append(f"• **{r['name']}**{lang} ⭐{r.get('stars',0)}")
        buttons.append([InlineKeyboardButton(f"📥 Clone {r['name'].split('/')[-1]}", callback_data=f"clone:{r['name']}")])
    await _reply(update, "\n".join(lines), keyboard=InlineKeyboardMarkup(buttons[:8]))


async def cmd_clone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await _reply(update, "Usage: /clone `<repo-url>`")
        return
    url = context.args[0]
    await _send_typing(update, context)
    msg = await update.effective_chat.send_message(f"📥 Cloning `{url}`...")
    result = await git_clone(url)
    await msg.delete()
    if result["success"]:
        await _reply(update, f"✅ Cloned to `{result.get('local_path')}`")
    else:
        await _reply(update, f"❌ Clone failed:\n```\n{result['output']}\n```")


async def cmd_push(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    message = " ".join(context.args) if context.args else "Update from ReplitAI"
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    msg = await update.effective_chat.send_message("📤 Pushing to GitHub...")
    from tools.git_tools import git_commit_push
    result = await git_commit_push(project_dir, message)
    await msg.delete()
    status = "✅" if result["success"] else "❌"
    await _reply(update, f"{status} `{result['output']}`")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    mem = memory_store(user_id)
    recent = await mem.get_recent(10)
    if not recent:
        await _reply(update, "🧠 No memories stored yet. I'll remember important things as we work together!")
        return
    lines = ["**🧠 Your AI Memory:**\n"]
    for m in recent:
        content = m["content"][:100] + "..." if len(m["content"]) > 100 else m["content"]
        meta = m.get("metadata", {})
        lines.append(f"• [{meta.get('type','general')}] {content}")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Clear Memory", callback_data="memory:clear")]])
    await _reply(update, "\n".join(lines), keyboard=keyboard)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    history = await get_chat_history(user_id, settings.active_project, 10)
    if not history:
        await _reply(update, "No chat history yet.")
        return
    lines = [f"**💬 Recent History ({settings.active_project}):**\n"]
    for msg in history[-10:]:
        role = "You" if msg["role"] == "user" else "AI"
        content = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
        lines.append(f"**{role}:** {content}")
    await _reply(update, "\n".join(lines))


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    from database.models import AsyncSessionLocal, Message
    from sqlalchemy import delete
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(Message).where(
                Message.user_id == user_id,
                Message.project_name == settings.active_project,
            )
        )
        await session.commit()
    await _reply(update, f"✅ Conversation reset for project **{settings.active_project}**.")


async def cmd_improve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS and ADMIN_IDS:
        await _reply(update, "⛔ Admin only command.")
        return
    msg = await update.effective_chat.send_message("🤖 Analyzing my own code for improvements...")
    result = await self_improve(update.effective_user.id)
    await msg.delete()
    await _reply(update, f"**🔄 Self-Improvement Analysis:**\n\n{result}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await get_or_create_settings(user_id)
    projects = await get_user_projects(user_id)
    mem = memory_store(user_id)
    recent_memories = await mem.get_recent(3)
    from model_router import router as mr
    stats = mr.get_stats()
    total_requests = sum(v.get("requests", 0) for v in stats["usage"].values())
    text = (
        f"**📊 ReplitAI Status**\n\n"
        f"👤 User: {update.effective_user.first_name} (#{user_id})\n"
        f"📁 Active project: **{settings.active_project}**\n"
        f"📦 Total projects: {len(projects)}\n"
        f"🧠 Memories stored: {len(recent_memories)}+\n"
        f"🤖 AI requests made: {total_requests}\n"
        f"🔑 GitHub: {'✅' if os.getenv('GITHUB_TOKEN') else '❌'}\n"
        f"🌐 WebApp: {'✅' if WEBAPP_URL else '❌'}\n"
        f"💾 Database: ✅\n"
    )
    await _reply(update, text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    if not text:
        return

    status_msg = None
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(
        _continuous_typing(update.effective_chat.id, context, stop_typing)
    )

    try:
        settings = await get_or_create_settings(user.id, user.username or "")
        await save_message(user.id, "user", text, settings.active_project)
        history = await get_chat_history(user.id, settings.active_project, 20)
        project_dir = str(SANDBOX_DIR / f"user_{user.id}" / settings.active_project)

        status_msg = await update.effective_chat.send_message(f"{THINKING_EMOJI} Thinking...")

        async def status_cb(raw: str):
            try:
                # raw is like "🔧 [CODER] using write_file..." — extract tool name
                tool_name = None
                for t in TOOL_LABELS:
                    if t in raw:
                        tool_name = t
                        break
                label = TOOL_LABELS.get(tool_name, raw) if tool_name else raw
                await status_msg.edit_text(label)
            except Exception:
                pass

        response = await run_agent(
            text, user.id, history, project_dir, settings.active_project,
            status_callback=status_cb,
        )
        stop_typing.set()
        try:
            await status_msg.delete()
        except Exception:
            pass
        await save_message(user.id, "assistant", response, settings.active_project)
        await _reply(update, response, keyboard=_action_keyboard(), reply_to=True)

    except Exception as e:
        stop_typing.set()
        logger.error(f"handle_message error: {e}", exc_info=True)
        try:
            if status_msg:
                await status_msg.delete()
        except Exception:
            pass
        await update.effective_chat.send_message(
            f"⚠️ Error: `{type(e).__name__}: {str(e)[:300]}`\n\nPlease try again.",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        stop_typing.set()
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await _send_typing(update, context)
    settings = await get_or_create_settings(user.id)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    img_path = str(UPLOADS_DIR / f"{user.id}_{photo.file_id}.jpg")
    await file.download_to_drive(img_path)

    caption = update.message.caption or ""
    status_msg = await update.effective_chat.send_message("👁️ Analyzing image...")

    task = "code" if any(k in caption.lower() for k in ["code", "error", "bug", "fix"]) else \
           "error" if any(k in caption.lower() for k in ["error", "exception", "traceback", "crash"]) else \
           "diagram" if any(k in caption.lower() for k in ["diagram", "architecture", "flow", "design"]) else \
           "general"

    result = await analyze_image(img_path, prompt=caption or None, task=task)
    await status_msg.delete()

    analysis = result.get("analysis", "Could not analyze image.")
    await save_message(user.id, "user", f"[Image: {caption}]", settings.active_project, "image")
    await save_message(user.id, "assistant", analysis, settings.active_project)

    if caption:
        history = await get_chat_history(user.id, settings.active_project, 10)
        project_dir = str(SANDBOX_DIR / f"user_{user.id}" / settings.active_project)
        full_msg = f"Image analysis result:\n{analysis}\n\nUser request: {caption}"
        status2 = await update.effective_chat.send_message(f"{THINKING_EMOJI} Processing your request...")

        async def status_cb(msg):
            try:
                await status2.edit_text(msg)
            except Exception:
                pass

        agent_response = await run_agent(
            full_msg, user.id, history, project_dir, settings.active_project,
            image_path=img_path, status_callback=status_cb,
        )
        await status2.delete()
        await _reply(update, agent_response, keyboard=_action_keyboard())
    else:
        await _reply(update, f"**🖼️ Image Analysis:**\n\n{analysis}", keyboard=_action_keyboard())


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    doc = update.message.document
    settings = await get_or_create_settings(user.id)

    file = await context.bot.get_file(doc.file_id)
    safe_name = doc.file_name.replace("/", "_").replace("..", "_")
    dest = UPLOADS_DIR / f"{user.id}_{safe_name}"
    await file.download_to_drive(str(dest))

    caption = update.message.caption or f"Process this file: {doc.file_name}"
    status_msg = await update.effective_chat.send_message(f"📄 Processing `{doc.file_name}`...")

    if safe_name.endswith((".zip", ".tar.gz", ".tgz")):
        from tools.file_manager import extract_archive
        project_dir = str(SANDBOX_DIR / f"user_{user.id}" / settings.active_project)
        result = await extract_archive(str(dest), project_dir)
        msg = f"📦 Archive extracted to project directory.\n\n{result.get('extracted_to','')}"
        await status_msg.edit_text(msg)
        history = await get_chat_history(user.id, settings.active_project, 10)

        async def status_cb(m):
            try:
                await status_msg.edit_text(m)
            except Exception:
                pass

        response = await run_agent(
            f"I uploaded a zip archive. {caption}",
            user.id, history, project_dir, settings.active_project,
            status_callback=status_cb,
        )
        await status_msg.delete()
        await _reply(update, response, keyboard=_action_keyboard())
        return

    try:
        content = dest.read_text(encoding="utf-8", errors="replace")[:8000]
    except Exception:
        content = f"[Binary file: {doc.file_name}]"

    history = await get_chat_history(user.id, settings.active_project, 10)
    project_dir = str(SANDBOX_DIR / f"user_{user.id}" / settings.active_project)

    full_msg = f"File uploaded: {doc.file_name}\nContent:\n```\n{content}\n```\n\nUser request: {caption}"

    async def status_cb(m):
        try:
            await status_msg.edit_text(m)
        except Exception:
            pass

    response = await run_agent(
        full_msg, user.id, history, project_dir, settings.active_project,
        status_callback=status_cb,
    )
    await status_msg.delete()
    await _reply(update, response, keyboard=_action_keyboard())


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await _send_typing(update, context)
    settings = await get_or_create_settings(user.id)

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    audio_path = str(UPLOADS_DIR / f"{user.id}_{voice.file_id}.ogg")
    await file.download_to_drive(audio_path)

    status_msg = await update.effective_chat.send_message("🎙️ Transcribing voice message...")
    try:
        from model_router import router as mr
        transcription = await mr.transcribe_audio(audio_path)
        await status_msg.edit_text(f"🎙️ Transcribed: _{transcription}_\n\n{THINKING_EMOJI} Processing...")
    except Exception as e:
        await status_msg.edit_text(f"❌ Transcription failed: {e}. Please type your message instead.")
        return

    history = await get_chat_history(user.id, settings.active_project, 20)
    project_dir = str(SANDBOX_DIR / f"user_{user.id}" / settings.active_project)

    async def status_cb(msg):
        try:
            await status_msg.edit_text(msg)
        except Exception:
            pass

    response = await run_agent(
        transcription, user.id, history, project_dir, settings.active_project,
        voice_text=transcription, status_callback=status_cb,
    )
    await status_msg.delete()
    await save_message(user.id, "user", f"[Voice]: {transcription}", settings.active_project, "voice")
    await save_message(user.id, "assistant", response, settings.active_project)
    await _reply(update, f"**🎙️ You said:** _{transcription}_\n\n{response}", keyboard=_action_keyboard())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    settings = await get_or_create_settings(user_id)
    project_dir = str(SANDBOX_DIR / f"user_{user_id}" / settings.active_project)
    history = await get_chat_history(user_id, settings.active_project, 10)

    if data == "show:help":
        await cmd_help(update, context)
    elif data == "show:projects":
        await cmd_projects(update, context)
    elif data == "show:status":
        await cmd_status(update, context)
    elif data == "memory:clear":
        mem = memory_store(user_id)
        await mem.clear()
        await query.edit_message_text("🧠 Memory cleared!")
    elif data == "action:run":
        msg = await query.edit_message_text("▶️ Running...")
        response = await run_agent("Run the project and show output.", user_id, history, project_dir, settings.active_project)
        await msg.edit_text(response[:4000])
    elif data == "action:test":
        msg = await query.edit_message_text("🧪 Running tests...")
        response = await run_agent("Run all tests.", user_id, history, project_dir, settings.active_project, force_agent="TESTER")
        await msg.edit_text(response[:4000])
    elif data == "action:review":
        msg = await query.edit_message_text("🔍 Reviewing code...")
        response = await run_agent("Review the code.", user_id, history, project_dir, settings.active_project, force_agent="REVIEWER")
        await msg.edit_text(response[:4000])
    elif data == "action:deploy":
        await query.edit_message_text("🚀 Choose platform:", reply_markup=_deploy_keyboard())
    elif data == "action:files":
        from tools.file_manager import list_files
        result = await list_files(".", project_dir)
        files = result.get("files", [])
        text = "📁 **Project files:**\n" + "\n".join(f"  `{f['path']}`" for f in files[:30])
        await query.edit_message_text(text[:4000], parse_mode=ParseMode.MARKDOWN)
    elif data == "action:security":
        msg = await query.edit_message_text("🔒 Scanning...")
        result = await scan_security(project_dir)
        await msg.edit_text(f"🔒 **Security Scan:**\n```\n{result['output'][:3500]}\n```", parse_mode=ParseMode.MARKDOWN)
    elif data == "action:github_push":
        repo_name = f"replitai-{settings.active_project}"
        msg = await query.edit_message_text(f"📤 Pushing to GitHub as `{repo_name}`...")
        result = await git_push_project_to_github(project_dir, repo_name)
        status = "✅" if result["success"] else "❌"
        await msg.edit_text(f"{status} {result['output']}")
    elif data == "action:clear":
        from database.models import AsyncSessionLocal, Message
        from sqlalchemy import delete
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Message).where(Message.user_id == user_id, Message.project_name == settings.active_project)
            )
            await session.commit()
        await query.edit_message_text("✅ Chat history cleared!")
    elif data.startswith("deploy:"):
        platform = data.split(":")[1]
        msg = await query.edit_message_text(f"🚀 Getting {platform} deployment instructions...")
        result = await deploy_to_platform(platform, project_dir)
        await msg.edit_text(result["instructions"][:4000], parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("switch:"):
        project_name = data.split(":")[1]
        from database.models import AsyncSessionLocal, UserSettings
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(select(UserSettings).where(UserSettings.user_id == user_id))
            s = result.scalar_one_or_none()
            if s:
                s.active_project = project_name
                await session.commit()
        await query.edit_message_text(f"✅ Switched to project **{project_name}**", parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("clone:"):
        repo_name = data.split(":")[1]
        msg = await query.edit_message_text(f"📥 Cloning {repo_name}...")
        result = await git_clone(f"https://github.com/{repo_name}")
        status = "✅" if result["success"] else "❌"
        await msg.edit_text(f"{status} {result['output'][:3000]}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}", exc_info=context.error)


async def post_init(application: Application):
    await init_db()
    await application.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in BOT_COMMANDS])
    logger.info("ReplitAI Bot initialized ✅")


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("deploy", cmd_deploy))
    app.add_handler(CommandHandler("docker", cmd_docker))
    app.add_handler(CommandHandler("security", cmd_security))
    app.add_handler(CommandHandler("repos", cmd_repos))
    app.add_handler(CommandHandler("clone", cmd_clone))
    app.add_handler(CommandHandler("push", cmd_push))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("improve", cmd_improve))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_error_handler(error_handler)
    return app


if __name__ == "__main__":
    app = build_app()
    logger.info("🤖 ReplitAI Bot starting...")
    app.run_polling(drop_pending_updates=True)
