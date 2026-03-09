/* ========================================
   PDFPilot - File handling and preview state
   ======================================== */

document.addEventListener("DOMContentLoaded", () => {
  const attachBtn = document.getElementById("attachBtn");
  const fileInput = document.getElementById("fileInput");
  const chatInput = document.getElementById("chatInput");
  const attachmentTray = document.getElementById("attachmentTray");
  const dragOverlay = document.getElementById("dragOverlay");
  const previewPlaceholder = document.getElementById("previewPlaceholder");
  const pdfViewer = document.getElementById("pdfViewer");
  const previewFileName = document.getElementById("previewFileName");
  const downloadBtn = document.getElementById("downloadBtn");
  const previewPanel = document.getElementById("previewPanel");
  const dashboardMain = document.getElementById("dashboardMain");

  if (!attachBtn || !fileInput) return;

  const MAX_FILE_SIZE = 25 * 1024 * 1024;
  const PDF_WORKER_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
  const API_BASE = window.location.protocol === "file:" ? "http://127.0.0.1:8000" : window.location.origin;
  const state = {
    attachedFiles: [],
    currentDownloadUrl: "",
    currentDownloadName: "",
  };

  attachBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      handleFiles(Array.from(fileInput.files));
      fileInput.value = "";
    }
  });

  if (attachmentTray) {
    attachmentTray.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-index]");
      if (removeButton) {
        removeAttachedFile(Number(removeButton.dataset.removeIndex));
        return;
      }

      const chip = event.target.closest("[data-index]");
      if (!chip) return;
      const file = state.attachedFiles[Number(chip.dataset.index)];
      if (file) {
        void previewLocalFile(file);
      }
    });
  }

  let dragCounter = 0;

  document.addEventListener("dragenter", (event) => {
    event.preventDefault();
    dragCounter += 1;
    if (dragOverlay) dragOverlay.classList.add("active");
  });

  document.addEventListener("dragleave", (event) => {
    event.preventDefault();
    dragCounter -= 1;
    if (dragCounter <= 0) {
      dragCounter = 0;
      if (dragOverlay) dragOverlay.classList.remove("active");
    }
  });

  document.addEventListener("dragover", (event) => event.preventDefault());

  document.addEventListener("drop", (event) => {
    event.preventDefault();
    dragCounter = 0;
    if (dragOverlay) dragOverlay.classList.remove("active");
    if (event.dataTransfer.files.length > 0) {
      handleFiles(Array.from(event.dataTransfer.files));
    }
  });

  function handleFiles(files) {
    const validFiles = files.filter((file) => {
      if (file.size <= MAX_FILE_SIZE) return true;
      alert(`"${file.name}" is larger than 25MB and was skipped.`);
      return false;
    });

    if (validFiles.length === 0) return;

    const existingKeys = new Set(state.attachedFiles.map((file) => `${file.name}-${file.size}-${file.lastModified}`));
    validFiles.forEach((file) => {
      const key = `${file.name}-${file.size}-${file.lastModified}`;
      if (!existingKeys.has(key)) {
        state.attachedFiles.push(file);
      }
    });

    renderPendingAttachments();
    updateChatPlaceholder();
    previewLocalFile(validFiles[0]);
  }

  function updateChatPlaceholder() {
    if (!chatInput) return;

    if (state.attachedFiles.length === 0) {
      chatInput.placeholder = "Tell PDFPilot what to do...";
      return;
    }

    if (state.attachedFiles.length === 1) {
      chatInput.placeholder = `What should I do with "${state.attachedFiles[0].name}"?`;
      chatInput.focus();
      return;
    }

    chatInput.placeholder = `What should I do with these ${state.attachedFiles.length} files?`;
    chatInput.focus();
  }

  function renderPendingAttachments() {
    if (!attachmentTray) return;

    if (state.attachedFiles.length === 0) {
      attachmentTray.innerHTML = "";
      attachmentTray.style.display = "none";
      return;
    }

    attachmentTray.style.display = "flex";
    attachmentTray.innerHTML = state.attachedFiles.map((file, index) => `
      <div class="attachment-chip" data-index="${index}">
        <i data-lucide="paperclip" style="width:14px;height:14px;"></i>
        <div class="attachment-chip-label">
          <div class="attachment-chip-name">${escapeHtml(file.name)}</div>
          <div class="attachment-chip-meta">${formatFileSize(file.size)}</div>
        </div>
        <button class="attachment-chip-remove" type="button" data-remove-index="${index}" aria-label="Remove ${escapeHtml(file.name)}">
          <i data-lucide="x" style="width:12px;height:12px;"></i>
        </button>
      </div>
    `).join("");

    if (window.lucide) window.lucide.createIcons();
  }

  function removeAttachedFile(index) {
    if (Number.isNaN(index) || index < 0 || index >= state.attachedFiles.length) return;

    state.attachedFiles.splice(index, 1);
    renderPendingAttachments();
    updateChatPlaceholder();

    if (state.attachedFiles.length > 0) {
      void previewLocalFile(state.attachedFiles[0]);
      return;
    }

    if (!state.currentDownloadUrl) {
      if (previewFileName) previewFileName.textContent = "Preview";
      showPlaceholder("Upload a file and run a command to see the result here.");
    }
  }

  function clearComposerAttachments() {
    state.attachedFiles = [];
    renderPendingAttachments();
    updateChatPlaceholder();
  }

  function ensurePreviewVisible() {
    if (previewPanel) previewPanel.classList.remove("hidden");
    if (dashboardMain) dashboardMain.classList.add("has-preview");
  }

  function showPlaceholder(message, shouldOpen = false) {
    if (shouldOpen) ensurePreviewVisible();
    if (previewPlaceholder) {
      previewPlaceholder.style.display = "block";
      const messageNodes = previewPlaceholder.querySelectorAll("p");
      if (messageNodes[1]) {
        messageNodes[1].textContent = message || "Upload a file to see the preview here.";
      }
    }
    if (pdfViewer) {
      pdfViewer.style.display = "none";
      pdfViewer.innerHTML = "";
    }
  }

  async function renderPdfSource(source) {
    if (!window.pdfjsLib || !pdfViewer) {
      showPlaceholder("PDF viewer is still loading.");
      return;
    }

    ensurePreviewVisible();
    pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_URL;

    try {
      const loadingTask = typeof source === "string"
        ? pdfjsLib.getDocument(source)
        : pdfjsLib.getDocument({ data: source });
      const pdf = await loadingTask.promise;

      if (previewPlaceholder) previewPlaceholder.style.display = "none";
      pdfViewer.style.display = "flex";
      pdfViewer.innerHTML = "";

      const maxPages = Math.min(pdf.numPages, 3);
      for (let pageNumber = 1; pageNumber <= maxPages; pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.2 });
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        await page.render({ canvasContext: context, viewport }).promise;
        pdfViewer.appendChild(canvas);
      }

      if (pdf.numPages > maxPages) {
        const more = document.createElement("p");
        more.style.cssText = "text-align:center;color:var(--text-tertiary);font-size:0.8rem;margin-top:8px;";
        more.textContent = `+ ${pdf.numPages - maxPages} more pages`;
        pdfViewer.appendChild(more);
      }
    } catch (error) {
      console.error("PDF render error:", error);
      showPlaceholder("Could not render the PDF preview.");
    }
  }

  async function previewLocalFile(file) {
    if (!file) {
      showPlaceholder("Attach a file to start.");
      return;
    }

    if (previewFileName) previewFileName.textContent = file.name;

    const ext = file.name.split(".").pop().toLowerCase();
    if (ext === "pdf") {
      const bytes = new Uint8Array(await file.arrayBuffer());
      await renderPdfSource(bytes);
      return;
    }

    if (["jpg", "jpeg", "png", "gif", "webp"].includes(ext)) {
      ensurePreviewVisible();
      if (previewPlaceholder) previewPlaceholder.style.display = "none";
      if (pdfViewer) {
        pdfViewer.style.display = "flex";
        pdfViewer.innerHTML = "";
        const img = document.createElement("img");
        img.style.cssText = "max-width:100%;border-radius:4px;box-shadow:var(--shadow-sm);";
        img.src = URL.createObjectURL(file);
        pdfViewer.appendChild(img);
      }
      return;
    }

    if (ext === "txt") {
      const text = await file.text();
      renderTextPreview(text);
      return;
    }

    showPlaceholder(`Preview is not available for .${ext} files before processing.`);
  }

  function renderTextPreview(text) {
    ensurePreviewVisible();
    if (previewPlaceholder) previewPlaceholder.style.display = "none";
    if (pdfViewer) {
      pdfViewer.style.display = "flex";
      pdfViewer.innerHTML = "";
      const pre = document.createElement("pre");
      pre.style.cssText = "width:100%;padding:16px;background:var(--bg-secondary);border-radius:8px;font-size:0.82rem;overflow:auto;white-space:pre-wrap;max-height:500px;border:1px solid var(--border);";
      pre.textContent = text;
      pdfViewer.appendChild(pre);
    }
  }

  function renderRemoteImageGallery(outputs) {
    ensurePreviewVisible();
    if (previewPlaceholder) previewPlaceholder.style.display = "none";
    if (!pdfViewer) return;

    pdfViewer.style.display = "grid";
    pdfViewer.style.gridTemplateColumns = "repeat(auto-fit, minmax(180px, 1fr))";
    pdfViewer.style.gap = "12px";
    pdfViewer.innerHTML = "";

    outputs.forEach((item) => {
      const card = document.createElement("div");
      card.style.cssText = "display:flex;flex-direction:column;gap:8px;";

      const img = document.createElement("img");
      img.src = resolveApiUrl(item.preview_url || item.output_url);
      img.alt = item.output;
      img.style.cssText = "width:100%;border-radius:8px;border:1px solid var(--border);box-shadow:var(--shadow-sm);";

      const label = document.createElement("div");
      label.style.cssText = "font-size:0.78rem;color:var(--text-secondary);word-break:break-word;";
      label.textContent = item.output;

      card.appendChild(img);
      card.appendChild(label);
      pdfViewer.appendChild(card);
    });
  }

  function renderRemoteFileList(outputs) {
    ensurePreviewVisible();
    if (previewPlaceholder) previewPlaceholder.style.display = "none";
    if (!pdfViewer) return;

    pdfViewer.style.display = "flex";
    pdfViewer.style.flexDirection = "column";
    pdfViewer.style.gap = "10px";
    pdfViewer.innerHTML = "";

    outputs.forEach((item) => {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid var(--border);border-radius:10px;background:var(--bg-secondary);";

      const meta = document.createElement("div");
      meta.style.cssText = "min-width:0;";

      const name = document.createElement("div");
      name.style.cssText = "font-size:0.84rem;font-weight:600;color:var(--text-primary);word-break:break-word;";
      name.textContent = item.output;

      const kind = document.createElement("div");
      kind.style.cssText = "font-size:0.76rem;color:var(--text-tertiary);margin-top:4px;";
      kind.textContent = (item.result_type || "file").replace("_", " ");

      meta.appendChild(name);
      meta.appendChild(kind);

      const actions = document.createElement("div");
      actions.style.cssText = "display:flex;gap:8px;flex-shrink:0;";

      if (item.preview_url) {
        const openLink = document.createElement("a");
        openLink.href = resolveApiUrl(item.preview_url);
        openLink.target = "_blank";
        openLink.rel = "noreferrer";
        openLink.textContent = "Open";
        openLink.style.cssText = "font-size:0.78rem;color:var(--primary);text-decoration:none;";
        actions.appendChild(openLink);
      }

      if (item.download_url) {
        const downloadLink = document.createElement("a");
        downloadLink.href = resolveApiUrl(item.download_url);
        downloadLink.target = "_blank";
        downloadLink.rel = "noreferrer";
        downloadLink.textContent = "Download";
        downloadLink.style.cssText = "font-size:0.78rem;color:var(--primary);text-decoration:none;";
        actions.appendChild(downloadLink);
      }

      row.appendChild(meta);
      row.appendChild(actions);
      pdfViewer.appendChild(row);
    });
  }

  function setDownloadTarget(url, filename) {
    state.currentDownloadUrl = url || "";
    state.currentDownloadName = filename || "";
  }

  function resolveApiUrl(path) {
    if (!path) return "";
    if (/^https?:\/\//i.test(path)) return path;
    return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  }

  async function showServerResult(result) {
    const primary = result.primary_output || result;
    if (!primary || !primary.output) {
      showPlaceholder("The server did not return a previewable result.");
      return;
    }

    if (previewFileName) previewFileName.textContent = primary.output;
    if (result.archive && result.archive.download_url) {
      setDownloadTarget(resolveApiUrl(result.archive.download_url), result.archive.output);
    } else if (result.result_type === "multi_file" && Array.isArray(result.outputs) && result.outputs.length > 1) {
      setDownloadTarget("", "");
    } else {
      setDownloadTarget(resolveApiUrl(primary.download_url), primary.output);
    }

    if (result.result_type === "image_gallery" && Array.isArray(result.outputs) && result.outputs.length > 0) {
      renderRemoteImageGallery(result.outputs);
      return;
    }

    if (result.result_type === "multi_file" && Array.isArray(result.outputs) && result.outputs.length > 1) {
      renderRemoteFileList(result.outputs);
      return;
    }

    const outputName = primary.output.toLowerCase();
    const previewResultType = primary.preview_result_type || primary.result_type || "";
    const previewMediaType = primary.preview_media_type || primary.media_type || "";
    if (previewResultType === "pdf" || previewMediaType.includes("pdf") || outputName.endsWith(".pdf")) {
      await renderPdfSource(resolveApiUrl(primary.preview_url));
      return;
    }

    if (previewResultType === "image" || previewMediaType.startsWith("image/")) {
      renderRemoteImageGallery([primary]);
      return;
    }

    if (previewResultType === "text" || previewMediaType.startsWith("text/") || outputName.endsWith(".txt")) {
      if (typeof result.extracted_text === "string" && result.extracted_text.length > 0) {
        renderTextPreview(result.extracted_text);
        return;
      }

      if (typeof result.text_preview === "string" && result.text_preview.length > 0) {
        renderTextPreview(result.text_preview);
        return;
      }

      try {
        const response = await fetch(resolveApiUrl(primary.preview_url));
        if (!response.ok) throw new Error("Preview request failed");
        const text = await response.text();
        renderTextPreview(text);
      } catch (error) {
        console.error("Text preview error:", error);
        showPlaceholder("The result was created, but the preview could not be loaded.");
      }
      return;
    }

    showPlaceholder("The result was created. Use Download to open the output file.");
  }

  function clearSession() {
    clearComposerAttachments();
    setDownloadTarget("", "");
    if (previewFileName) previewFileName.textContent = "Preview";
    showPlaceholder("Upload a file and run a command to see the result here.", false);
  }

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (state.currentDownloadUrl) {
        window.location.assign(state.currentDownloadUrl);
        return;
      }

      const localFile = state.attachedFiles[0];
      if (localFile) {
        const anchor = document.createElement("a");
        anchor.href = URL.createObjectURL(localFile);
        anchor.download = localFile.name;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      }
    });
  }

  window.PDFPilotApp = {
    getAttachedFiles: () => [...state.attachedFiles],
    getPrimaryFile: () => state.attachedFiles[0] || null,
    clearComposerAttachments,
    clearSession,
    previewLocalFile,
    showServerResult,
    resolveApiUrl,
  };

  renderPendingAttachments();
  updateChatPlaceholder();
  showPlaceholder("Upload a file and run a command to see the result here.", false);

  function formatFileSize(bytes) {
    const sizeInMb = bytes / (1024 * 1024);
    if (sizeInMb >= 1) return `${sizeInMb.toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }
});
