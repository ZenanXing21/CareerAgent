import pytest

from career_agent import (
    CandidateIntakeDraft,
    EducationDraft,
    ExperienceDraft,
    IntakePolish,
    ProjectDraft,
    build_fact_ledger,
    render_resume_html,
)
from career_agent.onboarding.models import validate_intake_polish


def test_incomplete_intake_returns_ui_field_issues() -> None:
    draft = CandidateIntakeDraft(candidate_id="candidate-1", name="张明")

    fields = {issue.field for issue in draft.validation_issues()}

    assert "email" in fields
    assert "education.school" in fields
    assert "skills" in fields
    with pytest.raises(ValueError, match="candidate intake is incomplete"):
        draft.build_resume()


def test_complete_intake_builds_traceable_resume_and_preview() -> None:
    draft = CandidateIntakeDraft(
        candidate_id="candidate-1",
        name="张明",
        email="zhang@example.com",
        phone="13800000000",
        current_city="上海",
        hometown="杭州",
        education=EducationDraft(
            school="上海工商学院",
            degree="本科",
            major="计算机科学",
            courses=["数据结构", "Python程序设计"],
        ),
        skills=["Python", "LangGraph"],
        self_summary="专注于可信 AI Agent 工程落地。",
        projects=[
            ProjectDraft(
                name="Career Agent",
                role="开发者",
                description="使用 Python 和 LangGraph 开发求职工作流",
                technologies=["Python", "LangGraph"],
                is_course_project=True,
            )
        ],
        photo_asset="/uploads/avatar.png",
    )

    resume = draft.build_resume()
    ledger = build_fact_ledger(resume, draft.candidate_id)
    html = render_resume_html(resume, photo_asset=draft.photo_asset)

    assert resume.educations[0].school == "上海工商学院"
    assert resume.project_experiences[0].name == "Career Agent"
    assert resume.summary == "专注于可信 AI Agent 工程落地。"
    assert any(fact.normalized_fact == "LangGraph" for fact in ledger.facts)
    assert "Career Agent" in html
    assert "个人总结" in html
    assert "可信 AI Agent" in html
    assert "/uploads/avatar.png" in html


def test_added_experience_requires_content_but_not_name_or_role() -> None:
    incomplete = CandidateIntakeDraft(
        candidate_id="candidate-2",
        experiences=[ExperienceDraft(date_range="去年暑假")],
    )
    complete = CandidateIntakeDraft(
        candidate_id="candidate-2",
        name="张明",
        email="zhang@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["python"],
        experiences=[ExperienceDraft(date_range="去年暑假", content="使用 python 完成数据清洗")],
    )

    assert "experiences.0.content" in {
        issue.field for issue in incomplete.validation_issues()
    }
    assert not complete.validation_issues()
    assert complete.build_resume().project_experiences[0].name is None
    assert complete.build_resume().project_experiences[0].start_date == "去年暑假"


def test_numeric_experience_date_range_is_split_and_normalized() -> None:
    draft = CandidateIntakeDraft(
        candidate_id="date-range",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["Python"],
        experiences=[
            ExperienceDraft(date_range="2026/6-2026/9", content="完成 Agent 项目")
        ],
    )

    experience = draft.build_resume().project_experiences[0]
    assert experience.start_date == "2026-06"
    assert experience.end_date == "2026-09"


def test_freeform_skill_text_accepts_semantic_structuring() -> None:
    draft = CandidateIntakeDraft(
        candidate_id="freeform-skills",
        skills=["熟练python sql / 会用 office；做过数据分析和 lang graph"],
    )

    result = validate_intake_polish(
        draft,
        IntakePolish(
            normalized_skills=["Python", "SQL", "Microsoft Office", "数据分析", "LangGraph"]
        ),
    )

    assert result.normalized_skills == [
        "Python",
        "SQL",
        "Microsoft Office",
        "数据分析",
        "LangGraph",
    ]


def test_multiple_educations_are_preserved() -> None:
    draft = CandidateIntakeDraft(
        candidate_id="graduate",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        educations=[
            EducationDraft(
                school="本科大学",
                degree="本科",
                major="计算机",
                courses=["数据结构"],
            ),
            EducationDraft(
                school="研究生大学",
                degree="硕士",
                major="人工智能",
                courses=["机器学习"],
            ),
        ],
        skills=["Python"],
    )

    resume = draft.build_resume()

    assert len(resume.educations) == 2
    assert resume.educations[0].description == "相关课程：数据结构"
    assert "相关课程：机器学习" in resume.educations[1].source_text
