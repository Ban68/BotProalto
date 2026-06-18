// ── Filtro de intervalo de tiempo para métricas de campañas ─────────
// Renderiza atajos (7 días, 30 días, Este mes, Hoy, Todo) más un rango
// personalizado desde/hasta. Lo usan paste-campaign.js (Familia B) y
// campaign-panel.js (Familia A) para acotar las métricas a un período.
//
// createMetricsTimeline(onChange) -> { el, params }
//   el        : nodo DOM para insertar en la cabecera de métricas
//   params()  : rango actual como query string
//               ('' | '?from=YYYY-MM-DD&to=YYYY-MM-DD')
//   onChange  : callback (sin args) que se dispara al cambiar el rango;
//               el panel lo usa para volver a consultar las métricas.

function createMetricsTimeline(onChange) {
    const PRESETS = [
        { id: '7d', label: '7 días' },
        { id: '30d', label: '30 días' },
        { id: 'month', label: 'Este mes' },
        { id: 'today', label: 'Hoy' },
        { id: 'all', label: 'Todo' },
    ];

    const pad = n => String(n).padStart(2, '0');
    const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

    function presetRange(id) {
        const now = new Date();
        const to = iso(now);
        if (id === 'today') return { from: to, to };
        if (id === '7d') { const f = new Date(now); f.setDate(f.getDate() - 6); return { from: iso(f), to }; }
        if (id === '30d') { const f = new Date(now); f.setDate(f.getDate() - 29); return { from: iso(f), to }; }
        if (id === 'month') { const f = new Date(now.getFullYear(), now.getMonth(), 1); return { from: iso(f), to }; }
        return { from: '', to: '' }; // Todo
    }

    let range = { from: '', to: '' }; // por defecto: todo el histórico

    const el = document.createElement('div');
    el.className = 'mtl';
    el.innerHTML = `
        <div class="mtl-presets">
            ${PRESETS.map(p => `<button type="button" class="mtl-chip" data-preset="${p.id}">${p.label}</button>`).join('')}
        </div>
        <div class="mtl-range">
            <input type="date" class="mtl-date" data-mtl="from" title="Desde">
            <span class="mtl-sep">→</span>
            <input type="date" class="mtl-date" data-mtl="to" title="Hasta">
        </div>`;

    const chips = el.querySelectorAll('.mtl-chip');
    const fromInput = el.querySelector('[data-mtl="from"]');
    const toInput = el.querySelector('[data-mtl="to"]');

    function markActive(presetId) {
        chips.forEach(c => c.classList.toggle('is-active', c.dataset.preset === presetId));
    }

    function setRange(next, presetId) {
        range = next;
        fromInput.value = next.from;
        toInput.value = next.to;
        markActive(presetId);
        onChange();
    }

    chips.forEach(c => c.addEventListener('click', () => setRange(presetRange(c.dataset.preset), c.dataset.preset)));
    [fromInput, toInput].forEach(inp => inp.addEventListener('change', () => {
        range = { from: fromInput.value, to: toInput.value };
        markActive(null); // rango manual: ningún atajo queda resaltado
        onChange();
    }));

    markActive('all');

    return {
        el,
        params() {
            const qs = [];
            if (range.from) qs.push('from=' + encodeURIComponent(range.from));
            if (range.to) qs.push('to=' + encodeURIComponent(range.to));
            return qs.length ? '?' + qs.join('&') : '';
        },
    };
}
