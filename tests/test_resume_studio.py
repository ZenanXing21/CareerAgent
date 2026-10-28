import asyncio
from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient

from career_agent.onboarding.models import CandidateIntakeDraft, IntakePolish, IntakeSemanticFacts
from career_agent.onboarding.workflow import build_intake_polish_graph
from career_agent.resume.exporter import render_resume_docx
from career_agent.resume.models import Resume
from career_agent.resume.studio import (
    ResumeDesignTheme,
    ResumeFieldPolish,
    explicit_design_context,
    field_text,
    validate_field_polish,
)
from career_agent.web.app import create_app


def test_design_skills_require_explicit_selection_and_reject_unknown_ids() -> None:
    with pytest.raises(ValueError, match="明确选择"):
        explicit_design_context([])
    with pytest.raises(ValueError, match="未找到"):
        explicit_design_context(["../../other"])
    assert "EXPLICIT_SKILL: ui-ux-pro-max" in explicit_design_context(["ui-ux-pro-max"])


def test_field_polishing_does_not_allow_system_fields_or_invented_metrics() -> None:
    resume = Resume(resume_id="test", version="v1", raw_text="原始事实", summary="做了数据清洗")
    assert field_text(resume, "summary") == "做了数据清洗"
    with pytest.raises(ValueError):
        field_text(resume, "raw_text")
    with pytest.raises(ValueError, match="数字"):
        validate_field_polish("做了数据清洗", ResumeFieldPolish(optimized_text="处理100万条数据"))


def test_generated_theme_is_used_in_real_word_export() -> None:
    resume = Resume(resume_id="test", version="v1", raw_text="真实事实", summary="参与数据处理")
    theme = ResumeDesignTheme(accent="#654321", title_size=30, heading_size=15)
    result = render_resume_docx(resume, template_id="designed", custom_theme=theme.model_dump())
    document = Document(BytesIO(result))
    assert str(document.styles["Heading 1"].font.color.rgb) == "654321"
    assert document.styles["Title"].font.size.pt == 30


def test_semantic_keywords_are_extracted_before_professional_rewriting() -> None:
    calls = []

    class Provider:
        async def analyze_candidate_facts(self, *, draft):
            calls.append("extract")
            return IntakeSemanticFacts(profile_keywords=["Python"])

        async def polish_candidate_intake(self, *, draft, facts):
            calls.append("rewrite")
            assert facts.profile_keywords == ["Python"]
            return IntakePolish(normalized_skills=["Python"])

    result = asyncio.run(
        build_intake_polish_graph(Provider()).ainvoke(
            {
                "draft": CandidateIntakeDraft(candidate_id="test", skills=["py"]),
            }
        )
    )
    assert calls == ["extract", "rewrite"]
    assert result["polish"].normalized_skills == ["Python"]


def test_workspace_survives_restart_and_design_requires_explicit_skill(tmp_path, monkeypatch):
    from career_agent.job_platform.liepin_mcp import LiepinMCPAdapter
    from career_agent.llm.openai_compatible import OpenAICompatibleProvider
    from career_agent.resume.studio import DesignedResumeTemplate

    calls = []

    class Provider:
        async def design_resume_template(self, *, message, skill_context, current_theme):
            calls.append("design")
            assert "EXPLICIT_SKILL: ui-ux-pro-max" in skill_context
            return DesignedResumeTemplate(
                name="深蓝", description="紧凑专业", theme=ResumeDesignTheme(accent="#123456")
            )

        async def optimize_resume_field(self, *, original, instruction):
            return ResumeFieldPolish(keywords=["数据清洗"], optimized_text="参与数据清洗与整理。")

    monkeypatch.setattr(OpenAICompatibleProvider, "from_env", lambda: Provider())
    monkeypatch.setattr(LiepinMCPAdapter, "from_env", lambda: object())
    path = tmp_path / "workspace.json"
    resume = Resume(resume_id="test", version="v1", raw_text="做了数据清洗", summary="做了数据清洗")
    with TestClient(create_app(state_file=path)) as client:
        payload = {
            "candidates": {
                "test": {
                    "raw_resume": resume.model_dump(mode="json"),
                    "display_resume": resume.model_dump(mode="json"),
                    "section_order": ["skills", "summary", "education"],
                    "photo_asset": "data:image/png;base64,dGVzdA==",
                }
            }
        }
        assert client.post("/api/workspace/restore", json=payload).status_code == 200
        assert client.get("/api/design/skills").json()["explicit_only"] is True
        response = client.post(
            "/api/resume/template/design", json={"candidate_id": "test", "message": "深蓝"}
        )
        assert response.status_code == 400
        assert calls == []
        response = client.post(
            "/api/resume/template/design",
            json={
                "candidate_id": "test",
                "message": "深蓝",
                "skill_ids": ["ui-ux-pro-max"],
            },
        )
        assert response.status_code == 200
        proposal = response.json()["proposal"]
        assert proposal["used_skills"] == ["ui-ux-pro-max"]
        current = client.get("/api/resume/current?candidate_id=test").json()
        assert current["template_id"] == "modern"
        assert current["designed_templates"] == []
        assert current["designed_template"] is None
        assert (
            client.post(
                "/api/resume/template/confirm",
                json={
                    "candidate_id": "test",
                    "template_id": "stale-proposal",
                },
            ).status_code
            == 409
        )
        response = client.post(
            "/api/resume/optimize-field", json={"candidate_id": "test", "path": "summary"}
        )
        assert response.status_code == 200
        assert response.json()["resume"]["summary"] == "参与数据清洗与整理。"
        assert (
            client.post(
                "/api/resume/optimize-field", json={"candidate_id": "test", "path": "raw_text"}
            ).status_code
            == 422
        )
    with TestClient(create_app(state_file=path)) as client:
        current = client.get("/api/resume/current?candidate_id=test").json()
        assert current["display_resume"]["summary"] == "参与数据清洗与整理。"
        assert current["raw_resume"]["summary"] == "做了数据清洗"
        assert current["photo_asset"] == "data:image/png;base64,dGVzdA=="
        assert current["section_order"][:2] == ["skills", "summary"]
        assert current["template_proposal"]["id"] == proposal["id"]
        confirm = {"candidate_id": "test", "template_id": proposal["id"]}
        response = client.post("/api/resume/template/confirm", json=confirm)
        assert response.status_code == 200
        assert response.json()["template"]["theme"]["accent"] == "#123456"
        assert len(response.json()["templates"]) == 1
        assert (
            len(client.post("/api/resume/template/confirm", json=confirm).json()["templates"]) == 1
        )
        assert calls == ["design"]  # Confirmation saves the actual theme without another LLM call.
        second = client.post(
            "/api/resume/template/design",
            json={
                "candidate_id": "test",
                "message": "另一版",
                "skill_ids": ["ui-ux-pro-max"],
            },
        ).json()["proposal"]
        response = client.post(
            "/api/resume/template/confirm",
            json={
                "candidate_id": "test",
                "template_id": second["id"],
            },
        )
        assert len(response.json()["templates"]) == 2
        assert (
            client.post("/api/resume/template/select", json=confirm).json()["active_design_id"]
            == proposal["id"]
        )
        document = Document(
            BytesIO(client.get("/api/resume/download/polished/docx?candidate_id=test").content)
        )
        assert str(document.styles["Heading 1"].font.color.rgb) == "123456"
        removed = client.delete(
            f"/api/resume/template/design?candidate_id=test&template_id={proposal['id']}"
        ).json()
        assert len(removed["templates"]) == 1
        assert removed["active_design_id"] == second["id"]
        assert (
            client.delete("/api/resume/template/design?candidate_id=test").json()["template_id"]
            == "modern"
        )


def test_old_single_template_is_retained_as_a_reusable_preset() -> None:
    resume = Resume(resume_id="legacy", version="v1", raw_text="原始事实")
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/workspace/restore",
            json={
                "candidates": {
                    "legacy": {
                        "raw_resume": resume.model_dump(mode="json"),
                        "display_resume": resume.model_dump(mode="json"),
                        "template_id": "designed",
                        "designed_template": {
                            "name": "旧模板",
                            "description": "保留旧配色",
                            "theme": {"accent": "#234567"},
                        },
                    }
                }
            },
        )
        assert response.status_code == 200
        current = client.get("/api/resume/current?candidate_id=legacy").json()
        assert len(current["designed_templates"]) == 1
        assert current["designed_templates"][0]["name"] == "旧模板"
        assert current["active_design_id"] == "legacy-custom"
        assert current["designed_template"]["theme"]["accent"] == "#234567"
