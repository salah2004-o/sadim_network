/*
  ui-kit.js — سلوكيات تفاعلية مشتركة لنظام تصميم شبكة سديم.
  بدون أي مكتبة خارجية (لا jQuery ولا Bootstrap JS) — Vanilla JS بحت.
  يوفر: SdModal, SdDropdown, SdToast, وربط تلقائي لتأثير Ripple على أي عنصر .sd-ripple.
*/
(function () {
    "use strict";

    /* ============ Ripple ============ */
    document.addEventListener("click", function (e) {
        const target = e.target.closest(".sd-ripple");
        if (!target) return;
        const rect = target.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const dot = document.createElement("span");
        dot.className = "sd-ripple-dot";
        dot.style.width = dot.style.height = size + "px";
        dot.style.left = (e.clientX - rect.left - size / 2) + "px";
        dot.style.top = (e.clientY - rect.top - size / 2) + "px";
        target.appendChild(dot);
        dot.addEventListener("animationend", () => dot.remove());
    });

    /* ============ Modal ============ */
    const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';
    let lastFocused = null;

    function trapFocus(e, modal) {
        if (e.key !== "Tab") return;
        const focusables = Array.from(modal.querySelectorAll(FOCUSABLE)).filter(el => el.offsetParent !== null);
        if (focusables.length === 0) return;
        const first = focusables[0], last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault(); first.focus();
        }
    }

    function openModal(idOrEl) {
        const overlay = typeof idOrEl === "string" ? document.getElementById(idOrEl) : idOrEl;
        if (!overlay) return;
        lastFocused = document.activeElement;
        overlay.classList.add("is-open");
        overlay.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
        const modal = overlay.querySelector(".sd-modal");
        const firstFocusable = modal && modal.querySelector(FOCUSABLE);
        (firstFocusable || modal || overlay).focus({ preventScroll: true });

        function onKeydown(e) {
            if (e.key === "Escape") closeModal(overlay);
            else if (modal) trapFocus(e, modal);
        }
        overlay.__sdKeydown = onKeydown;
        document.addEventListener("keydown", onKeydown);
    }

    function closeModal(idOrEl) {
        const overlay = typeof idOrEl === "string" ? document.getElementById(idOrEl) : idOrEl;
        if (!overlay) return;
        overlay.classList.remove("is-open");
        overlay.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        if (overlay.__sdKeydown) document.removeEventListener("keydown", overlay.__sdKeydown);
        if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus({ preventScroll: true });
    }

    document.addEventListener("click", function (e) {
        const opener = e.target.closest("[data-sd-modal-open]");
        if (opener) {
            e.preventDefault();
            openModal(opener.getAttribute("data-sd-modal-open"));
            return;
        }
        const closer = e.target.closest("[data-sd-modal-close]");
        if (closer) {
            e.preventDefault();
            closeModal(closer.closest(".sd-modal-overlay"));
            return;
        }
        if (e.target.classList && e.target.classList.contains("sd-modal-overlay")) {
            closeModal(e.target);
        }
    });

    window.SdModal = { open: openModal, close: closeModal };

    /* ============ Dropdown ============ */
    function closeAllDropdowns(except) {
        document.querySelectorAll(".sd-dropdown-menu.is-open").forEach(menu => {
            if (menu === except) return;
            menu.classList.remove("is-open");
            const trigger = menu.closest(".sd-dropdown").querySelector("[data-sd-dropdown-trigger]");
            if (trigger) trigger.setAttribute("aria-expanded", "false");
        });
    }

    document.addEventListener("click", function (e) {
        const trigger = e.target.closest("[data-sd-dropdown-trigger]");
        if (trigger) {
            e.preventDefault();
            const menu = trigger.closest(".sd-dropdown").querySelector(".sd-dropdown-menu");
            const willOpen = !menu.classList.contains("is-open");
            closeAllDropdowns();
            if (willOpen) {
                menu.classList.add("is-open");
                trigger.setAttribute("aria-expanded", "true");
            }
            return;
        }
        if (!e.target.closest(".sd-dropdown-menu")) closeAllDropdowns();
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeAllDropdowns();
    });

    /* ============ Toast ============ */
    let toastStack = null;
    function ensureStack() {
        if (!toastStack) {
            toastStack = document.createElement("div");
            toastStack.className = "sd-toast-stack";
            toastStack.setAttribute("role", "status");
            toastStack.setAttribute("aria-live", "polite");
            document.body.appendChild(toastStack);
        }
        return toastStack;
    }

    const TOAST_ICONS = { success: "fa-circle-check", danger: "fa-circle-exclamation", warning: "fa-triangle-exclamation", info: "fa-circle-info" };

    function showToast(message, type, duration) {
        type = type || "info";
        duration = duration || 4000;
        const stack = ensureStack();
        const toast = document.createElement("div");
        toast.className = "sd-toast";
        const icon = TOAST_ICONS[type] || TOAST_ICONS.info;
        const colorVar = type === "success" ? "var(--sd-success)" : type === "danger" ? "var(--sd-danger)" : type === "warning" ? "var(--sd-warning)" : "var(--sd-info)";
        toast.innerHTML = `<i class="fas ${icon}" style="color:${colorVar};margin-top:2px;"></i><span>${message}</span>`;
        stack.appendChild(toast);
        const timer = setTimeout(() => dismiss(), duration);
        toast.addEventListener("click", () => { clearTimeout(timer); dismiss(); });
        function dismiss() {
            toast.classList.add("is-leaving");
            toast.addEventListener("animationend", () => toast.remove(), { once: true });
        }
    }

    window.SdToast = { show: showToast };
})();
