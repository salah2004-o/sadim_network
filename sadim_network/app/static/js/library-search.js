/* بحث المكتبة الفوري + الفلاتر — في المتصفح بلا طلبات شبكة (عدد الكتب صغير).
   التطبيع نفس قواعد normalize_ar() في app/utlis/arabic.py.
   Enter بدون اختيار اقتراح يرسل النموذج لصفحة النتائج (حدث book.search بالخادم كما هو).
   فتح نتيجة أثناء البحث يسجّل search.result.clicked. */
(function () {
  "use strict";

  var input = document.getElementById("lib-q");
  var list = document.getElementById("lib-suggest");
  if (!input || !list) return;

  var clearBtn = document.getElementById("lib-clear");
  var empty = document.getElementById("lib-empty");
  var countEl = document.getElementById("lib-count");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".lib-chip"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("#tab-books .book-card[data-book-id]"));
  var active = { author: null, genre: null, length: null };
  var suggestions = [];
  var cursor = -1;

  function normalize(text) {
    return String(text || "")
      .replace(/[ؐ-ًؚ-ٰٟۖ-ۭـ]/g, "")
      .replace(/[أإآٱ]/g, "ا")
      .replace(/ة/g, "ه")
      .replace(/[ىئ]/g, "ي")
      .replace(/ؤ/g, "و")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  cards.forEach(function (card) {
    card._primary = normalize(card.dataset.title + " " + card.dataset.author);
    card._all = card._primary + " " + normalize(card.dataset.genre);
  });

  function track(card, position, source) {
    if (window.sdTrack) {
      window.sdTrack("search.result.clicked", {
        query: input.value.trim().slice(0, 100),
        book_id: Number(card.dataset.bookId),
        position: position,
        source: source
      });
    }
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function closeSuggest() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    cursor = -1;
  }

  function renderSuggest(query) {
    suggestions = query ? cards.filter(function (c) { return !c.hidden && c._primary.indexOf(query) !== -1; }).slice(0, 5) : [];
    if (!suggestions.length || document.activeElement !== input) { closeSuggest(); return; }
    list.innerHTML = suggestions.map(function (card, i) {
      return '<li role="option" id="lib-opt-' + i + '" aria-selected="false">' +
        '<a href="' + escapeHtml(card.dataset.url) + '" data-pos="' + (i + 1) + '">' +
        '<img src="' + escapeHtml(card.dataset.cover) + '" alt="" width="32" height="48" loading="lazy">' +
        '<span>' + escapeHtml(card.dataset.title) + '<small>' + escapeHtml(card.dataset.author) + '</small></span></a></li>';
    }).join("") +
      '<li role="option" id="lib-opt-all" aria-selected="false"><button type="button" data-all>' +
      '<i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i> كل النتائج لـ «' + escapeHtml(input.value.trim()) + '»</button></li>';
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    cursor = -1;
  }

  function apply(fromTyping) {
    var query = normalize(input.value);
    var visible = 0;
    cards.forEach(function (card) {
      var match = (!query || card._all.indexOf(query) !== -1) &&
        (!active.author || card.dataset.author === active.author) &&
        (!active.genre || card.dataset.genre === active.genre) &&
        (!active.length || card.dataset.length === active.length);
      card.hidden = !match;
      if (match) visible += 1;
    });
    if (empty) empty.hidden = visible > 0 || !cards.length;
    if (countEl) countEl.textContent = (query || active.author || active.genre || active.length) ? visible + " نتيجة" : "";
    clearBtn.hidden = !input.value;
    if (fromTyping) renderSuggest(query);
    syncUrl();
  }

  function syncUrl() {
    try {
      var url = new URL(window.location.href);
      ["q", "author", "genre", "length"].forEach(function (key) { url.searchParams.delete(key); });
      if (input.value.trim()) url.searchParams.set("q", input.value.trim());
      Object.keys(active).forEach(function (key) { if (active[key]) url.searchParams.set(key, active[key]); });
      window.history.replaceState(null, "", url.pathname + url.search);
    } catch (error) { }
  }

  function moveCursor(step) {
    var options = list.querySelectorAll("li");
    if (list.hidden || !options.length) return;
    if (cursor >= 0) { options[cursor].classList.remove("is-active"); options[cursor].setAttribute("aria-selected", "false"); }
    cursor = (cursor + step + options.length) % options.length;
    options[cursor].classList.add("is-active");
    options[cursor].setAttribute("aria-selected", "true");
    input.setAttribute("aria-activedescendant", options[cursor].id);
  }

  input.addEventListener("input", function () { apply(true); });
  input.addEventListener("focus", function () { renderSuggest(normalize(input.value)); });
  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") { event.preventDefault(); moveCursor(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); moveCursor(-1); }
    else if (event.key === "Escape") { closeSuggest(); }
    else if (event.key === "Enter" && cursor >= 0) {
      var link = list.querySelectorAll("li")[cursor].querySelector("a");
      if (link) { event.preventDefault(); link.click(); }
    }
  });
  document.addEventListener("click", function (event) {
    if (!event.target.closest(".lib-search")) closeSuggest();
  });

  list.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-pos]");
    if (link) {
      var position = Number(link.dataset.pos);
      track(suggestions[position - 1], position, "suggest");
      return;
    }
    if (event.target.closest("[data-all]")) {
      event.preventDefault();
      input.form.submit();
    }
  });

  // فتح بطاقة من الشبكة المصفّاة أثناء البحث = نتيجة بحث
  document.getElementById("tab-books").addEventListener("click", function (event) {
    var link = event.target.closest(".book-card a");
    if (!link || !input.value.trim()) return;
    var card = link.closest(".book-card");
    var visibleCards = cards.filter(function (c) { return !c.hidden; });
    track(card, visibleCards.indexOf(card) + 1, "grid");
  });

  clearBtn.addEventListener("click", function () {
    input.value = "";
    apply(false);
    closeSuggest();
    input.focus();
  });

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var key = chip.dataset.filter;
      var value = active[key] === chip.dataset.value ? null : chip.dataset.value;
      active[key] = value;
      chips.forEach(function (other) {
        if (other.dataset.filter === key) other.setAttribute("aria-pressed", String(other.dataset.value === value));
      });
      apply(false);
    });
  });

  if (empty) {
    document.getElementById("lib-reset").addEventListener("click", function () {
      input.value = "";
      Object.keys(active).forEach(function (key) { active[key] = null; });
      chips.forEach(function (chip) { chip.setAttribute("aria-pressed", "false"); });
      apply(false);
    });
  }

  // استعادة البحث/الفلاتر من الرابط (مثلاً بعد الرجوع من صفحة كتاب)
  var params = new URLSearchParams(window.location.search);
  if (params.get("q")) input.value = params.get("q");
  Object.keys(active).forEach(function (key) {
    var value = params.get(key);
    if (!value) return;
    var chip = chips.find(function (c) { return c.dataset.filter === key && c.dataset.value === value; });
    if (chip) { active[key] = value; chip.setAttribute("aria-pressed", "true"); }
  });
  if (input.value || active.author || active.genre || active.length) apply(false);
})();
