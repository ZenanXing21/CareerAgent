from __future__ import annotations

import asyncio
import importlib
import re

import httpx


def test_configuration_loads_from_project_file_when_shell_directory_changes(
    monkeypatch, tmp_path
) -> None:
    web = importlib.import_module("career_agent.web.app")
    config = tmp_path / "project.env"
    config.write_text(
        "CAREER_AGENT_LLM_API_KEY=test-key\n"
        "CAREER_AGENT_LLM_MODEL=test-model\n"
        "LIEPIN_MCP_USER_TOKEN=test-token\n",
        encoding="utf-8",
    )
    other_directory = tmp_path / "other"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)
    monkeypatch.setattr(web, "ENV_FILE", config, raising=False)
    for key in ("CAREER_AGENT_LLM_API_KEY", "CAREER_AGENT_LLM_MODEL", "LIEPIN_MCP_USER_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    application = web.create_app()

    async def check_status() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.get("/api/status")
        assert response.status_code == 200
        assert response.json() == {"ready": True, "model": "test-model", "liepin": True}
        assert "test-key" not in response.text
        assert "test-token" not in response.text

    asyncio.run(check_status())


def test_page_and_assets_are_revalidated_and_asset_urls_identify_current_release() -> None:
    web = importlib.import_module("career_agent.web.app")
    application = web.create_app()

    async def check_page() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            page = await client.get("/")
            assert page.status_code == 200
            assert page.headers.get("cache-control") == "no-store"
            assets = re.findall(r'(?:href|src)="(static/[^"?]+\?v=[a-f0-9]{12})"', page.text)
            assert len(assets) == 4
            for url in assets:
                asset = await client.get("/" + url)
                assert asset.status_code == 200
                assert asset.headers.get("cache-control") == "no-store"
                assert asset.content

    asyncio.run(check_page())


def test_proxy_prefix_keeps_assets_under_career_agent_without_trailing_slash() -> None:
    web = importlib.import_module("career_agent.web.app")
    application = web.create_app()

    async def check_page() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client:
            page = await client.get("/", headers={"X-Forwarded-Prefix": "/CareerAgent"})
        assert page.status_code == 200
        assert '<base href="/CareerAgent/">' in page.text
        assert 'href="static/styles.css?v=' in page.text

    asyncio.run(check_page())
