import asyncio
from types import SimpleNamespace

import pytest

from career_agent import EvidenceStatus, OpenAICompatibleProvider
from career_agent.llm.openai_compatible import _EvidenceMatches, _validate_plain_json


def test_provider_requires_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAREER_AGENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("CAREER_AGENT_LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="API_KEY"):
        OpenAICompatibleProvider.from_env(env_file=None)


def test_provider_reads_openai_compatible_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAREER_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("CAREER_AGENT_LLM_MODEL", "test-model")
    monkeypatch.setenv("CAREER_AGENT_LLM_BASE_URL", "https://example.invalid/v1")
    provider = OpenAICompatibleProvider.from_env(env_file=None)
    assert provider.model == "test-model"


def test_provider_falls_back_to_plain_json_when_response_format_unavailable() -> None:
    class FakeCompletions:
        async def parse(self, **kwargs: object) -> object:
            raise RuntimeError("response_format type is unavailable now")

        async def create(self, **kwargs: object) -> object:
            content = """
            ```json
            {
              "resume_id": "resume-1",
              "version": "v1",
              "raw_text": "张三 Python 开发",
              "personal_info": {"name": "张三"},
              "skills": [
                {"name": "Python", "source_text": "Python 开发"}
              ]
            }
            ```
            """
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    provider = OpenAICompatibleProvider(api_key="test-key", model="test-model")
    provider._client = SimpleNamespace(  # noqa: SLF001
        chat=SimpleNamespace(completions=FakeCompletions())
    )

    resume = asyncio.run(
        provider.parse_resume(
            resume_id="resume-1",
            version="v1",
            raw_text="张三 Python 开发",
        )
    )

    assert resume.personal_info.name == "张三"
    assert [skill.name for skill in resume.skills] == ["Python"]


def test_deepseek_v4_flash_uses_json_object_mode() -> None:
    class FakeCompletions:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        async def parse(self, **kwargs: object) -> object:
            raise AssertionError("DeepSeek must not use OpenAI SDK Pydantic parse")

        async def create(self, **kwargs: object) -> object:
            self.request = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                '{"resume_id":"resume-1","version":"v1",'
                                '"raw_text":"张三 Python 开发",'
                                '"personal_info":{"name":"张三"},'
                                '"skills":[{"name":"Python",'
                                '"source_text":"Python 开发"}]}'
                            )
                        )
                    )
                ]
            )

    completions = FakeCompletions()
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )
    provider._client = SimpleNamespace(  # noqa: SLF001
        chat=SimpleNamespace(completions=completions)
    )

    resume = asyncio.run(
        provider.parse_resume(
            resume_id="resume-1",
            version="v1",
            raw_text="张三 Python 开发",
        )
    )

    assert resume.personal_info.name == "张三"
    assert completions.request is not None
    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert completions.request["max_tokens"] == 16384


def test_evidence_plain_json_accepts_top_level_list() -> None:
    result = _validate_plain_json(
        """
        [
          {
            "requirement_id": "req-1",
            "status": "STRONG_MATCH",
            "evidence_fact_ids": ["fact-1"],
            "reasoning_summary": "Python fact supports the requirement.",
            "confidence": 0.9
          }
        ]
        """,
        _EvidenceMatches,
    )

    assert result.items[0].status is EvidenceStatus.STRONG_MATCH


def test_provider_repairs_invalid_plain_json_once() -> None:
    class FakeCompletions:
        def __init__(self) -> None:
            self.create_calls = 0

        async def parse(self, **kwargs: object) -> object:
            raise RuntimeError("response_format type is unavailable now")

        async def create(self, **kwargs: object) -> object:
            self.create_calls += 1
            content = (
                '{"items":[{"requirement_id":"req-1","status":"STRONG_MATCH",'
                '"evidence_fact_ids":[],"reasoning_summary":"Supported","confidence":0.9}]}'
                if self.create_calls == 1
                else '{"items":[{"requirement_id":"req-1","status":"STRONG_MATCH",'
                '"evidence_fact_ids":["fact-1"],"reasoning_summary":"Supported",'
                '"confidence":0.9}]}'
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    completions = FakeCompletions()
    provider = OpenAICompatibleProvider(api_key="test-key", model="test-model")
    provider._client = SimpleNamespace(  # noqa: SLF001
        chat=SimpleNamespace(completions=completions)
    )

    result = asyncio.run(
        provider._parse(  # noqa: SLF001
            operation="match_evidence",
            system="Match evidence.",
            user="input",
            schema=_EvidenceMatches,
        )
    )

    assert result.items[0].evidence_fact_ids == ["fact-1"]
    assert completions.create_calls == 2


def test_provider_classifies_resume_image_with_multimodal_message() -> None:
    class FakeCompletions:
        def __init__(self) -> None:
            self.request: dict[str, object] | None = None

        async def create(self, **kwargs: object) -> object:
            self.request = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"kind":"resume_document","text":"张明 Python 开发"}'
                        )
                    )
                ]
            )

    completions = FakeCompletions()
    provider = OpenAICompatibleProvider(api_key="test-key", model="deepseek-v4-flash")
    provider._client = SimpleNamespace(  # noqa: SLF001
        chat=SimpleNamespace(completions=completions)
    )

    analysis = asyncio.run(
        provider.analyze_intake_image(data_url="data:image/png;base64,AA==")
    )

    assert analysis.kind == "resume_document"
    assert analysis.text == "张明 Python 开发"
    assert completions.request is not None
    messages = completions.request["messages"]
    assert isinstance(messages, list)
    assert messages[1]["content"][1]["type"] == "image_url"
