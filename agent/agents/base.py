import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    name: str
    result: Any
    success: bool = True
    error: str = ""

    def to_message(self) -> dict:
        if isinstance(self.result, dict):
            content = self.result.get("output") or self.result.get("content") or json.dumps(self.result)
        else:
            content = str(self.result)
        if not self.success:
            content = f"[Tool Error] {self.error}: {content}"
        return {"role": "tool", "name": self.name, "content": str(content)[:4000]}


class AgentBase:
    TOOL_DEFINITIONS: list[dict] = []

    def __init__(self, router, user_id: int, project_dir: str = None):
        self.router = router
        self.user_id = user_id
        self.project_dir = project_dir
        self._tool_registry: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._register_tools()

    def _register_tools(self):
        pass

    def register(self, name: str, func: Callable):
        self._tool_registry[name] = func

    async def execute_tool(self, name: str, args: dict) -> ToolResult:
        func = self._tool_registry.get(name)
        if not func:
            return ToolResult(name=name, result={}, success=False, error=f"Unknown tool: {name}")
        try:
            if self.project_dir and "project_dir" not in args:
                import inspect
                sig = inspect.signature(func)
                if "project_dir" in sig.parameters:
                    args["project_dir"] = self.project_dir
            result = await func(**args)
            return ToolResult(name=name, result=result, success=True)
        except Exception as e:
            logger.error(f"Tool {name} error: {e}")
            return ToolResult(name=name, result={}, success=False, error=str(e))

    async def run(self, system_prompt: str, messages: list[dict],
                  max_iterations: int = 15, temperature: float = 0.2) -> str:
        working_messages = list(messages)
        tools = self.TOOL_DEFINITIONS

        for iteration in range(max_iterations):
            try:
                if tools:
                    response = await self.router.chat_with_tools(
                        messages=[{"role": "system", "content": system_prompt}] + working_messages,
                        tools=tools,
                        temperature=temperature,
                    )
                else:
                    content = await self.router.chat(
                        messages=[{"role": "system", "content": system_prompt}] + working_messages,
                        temperature=temperature,
                    )
                    return content

                if response.tool_calls:
                    tool_msg = {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in response.tool_calls
                        ],
                    }
                    working_messages.append(tool_msg)

                    for tc in response.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {}
                        tr = await self.execute_tool(tc.function.name, args)
                        working_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tr.to_message()["content"],
                        })
                else:
                    return response.content or ""

            except Exception as e:
                logger.error(f"Agent iteration {iteration} error: {e}")
                if iteration == max_iterations - 1:
                    return f"I encountered an error: {e}"
                continue

        return "Task completed (max iterations reached)."
