# Career Agent Doubao Calm Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Career Agent 前端重构为用户已选定的「静谧对话 · Doubao Calm」桌面/手机双端界面，同时完整保留对话建档、简历编辑与下载、猎聘岗位搜索、定制简历及投递准备业务。

**Architecture:** 保持 FastAPI + 原生 HTML/CSS/JavaScript 架构，不更改后端 API 和会话数据格式。页面继续使用单页四视图，但新增一个统一的响应式应用外壳：桌面/平板使用窄图标栏，手机使用顶部栏和导航 sheet；各业务视图在同一状态对象与现有事件绑定上渐进增强。UI 状态只保存在 DOM 和现有 `state` 对象中，不新增服务器持久化字段。

**Tech Stack:** Python 3、FastAPI、pytest、原生 HTML5、CSS 自定义属性与媒体查询、原生 JavaScript、内联 SVG。

**Spec:** `docs/superpowers/specs/2026-10-26-career-agent-doubao-calm-design.md`

---

## Global constraints

- 保留所有现有后端端点、请求/响应结构和模型调用逻辑。
- 尽量保留现有 DOM `id`、`data-view`、表单名称和事件入口，避免功能回归。
- 不引入 React/Vue、构建工具、CDN、远程字体或运行时依赖。
- 使用项目本地系统字体与内联 SVG；不复制豆包、BOSS 或猎聘的商标与品牌素材。
- 新用户仍进入对话建档；已有简历的用户刷新后仍恢复到初版简历页。
- 桌面端与手机端共享一份简历数据；手机 A4 页面预览只读，响应式内容流是唯一移动编辑入口。
- 所有图标按钮至少 44×44px，具备可见焦点、`aria-label` 或 tooltip；状态不能只依靠颜色表达。
- 320px–1440px 不出现页面级横向滚动；支持 `prefers-reduced-motion`。
- 所有行为变更先写失败的回归测试，再写最小实现。

## File map

| File | Responsibility |
|---|---|
| `career_agent/web/static/index.html` | 应用壳、桌面图标导航、手机导航 sheet、四个业务视图的语义结构与无障碍控件 |
| `career_agent/web/static/styles.css` | 设计 token、全局响应式布局、对话首页、简历/岗位/结果页和状态反馈样式 |
| `career_agent/web/static/app.js` | 视图状态、移动菜单、对话状态、简历移动预览与模块排序、岗位移动详情和筛选抽屉 |
| `tests/test_web_app.py` | 页面静态契约、现有入口和恢复能力的后端集成回归 |
| `tests/test_web_static_contract.py` | HTML/CSS/JS 响应式与无障碍结构的轻量静态回归测试 |

## Task 1: Lock the responsive shell and accessibility contract

**Files:**
- Create: `tests/test_web_static_contract.py`
- Modify: `career_agent/web/static/index.html`
- Modify: `career_agent/web/static/app.js`
- Test: `tests/test_web_static_contract.py`
- Test: `tests/test_web_app.py`

**Interfaces:**
- `showView(name: "profile" | "resume" | "jobs" | "result")`
- New `setMobileNav(open: boolean): void`
- New `syncShellState(viewName: string): void`
- DOM contract: `#mobile-nav-toggle`, `#mobile-nav-sheet`, `#mobile-nav-close`, `#mobile-nav-backdrop`, `.app-rail`, `.step[data-view]`

- [ ] Add a failing test that reads the served page and requires the new narrow app rail, mobile top bar, labelled navigation toggle/sheet, close button, backdrop, current-page semantics, and all existing business-critical IDs (`intake-chat-form`, `resume-editor`, `job-search-form`, `tailored-sections`).
- [ ] Run `python -m pytest tests/test_web_static_contract.py tests/test_web_app.py -q` and confirm the new contract test fails because the shell controls do not exist.
- [ ] Replace the full-width text sidebar in `index.html` with a 72px icon rail using inline SVG, retaining `.step` and `data-view` on each navigation button. Add hidden tooltip labels and `aria-current="page"` support.
- [ ] Add the 56px mobile brand bar and modal-like navigation sheet. Use semantic buttons, `aria-controls`, `aria-expanded`, `aria-hidden`, and a labelled navigation region.
- [ ] Implement `setMobileNav(open)` to synchronize sheet visibility, backdrop, `aria-expanded`, body scroll lock, focus placement, backdrop click, close click, and Escape handling.
- [ ] Update `showView(name)` to call `syncShellState(name)`, update both desktop and mobile titles, set `aria-current`, close the mobile sheet, and preserve existing view switching.
- [ ] Keep `restoreResumeSession()` behavior unchanged: a found server-side session unlocks navigation, renders the current resume, and calls `showView("resume")`; a 404 remains a valid first-visit state.
- [ ] Run the focused tests and `node --check career_agent/web/static/app.js`; confirm both pass.
- [ ] Checkpoint commit: `git add career_agent/web/static/index.html career_agent/web/static/app.js tests/test_web_app.py tests/test_web_static_contract.py && git commit -m "feat: add responsive career agent shell"`.

## Task 2: Apply the Doubao Calm visual system and responsive layout

**Files:**
- Modify: `career_agent/web/static/styles.css`
- Modify: `career_agent/web/static/index.html`
- Modify: `tests/test_web_static_contract.py`
- Test: `tests/test_web_static_contract.py`

**Interfaces:**
- CSS tokens: `--surface-page`, `--surface-card`, `--ink-strong`, `--ink-muted`, `--accent`, `--border`, `--danger`, `--warning`, `--rail-width`, `--topbar-height`
- Breakpoints: desktop `>=1024px`, compact rail `761px–1023px`, mobile `<=760px`

- [ ] Add failing static tests for the required semantic CSS variables, 72px/64px rail tokens, the `760px` mobile breakpoint, `prefers-reduced-motion`, visible `:focus-visible` rules, and a 44px minimum interactive target declaration.
- [ ] Run the static contract test and confirm it fails on the missing design system.
- [ ] Rebuild the root tokens around the approved palette (`#FAF9F6`, `#14283B`, `#667788`, `#0F8F78`, `#DCE4E7`) and system font stack.
- [ ] Implement the desktop 72px rail + 56px top bar + fluid workspace. At 761–1023px use the 64px rail and collapse two-column workspaces. At 760px and below remove the rail, fix the mobile top bar, and reserve safe space for fixed controls.
- [ ] Replace heavy shadows, thick panels, and oversized headings with 18px cards, quiet borders, restrained shadows, and the approved 8px spacing rhythm.
- [ ] Add high-contrast focus rings, disabled states with text/ARIA support, tooltip styles, error/warning states, and reduced-motion overrides.
- [ ] Verify CSS has no external URL imports or new dependencies.
- [ ] Run `python -m pytest tests/test_web_static_contract.py -q`; confirm the token/layout contract passes.
- [ ] Checkpoint commit: `git add career_agent/web/static/index.html career_agent/web/static/styles.css tests/test_web_static_contract.py && git commit -m "style: apply doubao calm responsive system"`.

## Task 3: Turn the intake page into the selected conversational first screen

**Files:**
- Modify: `career_agent/web/static/index.html`
- Modify: `career_agent/web/static/styles.css`
- Modify: `career_agent/web/static/app.js`
- Modify: `tests/test_web_static_contract.py`
- Test: `tests/test_web_static_contract.py`

**Interfaces:**
- New `setConversationStarted(started: boolean): void`
- Existing `renderIntakeMessage(role, content)`
- Existing `renderIntakeSummary(draft, hasPhoto = false)`
- Existing `renderUploadQueue()`
- Existing `sendIntakeTurn({message = "", generate = false} = {})`
- DOM contract: `#intake-hero`, `#intake-summary-toggle`, `#intake-summary-body`, existing `#intake-input`, `#intake-files`, `#generate-from-chat`, `#chat-resume-preview`

- [ ] Add failing static tests for the approved hero copy (“今天想从哪里开始？”), three quick actions (“从零生成简历”“优化已有简历”“上传简历或照片”), a collapsible collected-data summary, and the existing horizontal composer controls.
- [ ] Run the focused test and confirm it fails on the old card-first layout.
- [ ] Restructure `#view-profile` into a centered 760px conversation stage without changing the existing form/input/upload/preview IDs.
- [ ] Implement `setConversationStarted(started)` using a view class/data attribute. Trigger it when a user sends text, uploads a file, receives restored chat content, or a generated preview is rendered; keep the quiet hero visible only before the first real interaction.
- [ ] Make `renderIntakeMessage()` preserve `aria-live`, use constrained message widths, and scroll only the conversation region rather than the whole page.
- [ ] Change `renderIntakeSummary()` to populate `#intake-summary-body` and update a collapsed label such as “已整理 N 项资料”; add accessible expand/collapse behavior without discarding any collected values.
- [ ] Keep upload removal behavior, Enter-to-send, Shift+Enter-to-newline, request disabling, generated preview, and “进入初版简历精修” gating intact.
- [ ] On mobile keep attachment, auto-growing textarea, and send button in one horizontal composer row; add bottom safe-area padding so the last message remains visible.
- [ ] Run the static tests, `tests/test_web_app.py`, and `node --check career_agent/web/static/app.js`.
- [ ] Checkpoint commit: `git add career_agent/web/static/index.html career_agent/web/static/styles.css career_agent/web/static/app.js tests/test_web_static_contract.py && git commit -m "feat: redesign conversational intake experience"`.

## Task 4: Make resume editing responsive and section movement reliable

**Files:**
- Modify: `career_agent/web/static/index.html`
- Modify: `career_agent/web/static/styles.css`
- Modify: `career_agent/web/static/app.js`
- Modify: `tests/test_web_static_contract.py`
- Test: `tests/test_web_static_contract.py`

**Interfaces:**
- New `setResumeMobileMode(mode: "edit" | "preview"): void`
- New `moveResumeSection(sectionKey: string, direction: -1 | 1): void`
- Existing `sectionBlock(key, content)`
- Existing `renderResumeEditor()`
- Existing `syncSectionOrderFromCanvas()`
- Existing `bindResumeInteractions()`
- DOM contract: `#resume-mobile-edit`, `#resume-mobile-preview`, `#resume-editor`, existing template/download/confirm controls

- [ ] Add failing contract tests for mobile edit/preview toggles and per-section “上移/下移” buttons with explicit accessible names.
- [ ] Run the test and confirm the controls are absent.
- [ ] Add a compact mobile mode switch above the resume stage. `setResumeMobileMode("edit")` displays the responsive editable flow; `"preview"` displays the same resume state in a read-only A4-style preview. Desktop keeps the current A4 editor and sidebar/workbench.
- [ ] Extend `sectionBlock()` with a dedicated title drag handle plus up/down buttons. Implement `moveResumeSection()` by changing `state.sectionOrder`, rerendering, and scheduling the existing save endpoint.
- [ ] Keep desktop drag-and-drop but fix both directions by computing the target insertion index from the original order before DOM mutation; do not repeatedly reorder during ambiguous edge positions.
- [ ] Ensure keyboard/touch users can reorder every visible section without drag; disable “上移” on the first section and “下移” on the last section.
- [ ] Preserve direct content editing, template selection/upload, polished/raw variant toggle, automatic saving, Word/PDF downloads, resume Agent, and confirm-to-jobs behavior.
- [ ] At 761–1023px collapse settings and document into a single column; at <=760px use readable 16px body text and never scale the A4 editor into an unreadable miniature.
- [ ] Run static tests, `tests/test_web_app.py`, and `node --check career_agent/web/static/app.js`.
- [ ] Checkpoint commit: `git add career_agent/web/static/index.html career_agent/web/static/styles.css career_agent/web/static/app.js tests/test_web_static_contract.py && git commit -m "feat: add responsive resume editing controls"`.

## Task 5: Simplify jobs and tailored-result flows across desktop and mobile

**Files:**
- Modify: `career_agent/web/static/index.html`
- Modify: `career_agent/web/static/styles.css`
- Modify: `career_agent/web/static/app.js`
- Modify: `tests/test_web_static_contract.py`
- Test: `tests/test_web_static_contract.py`

**Interfaces:**
- New `setJobFiltersExpanded(expanded: boolean): void`
- New `setMobileJobDetail(open: boolean): void`
- Existing `renderJobs()`
- Existing `selectJob(jobId)`
- Existing `renderJobDetail(job, loading = false, warning = null)`
- Existing `renderTailoredResult()`
- DOM contract: `#job-filter-toggle`, `#job-extra-filters`, `#mobile-job-detail-back`, existing `#job-list`, `#job-detail`, `#result-job-detail`, `.tailored-download`

- [ ] Add failing contract tests for the “更多筛选” disclosure, mobile job-detail back control, and collapsible match/validation secondary regions while retaining batch selection and download controls.
- [ ] Run the focused test and confirm the new progressive-disclosure controls are missing.
- [ ] Keep keyword, city, and search action in the compact primary search row; move salary, company, and experience into `#job-extra-filters` controlled by `setJobFiltersExpanded()` with synchronized `aria-expanded`.
- [ ] Preserve desktop list/detail behavior. On mobile, capture the job list scroll position, let `selectJob()` open the full-screen detail state, and let `setMobileJobDetail(false)` return to the exact prior list position.
- [ ] Keep list cards keyboard-selectable, checkbox clicks isolated from card selection, attachment confirmation gating, batch submission, official job link, and tailor action unchanged.
- [ ] Reorder the tailored result for mobile to “定制简历 → 匹配分析 → 事实校验”. Keep Word/PDF downloads beside the tailored resume heading; put score, strategy, gaps, and validation into accessible expandable secondary sections.
- [ ] Replace the blocking full-screen loading presentation for these flows with stage-aware text and ensure errors appear near the triggering region with `role="alert"`, while retaining toast as secondary feedback.
- [ ] Run static tests, `tests/test_web_app.py`, and `node --check career_agent/web/static/app.js`.
- [ ] Checkpoint commit: `git add career_agent/web/static/index.html career_agent/web/static/styles.css career_agent/web/static/app.js tests/test_web_static_contract.py && git commit -m "feat: refine responsive job and result flows"`.

## Task 6: Full regression, visual verification, and cleanup

**Files:**
- Modify if required: `career_agent/web/static/index.html`
- Modify if required: `career_agent/web/static/styles.css`
- Modify if required: `career_agent/web/static/app.js`
- Modify if required: `tests/test_web_static_contract.py`
- Test: `tests/test_web_app.py`
- Test: `tests/test_web_static_contract.py`

- [ ] Run `python -m pytest -q` and resolve only regressions caused by this redesign; record the final passing count.
- [ ] Run `python -m ruff check .` (or the repository's configured equivalent) and `node --check career_agent/web/static/app.js`.
- [ ] Start the local app and verify fresh-candidate behavior: profile opens first, prompt/upload/message interactions start the conversation, required information is not skipped, summary/preview can expand, and generated preview alone unlocks the next CTA.
- [ ] Verify restored-candidate behavior: refresh with a stored server resume, confirm `restoreResumeSession()` opens the resume view and does not discard unlocked steps or existing messages.
- [ ] Capture/inspect the app at 1440×900, 1024×768, 768×1024, 414×896, 375×812, and 320×568. Confirm no page-level horizontal overflow, no covered last message, and no clipped primary action.
- [ ] Keyboard-check navigation, mobile sheet open/close/Escape, prompt buttons, attachment, Enter/Shift+Enter, resume editing, section up/down, downloads, job cards, filter disclosure, detail return, and result disclosures.
- [ ] Verify desktop section dragging succeeds both upward and downward, while mobile/touch reordering works through explicit buttons.
- [ ] Verify the selected visual target: quiet warm background, one clear conversational focal point, restrained teal state color, narrow icon navigation, no oversized dashboard cards, and phone layout matching the approved direction.
- [ ] Confirm no API URLs, request bodies, secret handling, resume export endpoints, MCP calls, or local/session storage keys changed.
- [ ] If the repository has a clean attributable baseline, create final checkpoint commit: `git add career_agent/web/static/index.html career_agent/web/static/styles.css career_agent/web/static/app.js tests/test_web_app.py tests/test_web_static_contract.py && git commit -m "test: verify doubao calm frontend redesign"`. If the worktree baseline is not safely attributable, skip committing and report that explicitly.

## Review focus

1. **State recovery:** A first-time 404 from `/api/resume/current` must remain harmless, while a real saved resume must still restore directly to the resume view.
2. **Conversation state:** Collapsing the hero or data summary must never hide/discard messages, uploads, collected draft data, or the generated resume preview.
3. **Responsive safety:** At 320px the fixed top bar/composer, mobile sheet, resume flow, filters, and job detail must not create horizontal scrolling or cover the final interactive content.
4. **Accessible alternatives:** Pure icon navigation, drag-and-drop, disclosure panels, and mobile overlays all need keyboard/touch alternatives, clear labels, correct focus behavior, and Escape support.
5. **Business preservation:** Resume save/download/confirm, official MCP job details, attachment confirmation, batch selection/apply, tailoring, validation, and restored session behavior must remain functionally unchanged.

