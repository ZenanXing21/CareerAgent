from io import BytesIO

import pytest

from career_agent.resume.skill_install import github_skill_text
from career_agent.resume.studio import explicit_design_context
from career_agent.web.workspace import WorkspaceStore


class _Opener:
    def __init__(self):
        self.url = ""

    def open(self, request, timeout):
        self.url = request.full_url
        return BytesIO(b"# Style\nUse generous whitespace and clear headings.")


def test_github_skill_folder_installs_only_skill_markdown(monkeypatch) -> None:
    opener = _Opener()
    monkeypatch.setattr("career_agent.resume.skill_install.build_opener", lambda *_: opener)
    name, content = github_skill_text("https://github.com/example/resume/tree/main/skills/calm")
    assert name == "calm"
    assert opener.url == "https://raw.githubusercontent.com/example/resume/main/skills/calm/SKILL.md"
    assert "generous whitespace" in content


def test_installed_skill_is_selectable_and_other_hosts_are_rejected() -> None:
    context = explicit_design_context(["installed-1"], [{"id": "installed-1", "name": "Calm", "content": "Use generous whitespace."}])
    assert "Use generous whitespace" in context
    with pytest.raises(ValueError):
        github_skill_text("https://example.com/private/SKILL.md")


def test_installed_skills_survive_workspace_reload(tmp_path) -> None:
    store = WorkspaceStore(tmp_path / "workspace.json")
    installed = {"owner-1": [{"id": "installed-1", "name": "Calm", "content": "Use generous whitespace."}]}
    store.write(store.snapshot({}, {}, installed_style_skills=installed))
    assert store.load().installed_style_skills == installed
