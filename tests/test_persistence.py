import asyncio

from sqlalchemy import func, select

from career_agent import ApplicationRecord, ApplicationStatus, Job
from career_agent.persistence import Database, SQLAlchemyCareerRepository
from career_agent.persistence.tables import JobRow


def test_sqlite_repository_upserts_jobs_and_applications(tmp_path) -> None:
    async def scenario() -> None:
        database = Database(f"sqlite+aiosqlite:///{tmp_path / 'career.db'}")
        await database.create_schema()
        repository = SQLAlchemyCareerRepository(database)
        job = Job(
            id="job-1",
            platform="mock",
            external_job_id="ext-1",
            title="Python 工程师",
            company="甲公司",
            location="上海",
        )
        await repository.upsert_job(job)
        await repository.upsert_job(job.model_copy(update={"summary": "更新后的摘要"}))
        async with database.sessions() as session:
            count = await session.scalar(select(func.count()).select_from(JobRow))
        assert count == 1

        record = ApplicationRecord(
            job_id="job-1",
            platform="mock",
            status=ApplicationStatus.READY_TO_APPLY,
            match_score=0.8,
            resume_version="v1",
        )
        await repository.save_application(record)
        loaded = await repository.get_application("job-1")
        assert loaded is not None
        assert loaded.status is ApplicationStatus.READY_TO_APPLY
        assert loaded.match_score == 0.8
        await database.dispose()

    asyncio.run(scenario())
