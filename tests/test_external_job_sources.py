import asyncio

from mcp.server import MCPServer

from career_agent import (
    AdapterUnavailable,
    ExternalMCPAdapter,
    FallbackJobPlatformAdapter,
    Job,
    JobPlatformAdapter,
    JobSearchQuery,
)
from career_agent.job_platform.liepin_cli import (
    LiepinCLIAdapter,
    _find_job_rows,
    _normalize_liepin_job,
)
from career_agent.job_platform.liepin_mcp import (
    _extract_job_description,
    _liepin_search_arguments,
    _normalize_liepin_search,
)


def test_external_mcp_adapter_supports_custom_tool_contract() -> None:
    async def scenario() -> None:
        server = MCPServer("third-party-jobs")

        @server.tool()
        async def find_positions(q: str, location: str) -> dict[str, object]:
            job = Job(
                id="partner:1",
                platform="partner",
                external_job_id="1",
                title=f"{q} Engineer",
                company="Partner Inc.",
                location=location,
                detail_text="Build AI agents with Python.",
                source_url="https://example.com/jobs/1",
                apply_url="https://example.com/jobs/1/apply",
                detail_verified=True,
            )
            return {"jobs": [job.model_dump(mode="json")]}

        adapter = ExternalMCPAdapter(
            platform="partner",
            target=server,
            search_tool="find_positions",
            build_search_arguments=lambda query: {
                "q": query.keyword,
                "location": query.city,
            },
        )
        jobs = await adapter.search_jobs(JobSearchQuery(keyword="AI", city="上海"))

        assert jobs[0].id == "partner:1"
        assert jobs[0].apply_url == "https://example.com/jobs/1/apply"

    asyncio.run(scenario())


def test_liepin_cli_response_is_normalized_without_enabling_apply() -> None:
    payload = {
        "data": {
            "jobList": [
                {
                    "jobId": 123,
                    "jobName": "Python开发工程师",
                    "compName": "示例公司",
                    "dq": "上海",
                    "salaryText": "20-30K",
                    "jobDescription": "负责 Python Agent 开发",
                    "jobUrl": "https://www.liepin.com/job/123",
                    "jobKind": "2",
                }
            ]
        }
    }

    rows = _find_job_rows(payload)
    job = _normalize_liepin_job(rows[0])

    assert job.id == "liepin:123"
    assert job.detail_verified is True
    assert job.apply_url == "https://www.liepin.com/job/123"
    assert job.external_job_kind == "2"


def test_liepin_cli_apply_reuses_job_kind_from_search_result() -> None:
    class RecordingAdapter(LiepinCLIAdapter):
        def __init__(self) -> None:
            self.platform = "liepin"
            self.python_executable = "python"
            self.commands: list[list[str]] = []

        async def _run(self, command: list[str]) -> object:
            self.commands.append(command)
            return {"success": True}

    job = _normalize_liepin_job(
        {"jobId": 123, "jobKind": "2", "jobName": "Agent工程师"}
    )
    adapter = RecordingAdapter()

    result = asyncio.run(adapter.apply_job(job))

    assert result == {"success": True}
    assert adapter.commands[0][-6:] == [
        "--job-id",
        "123",
        "--job-kind",
        "2",
        "--output",
        "json",
    ]


def test_liepin_mcp_maps_internal_query_to_official_tool_schema() -> None:
    arguments = _liepin_search_arguments(
        JobSearchQuery(
            keyword="Agent工程师",
            city="上海",
            salary_min=20000,
            page=2,
            company_names=["目标公司"],
            experience_levels=["1-3年"],
        )
    )

    assert arguments == {
        "jobName": "Agent工程师",
        "address": "上海",
        "page": 1,
        "salaryFloor": "20000",
        "companyName": "目标公司",
        "workExperience": "1-3年",
    }
    assert (
        _normalize_liepin_search({"data": {"items": [{"jobId": 1, "jobName": "Agent工程师"}]}})[
            0
        ].id
        == "liepin:1"
    )


def test_liepin_search_maps_official_detail_url_and_metadata() -> None:
    job = _normalize_liepin_search(
        {
            "data": {
                "list": [
                    {
                        "jobId": 7,
                        "jobType": "2",
                        "jobName": "AI Agent工程师",
                        "company": "目标公司",
                        "location": "上海",
                        "salary": "20-30k",
                        "education": "本科",
                        "workYears": "1-3年",
                        "industry": "软件",
                        "companySize": "100-499人",
                        "jobDetailUrl": "https://www.liepin.com/job/7.shtml",
                    }
                ]
            }
        }
    )[0]

    assert job.source_url == "https://www.liepin.com/job/7.shtml"
    assert job.apply_url == job.source_url
    assert job.industry == "软件"
    assert job.company_size == "100-499人"
    assert job.detail_verified is False


def test_liepin_job_posting_json_ld_extracts_verified_jd() -> None:
    document = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting",
     "description":"<p>负责 Python Agent 开发</p><p>要求熟悉 LangGraph</p>"}
    </script>
    """

    assert _extract_job_description(document) == "负责 Python Agent 开发\n要求熟悉 LangGraph"


def test_liepin_detail_selector_extracts_verified_jd() -> None:
    document = """
    <dd class="job-intro" data-selector="job-intro-content">
      负责 Python Agent 开发\\n熟悉 LangGraph 与 RAG<br>具备工程交付能力
    </dd>
    """

    assert _extract_job_description(document) == (
        "负责 Python Agent 开发\n熟悉 LangGraph 与 RAG\n具备工程交付能力"
    )


def test_platform_fallback_uses_cli_shape_when_mcp_is_unavailable() -> None:
    class Source(JobPlatformAdapter):
        platform = "liepin"

        def __init__(self, available: bool) -> None:
            self.available = available

        async def search_jobs(self, query: JobSearchQuery) -> list[Job]:
            if not self.available:
                raise AdapterUnavailable("offline", platform=self.platform)
            return [
                Job(
                    id="liepin:1",
                    platform="liepin",
                    external_job_id="1",
                    title=query.keyword,
                    company="猎聘企业",
                    location=query.city,
                )
            ]

        async def get_job_detail(self, job_id: str) -> Job:
            raise NotImplementedError

    async def scenario() -> None:
        source = FallbackJobPlatformAdapter([Source(False), Source(True)])
        jobs = await source.search_jobs(JobSearchQuery(keyword="Python", city="上海"))
        assert jobs[0].id == "liepin:1"

    asyncio.run(scenario())
