"""Pure-Python resume completeness inspection."""

from career_agent.resume.models import Resume, ResumeInspection


def inspect_resume(resume: Resume) -> ResumeInspection:
    missing: list[str] = []
    if resume.personal_info.name is None:
        missing.append("personal_info.name")
    if not resume.educations:
        missing.append("educations")
    if not resume.skills:
        missing.append("skills")
    return ResumeInspection(
        has_name=resume.personal_info.name is not None,
        education_count=len(resume.educations),
        work_count=len(resume.work_experiences),
        internship_count=len(resume.internships),
        project_count=len(resume.project_experiences),
        campus_count=len(resume.campus_experiences),
        skill_count=len(resume.skills),
        missing_fields=missing,
    )
