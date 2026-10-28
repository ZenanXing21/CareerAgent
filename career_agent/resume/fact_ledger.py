"""Build a deterministic, source-preserving fact ledger from a master resume."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from career_agent.models import FactStatus
from career_agent.resume.models import Fact, FactLedger, Resume

_SENTENCE_BREAK = re.compile(r"[。；;\n]+")


class FactLedgerBuildError(ValueError):
    """Raised when a fact cannot be traced to the resume's raw text."""


def _parts(text: str | None, source_text: str) -> Iterator[str]:
    if text is None:
        return
    for part in _SENTENCE_BREAK.split(text):
        value = part.strip(" \t\r，,")
        if value and value in source_text:
            yield value


def _metadata(item: Any, *, section: str) -> dict[str, str | bool]:
    source_text = getattr(item, "source_text", "")
    role = getattr(item, "role", None)
    title = getattr(item, "title", None)
    values: dict[str, str | bool | None] = {
        "section": section,
        "entry_id": getattr(item, "id", None),
        "start_date": getattr(item, "start_date", None),
        "end_date": getattr(item, "end_date", None),
        "role": role if role and role in source_text else None,
        "title": title if title and title in source_text else None,
        "project_type": getattr(item, "project_type", None),
        "is_course_project": getattr(item, "is_course_project", None),
    }
    return {key: value for key, value in values.items() if value is not None}


def build_fact_ledger(resume: Resume, candidate_id: str) -> FactLedger:
    """Extract only explicit resume facts, preserving deterministic source order."""

    source_items = (
        *resume.educations,
        *resume.work_experiences,
        *resume.internships,
        *resume.project_experiences,
        *resume.campus_experiences,
        *resume.skills,
    )
    if any(item.source_text not in resume.raw_text for item in source_items):
        raise FactLedgerBuildError("fact source_text is not present in resume.raw_text")

    candidates: list[tuple[str, str, str, str, dict[str, str | bool]]] = []

    def add_entry(
        *,
        category: str,
        section: str,
        item: Any,
        fields: tuple[str, ...],
    ) -> None:
        source = f"resume.{section}.{item.id}"
        metadata = _metadata(item, section=section)
        for field in fields:
            value = getattr(item, field, None)
            for fact_text in _parts(value, item.source_text):
                candidates.append((category, source, item.source_text, fact_text, metadata))
        for fact_text in _parts(getattr(item, "description", None), item.source_text):
            candidates.append((category, source, item.source_text, fact_text, metadata))

    for item in resume.educations:
        add_entry(
            category="education",
            section="education",
            item=item,
            fields=("school", "degree", "major", "start_date", "end_date"),
        )
    for item in resume.work_experiences:
        add_entry(
            category="work",
            section="work",
            item=item,
            fields=("company", "title", "start_date", "end_date"),
        )
    for item in resume.internships:
        add_entry(
            category="internship",
            section="internship",
            item=item,
            fields=("company", "title", "start_date", "end_date"),
        )
    for item in resume.project_experiences:
        add_entry(
            category="project",
            section="project",
            item=item,
            fields=("name", "role", "project_type", "start_date", "end_date"),
        )
        for technology in item.technologies:
            for fact_text in _parts(technology, item.source_text):
                candidates.append(
                    (
                        "project",
                        f"resume.project.{item.id}",
                        item.source_text,
                        fact_text,
                        _metadata(item, section="project"),
                    )
                )
    for item in resume.campus_experiences:
        add_entry(
            category="campus",
            section="campus",
            item=item,
            fields=("organization", "role", "start_date", "end_date"),
        )
    for index, skill in enumerate(resume.skills, start=1):
        for fact_text in _parts(skill.name, skill.source_text):
            metadata: dict[str, str | bool] = {"section": "skill", "skill_index": str(index)}
            if skill.category is not None:
                metadata["skill_category"] = skill.category
            if skill.proficiency is not None and skill.proficiency in skill.source_text:
                metadata["proficiency"] = skill.proficiency
            candidates.append(
                ("skill", f"resume.skill.{index:03d}", skill.source_text, fact_text, metadata)
            )

    seen: set[str] = set()
    facts: list[Fact] = []
    for category, source, source_text, normalized, metadata in candidates:
        key = " ".join(normalized.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        facts.append(
            Fact(
                id=f"fact_{len(facts) + 1:03d}",
                category=category,
                source=source,
                source_text=source_text,
                normalized_fact=normalized,
                status=FactStatus.CONFIRMED,
                metadata=metadata,
            )
        )
    return FactLedger(
        candidate_id=candidate_id,
        resume_id=resume.resume_id,
        resume_version=resume.version,
        facts=facts,
    )
