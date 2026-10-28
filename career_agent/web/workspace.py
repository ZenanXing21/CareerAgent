"""Validated local workspace snapshots, without executable deserialization."""

from __future__ import annotations

import base64
import os
from dataclasses import fields
from pathlib import Path

from pydantic import BaseModel, Field

from career_agent.jobs.models import Job
from career_agent.onboarding.models import CandidateIntakeDraft
from career_agent.product.service import InitialResumeResult, TailoredJobResult
from career_agent.resume.models import Resume
from career_agent.resume.renderer import render_resume_html
from career_agent.resume.studio import DesignedResumeTemplate, SavedResumeTemplate


class CandidateRecord(BaseModel):
    raw_resume: Resume
    display_resume: Resume
    raw_preview_html: str = ""
    polished_preview_html: str = ""
    raw_hometown: str | None = None
    polished_hometown: str | None = None
    photo_asset: str | None = None
    confirmed_resume: Resume | None = None
    confirmed: bool = False
    template_id: str = "modern"
    section_order: list[str] = Field(default_factory=list)
    custom_template_base64: str | None = None
    jobs: dict[str, Job] = Field(default_factory=dict)
    tailored_results: dict[str, TailoredJobResult] = Field(default_factory=dict)
    resume_chat: list[dict[str, str]] = Field(default_factory=list)
    omitted_fields: list[str] = Field(default_factory=list)
    designed_template: DesignedResumeTemplate | None = None
    designed_templates: list[SavedResumeTemplate] = Field(default_factory=list)
    active_design_id: str | None = None
    template_proposal: SavedResumeTemplate | None = None
    template_chat: list[dict[str, str]] = Field(default_factory=list)
    semantic_keywords: list[str] = Field(default_factory=list)


class IntakeRecord(BaseModel):
    draft: CandidateIntakeDraft
    messages: list[dict[str, str]] = Field(default_factory=list)
    phase: str = "required"
    optional_topic_index: int = 0
    covered_optional_topics: set[str] = Field(default_factory=set)
    preview_result: InitialResumeResult | None = None
    pending_clarification: str | None = None
    required_guidance_shown: bool = False
    optional_guidance_shown: bool = False


class WorkspaceRecords(BaseModel):
    candidates: dict[str, CandidateRecord] = Field(default_factory=dict)
    intakes: dict[str, IntakeRecord] = Field(default_factory=dict)


def candidate_from_record(record: CandidateRecord, factory):
    values = {
        item.name: getattr(record, item.name)
        for item in fields(factory)
        if item.name != "custom_template"
    }
    values["custom_template"] = (
        base64.b64decode(record.custom_template_base64, validate=True)
        if record.custom_template_base64
        else None
    )
    values["raw_preview_html"] = record.raw_preview_html or render_resume_html(
        record.raw_resume, photo_asset=record.photo_asset, hometown=record.raw_hometown
    )
    values["polished_preview_html"] = record.polished_preview_html or render_resume_html(
        record.display_resume, photo_asset=record.photo_asset, hometown=record.polished_hometown
    )
    return factory(**values)


def intake_from_record(record: IntakeRecord, factory):
    values = {item.name: getattr(record, item.name) for item in fields(factory)}
    if values["phase"] not in {"required", "optional", "final"}:
        raise ValueError("invalid intake phase")
    return factory(**values)


class WorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> WorkspaceRecords:
        if not self.path.exists():
            return WorkspaceRecords()
        return WorkspaceRecords.model_validate_json(self.path.read_text(encoding="utf-8"))

    def snapshot(self, candidates: dict, intakes: dict) -> str:
        records = {}
        for key, candidate in candidates.items():
            values = {
                name: getattr(candidate, name)
                for name in CandidateRecord.model_fields
                if name != "custom_template_base64"
            }
            values["custom_template_base64"] = (
                base64.b64encode(candidate.custom_template).decode("ascii")
                if candidate.custom_template
                else None
            )
            records[key] = CandidateRecord(**values)
        intake_records = {
            key: IntakeRecord(**{name: getattr(value, name) for name in IntakeRecord.model_fields})
            for key, value in intakes.items()
        }
        return WorkspaceRecords(candidates=records, intakes=intake_records).model_dump_json()

    def write(self, data: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(data, encoding="utf-8")
        os.replace(temporary, self.path)
