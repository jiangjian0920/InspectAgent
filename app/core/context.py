from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    """生成新的请求链路 ID。"""
    return uuid.uuid4().hex


def set_request_id(request_id: str | None = None) -> str:
    """设置当前请求链路 ID，返回最终使用的值。"""
    resolved = request_id or new_request_id()
    _request_id.set(resolved)
    return resolved


def current_request_id() -> str | None:
    """读取当前请求链路 ID。"""
    return _request_id.get()


@contextmanager
def request_context(request_id: str | None = None) -> Iterator[str]:
    """在上下文中绑定请求链路 ID。"""
    token = _request_id.set(request_id or new_request_id())
    try:
        yield _request_id.get() or ""
    finally:
        _request_id.reset(token)


__all__ = ["new_request_id", "set_request_id", "current_request_id", "request_context"]
