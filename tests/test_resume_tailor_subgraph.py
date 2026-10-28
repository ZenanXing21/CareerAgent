import asyncio

from career_agent import (
    EvidenceMatch,
    EvidenceStatus,
    JDAnalysis,
    JDRequirement,
    Resume,
    Skill,
    TailoredBullet,
    TailoredResume,
    TailorPlan,
    build_fact_ledger,
    build_resume_tailor_graph,
    calculate_match,
)


class GraphProvider:
    def __init__(self, *, recover_on_retry: bool = True) -> None:
        self.recover_on_retry = recover_on_retry
        self.calls = {"resume": 0, "jd": 0, "evidence": 0, "plan": 0, "rewrite": 0}

    async def parse_resume(self, **_: object) -> Resume:
        self.calls["resume"] += 1
        return Resume(
            resume_id="ignored",
            version="ignored",
            raw_text="ignored",
            skills=[Skill(name="Python", source_text="Python")],
        )

    async def parse_jd(self, *, job_id: str, source_text: str) -> JDAnalysis:
        self.calls["jd"] += 1
        return JDAnalysis(
            job_id=job_id,
            source_text=source_text,
            requirements=[
                JDRequirement(
                    id="ignored",
                    text="具备 Python 开发能力",
                    category="skill",
                    priority=1,
                    required=True,
                    keywords=["Python"],
                )
            ],
        )

    async def match_evidence(self, **_: object) -> list[EvidenceMatch]:
        self.calls["evidence"] += 1
        return [
            EvidenceMatch(
                requirement_id="req_001",
                status=EvidenceStatus.STRONG_MATCH,
                evidence_fact_ids=["fact_001"],
                reasoning_summary="简历明确包含 Python",
                confidence=0.9,
            )
        ]

    async def build_tailor_plan(self, **_: object) -> TailorPlan:
        self.calls["plan"] += 1
        return TailorPlan(
            highlight_fact_ids=["fact_001"],
            section_order=["skills"],
            target_keywords=["Python"],
        )

    async def rewrite_resume(self, **_: object) -> TailoredResume:
        self.calls["rewrite"] += 1
        failed = self.calls["rewrite"] == 1 or not self.recover_on_retry
        text = "使用 Python，提升 50%" if failed else "使用 Python"
        return TailoredResume(
            source_resume_id="resume-1",
            source_resume_version="v1",
            target_job_id="job-1",
            sections={"skills": [TailoredBullet(text=text, source_fact_ids=["fact_001"])]},
        )


def test_subgraph_runs_pipeline_and_rewrites_at_most_once() -> None:
    provider = GraphProvider()
    result = asyncio.run(
        build_resume_tailor_graph(provider).ainvoke(
            {
                "candidate_id": "candidate-1",
                "resume_id": "resume-1",
                "resume_version": "v1",
                "raw_resume_text": "Python",
                "job_id": "job-1",
                "jd_text": "要求具备 Python 开发能力",
                "retry_count": 0,
            }
        )
    )
    assert provider.calls == {"resume": 1, "jd": 1, "evidence": 1, "plan": 1, "rewrite": 2}
    assert result["retry_count"] == 1
    assert result["validation_report"].passed is True
    assert result["tailored_resume"].sections["skills"][0].text == "使用 Python"


def test_subgraph_stops_after_second_validation_failure() -> None:
    provider = GraphProvider(recover_on_retry=False)
    result = asyncio.run(
        build_resume_tailor_graph(provider).ainvoke(
            {
                "candidate_id": "candidate-1",
                "resume_id": "resume-1",
                "resume_version": "v1",
                "raw_resume_text": "Python",
                "job_id": "job-1",
                "jd_text": "要求具备 Python 开发能力",
            }
        )
    )
    assert provider.calls["rewrite"] == 2
    assert result["retry_count"] == 1
    assert result["validation_report"].passed is False


def test_subgraph_reuses_validated_precomputed_values() -> None:
    provider = GraphProvider()
    resume = Resume(
        resume_id="resume-1",
        version="v1",
        raw_text="Python",
        skills=[Skill(name="Python", source_text="Python")],
    )
    ledger = build_fact_ledger(resume, "candidate-1")
    jd = JDAnalysis(
        job_id="job-1",
        source_text="要求具备 Python 开发能力",
        requirements=[
            JDRequirement(
                id="req_001",
                text="具备 Python 开发能力",
                category="skill",
                priority=1,
                required=True,
                keywords=["Python"],
            )
        ],
    )
    matches = [
        EvidenceMatch(
            requirement_id="req_001",
            status=EvidenceStatus.STRONG_MATCH,
            evidence_fact_ids=["fact_001"],
            reasoning_summary="简历明确包含 Python",
            confidence=0.9,
        )
    ]
    plan = TailorPlan(
        highlight_fact_ids=["fact_001"],
        section_order=["skills"],
        target_keywords=["Python"],
    )
    result = asyncio.run(
        build_resume_tailor_graph(provider).ainvoke(
            {
                "candidate_id": "candidate-1",
                "resume_id": "resume-1",
                "resume_version": "v1",
                "raw_resume_text": "Python",
                "job_id": "job-1",
                "jd_text": jd.source_text,
                "resume": resume,
                "fact_ledger": ledger,
                "jd_analysis": jd,
                "evidence_matches": matches,
                "match_result": calculate_match(jd, matches),
                "tailor_plan": plan,
            }
        )
    )
    assert provider.calls == {"resume": 0, "jd": 0, "evidence": 0, "plan": 0, "rewrite": 2}
    assert result["validation_report"].passed is True
