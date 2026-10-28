"""Deterministic requirement-weighted job matching."""

from __future__ import annotations

from career_agent.jd.models import JDAnalysis
from career_agent.jobs.models import MatchResult
from career_agent.models import EvidenceStatus
from career_agent.resume.models import EvidenceMatch, ReferenceValidationError

_STATUS_VALUES = {
    EvidenceStatus.STRONG_MATCH: 1.0,
    EvidenceStatus.PARTIAL_MATCH: 0.5,
    EvidenceStatus.NO_MATCH: 0.0,
    EvidenceStatus.UNKNOWN: 0.0,
}
_PRIORITY_WEIGHTS = {1: 3.0, 2: 2.0, 3: 1.0}


def calculate_match(jd_analysis: JDAnalysis, matches: list[EvidenceMatch]) -> MatchResult:
    """Score every atomic requirement using fixed, auditable weights."""

    expected = [requirement.id for requirement in jd_analysis.requirements]
    received = [match.requirement_id for match in matches]
    duplicates = sorted({item for item in received if received.count(item) > 1})
    if duplicates:
        raise ReferenceValidationError(f"duplicate requirement ids: {duplicates}")
    unknown = sorted(set(received) - set(expected))
    missing = sorted(set(expected) - set(received))
    if unknown:
        raise ReferenceValidationError(f"unknown requirement ids: {unknown}")
    if missing:
        raise ReferenceValidationError(f"missing requirement ids: {missing}")

    by_id = {match.requirement_id: match for match in matches}
    numerator = 0.0
    denominator = 0.0
    strong: list[str] = []
    partial: list[str] = []
    unmet: list[str] = []
    for requirement in jd_analysis.requirements:
        match = by_id[requirement.id]
        weight = _PRIORITY_WEIGHTS[requirement.priority] * (2.0 if requirement.required else 1.0)
        denominator += weight
        numerator += weight * _STATUS_VALUES[match.status]
        if match.status is EvidenceStatus.STRONG_MATCH:
            strong.append(requirement.id)
        elif match.status is EvidenceStatus.PARTIAL_MATCH:
            partial.append(requirement.id)
        else:
            unmet.append(requirement.id)
    score = numerator / denominator if denominator else 0.0
    explanation = (
        "Fixed weighted score: required requirements use 2x weight; "
        "priorities 1/2/3 use weights 3/2/1; STRONG=1, PARTIAL=0.5, NO/UNKNOWN=0."
    )
    return MatchResult(
        score=score,
        strong_matches=strong,
        partial_matches=partial,
        missing_requirements=unmet,
        explanation=explanation,
    )
