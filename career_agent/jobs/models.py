"""Job search and normalized job domain models."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator, model_validator

from career_agent.models import (
    DomainModel,
    NonEmptyStr,
    Ratio,
    UTCDateTime,
    _unique_strings,
    utc_now,
)


class JobSearchQuery(DomainModel):
    keyword: NonEmptyStr
    city: NonEmptyStr
    salary_min: int | None = Field(default=None, ge=0)
    page: int = Field(default=1, ge=1)
    employment_types: list[NonEmptyStr] = Field(default_factory=list)
    experience_levels: list[NonEmptyStr] = Field(default_factory=list)
    company_names: list[NonEmptyStr] = Field(default_factory=list)
    industries: list[NonEmptyStr] = Field(default_factory=list)
    company_sizes: list[NonEmptyStr] = Field(default_factory=list)
    preferred_keywords: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator(
        "employment_types",
        "experience_levels",
        "company_names",
        "industries",
        "company_sizes",
        "preferred_keywords",
    )
    @classmethod
    def unique_filters(cls, values: list[str], info: object) -> list[str]:
        return _unique_strings(values, getattr(info, "field_name", "values"))


class Job(DomainModel):
    id: NonEmptyStr
    platform: NonEmptyStr
    external_job_id: NonEmptyStr
    external_job_kind: NonEmptyStr | None = None
    title: NonEmptyStr
    company: NonEmptyStr
    location: NonEmptyStr
    salary_text: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None
    detail_text: NonEmptyStr | None = None
    source_url: NonEmptyStr | None = None
    apply_url: NonEmptyStr | None = None
    department: NonEmptyStr | None = None
    employment_type: NonEmptyStr | None = None
    industry: NonEmptyStr | None = None
    company_size: NonEmptyStr | None = None
    detail_verified: bool = False
    collected_at: UTCDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def verified_details_have_source_text(self) -> Job:
        if self.detail_verified and self.detail_text is None:
            raise ValueError("detail_verified jobs require detail_text")
        return self


class MatchResult(DomainModel):
    """Deterministic score and requirement groupings for a job."""

    score: Ratio
    strong_matches: list[NonEmptyStr] = Field(default_factory=list)
    partial_matches: list[NonEmptyStr] = Field(default_factory=list)
    missing_requirements: list[NonEmptyStr] = Field(default_factory=list)
    explanation: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("strong_matches", "partial_matches", "missing_requirements")
    @classmethod
    def unique_requirement_ids(cls, values: list[str], info: object) -> list[str]:
        return _unique_strings(values, getattr(info, "field_name", "values"))

    @model_validator(mode="after")
    def requirement_groups_are_disjoint(self) -> MatchResult:
        groups = [
            set(self.strong_matches),
            set(self.partial_matches),
            set(self.missing_requirements),
        ]
        if any(groups[left] & groups[right] for left in range(3) for right in range(left + 1, 3)):
            raise ValueError("match result requirement groups must be disjoint")
        return self
