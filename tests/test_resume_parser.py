import asyncio

import pytest

from career_agent import (
    Education,
    ExperienceType,
    PersonalInfo,
    Resume,
    ResumeParser,
    StructuredOutputError,
    WorkExperience,
)


class ResumeProvider:
    def __init__(self, output: Resume) -> None:
        self.output = output
        self.calls = 0

    async def parse_resume(self, **_: object) -> Resume:
        self.calls += 1
        return self.output


def test_resume_parser_calls_once_and_normalizes_identity_and_ids() -> None:
    raw = "张三 张三@example.com 甲大学。甲公司工程师。乙公司实习生。"
    provider = ResumeProvider(
        Resume(
            resume_id="model-id",
            version="model-version",
            raw_text="model text",
            personal_info=PersonalInfo(name="张三", email="张三@example.com"),
            educations=[Education(id="x", source_text="甲大学。", school="甲大学")],
            work_experiences=[
                WorkExperience(
                    id="y",
                    source_text="甲公司工程师。",
                    experience_type=ExperienceType.WORK,
                )
            ],
            internships=[
                WorkExperience(
                    id="z",
                    source_text="乙公司实习生。",
                    experience_type=ExperienceType.INTERNSHIP,
                )
            ],
        )
    )
    parsed = asyncio.run(
        ResumeParser(provider).parse(resume_id="resume-1", version="v1", raw_text=raw)
    )
    assert provider.calls == 1
    assert (parsed.resume_id, parsed.version, parsed.raw_text) == ("resume-1", "v1", raw)
    assert parsed.educations[0].id == "edu_001"
    assert parsed.work_experiences[0].id == "work_001"
    assert parsed.internships[0].id == "intern_001"


def test_resume_parser_rejects_fabricated_source_text() -> None:
    provider = ResumeProvider(
        Resume(
            resume_id="x",
            version="x",
            raw_text="x",
            educations=[Education(id="x", source_text="不存在的学校")],
        )
    )
    with pytest.raises(StructuredOutputError, match="source_text"):
        asyncio.run(ResumeParser(provider).parse(resume_id="r", version="v", raw_text="张三"))


def test_resume_parser_rejects_fabricated_entity_inside_real_source_text() -> None:
    provider = ResumeProvider(
        Resume(
            resume_id="x",
            version="x",
            raw_text="甲公司工程师。",
            work_experiences=[
                WorkExperience(
                    id="x",
                    source_text="甲公司工程师。",
                    experience_type=ExperienceType.WORK,
                    company="虚构公司",
                    title="工程师",
                )
            ],
        )
    )
    with pytest.raises(StructuredOutputError, match="company"):
        asyncio.run(
            ResumeParser(provider).parse(
                resume_id="resume-1", version="v1", raw_text="甲公司工程师。"
            )
        )
