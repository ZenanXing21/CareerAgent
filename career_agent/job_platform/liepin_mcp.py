"""Read-only business adapter for Liepin's hosted job MCP server."""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from career_agent.job_platform.adapters import AdapterUnavailable, JobNotFound, JobPlatformAdapter
from career_agent.job_platform.external_mcp import ExternalMCPAdapter
from career_agent.job_platform.liepin_cli import _find_job_rows, _normalize_liepin_job
from career_agent.jobs.models import Job, JobSearchQuery

DEFAULT_LIEPIN_MCP_URL = "https://open-agent.liepin.com/mcp/user"


class LiepinMCPAdapter(JobPlatformAdapter):
    """Search Liepin through its hosted MCP without exposing write tools."""

    platform = "liepin"

    def __init__(
        self,
        *,
        token: str,
        url: str = DEFAULT_LIEPIN_MCP_URL,
    ) -> None:
        if not token.strip():
            raise ValueError("Liepin MCP token must not be empty")
        self.url = url
        self._token = token
        self._jobs: dict[str, Job] = {}
        self._client = ExternalMCPAdapter(
            platform=self.platform,
            target=self._transport,
            search_tool="user-search-job",
            build_search_arguments=_liepin_search_arguments,
            normalize_search=_normalize_liepin_search,
        )

    @classmethod
    def from_env(cls) -> LiepinMCPAdapter:
        token = os.getenv("LIEPIN_MCP_USER_TOKEN", "")
        url = os.getenv("LIEPIN_MCP_URL", DEFAULT_LIEPIN_MCP_URL)
        if not token:
            raise ValueError("LIEPIN_MCP_USER_TOKEN is required")
        return cls(token=token, url=url)

    @asynccontextmanager
    async def _transport(self) -> AsyncIterator[Any]:
        # A fresh transport is created per operation. The token remains only in
        # the HTTP client headers and is never placed in tool arguments or logs.
        async with (
            create_mcp_http_client(headers={"x-user-token": self._token}) as http_client,
            streamable_http_client(self.url, http_client=http_client) as streams,
        ):
            yield streams

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        jobs = await self._client.search_jobs(query)
        self._jobs.update((job.id, job) for job in jobs)
        return jobs

    async def get_job_detail(self, job_id: str) -> Job:
        try:
            job = self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFound(
                "search for the Liepin job before requesting its detail",
                platform=self.platform,
            ) from exc
        if job.detail_verified:
            return job
        if not job.source_url:
            raise AdapterUnavailable(
                "Liepin MCP search result does not contain a job detail URL",
                platform=self.platform,
                retryable=False,
            )
        try:
            detail_text = await _fetch_liepin_job_description(job.source_url)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            message = str(exc)
            raise AdapterUnavailable(
                message or "猎聘岗位详情暂时无法读取",
                platform=self.platform,
                retryable=isinstance(exc, httpx.HTTPError) or "限流" in message,
            ) from exc
        detailed_job = job.model_copy(
            update={
                "summary": detail_text[:500],
                "detail_text": detail_text,
                "detail_verified": True,
            }
        )
        self._jobs[job_id] = detailed_job
        return detailed_job


def _liepin_search_arguments(query: JobSearchQuery) -> dict[str, object]:
    arguments: dict[str, object] = {
        "jobName": query.keyword,
        "address": query.city,
        "page": max(query.page - 1, 0),
    }
    if query.salary_min is not None:
        arguments["salaryFloor"] = str(query.salary_min)
    if len(query.company_names) == 1:
        arguments["companyName"] = query.company_names[0]
    if query.experience_levels:
        arguments["workExperience"] = query.experience_levels[0]
    return arguments


def _normalize_liepin_search(payload: object) -> list[Job]:
    return [_normalize_liepin_job(item) for item in _find_job_rows(payload)]


async def _fetch_liepin_job_description(url: str) -> str:
    _validate_liepin_url(url)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (compatible; CareerAgent/0.1)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
    _validate_liepin_url(str(response.url))
    final_url = str(response.url)
    if "wow.liepin.com" in final_url or "transit.html" in final_url:
        raise ValueError("猎聘详情页当前触发限流保护，请稍后再查看；岗位搜索仍然可用")
    return _extract_job_description(response.text)


def _validate_liepin_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not (host == "liepin.com" or host.endswith(".liepin.com")):
        raise ValueError("job detail URL is not an HTTPS Liepin URL")


def _extract_job_description(document: str) -> str:
    if any(
        marker in document
        for marker in ("我们找遍了所有地方", "此页面似乎不存在", "4s 后将进入猎聘首页")
    ):
        raise ValueError("该猎聘岗位已经下线")
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for script in scripts:
        payload = json.loads(unescape(script.strip()))
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("@type") != "JobPosting":
                continue
            description = candidate.get("description")
            if not isinstance(description, str):
                continue
            text = re.sub(r"<\s*br\s*/?\s*>", "\n", description, flags=re.IGNORECASE)
            text = re.sub(r"<\s*/\s*(?:p|div|li)\s*>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = unescape(text)
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            if text:
                return text
    matches = re.findall(
        r'<dd[^>]*data-selector=["\']job-intro-content["\'][^>]*>(.*?)</dd>',
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for value in matches:
        text = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.IGNORECASE)
        text = re.sub(r"<\s*/\s*(?:p|div|li)\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = unescape(text).replace("\\n", "\n")
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if text:
            return text
    raise ValueError("猎聘岗位详情页面缺少可识别的 JD 正文")
