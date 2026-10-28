"""Validated MCP request/response and error models."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from career_agent.jobs.models import Job
from career_agent.models import DomainModel, NonEmptyStr


class JobPlatformErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    ADAPTER_UNAVAILABLE = "ADAPTER_UNAVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_FOUND = "NOT_FOUND"
    UPSTREAM_FAILURE = "UPSTREAM_FAILURE"
    TIMEOUT = "TIMEOUT"


class JobPlatformToolError(DomainModel):
    code: JobPlatformErrorCode
    message: NonEmptyStr
    retryable: bool = False
    platform: NonEmptyStr | None = None


class JobSearchResponse(DomainModel):
    jobs: list[Job] = Field(default_factory=list)
    unavailable_platforms: list[NonEmptyStr] = Field(default_factory=list)


class JobDetailResponse(DomainModel):
    job: Job


class JobSearchToolResult(DomainModel):
    result: JobSearchResponse | None = None
    error: JobPlatformToolError | None = None

    @model_validator(mode="after")
    def exactly_one_outcome(self) -> JobSearchToolResult:
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of result or error is required")
        return self


class JobDetailToolResult(DomainModel):
    result: JobDetailResponse | None = None
    error: JobPlatformToolError | None = None

    @model_validator(mode="after")
    def exactly_one_outcome(self) -> JobDetailToolResult:
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of result or error is required")
        return self
