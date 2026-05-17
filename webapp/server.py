"""FastAPI WebApp server for ReplitAI Telegram WebApp"""
import asyncio
import json
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="ReplitAI WebApp", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEBAPP_DIR = Path(__file__).parent
STATIC_DIR = WEBAPP_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

active_connections: dict[str, WebSocket] = {}


class ChatRequest(BaseModel):
    message: str
    user_id: int = 0
    project: str = "default"


class CommandRequest(BaseModel):
    command: str
    args: list = []
    user_id: int = 0
    project: str = "default"


@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = WEBAPP_DIR / "index.html"
    return HTMLResponse(html_file.read_text())


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from agent.core import run_agent
        from database.models import get_chat_history, save_message, get_or_create_settings
        from config import SANDBOX_DIR

        settings = await get_or_create_settings(req.user_id)
        history = await get_chat_history(req.user_id, req.project, 20)
        project_dir = str(SANDBOX_DIR / f"user_{req.user_id}" / req.project)

        response = await run_agent(req.message, req.user_id, history, project_dir, req.project)
        await save_message(req.user_id, "user", req.message, req.project)
        await save_message(req.user_id, "assistant", response, req.project)
        return {"success": True, "response": response}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return {"success": False, "response": str(e)}


@app.post("/api/execute")
async def execute(req: CommandRequest):
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tools.terminal import execute_code, execute_shell
        from config import SANDBOX_DIR

        project_dir = str(SANDBOX_DIR / f"user_{req.user_id}" / req.project)
        if req.command == "run_code":
            code = req.args[0] if req.args else ""
            lang = req.args[1] if len(req.args) > 1 else "python"
            result = await execute_code(code, lang, project_dir)
        elif req.command == "shell":
            cmd = req.args[0] if req.args else ""
            result = await execute_shell(cmd, cwd=project_dir)
        else:
            result = {"success": False, "output": f"Unknown command: {req.command}"}
        return result
    except Exception as e:
        return {"success": False, "output": str(e)}


@app.get("/api/files/{user_id}/{project}")
async def list_files_api(user_id: int, project: str):
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tools.file_manager import list_files
        from config import SANDBOX_DIR
        project_dir = str(SANDBOX_DIR / f"user_{user_id}" / project)
        result = await list_files(".", project_dir, recursive=True)
        return result
    except Exception as e:
        return {"success": False, "files": [], "error": str(e)}


@app.get("/api/file/{user_id}/{project}")
async def read_file_api(user_id: int, project: str, path: str):
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tools.file_manager import read_file
        from config import SANDBOX_DIR
        project_dir = str(SANDBOX_DIR / f"user_{user_id}" / project)
        result = await read_file(path, project_dir)
        return result
    except Exception as e:
        return {"success": False, "content": str(e)}


@app.get("/api/history/{user_id}/{project}")
async def get_history(user_id: int, project: str):
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from database.models import get_chat_history
        history = await get_chat_history(user_id, project, 30)
        return {"success": True, "history": history}
    except Exception as e:
        return {"success": False, "history": [], "error": str(e)}


@app.get("/api/projects/{user_id}")
async def get_projects(user_id: int):
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from database.models import get_user_projects
        projects = await get_user_projects(user_id)
        return {"success": True, "projects": [{"name": p.name, "language": p.language} for p in projects]}
    except Exception as e:
        return {"success": False, "projects": [], "error": str(e)}


@app.websocket("/ws/terminal/{user_id}/{project}")
async def terminal_ws(websocket: WebSocket, user_id: int, project: str):
    await websocket.accept()
    active_connections[f"{user_id}:{project}"] = websocket
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tools.terminal import execute_shell
        from config import SANDBOX_DIR
        project_dir = str(SANDBOX_DIR / f"user_{user_id}" / project)
        Path(project_dir).mkdir(parents=True, exist_ok=True)

        await websocket.send_text(json.dumps({"type": "welcome", "data": f"Connected to project: {project}\n$ "}))

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "command":
                cmd = msg.get("data", "").strip()
                if not cmd:
                    await websocket.send_text(json.dumps({"type": "output", "data": "$ "}))
                    continue
                result = await execute_shell(cmd, cwd=project_dir, timeout=30)
                output = result.get("output", "")
                await websocket.send_text(json.dumps({
                    "type": "output",
                    "data": output + "\n$ ",
                    "success": result.get("success", False),
                }))
    except WebSocketDisconnect:
        active_connections.pop(f"{user_id}:{project}", None)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        active_connections.pop(f"{user_id}:{project}", None)


if __name__ == "__main__":
    import uvicorn
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    port = int(os.getenv("PORT", os.getenv("WEBAPP_PORT", "8080")))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
