import importlib

from fastapi.testclient import TestClient

from career_agent import CandidateIntakeDraft, CareerProductService, EducationDraft
from career_agent.web.app import create_app


def test_repeated_generation_does_not_replace_saved_manual_resume(tmp_path, monkeypatch) -> None:
    web = importlib.import_module("career_agent.web.app")

    async def generated(service, draft):
        return service.create_initial_resume(draft).model_copy(update={"ai_polished": True})

    monkeypatch.setattr(web.OpenAICompatibleProvider, "from_env", lambda: object())
    monkeypatch.setattr(web.LiepinMCPAdapter, "from_env", lambda: object())
    monkeypatch.setattr(CareerProductService, "create_ai_initial_resume", generated)
    headers = {"X-Workspace-Key": "regeneration-test-workspace-key-123456"}
    with TestClient(create_app(state_file=tmp_path / "workspace.json")) as client:
        session_id = client.post("/api/sessions", headers=headers).json()["id"]
        draft = CandidateIntakeDraft(candidate_id=session_id, name="Test User", email="test@example.com",
            phone="13800000000", education=EducationDraft(school="Example University", degree="BSc",
                major="Computer Science", end_date="2026-06"), skills=["Python"],
            omitted_fields=["education.start_date"])
        first = client.post("/api/intake", headers=headers, json=draft.model_dump(mode="json"))
        assert first.status_code == 200 and first.json()["ready"]
        edited = first.json()["display_resume"]
        edited["summary"] = "Carefully edited by the user."
        saved = client.post("/api/resume/edit", headers=headers,
            json={"candidate_id": session_id, "resume": edited})
        assert saved.status_code == 200

        repeated = client.post("/api/intake", headers=headers, json=draft.model_dump(mode="json"))
        assert repeated.status_code == 200
        assert repeated.json()["display_resume"]["summary"] == "Carefully edited by the user."
        current = client.get(f"/api/resume/current?candidate_id={session_id}", headers=headers).json()
        assert current["display_resume"]["summary"] == "Carefully edited by the user."
