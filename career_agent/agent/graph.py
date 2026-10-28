"""Top-level Career Agent LangGraph with persisted human review."""

from __future__ import annotations

from typing import Literal, Protocol

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from career_agent.agent.state import CareerState
from career_agent.jd.parser import JDParser
from career_agent.jobs.matcher import calculate_match
from career_agent.jobs.models import Job, JobSearchQuery
from career_agent.llm.base import LLMProvider, StructuredOutputError
from career_agent.models import ApplicationRecord, ApplicationStatus, ErrorInfo
from career_agent.persistence.repository import CareerRepository
from career_agent.resume.evidence_matcher import EvidenceMatcher
from career_agent.resume.models import TailoredResume
from career_agent.resume.subgraph import build_resume_tailor_graph
from career_agent.resume.validator import validate_resume_deterministically


class JobSource(Protocol):
    async def search_jobs(self, query: JobSearchQuery) -> list[Job]: ...

    async def get_job_detail(self, job: Job) -> Job: ...


def build_career_graph(
    *,
    provider: LLMProvider,
    job_source: JobSource,
    repository: CareerRepository,
    checkpointer: object,
):
    jd_parser = JDParser(provider)
    evidence_matcher = EvidenceMatcher(provider)
    tailor_graph = build_resume_tailor_graph(provider)

    async def search_jobs_node(state: CareerState) -> dict[str, object]:
        profile = state["candidate_profile"]
        query = JobSearchQuery(
            keyword=profile.target_roles[0],
            city=profile.cities[0] if profile.cities else "不限",
            salary_min=profile.salary_min,
            employment_types=profile.employment_types,
        )
        return {"jobs": await job_source.search_jobs(query), "job_cursor": 0}

    async def normalize_jobs_node(state: CareerState) -> dict[str, object]:
        unique: dict[tuple[str, str], Job] = {}
        for job in state["jobs"]:
            unique.setdefault((job.platform, job.external_job_id), job)
        jobs = list(unique.values())
        for job in jobs:
            await repository.upsert_job(job)
        return {"jobs": jobs}

    def choose_next_job_node(state: CareerState) -> dict[str, object]:
        cursor = state.get("job_cursor", 0)
        jobs = state["jobs"]
        if cursor >= len(jobs):
            return {"current_job": None}
        return {
            "current_job": jobs[cursor],
            "jd_analysis": None,
            "evidence_matches": None,
            "match_result": None,
            "tailor_plan": None,
            "tailored_resume": None,
            "validation_report": None,
            "human_decision": "",
            "retry_count": 0,
        }

    def choose_route(state: CareerState) -> Literal["analyze", "end"]:
        return "end" if state.get("current_job") is None else "analyze"

    async def analyze_job_node(state: CareerState) -> dict[str, object]:
        job = state["current_job"]
        if not job.detail_verified:
            job = await job_source.get_job_detail(job)
            if not job.detail_verified or job.detail_text is None:
                raise StructuredOutputError("job source did not return verified detail text")
            await repository.upsert_job(job)
        analysis = await jd_parser.parse(job_id=job.id, source_text=job.detail_text or "")
        return {"current_job": job, "jd_analysis": analysis}

    async def match_job_node(state: CareerState) -> dict[str, object]:
        matches = await evidence_matcher.match(
            jd_analysis=state["jd_analysis"], fact_ledger=state["fact_ledger"]
        )
        return {
            "evidence_matches": matches,
            "match_result": calculate_match(state["jd_analysis"], matches),
        }

    def match_route(state: CareerState) -> Literal["skip", "tailor"]:
        threshold = state.get("match_threshold", 0.6)
        return "tailor" if state["match_result"].score >= threshold else "skip"

    async def skip_job_node(state: CareerState) -> dict[str, object]:
        job = state["current_job"]
        await repository.save_application(
            ApplicationRecord(
                job_id=job.id,
                platform=job.platform,
                status=ApplicationStatus.SKIPPED,
                match_score=state["match_result"].score,
                resume_version=state["base_resume"].version,
            )
        )
        return {"application_status": ApplicationStatus.SKIPPED}

    async def resume_tailor_node(state: CareerState) -> dict[str, object]:
        result = await tailor_graph.ainvoke(
            {
                "candidate_id": state["candidate_profile"].candidate_id,
                "resume": state["base_resume"],
                "fact_ledger": state["fact_ledger"],
                "job_id": state["current_job"].id,
                "jd_text": state["current_job"].detail_text,
                "jd_analysis": state["jd_analysis"],
                "evidence_matches": state["evidence_matches"],
                "match_result": state["match_result"],
                "require_semantic_review": state.get("require_semantic_review", False),
                "retry_count": 0,
            }
        )
        report = result["validation_report"]
        updates: dict[str, object] = {
            "tailor_plan": result["tailor_plan"],
            "tailored_resume": result["tailored_resume"],
            "validation_report": report,
            "retry_count": result.get("retry_count", 0),
        }
        if not report.passed:
            updates["error"] = ErrorInfo(
                code="TAILOR_VALIDATION_FAILED",
                message="tailored resume failed validation after the allowed retry",
                node="resume_tailor",
                job_id=state["current_job"].id,
            )
        return updates

    def tailor_route(state: CareerState) -> Literal["review", "end"]:
        return "review" if state["validation_report"].passed else "end"

    def human_review_node(state: CareerState) -> dict[str, object]:
        decision = interrupt(
            {
                "job_id": state["current_job"].id,
                "match_score": state["match_result"].score,
                "tailored_resume": state["tailored_resume"].model_dump(mode="json"),
                "validation_issues": [
                    issue.model_dump(mode="json") for issue in state["validation_report"].issues
                ],
                "allowed_actions": ["APPROVE", "REJECT", "EDIT"],
            }
        )
        if not isinstance(decision, dict):
            raise ValueError("human review command must be an object")
        action = str(decision.get("action", "")).upper()
        if action not in {"APPROVE", "REJECT", "EDIT"}:
            raise ValueError("human review action must be APPROVE, REJECT, or EDIT")
        updates: dict[str, object] = {"human_decision": action}
        if action == "EDIT":
            try:
                updates["edited_resume"] = TailoredResume.model_validate(
                    decision.get("tailored_resume")
                )
            except ValidationError as exc:
                raise ValueError("EDIT requires a valid tailored_resume") from exc
        return updates

    def human_route(state: CareerState) -> Literal["approve", "reject", "edit"]:
        return state["human_decision"].lower()  # type: ignore[return-value]

    def validate_user_edit_node(state: CareerState) -> dict[str, object]:
        edited = state["edited_resume"]
        report = validate_resume_deterministically(
            tailored_resume=edited,
            source_resume=state["base_resume"],
            fact_ledger=state["fact_ledger"],
            jd_analysis=state["jd_analysis"],
            tailor_plan=state["tailor_plan"],
        )
        updates: dict[str, object] = {"validation_report": report}
        if report.passed:
            updates["tailored_resume"] = edited
        return updates

    async def approve_node(state: CareerState) -> dict[str, object]:
        job = state["current_job"]
        await repository.save_resume_version(
            state["tailored_resume"], state["validation_report"], approved=True
        )
        await repository.save_application(
            ApplicationRecord(
                job_id=job.id,
                platform=job.platform,
                status=ApplicationStatus.READY_TO_APPLY,
                match_score=state["match_result"].score,
                resume_version=state["base_resume"].version,
            )
        )
        return {"application_status": ApplicationStatus.READY_TO_APPLY}

    async def reject_node(state: CareerState) -> dict[str, object]:
        job = state["current_job"]
        await repository.save_application(
            ApplicationRecord(
                job_id=job.id,
                platform=job.platform,
                status=ApplicationStatus.SKIPPED,
                match_score=state["match_result"].score,
                resume_version=state["base_resume"].version,
            )
        )
        return {"application_status": ApplicationStatus.SKIPPED}

    def advance_job_node(state: CareerState) -> dict[str, object]:
        return {"job_cursor": state.get("job_cursor", 0) + 1}

    builder = StateGraph(CareerState)
    builder.add_node("search_jobs", search_jobs_node)
    builder.add_node("normalize_jobs", normalize_jobs_node)
    builder.add_node("choose_next_job", choose_next_job_node)
    builder.add_node("analyze_job", analyze_job_node)
    builder.add_node("match_job", match_job_node)
    builder.add_node("skip_job", skip_job_node)
    builder.add_node("resume_tailor", resume_tailor_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("validate_user_edit", validate_user_edit_node)
    builder.add_node("approve", approve_node)
    builder.add_node("reject", reject_node)
    builder.add_node("advance_job", advance_job_node)
    builder.add_edge(START, "search_jobs")
    builder.add_edge("search_jobs", "normalize_jobs")
    builder.add_edge("normalize_jobs", "choose_next_job")
    builder.add_conditional_edges(
        "choose_next_job", choose_route, {"analyze": "analyze_job", "end": END}
    )
    builder.add_edge("analyze_job", "match_job")
    builder.add_conditional_edges(
        "match_job", match_route, {"skip": "skip_job", "tailor": "resume_tailor"}
    )
    builder.add_edge("skip_job", "advance_job")
    builder.add_conditional_edges(
        "resume_tailor", tailor_route, {"review": "human_review", "end": END}
    )
    builder.add_conditional_edges(
        "human_review",
        human_route,
        {"approve": "approve", "reject": "reject", "edit": "validate_user_edit"},
    )
    builder.add_edge("validate_user_edit", "human_review")
    builder.add_edge("approve", "advance_job")
    builder.add_edge("reject", "advance_job")
    builder.add_edge("advance_job", "choose_next_job")
    return builder.compile(checkpointer=checkpointer)
