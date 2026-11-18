"""Match JD terms to exact spans already present in a resume."""

from __future__ import annotations

import re

from career_agent.resume.models import Resume


def matching_terms(resume: Resume, jd_text: str, extra_terms: list[str] | None = None) -> list[str]:
    candidates = [item.name for item in resume.skills]
    candidates += extra_terms or []
    candidates += re.findall(r"[A-Za-z][A-Za-z0-9+#-]{2,}(?:\s+[A-Za-z][A-Za-z0-9+#-]{2,}){0,2}", jd_text)
    candidates += re.findall(r"[\u4e00-\u9fff]{3,8}", jd_text)
    text = "\n".join([resume.summary or "", *(item.description or "" for group in (
        resume.educations, resume.work_experiences, resume.internships,
        resume.project_experiences, resume.campus_experiences) for item in group)])
    found = []
    stopwords = {"the", "and", "for", "with", "from", "that", "this", "you", "your", "our", "are", "have", "work", "team", "experience", "requirements"}
    for term in candidates:
        term = term.strip()
        if len(term) >= 3 and term.casefold() not in stopwords and term.casefold() in jd_text.casefold() and term.casefold() in text.casefold():
            found.append(term)
    return sorted(set(found), key=len, reverse=True)[:30]


def emphasis_styles(resume: Resume, terms: list[str]) -> dict[str, dict[str, list[str]]]:
    fields = {"summary": resume.summary or ""}
    for collection in ("educations", "work_experiences", "internships", "project_experiences", "campus_experiences"):
        for index, item in enumerate(getattr(resume, collection)):
            fields[f"{collection}.{index}.description"] = item.description or ""
    return {path: {"emphasis": [term for term in terms if term.casefold() in value.casefold()]}
            for path, value in fields.items() if any(term.casefold() in value.casefold() for term in terms)}
