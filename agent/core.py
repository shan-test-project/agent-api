import json
import logging
from pathlib import Path
from typing import Optional, AsyncGenerator
from model_router import router as model_router
from agent.prompts import (
    SUPERVISOR_PROMPT, PLANNER_PROMPT, CODER_PROMPT, TESTER_PROMPT,
    REVIEWER_PROMPT, DEPLOYER_PROMPT, RESEARCHER_PROMPT,
    SELF_IMPROVEMENT_PROMPT, SYSTEM_IDENTITY,
)
from tools.terminal import execute_code, execute_shell, install_package, run_tests
from tools.file_manager import read_file, write_file, list_files, search_code, create_project_structure
from tools.git_tools import (
    git_clone, git_commit_push, git_create_pr, git_list_repos,
    git_create_repo, git_get_issues, git_push_project_to_github,
)
from tools.web_search import web_search, fetch_url, search_github
from tools.vision import analyze_image, analyze_code_screenshot
from tools.deploy_tools import generate_dockerfile, deploy_to_platform, scan_security
from memory.vector_store import memory_store
from config import SANDBOX_DIR, MAX_TOOL_ITERATIONS

logger = logging.getLogger(__name__)

ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Execute code in a sandboxed environment. Returns stdout/stderr and exit code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The code to execute"},
                    "language": {"type": "string", "enum": ["python", "javascript", "typescript", "bash", "go", "rust"], "default": "python"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Run a shell command. Use for npm install, pip install, git commands, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_package",
            "description": "Install packages for a given language (pip, npm, go get, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "packages": {"type": "string", "description": "Space-separated package names"},
                    "language": {"type": "string", "enum": ["python", "javascript", "typescript", "go"], "default": "python"},
                },
                "required": ["packages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or create a file with given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to project dir)"},
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path (relative to project dir)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory to list", "default": "."},
                    "recursive": {"type": "boolean", "default": True},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a pattern across all code files in the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Regex or text pattern to search"},
                    "directory": {"type": "string", "default": "."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite for the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_file": {"type": "string", "description": "Specific test file (optional)"},
                    "language": {"type": "string", "default": "python"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Use for documentation, solutions, tutorials.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and read the text content of a URL (documentation page, GitHub file, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_clone",
            "description": "Clone a GitHub repository to the local sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "Full GitHub URL"},
                    "branch": {"type": "string", "description": "Branch to clone (optional)"},
                },
                "required": ["repo_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit_push",
            "description": "Commit and push changes to the remote GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string", "description": "Local repo directory"},
                    "message": {"type": "string", "description": "Commit message"},
                    "branch": {"type": "string", "default": "main"},
                },
                "required": ["repo_dir", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_create_repo",
            "description": "Create a new GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string", "default": ""},
                    "private": {"type": "boolean", "default": False},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_list_repos",
            "description": "List GitHub repositories for the authenticated user.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "default": 15}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_dockerfile",
            "description": "Generate Dockerfile, docker-compose.yml, and GitHub Actions CI/CD for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "enum": ["python", "node", "fastapi", "nextjs", "go"], "default": "python"},
                    "port": {"type": "integer", "default": 8080},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deploy_to_platform",
            "description": "Get deployment instructions for a specific platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["railway", "fly", "render", "huggingface", "vercel", "replit"]},
                    "app_name": {"type": "string", "default": "myapp"},
                },
                "required": ["platform"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save an important fact, preference, or learning to long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "What to remember"},
                    "memory_type": {"type": "string", "enum": ["preference", "coding_style", "project", "general", "learning"], "default": "general"},
                    "importance": {"type": "integer", "description": "1-10 importance score", "default": 5},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_project_structure",
            "description": "Create a full project directory structure with multiple files at once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "structure": {
                        "type": "object",
                        "description": "Nested dict where string values are file contents, dict values are subdirs",
                    },
                    "project_name": {"type": "string", "description": "Project folder name"},
                },
                "required": ["structure", "project_name"],
            },
        },
    },
]

CODER_TOOLS = [t for t in ALL_TOOLS if t["function"]["name"] in (
    "execute_code", "execute_shell", "install_package", "write_file", "read_file",
    "list_files", "search_code", "run_tests", "save_memory", "create_project_structure",
)]
PLANNER_TOOLS = [t for t in ALL_TOOLS if t["function"]["name"] in (
    "web_search", "fetch_url", "list_files", "read_file", "create_project_structure",
    "write_file", "save_memory",
)]
TESTER_TOOLS = [t for t in ALL_TOOLS if t["function"]["name"] in (
    "execute_code", "write_file", "read_file", "list_files", "run_tests", "search_code",
)]
REVIEWER_TOOLS = [t for t in ALL_TOOLS if t["function"]["name"] in (
    "read_file", "list_files", "search_code", "execute_code", "web_search",
)]
DEPLOYER_TOOLS = [t for t in ALL_TOOLS if t["function"]["name"] in (
    "generate_dockerfile", "deploy_to_platform", "write_file", "read_file",
    "execute_shell", "git_commit_push", "git_create_repo",
)]
RESEARCHER_TOOLS = [t for t in ALL_TOOLS if t["function"]["name"] in (
    "web_search", "fetch_url", "save_memory",
)]

AGENT_CONFIG = {
    "PLANNER": (PLANNER_PROMPT, PLANNER_TOOLS, "planning"),
    "CODER": (CODER_PROMPT, CODER_TOOLS, "code_generation"),
    "TESTER": (TESTER_PROMPT, TESTER_TOOLS, "testing"),
    "REVIEWER": (REVIEWER_PROMPT, REVIEWER_TOOLS, "code_review"),
    "DEPLOYER": (DEPLOYER_PROMPT, DEPLOYER_TOOLS, "deployment"),
    "RESEARCHER": (RESEARCHER_PROMPT, RESEARCHER_TOOLS, "quick_question"),
    "SELF": (SELF_IMPROVEMENT_PROMPT, CODER_TOOLS, "code_review"),
}


async def _route_task(messages: list[dict]) -> str:
    recent = messages[-3:] if len(messages) >= 3 else messages
    prompt_msgs = [
        {"role": "system", "content": SUPERVISOR_PROMPT},
        *recent,
        {"role": "user", "content": "Which agent should handle this task? Reply with ONLY the agent name."},
    ]
    response = await model_router.chat(prompt_msgs, task_type="planning", temperature=0.1, max_tokens=50)
    response = response.strip().upper().split()[0] if response.strip() else "CODER"
    valid = {"PLANNER", "CODER", "TESTER", "REVIEWER", "DEPLOYER", "RESEARCHER", "DIRECT", "SELF"}
    return response if response in valid else "CODER"


async def _execute_tool(name: str, args: dict, project_dir: str, user_id: int) -> str:
    try:
        if name == "execute_code":
            r = await execute_code(args.get("code", ""), args.get("language", "python"), project_dir)
        elif name == "execute_shell":
            r = await execute_shell(args.get("command", ""), cwd=project_dir, timeout=args.get("timeout", 60))
        elif name == "install_package":
            r = await install_package(args.get("packages", ""), args.get("language", "python"), project_dir)
        elif name == "write_file":
            r = await write_file(args["path"], args["content"], project_dir)
        elif name == "read_file":
            r = await read_file(args["path"], project_dir)
        elif name == "list_files":
            r = await list_files(args.get("directory", "."), project_dir, args.get("recursive", True))
        elif name == "search_code":
            r = await search_code(args["query"], args.get("directory", "."), project_dir)
        elif name == "run_tests":
            r = await run_tests(args.get("test_file"), args.get("language", "python"), project_dir)
        elif name == "web_search":
            r = await web_search(args["query"], args.get("num_results", 5))
        elif name == "fetch_url":
            r = await fetch_url(args["url"])
        elif name == "git_clone":
            r = await git_clone(args["repo_url"], branch=args.get("branch"))
        elif name == "git_commit_push":
            r = await git_commit_push(args["repo_dir"], args["message"], branch=args.get("branch", "main"))
        elif name == "git_create_repo":
            r = await git_create_repo(args["name"], args.get("description", ""), args.get("private", False))
        elif name == "git_list_repos":
            r = await git_list_repos(args.get("limit", 15))
        elif name == "generate_dockerfile":
            r = await generate_dockerfile(args.get("language", "python"), project_dir, args.get("port", 8080))
        elif name == "deploy_to_platform":
            r = await deploy_to_platform(args["platform"], project_dir, args.get("app_name", "myapp"))
        elif name == "save_memory":
            mem = memory_store(user_id)
            success = await mem.add(
                args["content"], args.get("memory_type", "general"), args.get("importance", 5)
            )
            r = {"success": success, "output": "Memory saved" if success else "Failed to save memory"}
        elif name == "create_project_structure":
            project_path = str(Path(project_dir) / args.get("project_name", "project"))
            r = await create_project_structure(args["structure"], project_path)
        else:
            r = {"success": False, "output": f"Unknown tool: {name}"}

        if isinstance(r, dict):
            return r.get("output") or r.get("content") or r.get("formatted") or json.dumps(r)[:3000]
        return str(r)[:3000]

    except Exception as e:
        logger.error(f"Tool {name} execution error: {e}")
        return f"Tool error: {e}"


async def run_agent(
    user_message: str,
    user_id: int,
    history: list[dict],
    project_dir: str = None,
    project_name: str = "default",
    image_path: str = None,
    voice_text: str = None,
    force_agent: str = None,
    status_callback=None,
) -> str:
    if not project_dir:
        project_dir = str(SANDBOX_DIR / f"user_{user_id}" / project_name)
    Path(project_dir).mkdir(parents=True, exist_ok=True)

    mem = memory_store(user_id)
    memory_context = await mem.get_context_for_prompt(user_message)

    content_parts = []
    if voice_text:
        content_parts.append(f"[Voice message transcribed]: {voice_text}")
    if image_path:
        content_parts.append(f"[Image attached: {image_path}]")
    content_parts.append(user_message)
    full_user_content = "\n".join(content_parts)

    # Strip any non-standard fields — Groq only accepts role + content
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-20:]]
    messages.append({"role": "user", "content": full_user_content})

    system_prompt = SYSTEM_IDENTITY
    if memory_context:
        system_prompt += f"\n\n{memory_context}"
    system_prompt += f"\n\nCurrent project: {project_name}\nProject directory: {project_dir}"

    agent_name = force_agent or await _route_task(messages)

    if agent_name == "DIRECT":
        return await model_router.chat(
            [{"role": "system", "content": system_prompt}] + messages,
            task_type="quick_question",
        )

    agent_system_prompt, agent_tools, task_type = AGENT_CONFIG.get(
        agent_name, AGENT_CONFIG["CODER"]
    )
    if agent_name == "DEPLOYER":
        agent_system_prompt = DEPLOYER_PROMPT

    full_system = f"{system_prompt}\n\n---\n{agent_system_prompt}"

    if status_callback:
        await status_callback(f"🤖 [{agent_name}] thinking...")

    working_messages = list(messages)

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            if agent_tools:
                response = await model_router.chat_with_tools(
                    messages=[{"role": "system", "content": full_system}] + working_messages,
                    tools=agent_tools,
                    task_type=task_type,
                    temperature=0.2,
                )
            else:
                content = await model_router.chat(
                    messages=[{"role": "system", "content": full_system}] + working_messages,
                    task_type=task_type,
                )
                return content

            if response.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in response.tool_calls
                    ],
                }
                working_messages.append(assistant_msg)

                for tc in response.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    tool_name = tc.function.name
                    if status_callback:
                        await status_callback(f"🔧 [{agent_name}] using {tool_name}...")

                    tool_output = await _execute_tool(tool_name, args, project_dir, user_id)
                    working_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(tool_output)[:4000],
                    })

            else:
                final = response.content or ""
                if final:
                    try:
                        await mem.add(
                            f"Task: {user_message[:200]} | Agent: {agent_name}",
                            memory_type="general",
                            importance=3,
                        )
                    except Exception:
                        pass
                return final

        except Exception as e:
            logger.error(f"Agent loop error at iteration {iteration}: {e}", exc_info=True)
            raise

    return "I completed the task. Let me know if you need anything else!"


async def self_improve(user_id: int, project_dir: str = None) -> str:
    return await run_agent(
        user_message=(
            "Review the ReplitAI bot's own source code. "
            "Identify the top 5 improvements: bugs, missing features, performance issues, or security gaps. "
            "Provide specific code fixes for each."
        ),
        user_id=user_id,
        history=[],
        project_dir=project_dir or str(Path(__file__).parent.parent),
        force_agent="SELF",
    )
