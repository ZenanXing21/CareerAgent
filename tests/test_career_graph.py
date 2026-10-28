import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from career_agent import (
    ApplicationStatus,
    CandidateProfile,
    EvidenceMatch,
    EvidenceStatus,
    FactLedger,
    JDAnalysis,
    JDRequirement,
    Job,
    Resume,
    Skill,
    TailoredBullet,
    TailoredResume,
    TailorPlan,
    build_fact_ledger,
)
from career_agent.agent import build_career_graph


class MemoryRepository:
    def __init__(self) -> None:
        self.jobs: list[Job] = []
        self.applications = {}
        self.resume_versions: list[tuple[TailoredResume, bool]] = []

    async def upsert_job(self, job: Job) -> None:
        self.jobs.append(job)

    async def save_application(self, record) -> None:
        self.applications[record.job_id] = record

    async def get_application(self, job_id: str):
        return self.applications.get(job_id)

    async def save_resume_version(self, resume, validation, *, approved: bool) -> None:
        self.resume_versions.append((resume, approved))


class OneJobSource:
    def __init__(self) -> None:
        self.job = Job(
            id="job-1",
            platform="mock",
            external_job_id="ext-1",
            title="Python 工程师",
            company="甲公司",
            location="上海",
            detail_text="要求具备 Python 开发能力",
            detail_verified=True,
        )

    async def search_jobs(self, query) -> list[Job]:
        return [self.job]

    async def get_job_detail(self, job: Job) -> Job:
        return job


class CareerProvider:
    async def parse_jd(self, *, job_id: str, source_text: str) -> JDAnalysis:
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

    async def match_evidence(self, **_) -> list[EvidenceMatch]:
        return [
            EvidenceMatch(
                requirement_id="req_001",
                status=EvidenceStatus.STRONG_MATCH,
                evidence_fact_ids=["fact_001"],
                reasoning_summary="有 Python 证据",
                confidence=0.9,
            )
        ]

    async def build_tailor_plan(self, **_) -> TailorPlan:
        return TailorPlan(
            highlight_fact_ids=["fact_001"],
            section_order=["skills"],
            target_keywords=["Python"],
        )

    async def rewrite_resume(self, **_) -> TailoredResume:
        return TailoredResume(
            source_resume_id="resume-1",
            source_resume_version="v1",
            target_job_id="job-1",
            sections={"skills": [TailoredBullet(text="使用 Python", source_fact_ids=["fact_001"])]},
        )


def _input() -> tuple[dict, Resume, FactLedger]:
    resume = Resume(
        resume_id="resume-1",
        version="v1",
        raw_text="Python",
        skills=[Skill(name="Python", source_text="Python")],
    )
    ledger = build_fact_ledger(resume, "candidate-1")
    return (
        {
            "candidate_profile": CandidateProfile(
                candidate_id="candidate-1",
                target_roles=["Python 工程师"],
                cities=["上海"],
            ),
            "base_resume": resume,
            "fact_ledger": ledger,
            "match_threshold": 0.6,
        },
        resume,
        ledger,
    )


def test_career_graph_interrupt_and_approve() -> None:
    async def scenario() -> None:
        repository = MemoryRepository()
        graph = build_career_graph(
            provider=CareerProvider(),
            job_source=OneJobSource(),
            repository=repository,
            checkpointer=InMemorySaver(),
        )
        input_state, _, _ = _input()
        config = {"configurable": {"thread_id": "approve-flow"}}
        interrupted = await graph.ainvoke(input_state, config)
        assert interrupted["__interrupt__"]
        result = await graph.ainvoke(Command(resume={"action": "APPROVE"}), config)
        assert result["application_status"] is ApplicationStatus.READY_TO_APPLY
        assert repository.applications["job-1"].status is ApplicationStatus.READY_TO_APPLY
        assert repository.resume_versions[0][1] is True

    asyncio.run(scenario())


def test_career_graph_reject_and_edit_paths() -> None:
    async def scenario(action: str, thread_id: str) -> tuple[MemoryRepository, dict]:
        repository = MemoryRepository()
        graph = build_career_graph(
            provider=CareerProvider(),
            job_source=OneJobSource(),
            repository=repository,
            checkpointer=InMemorySaver(),
        )
        input_state, _, _ = _input()
        config = {"configurable": {"thread_id": thread_id}}
        interrupted = await graph.ainvoke(input_state, config)
        if action == "EDIT":
            edited = interrupted["tailored_resume"].model_copy(
                update={
                    "sections": {
                        "skills": [
                            TailoredBullet(text="Python 开发能力", source_fact_ids=["fact_001"])
                        ]
                    }
                }
            )
            interrupted = await graph.ainvoke(
                Command(
                    resume={
                        "action": "EDIT",
                        "tailored_resume": edited.model_dump(mode="json"),
                    }
                ),
                config,
            )
            assert interrupted["__interrupt__"]
            result = await graph.ainvoke(Command(resume={"action": "APPROVE"}), config)
        else:
            result = await graph.ainvoke(Command(resume={"action": "REJECT"}), config)
        return repository, result

    rejected_repo, rejected = asyncio.run(scenario("REJECT", "reject-flow"))
    assert rejected["application_status"] is ApplicationStatus.SKIPPED
    assert rejected_repo.applications["job-1"].status is ApplicationStatus.SKIPPED

    edited_repo, edited = asyncio.run(scenario("EDIT", "edit-flow"))
    assert edited["application_status"] is ApplicationStatus.READY_TO_APPLY
    assert edited_repo.resume_versions[0][0].sections["skills"][0].text == "Python 开发能力"
