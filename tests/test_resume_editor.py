from career_agent import CandidateIntakeDraft, EducationDraft, ExperienceDraft
from career_agent.resume.editor import confirm_user_edited_resume, normalize_section_order


def test_user_edits_become_source_preserving_confirmed_facts() -> None:
    resume = CandidateIntakeDraft(
        candidate_id="edited",
        name="张明",
        email="z@example.com",
        phone="13800000000",
        education=EducationDraft(school="测试大学", degree="本科", major="计算机"),
        skills=["Python"],
        experiences=[ExperienceDraft(content="完成数据清洗")],
    ).build_resume()
    edited = resume.model_copy(
        update={
            "project_experiences": [
                resume.project_experiences[0].model_copy(
                    update={"name": "招聘数据项目", "role": "开发者"}
                )
            ]
        }
    )

    confirmed = confirm_user_edited_resume(edited)

    assert confirmed.version.endswith("-confirmed")
    assert "招聘数据项目" in confirmed.project_experiences[0].source_text
    assert confirmed.project_experiences[0].source_text in confirmed.raw_text


def test_section_order_is_complete_unique_and_user_ordered() -> None:
    assert normalize_section_order(["skills", "education", "skills", "unknown"]) == [
        "skills",
        "education",
        "summary",
        "work",
        "internship",
        "experience",
        "campus",
    ]
