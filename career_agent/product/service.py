"""Application-facing use cases composed from the existing domain workflows."""

from __future__ import annotations

import logging
from typing import Literal, Protocol

from pydantic import Field

from career_agent.interview import InterviewPlan, build_interview_plan
from career_agent.jd.models import JDAnalysis
from career_agent.jd.parser import JDParser
from career_agent.jobs.matcher import calculate_match
from career_agent.jobs.models import Job, JobSearchQuery, MatchResult
from career_agent.llm.base import LLMProvider
from career_agent.models import DomainModel, NonEmptyStr
from career_agent.onboarding.models import (
    CandidateIntakeDraft,
    EducationDraft,
    ExperienceDraft,
    ExperienceKind,
    IntakeConversationUpdate,
    IntakeImageAnalysis,
    IntakeIssue,
    IntakePolish,
    unresolved_resume_fields,
)
from career_agent.onboarding.workflow import build_intake_polish_graph
from career_agent.resume.editor import confirm_user_edited_resume
from career_agent.resume.evidence_matcher import EvidenceMatcher
from career_agent.resume.fact_ledger import build_fact_ledger
from career_agent.resume.inspector import inspect_resume
from career_agent.resume.models import (
    CampusExperience,
    EvidenceMatch,
    ExperienceType,
    ProjectExperience,
    Resume,
    ResumeAgentEdit,
    Skill,
    TailoredResume,
    TailorPlan,
    ValidationReport,
    WorkExperience,
)
from career_agent.resume.renderer import render_resume_html
from career_agent.resume.studio import (
    field_text,
    validate_field_polish,
)
from career_agent.resume.subgraph import build_resume_tailor_graph

logger = logging.getLogger(__name__)


class ProductJobSource(Protocol):
    async def search_jobs(self, query: JobSearchQuery) -> list[Job]: ...

    async def get_job_detail(self, job_id: str) -> Job: ...


class InitialResumeResult(DomainModel):
    ready: bool
    issues: list[IntakeIssue] = Field(default_factory=list)
    resume: Resume | None = None
    preview_html: str | None = None
    raw_preview_html: str | None = None
    polished_preview_html: str | None = None
    display_resume: Resume | None = None
    normalized_hometown: NonEmptyStr | None = None
    ai_polished: bool = False
    generation_strategy: Literal["deterministic", "full", "decomposed"] = "deterministic"
    polish_warning: NonEmptyStr | None = None
    semantic_keywords: list[str] = Field(default_factory=list)


class TailoredJobResult(DomainModel):
    job: Job
    match: MatchResult
    plan: TailorPlan
    tailored_resume: TailoredResume
    validation: ValidationReport
    interview_plan: InterviewPlan | None = None
    apply_url: NonEmptyStr | None = None


class JobAnalysisResult(DomainModel):
    job: Job
    jd_analysis: JDAnalysis
    evidence_matches: list[EvidenceMatch]
    match: MatchResult
    interview_plan: InterviewPlan


class CareerProductService:
    """Stable backend facade intended for a future web frontend."""

    def __init__(self, *, provider: LLMProvider, job_source: ProductJobSource) -> None:
        self._provider = provider
        self._job_source = job_source
        self._tailor_graph = build_resume_tailor_graph(provider)
        self._intake_polish_graph = build_intake_polish_graph(provider)

    def create_initial_resume(self, draft: CandidateIntakeDraft) -> InitialResumeResult:
        draft = draft.without_omitted_values()
        issues = draft.validation_issues()
        if issues:
            return InitialResumeResult(ready=False, issues=issues)
        resume = draft.build_resume()
        # Keep the deterministic inspection at the product boundary so the UI
        # cannot advance with a structurally incomplete generated resume.
        inspection = inspect_resume(resume)
        missing = unresolved_resume_fields(inspection.missing_fields, draft.omitted_fields)
        if missing:
            return InitialResumeResult(
                ready=False,
                issues=[
                    IntakeIssue(field=field, message="基础简历缺少必填内容") for field in missing
                ],
            )
        raw_preview = render_resume_html(
            resume,
            photo_asset=draft.photo_asset,
            hometown=draft.hometown,
        )
        return InitialResumeResult(
            ready=True,
            resume=resume,
            preview_html=raw_preview,
            raw_preview_html=raw_preview,
            polished_preview_html=raw_preview,
            display_resume=resume,
            normalized_hometown=draft.hometown,
        )

    async def create_ai_initial_resume(self, draft: CandidateIntakeDraft) -> InitialResumeResult:
        draft = draft.without_omitted_values()
        base = self.create_initial_resume(draft)
        if not base.ready or base.resume is None:
            return base
        workflow_result = await self._intake_polish_graph.ainvoke({"draft": draft})
        polish = workflow_result.get("polish")
        if polish is None:
            logger.warning(
                "AI intake polish workflow failed; using editable raw resume (%s)",
                ",".join(workflow_result.get("errors", [])) or "unknown",
            )
            return base.model_copy(
                update={
                    "polish_warning": (
                        "AI 整理暂时失败，已使用原始内容生成可编辑简历；"
                        "你可以继续编辑，或返回资料页稍后重新生成。"
                    )
                }
            )
        display_resume = _build_display_resume(base.resume, polish)
        if draft.is_omitted("self_summary"):
            display_resume.summary = None
        if draft.is_omitted("skills"):
            display_resume.skills = []
        if draft.is_omitted("hometown"):
            polish = polish.model_copy(update={"normalized_hometown": None})
        polished_preview = render_resume_html(
            display_resume,
            photo_asset=draft.photo_asset,
            hometown=polish.normalized_hometown or draft.hometown,
        )
        return base.model_copy(
            update={
                "preview_html": polished_preview,
                "polished_preview_html": polished_preview,
                "display_resume": display_resume,
                "normalized_hometown": polish.normalized_hometown or draft.hometown,
                "ai_polished": True,
                "generation_strategy": workflow_result.get("strategy", "full"),
                "semantic_keywords": list(
                    dict.fromkeys(
                        [
                            *workflow_result["facts"].profile_keywords,
                            *[
                                keyword
                                for item in workflow_result["facts"].experiences
                                for keyword in item.keywords
                            ],
                        ]
                    )
                )
                if workflow_result.get("facts")
                else [],
            }
        )

    async def update_candidate_intake(
        self,
        *,
        draft: CandidateIntakeDraft,
        message: str,
        conversation: list[dict[str, str]],
    ) -> IntakeConversationUpdate:
        update = await self._provider.update_candidate_intake(
            draft=draft,
            message=message,
            conversation=conversation,
        )
        merged = update.draft.model_copy(
            update={
                "candidate_id": draft.candidate_id,
                "photo_asset": draft.photo_asset,
                "omitted_fields": list(
                    dict.fromkeys(
                        [
                            *[
                                path
                                for path in draft.omitted_fields
                                if not (
                                    update.draft.field_value(path)
                                    and update.draft.field_value(path) != draft.field_value(path)
                                    and not update.draft.is_omitted(path)
                                )
                            ],
                            *update.draft.omitted_fields,
                        ]
                    )
                ),
            }
        ).without_omitted_values()
        for index, experience in enumerate(merged.experiences):
            previous = draft.experiences[index] if index < len(draft.experiences) else None
            if previous is None or previous.content != experience.content:
                fragments = [previous.source_text if previous else None, message]
                experience.source_text = "\n".join(value for value in fragments if value)
        return update.model_copy(update={"draft": merged})

    async def intake_from_resume_text(
        self, *, candidate_id: str, raw_text: str, photo_asset: str | None = None
    ) -> CandidateIntakeDraft:
        parsed = await self._provider.parse_resume(
            resume_id=f"resume-{candidate_id}",
            version="v1",
            raw_text=raw_text,
        )
        educations = [
            EducationDraft(
                school=item.school,
                degree=item.degree,
                major=item.major,
                start_date=item.start_date,
                end_date=item.end_date,
                courses=[],
            )
            for item in parsed.educations
        ]
        experiences = [
            ExperienceDraft(
                name=getattr(item, name_field),
                role=getattr(item, role_field),
                date_range=" 至 ".join(value for value in (item.start_date, item.end_date) if value)
                or None,
                content=item.description or item.source_text,
                technologies=getattr(item, "technologies", []),
                kind_hint=kind_hint,
            )
            for items, name_field, role_field, kind_hint in (
                (parsed.work_experiences, "company", "title", "work"),
                (parsed.internships, "company", "title", "internship"),
                (parsed.project_experiences, "name", "role", "project"),
                (parsed.campus_experiences, "organization", "role", "campus"),
            )
            for item in items
        ]
        return CandidateIntakeDraft(
            candidate_id=candidate_id,
            name=parsed.personal_info.name,
            email=parsed.personal_info.email,
            phone=parsed.personal_info.phone,
            current_city=parsed.personal_info.location,
            educations=educations,
            skills=[item.name for item in parsed.skills],
            experiences=experiences,
            self_summary=parsed.summary,
            photo_asset=photo_asset,
        )

    async def analyze_intake_image(self, *, data_url: str) -> IntakeImageAnalysis:
        return await self._provider.analyze_intake_image(data_url=data_url)

    async def optimize_resume_field(self, *, resume: Resume, path: str, instruction: str):
        from career_agent.resume.studio import ResumeFieldPolish

        original = field_text(resume, path)
        if not original.strip():
            raise ValueError("请先填写要优化的文字")
        if path not in {"summary", "__skills__"} and not path.endswith(".description"):
            return ResumeFieldPolish(optimized_text=original)
        result = await self._provider.optimize_resume_field(
            original=original, instruction=instruction
        )
        return validate_field_polish(original, result)

    async def design_resume_template(self, *, message: str, skill_context: str, current_theme):
        return await self._provider.design_resume_template(
            message=message, skill_context=skill_context, current_theme=current_theme
        )

    async def discover_jobs(self, query: JobSearchQuery) -> list[Job]:
        return await self._job_source.search_jobs(query)

    async def edit_resume_with_agent(
        self,
        *,
        resume: Resume,
        instruction: str,
        conversation: list[dict[str, str]],
    ) -> ResumeAgentEdit:
        edit = await self._provider.edit_resume(
            resume=resume,
            instruction=instruction,
            conversation=conversation,
        )
        updated = edit.resume.model_copy(
            update={"resume_id": resume.resume_id, "version": resume.version}
        )
        return edit.model_copy(update={"resume": confirm_user_edited_resume(updated)})

    async def tailor_for_job(
        self,
        *,
        candidate_id: str,
        resume: Resume,
        job: Job,
        allow_suggestions: bool = False,
    ) -> TailoredJobResult:
        if not job.detail_verified or job.detail_text is None:
            job = await self._job_source.get_job_detail(job.id)
        if not job.detail_verified or job.detail_text is None:
            raise ValueError("selected job has no verified JD text")
        result = await self._tailor_graph.ainvoke(
            {
                "candidate_id": candidate_id,
                "resume_id": resume.resume_id,
                "resume_version": resume.version,
                "raw_resume_text": resume.raw_text,
                "resume": resume,
                "fact_ledger": build_fact_ledger(resume, candidate_id),
                "job_id": job.id,
                "jd_text": job.detail_text,
                "retry_count": 0,
                "require_semantic_review": True,
                "allow_suggestions": allow_suggestions,
            }
        )
        return TailoredJobResult(
            job=job,
            match=result["match_result"],
            plan=result["tailor_plan"],
            tailored_resume=result["tailored_resume"],
            validation=result["validation_report"],
            interview_plan=build_interview_plan(
                job=job,
                jd_analysis=result["jd_analysis"],
                match=result["match_result"],
                evidence_matches=result["evidence_matches"],
                fact_ledger=result["fact_ledger"],
            ),
            apply_url=job.apply_url or job.source_url,
        )

    async def analyze_job(
        self, *, candidate_id: str, resume: Resume, job: Job
    ) -> JobAnalysisResult:
        """Match existing facts to a JD without rewriting the resume."""

        if not job.detail_verified or job.detail_text is None:
            job = await self._job_source.get_job_detail(job.id)
        if not job.detail_verified or job.detail_text is None:
            raise ValueError("selected job has no verified JD text")
        ledger = build_fact_ledger(resume, candidate_id)
        jd_analysis = await JDParser(self._provider).parse(
            job_id=job.id, source_text=job.detail_text
        )
        evidence = await EvidenceMatcher(self._provider).match(
            jd_analysis=jd_analysis, fact_ledger=ledger
        )
        match = calculate_match(jd_analysis, evidence)
        return JobAnalysisResult(
            job=job,
            jd_analysis=jd_analysis,
            evidence_matches=evidence,
            match=match,
            interview_plan=build_interview_plan(
                job=job,
                jd_analysis=jd_analysis,
                match=match,
                evidence_matches=evidence,
                fact_ledger=ledger,
            ),
        )


def _build_display_resume(source: Resume, polish: IntakePolish) -> Resume:
    work: list[WorkExperience] = []
    internships: list[WorkExperience] = []
    projects: list[ProjectExperience] = []
    campus: list[CampusExperience] = []
    source_entries = source.project_experiences
    for index, item in enumerate(polish.experiences, start=1):
        source_text = source_entries[item.source_index].source_text
        if item.kind in {ExperienceKind.WORK, ExperienceKind.INTERNSHIP}:
            entry = WorkExperience(
                id=f"{item.kind.value}_{index:03d}",
                source_text=source_text,
                experience_type=(
                    ExperienceType.WORK
                    if item.kind is ExperienceKind.WORK
                    else ExperienceType.INTERNSHIP
                ),
                company=item.title,
                title=item.role,
                start_date=item.start_date,
                end_date=item.end_date,
                description=item.description,
            )
            (work if item.kind is ExperienceKind.WORK else internships).append(entry)
        elif item.kind is ExperienceKind.CAMPUS:
            campus.append(
                CampusExperience(
                    id=f"campus_{index:03d}",
                    source_text=source_text,
                    organization=item.title,
                    role=item.role,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    description=item.description,
                )
            )
        else:
            projects.append(
                ProjectExperience(
                    id=f"experience_{index:03d}",
                    source_text=source_text,
                    name=item.title,
                    role=item.role,
                    project_type=item.kind.value,
                    is_course_project=item.kind is ExperienceKind.COURSE,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    description=item.description,
                    technologies=item.technologies,
                )
            )
    skill_source = next((skill.source_text for skill in source.skills), "技能")
    education_descriptions = {item.source_index: item.description for item in polish.educations}
    educations = [
        item.model_copy(
            update={
                "description": education_descriptions.get(index, item.description),
            }
        )
        for index, item in enumerate(source.educations)
    ]
    return source.model_copy(
        update={
            "summary": polish.professional_summary or source.summary,
            "educations": educations,
            "work_experiences": work,
            "internships": internships,
            "project_experiences": projects,
            "campus_experiences": campus,
            "skills": [
                Skill(name=name, source_text=skill_source) for name in polish.normalized_skills
            ]
            or source.skills,
        }
    )
