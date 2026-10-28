"""FastAPI entrypoint that exposes the existing Career Agent as a local web app."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import uuid4

from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

from career_agent.job_platform.adapters import JobPlatformAdapterError
from career_agent.job_platform.liepin_cli import LiepinCLIAdapter
from career_agent.job_platform.liepin_mcp import LiepinMCPAdapter
from career_agent.jobs.models import Job, JobSearchQuery
from career_agent.llm.base import LLMError
from career_agent.llm.openai_compatible import OpenAICompatibleProvider
from career_agent.onboarding.models import (
    CandidateIntakeDraft,
    IntakeIssue,
    unresolved_resume_fields,
)
from career_agent.product.service import (
    CareerProductService,
    InitialResumeResult,
    TailoredJobResult,
)
from career_agent.resume.editor import (
    apply_explicit_profile_edits,
    apply_explicit_section_title_edits,
    confirm_user_edited_resume,
    normalize_section_order,
    preserve_unrequested_resume_facts,
)
from career_agent.resume.exporter import (
    inspect_docx_template,
    render_resume_docx,
    render_resume_pdf,
    section_overrides_with_suggestions,
)
from career_agent.resume.inspector import inspect_resume
from career_agent.resume.models import Resume, Skill
from career_agent.resume.studio import (
    DesignedResumeTemplate,
    SavedResumeTemplate,
    design_skills,
    explicit_design_context,
    field_text,
)
from career_agent.web.workspace import (
    WorkspaceRecords,
    WorkspaceStore,
    candidate_from_record,
    intake_from_record,
)

STATIC_DIR = Path(__file__).with_name("static")
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
logger = logging.getLogger(__name__)


@dataclass
class CandidateSession:
    raw_resume: Resume
    display_resume: Resume
    raw_preview_html: str
    polished_preview_html: str
    raw_hometown: str | None = None
    polished_hometown: str | None = None
    photo_asset: str | None = None
    confirmed_resume: Resume | None = None
    confirmed: bool = False
    template_id: str = "modern"
    section_order: list[str] = field(default_factory=lambda: normalize_section_order([]))
    custom_template: bytes | None = None
    jobs: dict[str, Job] = field(default_factory=dict)
    tailored_results: dict[str, TailoredJobResult] = field(default_factory=dict)
    resume_chat: list[dict[str, str]] = field(default_factory=list)
    omitted_fields: list[str] = field(default_factory=list)
    designed_template: DesignedResumeTemplate | None = None
    designed_templates: list[SavedResumeTemplate] = field(default_factory=list)
    active_design_id: str | None = None
    template_proposal: SavedResumeTemplate | None = None
    template_chat: list[dict[str, str]] = field(default_factory=list)
    semantic_keywords: list[str] = field(default_factory=list)


@dataclass
class IntakeConversationSession:
    draft: CandidateIntakeDraft
    messages: list[dict[str, str]] = field(default_factory=list)
    phase: Literal["required", "optional", "final"] = "required"
    optional_topic_index: int = 0
    covered_optional_topics: set[str] = field(default_factory=set)
    preview_result: InitialResumeResult | None = None
    pending_clarification: str | None = None
    required_guidance_shown: bool = False
    optional_guidance_shown: bool = False


class JobSearchRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    city: str = Field(default="不限", min_length=1)
    salary_min: int | None = Field(default=None, ge=0)
    company_name: str | None = None
    experience: str | None = None


class JobActionRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    allow_suggestions: bool = False


class JobApplyRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    job_ids: list[str] = Field(min_length=1, max_length=20)
    attachment_confirmed: bool = False


class ResumeEditRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    variant: Literal["raw", "polished"] = "polished"
    resume: dict[str, Any]
    hometown: str | None = None
    section_order: list[str] = Field(default_factory=list)
    template_id: Literal["modern", "classic", "minimal", "custom", "designed"] = "modern"
    design_id: str | None = None


class ResumeConfirmRequest(ResumeEditRequest):
    pass


class ResumeTemplateUploadRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=200)
    data_url: str = Field(min_length=1)


class ResumeAgentRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=12000)
    variant: Literal["raw", "polished"] = "polished"


class ResumeFieldRequest(BaseModel):
    candidate_id: str
    variant: Literal["raw", "polished"] = "polished"
    path: str = Field(min_length=1, max_length=160)
    instruction: str = Field(default="提取关键词后重新组织，改写得更专业、简洁", max_length=2000)


class TemplateDesignRequest(BaseModel):
    candidate_id: str
    message: str = Field(min_length=1, max_length=3000)
    skill_ids: list[str] = Field(default_factory=list, max_length=5)


class TemplateSelectionRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)


class IntakeAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    data_url: str = Field(min_length=1)


class IntakeChatRequest(BaseModel):
    candidate_id: str = Field(min_length=1)
    message: str = Field(default="", max_length=6000)
    attachments: list[IntakeAttachment] = Field(default_factory=list, max_length=5)
    generate: bool = False


_INTAKE_TRIGGER_MESSAGES = {
    "帮我从零生成简历",
    "帮我生成我的简历",
    "帮我修改我的简历",
    "请帮我生成简历",
    "我没有简历，请帮我生成",
    "请帮我修改简历",
    "我有简历，请帮我修改",
    "先告诉我生成简历需要提供哪些信息",
}

_OPTIONAL_INTAKE_TOPICS = (
    ("location", "可以补充现居城市、籍贯和期望工作城市。"),
    ("education_extras", "有没有相关课程、成绩、奖学金、校内荣誉？"),
    (
        "work",
        "有没有实习或工作经历？可以说公司、身份、时间、做过的事情和真实结果。",
    ),
    (
        "projects",
        "有没有项目、科研、竞赛或校园经历？可以说名称、角色、时间、做过的事情和使用的技术。",
    ),
    ("credentials", "有没有证书、语言能力、奖项，或想补充技能熟练程度？"),
    ("target", "有没有个人总结、求职方向或意向 JD？"),
    ("photo", "需要照片版简历的话，可以拖入、粘贴或选择一张照片。"),
)

_SKIP_OPTIONAL_MESSAGES = {"没有", "无", "跳过", "暂时没有", "不需要", "没有这项"}
_SKIP_ALL_OPTIONAL_MESSAGES = {"都没有", "全部跳过", "跳过全部", "直接生成", "没有其他了", "没有了"}


def _decode_attachment(attachment: IntakeAttachment) -> tuple[str | None, str | None]:
    try:
        header, encoded = attachment.data_url.split(",", 1)
        if ";base64" not in header:
            raise ValueError("not base64")
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="上传文件编码无效") from exc
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="单个文件不能超过 10MB")
    suffix = Path(attachment.filename).suffix.casefold()
    try:
        if suffix == ".docx":
            text = "\n".join(
                paragraph.text.strip()
                for paragraph in Document(BytesIO(content)).paragraphs
                if paragraph.text.strip()
            )
            return text[:60000], None
        if suffix == ".pdf":
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages
            )
            return text.strip()[:60000], None
        if suffix in {".txt", ".md"}:
            return content.decode("utf-8", errors="replace").strip()[:60000], None
        if suffix in {".png", ".jpg", ".jpeg", ".webp"} and header.startswith("data:image/"):
            return None, attachment.data_url
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法读取文件：{attachment.filename}") from exc
    raise HTTPException(status_code=400, detail="支持 Word、PDF、TXT、Markdown 和常见图片格式")


def _required_intake_issues(draft: CandidateIntakeDraft) -> list[IntakeIssue]:
    issues = draft.validation_issues()
    for index, education in enumerate(draft.all_educations()):
        prefix = f"educations.{index}" if draft.educations else "education"
        for name, label in (("start_date", "入学时间"), ("end_date", "毕业时间或预计毕业时间")):
            path = f"{prefix}.{name}"
            if not getattr(education, name) and not draft.is_omitted(path):
                issues.append(IntakeIssue(field=path, message=f"请提供{label}"))
    return issues


def _required_intake_messages(draft: CandidateIntakeDraft) -> list[str]:
    return list(dict.fromkeys(issue.message for issue in _required_intake_issues(draft)))


def _explicitly_omitted_fields(message: str, previous: CandidateIntakeDraft) -> list[str]:
    """Resolve short refusals against the actual question, independent of LLM prose."""
    refusal = r"不(?:想|愿意|方便)?(?:再)?(?:提供|填写|透露|公开|填)|保密|跳过|别问|不要问"
    clauses = [part for part in re.split(r"[，。；,;！!\n]", message) if re.search(refusal, part)]
    if not clauses or re.search(r"(?:可以|能不能|是否|可不可以).*(?:吗|么|[？?])$", message):
        return []
    issues = _required_intake_issues(previous)
    if message in _SKIP_ALL_OPTIONAL_MESSAGES:
        return [issue.field for issue in issues]
    labels = {
        "name": ("姓名", "名字"),
        "email": ("邮箱", "邮件", "email"),
        "phone": ("手机", "电话", "phone"),
        "education.start_date": ("入学", "开始时间"),
        "education.end_date": ("毕业", "结束时间"),
        "education.school": ("学校", "校名"),
        "education.major": ("专业",),
        "education.degree": ("学历", "学位"),
        "education": ("教育经历", "教育背景"),
        "skills": ("技能",),
    }
    explicit = [
        path
        for path, names in labels.items()
        if any(name in clause.casefold() for name in names for clause in clauses)
    ]
    if explicit:
        return explicit
    contact = [issue.field for issue in issues if issue.field in {"name", "email", "phone"}]
    education = [issue.field for issue in issues if issue.field.startswith("education")]
    skills = [issue.field for issue in issues if issue.field == "skills"]
    return contact or education or skills


def _required_intake_question(missing: list[str], *, include_guidance: bool = True) -> str:
    contact = [item for item in missing if any(word in item for word in ("姓名", "邮箱", "手机号"))]
    education = [
        item
        for item in missing
        if any(word in item for word in ("学校", "专业", "学历", "入学", "毕业"))
    ]
    skills = [item for item in missing if "技能" in item]
    current = contact or education or skills or missing
    if include_guidance:
        return (
            "为了生成可用的简历，还需要："
            + "、".join(current)
            + "。你可以直接用一句话回答；不想提供的项目也可以直接告诉我跳过。"
        )
    return "、".join(current) + "。"


def _next_intake_message(intake: IntakeConversationSession) -> tuple[str, list[str], bool]:
    missing = _required_intake_messages(intake.draft)
    if missing:
        intake.phase = "required"
        question = _required_intake_question(
            missing, include_guidance=not intake.required_guidance_shown
        )
        intake.required_guidance_shown = True
        return question, missing, False
    if intake.pending_clarification:
        return intake.pending_clarification, [], False
    if intake.phase == "required":
        intake.phase = "optional"
        intake.optional_topic_index = 0
    if intake.phase == "optional":
        experience_kinds = {
            item.kind_hint for item in intake.draft.all_experiences() if item.kind_hint
        }
        inferred_topics = {
            topic
            for topic, present in (
                ("location", bool(intake.draft.current_city or intake.draft.hometown)),
                (
                    "education_extras",
                    any(item.courses for item in intake.draft.all_educations()),
                ),
                ("work", bool(experience_kinds & {"work", "internship"})),
                (
                    "projects",
                    bool(
                        experience_kinds
                        & {"campus", "competition", "research", "course", "project"}
                    ),
                ),
                ("target", bool(intake.draft.self_summary or intake.draft.intended_jd)),
                ("photo", bool(intake.draft.photo_asset)),
            )
            if present
        }
        intake.covered_optional_topics.update(inferred_topics)
        while (
            intake.optional_topic_index < len(_OPTIONAL_INTAKE_TOPICS)
            and _OPTIONAL_INTAKE_TOPICS[intake.optional_topic_index][0]
            in intake.covered_optional_topics
        ):
            intake.optional_topic_index += 1
        if intake.optional_topic_index < len(_OPTIONAL_INTAKE_TOPICS):
            number = intake.optional_topic_index + 1
            question = _OPTIONAL_INTAKE_TOPICS[intake.optional_topic_index][1]
            if not intake.optional_guidance_shown:
                question = (
                    f"基础信息已经整理好。接下来补充可选信息（{number}/{len(_OPTIONAL_INTAKE_TOPICS)}）："
                    + question
                    + "没有的项目回复“跳过”，也可以回复“全部跳过”。"
                )
                intake.optional_guidance_shown = True
            return (
                question,
                [],
                False,
            )
        intake.phase = "final"
    return (
        "资料已经整理完成。还有什么需要补充或更正的吗？如果没有，请点击右下角“确认生成”。",
        [],
        True,
    )


def _merge_intake_drafts(
    current: CandidateIntakeDraft, incoming: CandidateIntakeDraft
) -> CandidateIntakeDraft:
    scalar_fields = (
        "name",
        "email",
        "phone",
        "current_city",
        "hometown",
        "self_summary",
        "intended_jd",
    )
    updates: dict[str, object] = {
        field_name: getattr(incoming, field_name) or getattr(current, field_name)
        for field_name in scalar_fields
    }
    updates.update(
        {
            "candidate_id": current.candidate_id,
            "educations": incoming.educations or current.educations,
            "education": (
                incoming.education
                if any(
                    getattr(incoming.education, name)
                    for name in ("school", "major", "degree", "start_date", "end_date")
                )
                else current.education
            ),
            "skills": incoming.skills or current.skills,
            "experiences": incoming.experiences or current.experiences,
            "projects": incoming.projects or current.projects,
            "photo_asset": incoming.photo_asset or current.photo_asset,
        }
    )
    return current.model_copy(update=updates)


def create_app(*, state_file: Path | None = None) -> FastAPI:
    load_dotenv(ENV_FILE, override=False)
    application = FastAPI(title="Career Agent", version="0.1.0")

    @application.middleware("http")
    async def prevent_stale_local_content(request: Any, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        if store and request.method in {"POST", "DELETE"} and response.status_code < 400:
            async with save_lock:
                data = store.snapshot(sessions, intake_sessions)
                await asyncio.to_thread(store.write, data)
        return response

    sessions: dict[str, CandidateSession] = {}
    intake_sessions: dict[str, IntakeConversationSession] = {}
    store = WorkspaceStore(state_file) if state_file else None
    save_lock = asyncio.Lock()
    if store:
        saved = store.load()
        sessions.update(
            {
                key: candidate_from_record(value, CandidateSession)
                for key, value in saved.candidates.items()
            }
        )
        intake_sessions.update(
            {
                key: intake_from_record(value, IntakeConversationSession)
                for key, value in saved.intakes.items()
            }
        )
    service: CareerProductService | None = None
    source: LiepinMCPAdapter | None = None
    applicator: LiepinCLIAdapter | None = None

    def get_dependencies() -> tuple[CareerProductService, LiepinMCPAdapter]:
        nonlocal service, source
        if service is None or source is None:
            try:
                provider = OpenAICompatibleProvider.from_env()
                source = LiepinMCPAdapter.from_env()
            except ValueError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            service = CareerProductService(provider=provider, job_source=source)
        return service, source

    def get_session(candidate_id: str) -> CandidateSession:
        try:
            candidate = sessions[candidate_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="请先完成候选人资料并生成初版简历") from exc
        if candidate.designed_template and not candidate.designed_templates:
            legacy = SavedResumeTemplate(
                id="legacy-custom", **candidate.designed_template.model_dump()
            )
            candidate.designed_templates.append(legacy)
            candidate.active_design_id = legacy.id
        return candidate

    def select_design(candidate: CandidateSession, template_id: str) -> None:
        template = next(
            (item for item in candidate.designed_templates if item.id == template_id), None
        )
        if template is None:
            raise HTTPException(status_code=404, detail="没有找到这个自定义模板")
        candidate.designed_template = DesignedResumeTemplate(**template.model_dump(exclude={"id"}))
        candidate.active_design_id = template.id
        candidate.template_id = "designed"
        candidate.confirmed = False
        candidate.confirmed_resume = None

    def design_library(candidate: CandidateSession) -> dict[str, object]:
        return {
            "templates": candidate.designed_templates,
            "template": candidate.designed_template,
            "template_id": candidate.template_id,
            "active_design_id": candidate.active_design_id,
            "proposal": candidate.template_proposal,
        }

    def get_applicator() -> LiepinCLIAdapter:
        nonlocal applicator
        if applicator is None:
            applicator = LiepinCLIAdapter(Path("vendor/liepin-cil"))
        return applicator

    def store_generated_resume(draft: CandidateIntakeDraft, result: Any) -> None:
        if not (
            result.ready
            and result.resume
            and result.display_resume
            and result.raw_preview_html
            and result.polished_preview_html
        ):
            return
        previous = sessions.get(draft.candidate_id)
        generated = CandidateSession(
            raw_resume=result.resume,
            display_resume=result.display_resume,
            raw_preview_html=result.raw_preview_html,
            polished_preview_html=result.polished_preview_html,
            raw_hometown=draft.hometown,
            polished_hometown=result.normalized_hometown,
            photo_asset=draft.photo_asset,
            omitted_fields=list(draft.omitted_fields),
            semantic_keywords=result.semantic_keywords,
        )
        if previous:
            for name in (
                "template_id",
                "section_order",
                "custom_template",
                "designed_template",
                "designed_templates",
                "active_design_id",
                "template_proposal",
                "template_chat",
                "jobs",
                "resume_chat",
            ):
                setattr(generated, name, getattr(previous, name))
        sessions[draft.candidate_id] = generated

    def apply_editor_update(
        candidate: CandidateSession,
        request: ResumeEditRequest,
    ) -> Resume:
        if request.template_id == "custom" and candidate.custom_template is None:
            raise HTTPException(status_code=400, detail="请先上传 Word 模板")
        if request.template_id == "designed" and request.design_id:
            select_design(candidate, request.design_id)
        if request.template_id == "designed" and candidate.designed_template is None:
            raise HTTPException(status_code=400, detail="请先生成自定义模板")
        edited = confirm_user_edited_resume(Resume.model_validate(request.resume, strict=False))
        hometown = request.hometown or edited.personal_info.hometown
        edited = edited.model_copy(
            update={"personal_info": edited.personal_info.model_copy(update={"hometown": hometown})}
        )
        if request.variant == "raw":
            candidate.raw_resume = edited
            candidate.raw_hometown = hometown
        else:
            candidate.display_resume = edited
            candidate.polished_hometown = hometown
        candidate.template_id = request.template_id
        candidate.section_order = normalize_section_order(request.section_order)
        candidate.confirmed = False
        candidate.confirmed_resume = None
        return edited

    @application.get("/", include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        markup = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        if request.headers.get("x-forwarded-prefix") == "/CareerAgent":
            markup = markup.replace("<head>", '<head>\n  <base href="/CareerAgent/">', 1)
        for filename in ("styles.css", "app.js", "intake-interactions.js", "resume-studio.js"):
            digest = hashlib.sha256((STATIC_DIR / filename).read_bytes()).hexdigest()[:12]
            markup = markup.replace(f'"static/{filename}"', f'"static/{filename}?v={digest}"')
        return HTMLResponse(markup)

    @application.get("/api/status")
    async def status() -> dict[str, object]:
        return {
            "ready": bool(
                os.getenv("CAREER_AGENT_LLM_API_KEY")
                and os.getenv("CAREER_AGENT_LLM_MODEL")
                and os.getenv("LIEPIN_MCP_USER_TOKEN")
            ),
            "model": os.getenv("CAREER_AGENT_LLM_MODEL") or "未配置",
            "liepin": bool(os.getenv("LIEPIN_MCP_USER_TOKEN")),
        }

    @application.post("/api/intake")
    async def create_resume(draft: CandidateIntakeDraft) -> dict[str, object]:
        product_service, _ = get_dependencies()
        try:
            result = await product_service.create_ai_initial_resume(draft)
        except (LLMError, ValueError) as exc:
            # This is a second safety boundary. Initial-resume generation must remain
            # usable when an OpenAI-compatible provider rejects structured output and
            # its plain-JSON fallback also has a transient failure.
            logger.warning(
                "AI intake request escaped service fallback; using raw resume (%s)",
                type(exc).__name__,
            )
            result = product_service.create_initial_resume(draft).model_copy(
                update={
                    "polish_warning": (
                        "模型暂时无法完成 AI 整理，已根据原始资料生成可编辑简历。"
                        "你可以继续修改和确认，不需要重新填写。"
                    )
                }
            )
        store_generated_resume(draft, result)
        return result.model_dump(mode="json")

    @application.post("/api/intake/chat")
    async def conversational_intake(request: IntakeChatRequest) -> dict[str, object]:
        product_service, _ = get_dependencies()
        intake = intake_sessions.setdefault(
            request.candidate_id,
            IntakeConversationSession(
                draft=CandidateIntakeDraft(candidate_id=request.candidate_id)
            ),
        )
        acknowledgements: list[str] = []
        resume_texts: list[str] = []
        image_uploads: list[tuple[str, str]] = []
        recognized_photo_filename: str | None = None
        for attachment in request.attachments:
            text, image = _decode_attachment(attachment)
            if text:
                resume_texts.append(text)
                acknowledgements.append(f"已读取 {attachment.filename}")
            elif image:
                image_uploads.append((attachment.filename, image))

        try:
            message = request.message.strip()
            phase_before = intake.phase
            refused_fields = _explicitly_omitted_fields(message, intake.draft)
            for filename, image in image_uploads:
                image_analysis = await product_service.analyze_intake_image(data_url=image)
                if image_analysis.kind == "portrait":
                    intake.draft = intake.draft.model_copy(update={"photo_asset": image})
                    intake.covered_optional_topics.add("photo")
                    recognized_photo_filename = filename
                    acknowledgements.append(f"已自动识别并保存 {filename} 作为简历照片")
                elif image_analysis.kind == "resume_document" and image_analysis.text.strip():
                    resume_texts.append(image_analysis.text)
                    acknowledgements.append(f"已识别图片简历 {filename}")
                else:
                    acknowledgements.append(f"已查看 {filename}，但它不是可用的个人照片或简历材料")
            if resume_texts:
                combined_text = "\n\n".join(resume_texts)
                if not combined_text.strip():
                    raise HTTPException(status_code=400, detail="文件中没有可提取的文字")
                imported = await product_service.intake_from_resume_text(
                    candidate_id=request.candidate_id,
                    raw_text=combined_text,
                    photo_asset=intake.draft.photo_asset,
                )
                intake.draft = _merge_intake_drafts(intake.draft, imported)

            skip_current = message in _SKIP_OPTIONAL_MESSAGES
            skip_all = message in _SKIP_ALL_OPTIONAL_MESSAGES
            should_extract_message = (
                bool(message)
                and message not in _INTAKE_TRIGGER_MESSAGES
                and not request.generate
                and not (phase_before == "optional" and (skip_current or skip_all))
                and not (phase_before == "final" and (skip_current or skip_all))
            )
            if should_extract_message:
                update = await product_service.update_candidate_intake(
                    draft=intake.draft,
                    message=message,
                    conversation=intake.messages,
                )
                intake.draft = update.draft
                intake.covered_optional_topics.update(update.covered_optional_topics)
                intake.pending_clarification = update.clarification_question
                acknowledgements.append(update.acknowledgement)

            if refused_fields:
                intake.draft = intake.draft.model_copy(
                    update={
                        "omitted_fields": list(
                            dict.fromkeys(
                                [
                                    *intake.draft.omitted_fields,
                                    *refused_fields,
                                ]
                            )
                        ),
                    }
                ).without_omitted_values()

            has_turn_content = bool(message or request.attachments)
            if (
                phase_before == "optional"
                and has_turn_content
                and not request.generate
                and not intake.pending_clarification
            ):
                if intake.optional_topic_index < len(_OPTIONAL_INTAKE_TOPICS):
                    intake.covered_optional_topics.add(
                        _OPTIONAL_INTAKE_TOPICS[intake.optional_topic_index][0]
                    )
                if skip_all:
                    intake.phase = "final"
                else:
                    intake.optional_topic_index += 1
                    if intake.optional_topic_index >= len(_OPTIONAL_INTAKE_TOPICS):
                        intake.phase = "final"
        except HTTPException:
            raise
        except (LLMError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        next_message, missing, ready_to_generate = _next_intake_message(intake)
        assistant_message = " ".join([*acknowledgements, next_message]).strip()
        if request.message.strip() or request.attachments:
            intake.messages.append(
                {
                    "role": "user",
                    "content": request.message.strip()
                    or "上传了文件：" + "、".join(item.filename for item in request.attachments),
                }
            )
        intake.messages.append({"role": "assistant", "content": assistant_message})
        intake.messages = intake.messages[-20:]

        if ready_to_generate:
            result = intake.preview_result
            if result is None or not request.generate:
                result = await product_service.create_ai_initial_resume(intake.draft)
                intake.preview_result = result if result.ai_polished else None
            preview_ready = bool(result.ready and result.ai_polished)
            if preview_ready:
                store_generated_resume(intake.draft, result)
            payload = result.model_dump(mode="json")
            payload.update(
                {
                    "generated": bool(request.generate and preview_ready),
                    "preview_generated": preview_ready,
                    "ready_to_generate": preview_ready,
                    "assistant_message": (
                        "预览简历已按你的事实完成专业整理。你可以继续在这里补充或修改；"
                        "可以直接编辑文字或拖动模块，右上角可打开精修编辑。"
                        if preview_ready and not request.generate
                        else (
                            "初版简历已经生成。可以在对话中继续修改，确认后再发现岗位。"
                            if preview_ready
                            else (
                                "资料已经收齐，但 AI 专业改写暂时没有成功。"
                                "原始口语内容不会直接作为简历；请回复“重新整理”再试一次。"
                            )
                        )
                    ),
                    "draft": intake.draft.model_dump(mode="json", exclude={"photo_asset"}),
                    "has_photo": bool(intake.draft.photo_asset),
                    "recognized_photo_filename": recognized_photo_filename,
                }
            )
            return payload

        return {
            "generated": False,
            "assistant_message": assistant_message,
            "ready_to_generate": ready_to_generate,
            "missing_required": missing,
            "draft": intake.draft.model_dump(mode="json", exclude={"photo_asset"}),
            "has_photo": bool(intake.draft.photo_asset),
            "recognized_photo_filename": recognized_photo_filename,
        }

    @application.post("/api/jobs/search")
    async def search_jobs(request: JobSearchRequest) -> dict[str, object]:
        product_service, _ = get_dependencies()
        candidate = get_session(request.candidate_id)
        if not candidate.confirmed or candidate.confirmed_resume is None:
            raise HTTPException(status_code=409, detail="请先在初版简历页确认简历内容")
        try:
            jobs = await product_service.discover_jobs(
                JobSearchQuery(
                    keyword=request.keyword,
                    city=request.city,
                    salary_min=request.salary_min,
                    company_names=[request.company_name] if request.company_name else [],
                    experience_levels=[request.experience] if request.experience else [],
                )
            )
        except JobPlatformAdapterError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        candidate.jobs = {job.id: job for job in jobs}
        return {"jobs": [job.model_dump(mode="json") for job in jobs]}

    @application.post("/api/jobs/detail")
    async def job_detail(request: JobActionRequest) -> dict[str, object]:
        _, job_source = get_dependencies()
        candidate = get_session(request.candidate_id)
        if request.job_id not in candidate.jobs:
            raise HTTPException(status_code=404, detail="岗位不在当前搜索结果中")
        try:
            job = await job_source.get_job_detail(request.job_id)
        except JobPlatformAdapterError as exc:
            return {
                "job": candidate.jobs[request.job_id].model_dump(mode="json"),
                "detail_warning": str(exc),
            }
        candidate.jobs[job.id] = job
        return {"job": job.model_dump(mode="json")}

    @application.post("/api/jobs/tailor")
    async def tailor_job(request: JobActionRequest) -> dict[str, object]:
        product_service, _ = get_dependencies()
        candidate = get_session(request.candidate_id)
        try:
            job = candidate.jobs[request.job_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="岗位不在当前搜索结果中") from exc
        try:
            result = await product_service.tailor_for_job(
                candidate_id=request.candidate_id,
                resume=candidate.confirmed_resume or candidate.display_resume,
                job=job,
                allow_suggestions=request.allow_suggestions,
            )
        except (JobPlatformAdapterError, LLMError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        candidate.jobs[result.job.id] = result.job
        candidate.tailored_results[result.job.id] = result
        return result.model_dump(mode="json")

    @application.post("/api/jobs/analyze")
    async def analyze_job(request: JobActionRequest) -> dict[str, object]:
        product_service, _ = get_dependencies()
        candidate = get_session(request.candidate_id)
        job = candidate.jobs.get(request.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="岗位不在当前搜索结果中")
        try:
            result = await product_service.analyze_job(
                candidate_id=request.candidate_id,
                resume=candidate.confirmed_resume or candidate.display_resume,
                job=job,
            )
        except (JobPlatformAdapterError, LLMError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        candidate.jobs[result.job.id] = result.job
        return result.model_dump(mode="json")

    @application.post("/api/jobs/apply")
    async def apply_jobs(request: JobApplyRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        if not candidate.confirmed:
            raise HTTPException(status_code=409, detail="请先确认初版简历")
        if not request.attachment_confirmed:
            raise HTTPException(
                status_code=409,
                detail="请先在猎聘上传附件、设为默认投递简历，并在本页确认完成",
            )
        cli = get_applicator()
        results: list[dict[str, object]] = []
        for job_id in dict.fromkeys(request.job_ids):
            job = candidate.jobs.get(job_id)
            if job is None:
                results.append(
                    {"job_id": job_id, "applied": False, "message": "岗位不在当前搜索结果中"}
                )
                continue
            try:
                response = await cli.apply_job(job)
                results.append({"job_id": job_id, "applied": True, "response": response})
            except JobPlatformAdapterError as exc:
                results.append({"job_id": job_id, "applied": False, "message": str(exc)})
        return {
            "results": results,
            "applied_count": sum(bool(item["applied"]) for item in results),
            "attachment_confirmation": "user_confirmed_default_resume",
        }

    @application.post("/api/resume/edit")
    async def edit_resume(request: ResumeEditRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        edited = apply_editor_update(candidate, request)
        return {
            "saved": True,
            "resume": edited.model_dump(mode="json"),
            "section_order": candidate.section_order,
            "template_id": candidate.template_id,
        }

    @application.post("/api/resume/agent")
    async def edit_resume_with_agent(request: ResumeAgentRequest) -> dict[str, object]:
        product_service, _ = get_dependencies()
        candidate = get_session(request.candidate_id)
        resume = candidate.raw_resume if request.variant == "raw" else candidate.display_resume
        try:
            result = await product_service.edit_resume_with_agent(
                resume=resume,
                instruction=request.message,
                conversation=candidate.resume_chat,
            )
        except (LLMError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        edited = preserve_unrequested_resume_facts(resume, result.resume, request.message)
        edited, explicit_hometown = apply_explicit_profile_edits(edited, request.message)
        edited = edited.model_copy(
            update={"section_titles": {**resume.section_titles, **edited.section_titles}}
        )
        edited = apply_explicit_section_title_edits(edited, request.message)
        hometown = (
            explicit_hometown
            or result.hometown
            or edited.personal_info.hometown
            or (candidate.raw_hometown if request.variant == "raw" else candidate.polished_hometown)
        )
        edited = confirm_user_edited_resume(
            edited.model_copy(
                update={
                    "personal_info": edited.personal_info.model_copy(update={"hometown": hometown})
                }
            )
        )

        def visible_entries(items: list[Any]) -> list[dict[str, Any]]:
            return [item.model_dump(exclude={"id", "source_text"}, mode="json") for item in items]

        changes = []
        for label, before, after in (
            ("栏目标题", resume.section_titles, edited.section_titles),
            ("姓名", resume.personal_info.name, edited.personal_info.name),
            ("邮箱", resume.personal_info.email, edited.personal_info.email),
            ("手机号", resume.personal_info.phone, edited.personal_info.phone),
            ("个人网站与链接", resume.personal_info.links, edited.personal_info.links),
            ("所在地", resume.personal_info.location, edited.personal_info.location),
            (
                "籍贯",
                resume.personal_info.hometown
                or (
                    candidate.raw_hometown
                    if request.variant == "raw"
                    else candidate.polished_hometown
                ),
                hometown,
            ),
            ("教育经历", visible_entries(resume.educations), visible_entries(edited.educations)),
            (
                "经历",
                (
                    visible_entries(resume.work_experiences),
                    visible_entries(resume.internships),
                    visible_entries(resume.project_experiences),
                    visible_entries(resume.campus_experiences),
                ),
                (
                    visible_entries(edited.work_experiences),
                    visible_entries(edited.internships),
                    visible_entries(edited.project_experiences),
                    visible_entries(edited.campus_experiences),
                ),
            ),
            ("技能", visible_entries(resume.skills), visible_entries(edited.skills)),
            ("个人总结", resume.summary, edited.summary),
        ):
            if before != after:
                changes.append(label)
        assistant_message = (
            "已更新到简历预览：" + "、".join(changes) + "。请查看上方简历。"
            if changes
            else "这次没有检测到简历内容的实际变化，请指出要修改的具体内容。"
        )
        if request.variant == "raw":
            candidate.raw_resume = edited
            candidate.raw_hometown = hometown
        else:
            candidate.display_resume = edited
            candidate.polished_hometown = hometown
        candidate.confirmed = False
        candidate.confirmed_resume = None
        candidate.resume_chat.extend(
            (
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": assistant_message},
            )
        )
        candidate.resume_chat = candidate.resume_chat[-20:]
        intake = intake_sessions.get(request.candidate_id)
        if intake:
            intake.messages.extend(candidate.resume_chat[-2:])
            intake.messages = intake.messages[-20:]
        return {
            "assistant_message": assistant_message,
            "resume": edited.model_dump(mode="json"),
            "hometown": hometown,
            "changed_sections": changes,
        }

    @application.get("/api/resume/current")
    async def current_resume(candidate_id: str) -> dict[str, object]:
        candidate = get_session(candidate_id)
        custom_theme = (
            inspect_docx_template(candidate.custom_template)
            if candidate.custom_template is not None
            else None
        )
        return {
            "raw_resume": candidate.raw_resume.model_dump(mode="json"),
            "display_resume": candidate.display_resume.model_dump(mode="json"),
            "raw_hometown": candidate.raw_hometown,
            "polished_hometown": candidate.polished_hometown,
            "section_order": candidate.section_order,
            "template_id": candidate.template_id,
            "custom_theme": custom_theme,
            "confirmed": candidate.confirmed,
            "resume_chat": candidate.resume_chat,
            "photo_asset": candidate.photo_asset,
            "designed_template": candidate.designed_template,
            "designed_templates": candidate.designed_templates,
            "active_design_id": candidate.active_design_id,
            "template_proposal": candidate.template_proposal,
            "template_chat": candidate.template_chat,
            "semantic_keywords": candidate.semantic_keywords,
            "intake_chat": intake_sessions[candidate_id].messages
            if candidate_id in intake_sessions
            else [],
            "intake_draft": intake_sessions[candidate_id].draft
            if candidate_id in intake_sessions
            else None,
        }

    @application.post("/api/resume/confirm")
    async def confirm_resume(request: ResumeConfirmRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        edited = apply_editor_update(candidate, request)
        inspection = inspect_resume(edited)
        missing = unresolved_resume_fields(inspection.missing_fields, candidate.omitted_fields)
        if missing:
            raise HTTPException(
                status_code=422,
                detail="确认前请补全：" + "、".join(missing),
            )
        candidate.confirmed_resume = edited
        candidate.confirmed = True
        return {"confirmed": True, "resume_version": edited.version}

    @application.post("/api/resume/template")
    async def upload_resume_template(
        request: ResumeTemplateUploadRequest,
    ) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        if not request.filename.casefold().endswith(".docx"):
            raise HTTPException(status_code=400, detail="目前支持上传 .docx Word 模板")
        try:
            header, encoded = request.data_url.split(",", 1)
            if ";base64" not in header:
                raise ValueError("template is not base64 encoded")
            content = base64.b64decode(encoded, validate=True)
            if len(content) > 5 * 1024 * 1024:
                raise ValueError("template is larger than 5 MB")
            theme = inspect_docx_template(content)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Word 模板无法读取或超过 5MB") from exc
        candidate.custom_template = content
        candidate.template_id = "custom"
        return {"uploaded": True, "filename": request.filename, "theme": theme}

    @application.post("/api/workspace/restore")
    async def restore_workspace(payload: dict[str, Any]) -> dict[str, object]:
        try:
            records = WorkspaceRecords.model_validate_json(json.dumps(payload))
            if len(records.candidates) + len(records.intakes) > 10:
                raise ValueError("too many workspace records")
            restored = []
            for key, record in records.candidates.items():
                if key not in sessions:
                    sessions[key] = candidate_from_record(record, CandidateSession)
                    restored.append(key)
            for key, record in records.intakes.items():
                if key not in intake_sessions:
                    intake_sessions[key] = intake_from_record(record, IntakeConversationSession)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="会话备份格式无效") from exc
        return {"restored": restored}

    @application.post("/api/resume/optimize-field")
    async def optimize_field(request: ResumeFieldRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        service, _ = get_dependencies()
        original = candidate.raw_resume if request.variant == "raw" else candidate.display_resume
        try:
            before = field_text(original, request.path)
            result = await service.optimize_resume_field(
                resume=original, path=request.path, instruction=request.instruction
            )
            latest = candidate.raw_resume if request.variant == "raw" else candidate.display_resume
            if field_text(latest, request.path) != before:
                raise HTTPException(
                    status_code=409, detail="这段文字已被修改，请基于最新内容重新优化"
                )
            edited = latest.model_copy(deep=True)
            if request.path == "__skills__":
                names = [
                    name.strip()
                    for name in re.split(r"[、，,;；\n]+", result.optimized_text)
                    if name.strip()
                ]
                edited.skills = [
                    Skill(name=name, source_text="技能：" + "、".join(names)) for name in names
                ]
            else:
                parts = request.path.split(".")
                target: Any = edited
                for part in parts[:-1]:
                    target = (
                        target[int(part)] if isinstance(target, list) else getattr(target, part)
                    )
                setattr(target, parts[-1], result.optimized_text)
        except (LLMError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if request.variant == "raw":
            candidate.raw_resume = edited
        else:
            candidate.display_resume = edited
        candidate.confirmed = False
        candidate.confirmed_resume = None
        return {
            "resume": edited.model_dump(mode="json"),
            "keywords": result.keywords,
            "path": request.path,
            "optimized_text": result.optimized_text,
        }

    @application.get("/api/design/skills")
    async def list_design_skills() -> dict[str, object]:
        return {"skills": design_skills(), "explicit_only": True}

    @application.post("/api/resume/template/design")
    async def design_template(request: TemplateDesignRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        try:
            context = explicit_design_context(request.skill_ids)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        service, _ = get_dependencies()
        try:
            design = await service.design_resume_template(
                message=request.message,
                skill_context=context,
                current_theme=(
                    (candidate.template_proposal or candidate.designed_template).theme.model_dump()
                    if candidate.template_proposal or candidate.designed_template
                    else None
                ),
            )
        except (LLMError, ValueError) as exc:
            raise HTTPException(status_code=502, detail="模板设计暂未完成，请重试") from exc
        design = design.model_copy(update={"used_skills": list(dict.fromkeys(request.skill_ids))})
        candidate.template_proposal = SavedResumeTemplate(id=uuid4().hex, **design.model_dump())
        candidate.template_chat.extend(
            [
                {"role": "user", "content": request.message},
                {"role": "assistant", "content": design.description},
            ]
        )
        candidate.template_chat = candidate.template_chat[-20:]
        return {"proposal": candidate.template_proposal, "messages": candidate.template_chat}

    @application.post("/api/resume/template/confirm")
    async def confirm_design_template(request: TemplateSelectionRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        saved = next(
            (item for item in candidate.designed_templates if item.id == request.template_id), None
        )
        if saved is None:
            proposal = candidate.template_proposal
            if proposal is None or proposal.id != request.template_id:
                raise HTTPException(status_code=409, detail="请先设计方案，再确认生成模板")
            candidate.designed_templates.append(proposal.model_copy(deep=True))
            candidate.template_proposal = None
            candidate.template_chat.append({"role": "user", "content": "确认生成这个模板"})
            candidate.template_chat.append(
                {"role": "assistant", "content": f"已生成「{proposal.name}」，可在模板栏反复选用。"}
            )
            candidate.template_chat = candidate.template_chat[-20:]
        select_design(candidate, request.template_id)
        return {**design_library(candidate), "messages": candidate.template_chat}

    @application.post("/api/resume/template/select")
    async def select_design_template(request: TemplateSelectionRequest) -> dict[str, object]:
        candidate = get_session(request.candidate_id)
        select_design(candidate, request.template_id)
        return design_library(candidate)

    @application.delete("/api/resume/template/design")
    async def delete_design_template(
        candidate_id: str, template_id: str | None = None
    ) -> dict[str, object]:
        candidate = get_session(candidate_id)
        removed_id = template_id or candidate.active_design_id
        if not any(item.id == removed_id for item in candidate.designed_templates):
            raise HTTPException(status_code=404, detail="没有找到这个自定义模板")
        candidate.designed_templates = [
            item for item in candidate.designed_templates if item.id != removed_id
        ]
        if candidate.active_design_id == removed_id:
            if candidate.designed_templates:
                select_design(candidate, candidate.designed_templates[-1].id)
            else:
                candidate.designed_template = None
                candidate.active_design_id = None
                if candidate.template_id == "designed":
                    candidate.template_id = "modern"
        return {"deleted": True, **design_library(candidate)}

    @application.get("/api/resume/download/{variant}/{file_format}")
    async def download_resume(
        variant: str,
        file_format: str,
        candidate_id: str,
        job_id: str | None = None,
        suggestions: str | None = None,
    ) -> Response:
        candidate = get_session(candidate_id)
        if variant not in {"raw", "polished", "tailored"}:
            raise HTTPException(status_code=400, detail="不支持的简历版本")
        tailored = None
        if variant == "tailored":
            if not job_id or job_id not in candidate.tailored_results:
                raise HTTPException(status_code=404, detail="没有找到该岗位的定制简历")
            tailored = candidate.tailored_results[job_id]
            resume = candidate.confirmed_resume or candidate.display_resume
            hometown = candidate.polished_hometown
        else:
            resume = candidate.raw_resume if variant == "raw" else candidate.display_resume
            hometown = candidate.raw_hometown if variant == "raw" else candidate.polished_hometown
        selected_indices = []
        if suggestions:
            try:
                selected_indices = [int(part) for part in suggestions.split(",")]
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="补写句子选择无效") from exc
        try:
            section_overrides = (
                section_overrides_with_suggestions(tailored.tailored_resume, selected_indices)
                if tailored is not None
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if file_format == "docx":
            try:
                content = render_resume_docx(
                    resume,
                    hometown=hometown,
                    photo_asset=candidate.photo_asset,
                    template_id=candidate.template_id,
                    section_order=candidate.section_order,
                    custom_template=(
                        candidate.custom_template if candidate.template_id == "custom" else None
                    ),
                    section_overrides=section_overrides,
                    custom_theme=(
                        candidate.designed_template.theme.model_dump()
                        if candidate.template_id == "designed" and candidate.designed_template
                        else None
                    ),
                )
            except Exception as exc:
                logger.exception("Word resume export failed")
                raise HTTPException(
                    status_code=422,
                    detail="Word 简历生成失败，请切换内置模板或重新上传照片后重试",
                ) from exc
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif file_format == "pdf":
            try:
                content = render_resume_pdf(
                    resume,
                    hometown=hometown,
                    photo_asset=candidate.photo_asset,
                    template_id=candidate.template_id,
                    section_order=candidate.section_order,
                    custom_template=(
                        candidate.custom_template if candidate.template_id == "custom" else None
                    ),
                    section_overrides=section_overrides,
                    custom_theme=(
                        candidate.designed_template.theme.model_dump()
                        if candidate.template_id == "designed" and candidate.designed_template
                        else None
                    ),
                )
            except Exception as exc:
                logger.exception("PDF resume export failed")
                raise HTTPException(
                    status_code=422,
                    detail="PDF 简历生成失败，请切换内置模板或重新上传照片后重试",
                ) from exc
            media_type = "application/pdf"
        else:
            raise HTTPException(status_code=400, detail="只支持 Word 或 PDF")
        if variant == "tailored":
            assert tailored is not None
            suffix = f"{tailored.job.company}-{tailored.job.title}-定制版"
        else:
            suffix = "原始版" if variant == "raw" else "AI整理版"
        filename = f"{resume.personal_info.name or '个人'}简历-{suffix}.{file_format}"
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="resume.{file_format}"; '
                    f"filename*=UTF-8''{quote(filename)}"
                )
            },
        )

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return application


app = create_app(state_file=Path(__file__).resolve().parents[2] / "tmp" / "workspaces.json")
