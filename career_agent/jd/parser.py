"""One-call structured JD parsing with source-bound keyword validation."""

from __future__ import annotations

import re
import unicodedata

from pydantic import ValidationError

from career_agent.jd.models import JDAnalysis
from career_agent.llm.base import LLMError, LLMProvider, LLMProviderError, StructuredOutputError


def _normalized_source_fragment(value: str) -> str:
    """Normalize harmless presentation differences without erasing semantics."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[、,，;；|｜/／]", "/", normalized)
    return re.sub(r"[‐‑‒–—―]", "-", normalized)


def _keyword_is_traceable(keyword: str, source_text: str) -> bool:
    return _normalized_source_fragment(keyword) in _normalized_source_fragment(source_text)


class JDParser:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def parse(self, *, job_id: str, source_text: str) -> JDAnalysis:
        try:
            parsed = await self._provider.parse_jd(job_id=job_id, source_text=source_text)
        except LLMError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise StructuredOutputError("JD provider returned invalid structured output") from exc
        except Exception as exc:
            raise LLMProviderError("JD parsing provider call failed") from exc
        if not isinstance(parsed, JDAnalysis):
            raise StructuredOutputError("JD provider did not return a JDAnalysis")
        if parsed.job_id != job_id or parsed.source_text != source_text:
            raise StructuredOutputError("JD output does not match the requested job/source")

        payload = parsed.model_dump()
        for index, requirement in enumerate(payload["requirements"], start=1):
            requirement["id"] = f"req_{index:03d}"
            # A model may normalize spacing or punctuation even when the keyword is
            # grounded in the JD. Keep traceable keywords and discard hallucinated
            # ones instead of failing the entire tailoring workflow.
            requirement["keywords"] = [
                keyword
                for keyword in requirement["keywords"]
                if _keyword_is_traceable(keyword, source_text)
            ]
        try:
            return JDAnalysis.model_validate(payload)
        except ValidationError as exc:
            raise StructuredOutputError("JD output failed domain validation") from exc
