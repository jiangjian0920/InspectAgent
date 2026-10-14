from __future__ import annotations

import logging
import os
import sys


_LOGGER_NAME = "inspect_agent"
_CONFIGURED = False


def setup_logging(level: str | None = None) -> None:
    """初始化结构化文本日志，重复调用安全。"""
    global _CONFIGURED
    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=logging.getLevelName(resolved),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stderr,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    """返回带统一前缀的 logger。"""
    if not _CONFIGURED:
        setup_logging()
    if not name:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


__all__ = ["setup_logging", "get_logger"]
