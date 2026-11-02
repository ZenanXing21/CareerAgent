"""Presentation language for resume labels."""

import re

from career_agent.resume.models import Resume

ENGLISH_TITLES = {
    "summary": "Professional Summary", "education": "Education",
    "work": "Work Experience", "internship": "Internships",
    "experience": "Projects", "campus": "Campus Experience",
    "skills": "Skills",
}


def english_resume(resume: Resume) -> bool:
    text = " ".join([resume.summary or "", *(resume.section_titles.values()),
                     *(item.description or "" for item in resume.work_experiences)])
    latin = len(re.findall(r"[A-Za-z]", text))
    han = len(re.findall(r"[\u4e00-\u9fff]", text))
    return latin > 20 and latin > han * 2


def section_title(resume: Resume, key: str, default: str) -> str:
    chosen = resume.section_titles.get(key)
    if english_resume(resume):
        return ENGLISH_TITLES.get(key, chosen or default) if not chosen or re.search(r"[\u4e00-\u9fff]", chosen) else chosen
    return chosen or default
