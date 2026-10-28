from career_agent import CandidateIntakeDraft, EducationDraft
from career_agent.resume.editor import (
    apply_explicit_profile_edits,
    apply_explicit_section_title_edits,
    confirm_user_edited_resume,
    preserve_unrequested_resume_facts,
)
from career_agent.resume.models import CampusExperience


def _resume():
    return CandidateIntakeDraft(
        candidate_id="profile-edit",
        name="林同学",
        email="demo@example.com",
        phone="13800000000",
        education=EducationDraft(school="示例大学", major="计算机", degree="本科"),
        skills=["Python"],
    ).build_resume()


def test_agent_profile_instruction_becomes_visible_structured_fields() -> None:
    resume = _resume()
    instruction = (
        "我的个人网站是https://portfolio.example GitHub链接是"
        "https://github.com/example，所在地是上海，老家是江苏苏州。"
    )

    updated, hometown = apply_explicit_profile_edits(resume, instruction)
    confirmed = confirm_user_edited_resume(updated)

    assert confirmed.personal_info.links == [
        "https://portfolio.example", "https://github.com/example"
    ]
    assert confirmed.personal_info.location == "上海"
    assert confirmed.personal_info.hometown == hometown == "江苏苏州"
    assert "https://portfolio.example" in confirmed.raw_text
    assert "江苏苏州" in confirmed.raw_text


def test_website_can_be_moved_before_github_without_repeating_urls() -> None:
    resume = _resume()
    info = resume.personal_info.model_copy(update={
        "links": ["https://github.com/example", "https://portfolio.example"]
    })
    resume = resume.model_copy(update={"personal_info": info})

    updated, _ = apply_explicit_profile_edits(resume, "把个人网站放在最前面、联系方式下面")

    assert updated.personal_info.links == [
        "https://portfolio.example", "https://github.com/example"
    ]


def test_agent_correction_renames_campus_heading_without_changing_entry() -> None:
    resume = _resume().model_copy(update={"campus_experiences": [CampusExperience(
        id="campus_001", source_text="参与求职助手推广",
        organization="校园项目", role="推广", description="参与求职助手推广",
    )]})
    updated = apply_explicit_section_title_edits(resume, "准确来说这是社会实践经历")

    assert updated.section_titles["campus"] == "社会实践经历"


def test_explicit_section_heading_rename_is_structured() -> None:
    resume = _resume()
    updated = apply_explicit_section_title_edits(resume, "把个人总结标题改成职业概述")

    assert updated.section_titles["summary"] == "职业概述"


def test_unrelated_agent_edit_does_not_erase_existing_sections_or_links() -> None:
    source = _resume().model_copy(update={
        "summary": "认真负责。",
        "campus_experiences": [CampusExperience(
            id="campus_001", source_text="校园活动", organization="校园活动",
        )],
    })
    source = source.model_copy(update={"personal_info": source.personal_info.model_copy(
        update={"links": ["https://example.com"], "location": "上海"}
    )})
    proposed = source.model_copy(update={
        "summary": None, "campus_experiences": [],
        "personal_info": source.personal_info.model_copy(
            update={"links": [], "location": None}
        ),
    })

    restored = preserve_unrequested_resume_facts(source, proposed, "把校园经历标题改为社会实践经历")

    assert restored.summary == source.summary
    assert restored.campus_experiences == source.campus_experiences
    assert restored.personal_info.links == source.personal_info.links
    assert restored.personal_info.location == source.personal_info.location


def test_explicit_removal_of_a_section_is_respected() -> None:
    source = _resume().model_copy(update={"campus_experiences": [CampusExperience(
        id="campus_001", source_text="校园活动", organization="校园活动",
    )]})
    proposed = source.model_copy(update={"campus_experiences": []})

    updated = preserve_unrequested_resume_facts(source, proposed, "把校园经历删除")

    assert updated.campus_experiences == []
