/**
 * LTX-Video Studio Web GUI Logic
 * Vanilla JavaScript managing state, real-time SSE progress, uploads, and playback.
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let currentMode = "image-to-video"; // 'image-to-video' | 'text-to-video'
  let selectedFile = null;
  let activeEventSource = null;

  // DOM Elements - Navigation & Modes
  const tabI2V = document.getElementById("tabImageToVideo");
  const tabT2V = document.getElementById("tabTextToVideo");
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  const dropzoneContent = document.getElementById("dropzoneContent");
  const imagePreviewContainer = document.getElementById("imagePreviewContainer");
  const imagePreview = document.getElementById("imagePreview");
  const btnRemoveImage = document.getElementById("btnRemoveImage");

  // DOM Elements - Form Inputs
  const genForm = document.getElementById("generationForm");
  const promptInput = document.getElementById("promptInput");
  const negPromptInput = document.getElementById("negPromptInput");
  const durationSlider = document.getElementById("durationSlider");
  const durationVal = document.getElementById("durationVal");
  const widthInput = document.getElementById("widthInput");
  const heightInput = document.getElementById("heightInput");
  const ratioBtns = document.querySelectorAll(".ratio-btn");
  const presetChips = document.querySelectorAll(".preset-chip");
  const cfgSlider = document.getElementById("cfgSlider");
  const cfgVal = document.getElementById("cfgVal");
  const seedInput = document.getElementById("seedInput");
  const randomizeSeedCheckbox = document.getElementById("randomizeSeedCheckbox");
  const improveTextureCheckbox = document.getElementById("improveTextureCheckbox");
  const advancedAccordion = document.getElementById("advancedAccordion");
  const accordionHeader = document.getElementById("accordionHeader");
  const btnGenerate = document.getElementById("btnGenerate");

  // DOM Elements - Output & Player
  const placeholderView = document.getElementById("placeholderView");
  const progressContainer = document.getElementById("progressContainer");
  const progressTitle = document.getElementById("progressTitle");
  const progressBadge = document.getElementById("progressBadge");
  const progressBarFill = document.getElementById("progressBarFill");
  const progressLogs = document.getElementById("progressLogs");
  const videoWrapper = document.getElementById("videoWrapper");
  const videoPlayer = document.getElementById("videoPlayer");
  const btnDownload = document.getElementById("btnDownload");
  const btnCopyLink = document.getElementById("btnCopyLink");
  const galleryGrid = document.getElementById("galleryGrid");

  // DOM Elements - Status
  const statusIndicator = document.getElementById("statusIndicator");
  const statusText = document.getElementById("statusText");
  const pulseDot = document.getElementById("pulseDot");

  // ─── Mode Switching ──────────────────────────────────────────────────────────
  tabI2V.addEventListener("click", () => {
    currentMode = "image-to-video";
    tabI2V.classList.add("active");
    tabT2V.classList.remove("active");
    dropzone.style.display = "block";
    btnGenerate.querySelector(".btn-text").textContent = "Generate Image-to-Video";
  });

  tabT2V.addEventListener("click", () => {
    currentMode = "text-to-video";
    tabT2V.classList.add("active");
    tabI2V.classList.remove("active");
    dropzone.style.display = "none";
    btnGenerate.querySelector(".btn-text").textContent = "Generate Text-to-Video";
  });

  // ─── File Upload & Drag-and-Drop ──────────────────────────────────────────
  dropzone.addEventListener("click", () => fileInput.click());

  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });

  dropzone.addEventListener("dragleave", () => {
    dropzone.classList.remove("dragover");
  });

  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleImageSelection(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleImageSelection(e.target.files[0]);
    }
  });

  btnRemoveImage.addEventListener("click", (e) => {
    e.stopPropagation();
    clearSelectedImage();
  });

  function handleImageSelection(file) {
    if (!file.type.startsWith("image/")) {
      showToast("Please select a valid image file (PNG, JPG, WebP)", "error");
      return;
    }
    selectedFile = file;
    const reader = new FileReader();
    reader.onload = (e) => {
      imagePreview.src = e.target.result;
      dropzoneContent.style.display = "none";
      imagePreviewContainer.style.display = "block";

      // Detect natural dimensions to compute matching aspect ratio
      const img = new Image();
      img.onload = () => {
        calculateBestDimensions(img.naturalWidth, img.naturalHeight);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  function clearSelectedImage() {
    selectedFile = null;
    fileInput.value = "";
    imagePreview.src = "";
    dropzoneContent.style.display = "flex";
    imagePreviewContainer.style.display = "none";
  }

  function calculateBestDimensions(naturalWidth, naturalHeight) {
    const ratio = naturalWidth / naturalHeight;
    let w, h;
    if (ratio >= 1.5) {
      // ~16:9
      w = 704; h = 384;
    } else if (ratio <= 0.65) {
      // ~9:16
      w = 384; h = 704;
    } else if (ratio >= 1.15 && ratio < 1.5) {
      // ~4:3
      w = 704; h = 512;
    } else {
      // ~1:1
      w = 512; h = 512;
    }
    widthInput.value = w;
    heightInput.value = h;
    highlightMatchingRatio(w, h);
  }

  // ─── Sliders & Presets ─────────────────────────────────────────────────────
  durationSlider.addEventListener("input", (e) => {
    durationVal.textContent = `${parseFloat(e.target.value).toFixed(1)}s`;
  });

  cfgSlider.addEventListener("input", (e) => {
    cfgVal.textContent = parseFloat(e.target.value).toFixed(1);
  });

  ratioBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      ratioBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const w = parseInt(btn.dataset.w);
      const h = parseInt(btn.dataset.h);
      if (w && h) {
        widthInput.value = w;
        heightInput.value = h;
      }
    });
  });

  function highlightMatchingRatio(w, h) {
    ratioBtns.forEach((b) => {
      if (parseInt(b.dataset.w) === w && parseInt(b.dataset.h) === h) {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    });
  }

  presetChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      promptInput.value = chip.dataset.prompt;
      promptInput.focus();
    });
  });

  accordionHeader.addEventListener("click", () => {
    advancedAccordion.classList.toggle("open");
  });

  // ─── Generation Execution ─────────────────────────────────────────────────
  genForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const promptText = promptInput.value.trim();
    if (!promptText) {
      showToast("Please enter an animation prompt", "error");
      return;
    }

    if (currentMode === "image-to-video" && !selectedFile) {
      showToast("Please upload an input image for Image-to-Video mode", "error");
      return;
    }

    // Set UI to loading state
    setGeneratingState(true);

    const formData = new FormData();
    formData.append("prompt", promptText);
    formData.append("negative_prompt", negPromptInput.value.trim());
    formData.append("duration", durationSlider.value);
    formData.append("width", widthInput.value);
    formData.append("height", heightInput.value);
    formData.append("guidance_scale", cfgSlider.value);
    formData.append("improve_texture", improveTextureCheckbox.checked);
    formData.append("seed", seedInput.value || 42);
    formData.append("randomize_seed", randomizeSeedCheckbox.checked);

    if (currentMode === "image-to-video" && selectedFile) {
      formData.append("image", selectedFile);
    }

    try {
      logMessage("[*] Submitting task to LTX-Video engine...");
      const resp = await fetch("/api/generate", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || `Server returned ${resp.status}`);
      }

      const { task_id } = await resp.json();
      logMessage(`[+] Task accepted (ID: ${task_id.substring(0, 8)}...). Connecting to stream...`);
      subscribeToProgress(task_id);
    } catch (err) {
      showToast(err.message, "error");
      logMessage(`[!] Error: ${err.message}`);
      setGeneratingState(false);
    }
  });

  function subscribeToProgress(taskId) {
    if (activeEventSource) {
      activeEventSource.close();
    }

    activeEventSource = new EventSource(`/api/progress/${taskId}`);

    activeEventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleSSEEvent(data);
      } catch (err) {
        console.error("SSE parse error", err);
      }
    };

    activeEventSource.onerror = (err) => {
      console.warn("SSE stream error/reconnect", err);
    };
  }

  function handleSSEEvent(event) {
    const type = event.type;

    if (type === "estimation") {
      const rank = event.rank !== undefined ? event.rank + 1 : 1;
      const total = event.queue_size || 1;
      const eta = event.eta ? `${event.eta.toFixed(1)}s` : "estimating";
      progressTitle.textContent = "Waiting in Queue";
      progressBadge.textContent = `Queue #${rank}/${total} • ETA: ${eta}`;
      logMessage(`[*] Queue position: ${rank}/${total} (ETA: ${eta})`);
    } else if (type === "process_starts") {
      progressTitle.textContent = "Generating Video on GPU";
      progressBadge.textContent = "Active";
      progressBarFill.style.width = "10%";
      logMessage("[*] GPU inference started...");
    } else if (type === "progress") {
      const idx = event.index || 0;
      const total = event.total || 1;
      const percent = Math.min(Math.max(event.percent || Math.round((idx / total) * 100), 5), 98);
      progressBarFill.style.width = `${percent}%`;
      progressBadge.textContent = `Step ${idx}/${total} (${percent}%)`;
      progressTitle.textContent = "Rendering Diffusion Steps";
      logMessage(`[*] Rendering step ${idx}/${total} (${percent}%)`);
    } else if (type === "completed") {
      progressBarFill.style.width = "100%";
      progressBadge.textContent = "100% Completed";
      logMessage(`[+] Video generated successfully: ${event.filename}`);
      showToast("Video generated successfully!", "success");

      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }

      displayCompletedVideo(event.video_url, event.filename);
      setGeneratingState(false);
      loadGallery();
    } else if (type === "error") {
      logMessage(`[!] Error: ${event.message}`);
      showToast(event.message, "error");
      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }
      setGeneratingState(false);
    }
  }

  function setGeneratingState(isGenerating) {
    btnGenerate.disabled = isGenerating;
    if (isGenerating) {
      placeholderView.style.display = "none";
      videoWrapper.style.display = "none";
      progressContainer.style.display = "flex";
      progressBarFill.style.width = "2%";
      progressLogs.innerHTML = "";
    } else {
      btnGenerate.disabled = false;
    }
  }

  function displayCompletedVideo(url, filename) {
    progressContainer.style.display = "none";
    videoWrapper.style.display = "flex";
    videoPlayer.src = url;
    videoPlayer.load();
    videoPlayer.play().catch(() => {});

    btnDownload.onclick = () => {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "video.mp4";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    };

    btnCopyLink.onclick = () => {
      const fullUrl = window.location.origin + url;
      navigator.clipboard.writeText(fullUrl).then(() => {
        showToast("Video link copied to clipboard!", "success");
      });
    };
  }

  function logMessage(msg) {
    const line = document.createElement("div");
    line.textContent = msg;
    progressLogs.appendChild(line);
    progressLogs.scrollTop = progressLogs.scrollHeight;
  }

  // ─── Video Gallery ─────────────────────────────────────────────────────────
  async function loadGallery() {
    try {
      const resp = await fetch("/api/videos");
      if (!resp.ok) return;
      const data = await resp.json();
      const videos = data.videos || [];

      galleryGrid.innerHTML = "";
      if (videos.length === 0) {
        galleryGrid.innerHTML = '<p style="color: #64748b; font-size: 0.85rem; grid-column: 1/-1;">No saved videos yet.</p>';
        return;
      }

      videos.forEach((vid) => {
        const item = document.createElement("div");
        item.className = "gallery-item";
        item.innerHTML = `
          <video class="gallery-video" src="${vid.url}#t=0.1" muted preload="metadata"></video>
          <div class="gallery-meta">
            <span>${vid.size_mb} MB</span>
            <span>${vid.created_at.split(" ")[1] || ""}</span>
          </div>
          <button class="gallery-delete" title="Delete Video">✕</button>
        `;

        // Click to play in main viewer
        item.addEventListener("click", () => {
          displayCompletedVideo(vid.url, vid.filename);
        });

        // Delete action
        const delBtn = item.querySelector(".gallery-delete");
        delBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (confirm(`Delete ${vid.filename}?`)) {
            await fetch(`/api/videos/${vid.filename}`, { method: "DELETE" });
            loadGallery();
          }
        });

        galleryGrid.appendChild(item);
      });
    } catch (err) {
      console.error("Failed to load gallery", err);
    }
  }

  // ─── Status Health Check ───────────────────────────────────────────────────
  async function checkSpaceStatus() {
    try {
      const resp = await fetch("/api/status");
      if (!resp.ok) throw new Error("Status endpoint error");
      const data = await resp.json();

      if (data.online) {
        pulseDot.className = "pulse-dot";
        statusText.textContent = "LTX Engine Online";
      } else {
        pulseDot.className = "pulse-dot waking";
        statusText.textContent = "Engine Waking Up";
      }
    } catch (err) {
      pulseDot.className = "pulse-dot offline";
      statusText.textContent = "Engine Offline";
    }
  }

  // Toast Notification
  function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${type === "success" ? "✓" : type === "error" ? "⚠" : "ℹ"}</span><span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => container.removeChild(toast), 300);
    }, 4000);
  }

  // Initial calls
  checkSpaceStatus();
  loadGallery();
  setInterval(checkSpaceStatus, 30000); // Check every 30s
});
