import asyncio

import pytest

from career_agent import (
    AdapterUnavailable,
    BossAdapter,
    JobPlatformRegistry,
    MCPJobPlatformClient,
    MCPJobPlatformError,
    MockAdapter,
    create_job_platform_server,
)
from career_agent.jobs.models import JobSearchQuery


def test_mock_adapter_runs_through_real_in_process_mcp_tools() -> None:
    async def scenario() -> None:
        server = create_job_platform_server(JobPlatformRegistry([MockAdapter(), BossAdapter()]))
        client = MCPJobPlatformClient(server)
        jobs = await client.search_jobs(JobSearchQuery(keyword="Python", city="上海"))
        assert [job.id for job in jobs] == ["mock:python-agent", "mock:data-analyst"]
        detail = await client.get_job_detail(jobs[0])
        assert detail.detail_verified is True
        assert detail.detail_text is not None

    asyncio.run(scenario())


def test_real_platform_stub_is_explicitly_unavailable() -> None:
    async def scenario() -> None:
        with pytest.raises(AdapterUnavailable, match="endpoint"):
            await BossAdapter().search_jobs(JobSearchQuery(keyword="Python", city="上海"))

    asyncio.run(scenario())


def test_registry_fails_when_every_platform_is_unavailable() -> None:
    async def scenario() -> None:
        registry = JobPlatformRegistry([BossAdapter()])
        with pytest.raises(AdapterUnavailable, match="all configured"):
            await registry.search(JobSearchQuery(keyword="Python", city="上海"))

    asyncio.run(scenario())


def test_mcp_maps_unavailable_adapter_to_stable_safe_code() -> None:
    async def scenario() -> None:
        server = create_job_platform_server(JobPlatformRegistry([BossAdapter()]))
        client = MCPJobPlatformClient(server)
        with pytest.raises(MCPJobPlatformError) as captured:
            await client.search_jobs(JobSearchQuery(keyword="Python", city="上海"))
        assert captured.value.code == "ADAPTER_UNAVAILABLE"

    asyncio.run(scenario())
