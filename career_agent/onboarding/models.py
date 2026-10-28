"""Candidate onboarding draft and deterministic base-resume construction."""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import Field, field_validator

from career_agent.models import DomainModel, NonEmptyStr, _unique_strings
from career_agent.resume.models import (
    Education,
    PersonalInfo,
    ProjectExperience,
    Resume,
    Skill,
)


class IntakeIssue(DomainModel):
    field: NonEmptyStr
    message: NonEmptyStr
    required: bool = True


class EducationDraft(DomainModel):
    school: NonEmptyStr | None = None
    degree: NonEmptyStr | None = None
    major: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    courses: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("courses")
    @classmethod
    def unique_education_values(cls, values: list[str], info: object) -> list[str]:
        return _unique_strings(values, getattr(info, "field_name", "education_values"))


class ProjectDraft(DomainModel):
    name: NonEmptyStr | None = None
    role: NonEmptyStr | None = None
    description: NonEmptyStr | None = None
    technologies: list[NonEmptyStr] = Field(default_factory=list)
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    is_course_project: bool | None = None

    @field_validator("technologies")
    @classmethod
    def unique_technologies(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "technologies")


class ExperienceDraft(DomainModel):
    """Free-form experience collected before AI classification."""

    name: NonEmptyStr | None = None
    role: NonEmptyStr | None = None
    date_range: NonEmptyStr | None = None
    content: NonEmptyStr | None = None
    source_text: NonEmptyStr | None = None
    technologies: list[NonEmptyStr] = Field(default_factory=list)
    kind_hint: (
        Literal[
            "work",
            "internship",
            "campus",
            "competition",
            "research",
            "course",
            "project",
        ]
        | None
    ) = None

    @field_validator("technologies")
    @classmethod
    def unique_technologies(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "technologies")


class ExperienceKind(str, Enum):
    WORK = "work"
    INTERNSHIP = "internship"
    CAMPUS = "campus"
    COMPETITION = "competition"
    RESEARCH = "research"
    COURSE = "course"
    PROJECT = "project"


class PolishedExperience(DomainModel):
    source_index: int = Field(ge=0)
    kind: ExperienceKind
    title: NonEmptyStr
    role: NonEmptyStr
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    description: NonEmptyStr
    technologies: list[NonEmptyStr] = Field(default_factory=list)

    @field_validator("technologies")
    @classmethod
    def unique_technologies(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "technologies")


class PolishedEducation(DomainModel):
    source_index: int = Field(ge=0)
    description: NonEmptyStr | None = None


class IntakePolish(DomainModel):
    normalized_hometown: NonEmptyStr | None = None
    normalized_skills: list[NonEmptyStr] = Field(default_factory=list)
    professional_summary: NonEmptyStr | None = None
    educations: list[PolishedEducation] = Field(default_factory=list)
    experiences: list[PolishedExperience] = Field(default_factory=list)

    @field_validator("normalized_skills")
    @classmethod
    def unique_skills(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "normalized_skills")


class ExperienceSemanticFacts(DomainModel):
    source_index: int = Field(ge=0)
    kind: ExperienceKind
    organization: NonEmptyStr | None = None
    role: NonEmptyStr | None = None
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    actions: list[NonEmptyStr] = Field(default_factory=list)
    outcomes: list[NonEmptyStr] = Field(default_factory=list)


class IntakeSemanticFacts(DomainModel):
    profile_keywords: list[NonEmptyStr] = Field(default_factory=list)
    experiences: list[ExperienceSemanticFacts] = Field(default_factory=list)


class IntakeProfilePolish(DomainModel):
    """Small, reliable semantic result for profile fields outside experiences."""

    normalized_hometown: NonEmptyStr | None = None
    normalized_skills: list[NonEmptyStr] = Field(default_factory=list)
    professional_summary: NonEmptyStr | None = None
    educations: list[PolishedEducation] = Field(default_factory=list)

    @field_validator("normalized_skills")
    @classmethod
    def unique_skills(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "normalized_skills")


def is_intake_field_omitted(path: str, omitted_fields: list[str]) -> bool:
    aliases = {path}
    if path.startswith("educations."):
        aliases.add(re.sub(r"^educations\.\d+", "education", path))
    elif path.startswith("education."):
        aliases.add(path.replace("education.", "educations.0.", 1))
    return any(
        alias == omitted or alias.startswith(omitted + ".")
        for omitted in omitted_fields
        for alias in aliases
    )


def unresolved_resume_fields(missing_fields: list[str], omitted_fields: list[str]) -> list[str]:
    remaining = []
    for field in missing_fields:
        path = {"personal_info.name": "name", "educations": "education"}.get(field, field)
        if is_intake_field_omitted(path, omitted_fields):
            continue
        if field == "educations" and all(
            is_intake_field_omitted(f"education.{part}", omitted_fields)
            for part in ("school", "major", "degree")
        ):
            continue
        remaining.append(field)
    return remaining


class CandidateIntakeDraft(DomainModel):
    """Permissive form state; required-field errors are returned for UI rendering."""

    candidate_id: NonEmptyStr
    name: NonEmptyStr | None = None
    email: NonEmptyStr | None = None
    phone: NonEmptyStr | None = None
    current_city: NonEmptyStr | None = None
    hometown: NonEmptyStr | None = None
    education: EducationDraft = Field(default_factory=EducationDraft)
    educations: list[EducationDraft] = Field(default_factory=list)
    skills: list[NonEmptyStr] = Field(default_factory=list)
    experiences: list[ExperienceDraft] = Field(default_factory=list)
    projects: list[ProjectDraft] = Field(default_factory=list)
    self_summary: NonEmptyStr | None = None
    intended_jd: NonEmptyStr | None = None
    photo_asset: NonEmptyStr | None = None
    omitted_fields: list[NonEmptyStr] = Field(
        default_factory=list,
        description="Fields the user explicitly declined to provide or asked to omit",
    )

    @field_validator("omitted_fields")
    @classmethod
    def validate_omitted_fields(cls, values: list[str]) -> list[str]:
        for value in values:
            if not re.fullmatch(
                r"name|email|phone|skills|current_city|hometown|self_summary|intended_jd|photo_asset|"
                r"(?:education|educations\.\d+)(?:\.(?:school|major|degree|start_date|end_date|courses))?",
                value,
            ):
                raise ValueError(f"unsupported omitted field: {value}")
        return list(dict.fromkeys(values))

    def is_omitted(self, path: str) -> bool:
        return is_intake_field_omitted(path, self.omitted_fields)

    def field_value(self, path: str) -> object:
        parts = path.split(".")
        current: object = self
        for part in parts:
            if isinstance(current, list):
                index = int(part)
                current = current[index] if index < len(current) else None
            else:
                current = getattr(current, part, None)
            if current is None:
                break
        return current

    def without_omitted_values(self) -> CandidateIntakeDraft:
        cleaned = self.model_copy(deep=True)
        for name in (
            "name",
            "email",
            "phone",
            "current_city",
            "hometown",
            "self_summary",
            "intended_jd",
            "photo_asset",
            "skills",
        ):
            if cleaned.is_omitted(name):
                setattr(cleaned, name, [] if name == "skills" else None)
        for prefix, education in [
            ("education", cleaned.education),
            *[(f"educations.{index}", item) for index, item in enumerate(cleaned.educations)],
        ]:
            for name in ("school", "major", "degree", "start_date", "end_date", "courses"):
                if cleaned.is_omitted(f"{prefix}.{name}"):
                    setattr(education, name, [] if name == "courses" else None)
        return cleaned

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, values: list[str]) -> list[str]:
        return _unique_strings(values, "skills")

    def validation_issues(self) -> list[IntakeIssue]:
        checks = [
            ("name", self.name, "请填写姓名"),
            ("email", self.email, "请填写邮箱"),
            ("phone", self.phone, "请填写手机号"),
        ]
        education_prefix = "educations" if self.educations else "education"
        for index, education in enumerate(self.all_educations()):
            prefix = f"{education_prefix}.{index}" if self.educations else education_prefix
            checks.extend(
                (
                    (f"{prefix}.school", education.school, "请填写学校"),
                    (f"{prefix}.major", education.major, "请填写专业"),
                    (f"{prefix}.degree", education.degree, "请选择学历"),
                )
            )
        issues = [
            IntakeIssue(field=field, message=message)
            for field, value, message in checks
            if value is None and not self.is_omitted(field)
        ]
        if not self.skills and not self.is_omitted("skills"):
            issues.append(IntakeIssue(field="skills", message="请至少填写一项技能"))
        for index, experience in enumerate(self.all_experiences()):
            if experience.content is None:
                issues.append(
                    IntakeIssue(
                        field=f"experiences.{index}.content",
                        message="已添加的经历必须填写经历内容",
                    )
                )
        cleaned = self.without_omitted_values()
        if not issues and not any(
            (
                cleaned.name,
                cleaned.email,
                cleaned.phone,
                cleaned.current_city,
                cleaned.hometown,
                cleaned.skills,
                cleaned.self_summary,
                any(any(item.model_dump().values()) for item in cleaned.all_educations()),
                any(item.content for item in cleaned.all_experiences()),
            )
        ):
            issues.append(
                IntakeIssue(
                    field="content",
                    message="请至少提供一项想展示的真实资料、技能或经历",
                )
            )
        return issues

    def all_educations(self) -> list[EducationDraft]:
        return self.educations or [self.education]

    def all_experiences(self) -> list[ExperienceDraft]:
        legacy = [
            ExperienceDraft(
                name=item.name,
                role=item.role,
                date_range=" 至 ".join(value for value in (item.start_date, item.end_date) if value)
                or None,
                content=item.description,
                technologies=item.technologies,
                kind_hint="course" if item.is_course_project else "project",
            )
            for item in self.projects
        ]
        return [*self.experiences, *legacy]

    def build_resume(self, *, version: str = "v1") -> Resume:
        self = self.without_omitted_values()
        issues = self.validation_issues()
        if issues:
            fields = ", ".join(issue.field for issue in issues)
            raise ValueError(f"candidate intake is incomplete: {fields}")

        education_drafts = [
            item
            for item in self.all_educations()
            if any(
                (
                    item.school,
                    item.major,
                    item.degree,
                    item.start_date,
                    item.end_date,
                    item.courses,
                )
            )
        ]
        education_sources = [_education_text(item) for item in education_drafts]
        experiences = self.all_experiences()
        experience_sources = [_experience_text(item) for item in experiences]
        skill_source = "技能：" + "、".join(self.skills)
        lines = [self.name] if self.name else []
        if self.email:
            lines.append(f"邮箱：{self.email}")
        if self.phone:
            lines.append(f"电话：{self.phone}")
        if self.current_city:
            lines.append(f"现居：{self.current_city}")
        if self.hometown:
            lines.append(f"籍贯：{self.hometown}")
        lines.extend(education_sources)
        if self.skills:
            lines.append(skill_source)
        lines.extend(experience_sources)
        if self.self_summary:
            lines.append(f"个人总结：{self.self_summary}")
        raw_text = "\n".join(lines)
        if not raw_text.strip():
            raise ValueError("请至少提供一项真实的教育、技能、经历或个人资料以生成简历")

        educations = [
            Education(
                id=f"education_{index:03d}",
                source_text=source,
                school=item.school,
                degree=item.degree,
                major=item.major,
                start_date=item.start_date,
                end_date=item.end_date,
                description=_education_description(item),
            )
            for index, (item, source) in enumerate(
                zip(education_drafts, education_sources, strict=True), start=1
            )
        ]
        projects = [
            ProjectExperience(
                id=f"experience_{index:03d}",
                source_text=source,
                name=experience.name,
                role=experience.role,
                description=experience.content,
                technologies=experience.technologies,
                start_date=_split_date_range(experience.date_range)[0],
                end_date=_split_date_range(experience.date_range)[1],
            )
            for index, (experience, source) in enumerate(
                zip(experiences, experience_sources, strict=True), start=1
            )
        ]
        return Resume(
            resume_id=f"resume-{self.candidate_id}",
            version=version,
            raw_text=raw_text,
            summary=self.self_summary,
            personal_info=PersonalInfo(
                name=self.name,
                email=self.email,
                phone=self.phone,
                location=self.current_city,
                hometown=self.hometown,
            ),
            educations=educations,
            project_experiences=projects,
            skills=[Skill(name=value, source_text=skill_source) for value in self.skills],
        )


class IntakeConversationUpdate(DomainModel):
    """Structured merge result from one conversational intake turn."""

    acknowledgement: NonEmptyStr
    draft: CandidateIntakeDraft
    covered_optional_topics: list[
        Literal[
            "location",
            "education_extras",
            "work",
            "projects",
            "credentials",
            "target",
            "photo",
        ]
    ] = Field(default_factory=list)
    clarification_question: NonEmptyStr | None = None


class IntakeImageAnalysis(DomainModel):
    """Classification result for an image uploaded during conversational intake."""

    kind: Literal["portrait", "resume_document", "other"]
    text: str = ""


def _education_text(value: EducationDraft) -> str:
    parts = [value.school, value.major, value.degree, value.start_date, value.end_date]
    if value.courses:
        parts.append("相关课程：" + "、".join(value.courses))
    return "教育经历：" + "；".join(part for part in parts if part)


def _education_description(value: EducationDraft) -> str | None:
    details: list[str] = []
    if value.courses:
        details.append("相关课程：" + "、".join(value.courses))
    return "；".join(details) or None


def _experience_text(value: ExperienceDraft) -> str:
    parts = [value.name, value.role, value.date_range, value.content]
    if value.technologies:
        parts.append("技术：" + "、".join(value.technologies))
    if value.source_text:
        parts.append("原始陈述：" + value.source_text)
    return "经历：" + "；".join(part for part in parts if part)


def _split_date_range(value: str | None) -> tuple[str | None, str | None]:
    """Split common free-form numeric ranges without guessing unknown dates."""

    if not value:
        return None, None
    match = re.fullmatch(
        r"\s*(\d{4}\s*(?:[./-]|年)\s*\d{1,2}\s*月?)\s*"
        r"(?:至|到|—|–|~|～|\s+-\s*|-(?=\s*\d{4}))\s*"
        r"(\d{4}\s*(?:[./-]|年)\s*\d{1,2}\s*月?)\s*",
        value,
    )
    if not match:
        return value, None

    def normalize(part: str) -> str:
        numbers = re.findall(r"\d+", part)
        return f"{numbers[0]}-{int(numbers[1]):02d}"

    return normalize(match.group(1)), normalize(match.group(2))


def validate_intake_polish(draft: CandidateIntakeDraft, polish: IntakePolish) -> IntakePolish:
    if polish.educations:
        expected_educations = set(range(len(draft.all_educations())))
        actual_educations = [item.source_index for item in polish.educations]
        if set(actual_educations) != expected_educations or len(actual_educations) != len(
            expected_educations
        ):
            raise ValueError("AI 整理结果必须逐条对应用户填写的教育经历")
    experiences = draft.all_experiences()
    expected = set(range(len(experiences)))
    actual = [item.source_index for item in polish.experiences]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("AI 整理结果必须逐条对应用户填写的经历")
    for item in polish.experiences:
        source = experiences[item.source_index]
        source_numbers = set(_numbers((source.content or "") + " " + (source.source_text or "")))
        output_numbers = set(_numbers(item.description))
        if not output_numbers.issubset(source_numbers):
            raise ValueError("AI 整理结果包含原始经历中不存在的数字")
        allowed_technologies = [
            *source.technologies,
            source.content or "",
            source.source_text or "",
        ]
        for technology in item.technologies:
            if not any(
                _canonical(technology) in _canonical(value) or _same_skill(technology, value)
                for value in allowed_technologies
            ):
                raise ValueError("AI 整理结果包含用户没有填写的技术")
    if polish.professional_summary:
        source_numbers = set(_numbers(draft.self_summary or ""))
        output_numbers = set(_numbers(polish.professional_summary))
        if not output_numbers.issubset(source_numbers):
            raise ValueError("AI 整理后的个人总结包含原始资料中不存在的数字")
    # Skills are deliberately accepted as a semantic normalization task. A user may enter
    # prose, whitespace-separated values, abbreviations, mixed Chinese/English, or symbols;
    # exact/sub-string validation caused valid model output to surface as a misleading 502.
    # The original text remains in the raw resume and the structured result is promoted to
    # confirmed facts only after the user reviews and confirms it in the resume editor.
    return polish


def _canonical(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def _numbers(value: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?%?", value)


def _same_skill(left: str, right: str) -> bool:
    aliases = {
        "py": "python",
        "python3": "python",
        "js": "javascript",
        "ts": "typescript",
        "postgres": "postgresql",
        "k8s": "kubernetes",
    }
    left_value = aliases.get(_canonical(left), _canonical(left))
    right_value = aliases.get(_canonical(right), _canonical(right))
    return left_value == right_value
