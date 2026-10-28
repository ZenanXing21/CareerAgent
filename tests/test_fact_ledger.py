import pytest

from career_agent import (
    FactLedgerBuildError,
    ProjectExperience,
    Resume,
    Skill,
    build_fact_ledger,
)


def test_fact_ledger_has_stable_ids_sources_and_course_metadata() -> None:
    resume = Resume(
        resume_id="r",
        version="v1",
        raw_text="课程项目 智慧校园；参与开发接口。Python",
        project_experiences=[
            ProjectExperience(
                id="project_001",
                source_text="课程项目 智慧校园；参与开发接口。Python",
                name="智慧校园",
                role="参与",
                project_type="课程项目",
                is_course_project=True,
                description="参与开发接口。",
                technologies=["Python"],
            )
        ],
        skills=[Skill(name="Python", source_text="Python")],
    )
    first = build_fact_ledger(resume, "candidate-1")
    second = build_fact_ledger(resume, "candidate-1")
    assert [fact.id for fact in first.facts] == [
        f"fact_{index:03d}" for index in range(1, len(first.facts) + 1)
    ]
    assert [fact.normalized_fact for fact in first.facts] == [
        fact.normalized_fact for fact in second.facts
    ]
    project = next(fact for fact in first.facts if fact.normalized_fact == "智慧校园")
    assert project.source == "resume.project.project_001"
    assert project.source_text in resume.raw_text
    assert project.metadata["is_course_project"] is True
    assert sum(fact.normalized_fact == "Python" for fact in first.facts) == 1


def test_fact_ledger_rejects_source_text_outside_resume_raw_text() -> None:
    resume = Resume(
        resume_id="r",
        version="v1",
        raw_text="Python",
        skills=[Skill(name="Rust", source_text="Rust")],
    )
    with pytest.raises(FactLedgerBuildError, match="resume.raw_text"):
        build_fact_ledger(resume, "candidate-1")
