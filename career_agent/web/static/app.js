const state = {
  candidateId: localStorage.getItem("careerCandidateId") || crypto.randomUUID(),
  photoAsset: null,
  rawResume: null,
  polishedResume: null,
  rawHometown: null,
  polishedHometown: null,
  previewVariant: "polished",
  templateId: "modern",
  sectionOrder: ["summary", "education", "work", "internship", "experience", "campus", "skills"],
  customTheme: null,
  resumeMobileMode: "edit",
  jobs: [],
  selectedJobIds: new Set(),
  attachmentReady: sessionStorage.getItem("liepinAttachmentReady") === "true",
  selectedJob: null,
  jobListScrollY: 0,
  analysis: null,
  intakeAttachments: [],
  intakeDraft: null,
  editorMode: "chat",
  designedTemplate: null,
  designedTemplates: [],
  activeDesignId: null,
  templateProposal: null,
  uploadedTheme: null,
  semanticKeywords: [],
  templateChat: [],
};
localStorage.setItem("careerCandidateId", state.candidateId);

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const splitValues = (value) => value.split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean);
const safeUrl = (value) => {
  try { const url = new URL(value); return url.protocol === "https:" ? url.href : "#"; }
  catch { return "#"; }
};
const appUrl = (path) => new URL(path.replace(/^\/+/, ""), document.baseURI).toString();

const viewCopy = {
  profile: ["对话建档", "Career Agent"],
  resume: ["初版简历", "编辑内容、调整顺序并选择合适的版式"],
  jobs: ["岗位发现", "用真实 JD 找到值得定制的机会"],
  result: ["匹配分析", "对照现有简历与岗位要求"],
  interview: ["模拟面试", "围绕已投递岗位练习真实经历"],
};

let lastMobileNavFocus = null;

function setMobileNav(open) {
  const toggle = $("#mobile-nav-toggle");
  const sheet = $("#mobile-nav-sheet");
  const backdrop = $("#mobile-nav-backdrop");
  const shell = $(".app-shell");
  if (!toggle || !sheet || !backdrop || !shell) return;
  const wasOpen = toggle.getAttribute("aria-expanded") === "true";
  if (open) lastMobileNavFocus = document.activeElement;
  toggle.setAttribute("aria-expanded", String(open));
  toggle.setAttribute("aria-label", open ? "关闭流程导航" : "打开流程导航");
  sheet.hidden = !open;
  sheet.setAttribute("aria-hidden", String(!open));
  backdrop.classList.toggle("hidden", !open);
  document.body.classList.toggle("mobile-nav-open", open);
  shell.inert = open;
  if (open) shell.setAttribute("aria-hidden", "true");
  else shell.removeAttribute("aria-hidden");
  if (open) requestAnimationFrame(() => $("#mobile-nav-close")?.focus());
  else if (wasOpen && window.matchMedia("(max-width: 760px)").matches && lastMobileNavFocus instanceof HTMLElement) lastMobileNavFocus.focus();
}

function setStepDisabled(viewName, disabled) {
  $$(`.step[data-view="${viewName}"], .mobile-step[data-view="${viewName}"]`).forEach((step) => {
    step.disabled = disabled;
  });
}

function invalidateJobAnalysis() {
  state.analysis = null;
  setStepDisabled("result", true);
  setStepDisabled("interview", true);
}

function syncShellState(viewName) {
  const currentCopy = viewCopy[viewName] || viewCopy.profile;
  const mobileTitle = $("#mobile-view-title");
  if (mobileTitle) mobileTitle.textContent = currentCopy[0];
  $$(".mobile-step").forEach((step) => {
    const desktopStep = $(`.step[data-view="${step.dataset.view}"]`);
    step.disabled = Boolean(desktopStep?.disabled);
  });
  $$(".step, .mobile-step").forEach((step) => {
    const active = step.dataset.view === (viewName === "resume" ? "profile" : viewName);
    step.classList.toggle("active", active);
    if (active) step.setAttribute("aria-current", "page");
    else step.removeAttribute("aria-current");
  });
  setMobileNav(false);
}

function showView(name) {
  if (name === "profile" || name === "resume") window.CareerResumeStudio?.mount(name === "resume" ? "detail" : "chat");
  document.body.classList.toggle("intake-view", name === "profile");
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  $("#view-eyebrow").textContent = viewCopy[name][0];
  $("#view-title").textContent = viewCopy[name][1];
  syncShellState(name);
  if (name === "resume") setResumeMobileMode(state.resumeMobileMode);
  window.scrollTo({top: 0, behavior: "smooth"});
}

function setLoading(active, title = "正在处理", message = "这可能需要几十秒，请不要关闭页面。") {
  $("#loading-title").textContent = title;
  $("#loading-message").textContent = message;
  $("#loading-overlay").classList.toggle("hidden", !active);
}

let toastTimer;
function toast(message) {
  clearTimeout(toastTimer);
  const node = $("#toast");
  node.textContent = message;
  node.classList.remove("hidden");
  toastTimer = setTimeout(() => node.classList.add("hidden"), 4500);
}

async function api(path, options = {}) {
  const response = await fetch(appUrl(path), {
    cache: "no-store",
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? "输入内容格式有误，请检查标红项目" : data.detail;
    throw new Error(detail || `请求失败（${response.status}）`);
  }
  return data;
}

let statusRetryTimer;
async function checkStatus() {
  clearTimeout(statusRetryTimer);
  const node = $("#system-state");
  const retry = $("#retry-backend");
  try {
    const status = await api("/api/status");
    node.classList.toggle("ready", status.ready);
    node.querySelector("span").textContent = status.ready ? "服务已就绪" : "后端正常 · 请完善模型或猎聘配置";
    node.title = `模型：${status.model} · 猎聘授权${status.liepin ? "已配置" : "未配置"}`;
    retry.classList.add("hidden");
  } catch {
    node.classList.remove("ready");
    node.querySelector("span").textContent = "后端暂未连接，正在重试";
    node.title = "请保持本地服务运行；服务恢复后会自动重新连接";
    retry.classList.remove("hidden");
    statusRetryTimer = setTimeout(checkStatus, 5000);
  }
}

async function restoreResumeSession() {
  try {
    const result = await api(`/api/resume/current?candidate_id=${encodeURIComponent(state.candidateId)}`);
    state.rawResume = result.raw_resume;
    state.polishedResume = result.display_resume;
    state.rawHometown = result.raw_hometown;
    state.polishedHometown = result.polished_hometown;
    state.sectionOrder = result.section_order;
    state.templateId = result.template_id;
    state.customTheme = result.custom_theme;
    state.uploadedTheme = result.custom_theme;
    state.designedTemplate = result.designed_template || null;
    state.designedTemplates = result.designed_templates || [];
    state.activeDesignId = result.active_design_id || null;
    state.templateProposal = result.template_proposal || null;
    state.templateChat = result.template_chat || [];
    state.semanticKeywords = result.semantic_keywords || [];
    state.photoAsset = result.photo_asset || state.photoAsset;
    if (state.templateId === "designed") state.customTheme = state.designedTemplate?.theme;
    if (result.intake_draft) renderIntakeSummary(result.intake_draft, Boolean(state.photoAsset));
    (result.intake_chat || []).forEach((message) => renderIntakeMessage(message.role, message.content));
    (result.resume_chat || []).forEach((message) => addAgentMessage(message.role, message.content));
    setStepDisabled("resume", false);
    setStepDisabled("jobs", !result.confirmed);
    renderResumeEditor();
    $("#chat-resume-preview").classList.remove("hidden");
    $("#generate-from-chat").dataset.action = "confirm-resume";
    $("#generate-from-chat").textContent = "确认简历并发现岗位 →";
    $("#generate-from-chat").classList.remove("hidden");
    showView("profile");
  } catch { /* A first-time visitor has no server-side resume session yet. */ }
}

$("#photo-name")?.addEventListener("click", () => $("input[name=photo]").click());
$("input[name=photo]")?.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) { toast("头像请控制在 2MB 以内"); event.target.value = ""; return; }
  const reader = new FileReader();
  reader.onload = () => { state.photoAsset = reader.result; $("#photo-name").textContent = file.name; };
  reader.readAsDataURL(file);
});

function addExperience() {
  const fragment = $("#experience-template").content.cloneNode(true);
  const card = fragment.querySelector(".experience-card");
  card.querySelector(".remove-experience").addEventListener("click", () => {
    card.remove();
    renumberExperiences();
  });
  $("#experience-list").appendChild(fragment);
  renumberExperiences();
}

function addEducation(values = {}) {
  const fragment = $("#education-template").content.cloneNode(true);
  const card = fragment.querySelector(".education-card");
  Object.entries(values).forEach(([field, value]) => {
    const input = card.querySelector(`[data-field="${field}"]`);
    if (input) input.value = Array.isArray(value) ? value.join("、") : (value || "");
  });
  card.querySelector(".remove-education").addEventListener("click", () => {
    card.remove();
    renumberEducations();
  });
  $("#education-list").appendChild(fragment);
  renumberEducations();
}

function renumberEducations() {
  const cards = $$(".education-card");
  cards.forEach((card, index) => {
    card.dataset.index = index;
    card.querySelector(".education-number").textContent = index + 1;
    card.querySelector(".remove-education").classList.toggle("hidden", cards.length === 1);
  });
}

function collectEducations() {
  return $$(".education-card").map((card) => ({
    school: card.querySelector('[data-field="school"]').value.trim() || null,
    major: card.querySelector('[data-field="major"]').value.trim() || null,
    degree: card.querySelector('[data-field="degree"]').value.trim() || null,
    start_date: card.querySelector('[data-field="start_date"]').value.trim() || null,
    end_date: card.querySelector('[data-field="end_date"]').value.trim() || null,
    courses: splitValues(card.querySelector('[data-field="courses"]').value),
  }));
}

function renumberExperiences() {
  $$(".experience-card").forEach((card, index) => {
    card.dataset.index = index;
    card.querySelector(".experience-number").textContent = index + 1;
  });
}

function collectExperiences() {
  return $$(".experience-card").map((card) => ({
    name: card.querySelector('[data-field="name"]').value.trim() || null,
    role: card.querySelector('[data-field="role"]').value.trim() || null,
    date_range: card.querySelector('[data-field="date_range"]').value.trim() || null,
    content: card.querySelector('[data-field="content"]').value.trim() || null,
    technologies: splitValues(card.querySelector('[data-field="technologies"]').value),
  }));
}

$("#add-experience")?.addEventListener("click", addExperience);
$("#add-education")?.addEventListener("click", () => addEducation());
if ($("#education-list")) addEducation();

$("#intake-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  form.querySelectorAll(".invalid").forEach((field) => field.classList.remove("invalid"));
  const values = Object.fromEntries(new FormData(form).entries());
  const educations = collectEducations();
  const payload = {
    candidate_id: state.candidateId,
    name: values.name || null,
    email: values.email || null,
    phone: values.phone || null,
    current_city: values.current_city || null,
    hometown: values.hometown || null,
    education: educations[0],
    educations,
    skills: values.skills?.trim() ? [values.skills.trim()] : [],
    experiences: collectExperiences(),
    projects: [],
    self_summary: values.self_summary || null,
    intended_jd: values.intended_jd || null,
    photo_asset: state.photoAsset,
  };

  setLoading(true, "正在生成初版简历", "AI 正在分类经历、整理日期与技能表达，同时保留原始事实。通常需要 1–2 分钟。");
  try {
    const result = await api("/api/intake", {method: "POST", body: JSON.stringify(payload)});
    const errorBox = $("#form-errors");
    if (!result.ready) {
      const fieldMap = {skills:"skills"};
      result.issues.forEach((issue) => {
        const match = issue.field.match(/^experiences\.(\d+)\.content$/);
        const educationMatch = issue.field.match(/^educations\.(\d+)\.(school|major|degree)$/);
        if (match) {
          $$(".experience-card")[Number(match[1])]?.querySelector('[data-field="content"]')?.classList.add("invalid");
        } else if (educationMatch) {
          $$(".education-card")[Number(educationMatch[1])]?.querySelector(`[data-field="${educationMatch[2]}"]`)?.classList.add("invalid");
        } else {
          form.elements[fieldMap[issue.field] || issue.field]?.classList.add("invalid");
        }
      });
      errorBox.innerHTML = result.issues.map((issue) => `<div>• ${escapeHtml(issue.message)}</div>`).join("");
      errorBox.classList.remove("hidden");
      return;
    }
    errorBox.classList.add("hidden");
    state.rawResume = structuredClone(result.resume);
    state.polishedResume = structuredClone(result.display_resume);
    state.rawHometown = payload.hometown;
    state.polishedHometown = result.normalized_hometown || payload.hometown;
    state.previewVariant = "polished";
    setStepDisabled("resume", false);
    setStepDisabled("jobs", true);
    renderResumeEditor();
    showView("resume");
    toast(result.polish_warning || "初版简历已生成，可直接点击文字修改");
  } catch (error) { toast(error.message); }
  finally { setLoading(false); }
});

function setConversationStarted(started) {
  const stage = $(".conversation-stage");
  if (!stage) return;
  stage.dataset.conversationStarted = String(started);
  stage.classList.toggle("conversation-started", started);
}

function renderIntakeMessage(role, content) {
  setConversationStarted(true);
  const node = document.createElement("div");
  node.className = `intake-message ${role}`;
  node.textContent = content;
  const messages = $("#intake-messages");
  messages.appendChild(node);
  const scrollRegion = $("#intake-scroll-region");
  requestAnimationFrame(() => { scrollRegion.scrollTop = scrollRegion.scrollHeight; });
}

function renderUploadQueue() {
  const queue = $("#upload-queue");
  if (!state.intakeAttachments.length) { queue.classList.add("hidden"); queue.innerHTML = ""; return; }
  setConversationStarted(true);
  queue.classList.remove("hidden");
  queue.innerHTML = state.intakeAttachments.map((file, index) => `<span>${escapeHtml(file.filename)}<button type="button" data-remove-upload="${index}" aria-label="移除">×</button></span>`).join("");
  $$('[data-remove-upload]').forEach((button) => button.addEventListener("click", () => {
    state.intakeAttachments.splice(Number(button.dataset.removeUpload), 1);
    renderUploadQueue();
  }));
}

function renderIntakeSummary(draft, hasPhoto = false) {
  state.intakeDraft = draft;
  const summary = $("#intake-summary");
  const summaryBody = $("#intake-summary-body");
  const education = (draft.educations?.length ? draft.educations : [draft.education]).filter((item) => item?.school);
  const rows = [
    ["基本信息", [draft.name, draft.email, draft.phone].filter(Boolean).join(" · ")],
    ["教育", education.map((item) => [item.school, item.major, item.degree].filter(Boolean).join(" · ")).join("；")],
    ["技能", (draft.skills || []).join("、")],
    ["经历", draft.experiences?.length ? `${draft.experiences.length} 条已收集` : ""],
    ["其他", [draft.current_city, draft.hometown, draft.self_summary ? "个人总结" : "", hasPhoto ? "头像" : ""].filter(Boolean).join(" · ")],
  ].filter(([, value]) => value);
  if (!rows.length) { summary.classList.add("hidden"); return; }
  setConversationStarted(true);
  summary.classList.remove("hidden");
  $("#intake-summary-label").textContent = `已整理 ${rows.length} 项资料`;
  summaryBody.innerHTML = rows.map(([label, value]) => `<div><span>${label}</span><p>${escapeHtml(value)}</p></div>`).join("");
}

async function sendIntakeTurn({message = "", generate = false} = {}) {
  if (!message.trim() && !state.intakeAttachments.length && !generate) return;
  setConversationStarted(true);
  $("#intake-summary-toggle").setAttribute("aria-expanded", "false");
  $("#intake-summary-body").classList.add("hidden");
  if (message.trim()) renderIntakeMessage("user", message.trim());
  if (state.intakeAttachments.length) renderIntakeMessage("user", `上传：${state.intakeAttachments.map((item) => item.filename).join("、")}`);
  const attachments = state.intakeAttachments;
  state.intakeAttachments = [];
  renderUploadQueue();
  const input = $("#intake-input");
  const submit = $("#intake-chat-form button[type=submit]");
  input.disabled = true; submit.disabled = true; $("#generate-from-chat").disabled = true;
  setLoading(true, generate ? "正在生成初版简历" : "正在理解并整理资料", generate ? "AI 正在分类经历、统一日期与技能表达。" : "Agent 正在提取你刚刚提供的事实并判断还缺什么。");
  try {
    if (currentResume() && message.trim() && !attachments.length && !generate) {
      await saveResume();
      const edited = await api("/api/resume/agent", {method: "POST", body: JSON.stringify({
        candidate_id: state.candidateId, variant: state.previewVariant, message,
      })});
      if (state.previewVariant === "polished") state.polishedResume = edited.resume;
      else state.rawResume = edited.resume;
      renderIntakeMessage("assistant", edited.assistant_message);
      renderResumeEditor();
      $("#save-state").textContent = "AI 修改已保存";
      setStepDisabled("jobs", true);
      invalidateJobAnalysis();
      const confirmAction = $("#generate-from-chat");
      confirmAction.dataset.action = "confirm-resume";
      confirmAction.textContent = "确认简历并发现岗位 →";
      confirmAction.classList.remove("hidden");
      return;
    }
    const result = await api("/api/intake/chat", {
      method: "POST",
      body: JSON.stringify({candidate_id: state.candidateId, message, attachments, generate}),
    });
    if (result.recognized_photo_filename) {
      state.photoAsset = attachments.find((item) => item.filename === result.recognized_photo_filename)?.data_url || state.photoAsset;
    }
    renderIntakeMessage("assistant", result.assistant_message);
    if (result.draft) renderIntakeSummary(result.draft, result.has_photo || Boolean(state.photoAsset));
    const intakeAction = $("#generate-from-chat");
    intakeAction.dataset.action = "generate";
    intakeAction.textContent = "确认生成初版简历 →";
    intakeAction.classList.toggle("hidden", !result.ready_to_generate || result.generated);
    if (result.generated || result.preview_generated) {
      state.rawResume = structuredClone(result.resume);
      state.polishedResume = structuredClone(result.display_resume || result.resume);
      state.rawHometown = result.draft?.hometown || null;
      state.polishedHometown = result.normalized_hometown || state.rawHometown;
      state.previewVariant = "polished";
      state.semanticKeywords = result.semantic_keywords || [];
      setStepDisabled("resume", false);
      setStepDisabled("jobs", true);
      renderResumeEditor();
      const previewReady = Boolean((result.preview_generated || result.generated) && result.preview_html);
      $("#chat-resume-preview").classList.remove("hidden");
      window.CareerResumeStudio?.mount("chat");
      intakeAction.dataset.action = "confirm-resume";
      intakeAction.textContent = "确认简历并发现岗位 →";
      intakeAction.classList.toggle("hidden", !previewReady);
      syncShellState("profile");
      toast(result.polish_warning || "简历已整理，可在对话里直接编辑，也可以打开精修编辑");
    }
  } catch (error) {
    renderIntakeMessage("assistant error", `处理失败：${error.message}`);
  } finally {
    setLoading(false); input.disabled = false; submit.disabled = false; $("#generate-from-chat").disabled = false; input.focus();
  }
}

$("#intake-chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#intake-input");
  const message = input.value.trim();
  input.value = "";
  await sendIntakeTurn({message});
});

$("#intake-input").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  $("#intake-chat-form").requestSubmit();
});

$("#intake-input").addEventListener("input", (event) => {
  event.currentTarget.style.height = "auto";
  const nextHeight = Math.min(event.currentTarget.scrollHeight, 180);
  event.currentTarget.style.height = `${nextHeight}px`;
  event.currentTarget.style.overflowY = event.currentTarget.scrollHeight > 180 ? "auto" : "hidden";
});

$$('[data-prompt]').forEach((button) => button.addEventListener("click", () => sendIntakeTurn({message: button.dataset.prompt})));
$("#intake-upload-prompt")?.addEventListener("click", () => $("#intake-files").click());
function bindKeyboardFilePicker(labelSelector, inputSelector) {
  const label = $(labelSelector);
  const input = $(inputSelector);
  label?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    input?.click();
  });
}
bindKeyboardFilePicker("#intake-files-label", "#intake-files");
bindKeyboardFilePicker("#template-upload-label", "#template-upload");
$("#intake-summary-toggle")?.addEventListener("click", (event) => {
  const expanded = event.currentTarget.getAttribute("aria-expanded") === "true";
  event.currentTarget.setAttribute("aria-expanded", String(!expanded));
  $("#intake-summary-body").classList.toggle("hidden", expanded);
});
$("#generate-from-chat").addEventListener("click", (event) => {
  if (event.currentTarget.dataset.action === "confirm-resume") $("#confirm-resume").click();
  else sendIntakeTurn({generate: true});
});

function setJobFiltersExpanded(expanded) {
  const toggle = $("#job-filter-toggle");
  const filters = $("#job-extra-filters");
  if (!toggle || !filters) return;
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.textContent = expanded ? "收起筛选" : "更多筛选";
  filters.classList.toggle("hidden", !expanded);
}

function setMobileJobDetail(open) {
  const jobsView = $("#view-jobs");
  const detail = $("#job-detail");
  if (!jobsView || !detail) return;
  const isMobile = window.matchMedia("(max-width: 760px)").matches;
  if (!isMobile) {
    jobsView.classList.remove("mobile-detail-open");
    detail.classList.remove("mobile-open");
    return;
  }
  if (open && !jobsView.classList.contains("mobile-detail-open")) state.jobListScrollY = window.scrollY;
  jobsView.classList.toggle("mobile-detail-open", open);
  detail.classList.toggle("mobile-open", open);
  if (open) window.scrollTo({top: 0, behavior: "auto"});
  else window.scrollTo({top: state.jobListScrollY, behavior: "auto"});
}

$("#job-search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget).entries());
  const errorBox = $("#job-search-error");
  errorBox.classList.add("hidden");
  errorBox.textContent = "";
  setLoading(true, "正在搜索猎聘岗位", "正在通过官方 MCP 获取实时岗位，请稍候。");
  try {
    const data = await api("/api/jobs/search", {method: "POST", body: JSON.stringify({
      candidate_id: state.candidateId,
      keyword: values.keyword,
      city: values.city,
      salary_min: values.salary_min ? Number(values.salary_min) : null,
      company_name: values.company_name || null,
      experience: values.experience || null,
    })});
    state.jobs = data.jobs;
    invalidateJobAnalysis();
    state.selectedJobIds = new Set();
    state.selectedJob = null;
    renderJobs();
    $("#job-count").textContent = `· ${state.jobs.length} 个`;
    if (!state.jobs.length) toast("没有找到符合条件的岗位，可以放宽搜索条件");
  } catch (error) { errorBox.textContent = error.message; errorBox.classList.remove("hidden"); toast(error.message); }
  finally { setLoading(false); }
});

function renderJobs() {
  const list = $("#job-list");
  if (!state.jobs.length) { list.innerHTML = '<div class="empty-list"><p>没有匹配结果，试试更宽泛的岗位名称。</p></div>'; return; }
  list.innerHTML = state.jobs.map((job) => `
    <article class="job-card ${state.selectedJob?.id === job.id ? "active" : ""}" data-job-id="${escapeHtml(job.id)}" tabindex="0">
      <label class="job-select" title="加入投递队列"><input type="checkbox" data-select-job="${escapeHtml(job.id)}" ${state.selectedJobIds.has(job.id) ? "checked" : ""}><span>选择</span></label>
      <div class="job-card-head"><div><h3>${escapeHtml(job.title)}</h3><p>${escapeHtml(job.company)} · ${escapeHtml(job.location)}</p></div><span class="salary">${escapeHtml(job.salary_text || "薪资面议")}</span></div>
      <div class="job-tags">${[job.industry, job.company_size, job.detail_verified ? "JD 已读取" : "可查看完整 JD"].filter(Boolean).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
    </article>`).join("");
  $$(".job-card").forEach((card) => {
    const select = () => selectJob(card.dataset.jobId);
    card.addEventListener("click", select);
    card.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
  });
  $$('[data-select-job]').forEach((input) => {
    input.addEventListener("click", (event) => event.stopPropagation());
    input.addEventListener("change", () => {
      if (input.checked) state.selectedJobIds.add(input.dataset.selectJob);
      else state.selectedJobIds.delete(input.dataset.selectJob);
      updateBatchApplyState();
    });
  });
  updateBatchApplyState();
}

function updateBatchApplyState() {
  const button = $("#open-selected-jobs");
  button.disabled = state.selectedJobIds.size === 0 || !state.attachmentReady;
  button.textContent = state.selectedJobIds.size ? `投递已选岗位（${state.selectedJobIds.size}）` : "投递已选岗位";
  $("#apply-job").disabled = !state.attachmentReady;
}

async function selectJob(jobId) {
  const summary = state.jobs.find((job) => job.id === jobId);
  state.selectedJob = summary;
  renderJobs();
  renderJobDetail(summary, true);
  setMobileJobDetail(true);
  if (summary.detail_verified) { renderJobDetail(summary, false); return; }
  try {
    const data = await api("/api/jobs/detail", {method: "POST", body: JSON.stringify({candidate_id: state.candidateId, job_id: jobId})});
    state.selectedJob = data.job;
    state.jobs = state.jobs.map((job) => job.id === jobId ? data.job : job);
    renderJobs();
    renderJobDetail(data.job, false, data.detail_warning || null);
  } catch (error) { renderJobDetail(summary, false, error.message); }
}

function renderJobDetail(job, loading = false, warning = null) {
  const detail = $("#job-detail-content");
  detail.innerHTML = `<div class="detail-content">
    <p class="section-kicker">${loading ? "正在读取完整 JD" : "岗位详情"}</p>
    <h2>${escapeHtml(job.title)}</h2><p class="detail-company">${escapeHtml(job.company)} · ${escapeHtml(job.location)}</p>
    <div class="detail-meta">${[job.salary_text, job.industry, job.company_size].filter(Boolean).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
    ${warning ? `<div class="inline-error" role="alert">${escapeHtml(warning)}</div>` : ""}
    <div class="detail-body">${loading ? "正在从猎聘官方详情页读取岗位职责与任职要求…" : escapeHtml(job.detail_text || job.summary || "暂无岗位详情")}</div>
    <div class="detail-actions">
      <button class="primary-button" id="analyze-job" ${loading || !job.detail_verified ? "disabled" : ""}>分析匹配并准备面试 →</button>
      <button class="secondary-button" id="copy-detail-jd" ${loading || !job.detail_verified ? "disabled" : ""}>复制 JD</button>
      ${job.source_url ? `<a class="secondary-button" href="${escapeHtml(safeUrl(job.source_url))}" target="_blank" rel="noopener">查看原岗位 ↗</a>` : ""}
    </div></div>`;
  $("#analyze-job")?.addEventListener("click", analyzeSelectedJob);
  $("#copy-detail-jd")?.addEventListener("click", () => copyJobJd(job));
}

async function copyJobJd(job) {
  if (!job?.detail_verified || !job.detail_text) { toast("完整 JD 尚未读取"); return; }
  const text = [job.title, job.company, job.detail_text].filter(Boolean).join("\n\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("完整 JD 已复制，返回首页对话即可粘贴并提出修改要求");
  } catch {
    toast("复制失败，请检查浏览器剪贴板权限");
  }
}

async function analyzeSelectedJob() {
  if (!state.selectedJob) return;
  setLoading(true, "正在分析匹配", "正在解析 JD、核对现有经历并准备面试题。");
  try {
    state.analysis = await api("/api/jobs/analyze", {method: "POST", body: JSON.stringify({
      candidate_id: state.candidateId, job_id: state.selectedJob.id,
    })});
    renderJobAnalysis();
    setStepDisabled("result", false);
    showView("result");
  } catch (error) { toast(error.message); }
  finally { setLoading(false); }
}

function renderJobAnalysis() {
  const result = state.analysis;
  $("#result-company").textContent = result.job.company;
  $("#result-job-title").textContent = result.job.title;
  $("#result-job-detail-body").textContent = result.job.detail_text || result.job.summary || "暂无岗位详情";
  $("#result-job-detail").open = false;
  $("#interview-job-title").textContent = `${result.job.title} · 模拟面试`;
  const score = Math.round(result.match.score * 100);
  $("#score-value").textContent = `${score}%`;
  $("#score-ring").style.setProperty("--score", `${score}%`);
  $("#score-groups").innerHTML = [
    ["强匹配", result.match.strong_matches.length],
    ["部分匹配", result.match.partial_matches.length],
    ["待补足", result.match.missing_requirements.length],
  ].map(([label, value]) => `<div class="metric-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  const evidence = Object.fromEntries(result.evidence_matches.map((item) => [item.requirement_id, item]));
  const statusLabels = {STRONG_MATCH: "强匹配", PARTIAL_MATCH: "部分匹配", NO_MATCH: "待补足", UNKNOWN: "待核实"};
  $("#analysis-requirements").innerHTML = result.jd_analysis.requirements.map((requirement) => {
    const item = evidence[requirement.id];
    const status = item?.status || "UNKNOWN";
    return `<article class="analysis-requirement"><span class="analysis-status ${escapeHtml(status.toLowerCase())}">${statusLabels[status] || "待核实"}</span><p>${escapeHtml(requirement.text)}</p></article>`;
  }).join("") || '<p class="interview-empty">这份 JD 未解析出可评分的要求。</p>';
  renderInterviewPlan(result.interview_plan);
}

function interviewAnswerKey(jobId) {
  return `careerInterviewAnswers:${state.candidateId}:${jobId}`;
}

function readInterviewAnswers(jobId) {
  try { return JSON.parse(localStorage.getItem(interviewAnswerKey(jobId)) || "{}"); }
  catch { return {}; }
}

function renderInterviewPlan(plan) {
  const content = $("#interview-content");
  if (!plan?.questions?.length) {
    content.innerHTML = '<p class="interview-empty">目前没有面试题。返回岗位页重新分析即可生成。</p>';
    $("#clear-interview-answers").disabled = true;
    return;
  }
  $("#clear-interview-answers").disabled = false;
  const saved = readInterviewAnswers(plan.job_id);
  const labels = {strong: "有直接经验", partial: "有部分经验", gap: "需要准备差距说明", unknown: "待核实"};
  content.innerHTML = plan.questions.map((item, index) => `
    <article class="interview-question">
      <div class="interview-question-head"><span class="interview-number">${String(index + 1).padStart(2, "0")}</span><span class="interview-match ${escapeHtml(item.match_level)}">${labels[item.match_level] || "待核实"}</span></div>
      <h3>${escapeHtml(item.question)}</h3>
      <p class="interview-requirement">JD 依据：${escapeHtml(item.requirement_text)}</p>
      <label class="interview-answer-label" for="interview-answer-${escapeHtml(item.id)}">你的练习回答</label>
      <textarea id="interview-answer-${escapeHtml(item.id)}" data-interview-answer="${escapeHtml(item.id)}" rows="4" placeholder="按真实经历回答：你的职责、方法、证据和结果。">${escapeHtml(saved[item.id] || "")}</textarea>
      <details class="interview-hints"><summary>查看答题线索与追问</summary><ul>${item.talking_points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul><p><strong>可能追问：</strong>${escapeHtml(item.follow_up)}</p></details>
    </article>`).join("");
}

$("#interview-content").addEventListener("input", (event) => {
  const field = event.target.closest("[data-interview-answer]");
  if (!field || !state.analysis?.interview_plan) return;
  const jobId = state.analysis.interview_plan.job_id;
  const answers = readInterviewAnswers(jobId);
  answers[field.dataset.interviewAnswer] = field.value;
  localStorage.setItem(interviewAnswerKey(jobId), JSON.stringify(answers));
});

$("#clear-interview-answers").addEventListener("click", () => {
  const jobId = state.analysis?.interview_plan?.job_id;
  if (!jobId) return;
  localStorage.removeItem(interviewAnswerKey(jobId));
  $("#interview-content").querySelectorAll("[data-interview-answer]").forEach((field) => {
    field.value = "";
  });
  toast("本机面试练习记录已清空");
});

const sectionLabels = {summary: "个人总结", education: "教育经历", work: "工作经历", internship: "实习经历", experience: "经历", campus: "校园经历", skills: "专业技能"};
const currentResume = () => state.previewVariant === "polished" ? state.polishedResume : state.rawResume;
const currentHometown = () => (state.previewVariant === "polished" ? state.polishedHometown : state.rawHometown) || currentResume()?.personal_info?.hometown || null;

function editable(value, path, className = "", placeholder = "点击编辑") {
  return `<span class="editable ${className}" contenteditable="true" spellcheck="false" data-path="${escapeHtml(path)}" data-placeholder="${escapeHtml(placeholder)}">${escapeHtml(value || "")}</span>`;
}

function renderProfileLinks(links = []) {
  const items = links.map((value, index) => {
    let href = "";
    try {
      const parsed = new URL(value);
      if (["http:", "https:"].includes(parsed.protocol)) href = parsed.href;
    } catch { /* Keep malformed historical values editable without opening them. */ }
    const label = /github\.com/i.test(value) ? "GitHub" : "个人网站";
    return `<div class="portfolio-link"><span class="link-label">${label}</span>${editable(value, `personal_info.links.${index}`, "", "链接地址")}${href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" aria-label="打开${label}">↗</a>` : ""}</div>`;
  });
  return items.length ? `<div class="portfolio-links" aria-label="个人网站与作品链接">${items.join("")}</div>` : "";
}

function dateRange(item, path) {
  const dates = [item.start_date ? editable(item.start_date, `${path}.start_date`) : "", item.end_date ? editable(item.end_date, `${path}.end_date`) : ""].filter(Boolean);
  return dates.length ? `<span class="resume-dates">${dates.join("<i>—</i>")}</span>` : "";
}

function sectionBlock(key, content, position, total, customTitle) {
  if (!content) return "";
  const title = customTitle || sectionLabels[key];
  return `<section class="editable-section" data-section="${key}"><div class="resume-section-title" title="点击文字编辑标题，按住空白处拖动模块"><span class="section-drag-handle" aria-hidden="true">⠿</span><h2>${editable(title, `section_titles.${key}`, "section-title-editable", "点击编辑栏目标题")}</h2><span class="drag-hint">点击标题编辑 · 拖动空白处排序</span><div class="resume-section-controls" aria-label="调整${escapeHtml(title)}位置"><button type="button" data-move-section="${key}" data-direction="-1" aria-label="上移${escapeHtml(title)}" ${position === 0 ? "disabled" : ""}>↑</button><button type="button" data-move-section="${key}" data-direction="1" aria-label="下移${escapeHtml(title)}" ${position === total - 1 ? "disabled" : ""}>↓</button></div></div><div class="resume-section-content">${content}</div></section>`;
}

function renderEducation(resume) {
  return (resume.educations || []).map((item, index) => {
    const path = `educations.${index}`;
    return `<div class="resume-entry"><div class="entry-heading"><div>${editable(item.school, `${path}.school`, "entry-primary", "学校")}${editable(item.major, `${path}.major`, "entry-secondary", "专业")}${editable(item.degree, `${path}.degree`, "entry-secondary", "学历")}</div>${dateRange(item, path)}</div>${editable(item.description, `${path}.description`, "entry-description block-editable", "课程、成绩或教育说明")}</div>`;
  }).join("");
}

function renderExperienceEntries(items, collection, primaryField, secondaryField) {
  return (items || []).map((item, index) => {
    const path = `${collection}.${index}`;
    const technologies = collection === "project_experiences" && item.technologies?.length ? `<div class="entry-technologies"><b>技术：</b>${editable(item.technologies.join("、"), `${path}.technologies`, "", "相关技术")}</div>` : "";
    return `<div class="resume-entry"><div class="entry-heading"><div>${editable(item[primaryField], `${path}.${primaryField}`, "entry-primary", "经历名称")}${editable(item[secondaryField], `${path}.${secondaryField}`, "entry-secondary", "角色")}</div>${dateRange(item, path)}</div>${editable(item.description, `${path}.description`, "entry-description block-editable", "点击填写经历内容")}${technologies}</div>`;
  }).join("");
}

function renderResumeEditor() {
  const resume = currentResume();
  if (!resume) return;
  const info = resume.personal_info;
  const sections = {
    summary: resume.summary ? `<div class="summary-line">${editable(resume.summary, "summary", "block-editable", "点击编辑个人总结")}</div>` : "",
    education: renderEducation(resume),
    work: renderExperienceEntries(resume.work_experiences, "work_experiences", "company", "title"),
    internship: renderExperienceEntries(resume.internships, "internships", "company", "title"),
    experience: renderExperienceEntries(resume.project_experiences, "project_experiences", "name", "role"),
    campus: renderExperienceEntries(resume.campus_experiences, "campus_experiences", "organization", "role"),
    skills: resume.skills?.length ? `<div class="skills-line">${editable(resume.skills.map((item) => item.name).join("、"), "__skills__", "block-editable", "点击编辑技能")}</div>` : "",
};
  const photo = state.photoAsset ? `<img class="editor-photo" src="${escapeHtml(state.photoAsset)}" alt="头像">` : "";
  const editor = $("#resume-editor");
  const visibleSections = state.sectionOrder.filter((key) => sections[key]);
  editor.innerHTML = `<header class="resume-paper-header"><div class="identity-block"><h1>${editable(info.name, "personal_info.name", "", "姓名")}</h1><div class="contact-line">${editable(info.email, "personal_info.email", "", "邮箱")}${editable(info.phone, "personal_info.phone", "", "电话")}${info.location ? `<span>所在地：${editable(info.location, "personal_info.location", "", "现居城市")}</span>` : ""}${currentHometown() ? `<span>籍贯：${editable(currentHometown(), "__hometown__", "", "籍贯")}</span>` : ""}</div>${renderProfileLinks(info.links)}</div>${photo}</header><div class="resume-sections">${visibleSections.map((key, index) => sectionBlock(key, sections[key], index, visibleSections.length, resume.section_titles?.[key])).join("")}</div>`;
  applyTemplateClass();
  bindResumeInteractions();
  renderResumeMobilePreview();
  window.CareerResumeStudio?.refresh();
}

function renderResumeMobilePreview() {
  const source = $("#resume-editor");
  const canvas = $("#resume-mobile-preview-canvas");
  if (!source || !canvas || !currentResume()) return;
  const clone = source.cloneNode(true);
  clone.id = "resume-mobile-preview-paper";
  clone.setAttribute("aria-label", "只读简历页面预览");
  clone.querySelectorAll("[contenteditable]").forEach((node) => {
    node.setAttribute("contenteditable", "false");
    node.removeAttribute("data-path");
  });
  clone.querySelectorAll("[draggable]").forEach((node) => node.setAttribute("draggable", "false"));
  clone.querySelectorAll(".resume-section-controls, .drag-hint, .section-drag-handle").forEach((node) => node.remove());
  canvas.replaceChildren(clone);
  requestAnimationFrame(() => {
    const availableWidth = Math.max(280, canvas.clientWidth - 16);
    const scale = Math.min(1, availableWidth / 794);
    clone.style.transform = `scale(${scale})`;
    canvas.style.height = `${Math.ceil(Math.max(1122, clone.scrollHeight) * scale) + 16}px`;
  });
}

function setResumeMobileMode(mode) {
  state.resumeMobileMode = mode === "preview" ? "preview" : "edit";
  const isMobile = window.matchMedia("(max-width: 760px)").matches && state.editorMode === "detail";
  const editPane = $("#resume-edit-pane");
  const previewPane = $("#resume-mobile-preview-pane");
  if (!editPane || !previewPane) return;
  editPane.classList.toggle("hidden", isMobile && state.resumeMobileMode === "preview");
  previewPane.classList.toggle("hidden", !isMobile || state.resumeMobileMode !== "preview");
  [["#resume-mobile-edit", "edit"], ["#resume-mobile-preview", "preview"]].forEach(([selector, value]) => {
    const button = $(selector);
    const selected = state.resumeMobileMode === value;
    button?.classList.toggle("active", selected);
    button?.setAttribute("aria-selected", String(selected));
  });
  if (isMobile && state.resumeMobileMode === "preview") renderResumeMobilePreview();
}

function applyTemplateClass() {
  const editor = $("#resume-editor");
  editor.className = `resume-paper template-${state.templateId}`;
  const layout = state.templateId === "modern" ? "banner" : state.templateId === "classic" ? "editorial" :
    state.templateId === "minimal" ? "sidebar" : (state.customTheme?.layout || "editorial");
  editor.classList.add(`layout-${layout}`);
  const requestedStyle = ["custom", "designed"].includes(state.templateId) ? state.customTheme?.visual_style : null;
  const visualStyle = requestedStyle && requestedStyle !== "auto" ? requestedStyle :
    layout === "sidebar" ? "blueprint" : layout === "banner" ? "aurora" : "paper";
  editor.classList.add(`style-${visualStyle}`);
  if (["custom", "designed"].includes(state.templateId) && state.customTheme) {
    editor.style.setProperty("--resume-font", state.customTheme.font_family);
    editor.style.setProperty("--resume-accent", state.customTheme.accent);
    editor.style.setProperty("--resume-title-size", `${state.customTheme.title_size}pt`);
    editor.style.setProperty("--resume-heading-size", `${state.customTheme.heading_size}pt`);
    editor.style.setProperty("--resume-body-size", `${state.customTheme.body_size || 10.5}pt`);
  } else {
    ["--resume-font", "--resume-accent", "--resume-title-size", "--resume-heading-size", "--resume-body-size"].forEach((name) => editor.style.removeProperty(name));
  }
  editor.classList.toggle("theme-centered", Boolean(["custom", "designed"].includes(state.templateId) && state.customTheme?.title_centered));
  editor.classList.toggle("theme-compact", Boolean(["custom", "designed"].includes(state.templateId) && state.customTheme?.compact));
  $$(".template-choice").forEach((button) => button.classList.toggle("active", button.dataset.template === state.templateId && (state.templateId !== "designed" || button.dataset.designId === state.activeDesignId)));
}

function setByPath(target, path, value) {
  const parts = path.split(".");
  let node = target;
  parts.slice(0, -1).forEach((part) => { node = node[Number.isNaN(Number(part)) ? part : Number(part)]; });
  node[parts.at(-1)] = value || null;
}

function updateEditorValue(node) {
  const resume = currentResume();
  const value = node.textContent.replace(/\u00a0/g, " ").trim();
  const path = node.dataset.path;
  if (path.startsWith("section_titles.")) {
    resume.section_titles ||= {};
    const key = path.split(".")[1];
    if (value) resume.section_titles[key] = value;
    else delete resume.section_titles[key];
  } else if (path === "__hometown__") {
    if (state.previewVariant === "polished") state.polishedHometown = value || null;
    else state.rawHometown = value || null;
    resume.personal_info.hometown = value || null;
  } else if (path.startsWith("personal_info.links.")) {
    const index = Number(path.split(".").at(-1));
    resume.personal_info.links[index] = value;
    resume.personal_info.links = resume.personal_info.links.filter(Boolean);
  } else if (path === "__skills__") {
    const names = value.split(/[,，、;；|\n·]+/).map((item) => item.trim()).filter(Boolean);
    resume.skills = names.map((name) => ({name, source_text: `技能：${names.join("、")}`, category: null, proficiency: null}));
  } else if (path.endsWith(".technologies")) {
    setByPath(resume, path, value.split(/[,，、;；|\n·]+/).map((item) => item.trim()).filter(Boolean));
  } else setByPath(resume, path, value);
  scheduleResumeSave();
}

let draggedResumeSection = null;

function syncSectionOrderFromCanvas() {
  const visible = $$("#resume-editor .editable-section").map((section) => section.dataset.section);
  const hidden = state.sectionOrder.filter((key) => !visible.includes(key));
  state.sectionOrder = [...visible, ...hidden];
}

function moveResumeSection(sectionKey, direction) {
  const visible = $$("#resume-editor .editable-section").map((section) => section.dataset.section);
  const currentIndex = visible.indexOf(sectionKey);
  const targetKey = visible[currentIndex + direction];
  if (currentIndex < 0 || !targetKey) return;
  const nextOrder = [...state.sectionOrder];
  const sourceIndex = nextOrder.indexOf(sectionKey);
  const targetIndex = nextOrder.indexOf(targetKey);
  [nextOrder[sourceIndex], nextOrder[targetIndex]] = [nextOrder[targetIndex], nextOrder[sourceIndex]];
  state.sectionOrder = nextOrder;
  renderResumeEditor();
  scheduleResumeSave();
}

function bindResumeInteractions() {
  $$("#resume-editor .editable").forEach((node) => {
    node.addEventListener("input", () => updateEditorValue(node));
    node.addEventListener("keydown", (event) => { if (event.key === "Enter" && !node.classList.contains("block-editable")) { event.preventDefault(); node.blur(); } });
    if (node.classList.contains("section-title-editable")) node.addEventListener("blur", () => {
      if (!node.textContent.trim()) renderResumeEditor();
    });
  });
  $$('[data-move-section]').forEach((button) => button.addEventListener("click", (event) => {
    event.stopPropagation();
    moveResumeSection(button.dataset.moveSection, Number(button.dataset.direction));
  }));
  $$("#resume-editor .resume-section-title").forEach((title) => {
    title.draggable = false;
    let originY = null;
    let moving = false;
    title.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.target.closest("button, [contenteditable]")) return;
      event.preventDefault();
      originY = event.clientY;
      $("#resume-editor").setPointerCapture(event.pointerId);
      draggedResumeSection = title.closest(".editable-section");
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", finish);
      document.addEventListener("pointercancel", finish);
    });
    const move = (event) => {
      if (originY === null || !draggedResumeSection) return;
      if (!moving && Math.abs(event.clientY - originY) < 5) return;
      moving = true;
      draggedResumeSection.classList.add("dragging");
      const siblings = $$("#resume-editor .editable-section");
      const target = siblings.find((section) => {
        const rect = section.getBoundingClientRect();
        return section !== draggedResumeSection && event.clientY >= rect.top && event.clientY <= rect.bottom;
      });
      if (target) {
        const after = siblings.indexOf(draggedResumeSection) < siblings.indexOf(target);
        target.parentElement.insertBefore(draggedResumeSection, after ? target.nextSibling : target);
        syncSectionOrderFromCanvas();
      }
      const scroller = state.editorMode === "chat" ? $("#intake-scroll-region") : null;
      const bounds = scroller?.getBoundingClientRect() || {top: 0, bottom: innerHeight};
      const amount = event.clientY > bounds.bottom - 55 ? 18 : event.clientY < bounds.top + 55 ? -18 : 0;
      if (amount) (scroller || window).scrollBy(0, amount);
    };
    const finish = (event) => {
      if (originY === null) return;
      const editor = $("#resume-editor");
      if (editor.hasPointerCapture(event.pointerId)) editor.releasePointerCapture(event.pointerId);
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", finish);
      document.removeEventListener("pointercancel", finish);
      originY = null;
      draggedResumeSection?.classList.remove("dragging");
      draggedResumeSection = null;
      if (moving) {
        moving = false;
        syncSectionOrderFromCanvas();
        renderResumeEditor();
        scheduleResumeSave();
      }
    };
  });
}

function resumePayload() {
  return {candidate_id: state.candidateId, variant: state.previewVariant, resume: currentResume(), hometown: currentHometown(), section_order: state.sectionOrder, template_id: state.templateId, design_id: state.activeDesignId};
}

let resumeSaveTimer;
let resumeSavePromise = Promise.resolve();
function scheduleResumeSave() {
  clearTimeout(resumeSaveTimer); $("#save-state").textContent = "正在编辑…"; setStepDisabled("jobs", true); invalidateJobAnalysis(); resumeSaveTimer = setTimeout(() => saveResume(), 650);
}

async function saveResume(endpoint = "/api/resume/edit") {
  clearTimeout(resumeSaveTimer);
  if (!currentResume()) return;
  $("#save-state").textContent = "正在保存…";
  resumeSavePromise = api(endpoint, {method: "POST", body: JSON.stringify(resumePayload())});
  try {
    const result = await resumeSavePromise;
    if (result.resume) { if (state.previewVariant === "polished") state.polishedResume = result.resume; else state.rawResume = result.resume; }
    $("#save-state").textContent = endpoint.endsWith("confirm") ? "已确认" : "已自动保存";
    return result;
  } catch (error) { $("#save-state").textContent = "保存失败"; toast(error.message); throw error; }
}

function downloadBlob(filename, content, type = "text/html;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$$("#view-resume .download-button").forEach((button) => button.addEventListener("click", async () => {
  if (!currentResume()) return;
  try {
    await saveResume();
    const format = button.dataset.format;
    const path = `/api/resume/download/${state.previewVariant}/${format}?candidate_id=${encodeURIComponent(state.candidateId)}`;
    const response = await fetch(appUrl(path));
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `下载失败（${response.status}）`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `简历.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(error.message); }
}));

$("#toggle-polish").addEventListener("click", async () => {
  await saveResume();
  state.previewVariant = state.previewVariant === "polished" ? "raw" : "polished";
  setStepDisabled("jobs", true);
  invalidateJobAnalysis();
  renderResumeEditor();
  $("#toggle-polish").textContent = state.previewVariant === "polished" ? "查看原始输入版" : "返回 AI 整理版";
  toast(state.previewVariant === "polished" ? "已恢复 AI 整理版" : "已切换为与输入内容一致的原始版");
});

$("#confirm-resume").addEventListener("click", async () => {
  try {
    await saveResume("/api/resume/confirm");
    setStepDisabled("jobs", false);
    showView("jobs");
  } catch { /* saveResume already reports the error */ }
});

$$('.template-choice').forEach((button) => button.addEventListener("click", () => {
  if (button.dataset.template === "designed") { window.CareerResumeStudio?.openTemplateAgent(); return; }
  state.templateId = button.dataset.template;
  applyTemplateClass();
  scheduleResumeSave();
}));

$("#template-upload").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".docx") || file.size > 5 * 1024 * 1024) {
    toast("请选择 5MB 以内的 .docx Word 模板"); event.target.value = ""; return;
  }
  const reader = new FileReader();
  reader.onload = async () => {
    setLoading(true, "正在读取模板", "正在提取 Word 模板的字体、颜色、字号和页面设置。");
    try {
      const result = await api("/api/resume/template", {method: "POST", body: JSON.stringify({candidate_id: state.candidateId, filename: file.name, data_url: reader.result})});
      state.templateId = "custom";
      state.customTheme = result.theme;
      state.uploadedTheme = result.theme;
      $("#template-file-name").textContent = file.name;
      renderResumeEditor();
      await saveResume();
      toast("自定义模板已应用，Word 下载会保留其样式和页面设置");
    } catch (error) { toast(error.message); }
    finally { setLoading(false); }
  };
  reader.readAsDataURL(file);
});
function addAgentMessage(role, content) {
  const node = document.createElement("div");
  node.className = `agent-message ${role}`;
  node.textContent = content;
  const messages = $("#resume-agent-messages");
  messages.appendChild(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

$("#resume-agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = event.submitter;
  const input = $("#resume-agent-input");
  const message = input.value.trim();
  if (!message || !currentResume()) return;
  addAgentMessage("user", message);
  const progress = addAgentMessage("assistant working", "正在理解你的要求并修改简历…");
  const originalButtonText = submitButton.textContent;
  input.value = "";
  input.disabled = true;
  submitButton.disabled = true;
  submitButton.classList.add("is-working");
  submitButton.textContent = "修改中…";
  $("#resume-agent-form").setAttribute("aria-busy", "true");
  try {
    await saveResume();
    const result = await api("/api/resume/agent", {
      method: "POST",
      body: JSON.stringify({candidate_id: state.candidateId, variant: state.previewVariant, message}),
    });
    if (state.previewVariant === "polished") state.polishedResume = result.resume;
    else state.rawResume = result.resume;
    if (state.previewVariant === "polished") state.polishedHometown = result.hometown || result.resume.personal_info.hometown || null;
    else state.rawHometown = result.hometown || result.resume.personal_info.hometown || null;
    renderResumeEditor();
    progress.remove();
    addAgentMessage("assistant", result.assistant_message);
    $("#save-state").textContent = "AI 修改已保存";
    setStepDisabled("jobs", true);
    invalidateJobAnalysis();
  } catch (error) {
    progress.remove();
    addAgentMessage("assistant error", `修改失败：${error.message}`);
  } finally {
    input.disabled = false;
    submitButton.disabled = false;
    submitButton.classList.remove("is-working");
    submitButton.textContent = originalButtonText;
    $("#resume-agent-form").setAttribute("aria-busy", "false");
    input.focus();
  }
});

async function submitApplications(jobIds) {
  if (!jobIds.length) return;
  setLoading(true, "正在投递", `正在使用猎聘在线简历投递 ${jobIds.length} 个岗位，请勿关闭页面。`);
  try {
    const result = await api("/api/jobs/apply", {
      method: "POST",
      body: JSON.stringify({candidate_id: state.candidateId, job_ids: jobIds, attachment_confirmed: state.attachmentReady}),
    });
    const failed = result.results.length - result.applied_count;
    toast(failed ? `已投递 ${result.applied_count} 个，${failed} 个失败；请检查岗位类型或猎聘授权` : `已成功投递 ${result.applied_count} 个岗位`);
    const analyzedJobId = state.analysis?.job?.id;
    if (analyzedJobId && result.results.some((item) => item.job_id === analyzedJobId && item.applied) && $("#open-interview-after-apply").checked) {
      setStepDisabled("interview", false);
      showView("interview");
    }
  } catch (error) { toast(error.message); }
  finally { setLoading(false); }
}

$("#apply-job").addEventListener("click", () => {
  if (state.analysis?.job?.id) submitApplications([state.analysis.job.id]);
});
$("#copy-job-jd").addEventListener("click", () => copyJobJd(state.analysis?.job));
$("#return-to-chat").addEventListener("click", () => {
  showView("profile");
  $("#intake-input")?.focus();
});
$("#open-selected-jobs").addEventListener("click", () => submitApplications([...state.selectedJobIds]));
$("#toggle-result-detail").addEventListener("click", () => {
  const detail = $("#result-job-detail");
  detail.open = !detail.open;
});
$("#attachment-ready").checked = state.attachmentReady;
updateBatchApplyState();
$("#attachment-ready").addEventListener("change", (event) => {
  state.attachmentReady = event.currentTarget.checked;
  sessionStorage.setItem("liepinAttachmentReady", String(state.attachmentReady));
  updateBatchApplyState();
  toast(state.attachmentReady ? "已确认附件为猎聘默认投递简历，可以选择岗位投递" : "已取消附件确认，批量投递已锁定");
});

$("#back-profile").addEventListener("click", () => showView("profile"));
$("#back-resume").addEventListener("click", () => showView("profile"));
$("#back-jobs").addEventListener("click", () => showView("jobs"));
$("#back-tailored-result").addEventListener("click", () => showView("result"));
$("#resume-mobile-edit")?.addEventListener("click", () => setResumeMobileMode("edit"));
$("#resume-mobile-preview")?.addEventListener("click", () => setResumeMobileMode("preview"));
$("#job-filter-toggle")?.addEventListener("click", (event) => setJobFiltersExpanded(event.currentTarget.getAttribute("aria-expanded") !== "true"));
$("#mobile-job-detail-back")?.addEventListener("click", () => setMobileJobDetail(false));
window.addEventListener("resize", () => {
  if (state.rawResume || state.polishedResume) setResumeMobileMode(state.resumeMobileMode);
  if (!window.matchMedia("(max-width: 760px)").matches) {
    setMobileNav(false);
    setMobileJobDetail(false);
  }
});
$$(".step, .mobile-step").forEach((step) => step.addEventListener("click", () => { if (!step.disabled) showView(step.dataset.view); }));
$("#mobile-nav-toggle")?.addEventListener("click", () => setMobileNav($("#mobile-nav-toggle").getAttribute("aria-expanded") !== "true"));
$("#mobile-nav-close")?.addEventListener("click", () => setMobileNav(false));
$("#mobile-nav-backdrop")?.addEventListener("click", () => setMobileNav(false));
document.addEventListener("keydown", (event) => {
  const navOpen = $("#mobile-nav-toggle")?.getAttribute("aria-expanded") === "true";
  if (event.key === "Escape" && navOpen) { setMobileNav(false); return; }
  if (event.key === "Tab" && navOpen) {
    const focusable = $$("#mobile-nav-sheet button:not(:disabled), #mobile-nav-sheet a[href]");
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});

$("#retry-backend")?.addEventListener("click", checkStatus);
window.addEventListener("online", checkStatus);
window.addEventListener("focus", checkStatus);
checkStatus();
restoreResumeSession();
