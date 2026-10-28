"""Fact-bound resume rewriting service."""

from __future__ import annotations

from pydantic import ValidationError

from career_agent.jd.models import JDAnalysis
from career_agent.llm.base import LLMError, LLMProvider, LLMProviderError, StructuredOutputError
from career_agent.resume.models import (
    FactLedger,
    ReferenceValidationError,
    Resume,
    TailoredResume,
    TailorPlan,
    ValidationReport,
    _resume_anchors,
    validate_tailored_resume_references,
)


class ResumeRewriter:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def rewrite(
        self,
        *,
        source_resume: Resume,
        fact_ledger: FactLedger,
        jd_analysis: JDAnalysis,
        tailor_plan: TailorPlan,
        previous_resume: TailoredResume | None = None,
        validation_report: ValidationReport | None = None,
        allow_suggestions: bool = False,
    ) -> TailoredResume:
        try:
            kwargs = {
                "source_resume": source_resume,
                "fact_ledger": fact_ledger,
                "jd_analysis": jd_analysis,
                "tailor_plan": tailor_plan,
                "previous_resume": previous_resume,
                "validation_report": validation_report,
            }
            if allow_suggestions:
                kwargs["allow_suggestions"] = True
            tailored = await self._provider.rewrite_resume(**kwargs)
        except LLMError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StructuredOutputError("rewriter returned invalid structured output") from exc
        except Exception as exc:
            raise LLMProviderError("resume rewrite provider call failed") from exc
        if not isinstance(tailored, TailoredResume):
            raise StructuredOutputError("rewriter did not return a TailoredResume")
        payload = tailored.model_dump()
        payload["anchors"] = [
            anchor.model_dump() for anchor in _resume_anchors(source_resume).values()
        ]
        allowed = {"summary", "education", "work", "internship", "project", "campus", "skills"}
        payload["suggestions"] = (
            [
                suggestion
                for suggestion in payload.get("suggestions", [])
                if suggestion["section"] in allowed
            ][:3]
            if allow_suggestions
            else []
        )
        try:
            tailored = TailoredResume.model_validate(payload)
        except ValidationError as exc:
            raise StructuredOutputError("rewriter output failed domain validation") from exc
        try:
            validate_tailored_resume_references(
                tailored,
                source_resume,
                fact_ledger,
                expected_job_id=jd_analysis.job_id,
            )
        except ReferenceValidationError as exc:
            raise StructuredOutputError(str(exc)) from exc
        return tailored
