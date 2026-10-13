from __future__ import annotations

from agent.skills import build_default_skills


def build_default_registry():
    """兼容旧入口：巡检能力已迁移到可插拔 Skill 注册表。"""
    raise RuntimeError(
        "巡检能力注册表已替换为 SkillRegistry。"
        "请使用 agent.skills.build_default_skills(settings)。"
    )
