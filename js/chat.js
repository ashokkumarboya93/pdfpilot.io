/* ========================================
   PDFPilot - Chat logic with backend-driven routing
   ======================================== */

document.addEventListener("DOMContentLoaded", () => {
  const chatMessages = document.getElementById("chatMessages");
  const chatInput = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const newChatBtn = document.getElementById("newChatBtn");
  const chatWelcome = document.getElementById("chatWelcome");
  const chatSuggestions = document.getElementById("chatSuggestions");

  if (!chatMessages || !chatInput || !sendBtn) return;

  let isProcessing = false;
  let activityCounter = 0;

  function addUserMessage(text, files = []) {
    if (chatWelcome) chatWelcome.style.display = "none";

    const attachmentsHtml = files.length > 0
      ? `
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
          ${files.map((file) => `
            <div style="display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:14px;background:rgba(15,23,42,0.06);font-size:0.76rem;max-width:100%;">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-8.49 8.49a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.5 3.5 0 0 1 4.95 4.95l-9.2 9.19a1.5 1.5 0 0 1-2.12-2.12l8.49-8.48"/></svg>
              <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:180px;">${escapeHtml(file.name)}</span>
            </div>
          `).join("")}
        </div>
      `
      : "";

    const row = document.createElement("div");
    row.className = "message-row user-row animate-fade-in-up";
    row.innerHTML = `
      <div class="message-content">
        <div class="message-icon">JD</div>
        <div class="message-text">${attachmentsHtml}<div>${escapeHtml(text)}</div></div>
      </div>
    `;
    chatMessages.appendChild(row);
    scrollToBottom();
  }

  function addSystemMessage(html, animate = false) {
    const row = document.createElement("div");
    row.className = "message-row system-row animate-fade-in-up";
    row.innerHTML = `
      <div class="message-content">
        <div class="message-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 18h.01"/><path d="M18 18h.01"/><path d="M2 14l3.13-6.27a2 2 0 0 1 1.79-1.11h10.16a2 2 0 0 1 1.79 1.11L22 14"/></svg>
        </div>
        <div class="message-text"></div>
      </div>
    `;
    const textContainer = row.querySelector(".message-text");
    chatMessages.appendChild(row);
    scrollToBottom();

    if (animate) {
      typewriteHtml(textContainer, html, 15);
    } else {
      textContainer.innerHTML = html;
      if (window.lucide) window.lucide.createIcons();
    }
    return row;
  }

  async function typewriteHtml(container, html, speed = 15) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const nodes = Array.from(doc.body.childNodes);
    container.innerHTML = "";

    async function typeNode(node, parent) {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent;
        const textNode = document.createTextNode("");
        parent.appendChild(textNode);
        for (let i = 0; i < text.length; i++) {
          textNode.textContent += text[i];
          scrollToBottom();
          await new Promise((r) => setTimeout(r, speed));
        }
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const el = document.createElement(node.tagName);
        for (const attr of node.attributes) {
          el.setAttribute(attr.name, attr.value);
        }
        parent.appendChild(el);
        for (const child of Array.from(node.childNodes)) {
          await typeNode(child, el);
        }
      }
    }

    for (const node of nodes) {
      await typeNode(node, container);
    }
    if (window.lucide) window.lucide.createIcons();
  }

  function createActivityCard(label, steps) {
    const idPrefix = `activity-${activityCounter++}`;
    const stepsHtml = steps
      .map(
        (step, index) => `
          <div class="activity-step" id="${idPrefix}-step-${index}">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/></svg>
            ${escapeHtml(step)}
          </div>
        `
      )
      .join("");

    addSystemMessage(`
      <p>Processing your request.</p>
      <div class="activity-card">
        <div class="activity-card-header">
          <div class="activity-spinner" id="${idPrefix}-spinner"></div>
          <span id="${idPrefix}-label">${escapeHtml(label)}</span>
        </div>
        <div class="activity-steps">${stepsHtml}</div>
      </div>
    `);

    return {
      markDone(index) {
        const step = document.getElementById(`${idPrefix}-step-${index}`);
        if (!step || step.classList.contains("done")) return;
        step.classList.add("done");
        step.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          ${escapeHtml(steps[index])}
        `;
      },
      complete(finalLabel) {
        const labelNode = document.getElementById(`${idPrefix}-label`);
        const spinner = document.getElementById(`${idPrefix}-spinner`);
        if (labelNode && finalLabel) labelNode.textContent = finalLabel;
        if (spinner) spinner.style.display = "none";
      },
      fail(message) {
        const labelNode = document.getElementById(`${idPrefix}-label`);
        const spinner = document.getElementById(`${idPrefix}-spinner`);
        if (labelNode) labelNode.textContent = message;
        if (spinner) spinner.style.display = "none";
      },
    };
  }

  function buildResultMessage(result, files) {
    const primary = result.primary_output || result;
    const appState = window.PDFPilotApp;
    const resolveApiUrl = appState && typeof appState.resolveApiUrl === "function"
      ? appState.resolveApiUrl
      : (value) => value;
    const previewUrl = primary && primary.preview_url ? resolveApiUrl(primary.preview_url) : "";
    const hasMultiFileList = result.result_type === "multi_file"
      && Array.isArray(result.outputs)
      && result.outputs.length > 1
      && !result.archive;
    const downloadTarget = hasMultiFileList
      ? ""
      : (result.archive ? result.archive.download_url : (primary ? primary.download_url : ""));
    const downloadUrl = downloadTarget ? resolveApiUrl(downloadTarget) : "";
    const previewLink = !hasMultiFileList && previewUrl
      ? `<a href="${previewUrl}" target="_blank" rel="noreferrer">Open preview</a>`
      : "";
    const downloadLink = downloadUrl
      ? `<a href="${downloadUrl}" target="_blank" rel="noreferrer">Download result</a>`
      : "";
    const links = [previewLink, downloadLink].filter(Boolean).join(" | ");
    const operation = result.operation;
    const intents = Array.isArray(result.intents) ? result.intents : (result.intent ? [result.intent] : []);
    const pipelineLabel = intents.length > 1 ? `<p>Pipeline: ${escapeHtml(intents.join(" -> "))}</p>` : "";

    if (operation === "convert_to_pdf" || operation === "images_to_pdf" || operation === "text_to_pdf") {
      return `${pipelineLabel}<p>Converted your content to PDF. The preview panel has been updated.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "extract_images" || operation === "pdf_to_images") {
      const count = Array.isArray(result.outputs) ? result.outputs.length : 0;
      return `${pipelineLabel}<p>Converted the PDF into ${count} image file${count === 1 ? "" : "s"}.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "pdf_to_word") {
      const targetExtension = (result.target_extension || ".docx").replace(".", "").toUpperCase();
      return `${pipelineLabel}<p>Converted the PDF into a ${targetExtension} document.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "merge_pdf" || operation === "merge_pdfs") {
      return `${pipelineLabel}<p>Merged ${result.merged_count} PDF files into one document.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "split_pdf") {
      if (hasMultiFileList) {
        return `${pipelineLabel}<p>Split complete. ${result.parts || 0} output file${result.parts === 1 ? "" : "s"} created. Use the preview panel to open or download each part.</p>`;
      }
      return `${pipelineLabel}<p>Split complete. ${result.parts || 0} output file${result.parts === 1 ? "" : "s"} created.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "extract_pages") {
      if (result.output_type === "image") {
        const count = Array.isArray(result.outputs) ? result.outputs.length : 0;
        return `${pipelineLabel}<p>Extracted page ${escapeHtml(result.page_selection || "")} as ${count} image file${count === 1 ? "" : "s"}.</p><p style="margin-top:8px;">${links}</p>`;
      }
      return `${pipelineLabel}<p>Created a PDF for page selection ${escapeHtml(result.page_selection || "")}.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "compress_pdf") {
      return `${pipelineLabel}<p>Compression complete. File size reduced by ${result.reduction_pct}%.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "create_zip" || operation === "archive_files") {
      return `${pipelineLabel}<p>Created a ZIP archive from ${result.archived_count || 0} file${result.archived_count === 1 ? "" : "s"}.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "extract_zip" || operation === "extract_archive") {
      if (hasMultiFileList) {
        return `${pipelineLabel}<p>Extracted ${result.extracted_count || 0} file${result.extracted_count === 1 ? "" : "s"} from the ZIP archive. Use the preview panel to open or download each extracted file.</p>`;
      }
      return `${pipelineLabel}<p>Extracted ${result.extracted_count || 0} file${result.extracted_count === 1 ? "" : "s"} from the ZIP archive.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "extract_text") {
      const extractedText = escapeHtml(result.extracted_text || result.text_preview || "");
      return `${pipelineLabel}<p>Extracted all text from <strong>${escapeHtml(files[0].name)}</strong> and saved it as a .txt file.</p><p style="margin-top:8px;">${links}</p><pre style="margin-top:10px;white-space:pre-wrap;background:var(--bg-secondary);padding:12px;border-radius:8px;border:1px solid var(--border);font-size:0.8rem;max-height:320px;overflow:auto;">${extractedText}</pre>`;
    }

    if (operation === "rotate_pdf") {
      return `${pipelineLabel}<p>Rotated the PDF by ${result.rotation} degrees.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "add_watermark") {
      return `${pipelineLabel}<p>Added the watermark "${escapeHtml(result.watermark_text || "PDFPilot")}" to the PDF.</p><p style="margin-top:8px;">${links}</p>`;
    }

    if (operation === "remove_pages") {
      return `${pipelineLabel}<p>Removed pages ${escapeHtml(result.removed_pages || "")} from the PDF.</p><p style="margin-top:8px;">${links}</p>`;
    }

    return `${pipelineLabel}<p>The routed tool completed successfully.</p><p style="margin-top:8px;">${links}</p>`;
  }

  function activityStepsFor(files) {
    return [
      files.length > 0 ? "Uploading files" : "Preparing request",
      "Routing command",
      "Generating output",
    ];
  }

  async function processCommand(text, files) {
    const appState = window.PDFPilotApp;
    if (files.length === 0) {
      addSystemMessage("<p>Attach one or more files first. The current UI is file-driven.</p>", true);
      return;
    }

    const activity = createActivityCard("Routing request", activityStepsFor(files));
    activity.markDone(0);

    const formData = new FormData();
    formData.append("command", text);
    files.forEach((file) => formData.append("files", file));

    const resolveApiUrl = appState && typeof appState.resolveApiUrl === "function"
      ? appState.resolveApiUrl
      : (value) => value;
    const response = await fetch(resolveApiUrl("/api/process"), {
      method: "POST",
      body: formData,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      activity.fail("Processing failed");
      throw new Error(payload.detail || "The request failed");
    }

    activity.markDone(1);
    activity.markDone(2);
    activity.complete(payload.operation || "Completed");

    if (appState) {
      await appState.showServerResult(payload);
    }

    if (appState && typeof appState.clearComposerAttachments === "function") {
      appState.clearComposerAttachments();
    }

    addSystemMessage(buildResultMessage(payload, files), true);
  }

  async function sendMessage() {
    const text = chatInput.value.trim();
    if (isProcessing) return;

    const appState = window.PDFPilotApp;
    const files = appState ? appState.getAttachedFiles() : [];
    if (!text && files.length === 0) return;
    if (!text && files.length > 0) {
      addSystemMessage("<p>Add a prompt with your file so the router knows what to do.</p>", true);
      return;
    }

    addUserMessage(text, files);
    chatInput.value = "";
    chatInput.style.height = "auto";
    isProcessing = true;
    sendBtn.disabled = true;

    try {
      await processCommand(text, files);
    } catch (error) {
      console.error("Command error:", error);
      addSystemMessage(`<p>${escapeHtml(error.message || "Something went wrong while processing your file.")}</p>`, true);
    } finally {
      isProcessing = false;
      sendBtn.disabled = false;
    }
  }

  sendBtn.addEventListener("click", () => {
    void sendMessage();
  });

  chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  });

  chatInput.addEventListener("input", function onInput() {
    this.style.height = "auto";
    this.style.height = `${this.scrollHeight}px`;
  });

  if (chatSuggestions) {
    chatSuggestions.addEventListener("click", (event) => {
      const chip = event.target.closest(".chat-suggestion");
      if (!chip) return;
      chatInput.value = chip.dataset.msg || "";
      void sendMessage();
    });
  }

  if (newChatBtn) {
    newChatBtn.addEventListener("click", () => {
      chatMessages.innerHTML = "";
      if (chatWelcome) {
        chatWelcome.style.display = "flex";
        chatMessages.appendChild(chatWelcome);
      }
      chatInput.value = "";
      chatInput.style.height = "auto";
      if (window.PDFPilotApp) {
        window.PDFPilotApp.clearSession();
      }
    });
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }
});
