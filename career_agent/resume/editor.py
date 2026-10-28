"""Deterministically promote user-edited resume content into confirmed facts."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from career_agent.resume.models import Resume, Skill

SECTION_KEYS = ("summary", "education", "work", "internship", "experience", "campus", "skills")
SECTION_LABELS = {
    "summary": "个人总结", "education": "教育经历", "work": "工作经历",
    "internship": "实习经历", "experience": "经历", "campus": "校园经历",
    "skills": "专业技能",
}


def preserve_unrequested_resume_facts(
    current: Resume, proposed: Resume, instruction: str
) -> Resume:
    """Avoid losing entire known fields when a provider returns an incomplete resume."""

    removal = r"(?:删除|删掉|移除|去掉|去除|不保留|不要|不需要|清空)"

    def requested_removal(labels: str) -> bool:
        return bool(re.search(
            rf"(?:{removal}).{{0,14}}(?:{labels})|(?:{labels}).{{0,14}}(?:{removal})",
            instruction,
        ))

    profile_labels = {
        "name": "姓名|名字", "email": "邮箱|邮件", "phone": "手机|电话",
        "location": "所在地|现居城市|所在城市", "hometown": "籍贯|老家",
        "links": "网站|个人主页|GitHub|链接",
    }
    profile_updates = {}
    for field, labels in profile_labels.items():
        before = getattr(current.personal_info, field)
        after = getattr(proposed.personal_info, field)
        if before and not after and not requested_removal(labels):
            profile_updates[field] = before
    resume_updates = {}
    if profile_updates:
        resume_updates["personal_info"] = proposed.personal_info.model_copy(
            update=profile_updates
        )
    collections = {
        "educations": "教育经历|学校|学历",
        "work_experiences": "工作经历|工作",
        "internships": "实习经历|实习",
        "project_experiences": "项目经历|项目|科研|竞赛",
        "campus_experiences": "校园经历|校园活动|社会实践经历",
        "skills": "专业技能|技能",
        "summary": "个人总结|自我评价|职业概述",
    }
    for field, labels in collections.items():
        before = getattr(current, field)
        after = getattr(proposed, field)
        if before and not after and not requested_removal(labels):
            resume_updates[field] = before
    return proposed.model_copy(update=resume_updates) if resume_updates else proposed


def apply_explicit_section_title_edits(resume: Resume, instruction: str) -> Resume:
    """Honor clear requests to rename headings even when the model edits only the body."""

    titles = dict(resume.section_titles)
    for key, label in SECTION_LABELS.items():
        match = re.search(
            rf"(?:把|将)?{re.escape(label)}(?:这个|这一栏|的)?(?:栏目|标题)?"
            r"\s*(?:改成|改为|换成|更名为|叫)\s*"
            r"([\u4e00-\u9fffA-Za-z0-9]{2,30}?)(?=[，。；;、\s]|$)",
            instruction,
        )
        if match:
            titles[key] = match.group(1)
    if resume.campus_experiences or "校园经历" in instruction:
        social = re.search(r"(?:准确来说|其实)?这(?:个|条)?(?:经历)?(?:是|属于)?"
                           r"\s*(社会实践经历|社会经历)(?=[，。；;、\s]|$)", instruction)
        if social:
            titles["campus"] = social.group(1)
        elif re.search(r"(?:改成|改为)\s*(社会实践经历|社会经历)", instruction):
            match = re.search(r"(?:改成|改为)\s*(社会实践经历|社会经历)", instruction)
            if match:
                titles["campus"] = match.group(1)
    return resume.model_copy(update={"section_titles": titles})


def apply_explicit_profile_edits(resume: Resume, instruction: str) -> tuple[Resume, str | None]:
    """Keep unambiguous contact facts even if a model puts them only in its explanation."""

    urls = []
    for match in re.findall(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", instruction):
        url = match.rstrip(".,;:)")
        parsed = urlsplit(url)
        if parsed.netloc and "." in parsed.netloc:
            urls.append(url)
    links = list(resume.personal_info.links)
    if urls:
        links = list(dict.fromkeys([*urls, *links]))
    if re.search(r"(?:网站|个人主页).{0,16}(?:最前|前面|前边)", instruction):
        links.sort(key=lambda item: "github.com" in urlsplit(item).netloc.casefold())

    def explicit_place(labels: str) -> str | None:
        pattern = (
            rf"(?:{labels})(?:是|为|写为|写成|要写明确为)?"
            rf"\s*[:：]?\s*([\u4e00-\u9fff]{{2,16}})"
        )
        found = re.search(pattern, instruction)
        if not found:
            return None
        return re.split(r"(?:然后|并且|同时|另外|以及)", found.group(1), maxsplit=1)[0]

    city = explicit_place("所在地|所在城市|现居城市")
    hometown = explicit_place("籍贯|老家")
    info = resume.personal_info.model_copy(update={
        "links": links,
        "location": city or resume.personal_info.location,
        "hometown": hometown or resume.personal_info.hometown,
    })
    return resume.model_copy(update={"personal_info": info}), hometown


def normalize_section_order(values: list[str]) -> list[str]:
    """Return every supported section exactly once, preserving the user's order."""

    ordered = [value for value in values if value in SECTION_KEYS]
    ordered = list(dict.fromkeys(ordered))
    return [*ordered, *(value for value in SECTION_KEYS if value not in ordered)]


def confirm_user_edited_resume(resume: Resume) -> Resume:
    """Make visible user edits the authoritative, source-preserving resume version."""

    educations = [
        item.model_copy(update={"source_text": _entry_text("教育", item, (
            "school", "major", "degree", "start_date", "end_date", "description"
        ))})
        for item in resume.educations
    ]
    work = [
        item.model_copy(update={"source_text": _entry_text("工作", item, (
            "company", "title", "start_date", "end_date", "description"
        ))})
        for item in resume.work_experiences
    ]
    internships = [
        item.model_copy(update={"source_text": _entry_text("实习", item, (
            "company", "title", "start_date", "end_date", "description"
        ))})
        for item in resume.internships
    ]
    projects = [
        item.model_copy(update={"source_text": _entry_text("经历", item, (
            "name", "role", "project_type", "start_date", "end_date",
            "description", "technologies"
        ))})
        for item in resume.project_experiences
    ]
    campus = [
        item.model_copy(update={"source_text": _entry_text("校园", item, (
            "organization", "role", "start_date", "end_date", "description"
        ))})
        for item in resume.campus_experiences
    ]
    skill_text = "技能：" + "、".join(item.name for item in resume.skills)
    skills = [
        Skill(
            name=item.name,
            source_text=skill_text,
            category=item.category,
            proficiency=item.proficiency,
        )
        for item in resume.skills
    ]
    contact = resume.personal_info
    lines = [
        contact.name or "",
        *(value for value in (contact.email, contact.phone, contact.location,
                             contact.hometown) if value),
        *contact.links,
        *(item.source_text for item in educations),
        *(item.source_text for item in work),
        *(item.source_text for item in internships),
        *(item.source_text for item in projects),
        *(item.source_text for item in campus),
    ]
    if resume.summary:
        lines.append(f"个人总结：{resume.summary}")
    if skills:
        lines.append(skill_text)
    return resume.model_copy(
        update={
            "version": _confirmed_version(resume.version),
            "raw_text": "\n".join(value for value in lines if value),
            "educations": educations,
            "work_experiences": work,
            "internships": internships,
            "project_experiences": projects,
            "campus_experiences": campus,
            "skills": skills,
        }
    )


def _entry_text(label: str, item: object, fields: tuple[str, ...]) -> str:
    parts: list[str] = []
    for field in fields:
        value = getattr(item, field, None)
        if isinstance(value, list):
            if value:
                parts.append("、".join(str(entry) for entry in value))
        elif value is not None and not isinstance(value, bool):
            parts.append(str(value))
    return f"{label}：" + "；".join(parts)


def _confirmed_version(version: str) -> str:
    return version if version.endswith("-confirmed") else f"{version}-confirmed"
