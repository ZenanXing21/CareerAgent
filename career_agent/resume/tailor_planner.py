"""Semantic tailoring decisions with deterministic allow-list validation."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from career_agent.jd.models import JDAnalysis
from career_agent.jd.parser import _keyword_is_traceable
from career_agent.jobs.models import MatchResult
from career_agent.llm.base import LLMError, LLMProvider, LLMProviderError, StructuredOutputError
from career_agent.models import FactStatus
from career_agent.resume.models import (
    EvidenceMatch,
    FactLedger,
    ReferenceValidationError,
    Resume,
    TailorPlan,
    validate_tailor_plan_references,
)

_SECTIONS = {"education", "work", "internship", "project", "campus", "skills"}
logger = logging.getLogger(__name__)


class TailorPlanner:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def build(
        self,
        *,
        resume: Resume,
        fact_ledger: FactLedger,
        jd_analysis: JDAnalysis,
        evidence_matches: list[EvidenceMatch],
        match_result: MatchResult,
    ) -> TailorPlan:
        try:
            plan = await self._provider.build_tailor_plan(
                resume=resume,
                fact_ledger=fact_ledger,
                jd_analysis=jd_analysis,
                evidence_matches=evidence_matches,
                match_result=match_result,
            )
        except LLMError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StructuredOutputError(
                "tailor planner returned invalid structured output"
            ) from exc
        except Exception as exc:
            raise LLMProviderError("tailor planner provider call failed") from exc
        if not isinstance(plan, TailorPlan):
            raise StructuredOutputError("tailor planner did not return a TailorPlan")
        plan = _ground_plan_output(plan, fact_ledger, jd_analysis)
        validate_tailor_plan_output(plan, fact_ledger, jd_analysis)
        return plan


def _ground_plan_output(
    plan: TailorPlan, fact_ledger: FactLedger, jd_analysis: JDAnalysis
) -> TailorPlan:
    """Remove unsupported model suggestions while retaining the grounded plan."""

    confirmed_ids = {
        fact.id for fact in fact_ledger.facts if fact.status is FactStatus.CONFIRMED
    }
    updates = {
        "highlight_fact_ids": [
            fact_id for fact_id in plan.highlight_fact_ids if fact_id in confirmed_ids
        ],
        "deemphasize_fact_ids": [
            fact_id for fact_id in plan.deemphasize_fact_ids if fact_id in confirmed_ids
        ],
        "section_order": [section for section in plan.section_order if section in _SECTIONS],
        "target_keywords": [
            keyword for keyword in plan.target_keywords
            if _keyword_is_traceable(keyword, jd_analysis.source_text)
        ],
    }
    removed = sum(len(getattr(plan, key)) - len(value) for key, value in updates.items())
    if removed:
        logger.warning("Discarded %d unsupported resume-tailoring plan items", removed)
    return plan.model_copy(update=updates)


def validate_tailor_plan_output(
    plan: TailorPlan, fact_ledger: FactLedger, jd_analysis: JDAnalysis
) -> None:
    try:
        validate_tailor_plan_references(plan, fact_ledger)
    except ReferenceValidationError as exc:
        raise StructuredOutputError(str(exc)) from exc
    unknown_sections = sorted(set(plan.section_order) - _SECTIONS)
    if unknown_sections:
        raise StructuredOutputError(f"tailor plan contains unknown sections: {unknown_sections}")
    unsupported_keywords = [
        keyword for keyword in plan.target_keywords
        if not _keyword_is_traceable(keyword, jd_analysis.source_text)
    ]
    if unsupported_keywords:
        raise StructuredOutputError(
            f"tailor plan keywords are absent from the JD: {unsupported_keywords}"
        )
