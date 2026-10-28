"""Resilient semantic workflow for turning collected facts into a resume draft."""

from __future__ import annotations

import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from career_agent.llm.base import LLMProvider
from career_agent.onboarding.models import (
    CandidateIntakeDraft,
    IntakePolish,
    IntakeProfilePolish,
    IntakeSemanticFacts,
    PolishedExperience,
    validate_intake_polish,
)


class IntakePolishState(TypedDict, total=False):
    """Typed state makes every resume-generation stage observable and recoverable."""

    draft: CandidateIntakeDraft
    polish: IntakePolish
    profile: IntakeProfilePolish
    experiences: list[PolishedExperience]
    strategy: str
    errors: list[str]
    facts: IntakeSemanticFacts


def build_intake_polish_graph(provider: LLMProvider):
    """Build full-pass -> decomposed-pass -> deterministic-validation workflow.

    Providers are often less reliable when one response contains a large nested schema.
    The first node keeps the efficient one-call path. If it fails structurally or violates
    source boundaries, the graph automatically asks for a small profile object and one small
    object per experience, then validates the assembled result against the original facts.
    """

    async def extract_facts(state: IntakePolishState) -> dict[str, object]:
        operation = getattr(provider, "analyze_candidate_facts", None)
        if operation is None:
            return {}
        try:
            facts = await operation(draft=state["draft"])
            expected = set(range(len(state["draft"].all_experiences())))
            if (
                len(facts.experiences) != len(expected)
                or {item.source_index for item in facts.experiences} != expected
            ):
                raise ValueError("semantic facts do not cover source experiences")
            return {"facts": facts}
        except Exception as exc:
            return {"errors": [f"facts:{type(exc).__name__}"]}

    async def full_pass(state: IntakePolishState) -> dict[str, object]:
        try:
            arguments = {"draft": state["draft"]}
            if state.get("facts") is not None:
                arguments["facts"] = state["facts"]
            polish = validate_intake_polish(
                state["draft"],
                await provider.polish_candidate_intake(**arguments),
            )
            return {"polish": polish, "strategy": "full", "errors": []}
        except Exception as exc:  # provider/schema failures are routed to the smaller workflow
            return {
                "strategy": "decomposed",
                "errors": [f"full:{type(exc).__name__}"],
            }

    def full_route(state: IntakePolishState) -> str:
        return "done" if state.get("polish") is not None else "decompose"

    async def profile_pass(state: IntakePolishState) -> dict[str, object]:
        operation = getattr(provider, "polish_candidate_profile", None)
        if operation is None:
            return {"errors": [*state.get("errors", []), "profile:unsupported"]}
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                return {"profile": await operation(draft=state["draft"])}
            except Exception as exc:
                last_error = exc
        return {
            "errors": [
                *state.get("errors", []),
                f"profile:{type(last_error).__name__ if last_error else 'unknown'}",
            ]
        }

    async def experience_pass(state: IntakePolishState) -> dict[str, object]:
        entries = state["draft"].all_experiences()
        if not entries:
            return {"experiences": []}
        operation = getattr(provider, "polish_candidate_experience", None)
        if operation is None:
            return {"errors": [*state.get("errors", []), "experiences:unsupported"]}

        async def polish_one(index: int):
            last_error: Exception | None = None
            for _attempt in range(2):
                try:
                    return await operation(experience=entries[index], source_index=index)
                except Exception as exc:
                    last_error = exc
            assert last_error is not None
            raise last_error

        try:
            results = await asyncio.gather(*(polish_one(index) for index in range(len(entries))))
            return {"experiences": list(results)}
        except Exception as exc:
            return {"errors": [*state.get("errors", []), f"experiences:{type(exc).__name__}"]}

    def assemble_and_validate(state: IntakePolishState) -> dict[str, object]:
        profile = state.get("profile")
        experiences = state.get("experiences")
        if profile is None or experiences is None:
            return {}
        try:
            polish = IntakePolish(
                normalized_hometown=profile.normalized_hometown,
                normalized_skills=profile.normalized_skills,
                professional_summary=profile.professional_summary,
                educations=profile.educations,
                experiences=experiences,
            )
            return {
                "polish": validate_intake_polish(state["draft"], polish),
                "strategy": "decomposed",
            }
        except Exception as exc:
            return {"errors": [*state.get("errors", []), f"validate:{type(exc).__name__}"]}

    builder = StateGraph(IntakePolishState)
    builder.add_node("extract_facts", extract_facts)
    builder.add_node("full_pass", full_pass)
    builder.add_node("profile_pass", profile_pass)
    builder.add_node("experience_pass", experience_pass)
    builder.add_node("assemble_and_validate", assemble_and_validate)
    builder.add_edge(START, "extract_facts")
    builder.add_edge("extract_facts", "full_pass")
    builder.add_conditional_edges(
        "full_pass", full_route, {"done": END, "decompose": "profile_pass"}
    )
    builder.add_edge("profile_pass", "experience_pass")
    builder.add_edge("experience_pass", "assemble_and_validate")
    builder.add_edge("assemble_and_validate", END)
    return builder.compile()
