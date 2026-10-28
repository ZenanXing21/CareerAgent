"""Safe, dependency-free HTML preview for an initial structured resume."""

from html import escape
from urllib.parse import urlsplit

from career_agent.resume.models import ProjectExperience, Resume


def render_resume_html(
    resume: Resume,
    *,
    photo_asset: str | None = None,
    hometown: str | None = None,
) -> str:
    info = resume.personal_info
    contact_values = [value for value in (info.email, info.phone) if value]
    if info.location:
        contact_values.append(f"所在地：{info.location}")
    if hometown or info.hometown:
        contact_values.append(f"籍贯：{hometown or info.hometown}")
    contact = " · ".join(escape(value) for value in contact_values)
    links = []
    for value in info.links:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        label = "GitHub" if "github.com" in parsed.netloc.casefold() else "个人网站"
        links.append(
            f'{label}：<a href="{escape(value, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{escape(value)}</a>'
        )
    profile_links = f'<p class="profile-links">{" · ".join(links)}</p>' if links else ""
    photo = (
        f'<img class="photo" src="{escape(photo_asset, quote=True)}" alt="候选人照片">'
        if photo_asset
        else ""
    )
    sections: list[str] = []
    def heading(key: str, default: str) -> str:
        return resume.section_titles.get(key, default)

    if resume.summary:
        sections.append(_section(heading("summary", "个人总结"), [escape(resume.summary)]))
    if resume.educations:
        sections.append(
            _section(
                heading("education", "教育经历"),
                [
                    _experience_item(
                        item.school or "教育经历",
                        " · ".join(value for value in (item.major, item.degree) if value),
                        item.start_date,
                        item.end_date,
                        item.description,
                    )
                    for item in resume.educations
                ],
            )
        )
    if resume.project_experiences:
        sections.append(
            _section(
                heading("experience", "经历"),
                [
                    _experience_item(
                        item.name or "经历",
                        item.role,
                        item.start_date,
                        item.end_date,
                        _project_description(item),
                    )
                    for item in resume.project_experiences
                ],
            )
        )
    if resume.work_experiences:
        sections.append(
            _section(
                heading("work", "工作经历"),
                [
                    _experience_item(
                        item.company or "工作经历",
                        item.title,
                        item.start_date,
                        item.end_date,
                        item.description,
                    )
                    for item in resume.work_experiences
                ],
            )
        )
    if resume.internships:
        sections.append(
            _section(
                heading("internship", "实习经历"),
                [
                    _experience_item(
                        item.company or "实习经历",
                        item.title,
                        item.start_date,
                        item.end_date,
                        item.description,
                    )
                    for item in resume.internships
                ],
            )
        )
    if resume.campus_experiences:
        sections.append(
            _section(
                heading("campus", "校园经历"),
                [
                    _experience_item(
                        item.organization or "校园经历",
                        item.role,
                        item.start_date,
                        item.end_date,
                        item.description,
                    )
                    for item in resume.campus_experiences
                ],
            )
        )
    if resume.skills:
        sections.append(_section(heading("skills", "专业技能"), [
            "、".join(escape(item.name) for item in resume.skills)
        ]))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{escape(info.name or "简历")}</title>
<style>
*{{box-sizing:border-box}}html{{background:#e9eef2}}
body{{font-family:Arial,'Microsoft YaHei',sans-serif;
width:210mm;min-height:297mm;margin:0 auto;padding:18mm 19mm;color:#253342;line-height:1.62;
background:#fff;font-size:14px}}header{{display:flex;justify-content:space-between;align-items:flex-start;
gap:24px;padding-bottom:15px;border-bottom:2px solid #176b72}}h1{{margin:0 0 7px;font-size:29px;
letter-spacing:1px;color:#17212b}}header p{{margin:0;color:#526371}}.photo{{width:26mm;height:34mm;
object-fit:cover;border-radius:3px}}header .profile-links{{margin-top:7px;overflow-wrap:anywhere}}
header .profile-links a{{color:#176b72}}
section{{margin-top:19px;break-inside:avoid}}h2{{margin:0 0 9px;
padding-bottom:4px;font-size:17px;letter-spacing:.5px;color:#176b72;
border-bottom:1px solid #8ebbc0}}
.resume-entry{{margin:0 0 11px}}.resume-entry:last-child{{margin-bottom:0}}
.resume-entry>strong{{font-size:14px;
color:#1e2b37}}.resume-entry p{{margin:4px 0 0;color:#3f4f5c;white-space:pre-line}}
.resume-entry small{{float:right;margin-left:16px;color:#667784;font-size:12px}}
@media(max-width:800px){{body{{width:100%;min-height:100vh;padding:30px}}}}
@media print{{html{{background:#fff}}body{{width:auto;min-height:auto;margin:0}}}}
</style></head>
<body><header><div><h1>{escape(info.name or "")}</h1><p>{contact}</p>
{profile_links}</div>{photo}</header>
{"".join(sections)}</body></html>"""


def _section(title: str, items: list[str]) -> str:
    entries = "".join(f'<div class="resume-entry">{item}</div>' for item in items)
    return f"<section><h2>{escape(title)}</h2>{entries}</section>"


def _project_description(item: ProjectExperience) -> str | None:
    technologies = "相关技术：" + "、".join(item.technologies) if item.technologies else ""
    return "\n".join(part for part in (item.description or "", technologies) if part) or None


def _experience_item(
    title: str,
    role: str | None,
    start_date: str | None,
    end_date: str | None,
    description: str | None,
) -> str:
    heading = " · ".join(escape(value) for value in (title, role) if value)
    dates = " 至 ".join(escape(value) for value in (start_date, end_date) if value)
    suffix = f" <small>{dates}</small>" if dates else ""
    detail = f"<p>{escape(description)}</p>" if description else ""
    return f"<strong>{heading}</strong>{suffix}{detail}"
