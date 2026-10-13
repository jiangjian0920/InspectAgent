from __future__ import annotations

import time
from typing import Any

from agent.config import Settings
from agent.llm.sdk import load_zhipu_client_class
from agent.logger import get_logger


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
    return (
        "timeout" in joined
        or "timed out" in text
        or "readtimeout" in joined
        or "connecttimeout" in joined
    )


class ZhipuLLMClient:
    """封装智谱对话 API 的调用和超时处理。"""

    def __init__(self, settings: Settings) -> None:
        if not settings.zhipu_api_key:
            raise ValueError(
                "未配置 ZHIPU_API_KEY。请复制 .env.example 为 .env 并填写智谱 API Key。"
            )
        self.settings = settings
        self.logger = get_logger()
        self.client = self._build_client(settings)

    def _build_client(self, settings: Settings) -> Any:
        client_cls = load_zhipu_client_class()
        kwargs: dict[str, Any] = {
            "api_key": settings.zhipu_api_key,
            "timeout": self._build_timeout(settings.zhipu_timeout_seconds),
            "max_retries": 0,
        }
        if settings.zhipu_base_url:
            kwargs["base_url"] = settings.zhipu_base_url
        try:
            return client_cls(**kwargs)
        except TypeError:
            kwargs.pop("max_retries", None)
            try:
                return client_cls(**kwargs)
            except TypeError:
                return client_cls(api_key=settings.zhipu_api_key)

    def _build_timeout(self, seconds: float) -> Any:
        try:
            import httpx

            connect = min(10.0, max(3.0, seconds))
            return httpx.Timeout(timeout=seconds, connect=connect, read=seconds, write=30.0)
        except Exception:
            return seconds

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        round_index: int = 1,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self.settings.zhipu_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        timeout = self.settings.zhipu_timeout_seconds
        self.logger.info(
            "LLM 请求 round=%s model=%s messages=%s timeout=%ss tools=%s",
            round_index,
            self.settings.zhipu_model,
            len(messages),
            timeout,
            [item.get("function", {}).get("name") for item in tools or []],
        )
        self.logger.info(
            "等待智谱响应 round=%s，若超过 %s 秒仍无返回会超时退出",
            round_index,
            timeout,
        )
        started = time.monotonic()
        try:
            response = self.client.chat.completions.create(**payload)
        except Exception as exc:
            elapsed = time.monotonic() - started
            if _is_timeout(exc):
                self.logger.error(
                    "LLM 读超时 round=%s elapsed=%.1fs timeout=%ss error=%s",
                    round_index,
                    elapsed,
                    timeout,
                    exc,
                )
                raise LLMTimeoutError(
                    "智谱 GLM 请求超时："
                    f"round={round_index}，已等待 {elapsed:.1f}s，"
                    f"超时阈值 {timeout}s。"
                    "这是 HTTPS 读超时：TCP/域名通常已连通，但模型在超时时间内没有返回完整响应。"
                    "ping 通 open.bigmodel.cn 不能说明对话接口可用。"
                ) from exc
            self.logger.exception(
                "LLM 请求失败 round=%s elapsed=%.1fs error=%s",
                round_index,
                elapsed,
                exc,
            )
            raise RuntimeError(f"调用智谱 GLM 失败: {exc}") from exc
        elapsed = time.monotonic() - started
        choice = response.choices[0]
        message = choice.message
        finish_reason = getattr(choice, "finish_reason", None)
        tool_calls = getattr(message, "tool_calls", None) or []
        self.logger.info(
            "LLM 返回 round=%s elapsed=%.1fs finish_reason=%s tool_calls=%s content_preview=%s",
            round_index,
            elapsed,
            finish_reason,
            len(tool_calls),
            (message.content or "")[:300],
        )
        return response
