from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from career_agent import (
    ApplicationRecord,
    ApplicationStatus,
    CandidateProfile,
    EvidenceMatch,
    EvidenceStatus,
    ExperienceType,
    Fact,
    FactLedger,
    FactStatus,
    JDAnalysis,
    JDRequirement,
    Job,
    JobSearchQuery,
    MatchResult,
    ReferenceValidationError,
    Resume,
    ResumeAnchor,
    TailoredBullet,
    TailoredResume,
    TailorPlan,
    WorkExperience,
    validate_evidence_references,
    validate_tailor_plan_references,
    validate_tailored_resume_references,
)


def confirmed_fact(fact_id: str = "fact_001") -> Fact:
    return Fact(
        id=fact_id,
        category="project",
        source="resume.project.project_001",
        source_text="参与智慧校园项目，完成 MCP 工具迁移。",
        normalized_fact="完成 MCP 工具迁移",
        status=FactStatus.CONFIRMED,
    )


def ledger(*facts: Fact) -> FactLedger:
    return FactLedger(
        candidate_id="candidate_001",
        resume_id="resume_001",
        resume_version="v1",
        facts=list(facts) or [confirmed_fact()],
    )


def jd() -> JDAnalysis:
    return JDAnalysis(
        job_id="job_001",
        source_text="了解 MCP，具备 Python 开发能力。",
        requirements=[
            JDRequirement(
                id="req_001",
                text="了解 MCP",
                category="skill",
                priority=1,
                required=True,
                keywords=["MCP"],
            )
        ],
    )


def test_normal_construction_and_strings_are_stripped() -> None:
    profile = CandidateProfile(
        candidate_id=" candidate_001 ",
        target_roles=[" AI Agent Engineer "],
        cities=["上海"],
        salary_min=12_000,
        salary_max=20_000,
        employment_types=["全职"],
    )
    query = JobSearchQuery(keyword=" Python ", city="上海")
    job = Job(
        id="job_001",
        platform="mock",
        external_job_id="external_001",
        title="AI Engineer",
        company="Example",
        location="上海",
        detail_text="真实 JD 原文",
        detail_verified=True,
    )
    result = MatchResult(
        score=0.75,
        strong_matches=["req_001"],
        explanation="确定性权重计算结果",
    )

    assert profile.candidate_id == "candidate_001"
    assert profile.target_roles == ["AI Agent Engineer"]
    assert query.page == 1
    assert job.collected_at.utcoffset() == timedelta(0)
    assert result.score == 0.75


def test_models_forbid_extra_fields_and_validate_assignment() -> None:
    with pytest.raises(ValidationError, match="extra"):
        CandidateProfile(
            candidate_id="candidate_001",
            target_roles=["Python"],
            invented_skill="expert",
        )

    query = JobSearchQuery(keyword="Python", city="上海")
    with pytest.raises(ValidationError):
        query.page = 0

    with pytest.raises(ValidationError):
        JDRequirement(
            id="req",
            text="Python",
            category="skill",
            priority="1",
            required="false",
        )


def test_non_empty_ids_and_ratio_priority_ranges() -> None:
    with pytest.raises(ValidationError):
        confirmed_fact("   ")
    with pytest.raises(ValidationError):
        JDRequirement(
            id="req",
            text="Python",
            category="skill",
            priority=4,
            required=True,
        )
    with pytest.raises(ValidationError):
        EvidenceMatch(
            requirement_id="req",
            status=EvidenceStatus.STRONG_MATCH,
            evidence_fact_ids=["fact"],
            reasoning_summary="matched",
            confidence=1.1,
        )
    with pytest.raises(ValidationError):
        MatchResult(score=-0.1, explanation="invalid")


def test_duplicate_fact_and_requirement_ids_are_rejected() -> None:
    fact = confirmed_fact()
    with pytest.raises(ValidationError, match="fact ids must be unique"):
        ledger(fact, fact.model_copy())

    requirement = jd().requirements[0]
    with pytest.raises(ValidationError, match="requirement ids must be unique"):
        JDAnalysis(
            job_id="job_001",
            source_text="MCP",
            requirements=[requirement, requirement.model_copy()],
        )


def test_resume_keeps_internships_separate_from_work() -> None:
    work = WorkExperience(
        id="work_001",
        source_text="在甲公司担任开发工程师。",
        experience_type=ExperienceType.WORK,
        company="甲公司",
    )
    internship = WorkExperience(
        id="intern_001",
        source_text="在乙公司实习。",
        experience_type=ExperienceType.INTERNSHIP,
        company="乙公司",
    )
    resume = Resume(
        resume_id="resume_001",
        version="v1",
        raw_text="原始简历全文",
        work_experiences=[work],
        internships=[internship],
    )
    assert resume.work_experiences == [work]
    assert resume.internships == [internship]
    assert resume.internships[0].source_text == "在乙公司实习。"

    with pytest.raises(ValidationError, match="internships must be stored"):
        Resume(
            resume_id="resume_001",
            version="v1",
            raw_text="原文",
            work_experiences=[internship],
        )


def test_resume_entry_ids_are_unique_across_all_sections() -> None:
    from career_agent import Education, ProjectExperience

    with pytest.raises(ValidationError, match="unique across all sections"):
        Resume(
            resume_id="resume_001",
            version="v1",
            raw_text="原始简历全文",
            educations=[Education(id="entry_001", source_text="甲大学")],
            project_experiences=[ProjectExperience(id="entry_001", source_text="课程项目")],
        )


def test_evidence_references_are_allow_listed_to_current_jd_and_ledger() -> None:
    valid = EvidenceMatch(
        requirement_id="req_001",
        status=EvidenceStatus.STRONG_MATCH,
        evidence_fact_ids=["fact_001"],
        reasoning_summary="有实际 MCP 工具迁移经历。",
        confidence=0.94,
    )
    current_ledger = ledger()
    validate_evidence_references([valid], jd(), current_ledger)

    dangling_requirement = valid.model_copy(update={"requirement_id": "req_missing"})
    with pytest.raises(ReferenceValidationError, match="unknown requirement"):
        validate_evidence_references([dangling_requirement], jd(), current_ledger)

    dangling_fact = valid.model_copy(update={"evidence_fact_ids": ["fact_missing"]})
    with pytest.raises(ReferenceValidationError, match="unknown fact"):
        validate_evidence_references([dangling_fact], jd(), current_ledger)


def test_unconfirmed_facts_cannot_support_positive_evidence_or_generation() -> None:
    unknown = confirmed_fact()
    unknown.status = FactStatus.UNKNOWN
    current_ledger = ledger(unknown)
    evidence = EvidenceMatch(
        requirement_id="req_001",
        status=EvidenceStatus.PARTIAL_MATCH,
        evidence_fact_ids=[unknown.id],
        reasoning_summary="信息尚未确认。",
        confidence=0.2,
    )
    plan = TailorPlan(highlight_fact_ids=[unknown.id])
    tailored = TailoredResume(
        source_resume_id="resume_001",
        source_resume_version="v1",
        target_job_id="job_001",
        sections={"projects": [TailoredBullet(text="声称掌握 MCP", source_fact_ids=[unknown.id])]},
    )

    with pytest.raises(ReferenceValidationError, match="not CONFIRMED"):
        validate_evidence_references([evidence], jd(), current_ledger)
    with pytest.raises(ReferenceValidationError, match="not CONFIRMED"):
        validate_tailor_plan_references(plan, current_ledger)
    with pytest.raises(ReferenceValidationError, match="not CONFIRMED"):
        validate_tailored_resume_references(
            tailored,
            Resume(resume_id="resume_001", version="v1", raw_text="原文"),
            current_ledger,
        )


def test_tailored_bullet_requires_unique_nonempty_sources() -> None:
    with pytest.raises(ValidationError):
        TailoredBullet(text="完成 MCP 迁移", source_fact_ids=[])
    with pytest.raises(ValidationError, match="duplicates"):
        TailoredBullet(text="完成 MCP 迁移", source_fact_ids=["fact_001", "fact_001"])


def test_tailored_resume_checks_current_resume_job_and_dangling_facts() -> None:
    from career_agent import ProjectExperience

    source_resume = Resume(
        resume_id="resume_001",
        version="v1",
        raw_text="原始简历全文",
        project_experiences=[
            ProjectExperience(
                id="project_001",
                source_text="智慧校园项目，2025.03-2025.06。",
                name="智慧校园项目",
                role="参与成员",
                project_type="课程项目",
                is_course_project=True,
                start_date="2025.03",
                end_date="2025.06",
            )
        ],
    )
    tailored = TailoredResume(
        source_resume_id="resume_001",
        source_resume_version="v1",
        target_job_id="job_001",
        sections={
            "projects": [TailoredBullet(text="完成 MCP 工具迁移", source_fact_ids=["fact_001"])]
        },
        anchors=[
            ResumeAnchor(
                source_entry_id="project_001",
                section="project",
                project_name="智慧校园项目",
                project_role="参与成员",
                project_type="课程项目",
                is_course_project=True,
                start_date="2025.03",
                end_date="2025.06",
            )
        ],
    )
    validate_tailored_resume_references(
        tailored,
        source_resume,
        ledger(),
        expected_job_id="job_001",
    )

    stale = tailored.model_copy(update={"source_resume_version": "old"})
    with pytest.raises(ReferenceValidationError, match="current resume version"):
        validate_tailored_resume_references(
            stale,
            source_resume,
            ledger(),
            expected_job_id="job_001",
        )

    changed_anchor = tailored.model_copy(
        update={"anchors": [tailored.anchors[0].model_copy(update={"project_type": "企业项目"})]}
    )
    with pytest.raises(ReferenceValidationError, match="changed immutable anchors"):
        validate_tailored_resume_references(
            changed_anchor,
            source_resume,
            ledger(),
        )

    missing_anchor = tailored.model_copy(update={"anchors": []})
    with pytest.raises(ReferenceValidationError, match="coverage mismatch"):
        validate_tailored_resume_references(
            missing_anchor,
            source_resume,
            ledger(),
        )


def test_reasoning_summary_has_a_safe_explanatory_length() -> None:
    with pytest.raises(ValidationError):
        EvidenceMatch(
            requirement_id="req_001",
            status=EvidenceStatus.NO_MATCH,
            reasoning_summary="x" * 501,
            confidence=0.4,
        )


def test_application_record_uses_aware_utc_time_and_stable_status() -> None:
    record = ApplicationRecord(
        job_id="job_001",
        platform="mock",
        status=ApplicationStatus.READY_TO_APPLY,
        match_score=0.85,
        resume_version="v2",
    )
    assert record.status.value == "READY_TO_APPLY"
    assert record.created_at.utcoffset() == timedelta(0)
    assert record.updated_at.utcoffset() == timedelta(0)

    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="updated_at"):
        ApplicationRecord(
            job_id="job_001",
            platform="mock",
            status=ApplicationStatus.DISCOVERED,
            created_at=start,
            updated_at=start - timedelta(seconds=1),
        )

    with pytest.raises(ValidationError):
        ApplicationRecord(
            job_id="job_001",
            platform="mock",
            status=ApplicationStatus.DISCOVERED,
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )

    china_time = datetime(2026, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    normalized = ApplicationRecord(
        job_id="job_001",
        platform="mock",
        status=ApplicationStatus.DISCOVERED,
        created_at=china_time,
        updated_at=china_time,
    )
    assert normalized.created_at.utcoffset() == timedelta(0)
    assert normalized.created_at.hour == 0


def test_verified_job_requires_detail_text() -> None:
    with pytest.raises(ValidationError, match="require detail_text"):
        Job(
            id="job_001",
            platform="mock",
            external_job_id="external_001",
            title="AI Engineer",
            company="Example",
            location="上海",
            detail_verified=True,
        )


def test_status_enums_exactly_match_the_domain_contract() -> None:
    assert {status.value for status in FactStatus} == {
        "CONFIRMED",
        "UNKNOWN",
        "NONE",
        "UNSURE",
        "WITHHELD",
        "CONFLICT",
    }
    assert {status.value for status in EvidenceStatus} == {
        "STRONG_MATCH",
        "PARTIAL_MATCH",
        "NO_MATCH",
        "UNKNOWN",
    }
    assert {status.value for status in ApplicationStatus} == {
        "DISCOVERED",
        "ANALYZED",
        "MATCHED",
        "READY_FOR_REVIEW",
        "READY_TO_APPLY",
        "APPLIED",
        "REJECTED",
        "INTERVIEW",
        "SKIPPED",
    }


def test_evidence_validation_requires_every_jd_requirement_by_default() -> None:
    analysis = jd().model_copy(
        update={
            "requirements": [
                *jd().requirements,
                JDRequirement(
                    id="req_002",
                    text="具备 Python 开发能力",
                    category="skill",
                    priority=2,
                    required=True,
                    keywords=["Python"],
                ),
            ]
        }
    )
    one_match = EvidenceMatch(
        requirement_id="req_001",
        status=EvidenceStatus.STRONG_MATCH,
        evidence_fact_ids=["fact_001"],
        reasoning_summary="有实际 MCP 工具迁移经历。",
        confidence=0.94,
    )

    with pytest.raises(ReferenceValidationError, match="missing matches"):
        validate_evidence_references([one_match], analysis, ledger())

    validate_evidence_references([one_match], analysis, ledger(), require_complete=False)
