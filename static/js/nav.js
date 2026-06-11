// ── Nav rail: estado activo, colapso y badges de pendientes ────────
// Script clásico (sin módulos): expone funciones globales que usa
// legacy.js (updateNavActive) y el HTML (toggleNavRail).

function updateNavActive(tab) {
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === tab);
    });
}

function toggleNavRail() {
    const collapsed = document.body.classList.toggle('nav-collapsed');
    localStorage.setItem('navRailCollapsed', collapsed ? '1' : '0');
}

(function initNavRail() {
    const saved = localStorage.getItem('navRailCollapsed');
    const autoCollapse = window.innerWidth < 1280;
    if (saved === '1' || (saved === null && autoCollapse)) {
        document.body.classList.add('nav-collapsed');
    }
})();

// ── Badges de pendientes en el nav (poll cada 60s) ─────────────────
// Usa /admin/api/pending-counts (endpoint agregado, más barato que
// pollear las 3 listas completas). Los mismos badges también los
// actualiza cada vista al entrar (legacy.js).
async function refreshNavBadges() {
    try {
        const res = await fetch('/admin/api/pending-counts');
        if (!res.ok) return;
        const data = await res.json();
        const counts = (data && data.counts) || {};
        const map = {
            badgeDocsPendientes: counts.received_docs,
            badgeLLMPendientes: counts.llm_requests,
            badgeDocReqPendientes: counts.document_requests,
        };
        for (const [id, value] of Object.entries(map)) {
            const el = document.getElementById(id);
            if (!el) continue;
            const n = Number(value) || 0;
            el.style.display = n > 0 ? 'inline-flex' : 'none';
            el.textContent = n;
        }
    } catch (err) {
        console.error('Error refrescando badges:', err);
    }
}

refreshNavBadges();
setInterval(refreshNavBadges, 60000);
