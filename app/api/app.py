from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel

from app.analysis.registry import registered_names
from app.core.config import Settings, load_settings
from app.nlu.client import GLMClient
from app.orchestrator import InspectionAgent
from app.reporting.builder import target_label
from app.reporting.render import render_text


class InspectRequest(BaseModel):
    instruction: str


class InspectResponse(BaseModel):
    request_id: str
    task_type: str
    query_status: str
    target: str
    summary: str
    report: dict
    text: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_agent() -> InspectionAgent:
    settings = get_settings()
    llm = GLMClient(settings.llm) if settings.llm.enabled else None
    return InspectionAgent(settings, llm=llm)


def create_app():  # pragma: no cover - 需要 fastapi 依赖
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("未安装 fastapi，请执行 pip install fastapi uvicorn") from exc

    app = FastAPI(title="AI Prometheus 巡检 Agent", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        settings = get_settings()
        return {
            "status": "ok",
            "prometheus_configured": bool(settings.prometheus_url),
            "llm_enabled": settings.llm.enabled,
        }

    @app.get("/capabilities")
    def capabilities() -> dict:
        agent = get_agent()
        return {
            "resource_types": [agent.provider.resource_type],
            "metrics": [
                {"metric_id": d.metric_id, "display_name": d.display_name, "unit": d.unit}
                for d in agent.provider.supported_metrics()
            ],
            "operators": registered_names(),
        }

    @app.post("/inspect", response_model=InspectResponse)
    def inspect(payload: InspectRequest) -> InspectResponse:
        agent = get_agent()
        report = agent.run(payload.instruction)
        return InspectResponse(
            request_id=report.request_id,
            task_type=report.task_type,
            query_status=report.query_status,
            target=report.target,
            summary=report.summary,
            report=report.model_dump(mode="json"),
            text=render_text(report),
        )

    return app


__all__ = ["create_app", "InspectRequest", "InspectResponse", "get_agent", "get_settings", "target_label"]
