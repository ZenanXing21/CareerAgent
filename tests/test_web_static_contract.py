from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

STATIC_ROOT = Path(__file__).parents[1] / "career_agent" / "web" / "static"


class _Markup(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.feed(source)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def by_id(self, element_id: str) -> tuple[str, dict[str, str | None]]:
        return next(element for element in self.elements if element[1].get("id") == element_id)

    def with_class(self, class_name: str) -> list[tuple[str, dict[str, str | None]]]:
        return [
            element
            for element in self.elements
            if class_name in (element[1].get("class") or "").split()
        ]


def _page() -> _Markup:
    return _Markup((STATIC_ROOT / "index.html").read_text(encoding="utf-8"))


def test_responsive_shell_exposes_accessible_desktop_and_mobile_navigation() -> None:
    page = _page()

    assert page.with_class("app-rail")
    assert page.by_id("mobile-topbar")[0] == "header"

    _, toggle = page.by_id("mobile-nav-toggle")
    assert toggle["aria-controls"] == "mobile-nav-sheet"
    assert toggle["aria-expanded"] == "false"
    assert toggle["aria-label"]

    _, sheet = page.by_id("mobile-nav-sheet")
    assert sheet["aria-hidden"] == "true"
    assert sheet["aria-label"]
    assert page.by_id("mobile-nav-close")[1]["aria-label"]
    assert page.by_id("mobile-nav-backdrop")[1]["aria-hidden"] == "true"

    steps = page.with_class("step")
    assert {attrs.get("data-view") for _, attrs in steps} == {
        "profile",
        "jobs",
        "result",
        "interview",
    }
    active = [attrs for _, attrs in steps if attrs.get("aria-current") == "page"]
    assert len(active) == 1
    assert active[0]["data-view"] == "profile"


def test_responsive_shell_keeps_business_critical_entry_points() -> None:
    page = _page()

    for element_id in (
        "intake-chat-form",
        "intake-files",
        "intake-input",
        "chat-resume-preview",
        "resume-editor",
        "resume-agent-form",
        "job-search-form",
        "job-list",
        "job-detail",
        "analysis-requirements",
    ):
        page.by_id(element_id)


def test_styles_define_the_doubao_calm_tokens_and_responsive_safety_rules() -> None:
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    for token in (
        "--surface-page",
        "--surface-card",
        "--ink-strong",
        "--ink-muted",
        "--accent",
        "--border",
        "--danger",
        "--warning",
        "--rail-width: 72px",
        "--topbar-height: 56px",
    ):
        assert token in styles

    assert "@media (max-width: 1023px)" in styles
    assert "--rail-width: 64px" in styles
    assert "@media (max-width: 760px)" in styles
    assert ":focus-visible" in styles
    assert "min-height: 44px" in styles
    assert "@media (prefers-reduced-motion: reduce)" in styles


def test_intake_starts_as_a_quiet_conversation_with_progressive_disclosure() -> None:
    page = _page()
    source = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert page.by_id("intake-hero")
    assert "今天想从哪里开始？" in source
    prompts = {attrs.get("data-prompt") for _, attrs in page.with_class("quick-prompt")}
    assert prompts == {"帮我从零生成简历", "帮我修改我的简历", None}
    assert page.by_id("intake-upload-prompt")[0] == "button"

    _, summary_toggle = page.by_id("intake-summary-toggle")
    assert summary_toggle["aria-controls"] == "intake-summary-body"
    assert summary_toggle["aria-expanded"] == "false"
    assert page.by_id("intake-summary-body")

    assert page.by_id("intake-files")[0] == "input"
    assert page.by_id("intake-input")[0] == "textarea"
    submit_buttons = [
        attrs
        for tag, attrs in page.elements
        if tag == "button"
        and attrs.get("type") == "submit"
        and "composer-send" in (attrs.get("class") or "")
    ]
    assert submit_buttons


def test_resume_editor_offers_mobile_modes_and_accessible_section_reordering() -> None:
    page = _page()
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    _, edit_mode = page.by_id("resume-mobile-edit")
    _, preview_mode = page.by_id("resume-mobile-preview")
    assert edit_mode["aria-controls"] == "resume-edit-pane"
    assert edit_mode["aria-selected"] == "true"
    assert preview_mode["aria-controls"] == "resume-mobile-preview-pane"
    assert preview_mode["aria-selected"] == "false"
    assert page.by_id("resume-mobile-preview-canvas")

    assert "function setResumeMobileMode(" in script
    assert "function moveResumeSection(" in script
    assert 'data-move-section="${key}"' in script
    assert "上移${escapeHtml(title)}" in script
    assert "下移${escapeHtml(title)}" in script


def test_jobs_and_tailored_results_use_progressive_disclosure_on_small_screens() -> None:
    page = _page()
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    _, filter_toggle = page.by_id("job-filter-toggle")
    assert filter_toggle["aria-controls"] == "job-extra-filters"
    assert filter_toggle["aria-expanded"] == "false"
    assert "hidden" in (page.by_id("job-extra-filters")[1].get("class") or "").split()

    _, detail_back = page.by_id("mobile-job-detail-back")
    assert detail_back["aria-label"]
    assert page.by_id("job-detail-content")
    assert "function setJobFiltersExpanded(" in script
    assert "function setMobileJobDetail(" in script

    assert page.by_id("score-card")[0] == "details"
    assert page.by_id("analysis-requirements")
    assert page.by_id("copy-job-jd")
    assert page.by_id("view-interview")


def test_mobile_composer_does_not_show_scroll_controls_before_typing() -> None:
    page = _page()
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "直接说你的情况" in page.by_id("intake-input")[1]["placeholder"]
    assert "overflow-y: hidden" in styles


def test_verified_job_reopens_without_staying_in_loading_state() -> None:
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert (
        "if (summary.detail_verified) { renderJobDetail(summary, false); return; }"
        in script
    )


def test_navigation_availability_is_updated_for_desktop_and_mobile() -> None:
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "function setStepDisabled(" in script
    assert "setStepDisabled(\"jobs\", true)" in script
    assert "setStepDisabled(\"jobs\", false)" in script
    assert "setStepDisabled(\"resume\", false)" in script


def test_conversation_and_resume_mobile_layouts_can_shrink_without_overflow() -> None:
    page = _page()
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    assert page.by_id("intake-scroll-region")
    assert ".intake-scroll-region {" in styles
    assert "min-height: 0" in styles
    assert ".intake-summary > .intake-summary-body { display: block;" in styles
    assert ".template-list { grid-template-columns: repeat(3, minmax(0, 1fr));" in styles


def test_upload_controls_remain_keyboard_accessible_after_conversation_starts() -> None:
    page = _page()
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (STATIC_ROOT / "styles.css").read_text(encoding="utf-8")

    for element_id in ("intake-files-label", "template-upload-label"):
        _, attrs = page.by_id(element_id)
        assert attrs["role"] == "button"
        assert attrs["tabindex"] == "0"
    assert "function bindKeyboardFilePicker(" in script
    assert ".upload-queue button { min-width: 44px;" in styles


def test_mobile_navigation_behaves_like_a_modal_and_resets_on_desktop_resize() -> None:
    script = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'shell.inert = open' in script
    assert 'event.key === "Tab"' in script
    assert 'setMobileNav(false)' in script
    assert 'window.matchMedia("(max-width: 760px)").matches' in script
