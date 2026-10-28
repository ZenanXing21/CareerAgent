"""Build interview practice from verified JD requirements and resume facts."""

from __future__ import annotations

from career_agent.interview.models import InterviewPlan, InterviewQuestion
from career_agent.jd.models import JDAnalysis
from career_agent.jobs.models import Job, MatchResult
from career_agent.models import FactStatus
from career_agent.resume.models import EvidenceMatch, FactLedger


def build_interview_plan(
    *, job: Job, jd_analysis: JDAnalysis, match: MatchResult,
    evidence_matches: list[EvidenceMatch], fact_ledger: FactLedger,
) -> InterviewPlan:
    facts = {
        fact.id: fact for fact in fact_ledger.facts if fact.status is FactStatus.CONFIRMED
    }
    evidence = {item.requirement_id: item for item in evidence_matches}
    ranked = sorted(jd_analysis.requirements, key=lambda item: item.priority)[:6]
    questions = []
    for index, requirement in enumerate(ranked, start=1):
        level = (
            "strong" if requirement.id in match.strong_matches else
            "partial" if requirement.id in match.partial_matches else
            "gap" if requirement.id in match.missing_requirements else "unknown"
        )
        match_item = evidence.get(requirement.id)
        fact_ids = [
            fact_id for fact_id in (match_item.evidence_fact_ids if match_item else [])
            if fact_id in facts
        ]
        points = [facts[fact_id].normalized_fact for fact_id in fact_ids]
        if level == "gap":
            prompt = f"岗位要求“{requirement.text}”。你有哪些相近经验？哪些部分尚未亲自做过？"
            points.append("没有直接经历的部分请如实说明，并指出可以迁移的经验。")
        else:
            prompt = (
                f"请结合一段真实经历，说明你如何满足岗位要求“{requirement.text}”。"
                "你具体负责什么、如何解决问题？"
            )
            if not points:
                points.append("请仅引用你真实参与过的工作或项目，不补造结果。")
        questions.append(InterviewQuestion(
            id=f"interview_{index:03d}", requirement_id=requirement.id,
            requirement_text=requirement.text, question=prompt,
            follow_up="如果追问你的个人贡献与验证方式，你会如何举证？",
            match_level=level, evidence_fact_ids=fact_ids, talking_points=points,
        ))
    if not questions:
        questions.append(InterviewQuestion(
            id="interview_001", requirement_text=job.title,
            question=f"请介绍你与“{job.title}”岗位最相关的一段真实经历。",
            follow_up="你的具体职责、采用的方法和可以核实的结果分别是什么？",
            match_level="unknown",
            talking_points=["结合简历中的真实经历作答，未知的岗位要求不要猜测。"],
        ))
    return InterviewPlan(job_id=job.id, job_title=job.title, questions=questions)
