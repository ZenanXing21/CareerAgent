/* One resume canvas shared by the conversation and the detailed editor. */
(() => {
  const toolbar = $("#resume-text-toolbar");
  const popover = $("#template-agent-popover");
  const launcher = $("#template-agent-launcher");
  const selectedSkills = new Set();
  const undo = new Map();
  let activeField = null;
  let toolbarAnchor = null;
  let hideTimer;
  let designing = false;
  let optimizing = false;
  let templateHistoryRestored = false;
  let floatingPosition = null;
  try {
    const stored = JSON.parse(sessionStorage.getItem("careerTemplateAgentPosition") || "null");
    if (stored && Number.isFinite(stored.x) && Number.isFinite(stored.y)) floatingPosition = stored;
  } catch { /* Use the position beside the template list. */ }

  function mount(mode) {
    state.editorMode = mode === "detail" ? "detail" : "chat";
    const host = $(state.editorMode === "detail" ? "#resume-editor-home" : "#chat-editor-host");
    const pane = $("#resume-edit-pane");
    if (host && pane && pane.parentElement !== host) host.appendChild(pane);
    setResumeMobileMode(state.resumeMobileMode);
    hideToolbar();
    refresh();
    if (!popover.classList.contains("hidden")) positionTemplateAgent();
  }

  function refresh() {
    if (!templateHistoryRestored && state.templateChat.length) {
      templateHistoryRestored = true;
      $("#template-agent-messages").replaceChildren();
      state.templateChat.forEach((message) => templateMessage(message.role, message.content));
    }
    const ready = Boolean(currentResume());
    $("#chat-resume-preview").classList.toggle("hidden", !ready);
    const keywords = $("#resume-semantic-keywords");
    keywords.classList.toggle("hidden", !state.semanticKeywords.length);
    keywords.innerHTML = state.semanticKeywords.slice(0, 18).map((word) => `<span>${escapeHtml(word)}</span>`).join("");
    $("#saved-template-list").innerHTML = state.designedTemplates.map((template) => `
      <div class="designed-template-slot">
        <button class="template-choice saved-template-choice" data-template="designed" data-design-id="${escapeHtml(template.id)}" type="button" title="${escapeHtml(template.description)}">
          <span class="template-swatch generated-swatch mini-layout-${escapeHtml(template.theme.layout || "editorial")} mini-style-${escapeHtml(template.theme.visual_style && template.theme.visual_style !== "auto" ? template.theme.visual_style : ({sidebar:"blueprint",banner:"aurora",editorial:"paper"}[template.theme.layout || "editorial"]))} ${template.theme.title_centered ? "mini-centered" : ""} ${template.theme.compact ? "mini-compact" : ""}" style="--swatch-accent:${escapeHtml(template.theme.accent)}" aria-hidden="true"><span class="mini-resume-name">个人简历</span><span class="mini-resume-rule"></span><span class="mini-resume-heading"></span><span class="mini-resume-lines"></span><span class="mini-resume-heading"></span><span class="mini-resume-lines"></span></span>
          <b>${escapeHtml(template.name)}</b><small>点击应用模板</small>
        </button>
        <button class="template-slot-remove" data-delete-design="${escapeHtml(template.id)}" type="button" aria-label="删除模板 ${escapeHtml(template.name)}">×</button>
      </div>`).join("");
    $("#template-proposal-actions").classList.toggle("hidden", !state.templateProposal);
    $("#confirm-template-design").disabled = designing;
    if (state.templateId === "designed") state.customTheme = state.designedTemplate?.theme;
    else if (state.templateId === "custom") state.customTheme = state.uploadedTheme;
    applyTemplateClass();
  }

  function cancelToolbarHide() {
    clearTimeout(hideTimer);
    hideTimer = null;
  }

  function hideToolbar() {
    cancelToolbarHide();
    toolbarAnchor = null;
    toolbar.classList.add("hidden");
  }

  function scheduleToolbarHide() {
    if (hideTimer) return;
    hideTimer = setTimeout(() => {
      hideTimer = null;
      if (toolbar.matches(":hover") || activeField?.matches(":hover") ||
          toolbar.contains(document.activeElement) || document.activeElement === activeField) return;
      hideToolbar();
    }, 900);
  }

  function showToolbar(node, event) {
    const path = node?.dataset.path || "";
    const isContent = path === "summary" || path === "__skills__" || path.endsWith(".description");
    if (!isContent) {
      if (event?.type === "pointerover" && activeField && !toolbar.classList.contains("hidden")) {
        scheduleToolbarHide();
        return;
      }
      activeField = null;
      hideToolbar();
      return;
    }
    if (optimizing || !node?.isConnected) return;
    cancelToolbarHide();
    const rect = node.getBoundingClientRect();
    if (activeField !== node) toolbarAnchor = null;
    if (event?.type === "pointerover" || (event?.type === "click" && event.detail > 0)) {
      toolbarAnchor = {x: event.clientX - rect.left, y: event.clientY - rect.top};
    }
    activeField = node;
    toolbar.classList.remove("hidden");
    toolbar.querySelector('[data-text-action="optimize"]').disabled = false;
    toolbar.querySelector('[data-text-action="shorten"]').disabled = false;
    toolbar.querySelector('[data-text-action="undo"]').disabled = !undo.has(`${state.previewVariant}:${node.dataset.path}`);
    const width = toolbar.offsetWidth;
    const height = toolbar.offsetHeight;
    const optimize = toolbar.querySelector('[data-text-action="optimize"]');
    const x = toolbarAnchor ? rect.left + toolbarAnchor.x - optimize.offsetLeft - optimize.offsetWidth / 2 : rect.left;
    const y = rect.top + (toolbarAnchor?.y || 0);
    const top = y - height - 10 >= 8 ? y - height - 10 : y + 12;
    toolbar.style.left = `${Math.max(8, Math.min(x, innerWidth - width - 8))}px`;
    toolbar.style.top = `${Math.max(8, Math.min(top, innerHeight - height - 8))}px`;
  }

  document.addEventListener("pointerover", (event) => {
    const node = event.target.closest("#resume-editor .editable");
    if (node) showToolbar(node, event);
  });
  document.addEventListener("focusin", (event) => {
    if (event.target.matches("#resume-editor .editable")) showToolbar(event.target, event);
  });
  document.addEventListener("click", (event) => {
    const node = event.target.closest("#resume-editor .editable");
    if (node) requestAnimationFrame(() => showToolbar(node, event));
    else if (!event.target.closest("#resume-text-toolbar")) hideToolbar();
  });
  document.addEventListener("pointerout", (event) => {
    if (event.target.closest("#resume-editor .editable, #resume-text-toolbar")) {
      if (activeField?.contains(event.relatedTarget) || toolbar.contains(event.relatedTarget)) {
        cancelToolbarHide();
        return;
      }
      scheduleToolbarHide();
    }
  });
  document.addEventListener("pointermove", (event) => {
    if (toolbar.classList.contains("hidden") || !activeField?.isConnected) return;
    if (toolbar.contains(event.target) || activeField.contains(event.target)) {
      cancelToolbarHide();
      return;
    }
    // Keep the route between the paragraph and its tools interactive, even during a slow move.
    const field = activeField.getBoundingClientRect(), tools = toolbar.getBoundingClientRect();
    const between = event.clientX >= Math.min(field.left, tools.left) - 12 &&
      event.clientX <= Math.max(field.right, tools.right) + 12 &&
      event.clientY >= Math.min(field.top, tools.top) - 12 &&
      event.clientY <= Math.max(field.bottom, tools.bottom) + 12;
    if (between && !event.target.closest("#resume-editor .editable")) cancelToolbarHide();
    else scheduleToolbarHide();
  });
  toolbar.addEventListener("pointerenter", cancelToolbarHide);
  toolbar.addEventListener("focusin", cancelToolbarHide);
  toolbar.addEventListener("pointerdown", (event) => event.preventDefault());
  window.addEventListener("resize", hideToolbar);
  $("#intake-scroll-region").addEventListener("scroll", () => {
    if (activeField?.isConnected && document.activeElement === activeField) showToolbar(activeField);
    else hideToolbar();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") hideToolbar(); });
  toolbar.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-text-action]")?.dataset.textAction;
    if (!action || !activeField?.isConnected || optimizing) return;
    const node = activeField;
    const path = node.dataset.path;
    const variant = state.previewVariant;
    const key = `${variant}:${path}`;
    if (action === "edit") { node.focus(); hideToolbar(); return; }
    if (action === "undo") {
      if (undo.has(key)) {
        node.textContent = undo.get(key);
        updateEditorValue(node);
        undo.delete(key);
        hideToolbar();
      }
      return;
    }
    if (!node.textContent.trim()) { toast("先填写一些内容，再让 AI 整理"); return; }
    optimizing = true;
    const original = node.textContent;
    toolbar.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    node.classList.add("ai-optimizing");
    try {
      await saveResume();
      const result = await api("/api/resume/optimize-field", {method: "POST", body: JSON.stringify({
        candidate_id: state.candidateId, variant, path,
        instruction: action === "shorten" ? "提取关键事实后精简为专业、紧凑的简历表述" : "先理解事实并提取关键词，再用专业简历语言重新组织",
      })});
      undo.set(key, original);
      if (node.isConnected && node.textContent === original) {
        node.textContent = result.optimized_text;
        updateEditorValue(node);
      } else { toast("文字已变化，保留你的最新编辑"); return; }
      state.semanticKeywords = result.keywords || [];
      renderResumeEditor();
      $("#save-state").textContent = "AI 优化已保存";
      setStepDisabled("jobs", true);
      toast("已理解并优化这段内容，可在悬浮栏撤销");
    } catch (error) { toast(error.message); }
    finally {
      optimizing = false;
      node.classList.remove("ai-optimizing");
      toolbar.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      hideToolbar();
    }
  });

  function templateMessage(role, content) {
    const node = document.createElement("div");
    node.className = `agent-message ${role}`;
    node.textContent = content;
    const messages = $("#template-agent-messages");
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
  }

  function positionTemplateAgent() {
    const bounds = popover.getBoundingClientRect();
    const width = bounds.width || Math.min(350, innerWidth - 24);
    const height = bounds.height || Math.min(430, innerHeight - 100);
    const sidebar = $(".editor-sidebar").getBoundingClientRect();
    const defaultX = innerWidth > 760 && sidebar.width ? sidebar.right + 14 : (innerWidth - width) / 2;
    const x = Math.max(12, Math.min(floatingPosition?.x ?? defaultX, innerWidth - width - 12));
    const y = Math.max(12, Math.min(floatingPosition?.y ?? (innerHeight - height) / 2, innerHeight - height - 12));
    Object.assign(popover.style, {left: `${x}px`, top: `${y}px`, right: "auto", bottom: "auto"});
    Object.assign(launcher.style, {left: `${Math.min(x, innerWidth - 130)}px`, top: `${y}px`, right: "auto", bottom: "auto"});
  }

  const agentHeader = popover.querySelector("header");
  let panelDrag = null;
  agentHeader.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest("button")) return;
    event.preventDefault();
    const rect = popover.getBoundingClientRect();
    panelDrag = {pointer: event.pointerId, x: event.clientX, y: event.clientY, left: rect.left, top: rect.top, moved: false};
    agentHeader.setPointerCapture(event.pointerId);
  });
  agentHeader.addEventListener("pointermove", (event) => {
    if (!panelDrag || event.pointerId !== panelDrag.pointer) return;
    const dx = event.clientX - panelDrag.x, dy = event.clientY - panelDrag.y;
    if (!panelDrag.moved && Math.hypot(dx, dy) < 5) return;
    panelDrag.moved = true;
    const rect = popover.getBoundingClientRect();
    floatingPosition = {x: Math.max(12, Math.min(panelDrag.left + dx, innerWidth - rect.width - 12)), y: Math.max(12, Math.min(panelDrag.top + dy, innerHeight - rect.height - 12))};
    positionTemplateAgent();
  });
  function finishPanelDrag(event) {
    if (!panelDrag || event.pointerId !== panelDrag.pointer) return;
    if (agentHeader.hasPointerCapture(event.pointerId)) agentHeader.releasePointerCapture(event.pointerId);
    if (panelDrag.moved) sessionStorage.setItem("careerTemplateAgentPosition", JSON.stringify(floatingPosition));
    panelDrag = null;
  }
  agentHeader.addEventListener("pointerup", finishPanelDrag);
  agentHeader.addEventListener("pointercancel", finishPanelDrag);
  window.addEventListener("resize", () => {
    if (!popover.classList.contains("hidden") || !launcher.classList.contains("hidden")) positionTemplateAgent();
  });

  async function openTemplateAgent() {
    popover.classList.remove("hidden");
    launcher.classList.add("hidden");
    positionTemplateAgent();
    requestAnimationFrame(() => {
      if (!floatingPosition && !popover.classList.contains("hidden")) positionTemplateAgent();
    });
    $("#template-agent-input").focus();
    if ($("#template-skill-picker").children.length) return;
    try {
      const result = await api("/api/design/skills");
      const picker = $("#template-skill-picker");
      const label = document.createElement("small");
      label.textContent = "本次调用技能（需手动选择）";
      picker.appendChild(label);
      for (const skill of result.skills) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = skill.name;
        button.title = skill.description;
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", () => {
          if (selectedSkills.has(skill.id)) selectedSkills.delete(skill.id);
          else selectedSkills.add(skill.id);
          button.setAttribute("aria-pressed", String(selectedSkills.has(skill.id)));
        });
        picker.appendChild(button);
      }
      if (!result.skills.length) label.textContent = "暂无可用设计技能";
      if (!floatingPosition) positionTemplateAgent();
    } catch (error) { toast(error.message); }
  }

  $("#minimize-template-agent").addEventListener("click", () => {
    popover.classList.add("hidden"); launcher.classList.remove("hidden");
  });
  $("#close-template-agent").addEventListener("click", () => {
    popover.classList.add("hidden"); launcher.classList.add("hidden");
  });
  launcher.addEventListener("click", openTemplateAgent);
  $("#add-custom-template").addEventListener("click", openTemplateAgent);

  function updateDesignLibrary(result) {
    state.designedTemplates = result.templates || [];
    state.designedTemplate = result.template || null;
    state.activeDesignId = result.active_design_id || null;
    state.templateProposal = result.proposal || null;
    state.templateId = result.template_id;
    if (result.messages) state.templateChat = result.messages;
    renderResumeEditor();
  }

  function setTemplateBusy(busy) {
    designing = busy;
    $("#template-agent-input").disabled = busy;
    const button = $("#template-agent-form button[type=submit]");
    button.disabled = busy;
    button.textContent = busy ? "处理中…" : "发送";
    $("#confirm-template-design").disabled = busy;
  }

  async function confirmTemplateDesign() {
    if (designing) return;
    if (!state.templateProposal) { toast("先描述想要的风格，收到方案后再确认"); return; }
    const proposalId = state.templateProposal.id;
    setTemplateBusy(true);
    templateMessage("user", "确认生成这个模板");
    try {
      await saveResume();
      const result = await api("/api/resume/template/confirm", {method: "POST", body: JSON.stringify({candidate_id: state.candidateId, template_id: proposalId})});
      templateHistoryRestored = true;
      updateDesignLibrary(result);
      await saveResume();
      templateMessage("assistant", `已生成「${state.designedTemplate.name}」并应用到简历。模板栏可反复选用，下面的「+ 自定义简历」可继续新增。`);
      toast("模板已生成并保存，Word / PDF 会使用该版式");
    } catch (error) { templateMessage("assistant error", error.message); }
    finally { setTemplateBusy(false); }
  }
  $("#confirm-template-design").addEventListener("click", confirmTemplateDesign);

  $("#saved-template-list").addEventListener("click", async (event) => {
    if (designing) return;
    const deleted = event.target.closest("[data-delete-design]");
    const selected = event.target.closest("[data-design-id]");
    if (!deleted && !selected) return;
    try {
      await saveResume();
      const result = deleted
        ? await api(`/api/resume/template/design?candidate_id=${encodeURIComponent(state.candidateId)}&template_id=${encodeURIComponent(deleted.dataset.deleteDesign)}`, {method: "DELETE"})
        : await api("/api/resume/template/select", {method: "POST", body: JSON.stringify({candidate_id: state.candidateId, template_id: selected.dataset.designId})});
      updateDesignLibrary(result);
      await saveResume();
      toast(deleted ? "模板已删除" : "已应用这个模板");
    } catch (error) { toast(error.message); }
  });

  $("#template-agent-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#template-agent-input");
    const message = input.value.trim();
    if (!message || designing) return;
    if (/^(确认(?:生成(?:模板)?)?|就用这个|采用这个方案)[吧。！!]*$/.test(message)) {
      if (state.templateProposal) input.value = "";
      await confirmTemplateDesign();
      return;
    }
    if (!selectedSkills.size) { toast("请先明确选择要调用的设计技能"); return; }
    setTemplateBusy(true);
    templateMessage("user", message);
    try {
      await saveResume();
      const result = await api("/api/resume/template/design", {method: "POST", body: JSON.stringify({
        candidate_id: state.candidateId, message, skill_ids: [...selectedSkills],
      })});
      state.templateProposal = result.proposal;
      templateMessage("assistant", `${result.proposal.name}：${result.proposal.description}\n\n满意后回复“确认”，或点击下方按钮，我再生成可选用的模板。`);
      state.templateChat = result.messages || [];
      templateHistoryRestored = true;
      input.value = "";
      $("#template-proposal-actions").classList.remove("hidden");
    } catch (error) { templateMessage("assistant error", error.message); }
    finally {
      setTemplateBusy(false);
    }
  });
  $("#template-agent-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault(); $("#template-agent-form").requestSubmit();
    }
  });

  $("#open-fine-editor").addEventListener("click", async () => {
    try { await saveResume(); showView("resume"); }
    catch { /* saveResume reports failures */ }
  });
  $$(".chat-download").forEach((button) => button.addEventListener("click", () => {
    $(`#view-resume .download-button[data-format="${button.dataset.format}"]`).click();
  }));
  new MutationObserver(() => { $("#chat-save-state").textContent = $("#save-state").textContent; })
    .observe($("#save-state"), {childList: true, characterData: true, subtree: true});
  window.CareerResumeStudio = {mount, refresh, openTemplateAgent};
  mount("chat");
})();
