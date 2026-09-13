"""内容生成三阶段：选题 / 文案 / 脚本（BR-05.1）。"""
from __future__ import annotations

from app_core.llm import LLMClient
from app_core.models import ContentStage


def _name(product_info: dict) -> str:
    return product_info.get("name") or product_info.get("product_id", "产品")


def generate_topic(llm: LLMClient, product_info: dict) -> str:
    name = _name(product_info)
    return llm.generate(
        [{"role": "user", "content": f"为产品【{name}】生成 3 个选题。用户问题：{name}"}],
        mode="topic",
    )


def generate_copy(llm: LLMClient, product_info: dict) -> str:
    name = _name(product_info)
    return llm.generate(
        [{"role": "user", "content": f"为产品【{name}】生成推广文案。用户问题：{name}"}],
        mode="copy",
    )


def generate_script(llm: LLMClient, product_info: dict) -> str:
    name = _name(product_info)
    return llm.generate(
        [{"role": "user", "content": f"为产品【{name}】生成短视频脚本。用户问题：{name}"}],
        mode="script",
    )


STAGE_GENERATORS = {
    ContentStage.TOPIC: generate_topic,
    ContentStage.COPY: generate_copy,
    ContentStage.SCRIPT: generate_script,
}