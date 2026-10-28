"""Standalone LangGraph workflow for traceable resume tailoring."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from career_agent.jd.parser import JDParser
from career_agent.jobs.matcher import calculate_match
from career_agent.llm.base import LLMProvider, StructuredOutputError
from career_agent.resume.evidence_matcher import EvidenceMatcher
from career_agent.resume.fact_ledger import FactLedgerBuildError, build_fact_ledger
from career_agent.resume.models import (
    ReferenceValidationError,
    validate_evidence_references,
    validate_tailored_resume_references,
)
from career_agent.resume.parser import ResumeParser
from career_agent.resume.rewriter import ResumeRewriter
from career_agent.resume.state import ResumeTailorState
from career_agent.resume.tailor_planner import TailorPlanner, validate_tailor_plan_output
from career_agent.resume.validator import validate_resume


def build_resume_tailor_graph(provider: LLMProvider, *, checkpointer: object | None = None):
    """Compile the independently runnable resume-tailoring subgraph."""

    parser = ResumeParser(provider)
    jd_parser = JDParser(provider)
    evidence_matcher = EvidenceMatcher(provider)
    planner = TailorPlanner(provider)
    rewriter = ResumeRewriter(provider)

    async def parse_resume_node(state: ResumeTailorState) -> dict[str, object]:
        existing = state.get("resume")
        if existing is not None:
            if state.get("resume_id", existing.resume_id) != existing.resume_id:
                raise StructuredOutputError("reused resume_id does not match graph input")
            if state.get("resume_version", existing.version) != existing.version:
                raise StructuredOutputError("reused resume version does not match graph input")
            if state.get("raw_resume_text", existing.raw_text) != existing.raw_text:
                raise StructuredOutputError("reused resume text does not match graph input")
            ResumeParser._validate_provenance(existing)
            return {}
        return {
            "resume": await parser.parse(
                resume_id=state["resume_id"],
                version=state["resume_version"],
                raw_text=state["raw_resume_text"],
            )
        }

    def build_fact_ledger_node(state: ResumeTailorState) -> dict[str, object]:
        resume = state["resume"]
        existing = state.get("fact_ledger")
        if existing is not None:
            if (
                existing.candidate_id != state["candidate_id"]
                or existing.resume_id != resume.resume_id
                or existing.resume_version != resume.version
            ):
                raise FactLedgerBuildError("reused fact ledger does not match graph input")
            if any(fact.source_text not in resume.raw_text for fact in existing.facts):
                raise FactLedgerBuildError("reused fact ledger contains an untraceable source")
            return {}
        return {"fact_ledger": build_fact_ledger(resume, state["candidate_id"])}

    async def parse_jd_node(state: ResumeTailorState) -> dict[str, object]:
        existing = state.get("jd_analysis")
        if existing is not None:
            if existing.job_id != state["job_id"] or existing.source_text != state["jd_text"]:
                raise StructuredOutputError("reused JD analysis does not match graph input")
            return {}
        return {
            "jd_analysis": await jd_parser.parse(
                job_id=state["job_id"], source_text=state["jd_text"]
            )
        }

    async def match_evidence_node(state: ResumeTailorState) -> dict[str, object]:
        existing = state.get("evidence_matches")
        if existing is not None:
            try:
                validate_evidence_references(existing, state["jd_analysis"], state["fact_ledger"])
            except ReferenceValidationError as exc:
                raise StructuredOutputError(str(exc)) from exc
            return {}
        return {
            "evidence_matches": await evidence_matcher.match(
                jd_analysis=state["jd_analysis"], fact_ledger=state["fact_ledger"]
            )
        }

    def calculate_match_node(state: ResumeTailorState) -> dict[str, object]:
        calculated = calculate_match(state["jd_analysis"], state["evidence_matches"])
        existing = state.get("match_result")
        if existing is not None and existing != calculated:
            raise StructuredOutputError("reused match result is not the deterministic result")
        return {} if existing is not None else {"match_result": calculated}

    async def build_tailor_plan_node(state: ResumeTailorState) -> dict[str, object]:
        existing = state.get("tailor_plan")
        if existing is not None:
            validate_tailor_plan_output(existing, state["fact_ledger"], state["jd_analysis"])
            return {}
        return {
            "tailor_plan": await planner.build(
                resume=state["resume"],
                fact_ledger=state["fact_ledger"],
                jd_analysis=state["jd_analysis"],
                evidence_matches=state["evidence_matches"],
                match_result=state["match_result"],
            )
        }

    async def rewrite_resume_node(state: ResumeTailorState) -> dict[str, object]:
        existing = state.get("tailored_resume")
        report = state.get("validation_report")
        retry_count = state.get("retry_count", 0)
        if existing is not None and report is None and retry_count == 0:
            try:
                validate_tailored_resume_references(
                    existing,
                    state["resume"],
                    state["fact_ledger"],
                    expected_job_id=state["jd_analysis"].job_id,
                )
            except ReferenceValidationError as exc:
                raise StructuredOutputError(str(exc)) from exc
            return {}
        return {
            "tailored_resume": await rewriter.rewrite(
                source_resume=state["resume"],
                fact_ledger=state["fact_ledger"],
                jd_analysis=state["jd_analysis"],
                tailor_plan=state["tailor_plan"],
                previous_resume=existing if retry_count else None,
                validation_report=report if retry_count else None,
                allow_suggestions=state.get("allow_suggestions", False),
            ),
            "validation_report": None,
        }

    async def validate_resume_node(state: ResumeTailorState) -> dict[str, object]:
        return {
            "validation_report": await validate_resume(
                tailored_resume=state["tailored_resume"],
                source_resume=state["resume"],
                fact_ledger=state["fact_ledger"],
                jd_analysis=state["jd_analysis"],
                tailor_plan=state["tailor_plan"],
                provider=provider,
                require_semantic_review=state.get("require_semantic_review", False),
            )
        }

    def validation_route(state: ResumeTailorState) -> Literal["retry", "end"]:
        report = state["validation_report"]
        if not report.passed and state.get("retry_count", 0) < 1:
            return "retry"
        return "end"

    def increment_retry_node(state: ResumeTailorState) -> dict[str, object]:
        return {"retry_count": state.get("retry_count", 0) + 1}

    builder = StateGraph(ResumeTailorState)
    builder.add_node("parse_resume", parse_resume_node)
    builder.add_node("build_fact_ledger", build_fact_ledger_node)
    builder.add_node("parse_jd", parse_jd_node)
    builder.add_node("match_evidence", match_evidence_node)
    builder.add_node("calculate_match", calculate_match_node)
    builder.add_node("build_tailor_plan", build_tailor_plan_node)
    builder.add_node("rewrite_resume", rewrite_resume_node)
    builder.add_node("validate_resume", validate_resume_node)
    builder.add_node("increment_retry", increment_retry_node)
    builder.add_edge(START, "parse_resume")
    builder.add_edge("parse_resume", "build_fact_ledger")
    builder.add_edge("build_fact_ledger", "parse_jd")
    builder.add_edge("parse_jd", "match_evidence")
    builder.add_edge("match_evidence", "calculate_match")
    builder.add_edge("calculate_match", "build_tailor_plan")
    builder.add_edge("build_tailor_plan", "rewrite_resume")
    builder.add_edge("rewrite_resume", "validate_resume")
    builder.add_conditional_edges(
        "validate_resume", validation_route, {"retry": "increment_retry", "end": END}
    )
    builder.add_edge("increment_retry", "rewrite_resume")
    compile_kwargs = {} if checkpointer is None else {"checkpointer": checkpointer}
    return builder.compile(**compile_kwargs)
