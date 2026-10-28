from __future__ import annotations

import asyncio
import importlib

from fastapi.testclient import TestClient

from career_agent import CandidateIntakeDraft, CareerProductService, EducationDraft
from career_agent.onboarding.models import IntakeConversationUpdate
from career_agent.web.app import IntakeConversationSession, _next_intake_message, create_app


def _draft(**updates) -> CandidateIntakeDraft:
    values = {
        "candidate_id": "omissions-test",
        "name": "测试用户",
        "email": "test@example.com",
        "phone": "13800000000",
        "education": EducationDraft(
            school="测试大学", degree="本科", major="计算机", end_date="2022-06"
        ),
        "skills": ["Python"],
    }
    values.update(updates)
    return CandidateIntakeDraft(**values)


def test_explicitly_omitted_enrolment_date_does_not_get_asked_again() -> None:
    draft = _draft(omitted_fields=["education.start_date"])
    session = IntakeConversationSession(draft=draft)

    message, missing, ready = _next_intake_message(session)

    assert missing == []
    assert "请提供入学时间" not in message
    assert "可选信息" in message
    assert not ready


def test_omitted_contact_and_education_are_not_fabricated_or_blocked() -> None:
    draft = CandidateIntakeDraft(
        candidate_id="private-profile",
        skills=["Python"],
        omitted_fields=["name", "email", "phone", "education"],
    )
    service = CareerProductService(provider=object(), job_source=object())

    result = service.create_initial_resume(draft)

    assert result.ready
    assert result.resume.personal_info.name is None
    assert result.resume.personal_info.email is None
    assert result.resume.educations == []
    assert "None" not in result.resume.raw_text
    assert "未提供" not in result.resume.raw_text
    assert "Python" in result.preview_html


def test_declining_every_field_still_requires_some_real_content() -> None:
    draft = CandidateIntakeDraft(
        candidate_id="empty-profile",
        omitted_fields=["name", "email", "phone", "education", "skills"],
    )
    service = CareerProductService(provider=object(), job_source=object())

    result = service.create_initial_resume(draft)

    assert not result.ready
    assert [issue.field for issue in result.issues] == ["content"]


def test_omission_survives_next_model_turn_and_can_be_replaced_by_a_real_value() -> None:
    class Provider:
        async def update_candidate_intake(self, *, draft, message, conversation):
            incoming = draft.model_copy(deep=True, update={"omitted_fields": []})
            if message == "入学时间是2018年9月":
                incoming.education.start_date = "2018-09"
            return IntakeConversationUpdate(acknowledgement="已整理", draft=incoming)

    service = CareerProductService(provider=Provider(), job_source=object())
    initial = _draft(omitted_fields=["education.start_date"])

    first = asyncio.run(
        service.update_candidate_intake(draft=initial, message="我还会SQL", conversation=[])
    )
    assert "education.start_date" in first.draft.omitted_fields
    second = asyncio.run(
        service.update_candidate_intake(
            draft=first.draft, message="入学时间是2018年9月", conversation=[]
        )
    )
    assert "education.start_date" not in second.draft.omitted_fields
    assert second.draft.education.start_date == "2018-09"


def test_contextual_refusal_advances_and_generated_resume_can_be_confirmed(
    monkeypatch,
) -> None:
    web = importlib.import_module("career_agent.web.app")

    class Provider:
        async def update_candidate_intake(self, *, draft, message, conversation):
            return IntakeConversationUpdate(
                acknowledgement="已记录你的选择。", draft=_draft()
            )

    async def polished(service, draft):
        result = service.create_initial_resume(draft)
        return result.model_copy(update={"ai_polished": True})

    monkeypatch.setattr(web.OpenAICompatibleProvider, "from_env", lambda: Provider())
    monkeypatch.setattr(web.LiepinMCPAdapter, "from_env", lambda: object())
    monkeypatch.setattr(CareerProductService, "create_ai_initial_resume", polished)
    client = TestClient(create_app())
    candidate = "omissions-test"
    initial = client.post(
        "/api/intake/chat", json={"candidate_id": candidate, "message": "这是我的资料"}
    )
    assert initial.status_code == 200
    assert "请提供入学时间" in initial.json()["missing_required"]

    refusal = client.post(
        "/api/intake/chat",
        json={"candidate_id": candidate, "message": "我不提供，别给我生成这个"},
    )
    assert refusal.status_code == 200
    assert not refusal.json()["missing_required"]
    assert "请提供入学时间" not in refusal.json()["assistant_message"]
    assert "education.start_date" in refusal.json()["draft"]["omitted_fields"]

    client.post(
        "/api/intake/chat", json={"candidate_id": candidate, "message": "全部跳过"}
    )
    generated = client.post(
        "/api/intake/chat", json={"candidate_id": candidate, "generate": True}
    )
    assert generated.status_code == 200
    assert generated.json()["generated"]
    resume = generated.json()["display_resume"]
    assert resume["educations"][0]["start_date"] is None
    confirmed = client.post(
        "/api/resume/confirm", json={"candidate_id": candidate, "resume": resume}
    )
    assert confirmed.status_code == 200


def test_private_resume_can_be_confirmed_and_downloaded_without_missing_contacts(
    monkeypatch,
) -> None:
    web = importlib.import_module("career_agent.web.app")

    async def polished(service, draft):
        return service.create_initial_resume(draft).model_copy(update={"ai_polished": True})

    monkeypatch.setattr(web.OpenAICompatibleProvider, "from_env", lambda: object())
    monkeypatch.setattr(web.LiepinMCPAdapter, "from_env", lambda: object())
    monkeypatch.setattr(CareerProductService, "create_ai_initial_resume", polished)
    client = TestClient(create_app())
    draft = CandidateIntakeDraft(
        candidate_id="private-profile", skills=["Python"],
        omitted_fields=["name", "email", "phone", "education"],
    )
    generated = client.post("/api/intake", json=draft.model_dump(mode="json"))
    assert generated.status_code == 200
    assert generated.json()["ready"]
    resume = generated.json()["display_resume"]
    confirmed = client.post(
        "/api/resume/confirm", json={"candidate_id": draft.candidate_id, "resume": resume}
    )
    assert confirmed.status_code == 200
    downloaded = client.get(
        "/api/resume/download/polished/docx", params={"candidate_id": draft.candidate_id}
    )
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"PK")
