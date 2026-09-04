(() => {
    const widget = document.querySelector('[data-sd-ai-float]');
    if (!widget) return;

    const trigger = widget.querySelector('[data-sd-ai-trigger]');
    const close = widget.querySelector('[data-sd-ai-close]');
    const drawer = widget.querySelector('[data-sd-ai-drawer]');

    const setOpen = (open) => {
        widget.classList.toggle('is-open', open);
        trigger.setAttribute('aria-expanded', String(open));
        drawer.setAttribute('aria-hidden', String(!open));
        if (open) close.focus();
    };

    trigger.addEventListener('click', () => setOpen(!widget.classList.contains('is-open')));
    close.addEventListener('click', () => setOpen(false));
    document.addEventListener('click', (event) => {
        if (!widget.contains(event.target)) setOpen(false);
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') setOpen(false);
    });
})();
