import asyncio
import os
import tempfile
import subprocess
import time
import shutil
import logging
from pathlib import Path
from config import SANDBOX_DIR, CODE_EXECUTION_TIMEOUT, SANDBOX_LANGUAGES

logger = logging.getLogger(__name__)

MAX_OUTPUT_LEN = 8000


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT_LEN:
        half = MAX_OUTPUT_LEN // 2
        return text[:half] + "\n\n... [output truncated] ...\n\n" + text[-half:]
    return text


async def execute_code(code: str, language: str = "python", project_dir: str = None) -> dict:
    lang = language.lower().strip()
    if lang not in SANDBOX_LANGUAGES:
        return {"success": False, "output": f"Unsupported language: {lang}. Supported: {list(SANDBOX_LANGUAGES.keys())}"}

    cfg = SANDBOX_LANGUAGES[lang]
    work_dir = Path(project_dir) if project_dir else SANDBOX_DIR
    work_dir.mkdir(parents=True, exist_ok=True)

    suffix = cfg["ext"]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, dir=work_dir, delete=False, prefix="exec_"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        start = time.time()
        if lang == "python":
            cmd = ["python3", tmp_path]
        elif lang in ("javascript", "node"):
            cmd = ["node", tmp_path]
        elif lang == "typescript":
            cmd = ["npx", "--yes", "ts-node", tmp_path]
        elif lang == "bash":
            cmd = ["bash", tmp_path]
        elif lang == "go":
            cmd = ["go", "run", tmp_path]
        else:
            cmd = cfg["cmd"].split() + [tmp_path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_dir),
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CODE_EXECUTION_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "output": f"Execution timed out after {CODE_EXECUTION_TIMEOUT}s",
                "elapsed": CODE_EXECUTION_TIMEOUT,
            }

        elapsed = round(time.time() - start, 2)
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        combined = (out + ("\n[stderr]\n" + err if err.strip() else "")).strip()

        return {
            "success": proc.returncode == 0,
            "output": _truncate(combined) or "(no output)",
            "return_code": proc.returncode,
            "elapsed": elapsed,
            "language": lang,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


async def execute_shell(command: str, cwd: str = None, timeout: int = 60) -> dict:
    safe_cwd = str(Path(cwd) if cwd else SANDBOX_DIR)
    try:
        start = time.time()
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=safe_cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"success": False, "output": f"Command timed out after {timeout}s"}

        elapsed = round(time.time() - start, 2)
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        combined = (out + ("\n[stderr]\n" + err if err.strip() else "")).strip()

        return {
            "success": proc.returncode == 0,
            "output": _truncate(combined) or "(no output)",
            "return_code": proc.returncode,
            "elapsed": elapsed,
        }
    except Exception as e:
        return {"success": False, "output": f"Shell error: {e}"}


async def install_package(packages: str | list[str], language: str = "python", project_dir: str = None) -> dict:
    if isinstance(packages, str):
        packages = [p.strip() for p in packages.split() if p.strip()]

    cwd = project_dir or str(SANDBOX_DIR)

    if language == "python":
        cmd = f"pip install {' '.join(packages)} --quiet"
    elif language in ("javascript", "typescript", "node"):
        cmd = f"npm install {' '.join(packages)}"
    elif language == "go":
        cmd = f"go get {' '.join(packages)}"
    else:
        return {"success": False, "output": f"Package install not supported for {language}"}

    result = await execute_shell(cmd, cwd=cwd, timeout=120)
    if result["success"]:
        result["output"] = f"Installed: {', '.join(packages)}\n" + result["output"]
    return result


async def run_tests(test_file: str = None, language: str = "python", project_dir: str = None) -> dict:
    cwd = project_dir or str(SANDBOX_DIR)
    if language == "python":
        if test_file:
            cmd = f"python3 -m pytest {test_file} -v --tb=short 2>&1"
        else:
            cmd = "python3 -m pytest . -v --tb=short 2>&1"
    elif language in ("javascript", "typescript"):
        cmd = "npm test 2>&1"
    elif language == "go":
        cmd = "go test ./... -v 2>&1"
    else:
        cmd = f"python3 -m pytest {test_file or '.'} -v 2>&1"

    return await execute_shell(cmd, cwd=cwd, timeout=120)
