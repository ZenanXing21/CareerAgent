import asyncio

from career_agent import (
    CandidateIntakeDraft,
    CareerProductService,
    EducationDraft,
    EvidenceMatch,
    EvidenceStatus,
    ExperienceDraft,
    ExperienceKind,
    IntakeConversationUpdate,
    IntakePolish,
    JDAnalysis,
    JDRequirement,
    PolishedEducation,
    PolishedExperience,
    Resume,
    ResumeAgentEdit,
    Skill,
)
from career_agent.jobs.models import Job
from career_agent.llm.base import LLMProviderError, StructuredOutputError


class UnusedProvider:
    pass


class UnusedJobSource:
    pass


def _service() -> CareerProductService:
    return CareerProductService(  # type: ignore[arg-type]
        provider=UnusedProvider(), job_source=UnusedJobSource()
    )


def test_job_analysis_scores_and_prepares_interview_without_rewriting() -> None:
    class AnalysisProvider:
        async def parse_jd(self, *, job_id: str, source_text: str) -> JDAnalysis:
            return JDAnalysis(
                job_id=job_id,
                source_text=source_text,
                requirements=[
                    JDRequirement(
                        id="draft",
                        text="熟悉 Python",
                        category="skill",
                        priority=1,
                        required=True,
                        keywords=["Python"],
                    )
                ],
            )

        async def match_evidence(self, **_: object) -> list[EvidenceMatch]:
            return [
                EvidenceMatch(
                    requirement_id="req_001",
                    status=EvidenceStatus.STRONG_MATCH,
                    evidence_fact_ids=["fact_001"],
                    reasoning_summary="简历明确记录 Python",
                    confidence=0.9,
                )
            ]

        async def rewrite_resume(self, **_: object) -> None:
            raise AssertionError("job analysis must not rewrite the resume")

    service = CareerProductService(  # type: ignore[arg-type]
        provider=AnalysisProvider(), job_source=UnusedJobSource()
    )
    resume = Resume(
        resume_id="resume-1",
        version="v1",
        raw_text="Python",
        skills=[Skill(name="Python", source_text="Python")],
    )
    job = Job(
        id="job-1",
        platform="mock",
        external_job_id="1",
        title="Python 工程师",
        company="示例企业",
        location="上海",
        detail_text="要求熟悉 Python",
        detail_verified=True,
    )

    result = asyncio.run(service.analyze_job(candidate_id="candidate-1", resume=resume, job=job))

    assert result.match.score == 1.0
    assert result.interview_plan.questions[0].requirement_text == "熟悉 Python"
    assert result.job.id == job.id


def test_product_service_blocks_incomplete_initial_resume() -> None:
    result = _service().create_initial_resume(CandidateIntakeDraft(candidate_id="c-1"))

    assert result.ready is False
    assert {issue.field for issue in result.issues} >= {"name", "education.school", "skills"}


def test_product_service_returns_preview_for_complete_initial_resume() -> None:
    result = _service().create_initial_resume(
        CandidateIntakeDraft(
            candidate_id="c-1",
            name="张明",
            email="z@example.com",
            phone="13800000000",
            education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
            skills=["Python"],
        )
    )

    assert result.ready is True
    assert result.resume is not None
    assert result.preview_html is not None
    assert "测试大学" in result.preview_html


def test_product_service_keeps_raw_resume_while_building_ai_display_version() -> None:
    class PolishingProvider:
        async def polish_candidate_intake(self, *, draft):  # type: ignore[no-untyped-def]
            del draft
            return IntakePolish(
                normalized_hometown="江苏省苏州市",
                normalized_skills=["Python"],
                professional_summary="具备严谨的问题分析与工程交付能力。",
                educations=[
                    PolishedEducation(source_index=0, description="主修数据结构与数据库。")
                ],
                experiences=[
                    PolishedExperience(
                        source_index=0,
                        kind=ExperienceKind.RESEARCH,
                        title="智能招聘研究",
                        role="研究助理",
                        start_date="2024-06",
                        end_date="2024-09",
                        description="使用 Python 完成数据清洗",
                        technologies=["Python"],
                    )
                ],
            )

    service = CareerProductService(  # type: ignore[arg-type]
        provider=PolishingProvider(), job_source=UnusedJobSource()
    )
    draft = CandidateIntakeDraft(
        candidate_id="c-ai",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        hometown="苏州",
        self_summary="做事认真，能把事情做完",
        education=EducationDraft(
            school="测试大学",
            degree="本科",
            major="计算机",
            courses=["数据结构", "数据库"],
        ),
        skills=["py"],
        experiences=[
            ExperienceDraft(
                content="使用 python 完成数据清洗",
                technologies=["python"],
            )
        ],
    )

    result = asyncio.run(service.create_ai_initial_resume(draft))

    assert result.ready is True
    assert result.resume is not None
    assert result.display_resume is not None
    assert result.resume.project_experiences[0].name is None
    assert result.display_resume.project_experiences[0].name == "智能招聘研究"
    assert result.display_resume.summary == "具备严谨的问题分析与工程交付能力。"
    assert result.display_resume.educations[0].description == "主修数据结构与数据库。"
    assert result.normalized_hometown == "江苏省苏州市"
    assert "研究助理" in (result.polished_preview_html or "")
    assert "研究助理" not in (result.raw_preview_html or "")


def test_initial_resume_falls_back_to_editable_raw_version_when_ai_output_fails() -> None:
    class FailingProvider:
        async def polish_candidate_intake(self, *, draft):  # type: ignore[no-untyped-def]
            del draft
            raise StructuredOutputError("invalid provider JSON")

    service = CareerProductService(  # type: ignore[arg-type]
        provider=FailingProvider(), job_source=UnusedJobSource()
    )
    draft = CandidateIntakeDraft(
        candidate_id="fallback",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["python sql / office"],
    )

    result = asyncio.run(service.create_ai_initial_resume(draft))

    assert result.ready is True
    assert result.ai_polished is False
    assert result.display_resume == result.resume
    assert result.polish_warning is not None


def test_initial_resume_falls_back_when_provider_request_itself_fails() -> None:
    class UnavailableProvider:
        async def polish_candidate_intake(self, *, draft):  # type: ignore[no-untyped-def]
            del draft
            raise LLMProviderError(
                "polish_candidate_intake provider request failed; "
                "structured and plain JSON attempts failed"
            )

    service = CareerProductService(  # type: ignore[arg-type]
        provider=UnavailableProvider(), job_source=UnusedJobSource()
    )
    draft = CandidateIntakeDraft(
        candidate_id="provider-fallback",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["Python / SQL / Office"],
    )

    result = asyncio.run(service.create_ai_initial_resume(draft))

    assert result.ready is True
    assert result.ai_polished is False
    assert result.display_resume == result.resume
    assert result.polish_warning is not None


def test_initial_resume_uses_decomposed_workflow_when_full_object_fails() -> None:
    class DecomposedProvider:
        async def polish_candidate_intake(self, *, draft):  # type: ignore[no-untyped-def]
            del draft
            raise StructuredOutputError("large object invalid")

        async def polish_candidate_profile(self, *, draft):  # type: ignore[no-untyped-def]
            del draft
            from career_agent.onboarding.models import IntakeProfilePolish

            return IntakeProfilePolish(
                normalized_skills=["Python", "SQL"],
                professional_summary="具备持续学习与跨团队协作能力。",
                educations=[PolishedEducation(source_index=0, description="主修数据结构。")],
            )

        async def polish_candidate_experience(  # type: ignore[no-untyped-def]
            self, *, experience, source_index
        ):
            assert experience.content == "用 python 清洗数据"
            return PolishedExperience(
                source_index=source_index,
                kind=ExperienceKind.PROJECT,
                title="数据清洗项目",
                role="开发者",
                description="使用 Python 完成数据清洗。",
                technologies=["Python"],
            )

    service = CareerProductService(  # type: ignore[arg-type]
        provider=DecomposedProvider(), job_source=UnusedJobSource()
    )
    draft = CandidateIntakeDraft(
        candidate_id="decomposed",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["python sql"],
        self_summary="我喜欢学新东西，也能和别人一起做事",
        experiences=[ExperienceDraft(content="用 python 清洗数据", technologies=["python"])],
    )

    result = asyncio.run(service.create_ai_initial_resume(draft))

    assert result.ai_polished is True
    assert result.generation_strategy == "decomposed"
    assert result.display_resume is not None
    assert result.display_resume.summary == "具备持续学习与跨团队协作能力。"
    assert result.display_resume.project_experiences[0].name == "数据清洗项目"
    assert "我喜欢学新东西" not in (result.polished_preview_html or "")


def test_resume_agent_applies_structured_edit_and_promotes_it_to_user_fact() -> None:
    source = CandidateIntakeDraft(
        candidate_id="agent-edit",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["Python"],
    ).build_resume()

    class EditingProvider:
        async def edit_resume(self, *, resume, instruction, conversation):  # type: ignore[no-untyped-def]
            assert instruction == "补充 SQL 技能"
            assert conversation == []
            skill = resume.skills[0].model_copy(update={"name": "Python、SQL"})
            return ResumeAgentEdit(
                assistant_message="已补充 SQL 技能。",
                resume=resume.model_copy(update={"skills": [skill]}),
            )

    service = CareerProductService(  # type: ignore[arg-type]
        provider=EditingProvider(), job_source=UnusedJobSource()
    )
    result = asyncio.run(
        service.edit_resume_with_agent(
            resume=source,
            instruction="补充 SQL 技能",
            conversation=[],
        )
    )

    assert result.assistant_message == "已补充 SQL 技能。"
    assert result.resume.skills[0].name == "Python、SQL"
    assert result.resume.version.endswith("-confirmed")
    assert "Python、SQL" in result.resume.raw_text


def test_conversational_intake_preserves_candidate_and_photo() -> None:
    current = CandidateIntakeDraft(
        candidate_id="chat-candidate",
        name="张明",
        photo_asset="data:image/png;base64,AA==",
    )

    class IntakeProvider:
        async def update_candidate_intake(self, *, draft, message, conversation):  # type: ignore[no-untyped-def]
            assert draft.name == "张明"
            assert message == "邮箱是 z@example.com"
            assert conversation == []
            return IntakeConversationUpdate(
                acknowledgement="已记录邮箱。",
                draft=draft.model_copy(
                    update={"candidate_id": "模型错误改写", "email": "z@example.com"}
                ),
            )

    service = CareerProductService(  # type: ignore[arg-type]
        provider=IntakeProvider(), job_source=UnusedJobSource()
    )
    result = asyncio.run(
        service.update_candidate_intake(
            draft=current,
            message="邮箱是 z@example.com",
            conversation=[],
        )
    )

    assert result.draft.candidate_id == "chat-candidate"
    assert result.draft.email == "z@example.com"
    assert result.draft.photo_asset == current.photo_asset
