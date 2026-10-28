import asyncio

from career_agent import (
    Fact,
    FactLedger,
    FactStatus,
    JDAnalysis,
    Resume,
    SemanticReview,
    TailoredBullet,
    TailoredResume,
    ValidationIssue,
    ValidationSeverity,
    validate_resume,
    validate_resume_deterministically,
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
                source="resume.skill.001",
                source_text="使用 Python 开发接口",
                normalized_fact="使用 Python 开发接口",
                status=FactStatus.CONFIRMED,
            )
        ],
    )


def test_deterministic_validator_rejects_duplicates_and_unsupported_numbers() -> None:
    report = validate_resume_deterministically(
        tailored_resume=TailoredResume(
            source_resume_id="r",
            source_resume_version="v",
            target_job_id="j",
            sections={
                "skills": [
                    TailoredBullet(text="使用 Python，提升 50%", source_fact_ids=["fact_001"]),
                    TailoredBullet(text="使用 Python，提升 50%", source_fact_ids=["fact_001"]),
                ]
            },
        ),
        source_resume=Resume(resume_id="r", version="v", raw_text="使用 Python 开发接口"),
        fact_ledger=_ledger(),
        jd_analysis=JDAnalysis(job_id="j", source_text="Python"),
    )
    assert report.passed is False
    assert {issue.code for issue in report.issues} == {
        "DUPLICATE_BULLET",
        "UNSUPPORTED_NUMBER",
    }


class ReviewProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def semantic_review(self, **_: object) -> SemanticReview:
        self.calls += 1
        return SemanticReview(
            passed=False,
            issues=[
                ValidationIssue(
                    code="SEMANTIC_DRIFT",
                    severity=ValidationSeverity.ERROR,
                    message="表达超出事实范围",
                )
            ],
        )


def test_semantic_review_runs_only_after_deterministic_pass() -> None:
    provider = ReviewProvider()
    report = asyncio.run(
        validate_resume(
            tailored_resume=TailoredResume(
                source_resume_id="r",
                source_resume_version="v",
                target_job_id="j",
                sections={
                    "skills": [
                        TailoredBullet(text="使用 Python 开发接口", source_fact_ids=["fact_001"])
                    ]
                },
            ),
            source_resume=Resume(resume_id="r", version="v", raw_text="使用 Python 开发接口"),
            fact_ledger=_ledger(),
            jd_analysis=JDAnalysis(job_id="j", source_text="Python"),
            provider=provider,
            require_semantic_review=True,
        )
    )
    assert provider.calls == 1
    assert report.passed is False
    assert report.semantic_review_performed is True
