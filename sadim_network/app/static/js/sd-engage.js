/* دعوة التسجيل للزوار في لحظة الحاجة — لا عند الدخول، ومرة واحدة على الأكثر في الزيارة (sessionStorage):
   - بعد التحميل الثاني في الزيارة          → placement=second_download, value=shelf
   - عند الخروج من القارئ بعد 5 دقائق قراءة → placement=reader_exit,     value=save_place
   وأزرار التسجيل المضمّنة [data-signup-cta] (تنبيه الكتب الجديدة، الإعجاب، صفحة الرف):
   shown عند ظهورها فعلاً في الشاشة، وclicked عند الضغط. */
(function () {
  "use strict";

  var sheet = document.getElementById("sd-signup-sheet");
  if (!sheet) return; // القالب لا يعرضها إلا للزوار

  var SHOWN_KEY = "sd-signup-shown";
  var DL_KEY = "sd-dl-count";
  var EXIT_KEY = "sd-reader-exit";
  var READER_PROMPT_MS = 5 * 60 * 1000;

  function store(key, value) {
    try {
      if (value === undefined) return sessionStorage.getItem(key);
      if (value === null) sessionStorage.removeItem(key);
      else sessionStorage.setItem(key, value);
    } catch (error) { }
    return null;
  }

  function track(name, metadata) {
    if (window.sdTrack) window.sdTrack(name, metadata);
  }

  function loginUrl(next, placement, intent) {
    return "/auth/google?next=" + encodeURIComponent(next) + "&src=" + encodeURIComponent(placement) +
      (intent ? "&intent=" + encodeURIComponent(intent) : "");
  }

  var title = document.getElementById("sd-signup-title");
  var body = document.getElementById("sd-signup-body");
  var cta = sheet.querySelector("[data-signup-sheet-cta]");
  var continueUrl = null;

  function show(placement, value, next, copy, afterDismissUrl) {
    if (store(SHOWN_KEY)) return false;
    store(SHOWN_KEY, "1");
    title.textContent = copy.title;
    body.textContent = copy.body;
    cta.href = loginUrl(next, placement);
    cta.dataset.placement = placement;
    cta.dataset.value = value;
    continueUrl = afterDismissUrl || null;
    sheet.hidden = false;
    requestAnimationFrame(function () { sheet.classList.add("is-open"); });
    track("signup.prompt.shown", { placement: placement, value: value });
    return true;
  }

  function dismiss() {
    sheet.classList.remove("is-open");
    sheet.hidden = true;
    if (continueUrl) window.location.href = continueUrl;
  }

  sheet.querySelectorAll("[data-signup-dismiss]").forEach(function (btn) { btn.addEventListener("click", dismiss); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !sheet.hidden) dismiss();
  });

  // ---------- ضغطات التسجيل (الورقة + الأزرار المضمّنة) ----------
  document.addEventListener("click", function (event) {
    var el = event.target.closest("[data-signup-sheet-cta], [data-signup-cta]");
    if (el) track("signup.prompt.clicked", { placement: el.dataset.placement || null, value: el.dataset.value || null });
  });

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        observer.unobserve(entry.target);
        track("signup.prompt.shown", { placement: entry.target.dataset.placement || null, value: entry.target.dataset.value || null });
      });
    }, { threshold: 0.6 });
    document.querySelectorAll("[data-signup-cta]").forEach(function (el) { observer.observe(el); });
  }

  // ---------- التحميل الثاني في الزيارة ----------
  var SHELF_COPY = {
    title: "احتفظ بكتبك في رفّك",
    body: "سجّل بحساب Google وتُحفظ الكتب التي حمّلتها في رفّك، ترجع لها من أي جهاز."
  };

  function countDownload() {
    var count = (Number(store(DL_KEY)) || 0) + 1;
    store(DL_KEY, String(count));
    // بعد بدء التحميل بلحظة، حتى لا تغطي الورقة زر التحميل نفسه
    if (count >= 2) setTimeout(function () { show("second_download", "shelf", "/shelf", SHELF_COPY); }, 1200);
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-download-link]")) countDownload();
  });
  if (document.querySelector("[data-sd-autodownload]")) countDownload();

  // ---------- الخروج من القارئ بعد 5 دقائق قراءة ----------
  function savePlaceCopy(data) {
    return {
      title: "احفظ مكانك في «" + data.title + "»",
      body: "توقفتَ عند الصفحة " + data.page + ". سجّل بحساب Google وأكمل من نفس الصفحة على أي جهاز."
    };
  }

  function readerSnapshot() {
    var reader = window.Reader;
    if (!reader || !reader.readingMs) return null;
    var canvas = reader.els.canvas;
    return {
      ms: reader.readingMs(),
      page: reader.state.page,
      title: canvas.dataset.bookTitle || document.title,
      next: location.pathname
    };
  }

  if (document.body.classList.contains("reader-page")) {
    var back = document.querySelector(".read-header__brand");
    if (back) {
      back.addEventListener("click", function (event) {
        var data = readerSnapshot();
        if (!data || data.ms < READER_PROMPT_MS) return;
        if (show("reader_exit", "save_place", data.next, savePlaceCopy(data), back.href)) event.preventDefault();
      });
    }
    // خرج بزر الرجوع في المتصفح أو أغلق التبويب: تظهر الدعوة في الصفحة التالية
    window.addEventListener("pagehide", function () {
      var data = readerSnapshot();
      if (data && data.ms >= READER_PROMPT_MS && !store(SHOWN_KEY)) store(EXIT_KEY, JSON.stringify(data));
    });
  } else {
    var pending = store(EXIT_KEY);
    if (pending) {
      store(EXIT_KEY, null);
      try {
        var data = JSON.parse(pending);
        setTimeout(function () { show("reader_exit", "save_place", data.next, savePlaceCopy(data)); }, 600);
      } catch (error) { }
    }
  }
})();
