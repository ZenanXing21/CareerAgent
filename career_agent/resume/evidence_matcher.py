"""One-call semantic evidence matching followed by strict ID validation."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from career_agent.jd.models import JDAnalysis
from career_agent.llm.base import LLMError, LLMProvider, LLMProviderError, StructuredOutputError
from career_agent.models import EvidenceStatus, FactStatus
from career_agent.resume.models import (
    EvidenceMatch,
    FactLedger,
    ReferenceValidationError,
    validate_evidence_references,
)

logger = logging.getLogger(__name__)


class EvidenceMatcher:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def match(
        self, *, jd_analysis: JDAnalysis, fact_ledger: FactLedger
    ) -> list[EvidenceMatch]:
        try:
            matches = await self._provider.match_evidence(
                jd_analysis=jd_analysis, fact_ledger=fact_ledger
            )
        except LLMError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StructuredOutputError(
                "evidence provider returned invalid structured output"
            ) from exc
        except Exception as exc:
            raise LLMProviderError("evidence matching provider call failed") from exc
        if not isinstance(matches, list) or not all(
            isinstance(match, EvidenceMatch) for match in matches
        ):
            raise StructuredOutputError("evidence provider did not return EvidenceMatch objects")
        grounded = _ground_matches(matches, jd_analysis, fact_ledger)
        try:
            validate_evidence_references(grounded, jd_analysis, fact_ledger)
        except ReferenceValidationError as exc:
            raise StructuredOutputError(str(exc)) from exc
        by_id = {match.requirement_id: match for match in grounded}
        return [by_id[requirement.id] for requirement in jd_analysis.requirements]


def _ground_matches(
    matches: list[EvidenceMatch], jd_analysis: JDAnalysis, fact_ledger: FactLedger
) -> list[EvidenceMatch]:
    valid_requirements = {item.id for item in jd_analysis.requirements}
    confirmed_facts = {
        item.id for item in fact_ledger.facts if item.status is FactStatus.CONFIRMED
    }
    grounded: dict[str, EvidenceMatch] = {}
    discarded = 0
    for match in matches:
        if match.requirement_id not in valid_requirements or match.requirement_id in grounded:
            discarded += 1
            continue
        fact_ids = [fact_id for fact_id in match.evidence_fact_ids if fact_id in confirmed_facts]
        if len(fact_ids) != len(match.evidence_fact_ids):
            discarded += len(match.evidence_fact_ids) - len(fact_ids)
            match = (
                match.model_copy(update={
                    "status": EvidenceStatus.PARTIAL_MATCH,
                    "evidence_fact_ids": fact_ids,
                    "reasoning_summary": "仅保留已确认事实的证据",
                    "confidence": min(match.confidence, 0.5),
                }) if fact_ids else _unknown_match(match.requirement_id)
            )
        grounded[match.requirement_id] = match
    for requirement in jd_analysis.requirements:
        if requirement.id not in grounded:
            grounded[requirement.id] = _unknown_match(requirement.id)
            discarded += 1
    if discarded:
        logger.warning("Discarded %d unsupported evidence references or matches", discarded)
    return list(grounded.values())


def _unknown_match(requirement_id: str) -> EvidenceMatch:
    return EvidenceMatch(
        requirement_id=requirement_id,
        status=EvidenceStatus.UNKNOWN,
        evidence_fact_ids=[],
        reasoning_summary="没有可核实的匹配证据",
        confidence=0,
    )
