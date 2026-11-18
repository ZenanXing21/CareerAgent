from career_agent.resume.talent_pool import add_fact, collect_user_message, delete_fact, relevant_facts
from career_agent.web.workspace import WorkspaceRecords


def test_talent_pool_survives_restart_and_chat_deletion(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from career_agent.web.app import create_app

    state_file = tmp_path / "workspace.json"
    headers = {"X-Workspace-Key": "talent-pool-test-workspace-key-123456789"}
    resume = {"resume_id": "resume-test", "version": "v1", "raw_text": "Python skill",
              "personal_info": {"name": "Test User"},
              "skills": [{"name": "Python", "source_text": "Python skill"}]}
    with TestClient(create_app(state_file=state_file)) as client:
        session_id = client.post("/api/sessions", headers=headers).json()["id"]
        restored = client.post("/api/workspace/restore", headers=headers,
            json={"candidates": {session_id: {"raw_resume": resume, "display_resume": resume}}})
        assert restored.status_code == 200
        edited = client.post("/api/resume/edit", headers=headers, json={
            "candidate_id": session_id, "variant": "polished", "resume": resume})
        assert edited.status_code == 200
        assert client.get("/api/talent-pool", headers=headers).json()["facts"][0]["text"] == "Python"
        assert client.get("/api/talent-pool", headers={"X-Workspace-Key": "different-workspace-key-1234567890"}).json()["facts"] == []
        deleted = client.post("/api/resume/agent", headers=headers,
            json={"candidate_id": session_id, "message": "从人才池删除 Python"})
        assert deleted.status_code == 200
    with TestClient(create_app(state_file=state_file)) as client:
        assert client.get("/api/talent-pool", headers=headers).json()["facts"] == []


def test_pool_accumulates_across_sessions_and_deletion_blocks_replay() -> None:
    pool = {"facts": {}, "deleted": []}
    assert add_fact(pool, "skill", "Python", "session-a", "intake")
    assert add_fact(pool, "skill", "Python", "session-b", "user_message")
    assert len(pool["facts"]) == 1
    assert len(next(iter(pool["facts"].values()))["sources"]) == 2
    assert relevant_facts(pool, "需要 Python 数据分析")
    assert not relevant_facts(pool, "需要工业设计")
    assert delete_fact(pool, "skill", "Python")
    assert not add_fact(pool, "skill", "Python", "session-a", "intake")
    assert not relevant_facts(pool, "需要 Python 数据分析")


def test_jd_is_not_collected_as_user_skill_and_owner_pools_are_separate() -> None:
    first = {"facts": {}, "deleted": []}
    second = {"facts": {}, "deleted": []}
    collect_user_message(first, "岗位要求：我会 Python，熟悉机器学习", "a")
    assert not first["facts"]
    collect_user_message(first, "我会 Python、SQL", "a")
    assert first["facts"] and not second["facts"]
    restored = WorkspaceRecords.model_validate_json(WorkspaceRecords(talent_pools={"owner-a": first, "owner-b": second}).model_dump_json())
    assert restored.talent_pools["owner-a"]["facts"]
    assert not restored.talent_pools["owner-b"]["facts"]
