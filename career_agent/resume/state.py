"""State schema for the standalone resume-tailoring graph."""

from __future__ import annotations

from typing import TypedDict

from career_agent.jd.models import JDAnalysis
from career_agent.jobs.models import MatchResult
from career_agent.resume.models import (
    EvidenceMatch,
    FactLedger,
    Resume,
    TailoredResume,
    TailorPlan,
    ValidationReport,
)


class ResumeTailorState(TypedDict, total=False):
    candidate_id: str
    resume_id: str
    resume_version: str
    raw_resume_text: str
    job_id: str
    jd_text: str
    resume: Resume
    fact_ledger: FactLedger
    jd_analysis: JDAnalysis
    evidence_matches: list[EvidenceMatch]
    match_result: MatchResult
    tailor_plan: TailorPlan
    tailored_resume: TailoredResume
    validation_report: ValidationReport
    require_semantic_review: bool
    allow_suggestions: bool
    retry_count: int
