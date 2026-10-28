import asyncio

import pytest

from career_agent import (
    Fact,
    FactLedger,
    FactStatus,
    JDAnalysis,
    Resume,
    ResumeRewriter,
    StructuredOutputError,
    TailoredBullet,
    TailoredResume,
    TailorPlan,
)
from career_agent.resume.models import DraftSuggestion


class RewriteProvider:
    async def rewrite_resume(self, **_: object) -> TailoredResume:
        return TailoredResume(
            source_resume_id="r",
            source_resume_version="v",
            target_job_id="j",
            sections={
                "skills": [TailoredBullet(text="虚构技能", source_fact_ids=["fact_missing"])]
            },
        )


def test_rewriter_rejects_unknown_fact_reference() -> None:
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
    with pytest.raises(StructuredOutputError, match="unknown fact"):
        asyncio.run(
            ResumeRewriter(RewriteProvider()).rewrite(
                source_resume=Resume(resume_id="r", version="v", raw_text="Python"),
                fact_ledger=ledger,
                jd_analysis=JDAnalysis(job_id="j", source_text="Python"),
                tailor_plan=TailorPlan(highlight_fact_ids=["fact_001"]),
            )
        )


def test_optional_suggestions_do_not_replace_verified_sections() -> None:
    class SuggestionProvider:
        async def rewrite_resume(self, **_: object) -> TailoredResume:
            return TailoredResume(
                source_resume_id="r",
                source_resume_version="v",
                target_job_id="j",
                sections={"skills": [TailoredBullet(text="Python", source_fact_ids=["fact_001"])]},
                suggestions=[
                    DraftSuggestion(section="project", text="待确认的岗位相关项目描述"),
                    DraftSuggestion(section="unknown", text="不支持的栏目"),
                ],
            )

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
    args = dict(
        source_resume=Resume(resume_id="r", version="v", raw_text="Python"),
        fact_ledger=ledger,
        jd_analysis=JDAnalysis(job_id="j", source_text="Python"),
        tailor_plan=TailorPlan(highlight_fact_ids=["fact_001"]),
    )
    safe = asyncio.run(ResumeRewriter(SuggestionProvider()).rewrite(**args))
    optional = asyncio.run(
        ResumeRewriter(SuggestionProvider()).rewrite(**args, allow_suggestions=True)
    )

    assert safe.suggestions == []
    assert len(optional.suggestions) == 1
    assert optional.suggestions[0].section == "project"
    assert optional.sections == safe.sections
