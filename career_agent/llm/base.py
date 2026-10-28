"""Narrow structured-output boundary used by Phase 2 services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from career_agent.jd.models import JDAnalysis
    from career_agent.jobs.models import MatchResult
    from career_agent.onboarding.models import (
        CandidateIntakeDraft,
        ExperienceDraft,
        IntakeConversationUpdate,
        IntakeImageAnalysis,
        IntakePolish,
        IntakeProfilePolish,
        PolishedExperience,
    )
    from career_agent.resume.models import (
        EvidenceMatch,
        FactLedger,
        Resume,
        ResumeAgentEdit,
        SemanticReview,
        TailoredResume,
        TailorPlan,
        ValidationReport,
    )


class LLMError(RuntimeError):
    """Base error for a structured LLM operation."""


class LLMProviderError(LLMError):
    """A provider call failed before valid structured output was returned."""


class StructuredOutputError(LLMError):
    """Structured output is invalid or violates a source boundary."""


class LLMProvider(Protocol):
    """Provider-independent, async structured-output operations for Phase 2."""

    async def parse_resume(self, *, resume_id: str, version: str, raw_text: str) -> Resume: ...

    async def polish_candidate_intake(self, *, draft: CandidateIntakeDraft) -> IntakePolish: ...

    async def polish_candidate_profile(
        self, *, draft: CandidateIntakeDraft
    ) -> IntakeProfilePolish: ...

    async def polish_candidate_experience(
        self, *, experience: ExperienceDraft, source_index: int
    ) -> PolishedExperience: ...

    async def update_candidate_intake(
        self,
        *,
        draft: CandidateIntakeDraft,
        message: str,
        conversation: list[dict[str, str]],
    ) -> IntakeConversationUpdate: ...

    async def analyze_intake_image(self, *, data_url: str) -> IntakeImageAnalysis: ...

    async def edit_resume(
        self, *, resume: Resume, instruction: str, conversation: list[dict[str, str]]
    ) -> ResumeAgentEdit: ...

    async def parse_jd(self, *, job_id: str, source_text: str) -> JDAnalysis: ...

    async def match_evidence(
        self, *, jd_analysis: JDAnalysis, fact_ledger: FactLedger
    ) -> list[EvidenceMatch]: ...

    async def build_tailor_plan(
        self,
        *,
        resume: Resume,
        fact_ledger: FactLedger,
        jd_analysis: JDAnalysis,
        evidence_matches: list[EvidenceMatch],
        match_result: MatchResult,
    ) -> TailorPlan: ...

    async def rewrite_resume(
        self,
        *,
        source_resume: Resume,
        fact_ledger: FactLedger,
        jd_analysis: JDAnalysis,
        tailor_plan: TailorPlan,
        previous_resume: TailoredResume | None = None,
        validation_report: ValidationReport | None = None,
        allow_suggestions: bool = False,
    ) -> TailoredResume: ...

    async def semantic_review(
        self,
        *,
        tailored_resume: TailoredResume,
        source_resume: Resume,
        fact_ledger: FactLedger,
        jd_analysis: JDAnalysis,
    ) -> SemanticReview: ...
