"""Explicitly import a public MCP tool result or text resource as style guidance."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import ipaddress
import json
import socket
from urllib.parse import urlsplit

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client


def validate_mcp_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("MCP 服务器必须使用公开的 HTTPS 地址")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("无法解析 MCP 服务器地址") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("不允许连接本机或内网 MCP 服务器")
    return url.strip()


@asynccontextmanager
async def _client(url: str, token: str | None):
    url = await asyncio.to_thread(validate_mcp_url, url)
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with (
        create_mcp_http_client(headers=headers) as http_client,
        streamable_http_client(url, http_client=http_client) as streams,
        Client(streams, read_timeout_seconds=15) as client,
    ):
        yield client


async def list_style_sources(url: str, token: str | None) -> list[dict[str, object]]:
    async def collect():
        async with _client(url, token) as client:
            tools = await client.list_tools()
            result = [
                {"kind": "tool", "name": item.name, "description": item.description or "", "input_schema": item.inputSchema}
                for item in tools.tools
            ]
            try:
                resources = await client.list_resources()
                result.extend(
                    {"kind": "resource", "name": str(item.uri), "description": item.description or item.name or "", "input_schema": {}}
                    for item in resources.resources
                )
            except Exception:
                pass
            return result[:100]
    return await asyncio.wait_for(collect(), timeout=25)


async def import_style_source(url: str, token: str | None, kind: str, name: str, arguments: dict) -> str:
    async def collect():
        async with _client(url, token) as client:
            if kind == "tool":
                available = await client.list_tools()
                if name not in {item.name for item in available.tools}:
                    raise ValueError("MCP 服务器没有这个工具")
                result = await client.call_tool(name, arguments, read_timeout_seconds=15)
                if result.is_error:
                    raise ValueError("MCP 工具返回了错误")
                parts = [getattr(item, "text", "") for item in result.content]
                if result.structured_content:
                    parts.append(json.dumps(result.structured_content, ensure_ascii=False))
            elif kind == "resource":
                available = await client.list_resources()
                if name not in {str(item.uri) for item in available.resources}:
                    raise ValueError("MCP 服务器没有这个资源")
                result = await client.read_resource(name)
                parts = [getattr(item, "text", "") for item in result.contents]
            else:
                raise ValueError("不支持的 MCP 内容类型")
            content = "\n\n".join(part for part in parts if isinstance(part, str) and part.strip())
            if not 20 <= len(content) <= 20_000:
                raise ValueError("MCP 输出需要是 20 KB 以内的文本")
            return f"# {name}\n\n{content}"
    return await asyncio.wait_for(collect(), timeout=30)
