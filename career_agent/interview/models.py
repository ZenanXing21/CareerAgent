"""Structured interview questions and answer feedback."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from career_agent.models import DomainModel, NonEmptyStr


class InterviewQuestion(DomainModel):
    id: NonEmptyStr
    requirement_id: NonEmptyStr | None = None
    requirement_text: NonEmptyStr
    question: NonEmptyStr
    follow_up: NonEmptyStr
    match_level: Literal["strong", "partial", "gap", "unknown"]
    evidence_fact_ids: list[NonEmptyStr] = Field(default_factory=list)
    talking_points: list[NonEmptyStr] = Field(default_factory=list)


class InterviewPlan(DomainModel):
    job_id: NonEmptyStr
    job_title: NonEmptyStr
    questions: Annotated[list[InterviewQuestion], Field(min_length=1)]


class InterviewFeedback(DomainModel):
    question_id: NonEmptyStr
    strengths: list[NonEmptyStr] = Field(default_factory=list)
    improvements: list[NonEmptyStr] = Field(default_factory=list)
    follow_up_question: NonEmptyStr | None = None
