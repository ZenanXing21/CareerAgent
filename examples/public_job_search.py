"""Search one configured public company ATS without a browser or model call."""

from __future__ import annotations

import argparse
import asyncio

from career_agent import (
    GreenhouseAdapter,
    JobSearchQuery,
    LeverAdapter,
    SmartRecruitersAdapter,
)


async def main(args: argparse.Namespace) -> None:
    adapters = {
        "greenhouse": GreenhouseAdapter,
        "lever": LeverAdapter,
        "smartrecruiters": SmartRecruitersAdapter,
    }
    adapter = adapters[args.provider]({args.company: args.slug})
    jobs = await adapter.search_jobs(
        JobSearchQuery(
            keyword=args.keyword,
            city=args.city,
            company_names=[args.company],
            preferred_keywords=args.preference,
        )
    )
    print(f"找到 {len(jobs)} 个岗位")
    for job in jobs:
        print(f"\n{job.title} @ {job.company} ({job.location})")
        print(f"岗位ID：{job.id}")
        print(f"投递链接：{job.apply_url or job.source_url or '未提供'}")
        print(f"JD：{(job.detail_text or '未提供')[:300]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider", choices=["greenhouse", "lever", "smartrecruiters"], required=True
    )
    parser.add_argument("--company", required=True, help="展示用公司名称")
    parser.add_argument("--slug", required=True, help="ATS 中的公司/board 标识")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--city", default="不限")
    parser.add_argument("--preference", action="append", default=[])
    asyncio.run(main(parser.parse_args()))
