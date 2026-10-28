"""Server-side adapters for public company ATS job-board APIs."""

from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Mapping
from html import unescape
from typing import Any

import httpx

from career_agent.job_platform.adapters import (
    AdapterUnavailable,
    JobNotFound,
    JobPlatformAdapter,
)
from career_agent.jobs.models import Job, JobSearchQuery

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _plain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _SPACE.sub(" ", unescape(_TAG.sub(" ", value))).strip()


def _matches(job: Job, query: JobSearchQuery, *, require_keyword: bool = True) -> bool:
    text = " ".join(
        filter(None, (job.title, job.summary, job.detail_text, job.department))
    ).casefold()
    keyword_match = not require_keyword or query.keyword.casefold() in text
    preferred_match = not query.preferred_keywords or any(
        keyword.casefold() in text for keyword in query.preferred_keywords
    )
    city_match = query.city.casefold() in {"不限", "全国", "any", "all"} or (
        query.city.casefold() in job.location.casefold()
    )
    company_match = not query.company_names or any(
        name.casefold() in job.company.casefold() for name in query.company_names
    )
    industry_match = not query.industries or (
        job.industry is not None
        and any(value.casefold() in job.industry.casefold() for value in query.industries)
    )
    size_match = not query.company_sizes or job.company_size in query.company_sizes
    return (
        keyword_match
        and preferred_match
        and city_match
        and company_match
        and industry_match
        and size_match
    )


class PublicATSAdapter(JobPlatformAdapter):
    """Shared transport/error boundary for unauthenticated public job boards."""

    def __init__(
        self,
        companies: Mapping[str, str],
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not companies:
            raise ValueError("at least one company mapping is required")
        self.companies = dict(companies)
        self._client = client
        self._timeout = timeout_seconds

    async def _get_json(self, url: str, *, params: dict[str, object] | None = None) -> Any:
        owned = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        try:
            response = await client.get(url, params=params, headers={"Accept": "application/json"})
            if response.status_code == 404:
                raise JobNotFound("public job was not found", platform=self.platform)
            response.raise_for_status()
            return response.json()
        except JobNotFound:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AdapterUnavailable(
                "public ATS request failed", platform=self.platform, retryable=True
            ) from exc
        finally:
            if owned:
                await client.aclose()

    @abstractmethod
    async def _list_company(self, company: str, slug: str) -> list[Job]: ...

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        jobs: list[Job] = []
        for company, slug in self.companies.items():
            if query.company_names and not any(
                value.casefold() in company.casefold() for value in query.company_names
            ):
                continue
            jobs.extend(await self._list_company(company, slug))
        return [job for job in jobs if _matches(job, query)]


class GreenhouseAdapter(PublicATSAdapter):
    platform = "greenhouse"

    async def _list_company(self, company: str, slug: str) -> list[Job]:
        data = await self._get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            params={"content": "true"},
        )
        return [self._job(company, slug, item) for item in data.get("jobs", [])]

    def _job(self, company: str, slug: str, item: Mapping[str, Any]) -> Job:
        external_id = str(item["id"])
        detail = _plain(item.get("content"))
        departments = item.get("departments") or []
        department = departments[0].get("name") if departments else None
        url = str(item.get("absolute_url") or "") or None
        return Job(
            id=f"{self.platform}:{slug}:{external_id}",
            platform=self.platform,
            external_job_id=f"{slug}:{external_id}",
            title=str(item["title"]),
            company=company,
            location=str((item.get("location") or {}).get("name") or "未注明"),
            summary=detail[:500] or None,
            detail_text=detail or None,
            department=department,
            source_url=url,
            apply_url=url,
            detail_verified=bool(detail),
        )

    async def get_job_detail(self, job_id: str) -> Job:
        slug, external_id = _parts(job_id, self.platform)
        company = _company_for_slug(self.companies, slug, self.platform)
        data = await self._get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{external_id}"
        )
        return self._job(company, slug, data)


class LeverAdapter(PublicATSAdapter):
    platform = "lever"

    async def _list_company(self, company: str, slug: str) -> list[Job]:
        data = await self._get_json(
            f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"}
        )
        return [self._job(company, slug, item) for item in data]

    def _job(self, company: str, slug: str, item: Mapping[str, Any]) -> Job:
        external_id = str(item["id"])
        categories = item.get("categories") or {}
        detail = _plain(item.get("descriptionPlain") or item.get("description"))
        apply_url = str(item.get("applyUrl") or "") or None
        source_url = str(item.get("hostedUrl") or "") or apply_url
        return Job(
            id=f"{self.platform}:{slug}:{external_id}",
            platform=self.platform,
            external_job_id=f"{slug}:{external_id}",
            title=str(item["text"]),
            company=company,
            location=str(categories.get("location") or "未注明"),
            summary=detail[:500] or None,
            detail_text=detail or None,
            department=categories.get("department") or None,
            employment_type=categories.get("commitment") or None,
            source_url=source_url,
            apply_url=apply_url,
            detail_verified=bool(detail),
        )

    async def get_job_detail(self, job_id: str) -> Job:
        slug, external_id = _parts(job_id, self.platform)
        company = _company_for_slug(self.companies, slug, self.platform)
        data = await self._get_json(
            f"https://api.lever.co/v0/postings/{slug}/{external_id}",
            params={"mode": "json"},
        )
        return self._job(company, slug, data)


class SmartRecruitersAdapter(PublicATSAdapter):
    platform = "smartrecruiters"

    async def _list_company(self, company: str, slug: str) -> list[Job]:
        return await self._search_company(company, slug, keyword=None)

    async def _search_company(self, company: str, slug: str, *, keyword: str | None) -> list[Job]:
        offset = 0
        jobs: list[Job] = []
        while True:
            params: dict[str, object] = {"limit": 100, "offset": offset}
            if keyword:
                params["q"] = keyword
            data = await self._get_json(
                f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                params=params,
            )
            rows = data.get("content", [])
            for row in rows:
                detail = await self._get_json(
                    f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{row['id']}"
                )
                jobs.append(self._job(company, slug, detail))
            offset += len(rows)
            if not rows or offset >= int(data.get("totalFound", offset)):
                return jobs

    async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
        jobs: list[Job] = []
        for company, slug in self.companies.items():
            if query.company_names and not any(
                value.casefold() in company.casefold() for value in query.company_names
            ):
                continue
            jobs.extend(await self._search_company(company, slug, keyword=query.keyword))
        # SmartRecruiters already applies its server-side full-text query. Do not
        # discard results merely because the exact query term is absent from the
        # normalized title/body returned by the detail endpoint.
        return [job for job in jobs if _matches(job, query, require_keyword=False)]

    def _job(self, company: str, slug: str, item: Mapping[str, Any]) -> Job:
        external_id = str(item["id"])
        location = item.get("location") or {}
        sections = (item.get("jobAd") or {}).get("sections") or {}
        detail = "\n".join(
            text for text in (_plain(section.get("text")) for section in sections.values()) if text
        )
        department = (item.get("department") or {}).get("label")
        source_url = str(item.get("postingUrl") or "") or None
        apply_url = str(item.get("applyUrl") or "") or source_url
        location_text = ", ".join(
            str(value) for key in ("city", "region", "country") if (value := location.get(key))
        )
        return Job(
            id=f"{self.platform}:{slug}:{external_id}",
            platform=self.platform,
            external_job_id=f"{slug}:{external_id}",
            title=str(item["name"]),
            company=company,
            location=location_text or "未注明",
            summary=detail[:500] or None,
            detail_text=detail or None,
            department=department,
            employment_type=(item.get("typeOfEmployment") or {}).get("label"),
            source_url=source_url,
            apply_url=apply_url,
            detail_verified=bool(detail),
        )

    async def get_job_detail(self, job_id: str) -> Job:
        slug, external_id = _parts(job_id, self.platform)
        company = _company_for_slug(self.companies, slug, self.platform)
        data = await self._get_json(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{external_id}"
        )
        return self._job(company, slug, data)


def _parts(job_id: str, platform: str) -> tuple[str, str]:
    parts = job_id.split(":", maxsplit=2)
    if len(parts) != 3 or parts[0] != platform:
        raise JobNotFound("invalid opaque job id", platform=platform)
    return parts[1], parts[2]


def _company_for_slug(companies: Mapping[str, str], slug: str, platform: str) -> str:
    try:
        return next(company for company, value in companies.items() if value == slug)
    except StopIteration as exc:
        raise JobNotFound("company board is not configured", platform=platform) from exc
