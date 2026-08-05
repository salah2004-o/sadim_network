// قائمة الجوال المشتركة (hamburger menu) — مستخدمة بكل صفحة فيها #menu-toggle / #mobile-sidebar / #close-sidebar
document.addEventListener('DOMContentLoaded', () => {
    const menuToggle = document.getElementById('menu-toggle');
    const mobileSidebar = document.getElementById('mobile-sidebar');
    const closeSidebar = document.getElementById('close-sidebar');

    if (!menuToggle || !mobileSidebar) return;

    const overlay = document.createElement('div');
    overlay.className = 'overlay';
    document.body.appendChild(overlay);

    const showSidebar = () => {
        mobileSidebar.classList.add('active');
        overlay.classList.add('active');
        menuToggle.setAttribute('aria-expanded', 'true');
    };

    const hideSidebar = () => {
        mobileSidebar.classList.remove('active');
        overlay.classList.remove('active');
        menuToggle.setAttribute('aria-expanded', 'false');
    };

    menuToggle.addEventListener('click', showSidebar);
    if (closeSidebar) closeSidebar.addEventListener('click', hideSidebar);
    overlay.addEventListener('click', hideSidebar);

    // إغلاق بلوحة المفاتيح (Esc) — إتاحة للتنقل بدون فأرة
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && mobileSidebar.classList.contains('active')) {
            hideSidebar();
        }
    });
});
