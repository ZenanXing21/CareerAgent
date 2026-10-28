"""Unified MCP client implementing the Career graph's JobSource protocol."""

from __future__ import annotations

import json
from typing import Any

from mcp import Client

from career_agent.job_platform.models import JobDetailToolResult, JobSearchToolResult
from career_agent.jobs.models import Job, JobSearchQuery


class MCPJobPlatformError(RuntimeError):
    def __init__(self, code: str, *, operation: str) -> None:
        super().__init__(f"job platform MCP operation failed: {code}")
        self.code = code
        self.operation = operation


class MCPJobPlatformClient:
    """A short-lived client supporting an in-process server or remote MCP URL."""

    def __init__(self, target: Any) -> None:
        self._target = target

    async def _call(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        async with Client(self._target) as client:
            result = await client.call_tool(name, arguments)
        if result.is_error:
            detail = next(
                (
                    item.text
                    for item in result.content
                    if getattr(item, "type", None) == "text" and hasattr(item, "text")
                ),
                "UPSTREAM_FAILURE",
            )
            code = detail.split(":", maxsplit=1)[0]
            raise MCPJobPlatformError(code, operation=name)
        payload = result.structured_content
        if not isinstance(payload, dict):
            raise RuntimeError(f"MCP tool {name} returned no structured content")
        return payload

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        payload = await self._call(
            "search_jobs",
            {
                "keyword": query.keyword,
                "city": query.city,
                "salary_min": query.salary_min,
                "page": query.page,
                "company_names": query.company_names,
                "industries": query.industries,
                "company_sizes": query.company_sizes,
                "preferred_keywords": query.preferred_keywords,
            },
        )
        outcome = JobSearchToolResult.model_validate_json(json.dumps(payload))
        if outcome.error is not None:
            raise MCPJobPlatformError(outcome.error.code.value, operation="search_jobs")
        assert outcome.result is not None
        return outcome.result.jobs

    async def get_job_detail(self, job: Job) -> Job:
        payload = await self._call("get_job_detail", {"job_id": job.id})
        outcome = JobDetailToolResult.model_validate_json(json.dumps(payload))
        if outcome.error is not None:
            raise MCPJobPlatformError(outcome.error.code.value, operation="get_job_detail")
        assert outcome.result is not None
        return outcome.result.job
