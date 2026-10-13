from __future__ import annotations

import os
import sys
from pathlib import Path


def collect_doctor_report() -> str:
    lines = [
        "运行环境诊断（不调用智谱 API 和 Prometheus）",
        f"- python: {sys.executable}",
        f"- version: {sys.version.replace(chr(10), ' ')}",
        f"- cwd: {os.getcwd()}",
        f"- PYTHONPATH: {os.getenv('PYTHONPATH') or '<empty>'}",
        f"- sys.path: {sys.path}",
        f"- main.py exists: {Path('/app/main.py').exists()}",
        f"- requirements.txt exists: {Path('/app/requirements.txt').exists()}",
        f"- hostname: {os.uname().nodename}",
        f"- uid: {os.getuid()}",
    ]
    for name in ("zai", "dotenv", "requests", "langgraph"):
        try:
            module = __import__(name)
            location = getattr(module, "__file__", "<builtin>")
            version = getattr(module, "__version__", "unknown")
            lines.append(f"- import {name}: OK file={location} version={version}")
        except Exception as exc:
            lines.append(f"- import {name}: FAIL {type(exc).__name__}: {exc}")
    try:
        from agent.llm.sdk import load_zhipu_client_class

        client_cls = load_zhipu_client_class()
        lines.append(f"- Zhipu client class: {client_cls.__module__}.{client_cls.__name__}")
    except Exception as exc:
        lines.append(f"- Zhipu client class: FAIL {exc}")
    try:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "zai-sdk", "requests", "python-dotenv", "langgraph"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or result.stderr or "").strip() or "<empty>"
        lines.append("- pip show:")
        for raw in output.splitlines():
            lines.append(f"  {raw}")
    except Exception as exc:
        lines.append(f"- pip show: FAIL {exc}")
    return "\n".join(lines)
