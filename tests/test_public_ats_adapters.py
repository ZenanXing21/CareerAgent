import asyncio

import httpx

from career_agent import GreenhouseAdapter, JobSearchQuery, LeverAdapter


def test_greenhouse_adapter_normalizes_public_jobs_and_application_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["content"] == "true"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 42,
                        "title": "AI Agent Engineer",
                        "location": {"name": "上海"},
                        "absolute_url": "https://example.com/jobs/42",
                        "content": "<p>使用 Python 开发云服务 Agent</p>",
                        "departments": [{"name": "研发"}],
                    }
                ]
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = GreenhouseAdapter({"目标公司": "target"}, client=client)
            jobs = await adapter.search_jobs(
                JobSearchQuery(
                    keyword="Agent",
                    city="上海",
                    company_names=["目标公司"],
                    preferred_keywords=["云服务"],
                )
            )
        assert jobs[0].id == "greenhouse:target:42"
        assert jobs[0].detail_text == "使用 Python 开发云服务 Agent"
        assert jobs[0].apply_url == "https://example.com/jobs/42"
        assert jobs[0].detail_verified is True

    asyncio.run(run())


def test_lever_adapter_filters_preferences_without_llm() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "python-1",
                    "text": "Python Engineer",
                    "categories": {
                        "location": "Shanghai",
                        "department": "Cloud",
                        "commitment": "Full-time",
                    },
                    "descriptionPlain": "Build cloud services with Python.",
                    "hostedUrl": "https://jobs.lever.co/acme/python-1",
                    "applyUrl": "https://jobs.lever.co/acme/python-1/apply",
                },
                {
                    "id": "java-1",
                    "text": "Java Engineer",
                    "categories": {"location": "Shanghai"},
                    "descriptionPlain": "Build payment services.",
                    "hostedUrl": "https://jobs.lever.co/acme/java-1",
                    "applyUrl": "https://jobs.lever.co/acme/java-1/apply",
                },
            ],
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = LeverAdapter({"Acme": "acme"}, client=client)
            jobs = await adapter.search_jobs(
                JobSearchQuery(
                    keyword="Python",
                    city="Shanghai",
                    preferred_keywords=["cloud"],
                )
            )
        assert [job.external_job_id for job in jobs] == ["acme:python-1"]

    asyncio.run(run())
