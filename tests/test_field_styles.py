from hashlib import sha256

from fastapi.testclient import TestClient

from career_agent import CandidateIntakeDraft, EducationDraft
from career_agent.web.app import create_app
from career_agent.web.workspace import CandidateRecord, WorkspaceRecords, WorkspaceStore


def test_field_formatting_persists_after_reopening_session(tmp_path) -> None:
    resume = CandidateIntakeDraft(
        candidate_id="format-test", name="张明", email="z@example.com",
        phone="13800000000", education=EducationDraft(
            school="测试大学", degree="本科", major="计算机"
        ), skills=["Python"],
    ).build_resume()
    key = "formatting-test-workspace-key-long-enough"
    headers = {"X-Workspace-Key": key}
    store = WorkspaceStore(tmp_path / "workspace.json")
    store.write(WorkspaceRecords(
        candidates={"format-test": CandidateRecord(raw_resume=resume, display_resume=resume)},
        session_owners={"format-test": sha256(key.encode()).hexdigest()},
    ).model_dump_json())

    client = TestClient(create_app(state_file=store.path))
    saved = client.post("/api/resume/edit", json={
        "candidate_id": "format-test", "resume": resume.model_dump(mode="json"),
        "line_spacing": 2.0,
        "section_spacing": 10,
        "field_styles": {"personal_info.name": {"size": 18, "bold": True, "underline": True}},
    }, headers=headers)
    assert saved.status_code == 200

    reopened = TestClient(create_app(state_file=store.path)).get(
        "/api/resume/current?candidate_id=format-test", headers=headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["line_spacing"] == 2.0
    assert reopened.json()["section_spacing"] == 10
    assert reopened.json()["field_styles"]["personal_info.name"] == {
        "size": 18.0, "bold": True, "underline": True, "emphasis": [],
    }
