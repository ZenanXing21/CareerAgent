"""Shared, constrained contracts for paragraph polishing and template design."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from career_agent.models import DomainModel, NonEmptyStr
from career_agent.resume.models import Resume


class ResumeDesignTheme(DomainModel):
    layout: Literal["banner", "editorial", "sidebar"] = "editorial"
    visual_style: Literal["auto", "aurora", "blueprint", "paper", "plain"] = "auto"
    font_family: Literal["Microsoft YaHei", "SimSun", "DengXian", "Arial", "Georgia"] = (
        "Microsoft YaHei"
    )
    accent: str = Field(default="#176B72", pattern=r"^#[0-9a-fA-F]{6}$")
    title_size: float = Field(default=26, ge=20, le=36)
    heading_size: float = Field(default=13, ge=11, le=18)
    body_size: float = Field(default=10.5, ge=9, le=13)
    title_centered: bool = False
    compact: bool = False


class DesignedResumeTemplate(DomainModel):
    name: NonEmptyStr = Field(max_length=32)
    description: NonEmptyStr = Field(max_length=300)
    theme: ResumeDesignTheme
    used_skills: list[NonEmptyStr] = Field(default_factory=list)


class SavedResumeTemplate(DesignedResumeTemplate):
    id: NonEmptyStr


class ResumeFieldPolish(DomainModel):
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    optimized_text: NonEmptyStr


def design_skills() -> list[dict[str, str]]:
    root = Path(__file__).resolve().parents[2] / ".agents" / "skills"
    available = []
    for folder in sorted(root.glob("*")):
        if (folder / "SKILL.md").is_file() and folder.name == "ui-ux-pro-max":
            available.append(
                {
                    "id": folder.name,
                    "name": "UI/UX Pro Max",
                    "description": "排版、字体、配色与简洁专业的视觉设计",
                }
            )
    return available


def explicit_design_context(skill_ids: list[str]) -> str:
    allowed = {item["id"] for item in design_skills()}
    if not skill_ids:
        raise ValueError("请明确选择要调用的设计技能")
    if any(skill not in allowed for skill in skill_ids):
        raise ValueError("未找到所选设计技能")
    root = Path(__file__).resolve().parents[2] / ".agents" / "skills"
    return "\n\n".join(
        f"EXPLICIT_SKILL: {skill}\n" + (root / skill / "SKILL.md").read_text(encoding="utf-8")
        for skill in dict.fromkeys(skill_ids)
    )


def field_text(resume: Resume, path: str) -> str:
    if path == "__skills__":
        return "、".join(item.name for item in resume.skills)
    if not re.fullmatch(
        r"summary|personal_info\.(?:name|email|phone|location)|"
        r"(?:educations|work_experiences|internships|project_experiences|campus_experiences)"
        r"\.\d+\.(?:description|school|major|degree|company|title|name|role|organization|start_date|end_date)",
        path,
    ):
        raise ValueError("不能优化此字段")
    value: object = resume
    for part in path.split("."):
        if isinstance(value, list):
            if int(part) >= len(value):
                raise ValueError("未找到要优化的段落")
            value = value[int(part)]
        else:
            value = getattr(value, part)
    return str(value or "")


def validate_field_polish(original: str, result: ResumeFieldPolish) -> ResumeFieldPolish:
    def numbers(text: str) -> set[str]:
        return set(re.findall(r"\d+(?:\.\d+)?%?", text))

    if not numbers(result.optimized_text).issubset(numbers(original)):
        raise ValueError("改写包含原文没有的数字，请重新优化")
    return result
