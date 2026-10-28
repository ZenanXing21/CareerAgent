"""Offline end-to-end Career Agent demo with real MCP tools and human approval."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from career_agent import (
    CandidateProfile,
    EvidenceMatch,
    EvidenceStatus,
    JDAnalysis,
    JDRequirement,
    JobPlatformRegistry,
    MCPJobPlatformClient,
    MockAdapter,
    Resume,
    Skill,
    TailoredBullet,
    TailoredResume,
    TailorPlan,
    build_career_graph,
    build_fact_ledger,
    create_job_platform_server,
)

logging.getLogger("langgraph.checkpoint.serde.jsonplus").setLevel(logging.ERROR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class DemoRepository:
    def __init__(self) -> None:
        self.applications = {}

    async def upsert_job(self, job) -> None:
        return None

    async def save_application(self, record) -> None:
        self.applications[record.job_id] = record

    async def get_application(self, job_id):
        return self.applications.get(job_id)

    async def save_resume_version(self, resume, validation, *, approved: bool) -> None:
        return None


class DemoProvider:
    """Deterministic offline provider; production uses OpenAICompatibleProvider."""

    async def parse_jd(self, *, job_id: str, source_text: str) -> JDAnalysis:
        requirements = []
        for index, keyword in enumerate(
            ("Python", "SQL", "LangGraph", "Java", "团队管理"), start=1
        ):
            if keyword.casefold() in source_text.casefold():
                requirements.append(
                    JDRequirement(
                        id=f"model-{index}",
                        text=f"具备 {keyword} 相关能力",
                        category="skill",
                        priority=1 if keyword in {"Python", "Java"} else 2,
                        required=keyword in {"Python", "Java"},
                        keywords=[keyword],
                    )
                )
        return JDAnalysis(job_id=job_id, source_text=source_text, requirements=requirements)

    async def match_evidence(self, *, jd_analysis, fact_ledger) -> list[EvidenceMatch]:
        matches = []
        for requirement in jd_analysis.requirements:
            facts = [
                fact.id
                for fact in fact_ledger.facts
                if any(
                    keyword.casefold() in fact.normalized_fact.casefold()
                    for keyword in requirement.keywords
                )
            ]
            matches.append(
                EvidenceMatch(
                    requirement_id=requirement.id,
                    status=(EvidenceStatus.STRONG_MATCH if facts else EvidenceStatus.NO_MATCH),
                    evidence_fact_ids=facts[:1],
                    reasoning_summary="找到简历事实证据" if facts else "简历中没有对应事实",
                    confidence=1.0,
                )
            )
        return matches

    async def build_tailor_plan(
        self, *, fact_ledger, jd_analysis, evidence_matches, **kwargs
    ) -> TailorPlan:
        del kwargs
        highlighted = [fact_id for item in evidence_matches for fact_id in item.evidence_fact_ids]
        gaps = [
            req.text
            for req, match in zip(jd_analysis.requirements, evidence_matches, strict=True)
            if match.status is EvidenceStatus.NO_MATCH
        ]
        return TailorPlan(
            highlight_fact_ids=highlighted,
            section_order=["skills"],
            target_keywords=[
                keyword
                for req, match in zip(jd_analysis.requirements, evidence_matches, strict=True)
                if match.status is not EvidenceStatus.NO_MATCH
                for keyword in req.keywords
            ],
            gaps=gaps,
        )

    async def rewrite_resume(
        self, *, source_resume, jd_analysis, tailor_plan, fact_ledger, **kwargs
    ) -> TailoredResume:
        del kwargs
        facts = {fact.id: fact for fact in fact_ledger.facts}
        bullets = [
            TailoredBullet(text=facts[fact_id].normalized_fact, source_fact_ids=[fact_id])
            for fact_id in tailor_plan.highlight_fact_ids
        ]
        if not bullets:
            bullets = [TailoredBullet(text="Python", source_fact_ids=["fact_001"])]
        return TailoredResume(
            source_resume_id=source_resume.resume_id,
            source_resume_version=source_resume.version,
            target_job_id=jd_analysis.job_id,
            sections={"skills": bullets},
        )


async def main(decision: str) -> None:
    resume = Resume(
        resume_id="resume-demo",
        version="v1",
        raw_text="技能：Python、SQL、LangGraph。",
        skills=[
            Skill(name="Python", source_text="Python"),
            Skill(name="SQL", source_text="SQL"),
            Skill(name="LangGraph", source_text="LangGraph"),
        ],
    )
    ledger = build_fact_ledger(resume, "candidate-demo")
    server = create_job_platform_server(JobPlatformRegistry([MockAdapter()]))
    repository = DemoRepository()
    graph = build_career_graph(
        provider=DemoProvider(),
        job_source=MCPJobPlatformClient(server),
        repository=repository,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "career-agent-demo"}}
    result = await graph.ainvoke(
        {
            "candidate_profile": CandidateProfile(
                candidate_id="candidate-demo",
                target_roles=["Python"],
                cities=["上海"],
            ),
            "base_resume": resume,
            "fact_ledger": ledger,
            "match_threshold": 0.6,
        },
        config,
    )
    while result.get("__interrupt__"):
        print(f"\n岗位：{result['current_job'].title} @ {result['current_job'].company}")
        print(f"匹配度：{result['match_result'].score:.0%}")
        print(f"差距：{result['tailor_plan'].gaps or ['无']}")
        for section, bullets in result["tailored_resume"].sections.items():
            print(f"[{section}]")
            for bullet in bullets:
                print(f"- {bullet.text}  facts={bullet.source_fact_ids}")
        action = decision.upper()
        if decision == "interactive":
            answer = input("批准该版本？[y/N] ").strip().lower()
            action = "APPROVE" if answer == "y" else "REJECT"
        result = await graph.ainvoke(Command(resume={"action": action}), config)
    print("\n最终申请状态：")
    for job_id, record in repository.applications.items():
        print(f"- {job_id}: {record.status.value}, score={record.match_score:.0%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--decision", choices=["approve", "reject", "interactive"], default="approve"
    )
    args = parser.parse_args()
    asyncio.run(main(args.decision))
