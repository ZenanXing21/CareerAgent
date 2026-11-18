from types import SimpleNamespace

from fastapi.testclient import TestClient

from career_agent.web.app import create_app
from career_agent.resume.editor import preserve_unrequested_resume_facts
from career_agent.resume.models import ExperienceType, Resume


def test_agent_local_edit_preserves_manual_changes_in_same_section(tmp_path, monkeypatch) -> None:
    import importlib
    web_app = importlib.import_module("career_agent.web.app")

    class FakeService:
        def __init__(self, **kwargs):
            pass

        async def edit_resume_with_agent(self, *, resume, instruction, conversation):
            changed = [item.model_copy(update={"description": "AI rewrote everything.", "title": "Wrong title"})
                       for item in resume.work_experiences]
            return SimpleNamespace(resume=resume.model_copy(update={"work_experiences": changed}), hometown=None)

    monkeypatch.setattr(web_app, "CareerProductService", FakeService)
    monkeypatch.setattr(web_app.OpenAICompatibleProvider, "from_env", lambda: object())
    monkeypatch.setattr(web_app.LiepinMCPAdapter, "from_env", lambda: object())
    headers = {"X-Workspace-Key": "scoped-agent-test-workspace-key-123456"}
    with TestClient(create_app(state_file=tmp_path / "workspace.json")) as client:
        session_id = client.post("/api/sessions", headers=headers).json()["id"]
        resume = {"resume_id": session_id, "version": "v1", "raw_text": "Original resume",
            "personal_info": {"name": "Test User"},
            "work_experiences": [
                {"id": "a", "source_text": "A", "experience_type": "work", "company": "Schneider Electric", "title": "Engineer", "description": "My corrected A."},
                {"id": "b", "source_text": "B", "experience_type": "work", "company": "Huawei", "title": "Developer", "description": "My corrected B."},
            ]}
        assert client.post("/api/workspace/restore", headers=headers,
            json={"candidates": {session_id: {"raw_resume": resume, "display_resume": resume}}}).status_code == 200
        response = client.post("/api/resume/agent", headers=headers,
            json={"candidate_id": session_id, "message": "只精简 Schneider Electric 这段工作经历的职责"})
        assert response.status_code == 200
        entries = response.json()["resume"]["work_experiences"]
        assert entries[0]["description"] == "AI rewrote everything."
        assert entries[0]["title"] == "Engineer"
        assert entries[1]["description"] == "My corrected B."
        saved = client.get(f"/api/resume/current?candidate_id={session_id}", headers=headers).json()
        assert saved["display_resume"]["work_experiences"] == entries


def test_link_label_request_does_not_change_person_name_or_summary() -> None:
    current = Resume.model_validate({"resume_id": "test", "version": "v1", "raw_text": "source",
        "summary": "My carefully edited summary.",
        "personal_info": {"name": "ZENAN XING", "links": ["https://example.com"]}})
    proposed = current.model_copy(update={
        "summary": "AI replaced my summary.",
        "personal_info": current.personal_info.model_copy(update={
            "name": "邢泽楠", "links": ["https://www.linkedin.com/in/example", "https://example.com"]}),
    })
    result = preserve_unrequested_resume_facts(
        current, proposed, "第一个个人网站名字改成LinkedIn，再增加我的GitHub链接")
    assert result.personal_info.name == "ZENAN XING"
    assert result.summary == current.summary
    assert result.personal_info.links == proposed.personal_info.links


def test_adding_experience_does_not_rewrite_existing_entries() -> None:
    current = Resume.model_validate({"resume_id": "test", "version": "v1", "raw_text": "source",
        "work_experiences": [{"id": "old", "source_text": "source", "experience_type": ExperienceType.WORK,
            "company": "Existing Co", "title": "Engineer", "description": "Manually corrected text."}]})
    new_entry = current.work_experiences[0].model_copy(update={
        "id": "new", "company": "New Co", "description": "Added experience."})
    proposed = current.model_copy(update={"work_experiences": [
        current.work_experiences[0].model_copy(update={"description": "AI rewrote old content."}), new_entry]})
    result = preserve_unrequested_resume_facts(current, proposed, "增加一段新的工作经历：New Co")
    assert result.work_experiences[0].description == "Manually corrected text."
    assert result.work_experiences[1].description == "Added experience."
