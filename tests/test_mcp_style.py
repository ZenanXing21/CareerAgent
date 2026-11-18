import asyncio
from contextlib import asynccontextmanager
import hashlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from career_agent.resume import mcp_style
from career_agent.web.app import create_app
from career_agent.web.workspace import WorkspaceStore


def test_mcp_url_rejects_local_and_non_https(monkeypatch) -> None:
    monkeypatch.setattr(mcp_style.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))])
    with pytest.raises(ValueError):
        mcp_style.validate_mcp_url("https://example.com/mcp")
    with pytest.raises(ValueError):
        mcp_style.validate_mcp_url("http://example.com/mcp")


def test_mcp_tool_runs_only_on_explicit_import(monkeypatch) -> None:
    calls = []

    class FakeClient:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="style", description="Design style", inputSchema={"type": "object"})])

        async def list_resources(self):
            return SimpleNamespace(resources=[])

        async def call_tool(self, name, arguments, read_timeout_seconds):
            calls.append((name, arguments))
            return SimpleNamespace(is_error=False, content=[SimpleNamespace(text="Use clear headings and wide spacing")], structured_content=None)

    @asynccontextmanager
    async def fake_client(url, token):
        yield FakeClient()

    monkeypatch.setattr(mcp_style, "_client", fake_client)
    sources = asyncio.run(mcp_style.list_style_sources("https://example.com/mcp", None))
    assert sources[0]["name"] == "style"
    assert not calls
    content = asyncio.run(mcp_style.import_style_source("https://example.com/mcp", None, "tool", "style", {}))
    assert calls == [("style", {})]
    assert "wide spacing" in content


def test_mcp_import_creates_persistent_style_skill(tmp_path, monkeypatch) -> None:
    async def fake_sources(url, token):
        return [{"kind": "tool", "name": "style", "description": "", "input_schema": {}}]

    async def fake_import(url, token, kind, name, arguments):
        return "# style\n\nUse generous whitespace and clear section headings."

    monkeypatch.setattr(mcp_style, "list_style_sources", fake_sources)
    monkeypatch.setattr(mcp_style, "import_style_source", fake_import)
    state_file = tmp_path / "workspace.json"
    key = "test-workspace-key-for-mcp-style-import"
    headers = {"X-Workspace-Key": key}
    client = TestClient(create_app(state_file=state_file))
    found = client.post("/api/design/mcp/sources", json={"url": "https://example.com/mcp"}, headers=headers)
    assert found.status_code == 200
    assert found.json()["sources"][0]["name"] == "style"
    installed = client.post("/api/design/mcp/import", json={
        "url": "https://example.com/mcp", "kind": "tool", "name": "style", "arguments": {},
    }, headers=headers)
    assert installed.status_code == 200
    owner = hashlib.sha256(key.encode()).hexdigest()
    saved = WorkspaceStore(state_file).load().installed_style_skills[owner]
    assert saved[0]["id"] == installed.json()["id"]
    assert "generous whitespace" in saved[0]["content"]
