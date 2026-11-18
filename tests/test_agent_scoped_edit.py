from types import SimpleNamespace

from fastapi.testclient import TestClient

from career_agent.web.app import create_app


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
