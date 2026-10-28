"""Platform adapter contract, deterministic mock, and honest unavailable stubs."""

from __future__ import annotations

from abc import ABC, abstractmethod

from career_agent.jobs.models import Job, JobSearchQuery


class JobPlatformAdapterError(RuntimeError):
    """Base exception safe for mapping at the MCP boundary."""

    def __init__(self, message: str, *, platform: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.platform = platform
        self.retryable = retryable


class AdapterUnavailable(JobPlatformAdapterError):
    """The adapter has no configured authorized endpoint."""


class AdapterNotImplemented(JobPlatformAdapterError):
    """The platform contract exists, but its integration is intentionally absent."""


class JobNotFound(JobPlatformAdapterError):
    """The platform does not know the requested opaque job ID."""


class JobPlatformAdapter(ABC):
    platform: str

    @abstractmethod
    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        """Return normalized summaries with opaque platform-prefixed IDs."""

    @abstractmethod
    async def get_job_detail(self, job_id: str) -> Job:
        """Return a verified detail for an opaque ID previously returned by search."""


class FallbackJobPlatformAdapter(JobPlatformAdapter):
    """Use the first healthy implementation of one logical platform."""

    def __init__(self, adapters: list[JobPlatformAdapter]) -> None:
        if not adapters:
            raise ValueError("at least one fallback adapter is required")
        platforms = {adapter.platform for adapter in adapters}
        if len(platforms) != 1:
            raise ValueError("fallback adapters must represent the same platform")
        self.platform = adapters[0].platform
        self._adapters = adapters
        self._owners: dict[str, JobPlatformAdapter] = {}

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        errors: list[JobPlatformAdapterError] = []
        for adapter in self._adapters:
            try:
                jobs = await adapter.search_jobs(query)
            except (AdapterUnavailable, AdapterNotImplemented) as exc:
                errors.append(exc)
                continue
            self._owners.update((job.id, adapter) for job in jobs)
            return jobs
        raise AdapterUnavailable(
            "all implementations for this platform are unavailable",
            platform=self.platform,
            retryable=any(error.retryable for error in errors),
        )

    async def get_job_detail(self, job_id: str) -> Job:
        owner = self._owners.get(job_id)
        if owner is not None:
            return await owner.get_job_detail(job_id)
        for adapter in self._adapters:
            try:
                return await adapter.get_job_detail(job_id)
            except (AdapterUnavailable, AdapterNotImplemented, JobNotFound):
                continue
        raise JobNotFound("job is unknown to every platform implementation", platform=self.platform)


class MockAdapter(JobPlatformAdapter):
    platform = "mock"

    def __init__(self) -> None:
        self._jobs = {
            job.id: job
            for job in (
                Job(
                    id="mock:python-agent",
                    platform=self.platform,
                    external_job_id="python-agent",
                    title="Python AI Agent 工程师",
                    company="示例科技",
                    location="上海",
                    salary_text="20-30K",
                    summary="Python、Agent、结构化输出",
                    detail_text=(
                        "负责 Python AI Agent 开发；必须熟悉 Python；"
                        "有 LangGraph 或工作流经验优先；重视可测试性。"
                    ),
                    source_url="https://example.invalid/jobs/python-agent",
                    detail_verified=True,
                ),
                Job(
                    id="mock:data-analyst",
                    platform=self.platform,
                    external_job_id="data-analyst",
                    title="数据分析师",
                    company="示例数据",
                    location="上海",
                    salary_text="15-22K",
                    summary="Python、SQL、数据可视化",
                    detail_text="使用 Python 和 SQL 完成分析；有可视化项目经验优先。",
                    source_url="https://example.invalid/jobs/data-analyst",
                    detail_verified=True,
                ),
                Job(
                    id="mock:java-lead",
                    platform=self.platform,
                    external_job_id="java-lead",
                    title="Java 技术负责人",
                    company="示例企业",
                    location="上海",
                    salary_text="35-50K",
                    summary="Java、分布式系统、团队管理",
                    detail_text="必须精通 Java；五年以上团队管理经验；主导大型分布式系统。",
                    source_url="https://example.invalid/jobs/java-lead",
                    detail_verified=True,
                ),
            )
        }

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        keyword = query.keyword.casefold()
        city = query.city.casefold()
        matches = [
            job
            for job in self._jobs.values()
            if (keyword in job.title.casefold() or keyword in (job.summary or "").casefold())
            and (city in {"不限", "全国"} or city in job.location.casefold())
        ]
        # The fixed dataset remains useful for the POC even with a broad role query.
        return matches or list(self._jobs.values())

    async def get_job_detail(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFound(
                f"job not found: {job_id}", platform=self.platform, retryable=False
            ) from exc


class _UnavailablePlatformAdapter(JobPlatformAdapter):
    def __init__(self, *, endpoint: str | None = None) -> None:
        self._endpoint = endpoint

    def _raise(self) -> None:
        if not self._endpoint:
            raise AdapterUnavailable(
                "authorized API endpoint is not configured",
                platform=self.platform,
                retryable=False,
            )
        raise AdapterNotImplemented(
            "authorized platform integration is not implemented in this POC",
            platform=self.platform,
            retryable=False,
        )

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        del query
        self._raise()

    async def get_job_detail(self, job_id: str) -> Job:
        del job_id
        self._raise()


class BossAdapter(_UnavailablePlatformAdapter):
    platform = "boss"


class LiepinAdapter(_UnavailablePlatformAdapter):
    platform = "liepin"


class ZhilianAdapter(_UnavailablePlatformAdapter):
    platform = "zhilian"
