(() => {
    const widget = document.querySelector('[data-sd-ai-float]');
    if (!widget) return;

    const trigger = widget.querySelector('[data-sd-ai-trigger]');
    const close = widget.querySelector('[data-sd-ai-close]');
    const drawer = widget.querySelector('[data-sd-ai-drawer]');
    const summarizeBtn = widget.querySelector('[data-sd-ai-summarize]');
    const summaryEl = widget.querySelector('[data-sd-ai-summary]');
    const contextType = widget.getAttribute('data-sd-ai-context-type') || '';
    const contextId = widget.getAttribute('data-sd-ai-context-id') || '';

    if (contextType && contextId) {
        widget.classList.add('is-side-panel');
    }

    const setOpen = (open) => {
        widget.classList.toggle('is-open', open);
        trigger.setAttribute('aria-expanded', String(open));
        if (drawer) drawer.setAttribute('aria-hidden', String(!open));
        if (open && close) close.focus();
    };

    trigger.addEventListener('click', () => setOpen(!widget.classList.contains('is-open')));
    if (close) close.addEventListener('click', () => setOpen(false));
    document.addEventListener('click', (event) => {
        if (!widget.contains(event.target)) setOpen(false);
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') setOpen(false);
    });

    if (summarizeBtn && summaryEl && contextType && contextId) {
        summarizeBtn.addEventListener('click', async () => {
            summarizeBtn.disabled = true;
            summaryEl.hidden = false;
            summaryEl.textContent = 'جارٍ التلخيص…';
            try {
                const res = await fetch('/ai/summarize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: contextType, id: Number(contextId) }),
                });
                const data = await res.json();
                if (!res.ok) {
                    summaryEl.textContent = data.error === 'not_found'
                        ? 'تعذر العثور على المحتوى.'
                        : 'تعذر التلخيص حالياً.';
                    return;
                }
                summaryEl.textContent = data.content || 'لا يوجد ملخص.';
            } catch (err) {
                summaryEl.textContent = 'تعذر الاتصال بـ Sadeem AI.';
            } finally {
                summarizeBtn.disabled = false;
            }
        });
    }
})();
