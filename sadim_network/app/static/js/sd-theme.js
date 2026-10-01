/* زر تبديل الوضع الفاتح/الليلي. الاختيار يُحفظ فقط إن خالف إعداد الجهاز؛ لو طابقه يُمسح
   فيعود الموقع لاتباع الجهاز تلقائياً (بلا خيار ثالث مربك). */
(function () {
  "use strict";
  var root = document.documentElement;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;

  // الصفحات غير المهيّأة للوضعين (لا تضمّن partials/_theme_head.html) تبقى داكنة والزر مخفي
  if (!root.hasAttribute("data-theme")) return;

  function systemTheme() { return media && media.matches ? "light" : "dark"; }
  function stored() { try { return localStorage.getItem("sd-theme"); } catch (e) { return null; } }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.setAttribute("aria-label", theme === "dark" ? "التبديل إلى الوضع الفاتح" : "التبديل إلى الوضع الليلي");
      btn.setAttribute("title", btn.getAttribute("aria-label"));
    });
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-theme-toggle]")) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    try {
      if (next === systemTheme()) localStorage.removeItem("sd-theme");
      else localStorage.setItem("sd-theme", next);
    } catch (e) { }
    apply(next);
  });

  // بدون اختيار يدوي: يتبع تغيّر إعداد الجهاز مباشرة (مثلاً الوضع الليلي التلقائي مساءً)
  if (media && media.addEventListener) {
    media.addEventListener("change", function () {
      var choice = stored();
      if (choice !== "light" && choice !== "dark") apply(systemTheme());
    });
  }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) { btn.hidden = false; });
  apply(root.getAttribute("data-theme"));
})();
