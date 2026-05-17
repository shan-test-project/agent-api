#!/usr/bin/env python3
"""Push the ReplitAI project to GitHub as a new repo."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def main():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ GITHUB_TOKEN not set. Add it in Replit Secrets.")
        sys.exit(1)

    from github import Github
    g = Github(token)
    user = g.get_user()
    username = user.login
    print(f"✅ Logged in as: {username}")

    repo_name = os.getenv("GITHUB_REPO_NAME", "agent-api")
    description = "⚡ ReplitAI — Powerful AI Coding Assistant Telegram Bot with multi-agent system, vision, GitHub integration, and WebApp"

    # Check if repo already exists
    try:
        existing = g.get_repo(f"{username}/{repo_name}")
        print(f"ℹ️  Repo already exists: {existing.html_url}")
        clone_url = existing.clone_url
        created = False
    except Exception:
        print(f"📦 Creating repo: {repo_name}...")
        repo = user.create_repo(
            name=repo_name,
            description=description,
            private=False,
            auto_init=False,
        )
        clone_url = repo.clone_url
        print(f"✅ Repo created: {repo.html_url}")
        created = True

    # Inject auth token into URL
    auth_url = clone_url.replace("https://", f"https://{token}@")

    bot_dir = str(Path(__file__).parent)

    import subprocess

    def run(cmd, cwd=None):
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.stdout.strip():
            print(f"  {result.stdout.strip()}")
        return result.returncode == 0

    print("\n📤 Pushing code to GitHub...")

    cmds = [
        "git init",
        'git config user.email "replitai@bot.com"',
        'git config user.name "ReplitAI"',
        "git add -A",
        'git commit -m "Initial commit — ReplitAI Telegram Bot"',
        "git branch -M main",
        f"git remote remove origin 2>/dev/null; git remote add origin {auth_url}",
        "git push -u origin main --force",
    ]

    for cmd in cmds:
        ok = run(cmd, cwd=bot_dir)
        if not ok and "nothing to commit" not in cmd and "remove origin" not in cmd:
            print(f"  ⚠️  Command had issues: {cmd.split()[1] if len(cmd.split()) > 1 else cmd}")

    repo_url = clone_url.replace(".git", "")
    print(f"\n✅ Project pushed to GitHub!")
    print(f"🔗 {repo_url}")
    print(f"\n📋 Clone it anywhere with:")
    print(f"   git clone {clone_url}")


if __name__ == "__main__":
    asyncio.run(main())
