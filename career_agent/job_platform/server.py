"""MCP server exposing the two POC job-platform tools."""

from __future__ import annotations

from mcp.server import MCPServer

from career_agent.job_platform.adapters import (
    AdapterNotImplemented,
    AdapterUnavailable,
    JobNotFound,
    JobPlatformAdapter,
)
from career_agent.job_platform.models import (
    JobDetailResponse,
    JobDetailToolResult,
    JobPlatformErrorCode,
    JobPlatformToolError,
    JobSearchResponse,
    JobSearchToolResult,
)
from career_agent.jobs.models import JobSearchQuery


class JobPlatformRegistry:
    def __init__(self, adapters: list[JobPlatformAdapter]) -> None:
        self._adapters = {adapter.platform: adapter for adapter in adapters}
        if not self._adapters:
            raise ValueError("at least one job platform adapter is required")

    async def search(self, query: JobSearchQuery) -> JobSearchResponse:
        jobs = []
        unavailable = []
        for platform, adapter in self._adapters.items():
            try:
                jobs.extend(await adapter.search_jobs(query))
            except (AdapterUnavailable, AdapterNotImplemented):
                unavailable.append(platform)
        if not jobs and unavailable:
            raise AdapterUnavailable(
                "all configured job platforms are unavailable",
                platform=",".join(sorted(unavailable)),
            )
        return JobSearchResponse(
            jobs=jobs,
            unavailable_platforms=sorted(unavailable),
        )

    async def detail(self, job_id: str) -> JobDetailResponse:
        platform, separator, _ = job_id.partition(":")
        if not separator or platform not in self._adapters:
            raise JobNotFound("unknown opaque job id", platform=platform or "unknown")
        return JobDetailResponse(job=await self._adapters[platform].get_job_detail(job_id))


def create_job_platform_server(registry: JobPlatformRegistry) -> MCPServer:
    server = MCPServer("career-agent-job-platform")

    @server.tool()
    async def search_jobs(
        keyword: str,
        city: str,
        salary_min: int | None = None,
        page: int = 1,
        company_names: list[str] | None = None,
        industries: list[str] | None = None,
        company_sizes: list[str] | None = None,
        preferred_keywords: list[str] | None = None,
    ) -> JobSearchToolResult:
        """Search configured job platforms and return normalized job summaries."""

        query = JobSearchQuery(
            keyword=keyword,
            city=city,
            salary_min=salary_min,
            page=page,
            company_names=company_names or [],
            industries=industries or [],
            company_sizes=company_sizes or [],
            preferred_keywords=preferred_keywords or [],
        )
        try:
            return JobSearchToolResult(result=await registry.search(query))
        except AdapterUnavailable as exc:
            return JobSearchToolResult(
                error=JobPlatformToolError(
                    code=JobPlatformErrorCode.ADAPTER_UNAVAILABLE,
                    message="configured adapter is unavailable",
                    retryable=exc.retryable,
                    platform=exc.platform,
                )
            )
        except AdapterNotImplemented as exc:
            return JobSearchToolResult(
                error=JobPlatformToolError(
                    code=JobPlatformErrorCode.NOT_IMPLEMENTED,
                    message="configured adapter is not implemented",
                    retryable=exc.retryable,
                    platform=exc.platform,
                )
            )

    @server.tool()
    async def get_job_detail(job_id: str) -> JobDetailToolResult:
        """Fetch a verified job description using an opaque job ID from search_jobs."""

        try:
            return JobDetailToolResult(result=await registry.detail(job_id))
        except JobNotFound as exc:
            return _detail_error(JobPlatformErrorCode.NOT_FOUND, exc)
        except AdapterUnavailable as exc:
            return _detail_error(JobPlatformErrorCode.ADAPTER_UNAVAILABLE, exc)
        except AdapterNotImplemented as exc:
            return _detail_error(JobPlatformErrorCode.NOT_IMPLEMENTED, exc)

    return server


def _detail_error(code: JobPlatformErrorCode, exc: Exception) -> JobDetailToolResult:
    return JobDetailToolResult(
        error=JobPlatformToolError(
            code=code,
            message="job detail is unavailable",
            retryable=getattr(exc, "retryable", False),
            platform=getattr(exc, "platform", "unknown"),
        )
    )
