"""One-call structured resume parsing with deterministic provenance checks."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from career_agent.llm.base import LLMError, LLMProvider, LLMProviderError, StructuredOutputError
from career_agent.resume.models import ExperienceType, Resume


class ResumeParser:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def parse(self, *, resume_id: str, version: str, raw_text: str) -> Resume:
        try:
            parsed = await self._provider.parse_resume(
                resume_id=resume_id, version=version, raw_text=raw_text
            )
        except LLMError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StructuredOutputError(
                "resume provider returned invalid structured output"
            ) from exc
        except Exception as exc:
            raise LLMProviderError("resume parsing provider call failed") from exc

        if not isinstance(parsed, Resume):
            raise StructuredOutputError("resume provider did not return a Resume")

        payload = parsed.model_dump()
        payload.update(resume_id=resume_id, version=version, raw_text=raw_text)
        prefixes = {
            "educations": "edu",
            "work_experiences": "work",
            "internships": "intern",
            "project_experiences": "project",
            "campus_experiences": "campus",
        }
        for field, prefix in prefixes.items():
            for index, entry in enumerate(payload[field], start=1):
                entry["id"] = f"{prefix}_{index:03d}"
                if field == "work_experiences":
                    entry["experience_type"] = ExperienceType.WORK
                elif field == "internships":
                    entry["experience_type"] = ExperienceType.INTERNSHIP
        try:
            result = Resume.model_validate(payload)
        except ValidationError as exc:
            raise StructuredOutputError("resume output failed domain validation") from exc
        self._validate_provenance(result)
        return result

    @staticmethod
    def _validate_provenance(resume: Resume) -> None:
        raw_text = resume.raw_text
        entry_groups = (
            (resume.educations, ("school", "degree", "major")),
            (resume.work_experiences, ("company", "title")),
            (resume.internships, ("company", "title")),
            (resume.project_experiences, ("name", "role", "project_type")),
            (resume.campus_experiences, ("organization", "role")),
            (resume.skills, ("name",)),
        )
        for entries, source_bound_fields in entry_groups:
            for entry in entries:
                ResumeParser._validate_entry_provenance(
                    entry, raw_text=raw_text, source_bound_fields=source_bound_fields
                )
        for project in resume.project_experiences:
            for technology in project.technologies:
                if technology.casefold() not in project.source_text.casefold():
                    raise StructuredOutputError(
                        "project technology is not present in entry source_text"
                    )
        info = resume.personal_info
        values = [info.name, info.email, info.phone, info.location, *info.links]
        if any(value is not None and value not in raw_text for value in values):
            raise StructuredOutputError("personal information is not present in raw_text")

    @staticmethod
    def _validate_entry_provenance(
        entry: Any, *, raw_text: str, source_bound_fields: tuple[str, ...]
    ) -> None:
        source_text = entry.source_text
        if source_text not in raw_text:
            raise StructuredOutputError("resume entry source_text is not present in raw_text")
        folded_source = source_text.casefold()
        for field in source_bound_fields:
            value = getattr(entry, field, None)
            if value is not None and value.casefold() not in folded_source:
                raise StructuredOutputError(
                    f"resume entry {field} is not present in entry source_text"
                )
