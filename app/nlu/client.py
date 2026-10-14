from __future__ import annotations

import time
from typing import Any

from app.core.config import LLMSettings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger


class LLMTimeoutError(RuntimeError):
    pass


def _is_timeout(exc: BaseException) -> bool:
    names = {type(exc).__name__.lower()}
    text = str(exc).lower()
    current: BaseException | None = exc
    while current is not None:
        names.add(type(current).__name__.lower())
        text += " " + str(current).lower()
        current = current.__cause__ or current.__context__
    joined = " ".join(names)
    return "timeout" in joined or "timed out" in text or "readtimeout" in joined


class GLMClient:
    """智谱 GLM 对话客户端。仅用于意图/计划生成与可选报告摘要。"""

    def __init__(self, settings: LLMSettings) -> None:
        if not settings.api_key:
            raise ConfigurationError("未配置 ZHIPU_API_KEY")
        self.settings = settings
        self.logger = get_logger("glm")
        self._client = self._build_client()

    def _build_client(self) -> Any:
        try:
            from zai import ZhipuAiClient
        except ImportError as exc:  # pragma: no cover - 运行期依赖
            raise ConfigurationError(
                "未安装 zai-sdk，请执行 pip install -r requirements.txt"
            ) from exc
        kwargs: dict[str, Any] = {
            "api_key": self.settings.api_key,
            "timeout": self._build_timeout(self.settings.timeout_seconds),
        }
        if self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url
        try:
            return ZhipuAiClient(**kwargs)
        except TypeError:
            kwargs.pop("max_retries", None)
            return ZhipuAiClient(api_key=self.settings.api_key)

    def _build_timeout(self, seconds: float) -> Any:
        try:
            import httpx

            connect = min(10.0, max(3.0, seconds))
            return httpx.Timeout(timeout=seconds, connect=connect, read=seconds, write=30.0)
        except Exception:
            return seconds

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int = 2048,
    ) -> str:
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        started = time.monotonic()
        try:
            response = self._client.chat.completions.create(**payload)
        except Exception as exc:
            elapsed = time.monotonic() - started
            if _is_timeout(exc):
                raise LLMTimeoutError(
                    f"GLM 请求超时（已等待 {elapsed:.1f}s，阈值 {self.settings.timeout_seconds}s）"
                ) from exc
            raise RuntimeError(f"调用 GLM 失败: {exc}") from exc
        choice = response.choices[0]
        return choice.message.content or ""


__all__ = ["GLMClient", "LLMTimeoutError"]
