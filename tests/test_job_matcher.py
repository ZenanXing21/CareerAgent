import pytest

from career_agent import (
    EvidenceMatch,
    EvidenceStatus,
    JDAnalysis,
    JDRequirement,
    ReferenceValidationError,
    calculate_match,
)


def _jd() -> JDAnalysis:
    return JDAnalysis(
        job_id="j",
        source_text="Python MCP",
        requirements=[
            JDRequirement(id="req_001", text="Python", category="skill", priority=1, required=True),
            JDRequirement(id="req_002", text="MCP", category="skill", priority=3, required=False),
        ],
    )


def test_match_score_is_exact_and_required_has_greater_weight() -> None:
    result = calculate_match(
        _jd(),
        [
            EvidenceMatch(
                requirement_id="req_001",
                status=EvidenceStatus.PARTIAL_MATCH,
                evidence_fact_ids=["f"],
                reasoning_summary="部分",
                confidence=0.7,
            ),
            EvidenceMatch(
                requirement_id="req_002",
                status=EvidenceStatus.STRONG_MATCH,
                evidence_fact_ids=["f"],
                reasoning_summary="完整",
                confidence=0.9,
            ),
        ],
    )
    assert result.score == pytest.approx(4 / 7)
    assert result.partial_matches == ["req_001"]
    assert result.strong_matches == ["req_002"]


def test_unknown_scores_zero_and_invalid_coverage_is_rejected() -> None:
    unknown = EvidenceMatch(
        requirement_id="req_001",
        status=EvidenceStatus.UNKNOWN,
        reasoning_summary="未知",
        confidence=0.1,
    )
    with pytest.raises(ReferenceValidationError, match="missing"):
        calculate_match(_jd(), [unknown])
    duplicate = EvidenceMatch(
        requirement_id="req_001",
        status=EvidenceStatus.NO_MATCH,
        reasoning_summary="无",
        confidence=0.8,
    )
    with pytest.raises(ReferenceValidationError, match="duplicate"):
        calculate_match(_jd(), [unknown, duplicate])
