"""Deterministic resume validation with an optional semantic review."""

from __future__ import annotations

import re

from pydantic import ValidationError

from career_agent.jd.models import JDAnalysis
from career_agent.llm.base import LLMError, LLMProvider, LLMProviderError, StructuredOutputError
from career_agent.resume.models import (
    FactLedger,
    ReferenceValidationError,
    Resume,
    SemanticReview,
    TailoredResume,
    TailorPlan,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    validate_tailored_resume_references,
)

_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
_ESCALATION_TERMS = ("精通", "主导", "负责整个架构", "显著提升")


def validate_resume_deterministically(
    *,
    tailored_resume: TailoredResume,
    source_resume: Resume,
    fact_ledger: FactLedger,
    jd_analysis: JDAnalysis,
    tailor_plan: TailorPlan | None = None,
    semantic_review_required: bool = False,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    try:
        validate_tailored_resume_references(
            tailored_resume,
            source_resume,
            fact_ledger,
            expected_job_id=jd_analysis.job_id,
        )
    except ReferenceValidationError as exc:
        issues.append(_error("INVALID_REFERENCE_OR_ANCHOR", str(exc)))

    facts = {fact.id: fact for fact in fact_ledger.facts}
    seen: dict[str, tuple[str, int]] = {}
    for section, bullets in tailored_resume.sections.items():
        for index, bullet in enumerate(bullets):
            normalized = " ".join(bullet.text.casefold().split())
            if normalized in seen:
                issues.append(
                    _error(
                        "DUPLICATE_BULLET",
                        "duplicate tailored bullet",
                        section=section,
                        bullet_index=index,
                    )
                )
            else:
                seen[normalized] = (section, index)
            source_text = " ".join(
                facts[fact_id].source_text for fact_id in bullet.source_fact_ids if fact_id in facts
            )
            for number in _NUMBER.findall(bullet.text):
                if number not in source_text:
                    issues.append(
                        _error(
                            "UNSUPPORTED_NUMBER",
                            f"number {number!r} is absent from referenced source facts",
                            section=section,
                            bullet_index=index,
                        )
                    )
            for term in _ESCALATION_TERMS:
                if term in bullet.text and term not in source_text:
                    issues.append(
                        _error(
                            "UNSUPPORTED_CLAIM",
                            f"claim {term!r} is absent from referenced source facts",
                            section=section,
                            bullet_index=index,
                        )
                    )
            if tailor_plan is not None:
                for gap in tailor_plan.gaps:
                    if gap.casefold() in bullet.text.casefold():
                        issues.append(
                            _error(
                                "GAP_PRESENTED_AS_EVIDENCE",
                                "a declared evidence gap appears in a tailored bullet",
                                section=section,
                                bullet_index=index,
                            )
                        )

    return ValidationReport(
        passed=not any(issue.severity is ValidationSeverity.ERROR for issue in issues),
        issues=issues,
        semantic_review_required=semantic_review_required,
    )


async def validate_resume(
    *,
    tailored_resume: TailoredResume,
    source_resume: Resume,
    fact_ledger: FactLedger,
    jd_analysis: JDAnalysis,
    tailor_plan: TailorPlan | None = None,
    provider: LLMProvider | None = None,
    require_semantic_review: bool = False,
) -> ValidationReport:
    report = validate_resume_deterministically(
        tailored_resume=tailored_resume,
        source_resume=source_resume,
        fact_ledger=fact_ledger,
        jd_analysis=jd_analysis,
        tailor_plan=tailor_plan,
        semantic_review_required=require_semantic_review,
    )
    if not report.passed or not require_semantic_review:
        return report
    if provider is None:
        raise ValueError("provider is required when semantic review is requested")
    try:
        review = await provider.semantic_review(
            tailored_resume=tailored_resume,
            source_resume=source_resume,
            fact_ledger=fact_ledger,
            jd_analysis=jd_analysis,
        )
    except LLMError:
        raise
    except (ValidationError, TypeError, ValueError) as exc:
        raise StructuredOutputError("semantic reviewer returned invalid structured output") from exc
    except Exception as exc:
        raise LLMProviderError("semantic review provider call failed") from exc
    if not isinstance(review, SemanticReview):
        raise StructuredOutputError("semantic reviewer did not return a SemanticReview")
    return ValidationReport(
        passed=review.passed,
        issues=review.issues,
        semantic_review_required=True,
        semantic_review_performed=True,
    )


def _error(
    code: str,
    message: str,
    *,
    section: str | None = None,
    bullet_index: int | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=ValidationSeverity.ERROR,
        message=message,
        section=section,
        bullet_index=bullet_index,
    )
