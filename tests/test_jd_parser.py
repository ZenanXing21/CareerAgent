import asyncio

from career_agent import JDAnalysis, JDParser, JDRequirement


class JDProvider:
    def __init__(self, output: JDAnalysis) -> None:
        self.output = output
        self.calls = 0

    async def parse_jd(self, **_: object) -> JDAnalysis:
        self.calls += 1
        return self.output


def test_jd_parser_numbers_atomic_requirements_and_calls_once() -> None:
    source = "熟悉 Python；了解 MCP。"
    provider = JDProvider(
        JDAnalysis(
            job_id="job-1",
            source_text=source,
            requirements=[
                JDRequirement(
                    id="model-a",
                    text="熟悉 Python",
                    category="skill",
                    priority=1,
                    required=True,
                    keywords=["python"],
                ),
                JDRequirement(
                    id="model-b",
                    text="了解 MCP",
                    category="skill",
                    priority=2,
                    required=False,
                    keywords=["MCP"],
                ),
            ],
        )
    )
    parsed = asyncio.run(JDParser(provider).parse(job_id="job-1", source_text=source))
    assert provider.calls == 1
    assert [item.id for item in parsed.requirements] == ["req_001", "req_002"]


def test_jd_parser_drops_keyword_outside_source_without_failing() -> None:
    source = "熟悉 Python"
    provider = JDProvider(
        JDAnalysis(
            job_id="job-1",
            source_text=source,
            requirements=[
                JDRequirement(
                    id="x",
                    text="熟悉 Python",
                    category="skill",
                    priority=1,
                    required=True,
                    keywords=["Rust"],
                )
            ],
        )
    )
    parsed = asyncio.run(JDParser(provider).parse(job_id="job-1", source_text=source))
    assert parsed.requirements[0].keywords == []


def test_jd_parser_accepts_harmless_keyword_formatting_differences() -> None:
    source = "熟悉 Python/Java，了解 Agent Workflow。"
    provider = JDProvider(
        JDAnalysis(
            job_id="job-1",
            source_text=source,
            requirements=[
                JDRequirement(
                    id="x",
                    text="熟悉 Python/Java",
                    category="skill",
                    priority=1,
                    required=True,
                    keywords=["PYTHON ／ JAVA", "Agent   Workflow"],
                )
            ],
        )
    )

    parsed = asyncio.run(JDParser(provider).parse(job_id="job-1", source_text=source))

    assert parsed.requirements[0].keywords == ["PYTHON ／ JAVA", "Agent   Workflow"]
