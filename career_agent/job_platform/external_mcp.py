"""Adapter bridge for third-party MCP servers with configurable tool contracts."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp import Client

from career_agent.job_platform.adapters import AdapterUnavailable, JobPlatformAdapter
from career_agent.jobs.models import Job, JobSearchQuery

SearchArguments = Callable[[JobSearchQuery], dict[str, object]]
DetailArguments = Callable[[str], dict[str, object]]
SearchNormalizer = Callable[[object], list[Job]]
DetailNormalizer = Callable[[object], Job]


class ExternalMCPAdapter(JobPlatformAdapter):
    """Expose an external MCP server through the internal adapter contract.

    Third-party servers rarely share identical tool names or schemas, so request
    builders and result normalizers are explicit dependencies rather than hidden
    prompt logic.
    """

    def __init__(
        self,
        *,
        platform: str,
        target: Any,
        search_tool: str = "search_jobs",
        detail_tool: str = "get_job_detail",
        build_search_arguments: SearchArguments | None = None,
        build_detail_arguments: DetailArguments | None = None,
        normalize_search: SearchNormalizer | None = None,
        normalize_detail: DetailNormalizer | None = None,
    ) -> None:
        self.platform = platform
        self._target = target
        self._search_tool = search_tool
        self._detail_tool = detail_tool
        self._build_search_arguments = build_search_arguments or _default_search_arguments
        self._build_detail_arguments = build_detail_arguments or (lambda job_id: {"job_id": job_id})
        self._normalize_search = normalize_search or _default_search_normalizer
        self._normalize_detail = normalize_detail or _default_detail_normalizer

    async def _call(self, tool: str, arguments: dict[str, object]) -> object:
        try:
            target = self._target() if callable(self._target) else self._target
            async with Client(target) as client:
                result = await client.call_tool(tool, arguments)
        except Exception as exc:
            raise AdapterUnavailable(
                "external MCP server request failed",
                platform=self.platform,
                retryable=True,
            ) from exc
        if result.is_error:
            raise AdapterUnavailable(
                "external MCP tool returned an error",
                platform=self.platform,
                retryable=False,
            )
        if result.structured_content is not None:
            return result.structured_content
        for item in result.content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    continue
        raise AdapterUnavailable(
            "external MCP tool returned no machine-readable result",
            platform=self.platform,
        )

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        payload = await self._call(self._search_tool, self._build_search_arguments(query))
        return self._normalize_search(payload)

    async def get_job_detail(self, job_id: str) -> Job:
        payload = await self._call(self._detail_tool, self._build_detail_arguments(job_id))
        return self._normalize_detail(payload)


def _default_search_arguments(query: JobSearchQuery) -> dict[str, object]:
    return {
        "keyword": query.keyword,
        "city": query.city,
        "salary_min": query.salary_min,
        "page": query.page,
    }


def _default_search_normalizer(payload: object) -> list[Job]:
    if isinstance(payload, dict):
        payload = payload.get("jobs", payload.get("result", payload))
    if not isinstance(payload, list):
        raise ValueError("external MCP search result must contain a jobs list")
    return [Job.model_validate_json(json.dumps(item)) for item in payload]


def _default_detail_normalizer(payload: object) -> Job:
    if isinstance(payload, dict) and "job" in payload:
        payload = payload["job"]
    return Job.model_validate_json(json.dumps(payload))
