import asyncio

from career_agent import (
    EvidenceMatch,
    EvidenceMatcher,
    EvidenceStatus,
    Fact,
    FactLedger,
    FactStatus,
    JDAnalysis,
    JDRequirement,
)


def _analysis() -> JDAnalysis:
    return JDAnalysis(
        job_id="j",
        source_text="Python MCP",
        requirements=[
            JDRequirement(id="req_001", text="Python", category="skill", priority=1, required=True),
            JDRequirement(id="req_002", text="MCP", category="skill", priority=2, required=False),
        ],
    )


def _ledger() -> FactLedger:
    return FactLedger(
        candidate_id="c",
        resume_id="r",
        resume_version="v",
        facts=[
            Fact(
                id="fact_001",
                category="skill",
                source="resume",
                source_text="Python",
                normalized_fact="Python",
                status=FactStatus.CONFIRMED,
            )
        ],
    )


class EvidenceProvider:
    def __init__(self, matches: list[EvidenceMatch]) -> None:
        self.matches = matches
        self.calls = 0

    async def match_evidence(self, **_: object) -> list[EvidenceMatch]:
        self.calls += 1
        return self.matches


def test_evidence_matcher_validates_and_returns_jd_order() -> None:
    provider = EvidenceProvider(
        [
            EvidenceMatch(
                requirement_id="req_002",
                status=EvidenceStatus.UNKNOWN,
                reasoning_summary="未知",
                confidence=0.2,
            ),
            EvidenceMatch(
                requirement_id="req_001",
                status=EvidenceStatus.STRONG_MATCH,
                evidence_fact_ids=["fact_001"],
                reasoning_summary="有证据",
                confidence=0.9,
            ),
        ]
    )
    result = asyncio.run(
        EvidenceMatcher(provider).match(jd_analysis=_analysis(), fact_ledger=_ledger())
    )
    assert provider.calls == 1
    assert [item.requirement_id for item in result] == ["req_001", "req_002"]


def test_evidence_matcher_downgrades_dangling_fact_to_unknown() -> None:
    provider = EvidenceProvider(
        [
            EvidenceMatch(
                requirement_id="req_001",
                status=EvidenceStatus.STRONG_MATCH,
                evidence_fact_ids=["fact_missing"],
                reasoning_summary="错误",
                confidence=0.9,
            ),
            EvidenceMatch(
                requirement_id="req_002",
                status=EvidenceStatus.UNKNOWN,
                reasoning_summary="未知",
                confidence=0.2,
            ),
        ]
    )
    result = asyncio.run(
        EvidenceMatcher(provider).match(jd_analysis=_analysis(), fact_ledger=_ledger())
    )
    assert result[0].status is EvidenceStatus.UNKNOWN
    assert result[0].evidence_fact_ids == []
    assert result[0].confidence == 0


def test_evidence_matcher_fills_missing_requirement_without_inventing_evidence() -> None:
    result = asyncio.run(EvidenceMatcher(EvidenceProvider([])).match(
        jd_analysis=_analysis(), fact_ledger=_ledger(),
    ))
    assert [item.requirement_id for item in result] == ["req_001", "req_002"]
    assert all(item.status is EvidenceStatus.UNKNOWN for item in result)
