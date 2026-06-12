// ── Panel de Diagnóstico: estado de servicios y fallos clasificados ──
// Script clásico (sin módulos), mismo patrón que nav.js. legacy.js lo
// invoca vía VIEWS.diagnostico.onEnter → fetchDiagnostics().

const DIAG_ACTION_META = {
    esperar:    { label: 'Esperar — se resuelve solo',      cls: 'diag-chip-esperar' },
    gestionar:  { label: 'Gestionar desde el panel',        cls: 'diag-chip-gestionar' },
    intervenir: { label: 'Requiere intervención técnica',   cls: 'diag-chip-intervenir' },
};

const DIAG_ESTADO_META = {
    ok:     { dot: 'diag-dot-ok',     label: 'Operativo' },
    alerta: { dot: 'diag-dot-alerta', label: 'Con alertas' },
    caido:  { dot: 'diag-dot-caido',  label: 'Caído' },
};

const DIAG_SERVICE_NAMES = {
    servidor:  { titulo: 'Servidor (Render)',          icon: '🖥️' },
    meta:      { titulo: 'WhatsApp (Meta)',            icon: '💬' },
    supabase:  { titulo: 'Supabase (chats y estados)', icon: '🗄️' },
    cloud_run: { titulo: 'Base de solicitudes',        icon: '📋' },
    llm:       { titulo: 'Agente LLM',                 icon: '🤖' },
};

function diagEscape(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function renderDiagCard(key, info) {
    const svc = DIAG_SERVICE_NAMES[key] || { titulo: key, icon: '🔧' };
    const estado = DIAG_ESTADO_META[info.estado] || DIAG_ESTADO_META.alerta;
    const queHacer = info.que_hacer
        ? `<div class="diag-card-action"><strong>Qué hacer:</strong> ${diagEscape(info.que_hacer)}</div>`
        : '';
    return `
        <div class="diag-card card-x diag-card-${diagEscape(info.estado)}">
            <div class="diag-card-head">
                <span class="diag-dot ${estado.dot}"></span>
                <span class="diag-card-title">${svc.icon} ${diagEscape(svc.titulo)}</span>
                <span class="diag-card-estado">${estado.label}</span>
            </div>
            <div class="diag-card-detail">${diagEscape(info.detalle || '')}</div>
            ${queHacer}
        </div>`;
}

function renderDiagEvents(events) {
    const container = document.getElementById('diagEventsContainer');
    if (!events || events.length === 0) {
        container.innerHTML = '<div class="diag-empty">Sin fallos registrados desde el último reinicio del servidor. ✅</div>';
        return;
    }
    let rows = '';
    events.forEach(ev => {
        const action = DIAG_ACTION_META[ev.accion] || DIAG_ACTION_META.intervenir;
        const fecha = new Date(ev.timestamp).toLocaleString('es-CO', {
            day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
        });
        rows += `
            <tr>
                <td class="diag-td-fecha">${fecha}</td>
                <td><div class="diag-td-titulo">${diagEscape(ev.titulo)}</div>
                    <div class="diag-td-origen">${diagEscape(ev.origen)}</div></td>
                <td class="diag-td-phone">${ev.phone
                    ? `${diagEscape(ev.phone)}<br><button onclick="goToChat('${diagEscape(ev.phone)}')" style="margin-top:3px;padding:2px 9px;font-size:0.7rem;background:#eff6ff;border:1px solid #3b82f6;color:#1d4ed8;border-radius:4px;cursor:pointer;white-space:nowrap;">Ver chat →</button>`
                    : '—'}</td>
                <td class="diag-td-detail">${diagEscape(ev.detail)}
                    <div class="diag-td-quehacer">${diagEscape(ev.que_hacer)}</div></td>
                <td><span class="diag-chip ${action.cls}">${action.label}</span></td>
            </tr>`;
    });
    container.innerHTML = `
        <table class="diag-table">
            <thead><tr><th>Hora</th><th>Tipo de fallo</th><th>Teléfono</th><th>Detalle y qué hacer</th><th>Acción</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

async function fetchDiagnostics() {
    const cards = document.getElementById('diagHealthCards');
    const summaryEl = document.getElementById('diagSummary');
    cards.innerHTML = '<div class="diag-empty">Verificando servicios…</div>';

    let data;
    try {
        const res = await fetch('/admin/api/diagnostics');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        data = await res.json();
    } catch (err) {
        // Si este endpoint no responde, el propio servidor del bot está caído
        // (o sin internet del lado del panel). Es el único caso que el
        // servidor no puede reportar de sí mismo.
        cards.innerHTML = renderDiagCard('servidor', {
            estado: 'caido',
            detalle: `El panel no pudo contactar al servidor del bot (${diagEscape(err.message)}).`,
            que_hacer: 'Primero verifica tu propio internet recargando otra página. Si tu internet ' +
                'está bien, el servidor del bot (Render) está caído o reiniciándose: el bot NO está ' +
                'atendiendo a nadie. Espera 2-3 minutos y reintenta; si sigue caído, contactar a Carlos.',
        });
        document.getElementById('diagEventsContainer').innerHTML =
            '<div class="diag-empty">No se pudieron cargar los eventos (servidor no disponible).</div>';
        if (summaryEl) summaryEl.textContent = '—';
        return;
    }

    // El servidor respondió → Render operativo. Luego, una tarjeta por servicio.
    let html = renderDiagCard('servidor', {
        estado: 'ok',
        detalle: 'El servidor del bot está en línea y procesando mensajes.'
            + (data.environment === 'staging' ? ' (Entorno: STAGING — envíos reales bloqueados.)' : ''),
    });
    for (const key of ['meta', 'supabase', 'cloud_run', 'llm']) {
        if (data.health && data.health[key]) html += renderDiagCard(key, data.health[key]);
    }
    cards.innerHTML = html;

    const s = data.summary || {};
    if (summaryEl) {
        summaryEl.textContent = `${s.total || 0} (esperar: ${s.esperar || 0} · ` +
            `gestionar: ${s.gestionar || 0} · intervenir: ${s.intervenir || 0})`;
    }
    renderDiagEvents(data.events || []);
}
