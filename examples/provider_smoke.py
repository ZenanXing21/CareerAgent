"""Call every real structured-output operation using the configured model key."""

from __future__ import annotations

import argparse
import asyncio

from career_agent import (
    EvidenceMatcher,
    JDParser,
    OpenAICompatibleProvider,
    ResumeParser,
    ResumeRewriter,
    TailorPlanner,
    build_fact_ledger,
    calculate_match,
    validate_resume,
)

RESUME_TEXT = (
    "张明\n技能：Python、SQL、LangGraph。\n课程项目：Career Agent，使用 Python 和 LangGraph。"
)
JD_TEXT = """Python AI Agent 工程师。必须熟悉 Python；有 LangGraph 工作流经验优先。"""


async def main(stop_after: str) -> None:
    provider = OpenAICompatibleProvider.from_env()
    resume = await ResumeParser(provider).parse(
        resume_id="smoke-resume", version="v1", raw_text=RESUME_TEXT
    )
    print(f"[resume] entries={len(resume.project_experiences)}, skills={len(resume.skills)}")
    if stop_after == "resume":
        return
    ledger = build_fact_ledger(resume, "smoke-candidate")
    jd = await JDParser(provider).parse(job_id="smoke-job", source_text=JD_TEXT)
    print(f"[jd] requirements={len(jd.requirements)}")
    if stop_after == "jd":
        return
    evidence = await EvidenceMatcher(provider).match(jd_analysis=jd, fact_ledger=ledger)
    match = calculate_match(jd, evidence)
    print(f"[evidence] matches={len(evidence)}, score={match.score:.0%}")
    if stop_after == "evidence":
        return
    plan = await TailorPlanner(provider).build(
        resume=resume,
        fact_ledger=ledger,
        jd_analysis=jd,
        evidence_matches=evidence,
        match_result=match,
    )
    print(f"[plan] highlights={plan.highlight_fact_ids}, gaps={plan.gaps}")
    if stop_after == "plan":
        return
    tailored = await ResumeRewriter(provider).rewrite(
        source_resume=resume,
        fact_ledger=ledger,
        jd_analysis=jd,
        tailor_plan=plan,
    )
    report = await validate_resume(
        tailored_resume=tailored,
        source_resume=resume,
        fact_ledger=ledger,
        jd_analysis=jd,
        tailor_plan=plan,
        provider=provider,
        require_semantic_review=stop_after in {"semantic", "all"},
    )
    print(f"[rewrite] bullets={sum(1 for _ in tailored.iter_bullets())}")
    print(f"[validation] passed={report.passed}, issues={len(report.issues)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--step",
        choices=["resume", "jd", "evidence", "plan", "rewrite", "semantic", "all"],
        default="all",
    )
    asyncio.run(main(parser.parse_args().step))
