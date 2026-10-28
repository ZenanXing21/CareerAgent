"""Read-only search through Liepin's hosted MCP server."""

from __future__ import annotations

import argparse
import asyncio

from dotenv import load_dotenv

from career_agent import JobSearchQuery, LiepinMCPAdapter


async def main(args: argparse.Namespace) -> None:
    load_dotenv()
    adapter = LiepinMCPAdapter.from_env()
    jobs = await adapter.search_jobs(
        JobSearchQuery(
            keyword=args.keyword,
            city=args.city,
            salary_min=args.salary_min,
            company_names=[args.company] if args.company else [],
            experience_levels=[args.experience] if args.experience else [],
        )
    )
    print(f"找到 {len(jobs)} 个猎聘岗位")
    for job in jobs[: args.limit]:
        if args.details:
            job = await adapter.get_job_detail(job.id)
        print(f"\n{job.title} @ {job.company} ({job.location})")
        print(f"薪资：{job.salary_text or '未注明'}")
        print(f"JD完整：{job.detail_verified}")
        print(f"详情/投递链接：{job.apply_url or job.source_url or '未提供'}")
        if args.details:
            print(f"JD：\n{job.detail_text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--city", default="不限")
    parser.add_argument("--salary-min", type=int)
    parser.add_argument("--company")
    parser.add_argument("--experience")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    asyncio.run(main(parser.parse_args()))
