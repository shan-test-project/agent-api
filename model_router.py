import asyncio
import time
from typing import Optional, Any
from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODELS, MODEL_FALLBACK_CHAIN, TASK_MODEL_ROUTING
import logging

logger = logging.getLogger(__name__)


class ModelRouter:
    def __init__(self):
        self.client = AsyncGroq(api_key=GROQ_API_KEY)
        self.usage_stats = {}
        self.model_health = {m: True for m in MODEL_FALLBACK_CHAIN}
        self.last_error_time = {}

    def select_model(self, task_type: str = "general", force_model: Optional[str] = None) -> str:
        if force_model:
            return force_model
        tier = TASK_MODEL_ROUTING.get(task_type, "balanced")
        return GROQ_MODELS.get(tier, GROQ_MODELS["balanced"])

    async def chat(
        self,
        messages: list[dict],
        task_type: str = "general",
        temperature: float = 0.7,
        max_tokens: int = 8192,
        force_model: Optional[str] = None,
        stream: bool = False,
    ) -> str:
        model = self.select_model(task_type, force_model)
        models_to_try = [model] + [m for m in MODEL_FALLBACK_CHAIN if m != model]

        last_error = None
        for attempt_model in models_to_try:
            if not self.model_health.get(attempt_model, True):
                last_fail = self.last_error_time.get(attempt_model, 0)
                if time.time() - last_fail < 60:
                    continue
                self.model_health[attempt_model] = True

            try:
                logger.debug(f"Attempting model: {attempt_model} for task: {task_type}")
                response = await self.client.chat.completions.create(
                    model=attempt_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
                content = response.choices[0].message.content or ""
                self._record_usage(attempt_model, response.usage)
                return content

            except Exception as e:
                last_error = e
                logger.warning(f"Model {attempt_model} failed: {e}")
                self.model_health[attempt_model] = False
                self.last_error_time[attempt_model] = time.time()
                await asyncio.sleep(0.5)

        raise RuntimeError(f"All models failed. Last error: {last_error}")

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        task_type: str = "general",
        temperature: float = 0.2,
        max_tokens: int = 8192,
    ) -> Any:
        model = self.select_model(task_type)
        models_to_try = [model] + [m for m in MODEL_FALLBACK_CHAIN if m != model]

        for attempt_model in models_to_try:
            try:
                response = await self.client.chat.completions.create(
                    model=attempt_model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._record_usage(attempt_model, response.usage)
                return response.choices[0].message
            except Exception as e:
                logger.warning(f"Tool model {attempt_model} failed: {e}")
                continue

        raise RuntimeError("All models failed for tool calling")

    async def vision_analyze(
        self,
        image_url: str,
        prompt: str,
        detail: str = "high",
    ) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": detail}},
                ],
            }
        ]
        for vision_model in [GROQ_MODELS["vision_large"], GROQ_MODELS["vision"]]:
            try:
                response = await self.client.chat.completions.create(
                    model=vision_model,
                    messages=messages,
                    max_tokens=4096,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"Vision model {vision_model} failed: {e}")
                continue
        raise RuntimeError("Vision models unavailable")

    async def transcribe_audio(self, audio_path: str) -> str:
        try:
            with open(audio_path, "rb") as f:
                transcription = await self.client.audio.transcriptions.create(
                    file=(audio_path, f.read()),
                    model="whisper-large-v3",
                    language="en",
                )
            return transcription.text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

    def _record_usage(self, model: str, usage: Any):
        if model not in self.usage_stats:
            self.usage_stats[model] = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}
        self.usage_stats[model]["requests"] += 1
        if usage:
            self.usage_stats[model]["prompt_tokens"] += getattr(usage, "prompt_tokens", 0)
            self.usage_stats[model]["completion_tokens"] += getattr(usage, "completion_tokens", 0)

    def get_stats(self) -> dict:
        return {
            "usage": self.usage_stats,
            "model_health": self.model_health,
        }


router = ModelRouter()
