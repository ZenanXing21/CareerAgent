from io import BytesIO

from docx import Document

from career_agent.resume.inline_formatting import normalize_resume_formatting, preserve_source_emphasis
from career_agent.resume.models import Resume
from fastapi.testclient import TestClient
from career_agent.web.app import create_app
from career_agent.resume.exporter import render_resume_docx


def test_markdown_bold_underline_and_bullets_become_editable_styles() -> None:
    resume = Resume.model_validate({
        "resume_id": "format-test", "version": "v1", "raw_text": "source",
        "summary": "- **Business analysis** with __SQL__\n- Delivered reports",
        "project_experiences": [{"id": "p", "source_text": "source", "name": "Project",
            "description": "- **RAG** search\n- __API__ integration"}],
    })
    normalized, styles = normalize_resume_formatting(resume, {})

    assert normalized.summary == "• Business analysis with SQL\n• Delivered reports"
    assert normalized.project_experiences[0].description == "• RAG search\n• API integration"
    assert styles["summary"]["emphasis"] == ["Business analysis"]
    assert styles["summary"]["underline_terms"] == ["SQL"]
    assert styles["project_experiences.0.description"]["emphasis"] == ["RAG"]
    assert styles["project_experiences.0.description"]["underline_terms"] == ["API"]

    word = Document(BytesIO(render_resume_docx(normalized, field_styles=styles)))
    summary = next(paragraph for paragraph in word.paragraphs if "Business analysis" in paragraph.text)
    assert any(run.text == "Business analysis" and run.bold for run in summary.runs)
    assert any(run.text == "SQL" and run.underline for run in summary.runs)


def test_existing_resume_markdown_is_normalized_when_reopened(tmp_path) -> None:
    headers = {"X-Workspace-Key": "inline-format-test-workspace-key-123456"}
    with TestClient(create_app(state_file=tmp_path / "workspace.json")) as client:
        session_id = client.post("/api/sessions", headers=headers).json()["id"]
        resume = {"resume_id": session_id, "version": "v1", "raw_text": "source",
                  "summary": "- **RAG** and __API__"}
        assert client.post("/api/workspace/restore", headers=headers,
            json={"candidates": {session_id: {"raw_resume": resume, "display_resume": resume}}}).status_code == 200
        response = client.get(f"/api/resume/current?candidate_id={session_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["display_resume"]["summary"] == "• RAG and API"
        assert data["field_styles"]["summary"] == {
            "emphasis": ["RAG"], "underline_terms": ["API"]}


def test_source_emphasis_survives_plain_text_model_rewrite() -> None:
    resume = Resume.model_validate({"resume_id": "test", "version": "v1", "raw_text": "source",
        "summary": "Delivered RAG and API workflows."})
    styles = preserve_source_emphasis(resume, "**RAG** and __API__", {})
    assert styles["summary"] == {"emphasis": ["RAG"], "underline_terms": ["API"]}


def test_combined_bold_and_underline_on_one_phrase() -> None:
    resume = Resume.model_validate({"resume_id": "test", "version": "v1", "raw_text": "source",
        "summary": "**__RAG__** project"})
    normalized, styles = normalize_resume_formatting(resume, {})
    assert normalized.summary == "RAG project"
    assert styles["summary"] == {"emphasis": ["RAG"], "underline_terms": ["RAG"]}
