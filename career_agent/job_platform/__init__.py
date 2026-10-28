"""Job-platform adapters, MCP tools, and the Career Agent client boundary."""

from career_agent.job_platform.adapters import (
    AdapterNotImplemented,
    AdapterUnavailable,
    BossAdapter,
    FallbackJobPlatformAdapter,
    JobPlatformAdapter,
    LiepinAdapter,
    MockAdapter,
    ZhilianAdapter,
)
from career_agent.job_platform.client import MCPJobPlatformClient, MCPJobPlatformError
from career_agent.job_platform.external_mcp import ExternalMCPAdapter
from career_agent.job_platform.liepin_cli import LiepinCLIAdapter
from career_agent.job_platform.liepin_mcp import LiepinMCPAdapter
from career_agent.job_platform.public_ats import (
    GreenhouseAdapter,
    LeverAdapter,
    PublicATSAdapter,
    SmartRecruitersAdapter,
)
from career_agent.job_platform.server import JobPlatformRegistry, create_job_platform_server

__all__ = [
    "AdapterNotImplemented",
    "AdapterUnavailable",
    "BossAdapter",
    "ExternalMCPAdapter",
    "FallbackJobPlatformAdapter",
    "JobPlatformAdapter",
    "JobPlatformRegistry",
    "GreenhouseAdapter",
    "LiepinAdapter",
    "LiepinCLIAdapter",
    "LiepinMCPAdapter",
    "LeverAdapter",
    "MCPJobPlatformClient",
    "MCPJobPlatformError",
    "MockAdapter",
    "PublicATSAdapter",
    "SmartRecruitersAdapter",
    "ZhilianAdapter",
    "create_job_platform_server",
]
