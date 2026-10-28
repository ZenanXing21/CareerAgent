from career_agent import Resume, inspect_resume


def test_inspector_is_pure_python_and_does_not_require_provider() -> None:
    result = inspect_resume(Resume(resume_id="r", version="v", raw_text="简历"))
    assert result.has_name is False
    assert result.work_count == result.internship_count == 0
    assert result.missing_fields == ["personal_info.name", "educations", "skills"]
