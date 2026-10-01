/* أحداث الواجهة → /api/events (قائمة أسماء مسموحة في الخادم). sendBeacon حتى لا يضيع الحدث عند مغادرة الصفحة. */
(function () {
  "use strict";
  function sdTrack(event, metadata) {
    try {
      var body = JSON.stringify({ event: event, metadata: metadata || {}, path: location.pathname });
      if (navigator.sendBeacon && navigator.sendBeacon("/api/events", new Blob([body], { type: "application/json" }))) return;
      fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true,
        credentials: "same-origin"
      }).catch(function () {});
    } catch (error) { }
  }
  window.sdTrack = sdTrack;
})();
