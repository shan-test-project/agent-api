import os
import asyncio
import logging
from pathlib import Path
from typing import Optional
from config import GITHUB_TOKEN, GITHUB_USERNAME, SANDBOX_DIR

logger = logging.getLogger(__name__)


async def _git(cmd: str, cwd: str = None, timeout: int = 120) -> dict:
    env = {**os.environ}
    if GITHUB_TOKEN:
        env["GIT_ASKPASS"] = "echo"
        env["GIT_TERMINAL_PROMPT"] = "0"
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd or str(SANDBOX_DIR),
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return {"success": False, "output": "Git command timed out"}
    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    combined = out + ("\n" + err if err else "")
    return {"success": proc.returncode == 0, "output": combined.strip()}


def _auth_url(url: str) -> str:
    if GITHUB_TOKEN and "github.com" in url and "@" not in url:
        return url.replace("https://", f"https://{GITHUB_TOKEN}@")
    return url


async def git_clone(repo_url: str, dest_dir: str = None, branch: str = None) -> dict:
    auth_url = _auth_url(repo_url)
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    target = dest_dir or str(SANDBOX_DIR / repo_name)
    branch_flag = f"--branch {branch}" if branch else ""
    cmd = f"git clone {branch_flag} --depth=50 {auth_url} {target}"
    result = await _git(cmd)
    if result["success"]:
        result["local_path"] = target
        result["repo_name"] = repo_name
    return result


async def git_commit_push(
    repo_dir: str,
    message: str,
    files: list[str] = None,
    branch: str = "main",
) -> dict:
    add_cmd = f"git add {' '.join(files)}" if files else "git add -A"

    config_cmds = [
        'git config user.email "replitai@bot.com"',
        f'git config user.name "ReplitAI"',
    ]
    for c in config_cmds:
        await _git(c, cwd=repo_dir)

    add_result = await _git(add_cmd, cwd=repo_dir)
    if not add_result["success"]:
        return add_result

    commit_result = await _git(f'git commit -m "{message}"', cwd=repo_dir)
    if not commit_result["success"] and "nothing to commit" not in commit_result["output"]:
        return commit_result

    push_result = await _git(f"git push origin {branch}", cwd=repo_dir)
    return {
        "success": push_result["success"],
        "output": commit_result["output"] + "\n" + push_result["output"],
        "branch": branch,
    }


async def git_create_pr(
    repo_full_name: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
) -> dict:
    if not GITHUB_TOKEN:
        return {"success": False, "output": "GITHUB_TOKEN not configured"}
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_full_name)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
        )
        return {"success": True, "url": pr.html_url, "number": pr.number, "output": f"PR created: {pr.html_url}"}
    except Exception as e:
        return {"success": False, "output": f"PR creation failed: {e}"}


async def git_create_repo(name: str, description: str = "", private: bool = False) -> dict:
    if not GITHUB_TOKEN:
        return {"success": False, "output": "GITHUB_TOKEN not configured"}
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        user = g.get_user()
        repo = user.create_repo(
            name=name,
            description=description,
            private=private,
            auto_init=True,
        )
        return {
            "success": True,
            "url": repo.html_url,
            "clone_url": repo.clone_url,
            "ssh_url": repo.ssh_url,
            "output": f"Repo created: {repo.html_url}",
        }
    except Exception as e:
        return {"success": False, "output": f"Repo creation failed: {e}"}


async def git_list_repos(limit: int = 20) -> dict:
    if not GITHUB_TOKEN:
        return {"success": False, "repos": [], "output": "GITHUB_TOKEN not configured"}
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        user = g.get_user()
        repos = []
        for r in user.get_repos()[:limit]:
            repos.append({
                "name": r.full_name,
                "description": r.description or "",
                "url": r.html_url,
                "language": r.language,
                "updated": str(r.updated_at),
                "stars": r.stargazers_count,
            })
        return {"success": True, "repos": repos, "count": len(repos)}
    except Exception as e:
        return {"success": False, "repos": [], "output": str(e)}


async def git_get_issues(repo_full_name: str, state: str = "open", limit: int = 10) -> dict:
    if not GITHUB_TOKEN:
        return {"success": False, "issues": []}
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(repo_full_name)
        issues = []
        for i in repo.get_issues(state=state)[:limit]:
            issues.append({"number": i.number, "title": i.title, "url": i.html_url, "state": i.state})
        return {"success": True, "issues": issues}
    except Exception as e:
        return {"success": False, "issues": [], "output": str(e)}


async def git_push_project_to_github(local_dir: str, repo_name: str, description: str = "") -> dict:
    create_result = await git_create_repo(repo_name, description)
    if not create_result["success"]:
        return create_result

    clone_url = _auth_url(create_result["clone_url"])
    init_cmds = [
        "git init",
        'git config user.email "replitai@bot.com"',
        'git config user.name "ReplitAI"',
        "git add -A",
        'git commit -m "Initial commit from ReplitAI"',
        f"git branch -M main",
        f"git remote add origin {clone_url}",
        "git push -u origin main",
    ]
    for cmd in init_cmds:
        r = await _git(cmd, cwd=local_dir)
        if not r["success"] and "nothing to commit" not in r.get("output", ""):
            if "already exists" not in r.get("output", "") and "reinit" not in r.get("output", ""):
                logger.warning(f"Git cmd failed: {cmd} -> {r['output']}")

    return {
        "success": True,
        "repo_url": create_result["url"],
        "output": f"Project pushed to {create_result['url']}",
    }
