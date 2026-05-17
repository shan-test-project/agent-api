import base64
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _encode_image(image_path: str) -> tuple[str, str]:
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }
    mime = mime_map.get(suffix, "image/jpeg")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}", mime


async def analyze_image(image_path: str, prompt: str = None, task: str = "general") -> dict:
    from model_router import router

    default_prompts = {
        "general": "Describe this image in detail.",
        "code": (
            "This is a screenshot of code. Please:\n"
            "1. Identify the programming language\n"
            "2. Extract the complete code text\n"
            "3. Identify any visible errors or issues\n"
            "4. Suggest improvements if applicable"
        ),
        "error": (
            "This is a screenshot of an error or exception. Please:\n"
            "1. Extract the exact error message\n"
            "2. Identify the root cause\n"
            "3. Provide a step-by-step solution\n"
            "4. Show corrected code if applicable"
        ),
        "diagram": (
            "This is a technical diagram. Please:\n"
            "1. Describe the architecture/flow shown\n"
            "2. Identify all components and their relationships\n"
            "3. Suggest implementation approach\n"
            "4. List technologies that could be used"
        ),
        "ui": (
            "This is a UI/UX design or mockup. Please:\n"
            "1. Describe the layout and components\n"
            "2. Generate HTML/CSS code to recreate it\n"
            "3. Suggest improvements\n"
            "4. Identify the design system being used"
        ),
        "whiteboard": (
            "This is a whiteboard or hand-drawn diagram. Please:\n"
            "1. Interpret what's drawn\n"
            "2. Convert to a structured description\n"
            "3. Generate code if it represents an algorithm or architecture"
        ),
    }

    final_prompt = prompt or default_prompts.get(task, default_prompts["general"])

    try:
        data_url, mime = _encode_image(image_path)
        analysis = await router.vision_analyze(
            image_url=data_url,
            prompt=final_prompt,
        )
        return {"success": True, "analysis": analysis, "task": task}
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        return {"success": False, "error": str(e)}


async def analyze_code_screenshot(image_path: str) -> dict:
    return await analyze_image(image_path, task="code")


async def analyze_error_screenshot(image_path: str) -> dict:
    return await analyze_image(image_path, task="error")


async def analyze_diagram(image_path: str) -> dict:
    return await analyze_image(image_path, task="diagram")


async def generate_code_from_image(image_path: str, target_language: str = "python") -> dict:
    prompt = (
        f"Analyze this image and generate complete, working {target_language} code based on what you see.\n"
        "If it's a UI mockup: generate the full implementation code.\n"
        "If it's a diagram: generate the implementation.\n"
        "If it's existing code: extract and improve it.\n"
        "If it's an error: provide the fix.\n"
        "Return ONLY the code, no explanations."
    )
    return await analyze_image(image_path, prompt=prompt)
