"""Resume, fact-ledger, evidence, and tailoring domain models."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import TYPE_CHECKING, Annotated

from pydantic import Field, JsonValue, field_validator, model_validator

from career_agent.models import (
    DomainModel,
    EvidenceStatus,
    FactStatus,
    NonEmptyStr,
    Ratio,
    UTCDateTime,
    _unique_strings,
    utc_now,
)

if TYPE_CHECKING:
    from career_agent.jd.models import JDAnalysis


class ExperienceType(str, Enum):
    WORK = "work"
    INTERNSHIP = "internship"


class PersonalInfo(DomainModel):
    name: NonEmptyStr | None = None
    email: NonEmptyStr | None = None
    phone: NonEmptyStr | None = None
    location: NonEmptyStr | None = None
    hometown: NonEmptyStr | None = None
    links: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("links")
    @classmethod
    def unique_links(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "links")


class Education(DomainModel):
    id: NonEmptyStr
    source_text: NonEmptyStr
    school: NonEmptyStr | None = None
    degree: NonEmptyStr | None = None
    major: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    description: NonEmptyStr | None = None


class WorkExperience(DomainModel):
    id: NonEmptyStr
    source_text: NonEmptyStr
    experience_type: ExperienceType
    company: NonEmptyStr | None = None
    title: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    description: NonEmptyStr | None = None


class ProjectExperience(DomainModel):
    id: NonEmptyStr
    source_text: NonEmptyStr
    name: NonEmptyStr | None = None
    role: NonEmptyStr | None = None
    project_type: NonEmptyStr | None = None
    is_course_project: bool | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    description: NonEmptyStr | None = None
    technologies: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("technologies")
    @classmethod
    def unique_technologies(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "technologies")


class CampusExperience(DomainModel):
    id: NonEmptyStr
    source_text: NonEmptyStr
    organization: NonEmptyStr | None = None
    role: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    description: NonEmptyStr | None = None


class Skill(DomainModel):
    name: NonEmptyStr
    source_text: NonEmptyStr
    category: NonEmptyStr | None = None
    proficiency: NonEmptyStr | None = None


class Resume(DomainModel):
    resume_id: NonEmptyStr
    version: NonEmptyStr
    raw_text: NonEmptyStr
    summary: NonEmptyStr | None = None
    section_titles: dict[str, Annotated[str, Field(min_length=1, max_length=30)]] = Field(
        default_factory=dict
    )
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    educations: list[Education] = Field(default_factory=list)
    work_experiences: list[WorkExperience] = Field(default_factory=list)
    internships: list[WorkExperience] = Field(default_factory=list)
    project_experiences: list[ProjectExperience] = Field(default_factory=list)
    campus_experiences: list[CampusExperience] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)

    @field_validator("section_titles")
    @classmethod
    def known_section_titles(cls, values: dict[str, str]) -> dict[str, str]:
        allowed = {"summary", "education", "work", "internship", "experience", "campus", "skills"}
        if unknown := values.keys() - allowed:
            raise ValueError(f"unknown section title keys: {sorted(unknown)}")
        if any(not value.strip() for value in values.values()):
            raise ValueError("section titles cannot be blank")
        return {key: value.strip() for key, value in values.items()}

    @model_validator(mode="after")
    def validate_experience_buckets_and_ids(self) -> Resume:
        if any(item.experience_type is ExperienceType.INTERNSHIP for item in self.work_experiences):
            raise ValueError("internships must be stored in internships, not work_experiences")
        if any(item.experience_type is not ExperienceType.INTERNSHIP for item in self.internships):
            raise ValueError("internships may only contain internship experiences")

        collections = {
            "educations": self.educations,
            "work_experiences": self.work_experiences,
            "internships": self.internships,
            "project_experiences": self.project_experiences,
            "campus_experiences": self.campus_experiences,
        }
        for name, items in collections.items():
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} ids must be unique")

        all_entry_ids = [item.id for items in collections.values() for item in items]
        if len(all_entry_ids) != len(set(all_entry_ids)):
            raise ValueError("resume entry ids must be unique across all sections")
        return self


class ResumeAgentEdit(DomainModel):
    """A conversational resume edit plus the user-facing change summary."""

    assistant_message: Annotated[str, Field(min_length=1, max_length=1000)]
    resume: Resume
    hometown: NonEmptyStr | None = None


class ResumeInspection(DomainModel):
    """Deterministic completeness summary for a parsed resume."""

    has_name: bool
    education_count: Annotated[int, Field(ge=0)]
    work_count: Annotated[int, Field(ge=0)]
    internship_count: Annotated[int, Field(ge=0)]
    project_count: Annotated[int, Field(ge=0)]
    campus_count: Annotated[int, Field(ge=0)]
    skill_count: Annotated[int, Field(ge=0)]
    missing_fields: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("missing_fields")
    @classmethod
    def unique_missing_fields(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "missing_fields")


class Fact(DomainModel):
    id: NonEmptyStr
    category: NonEmptyStr
    source: NonEmptyStr
    source_text: NonEmptyStr
    normalized_fact: NonEmptyStr
    status: FactStatus
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class FactLedger(DomainModel):
    candidate_id: NonEmptyStr
    resume_id: NonEmptyStr
    resume_version: NonEmptyStr
    facts: list[Fact] = Field(default_factory=list)
    built_at: UTCDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def fact_ids_are_unique(self) -> FactLedger:
        ids = [fact.id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact ids must be unique")
        return self


class EvidenceMatch(DomainModel):
    requirement_id: NonEmptyStr
    status: EvidenceStatus
    evidence_fact_ids: list[NonEmptyStr] = Field(default_factory=list)
    reasoning_summary: Annotated[str, Field(min_length=1, max_length=500)]
    confidence: Ratio

    @field_validator("evidence_fact_ids")
    @classmethod
    def unique_fact_ids(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "evidence_fact_ids")

    @model_validator(mode="after")
    def evidence_shape_matches_status(self) -> EvidenceMatch:
        positive = {EvidenceStatus.STRONG_MATCH, EvidenceStatus.PARTIAL_MATCH}
        if self.status in positive and not self.evidence_fact_ids:
            raise ValueError("positive evidence matches require at least one evidence fact")
        if self.status not in positive and self.evidence_fact_ids:
            raise ValueError("NO_MATCH and UNKNOWN must not claim supporting evidence facts")
        return self


class TailorPlan(DomainModel):
    highlight_fact_ids: list[NonEmptyStr] = Field(default_factory=list)
    deemphasize_fact_ids: list[NonEmptyStr] = Field(default_factory=list)
    section_order: list[NonEmptyStr] = Field(default_factory=list)
    target_keywords: list[NonEmptyStr] = Field(default_factory=list)
    gaps: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator(
        "highlight_fact_ids",
        "deemphasize_fact_ids",
        "section_order",
        "target_keywords",
        "gaps",
    )
    @classmethod
    def unique_values(cls, values: list[str], info: object) -> list[str]:
        return _unique_strings(values, getattr(info, "field_name", "values"))

    @model_validator(mode="after")
    def fact_groups_are_disjoint(self) -> TailorPlan:
        overlap = set(self.highlight_fact_ids) & set(self.deemphasize_fact_ids)
        if overlap:
            raise ValueError("a fact cannot be both highlighted and deemphasized")
        return self


class TailoredBullet(DomainModel):
    text: NonEmptyStr
    source_fact_ids: Annotated[list[NonEmptyStr], Field(min_length=1)]

    @field_validator("source_fact_ids")
    @classmethod
    def unique_sources(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "source_fact_ids")


class DraftSuggestion(DomainModel):
    """Optional JD-aligned draft text that is not a verified resume fact."""

    section: NonEmptyStr
    text: Annotated[str, Field(min_length=1, max_length=400)]


class ResumeAnchor(DomainModel):
    """Immutable source fields copied into a tailored version for comparison."""

    source_entry_id: NonEmptyStr
    section: NonEmptyStr
    school: NonEmptyStr | None = None
    degree: NonEmptyStr | None = None
    major: NonEmptyStr | None = None
    company: NonEmptyStr | None = None
    job_title: NonEmptyStr | None = None
    project_name: NonEmptyStr | None = None
    project_role: NonEmptyStr | None = None
    project_type: NonEmptyStr | None = None
    is_course_project: bool | None = None
    campus_organization: NonEmptyStr | None = None
    campus_role: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None


class TailoredResume(DomainModel):
    source_resume_id: NonEmptyStr
    source_resume_version: NonEmptyStr
    target_job_id: NonEmptyStr
    sections: Annotated[dict[NonEmptyStr, list[TailoredBullet]], Field(min_length=1)]
    suggestions: list[DraftSuggestion] = Field(default_factory=list)
    anchors: list[ResumeAnchor] = Field(default_factory=list)

    @model_validator(mode="after")
    def sections_have_bullets(self) -> TailoredResume:
        empty_sections = [name for name, bullets in self.sections.items() if not bullets]
        if empty_sections:
            raise ValueError("tailored resume sections must contain at least one bullet")
        anchor_ids = [anchor.source_entry_id for anchor in self.anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("tailored resume anchor source_entry_ids must be unique")
        return self

    def iter_bullets(self) -> Iterable[TailoredBullet]:
        for bullets in self.sections.values():
            yield from bullets


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationIssue(DomainModel):
    code: NonEmptyStr
    severity: ValidationSeverity
    message: NonEmptyStr
    section: NonEmptyStr | None = None
    bullet_index: Annotated[int | None, Field(ge=0)] = None


class SemanticReview(DomainModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def result_matches_issues(self) -> SemanticReview:
        has_errors = any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)
        if self.passed == has_errors:
            raise ValueError("semantic review passed must be the inverse of error presence")
        return self


class ValidationReport(DomainModel):
    passed: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    semantic_review_required: bool = False
    semantic_review_performed: bool = False

    @model_validator(mode="after")
    def result_matches_issues(self) -> ValidationReport:
        has_errors = any(issue.severity is ValidationSeverity.ERROR for issue in self.issues)
        if self.passed == has_errors:
            raise ValueError("validation passed must be the inverse of error presence")
        if self.semantic_review_performed and not self.semantic_review_required:
            raise ValueError("semantic review cannot be performed when it was not required")
        return self


class ReferenceValidationError(ValueError):
    """Raised when structured LLM output escapes a current-run ID allow-list."""


def _facts_by_id(ledger: FactLedger) -> dict[str, Fact]:
    return {fact.id: fact for fact in ledger.facts}


def _require_fact_ids(
    ids: Iterable[str],
    ledger: FactLedger,
    *,
    context: str,
    confirmed_only: bool,
) -> None:
    facts = _facts_by_id(ledger)
    requested = list(ids)
    missing = sorted(set(requested) - set(facts))
    if missing:
        raise ReferenceValidationError(f"{context} references unknown fact ids: {missing}")
    if confirmed_only:
        unconfirmed = sorted(
            fact_id
            for fact_id in set(requested)
            if facts[fact_id].status is not FactStatus.CONFIRMED
        )
        if unconfirmed:
            raise ReferenceValidationError(
                f"{context} references facts that are not CONFIRMED: {unconfirmed}"
            )


def validate_evidence_references(
    matches: Iterable[EvidenceMatch],
    jd_analysis: JDAnalysis,
    ledger: FactLedger,
    *,
    confirmed_only: bool = True,
    require_complete: bool = True,
) -> None:
    """Validate EvidenceMatch output against the current JD and ledger allow-lists."""

    requirement_ids = {requirement.id for requirement in jd_analysis.requirements}
    seen: set[str] = set()
    for match in matches:
        if match.requirement_id not in requirement_ids:
            raise ReferenceValidationError(
                f"evidence references unknown requirement id: {match.requirement_id}"
            )
        if match.requirement_id in seen:
            raise ReferenceValidationError(
                f"multiple evidence matches reference requirement id: {match.requirement_id}"
            )
        seen.add(match.requirement_id)
        _require_fact_ids(
            match.evidence_fact_ids,
            ledger,
            context=f"evidence for {match.requirement_id}",
            confirmed_only=confirmed_only,
        )
    if require_complete:
        missing = sorted(requirement_ids - seen)
        if missing:
            raise ReferenceValidationError(
                f"evidence is missing matches for requirement ids: {missing}"
            )


def validate_tailor_plan_references(
    plan: TailorPlan,
    ledger: FactLedger,
    *,
    confirmed_only: bool = True,
) -> None:
    """Validate every fact selected by a plan against the current ledger."""

    _require_fact_ids(
        [*plan.highlight_fact_ids, *plan.deemphasize_fact_ids],
        ledger,
        context="tailor plan",
        confirmed_only=confirmed_only,
    )


def validate_tailored_resume_references(
    tailored_resume: TailoredResume,
    source_resume: Resume,
    ledger: FactLedger,
    *,
    expected_job_id: str | None = None,
    confirmed_only: bool = True,
) -> None:
    """Reject stale resume versions, wrong jobs, dangling facts, and unconfirmed sources."""

    source_is_current = (
        source_resume.resume_id == ledger.resume_id
        and source_resume.version == ledger.resume_version
    )
    if not source_is_current:
        raise ReferenceValidationError("source resume does not match the current fact ledger")
    if tailored_resume.source_resume_id != ledger.resume_id:
        raise ReferenceValidationError("tailored resume does not reference the current resume")
    if tailored_resume.source_resume_version != ledger.resume_version:
        raise ReferenceValidationError(
            "tailored resume does not reference the current resume version"
        )
    if expected_job_id is not None and tailored_resume.target_job_id != expected_job_id:
        raise ReferenceValidationError("tailored resume does not reference the current job")

    expected_anchors = _resume_anchors(source_resume)
    actual_anchors = {anchor.source_entry_id: anchor for anchor in tailored_resume.anchors}
    if set(actual_anchors) != set(expected_anchors):
        missing = sorted(set(expected_anchors) - set(actual_anchors))
        extra = sorted(set(actual_anchors) - set(expected_anchors))
        raise ReferenceValidationError(
            f"tailored resume anchor coverage mismatch; missing={missing}, extra={extra}"
        )
    changed = sorted(
        entry_id
        for entry_id, expected in expected_anchors.items()
        if actual_anchors[entry_id] != expected
    )
    if changed:
        raise ReferenceValidationError(
            f"tailored resume changed immutable anchors for entry ids: {changed}"
        )
    for index, bullet in enumerate(tailored_resume.iter_bullets()):
        _require_fact_ids(
            bullet.source_fact_ids,
            ledger,
            context=f"tailored bullet {index}",
            confirmed_only=confirmed_only,
        )


def _resume_anchors(resume: Resume) -> dict[str, ResumeAnchor]:
    anchors: dict[str, ResumeAnchor] = {}
    for item in resume.educations:
        anchors[item.id] = ResumeAnchor(
            source_entry_id=item.id,
            section="education",
            school=item.school,
            degree=item.degree,
            major=item.major,
            start_date=item.start_date,
            end_date=item.end_date,
        )
    for section, items in (
        ("work", resume.work_experiences),
        ("internship", resume.internships),
    ):
        for item in items:
            anchors[item.id] = ResumeAnchor(
                source_entry_id=item.id,
                section=section,
                company=item.company,
                job_title=item.title,
                start_date=item.start_date,
                end_date=item.end_date,
            )
    for item in resume.project_experiences:
        anchors[item.id] = ResumeAnchor(
            source_entry_id=item.id,
            section="project",
            project_name=item.name,
            project_role=item.role,
            project_type=item.project_type,
            is_course_project=item.is_course_project,
            start_date=item.start_date,
            end_date=item.end_date,
        )
    for item in resume.campus_experiences:
        anchors[item.id] = ResumeAnchor(
            source_entry_id=item.id,
            section="campus",
            campus_organization=item.organization,
            campus_role=item.role,
            start_date=item.start_date,
            end_date=item.end_date,
        )
    return anchors


# Concise aliases for business-code call sites.
validate_evidence_matches = validate_evidence_references
validate_tailor_plan = validate_tailor_plan_references
validate_tailored_resume = validate_tailored_resume_references
