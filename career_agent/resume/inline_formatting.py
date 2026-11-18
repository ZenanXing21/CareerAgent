"""Turn imported inline formatting markers into editable resume text and styles."""

from __future__ import annotations

import re

from career_agent.resume.models import Resume


_INLINE = re.compile(r"(\*\*|__)([^\n]+?)\1")
_BULLET = re.compile(r"(?m)^[ \t]*[-*][ \t]+")


def _normalize_text(value: str | None) -> tuple[str | None, list[str], list[str]]:
    if value is None:
        return None, [], []
    bold: list[str] = []
    underline: list[str] = []

    def replace(match: re.Match[str]) -> str:
        text = match.group(2)
        if text.strip():
            (bold if match.group(1) == "**" else underline).append(text.replace("**", "").replace("__", ""))
        return text

    clean = value
    for _ in range(3):
        updated = _INLINE.sub(replace, clean)
        if updated == clean:
            break
        clean = updated
    clean = _BULLET.sub("• ", clean)
    return clean, list(dict.fromkeys(bold)), list(dict.fromkeys(underline))


def normalize_resume_formatting(
    resume: Resume, field_styles: dict[str, dict]
) -> tuple[Resume, dict[str, dict]]:
    """Keep source bullets and emphasis without displaying raw Markdown markers."""
    styles = {path: dict(style) for path, style in field_styles.items()}

    def normalize_field(value: str | None, path: str) -> str | None:
        clean, bold, underline = _normalize_text(value)
        if bold or underline:
            style = styles.setdefault(path, {})
            for key, terms in (("emphasis", bold), ("underline_terms", underline)):
                if terms:
                    style[key] = list(dict.fromkeys([*style.get(key, []), *terms]))
        return clean

    updates = {"summary": normalize_field(resume.summary, "summary")}
    for collection in ("educations", "work_experiences", "internships", "project_experiences", "campus_experiences"):
        entries = []
        for index, entry in enumerate(getattr(resume, collection)):
            field_updates = {}
            for field in ("description", "school", "company", "organization", "name", "title", "role"):
                if hasattr(entry, field):
                    value = getattr(entry, field)
                    cleaned = normalize_field(value, f"{collection}.{index}.{field}")
                    if cleaned != value:
                        field_updates[field] = cleaned
            entries.append(entry.model_copy(update=field_updates) if field_updates else entry)
        updates[collection] = entries
    return resume.model_copy(update=updates), styles


def preserve_source_emphasis(
    resume: Resume, source_text: str, field_styles: dict[str, dict]
) -> dict[str, dict]:
    """Carry explicitly marked source terms through a model's plain-text rewrite."""
    _, bold, underline = _normalize_text(source_text)
    styles = {path: dict(style) for path, style in field_styles.items()}
    fields = {"summary": resume.summary}
    for collection in ("educations", "work_experiences", "internships", "project_experiences", "campus_experiences"):
        for index, entry in enumerate(getattr(resume, collection)):
            for field in ("description", "school", "company", "organization", "name", "title", "role"):
                if hasattr(entry, field):
                    fields[f"{collection}.{index}.{field}"] = getattr(entry, field)
    for path, value in fields.items():
        if not value:
            continue
        for key, terms in (("emphasis", bold), ("underline_terms", underline)):
            matched = [term for term in terms if len(term) <= 80 and term.casefold() in value.casefold()]
            if matched:
                style = styles.setdefault(path, {})
                style[key] = list(dict.fromkeys([*style.get(key, []), *matched]))
    return styles
