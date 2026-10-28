"""Repository protocol and SQLAlchemy implementation."""

from __future__ import annotations

from datetime import UTC
from typing import Protocol

from sqlalchemy import select

from career_agent.jobs.models import Job
from career_agent.models import ApplicationRecord, ApplicationStatus, utc_now
from career_agent.persistence.database import Database
from career_agent.persistence.tables import ApplicationRow, JobRow, ResumeVersionRow
from career_agent.resume.models import TailoredResume, ValidationReport


class CareerRepository(Protocol):
    async def upsert_job(self, job: Job) -> None: ...

    async def save_application(self, record: ApplicationRecord) -> None: ...

    async def get_application(self, job_id: str) -> ApplicationRecord | None: ...

    async def save_resume_version(
        self,
        resume: TailoredResume,
        validation: ValidationReport,
        *,
        approved: bool,
    ) -> None: ...


class SQLAlchemyCareerRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def upsert_job(self, job: Job) -> None:
        async with self._database.sessions.begin() as session:
            result = await session.execute(
                select(JobRow).where(
                    JobRow.platform == job.platform,
                    JobRow.external_job_id == job.external_job_id,
                )
            )
            row = result.scalar_one_or_none()
            payload = job.model_dump_json()
            if row is None:
                session.add(
                    JobRow(
                        id=job.id,
                        platform=job.platform,
                        external_job_id=job.external_job_id,
                        payload=payload,
                        collected_at=job.collected_at,
                    )
                )
            else:
                row.payload = payload
                row.collected_at = job.collected_at

    async def save_application(self, record: ApplicationRecord) -> None:
        async with self._database.sessions.begin() as session:
            row = await session.get(ApplicationRow, record.job_id)
            values = record.model_dump(mode="python")
            values["status"] = record.status.value
            if row is None:
                session.add(ApplicationRow(**values))
            else:
                row.platform = record.platform
                row.status = record.status.value
                row.match_score = record.match_score
                row.resume_version = record.resume_version
                row.updated_at = record.updated_at

    async def get_application(self, job_id: str) -> ApplicationRecord | None:
        async with self._database.sessions() as session:
            row = await session.get(ApplicationRow, job_id)
            if row is None:
                return None
            created_at = (
                row.created_at.replace(tzinfo=UTC)
                if row.created_at.tzinfo is None
                else row.created_at
            )
            updated_at = (
                row.updated_at.replace(tzinfo=UTC)
                if row.updated_at.tzinfo is None
                else row.updated_at
            )
            return ApplicationRecord(
                job_id=row.job_id,
                platform=row.platform,
                status=ApplicationStatus(row.status),
                match_score=row.match_score,
                resume_version=row.resume_version,
                created_at=created_at,
                updated_at=updated_at,
            )

    async def save_resume_version(
        self,
        resume: TailoredResume,
        validation: ValidationReport,
        *,
        approved: bool,
    ) -> None:
        async with self._database.sessions.begin() as session:
            result = await session.execute(
                select(ResumeVersionRow).where(
                    ResumeVersionRow.resume_id == resume.source_resume_id,
                    ResumeVersionRow.version == resume.source_resume_version,
                    ResumeVersionRow.target_job_id == resume.target_job_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                session.add(
                    ResumeVersionRow(
                        resume_id=resume.source_resume_id,
                        version=resume.source_resume_version,
                        target_job_id=resume.target_job_id,
                        payload=resume.model_dump_json(),
                        validation_passed=validation.passed,
                        approved=approved,
                        created_at=utc_now(),
                    )
                )
            else:
                row.payload = resume.model_dump_json()
                row.validation_passed = validation.passed
                row.approved = approved
