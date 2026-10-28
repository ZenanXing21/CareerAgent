"""Atomic job-description analysis models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator, model_validator

from career_agent.models import DomainModel, NonEmptyStr, _unique_strings


class JDRequirement(DomainModel):
    id: NonEmptyStr
    text: NonEmptyStr
    category: NonEmptyStr
    priority: Annotated[int, Field(ge=1, le=3)]
    required: bool
    keywords: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def unique_keywords(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "keywords")


class JDAnalysis(DomainModel):
    job_id: NonEmptyStr
    job_title: NonEmptyStr | None = None
    source_text: NonEmptyStr
    requirements: list[JDRequirement] = Field(default_factory=list)
    summary: Annotated[str, Field(min_length=1, max_length=1000)] | None = None

    @model_validator(mode="after")
    def requirement_ids_are_unique(self) -> JDAnalysis:
        ids = [requirement.id for requirement in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")
        texts = [requirement.text.casefold() for requirement in self.requirements]
        if len(texts) != len(set(texts)):
            raise ValueError("requirement texts must be unique")
        return self
