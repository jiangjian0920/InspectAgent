from __future__ import annotations

from typing import Any


def load_zhipu_client_class() -> type[Any]:
    """导入 zai-sdk 里的客户端类。"""
    errors: list[str] = []
    try:
        from zai import ZhipuAiClient

        return ZhipuAiClient
    except ImportError as exc:
        errors.append(f"zai.ZhipuAiClient: {exc}")
    try:
        from zai import ZaiClient

        return ZaiClient
    except ImportError as exc:
        errors.append(f"zai.ZaiClient: {exc}")
    detail = "；".join(errors) or "未知导入错误"
    raise RuntimeError(
        "无法导入智谱官方 SDK。"
        "请安装 zai-sdk==0.2.3，不要同时安装旧包 zhipuai。"
        "国内平台使用：from zai import ZhipuAiClient。"
        "请确认镜像构建时已执行 pip install -r requirements.txt，"
        "并且集群节点加载的是最新镜像。"
        f"详情：{detail}"
    )
