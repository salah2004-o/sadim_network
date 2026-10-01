/* زر مشاركة موحّد: Web Share API على الجوال، ونسخ الرابط كبديل. كل ضغطة تُسجَّل share.clicked.
   [data-share]      زر يحمل data-share-url/title/text + data-content-type/id + data-placement
   [data-share-link] رابط مشاركة مباشر (واتساب، تيليجرام...) — قيمته اسم الطريقة */
(function () {
  "use strict";

  function track(el, method) {
    if (!window.sdTrack) return;
    window.sdTrack("share.clicked", {
      content_type: el.dataset.contentType || null,
      content_id: el.dataset.contentId ? Number(el.dataset.contentId) : null,
      placement: el.dataset.placement || null,
      method: method
    });
  }

  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try { if (document.execCommand("copy")) resolve(); else reject(); }
      catch (error) { reject(error); }
      finally { area.remove(); }
    });
  }

  function confirmCopied(btn) {
    if (btn.dataset.shareBusy) return;
    var original = btn.innerHTML;
    btn.dataset.shareBusy = "1";
    btn.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i> تم نسخ الرابط';
    setTimeout(function () { btn.innerHTML = original; delete btn.dataset.shareBusy; }, 1800);
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-share]");
    if (btn) {
      event.preventDefault();
      var url = btn.dataset.shareUrl || location.href;
      if (navigator.share) {
        track(btn, "web_share");
        navigator.share({ title: btn.dataset.shareTitle || document.title, text: btn.dataset.shareText || "", url: url }).catch(function () {});
      } else {
        track(btn, "clipboard");
        copy(url).then(function () { confirmCopied(btn); }).catch(function () { window.prompt("انسخ الرابط:", url); });
      }
      return;
    }
    var link = event.target.closest("[data-share-link]");
    if (link) track(link, link.dataset.shareLink);
  });
})();
