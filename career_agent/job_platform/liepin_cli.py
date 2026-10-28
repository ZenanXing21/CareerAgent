"""Bridge from the downloaded Liepin CLI to jobs, resume sync, and applications."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from career_agent.job_platform.adapters import (
    AdapterUnavailable,
    JobNotFound,
    JobPlatformAdapter,
)
from career_agent.jobs.models import Job, JobSearchQuery


class LiepinCLIAdapter(JobPlatformAdapter):
    platform = "liepin"

    def __init__(
        self,
        repo_path: str | Path,
        *,
        python_executable: str = sys.executable,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        if not (self.repo_path / "liepin_cli" / "main.py").is_file():
            raise ValueError("repo_path does not contain the Liepin CLI source")
        self.python_executable = python_executable
        self.timeout_seconds = timeout_seconds
        self._jobs: dict[str, Job] = {}

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        command = [
            self.python_executable,
            "-m",
            "liepin_cli.main",
            "job",
            "search",
            "--job-name",
            query.keyword,
            "--address",
            query.city,
            "--page",
            str(max(query.page - 1, 0)),
            "--output",
            "json",
        ]
        if query.salary_min is not None:
            command.extend(("--salary-floor", str(query.salary_min)))
        if len(query.company_names) == 1:
            command.extend(("--company-name", query.company_names[0]))
        payload = await self._run(command)
        jobs = [_normalize_liepin_job(item) for item in _find_job_rows(payload)]
        self._jobs.update((job.id, job) for job in jobs)
        return jobs

    async def get_job_detail(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFound(
                "Liepin CLI has no detail command; search for the job first",
                platform=self.platform,
            ) from exc

    async def apply_job(self, job: Job) -> object:
        """Apply using the resume currently stored in the user's Liepin account."""

        if job.platform != self.platform or not job.external_job_kind:
            raise AdapterUnavailable(
                "Liepin application requires jobKind from the search result",
                platform=self.platform,
                retryable=False,
            )
        if job.external_job_kind not in {"1", "2"} or not job.external_job_id.isdigit():
            raise AdapterUnavailable(
                "Liepin search returned an invalid jobId or jobKind",
                platform=self.platform,
                retryable=False,
            )
        return await self._run(
            [
                self.python_executable,
                "-m",
                "liepin_cli.main",
                "job",
                "apply",
                "--job-id",
                job.external_job_id,
                "--job-kind",
                job.external_job_kind,
                "--output",
                "json",
            ]
        )


    async def _run(self, command: list[str]) -> object:
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        # The hosted MCP and CLI use the same x-user-token. Reuse the already
        # configured local value through the child environment, never argv/logs.
        if not environment.get("LIEPIN_USER_TOKEN") and environment.get(
            "LIEPIN_MCP_USER_TOKEN"
        ):
            environment["LIEPIN_USER_TOKEN"] = environment["LIEPIN_MCP_USER_TOKEN"]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.repo_path,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout_seconds
            )
        except TimeoutError as exc:
            raise AdapterUnavailable(
                "Liepin CLI timed out", platform=self.platform, retryable=True
            ) from exc
        except OSError as exc:
            raise AdapterUnavailable(
                "Liepin CLI could not be started", platform=self.platform
            ) from exc
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").casefold()
            authentication = any(token in message for token in ("token", "授权", "401", "403"))
            raise AdapterUnavailable(
                "Liepin CLI authorization is required"
                if authentication
                else "Liepin CLI search failed",
                platform=self.platform,
                retryable=authentication,
            )
        try:
            return json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdapterUnavailable(
                "Liepin CLI returned invalid JSON", platform=self.platform
            ) from exc


def _find_job_rows(payload: object) -> list[Mapping[str, Any]]:
    if (
        isinstance(payload, list)
        and all(isinstance(item, dict) for item in payload)
        and (not payload or any(_first(item, "jobId", "job_id", "id") for item in payload))
    ):
        return payload
    if isinstance(payload, dict):
        for key in ("jobs", "jobList", "list", "items", "records", "data", "result"):
            if key in payload:
                rows = _find_job_rows(payload[key])
                if rows:
                    return rows
    return []


def _normalize_liepin_job(item: Mapping[str, Any]) -> Job:
    external_id = str(_first(item, "jobId", "job_id", "id") or "").strip()
    title = str(_first(item, "jobName", "jobTitle", "title", "name") or "").strip()
    if not external_id or not title:
        raise ValueError("Liepin job result lacks job id or title")
    company = str(_first(item, "compName", "companyName", "company") or "猎聘企业").strip()
    location = str(_first(item, "dq", "address", "city", "location") or "未注明").strip()
    details = "\n".join(
        str(value).strip()
        for key in (
            "jobDescription",
            "jobDesc",
            "description",
            "responsibility",
            "requirement",
        )
        if (value := item.get(key))
    )
    url_value = _first(item, "jobDetailUrl", "jobUrl", "applyUrl", "url", "link")
    url = str(url_value).strip() if url_value else None
    salary_value = _first(item, "salary", "salaryText", "salaryDesc")
    salary = str(salary_value).strip() if salary_value else None
    summary_parts = [
        str(item[key]).strip()
        for key in ("education", "workYears", "industry", "companySize")
        if item.get(key)
    ]
    return Job(
        id=f"liepin:{external_id}",
        platform="liepin",
        external_job_id=external_id,
        external_job_kind=(
            str(_first(item, "jobKind", "job_kind", "kind")).strip()
            if _first(item, "jobKind", "job_kind", "kind") is not None
            else None
        ),
        title=title,
        company=company,
        location=location,
        salary_text=salary,
        summary=details[:500] or " · ".join(summary_parts) or None,
        detail_text=details or None,
        source_url=url,
        apply_url=url,
        employment_type=str(item["jobType"]).strip() if item.get("jobType") else None,
        industry=str(item["industry"]).strip() if item.get("industry") else None,
        company_size=str(item["companySize"]).strip() if item.get("companySize") else None,
        detail_verified=bool(details),
    )


def _first(item: Mapping[str, Any], *keys: str) -> object | None:
    return next((item[key] for key in keys if item.get(key) is not None), None)
