"""State schema for the top-level Career Agent graph."""

from __future__ import annotations

from typing import TypedDict

from career_agent.jd.models import JDAnalysis
from career_agent.jobs.models import Job, MatchResult
from career_agent.models import (
    ApplicationStatus,
    CandidateProfile,
    ErrorInfo,
)
from career_agent.resume.models import (
    EvidenceMatch,
    FactLedger,
    Resume,
    TailoredResume,
    TailorPlan,
    ValidationReport,
)


class CareerState(TypedDict, total=False):
    candidate_profile: CandidateProfile
    base_resume: Resume
    fact_ledger: FactLedger
    jobs: list[Job]
    job_cursor: int
    current_job: Job | None
    jd_analysis: JDAnalysis
    evidence_matches: list[EvidenceMatch]
    match_result: MatchResult
    tailor_plan: TailorPlan
    tailored_resume: TailoredResume
    validation_report: ValidationReport
    edited_resume: TailoredResume
    human_decision: str
    application_status: ApplicationStatus
    match_threshold: float
    require_semantic_review: bool
    error: ErrorInfo
    retry_count: int
