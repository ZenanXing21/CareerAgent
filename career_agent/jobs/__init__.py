"""Job-search domain API."""

from career_agent.jobs.matcher import calculate_match
from career_agent.jobs.models import Job, JobSearchQuery, MatchResult

__all__ = ["Job", "JobSearchQuery", "MatchResult", "calculate_match"]
