"""Cross-module domain models and stable enums."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

NonEmptyStr = Annotated[str, Field(min_length=1)]
Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


def _normalize_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


UTCDateTime = Annotated[AwareDatetime, AfterValidator(_normalize_utc)]


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for persisted system events."""

    return datetime.now(UTC)


def _unique_strings(values: list[str], field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class DomainModel(BaseModel):
    """Strict base for domain data crossing component boundaries."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class FactStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"
    UNSURE = "UNSURE"
    WITHHELD = "WITHHELD"
    CONFLICT = "CONFLICT"


class EvidenceStatus(str, Enum):
    STRONG_MATCH = "STRONG_MATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    NO_MATCH = "NO_MATCH"
    UNKNOWN = "UNKNOWN"


class ApplicationStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    ANALYZED = "ANALYZED"
    MATCHED = "MATCHED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    INTERVIEW = "INTERVIEW"
    SKIPPED = "SKIPPED"


class CandidateProfile(DomainModel):
    """Explicit search preferences; these are not candidate ability facts."""

    candidate_id: NonEmptyStr
    target_roles: Annotated[list[NonEmptyStr], Field(min_length=1)]
    cities: list[NonEmptyStr] = Field(default_factory=list)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    employment_types: list[NonEmptyStr] = Field(default_factory=list)
    other_constraints: dict[NonEmptyStr, NonEmptyStr] = Field(default_factory=dict)

    @field_validator("target_roles", "cities", "employment_types")
    @classmethod
    def unique_lists(cls, values: list[str], info: object) -> list[str]:
        return _unique_strings(values, getattr(info, "field_name", "values"))

    @model_validator(mode="after")
    def validate_salary_range(self) -> CandidateProfile:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return self


class ApplicationRecord(DomainModel):
    job_id: NonEmptyStr
    platform: NonEmptyStr
    status: ApplicationStatus
    match_score: Ratio | None = None
    resume_version: NonEmptyStr | None = None
    created_at: UTCDateTime = Field(default_factory=utc_now)
    updated_at: UTCDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_timestamps(self) -> ApplicationRecord:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")
        return self


class ErrorInfo(DomainModel):
    """A deliberately small, safe-to-display workflow error summary."""

    code: NonEmptyStr
    message: Annotated[str, Field(min_length=1, max_length=500)]
    node: NonEmptyStr
    operation: NonEmptyStr | None = None
    retryable: bool = False
    job_id: NonEmptyStr | None = None
