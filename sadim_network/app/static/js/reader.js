(function () {
  "use strict";

  const PDFJS_VERSION = "3.11.174";
  const PDFJS_CDN = "https://cdn.jsdelivr.net/npm/pdfjs-dist@" + PDFJS_VERSION + "/build/pdf.min.js";
  const PDFJS_WORKER = "https://cdn.jsdelivr.net/npm/pdfjs-dist@" + PDFJS_VERSION + "/build/pdf.worker.min.js";
  const PDFJS_CMAPS = "https://cdn.jsdelivr.net/npm/pdfjs-dist@" + PDFJS_VERSION + "/cmaps/";
  const STORAGE_PREFIX = "sadim-reader-";

  const els = {
    canvas: document.getElementById("pdf-canvas"),
    canvasWrap: document.getElementById("reader-canvas-wrap"),
    pageStatus: document.getElementById("reader-page-status"),
    loading: document.getElementById("reader-loading"),
    loadingBar: document.getElementById("reader-loading-bar"),
    loadingLabel: document.getElementById("reader-loading-label"),
    error: document.getElementById("reader-error"),
    errorMsg: document.getElementById("reader-error-msg"),
    retry: document.getElementById("reader-retry"),
    progress: document.getElementById("reader-progress-bar"),
    header: document.getElementById("reader-header"),
    hero: document.querySelector(".read-hero"),
    main: document.getElementById("reader-main"),
    skipLink: document.querySelector(".reader-skip-link"),
    toolbar: document.getElementById("reader-toolbar"),
    previous: document.getElementById("page-prev"),
    next: document.getElementById("page-next"),
    pageNumber: document.getElementById("page-number"),
    pageTotal: document.getElementById("page-total"),
    zoomOut: document.getElementById("zoom-out"),
    zoomIn: document.getElementById("zoom-in"),
    zoomLabel: document.getElementById("zoom-label"),
    zoomRange: document.getElementById("zoom-range"),
    zoomOutput: document.getElementById("zoom-output"),
    sheetZoomOut: document.getElementById("sheet-zoom-out"),
    sheetZoomIn: document.getElementById("sheet-zoom-in"),
    preferencesToggle: document.getElementById("preferences-toggle"),
    sheetOverlay: document.getElementById("reader-sheet-overlay"),
    sheet: document.getElementById("reader-sheet"),
    sheetClose: document.getElementById("reader-sheet-close"),
    reset: document.getElementById("reader-reset"),
    themeButtons: Array.from(document.querySelectorAll("[data-reader-theme]")),
    outlineToggle: document.getElementById("outline-toggle"),
    outline: document.getElementById("reader-outline"),
    outlineClose: document.getElementById("reader-outline-close"),
    outlineList: document.getElementById("reader-outline-list"),
    immersiveToggle: document.getElementById("immersive-toggle"),
    startReading: document.getElementById("start-reading")
  };

  const state = {
    pdf: null,
    loadingTask: null,
    page: 1,
    totalPages: 0,
    zoom: 1,
    theme: "dark",
    renderTask: null,
    renderGeneration: 0,
    outline: [],
    sheetOpen: false,
    outlineOpen: false,
    immersive: false,
    lastImmersiveFocus: null,
    lastScrollY: 0,
    headerHidden: false,
    touchStartX: 0,
    touchStartY: 0,
    touchMoved: false,
    resizeTimer: null,
    zoomRenderTimer: null,
    resizeObserver: null,
    viewportResizeHandler: null,
    bookId: ""
  };

  function readStorage(key, fallback) {
    try {
      const value = window.localStorage.getItem(STORAGE_PREFIX + key);
      return value === null ? fallback : value;
    } catch (error) {
      return fallback;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(STORAGE_PREFIX + key, String(value));
    } catch (error) {
      return;
    }
  }

  function finiteNumber(value, fallback, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.min(max, Math.max(min, number));
  }

  function loadStoredState() {
    state.bookId = els.canvas.dataset.bookId || "";
    state.zoom = finiteNumber(readStorage("zoom", "1"), 1, 0.6, 1.8);
    state.theme = ["light", "dark", "sepia"].includes(readStorage("theme", "dark")) ? readStorage("theme", "dark") : "dark";
    state.page = Math.max(1, Math.floor(finiteNumber(readStorage("page-" + state.bookId, "1"), 1, 1, Number.MAX_SAFE_INTEGER)));
  }

  function loadPdfScript() {
    if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
    return new Promise(function (resolve, reject) {
      const existing = document.querySelector('script[src*="pdf.min.js"]');
      if (existing && (existing.dataset.readerFailed || (existing.readyState === "complete" && !window.pdfjsLib))) existing.remove();
      const script = existing || document.createElement("script");
      if (!existing) {
        script.src = PDFJS_CDN;
        script.defer = true;
        document.head.appendChild(script);
      }
      script.addEventListener("load", function () {
        if (window.pdfjsLib) resolve(window.pdfjsLib);
        else reject(new Error("pdfjs-load-failed"));
      }, { once: true });
      script.addEventListener("error", function () {
        script.dataset.readerFailed = "true";
        reject(new Error("pdfjs-load-failed"));
      }, { once: true });
    });
  }

  function init() {
    loadStoredState();
    bindEvents();
    applyTheme(false);
    applyZoom(false);
    updatePageUI();
    loadPdfScript().then(function (pdfjsLib) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
      loadDocument(pdfjsLib);
    }).catch(function () {
      showError("تعذر تحميل مكتبة العرض. تحقق من الاتصال بالإنترنت ثم أعد المحاولة.");
    });
  }

  function bindEvents() {
    els.previous.addEventListener("click", function () { goToPage(state.page - 1); });
    els.next.addEventListener("click", function () { goToPage(state.page + 1); });
    els.pageNumber.addEventListener("change", function () {
      const value = Math.floor(Number(els.pageNumber.value));
      if (Number.isFinite(value) && state.totalPages > 0) goToPage(value);
      else updatePageUI();
    });
    els.pageNumber.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        els.pageNumber.blur();
      }
    });
    els.zoomOut.addEventListener("click", function () { setZoom(state.zoom - 0.1); });
    els.zoomIn.addEventListener("click", function () { setZoom(state.zoom + 0.1); });
    els.sheetZoomOut.addEventListener("click", function () { setZoom(state.zoom - 0.1); });
    els.sheetZoomIn.addEventListener("click", function () { setZoom(state.zoom + 0.1); });
    els.zoomRange.addEventListener("input", function () { setZoom(Number(els.zoomRange.value), false); });
    els.zoomRange.addEventListener("change", function () { setZoom(Number(els.zoomRange.value), true); });
    els.themeButtons.forEach(function (button) {
      button.addEventListener("click", function () { setTheme(button.dataset.readerTheme); });
    });
    els.preferencesToggle.addEventListener("click", openSheet);
    els.sheetClose.addEventListener("click", closeSheet);
    els.sheetOverlay.addEventListener("click", function (event) {
      if (event.target === els.sheetOverlay) closeSheet();
    });
    els.reset.addEventListener("click", resetPreferences);
    els.outlineToggle.addEventListener("click", toggleOutline);
    els.outlineClose.addEventListener("click", closeOutline);
    els.immersiveToggle.addEventListener("click", function () { setImmersive(!state.immersive); });
    els.retry.addEventListener("click", retryLoad);
    els.startReading.addEventListener("click", function () {
      els.main.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
      els.canvasWrap.focus({ preventScroll: true });
    });
    window.addEventListener("resize", onResize, { passive: true });
    if (window.ResizeObserver) {
      state.resizeObserver = new ResizeObserver(onResize);
      state.resizeObserver.observe(els.canvasWrap);
    }
    if (window.visualViewport) {
      state.viewportResizeHandler = onResize;
      window.visualViewport.addEventListener("resize", state.viewportResizeHandler, { passive: true });
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("keydown", onKeydown);
    window.addEventListener("pagehide", destroyDocument);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && state.renderTask) {
        try { state.renderTask.cancel(); } catch (error) { }
      }
    });
    els.canvasWrap.addEventListener("touchstart", onTouchStart, { passive: true });
    els.canvasWrap.addEventListener("touchend", onTouchEnd, { passive: true });
    els.canvasWrap.addEventListener("touchcancel", function () { state.touchMoved = false; }, { passive: true });
    els.canvasWrap.addEventListener("click", function (event) {
      if (event.detail === 0 || state.touchMoved) return;
      if (event.target.closest("button, a, input, select, textarea, [role='button']")) return;
      setImmersive(!state.immersive);
    });
  }

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function showLoading(message) {
    els.loading.hidden = false;
    els.loading.setAttribute("aria-busy", "true");
    els.error.hidden = true;
    els.canvas.hidden = false;
    els.canvas.setAttribute("aria-busy", "true");
    els.loadingLabel.textContent = message || "بانتظار بدء التحميل";
    els.loadingBar.style.width = "0%";
    els.loadingBar.parentElement.classList.remove("is-indeterminate");
  }

  function hideLoading() {
    els.loading.hidden = true;
    els.loading.setAttribute("aria-busy", "false");
  }

  function showError(message) {
    hideLoading();
    els.errorMsg.textContent = message || "حدث خطأ غير متوقع أثناء تحميل الملف.";
    els.error.hidden = false;
    els.canvas.hidden = true;
    els.canvas.setAttribute("aria-busy", "false");
  }

  function hideError() {
    els.error.hidden = true;
    els.canvas.hidden = false;
    els.canvas.setAttribute("aria-busy", "false");
  }

  function setLoadingProgress(loaded, total) {
    if (!total || total <= 0) {
      els.loadingBar.parentElement.classList.add("is-indeterminate");
      els.loadingLabel.textContent = "جاري تحميل البيانات";
      return;
    }
    const percent = Math.min(100, Math.max(0, Math.round((loaded / total) * 100)));
    els.loadingBar.parentElement.classList.remove("is-indeterminate");
    els.loadingBar.style.width = percent + "%";
    els.loadingLabel.textContent = percent + "%";
  }

  function loadDocument(pdfjsLib) {
    const url = els.canvas.dataset.pdfUrl;
    if (!url) {
      showError("لا يوجد رابط للكتاب.");
      return;
    }
    destroyDocument();
    showLoading("جاري تجهيز الكتاب");
    try {
      const loadingTask = pdfjsLib.getDocument({
        url: url,
        cMapUrl: PDFJS_CMAPS,
        cMapPacked: true,
        disableFontFace: false,
        disableStream: false,
        disableAutoFetch: false,
        rangeChunkSize: 262144
      });
      state.loadingTask = loadingTask;
      loadingTask.onProgress = function (progress) {
        setLoadingProgress(progress.loaded, progress.total);
      };
      loadingTask.promise.then(function (pdf) {
        if (state.loadingTask !== loadingTask) return;
        state.pdf = pdf;
        state.totalPages = pdf.numPages;
        els.pageTotal.textContent = String(state.totalPages);
        els.pageNumber.max = String(state.totalPages);
        if (state.page > state.totalPages) state.page = state.totalPages;
        loadOutline(pdf);
        hideLoading();
        hideError();
        renderPage(state.page);
      }).catch(function (error) {
        if (state.loadingTask !== loadingTask) return;
        showError("تعذر تحميل الملف. تحقق من الرابط أو اتصال الإنترنت ثم أعد المحاولة.");
      });
    } catch (error) {
      showError("تعذر تحميل الملف. تحقق من الرابط أو اتصال الإنترنت ثم أعد المحاولة.");
    }
  }

  function retryLoad() {
    loadPdfScript().then(function (pdfjsLib) {
      pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
      loadDocument(pdfjsLib);
    }).catch(function () {
      showError("تعذر تحميل مكتبة العرض. تحقق من الاتصال بالإنترنت ثم أعد المحاولة.");
    });
  }

  function destroyDocument() {
    window.clearTimeout(state.resizeTimer);
    window.clearTimeout(state.zoomRenderTimer);
    if (state.resizeObserver) {
      try { state.resizeObserver.disconnect(); } catch (error) { }
      state.resizeObserver = null;
    }
    if (window.visualViewport && state.viewportResizeHandler) {
      window.visualViewport.removeEventListener("resize", state.viewportResizeHandler);
      state.viewportResizeHandler = null;
    }
    const generation = ++state.renderGeneration;
    if (state.renderTask) {
      try { state.renderTask.cancel(); } catch (error) { }
      state.renderTask = null;
    }
    if (state.loadingTask) {
      try { state.loadingTask.destroy(); } catch (error) { }
      state.loadingTask = null;
    }
    if (state.pdf) {
      try { state.pdf.destroy(); } catch (error) { }
      state.pdf = null;
    }
    state.totalPages = 0;
    state.outline = [];
    els.pageTotal.textContent = "-";
    els.pageNumber.max = "1";
    els.outlineList.replaceChildren();
    if (generation === state.renderGeneration) updatePageUI();
  }

  async function renderPage(pageNumber) {
    if (!state.pdf || !els.canvas) return;
    const page = Math.min(state.totalPages, Math.max(1, pageNumber));
    if (state.renderTask) {
      try { state.renderTask.cancel(); } catch (error) { }
    }
    const generation = ++state.renderGeneration;
    state.page = page;
    writeStorage("page-" + state.bookId, page);
    els.canvasWrap.classList.add("is-rendering");
    try {
      const pdfPage = await state.pdf.getPage(page);
      if (generation !== state.renderGeneration) return;
      const paddingStyle = window.getComputedStyle(els.canvasWrap);
      const padding = parseFloat(paddingStyle.paddingLeft || "0") + parseFloat(paddingStyle.paddingRight || "0");
      const availableWidth = Math.max(220, els.canvasWrap.clientWidth - padding);
      const unscaled = pdfPage.getViewport({ scale: 1 });
      const fitScale = availableWidth / unscaled.width;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const cssScale = fitScale * state.zoom;
      const renderScale = cssScale * pixelRatio;
      const viewport = pdfPage.getViewport({ scale: renderScale });
      els.canvas.width = Math.max(1, Math.floor(viewport.width));
      els.canvas.height = Math.max(1, Math.floor(viewport.height));
      els.canvas.style.width = Math.max(1, viewport.width / pixelRatio) + "px";
      els.canvas.style.height = "auto";
      const context = els.canvas.getContext("2d");
      const renderTask = pdfPage.render({ canvasContext: context, viewport: viewport });
      state.renderTask = renderTask;
      await renderTask.promise;
      if (generation !== state.renderGeneration) return;
      state.renderTask = null;
      els.canvas.setAttribute("aria-label", "الصفحة " + page + " من " + state.totalPages + " من " + (document.title || "الكتاب"));
      updatePageUI();
    } catch (error) {
      if (generation !== state.renderGeneration) return;
      state.renderTask = null;
      showError("تعذر عرض هذه الصفحة. يمكن إعادة المحاولة من الشريط السفلي.");
    } finally {
      if (generation === state.renderGeneration) els.canvasWrap.classList.remove("is-rendering");
    }
  }

  async function goToPage(pageNumber) {
    if (!state.pdf) return;
    const page = Math.min(state.totalPages, Math.max(1, pageNumber));
    if (page === state.page && els.canvas.width > 0) return;
    await renderPage(page);
    els.canvasWrap.scrollTo({ top: 0, left: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }

  function updatePageUI() {
    const hasDocument = state.totalPages > 0;
    els.previous.disabled = !hasDocument || state.page <= 1;
    els.next.disabled = !hasDocument || state.page >= state.totalPages;
    els.pageNumber.disabled = !hasDocument;
    if (hasDocument) els.pageNumber.value = String(state.page);
    const percent = hasDocument ? (state.page / state.totalPages) * 100 : 0;
    els.progress.style.width = percent + "%";
    els.progress.setAttribute("aria-valuenow", String(Math.round(percent)));
  }

  function setZoom(value, persist) {
    const nextZoom = finiteNumber(value, state.zoom, 0.6, 1.8);
    state.zoom = Math.round(nextZoom * 10) / 10;
    const label = Math.round(state.zoom * 100) + "%";
    els.zoomLabel.textContent = label;
    els.zoomOutput.value = label;
    els.zoomRange.value = String(state.zoom);
    els.zoomOut.disabled = state.zoom <= 0.6;
    els.zoomIn.disabled = state.zoom >= 1.8;
    if (persist !== false) writeStorage("zoom", state.zoom);
    if (state.pdf) {
      window.clearTimeout(state.zoomRenderTimer);
      if (persist === false) {
        state.zoomRenderTimer = window.setTimeout(function () {
          renderPage(state.page);
        }, 90);
      } else {
        renderPage(state.page);
      }
    }
  }

  function applyZoom(persist) {
    setZoom(state.zoom, persist);
  }

  function setTheme(theme) {
    if (!["light", "dark", "sepia"].includes(theme)) theme = "dark";
    state.theme = theme;
    document.documentElement.dataset.readerTheme = theme;
    els.themeButtons.forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.readerTheme === theme));
      button.classList.toggle("is-active", button.dataset.readerTheme === theme);
    });
    writeStorage("theme", theme);
  }

  function applyTheme(persist) {
    setTheme(state.theme);
    if (persist === false) writeStorage("theme", state.theme);
  }

  function resetPreferences() {
    state.zoom = 1;
    setTheme("dark");
    setZoom(1);
    writeStorage("zoom", 1);
  }

  function setContentInert(value, keepOutline) {
    const elements = [els.header, els.hero, els.canvasWrap, els.toolbar, els.skipLink];
    if (!keepOutline) elements.push(els.main);
    elements.forEach(function (element) {
      if (!element) return;
      try { element.inert = value; } catch (error) { }
      if (value) element.setAttribute("aria-hidden", "true");
      else element.removeAttribute("aria-hidden");
    });
  }

  function openSheet() {
    if (state.sheetOpen) return;
    if (state.outlineOpen) closeOutline(false);
    state.sheetOpen = true;
    setContentInert(true, false);
    els.sheetOverlay.inert = false;
    els.sheetOverlay.classList.add("is-open");
    els.sheetOverlay.setAttribute("aria-hidden", "false");
    els.sheet.setAttribute("aria-hidden", "false");
    els.preferencesToggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("reader-modal-open");
    els.sheetClose.focus();
  }

  function closeSheet(restoreFocus) {
    if (!state.sheetOpen) return;
    state.sheetOpen = false;
    setContentInert(false, false);
    els.sheetOverlay.classList.remove("is-open");
    els.sheetOverlay.setAttribute("aria-hidden", "true");
    els.sheet.setAttribute("aria-hidden", "true");
    els.sheetOverlay.inert = true;
    els.preferencesToggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("reader-modal-open");
    if (restoreFocus !== false && !els.preferencesToggle.disabled) els.preferencesToggle.focus();
  }

  function toggleOutline() {
    if (state.outlineOpen) closeOutline();
    else openOutline();
  }

  function openOutline() {
    if (state.outlineOpen || !state.outline.length) return;
    if (state.sheetOpen) closeSheet(false);
    state.outlineOpen = true;
    setContentInert(true, true);
    els.outline.inert = false;
    els.outline.classList.add("is-open");
    els.outline.setAttribute("aria-hidden", "false");
    els.outlineToggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("reader-modal-open");
    els.outlineClose.focus();
  }

  function closeOutline(restoreFocus) {
    if (!state.outlineOpen) return;
    state.outlineOpen = false;
    els.outline.classList.remove("is-open");
    els.outline.setAttribute("aria-hidden", "true");
    els.outline.inert = true;
    els.outlineToggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("reader-modal-open");
    setContentInert(false, true);
    if (restoreFocus !== false && !els.outlineToggle.disabled) els.outlineToggle.focus();
  }

  async function loadOutline(pdf) {
    try {
      const outline = await pdf.getOutline();
      if (!outline || !outline.length) {
        state.outline = [];
        els.outlineToggle.disabled = true;
        els.outlineToggle.setAttribute("aria-label", "لا يوجد فهرس للكتاب");
        return;
      }
      state.outline = outline;
      els.outlineToggle.disabled = false;
      els.outlineToggle.setAttribute("aria-label", "فتح فهرس الكتاب");
      els.outlineList.replaceChildren();
      for (const item of outline) {
        els.outlineList.appendChild(await buildOutlineItem(pdf, item));
      }
    } catch (error) {
      state.outline = [];
      els.outlineToggle.disabled = true;
      els.outlineToggle.setAttribute("aria-label", "تعذر تحميل فهرس الكتاب");
    }
  }

  async function buildOutlineItem(pdf, item) {
    const listItem = document.createElement("li");
    const page = await destinationToPage(pdf, item.dest);
    if (page) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "reader-outline__item";
      button.textContent = item.title || "بدون عنوان";
      button.addEventListener("click", function () {
        closeOutline();
        goToPage(page);
      });
      listItem.appendChild(button);
    } else if (item.url) {
      const link = document.createElement("a");
      link.className = "reader-outline__item";
      link.textContent = item.title || "رابط خارجي";
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      listItem.appendChild(link);
    } else {
      const label = document.createElement("span");
      label.className = "reader-outline__item";
      label.textContent = item.title || "بدون عنوان";
      listItem.appendChild(label);
    }
    if (item.items && item.items.length) {
      const childList = document.createElement("ol");
      childList.className = "reader-outline__children";
      for (const child of item.items) {
        childList.appendChild(await buildOutlineItem(pdf, child));
      }
      listItem.appendChild(childList);
    }
    return listItem;
  }

  async function destinationToPage(pdf, destination) {
    if (!destination) return null;
    try {
      let resolved = destination;
      if (typeof resolved === "string") resolved = await pdf.getDestination(resolved);
      if (!Array.isArray(resolved) || !resolved[0]) return null;
      const reference = resolved[0].ref || resolved[0];
      return (await pdf.getPageIndex(reference)) + 1;
    } catch (error) {
      return null;
    }
  }

  function setImmersive(value) {
    state.immersive = Boolean(value);
    document.body.classList.toggle("reader-immersive", state.immersive);
    els.immersiveToggle.setAttribute("aria-pressed", String(state.immersive));
    els.immersiveToggle.setAttribute("aria-label", state.immersive ? "الخروج من وضع القراءة العميقة" : "الدخول في وضع القراءة العميقة");
    els.toolbar.inert = Boolean(state.immersive);
    els.header.inert = Boolean(state.immersive);
    els.toolbar.setAttribute("aria-hidden", String(state.immersive));
  }

  function onScroll() {
    const scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    const delta = scrollY - state.lastScrollY;
    state.lastScrollY = scrollY;
    if (state.sheetOpen || state.immersive) return;
    if (!state.headerHidden && scrollY > 180 && delta > 8) {
      state.headerHidden = true;
      els.header.classList.add("is-hidden");
    } else if (state.headerHidden && (delta < -8 || scrollY < 80)) {
      state.headerHidden = false;
      els.header.classList.remove("is-hidden");
    }
  }

  function onResize() {
    window.clearTimeout(state.resizeTimer);
    state.resizeTimer = window.setTimeout(function () {
      if (state.pdf && !state.sheetOpen && !state.outlineOpen) renderPage(state.page);
    }, 160);
  }

  function onTouchStart(event) {
    if (event.touches.length !== 1) return;
    state.touchStartX = event.touches[0].clientX;
    state.touchStartY = event.touches[0].clientY;
    state.touchMoved = false;
  }

  function onTouchEnd(event) {
    if (event.changedTouches.length !== 1) return;
    const deltaX = event.changedTouches[0].clientX - state.touchStartX;
    const deltaY = event.changedTouches[0].clientY - state.touchStartY;
    if (Math.abs(deltaX) < 55 || Math.abs(deltaX) < Math.abs(deltaY) * 1.2) return;
    state.touchMoved = true;
    const rtl = document.documentElement.dir !== "ltr";
    if ((rtl && deltaX < 0) || (!rtl && deltaX > 0)) goToPage(state.page + 1);
    else goToPage(state.page - 1);
    window.setTimeout(function () { state.touchMoved = false; }, 350);
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      if (state.sheetOpen) closeSheet();
      else if (state.outlineOpen) closeOutline();
      else if (state.immersive) setImmersive(false);
      return;
    }
    if (state.sheetOpen) {
      if (event.key === "Tab") trapFocus(event, els.sheet);
      return;
    }
    const target = event.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)) return;
    const rtl = document.documentElement.dir !== "ltr";
    if (event.key === "ArrowLeft" && rtl) goToPage(state.page + 1);
    else if (event.key === "ArrowRight" && rtl) goToPage(state.page - 1);
    else if (event.key === "ArrowLeft" && !rtl) goToPage(state.page - 1);
    else if (event.key === "ArrowRight" && !rtl) goToPage(state.page + 1);
    else if (event.key === "PageUp") goToPage(state.page - 1);
    else if (event.key === "PageDown") goToPage(state.page + 1);
    else if (event.key === "Home") goToPage(1);
    else if (event.key === "End") goToPage(state.totalPages || 1);
    else if (event.key === "+" || event.key === "=") setZoom(state.zoom + 0.1);
    else if (event.key === "-" || event.key === "_") setZoom(state.zoom - 0.1);
    else if (event.key.toLowerCase() === "i" && !event.ctrlKey && !event.metaKey && !event.altKey) setImmersive(!state.immersive);
  }

  function trapFocus(event, container) {
    const focusable = Array.from(container.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  window.Reader = { init: init, state: state, els: els };
})();
