"""Read a style SKILL.md from a narrowly scoped GitHub URL."""

from __future__ import annotations

import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("Skill 链接发生跳转，请使用 GitHub 上的 SKILL.md 直达链接")


def github_skill_text(url: str) -> tuple[str, str]:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ValueError("请使用 GitHub 的 HTTPS Skill 链接")
    parts = [part for part in parsed.path.split("/") if part]
    refs = None
    if parsed.hostname == "github.com" and len(parts) == 2:
        owner, repo = parts
        ref, path = "main", ["SKILL.md"]
        refs = ("main", "master")
    elif parsed.hostname == "github.com" and len(parts) >= 4 and parts[2] in {"blob", "tree"}:
        owner, repo, _, ref, *path = parts
        if parts[2] == "tree" or not path or path[-1].lower() != "skill.md":
            path.append("SKILL.md")
    elif parsed.hostname == "raw.githubusercontent.com" and len(parts) >= 4:
        owner, repo, ref, *path = parts
        if not path or path[-1].lower() != "skill.md":
            path.append("SKILL.md")
    else:
        raise ValueError("请粘贴 GitHub 仓库中 SKILL.md 文件或所在文件夹的链接")
    segments = [owner, repo, ref, *path]
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in {".", ".."} for part in segments):
        raise ValueError("Skill 链接路径无效")
    data = None
    for branch in refs or (ref,):
        raw_url = "https://raw.githubusercontent.com/" + "/".join([owner, repo, branch, *path])
        request = Request(raw_url, headers={"User-Agent": "CareerAgent-Skill-Installer/1.0"})
        try:
            with build_opener(_NoRedirect).open(request, timeout=12) as response:
                data = response.read(20_001)
            break
        except Exception:
            continue
    if data is None:
        raise ValueError("无法读取 GitHub Skill 文件，请检查链接是否公开且可访问")
    if len(data) > 20_000:
        raise ValueError("Skill 文件不能超过 20 KB")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Skill 文件必须是 UTF-8 文本") from exc
    if len(content.strip()) < 20:
        raise ValueError("Skill 文件内容太短")
    name = path[-2] if len(path) > 1 else repo
    return name[:60], content
