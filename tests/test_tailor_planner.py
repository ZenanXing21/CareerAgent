import asyncio

import pytest

from career_agent import (
    Fact,
    FactLedger,
    FactStatus,
    JDAnalysis,
    MatchResult,
    Resume,
    StructuredOutputError,
    TailorPlan,
    TailorPlanner,
)
from career_agent.resume.tailor_planner import validate_tailor_plan_output


class PlanProvider:
    def __init__(self, plan: TailorPlan) -> None:
        self.plan = plan
        self.calls = 0

    async def build_tailor_plan(self, **_: object) -> TailorPlan:
        self.calls += 1
        return self.plan


def test_tailor_planner_filters_unsupported_keywords_from_model() -> None:
    ledger = FactLedger(
        candidate_id="c",
        resume_id="r",
        resume_version="v",
        facts=[
            Fact(
                id="fact_001",
                category="skill",
                source="resume.skill.001",
                source_text="Python",
                normalized_fact="Python",
                status=FactStatus.CONFIRMED,
            )
        ],
    )
    provider = PlanProvider(
        TailorPlan(
            highlight_fact_ids=["fact_001"],
            section_order=["skills"],
            target_keywords=["Rust", "Python"],
        )
    )
    plan = asyncio.run(
        TailorPlanner(provider).build(
            resume=Resume(resume_id="r", version="v", raw_text="x"),
            fact_ledger=ledger,
            jd_analysis=JDAnalysis(job_id="j", source_text="Python"),
            evidence_matches=[],
            match_result=MatchResult(score=0, explanation="none"),
        )
    )
    assert plan.target_keywords == ["Python"]
    assert provider.calls == 1

    with pytest.raises(StructuredOutputError, match="absent from the JD"):
        validate_tailor_plan_output(
            provider.plan, ledger, JDAnalysis(job_id="j", source_text="Python")
        )


def test_tailor_planner_discards_unknown_fact_ids_and_sections() -> None:
    ledger = FactLedger(candidate_id="c", resume_id="r", resume_version="v")
    provider = PlanProvider(TailorPlan(
        highlight_fact_ids=["made_up_fact"],
        section_order=["skills", "imagined_section"],
        target_keywords=["AI-Agent", "不存在的技术"],
    ))

    plan = asyncio.run(TailorPlanner(provider).build(
        resume=Resume(resume_id="r", version="v", raw_text="x"),
        fact_ledger=ledger,
        jd_analysis=JDAnalysis(job_id="j", source_text="需要 AI—Agent 开发经验"),
        evidence_matches=[], match_result=MatchResult(score=0, explanation="none"),
    ))

    assert plan.highlight_fact_ids == []
    assert plan.section_order == ["skills"]
    assert plan.target_keywords == ["AI-Agent"]
