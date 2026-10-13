from __future__ import annotations

from agent.config import Settings
from agent.intent import parse_intent
from agent.skills.catalogs import catalog_for


def build_inspection_plan(user_input: str, settings: Settings) -> str:
    """根据指令打印将要调用的 Skill 和指标，不真正查询。"""
    instruction = (user_input or "").strip() or "帮我巡检最近2小时服务器主机指标"
    intent = parse_intent(instruction, settings.default_time_range)
    lines = [
        "离线巡检规划（不调用智谱 API，不查询 Prometheus）",
        f"- 用户指令：{instruction}",
        f"- 时间范围：{intent.time_range}",
        f"- 全集群：{'是' if intent.cluster_wide else '否'}",
        f"- Prometheus：{settings.prometheus_url}",
        "",
        "将调用的 Skill（单轮，不循环）：",
    ]
    for target in intent.targets:
        catalog = catalog_for(str(target["target_type"]))
        metrics = list(target.get("metrics") or []) or [item["key"] for item in catalog]
        names = []
        for key in metrics:
            item = next((row for row in catalog if row["key"] == key), None)
            names.append(item["name"] if item else key)
        lines.append(
            f"- {target['skill']} / 实例={target.get('instance') or '未指定'} / 指标={'、'.join(names)}"
        )
    lines.append("")
    lines.append("约束：Skill 先校验实例是否存在；不存在则返回「未找到对应实例」，不再查业务指标。")
    lines.append("阈值判断在 Skill 内完成，只回异常项。禁止编造监控数据。")
    return "\n".join(lines)
