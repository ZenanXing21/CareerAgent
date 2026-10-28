from career_agent import (
    EvidenceMatch,
    EvidenceStatus,
    Fact,
    FactLedger,
    FactStatus,
    JDAnalysis,
    JDRequirement,
    Job,
    MatchResult,
)
from career_agent.interview import build_interview_plan


def test_interview_questions_use_jd_requirements_and_confirmed_resume_facts() -> None:
    job = Job(
        id="mock:agent", platform="mock", external_job_id="agent",
        title="AI Agent 工程师", company="示例公司", location="上海",
        detail_text="需要 Python 和 Agent 项目经验", detail_verified=True,
    )
    jd = JDAnalysis(
        job_id=job.id, source_text=job.detail_text,
        requirements=[
            JDRequirement(id="req_001", text="Python 开发经验", category="skill",
                          priority=1, required=True, keywords=["Python"]),
            JDRequirement(id="req_002", text="大规模线上系统经验", category="experience",
                          priority=2, required=True),
        ],
    )
    ledger = FactLedger(
        candidate_id="c", resume_id="r", resume_version="v",
        facts=[Fact(
            id="fact_001", category="skill", source="resume.skill.001",
            source_text="使用 Python", normalized_fact="使用 Python 开发项目",
            status=FactStatus.CONFIRMED,
        )],
    )
    matches = [
        EvidenceMatch(
            requirement_id="req_001", status=EvidenceStatus.STRONG_MATCH,
            evidence_fact_ids=["fact_001"], reasoning_summary="有 Python 经验", confidence=0.9,
        ),
        EvidenceMatch(
            requirement_id="req_002", status=EvidenceStatus.NO_MATCH,
            reasoning_summary="没有线上系统证据", confidence=0.8,
        ),
    ]
    score = MatchResult(
        score=0.5, strong_matches=["req_001"], missing_requirements=["req_002"],
        explanation="一项强匹配，一项缺口",
    )

    plan = build_interview_plan(
        job=job, jd_analysis=jd, match=score,
        evidence_matches=matches, fact_ledger=ledger,
    )

    assert [question.requirement_id for question in plan.questions] == ["req_001", "req_002"]
    assert plan.questions[0].evidence_fact_ids == ["fact_001"]
    assert "使用 Python 开发项目" in plan.questions[0].talking_points
    assert plan.questions[1].match_level == "gap"
    assert plan.questions[1].evidence_fact_ids == []
    assert "如实说明" in plan.questions[1].talking_points[0]
