/* Independently installable so an active conversation can receive an update without reload. */
(() => {
  function createReplyFormatter() {
    const seen = new Set();
    return (content) => {
      let text = String(content || "");
      const once = (key, expression, replacement = "") => {
        if (!expression.test(text)) return;
        expression.lastIndex = 0;
        if (seen.has(key)) text = text.replace(expression, replacement);
        seen.add(key);
      };
      once("required-intro", /为了生成可用的简历，[还仍]*(?:需要|需)[：:]/g, "还需要：");
      once("answer-hint", /你可以直接用一句话回答[；;，,。]?/g);
      once("refusal-hint", /不想提供的项目也可以直接告诉我跳过[。]?/g);
      once("optional-intro", /(?:基础|必填)信息已经(?:整理好|收齐)。接下来补充可选信息[（(]\d+\/\d+[）)][：:]/g);
      once("skip-current", /[；;]?没有可以回复[“"]跳过[”"]。[ ]?/g);
      once("skip-all", /也可以回复[“"]全部跳过[”"]。[ ]?/g);
      return text.replace(/[ \t]{2,}/g, " ").replace(/^[；;，,\s]+/, "").trim();
    };
  }

  function filesFromTransfer(transfer) {
    if (!transfer) return [];
    const files = [...(transfer.files || [])];
    for (const item of [...(transfer.items || [])]) {
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    const seen = new Set();
    return files.filter(file => {
      const key = `${file.name}|${file.size}|${file.lastModified}|${file.type}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("无法读取文件"));
      reader.onabort = () => reject(new Error("文件读取已取消"));
      reader.readAsDataURL(file);
    });
  }

  function createFileQueue({getQueue, setQueue, notify, readFile = readFileAsDataURL}) {
    let chain = Promise.resolve();
    let batches = 0;
    const enqueue = (files) => {
      const incoming = [...files];
      batches += 1;
      chain = chain.then(async () => {
        for (const file of incoming) {
          const extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[file.type];
          const filename = file.name || `粘贴图片-${Date.now()}.${extension || "png"}`;
          if (!/\.(docx|pdf|txt|md|png|jpe?g|webp)$/i.test(filename)) {
            notify(`${filename}：支持照片、Word、PDF 和文本文件`);
            continue;
          }
          if (file.size > 10 * 1024 * 1024) {
            notify(`${filename} 超过 10MB，请压缩后再添加`);
            continue;
          }
          if (getQueue().length >= 5) {
            notify("每次最多添加 5 个文件，请先发送或移除已有文件");
            break;
          }
          try {
            const dataUrl = await readFile(file);
            const pending = getQueue();
            if (!pending.some(item => item.data_url === dataUrl)) {
              setQueue([...pending, {filename: filename.slice(0, 200), data_url: dataUrl}]);
            }
          } catch {
            notify(`${filename} 读取失败，请重新拖入或粘贴`);
          }
        }
      }).finally(() => { batches -= 1; });
      return chain;
    };
    enqueue.whenIdle = () => chain;
    enqueue.isBusy = () => batches > 0;
    return enqueue;
  }

  function install({root, fileInput, form, messages, queueNode, getQueue, setQueue, notify}) {
    const enqueueFiles = createFileQueue({getQueue, setQueue, notify});
    form.before(queueNode);
    const bindings = [];
    const on = (target, name, handler, options) => {
      target.addEventListener(name, handler, options);
      bindings.push(() => target.removeEventListener(name, handler, options));
    };
    const hint = document.createElement("div");
    hint.className = "attachment-drop-hint hidden";
    hint.setAttribute("role", "status");
    hint.textContent = "松开以添加照片或简历";
    root.appendChild(hint);
    let dragDepth = 0;
    const hasFiles = event => [...(event.dataTransfer?.types || [])].includes("Files")
      || [...(event.dataTransfer?.items || [])].some(item => item.kind === "file");
    const setDragging = active => {
      root.classList.toggle("dragging-attachments", active);
      hint.classList.toggle("hidden", !active);
    };
    on(root, "dragenter", event => {
      if (!hasFiles(event)) return;
      event.preventDefault(); dragDepth += 1; setDragging(true);
    });
    on(root, "dragover", event => {
      if (!hasFiles(event)) return;
      event.preventDefault(); event.dataTransfer.dropEffect = "copy"; setDragging(true);
    });
    on(root, "dragleave", event => {
      if (!hasFiles(event)) return;
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) setDragging(false);
    });
    on(root, "drop", event => {
      if (!hasFiles(event)) return;
      event.preventDefault(); event.stopPropagation(); dragDepth = 0; setDragging(false);
      enqueueFiles(filesFromTransfer(event.dataTransfer));
    });
    on(root, "paste", event => {
      const files = filesFromTransfer(event.clipboardData);
      if (!files.length) return; // Keep normal text paste and native keyboard shortcuts.
      const text = event.clipboardData?.getData("text/plain");
      if (!text) event.preventDefault();
      enqueueFiles(files);
    });
    on(fileInput, "change", event => {
      event.stopImmediatePropagation(); // Also replaces the old handler during a live update.
      enqueueFiles([...event.target.files]);
      event.target.value = "";
    }, true);
    let waitingToSubmit = false;
    on(form, "submit", async event => {
      if (!enqueueFiles.isBusy()) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (waitingToSubmit) return;
      waitingToSubmit = true;
      try { await enqueueFiles.whenIdle(); }
      finally { waitingToSubmit = false; }
      form.requestSubmit();
    }, true);
    const decorateQueue = () => {
      [...queueNode.children].forEach((chip, index) => {
        const attachment = getQueue()[index];
        if (!attachment) return;
        const label = [...chip.childNodes].find(node => node.nodeType === 3);
        if (label) {
          const filename = document.createElement("span");
          filename.className = "upload-file-name";
          filename.textContent = label.textContent;
          filename.title = attachment.filename;
          label.replaceWith(filename);
        }
        if (/^data:image\/(png|jpeg|webp);/i.test(attachment.data_url) && !chip.querySelector("img")) {
          const thumbnail = document.createElement("img");
          thumbnail.src = attachment.data_url;
          thumbnail.alt = attachment.filename;
          thumbnail.className = "upload-thumbnail";
          chip.prepend(thumbnail);
        }
      });
    };
    const queueObserver = new MutationObserver(decorateQueue);
    queueObserver.observe(queueNode, {childList: true});
    decorateQueue();
    const format = createReplyFormatter();
    const processed = new WeakSet();
    const compactMessages = () => {
      messages.querySelectorAll(".intake-message.assistant").forEach(node => {
        if (processed.has(node)) return;
        processed.add(node);
        const text = format(node.textContent);
        if (text !== node.textContent) node.textContent = text;
      });
    };
    const messageObserver = new MutationObserver(compactMessages);
    messageObserver.observe(messages, {childList: true});
    compactMessages();
    return {
      enqueueFiles,
      dispose() {
        bindings.forEach(remove => remove());
        queueObserver.disconnect(); messageObserver.disconnect(); hint.remove();
        root.classList.remove("dragging-attachments");
      },
    };
  }

  const api = {createReplyFormatter, filesFromTransfer, createFileQueue, install};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") {
    window.CareerIntakeInteractions?.instance?.dispose();
    window.CareerIntakeInteractions = api;
    const root = document.querySelector("#view-profile");
    if (root && typeof state !== "undefined") {
      api.instance = install({
        root, fileInput: document.querySelector("#intake-files"),
        form: document.querySelector("#intake-chat-form"),
        messages: document.querySelector("#intake-messages"),
        queueNode: document.querySelector("#upload-queue"),
        getQueue: () => state.intakeAttachments,
        setQueue: files => { state.intakeAttachments = files; renderUploadQueue(); },
        notify: message => toast(message),
      });
    }
  }
})();
