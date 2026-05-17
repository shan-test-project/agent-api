import os
import shutil
import zipfile
import json
import re
import logging
from pathlib import Path
from typing import Optional
from config import SANDBOX_DIR, UPLOADS_DIR, MAX_FILE_SIZE_MB, ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)


def _resolve_path(path: str, base_dir: str = None) -> Path:
    base = Path(base_dir) if base_dir else SANDBOX_DIR
    resolved = (base / path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError(f"Path traversal detected: {path}")
    return resolved


async def read_file(path: str, project_dir: str = None) -> dict:
    try:
        p = _resolve_path(path, project_dir)
        if not p.exists():
            return {"success": False, "content": f"File not found: {path}"}
        if p.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            return {"success": False, "content": f"File too large (>{MAX_FILE_SIZE_MB}MB)"}
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"success": True, "content": content, "path": str(p), "size": len(content)}
    except ValueError as e:
        return {"success": False, "content": str(e)}
    except Exception as e:
        return {"success": False, "content": f"Read error: {e}"}


async def write_file(path: str, content: str, project_dir: str = None) -> dict:
    try:
        p = _resolve_path(path, project_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p), "size": len(content)}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}"}


async def list_files(directory: str = ".", project_dir: str = None, recursive: bool = True) -> dict:
    try:
        base = Path(project_dir) if project_dir else SANDBOX_DIR
        target = (base / directory).resolve()
        if not target.exists():
            return {"success": True, "files": [], "count": 0}

        files = []
        if recursive:
            for p in sorted(target.rglob("*")):
                rel = str(p.relative_to(target))
                if any(part.startswith(".") for part in p.parts[-3:]) and ".git" in str(p):
                    continue
                if p.is_file():
                    files.append({"path": rel, "size": p.stat().st_size, "type": "file"})
                elif p.is_dir():
                    files.append({"path": rel + "/", "type": "dir"})
        else:
            for p in sorted(target.iterdir()):
                rel = p.name
                if p.is_file():
                    files.append({"path": rel, "size": p.stat().st_size, "type": "file"})
                elif p.is_dir():
                    files.append({"path": rel + "/", "type": "dir"})

        return {"success": True, "files": files[:200], "count": len(files)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def search_code(query: str, directory: str = ".", project_dir: str = None,
                      file_extensions: list[str] = None) -> dict:
    try:
        base = Path(project_dir) if project_dir else SANDBOX_DIR
        target = (base / directory).resolve()
        results = []
        pattern = re.compile(query, re.IGNORECASE)
        exts = file_extensions or [".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c"]

        for p in target.rglob("*"):
            if p.is_file() and p.suffix in exts:
                try:
                    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    for i, line in enumerate(lines, 1):
                        if pattern.search(line):
                            results.append({
                                "file": str(p.relative_to(target)),
                                "line": i,
                                "content": line.strip(),
                            })
                            if len(results) >= 50:
                                break
                except Exception:
                    continue
            if len(results) >= 50:
                break

        return {"success": True, "results": results, "count": len(results), "query": query}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_project_structure(structure: dict, project_dir: str) -> dict:
    created = []
    try:
        base = Path(project_dir)
        base.mkdir(parents=True, exist_ok=True)

        def _create(d: dict, current: Path):
            for name, value in d.items():
                p = current / name
                if isinstance(value, dict):
                    p.mkdir(parents=True, exist_ok=True)
                    _create(value, p)
                    created.append(f"dir: {p.relative_to(base)}")
                elif isinstance(value, str):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(value, encoding="utf-8")
                    created.append(f"file: {p.relative_to(base)}")
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text("", encoding="utf-8")
                    created.append(f"file: {p.relative_to(base)}")

        _create(structure, base)
        return {"success": True, "created": created, "count": len(created)}
    except Exception as e:
        return {"success": False, "error": str(e), "created": created}


async def extract_archive(archive_path: str, dest_dir: str = None) -> dict:
    try:
        src = Path(archive_path)
        dest = Path(dest_dir) if dest_dir else src.parent / src.stem
        dest.mkdir(parents=True, exist_ok=True)

        if archive_path.endswith(".zip"):
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest)
            return {"success": True, "extracted_to": str(dest)}
        elif archive_path.endswith((".tar.gz", ".tgz")):
            import tarfile
            with tarfile.open(src, "r:gz") as tf:
                tf.extractall(dest)
            return {"success": True, "extracted_to": str(dest)}
        else:
            return {"success": False, "error": "Unsupported archive format"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_project_summary(project_dir: str) -> str:
    files_result = await list_files(".", project_dir, recursive=True)
    if not files_result["success"]:
        return "Could not read project"

    file_list = [f["path"] for f in files_result["files"] if f.get("type") == "file"]
    summary = f"Project has {len(file_list)} files:\n"
    summary += "\n".join(file_list[:40])
    if len(file_list) > 40:
        summary += f"\n... and {len(file_list) - 40} more files"
    return summary
