from career_agent import CandidateIntakeDraft, EducationDraft
from career_agent.web.app import IntakeConversationSession, _next_intake_message


def test_required_guidance_is_explained_once_and_later_questions_are_direct() -> None:
    intake = IntakeConversationSession(draft=CandidateIntakeDraft(candidate_id="prompt-test"))
    first, _, _ = _next_intake_message(intake)
    intake.messages.append({"role": "assistant", "content": first})
    second, missing, _ = _next_intake_message(intake)

    assert "不想提供" in first
    assert "不想提供" not in second
    assert "一句话回答" not in second
    assert "为了生成可用的简历" not in second
    assert "姓名" in second
    assert missing


def test_optional_transition_and_skip_instruction_are_not_repeated_for_each_topic() -> None:
    intake = IntakeConversationSession(draft=CandidateIntakeDraft(
        candidate_id="prompt-test", name="测试用户", email="test@example.com",
        phone="13800000000", skills=["Python"],
        education=EducationDraft(
            school="测试大学", degree="本科", major="计算机",
            start_date="2018-09", end_date="2022-06",
        ),
    ))
    first, _, _ = _next_intake_message(intake)
    intake.messages.append({"role": "assistant", "content": first})
    intake.optional_topic_index += 1
    second, _, _ = _next_intake_message(intake)

    assert "全部跳过" in first
    assert "基础信息已经整理好" not in second
    assert "全部跳过" not in second
    assert "没有可以回复" not in second
    assert "课程" in second
