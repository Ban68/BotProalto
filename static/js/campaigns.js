// ── Configuración declarativa de las campañas Familia A ────────────
// Cada panel se monta en su contenedor [data-campaign="<id>"] dentro
// del estado correspondiente en admin.html. La lógica vive en
// campaign-panel.js; aquí solo se describen las diferencias.

const CampaignPanels = {};

function fmtAbMinutes(value) {
    return value === null || value === undefined ? '—' : `${value} min`;
}

function fmtAbRate(value) {
    const n = Number(value || 0);
    return n.toFixed(2);
}

function renderReferralAbSummary(mt, h) {
    const rows = (mt.variants || []).map(v => `
        <tr>
            <td>${h.escapeHtml(v.variant_label)}</td>
            <td class="cmp-c">${v.sent}</td>
            <td class="cmp-c">${v.sent_pct}%</td>
            <td class="cmp-c">${v.como_funciona_count}</td>
            <td class="cmp-c">${v.quiero_beneficio_count}</td>
            <td class="cmp-c">${v.quizas_despues_count}</td>
            <td class="cmp-c">${v.referral_count}</td>
            <td class="cmp-c">${fmtAbRate(v.referrals_per_contact)}</td>
            <td class="cmp-c">${fmtAbMinutes(v.first_response_avg_minutes)}</td>
            <td class="cmp-c">${fmtAbMinutes(v.info_to_benefit_avg_minutes)}</td>
            <td class="cmp-c">${fmtAbMinutes(v.name_to_phone_avg_minutes)}</td>
        </tr>`).join('');
    return `
        <div class="pcmp-ab-summary">
            <table class="table-x pcmp-table">
                <thead>
                    <tr>
                        <th>Variante</th>
                        <th class="cmp-c">Enviados</th>
                        <th class="cmp-c">Split</th>
                        <th class="cmp-c">Cómo funciona</th>
                        <th class="cmp-c">Beneficio</th>
                        <th class="cmp-c">Después</th>
                        <th class="cmp-c">Referidos</th>
                        <th class="cmp-c">Ref/contacto</th>
                        <th class="cmp-c">1ra resp.</th>
                        <th class="cmp-c">Info→beneficio</th>
                        <th class="cmp-c">Nombre→tel.</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function ensureReferralAbShell() {
    if (!document.getElementById('referidosabState')) {
        const leadsState = document.getElementById('leadsState');
        const panel = document.createElement('div');
        panel.className = 'main-chat';
        panel.id = 'referidosabState';
        panel.style.cssText = 'display:none; overflow-y:auto; background:white;';
        panel.innerHTML = '<div data-campaign="referidosab"></div>';
        if (leadsState && leadsState.parentNode) {
            leadsState.insertAdjacentElement('afterend', panel);
        }
    }

    if (!document.querySelector('.nav-item[data-view="referidosab"]')) {
        const leadsNav = document.querySelector('.nav-item[data-view="leads"]');
        if (leadsNav) {
            leadsNav.insertAdjacentHTML('afterend', `
                <button type="button" class="nav-item" data-view="referidosab" data-title="Campaña Referidos A/B" style="--accent:#0f766e" onclick="switchTab('referidosab')">
                    <span class="nav-item-icon">🤝</span><span class="nav-item-label">Referidos A/B</span>
                </button>`);
        }
    }
}

ensureReferralAbShell();

[
    {
        id: 'envios',
        icon: '⚡',
        accent: '#4f46e5',
        title: 'Envíos Masivos: Aprobado por el cliente',
        description: 'Esta herramienta te permite notificar a todos los clientes que han sido aprobados y no han recibido un mensaje hoy.',
        templateName: 'estado_verde',
        fetchEndpoint: '/admin/api/pending-notifications',
        sendEndpoint: '/admin/api/trigger-bulk-send',
        confirm: n => `¿Estás seguro de enviar la notificación de Aprobado a ${n} clientes seleccionados?`,
        executeLabel: '🚀 Ejecutar Envío a Seleccionados',
        batchSize: 15,
        features: { empresa: true, soloNuevos: true, lastSentTime: true },
        metrics: {
            endpoint: '/admin/api/aprobado-metrics',
            header: 'Métricas: estado_verde',
            cards: [
                { label: 'Total enviados', color: '#4f46e5', count: m => m.total },
                { label: 'Aceptaron condiciones', color: '#059669', count: m => m.acepto_count, pct: true },
                { label: 'Respondieron por chat', color: '#2563eb', count: m => m.respondieron_chat_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Clientes que aceptaron las condiciones',
            emptyMsg: 'Sin respuestas aún.',
        },
    },
    {
        id: 'rojo',
        icon: '🔴',
        accent: '#dc2626',
        title: 'Envíos Masivos: Falta Algún Documento',
        description: 'Notifica a los clientes cuyo proceso está detenido por documentos faltantes. Se enviará el template <strong>estado_rojo</strong> con la lista completa de documentos requeridos.',
        templateName: 'estado_rojo',
        fetchEndpoint: '/admin/api/pending-falta-documento',
        sendEndpoint: '/admin/api/trigger-bulk-rojo',
        confirm: n => `¿Estás seguro de enviar el template "estado_rojo" a ${n} clientes seleccionados?`,
        executeLabel: '🔴 Ejecutar Envío a Seleccionados',
        batchSize: 15,
        features: { empresa: true, soloNuevos: true, finca: true, lastSentTime: true },
        metrics: {
            endpoint: '/admin/api/rojo-metrics',
            header: 'Métricas: estado_rojo',
            cards: [
                { label: 'Total enviados', color: '#dc2626', count: m => m.total },
                { label: 'Enviaron documentos', color: '#059669', count: m => m.enviaron_docs_count, pct: true },
                { label: 'Consultaron documentos', color: '#0284c7', count: m => m.consultaron_count, pct: true },
                { label: 'Respondieron por chat', color: '#2563eb', count: m => m.respondieron_chat_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Clientes que enviaron documentos o consultaron',
            emptyMsg: 'Sin respuestas aún.',
        },
    },
    {
        id: 'amarillo',
        icon: '🟡',
        accent: '#d97706',
        title: 'Envíos Masivos: Listo en PandaDoc',
        description: 'Notifica a los clientes cuya solicitud está lista en PandaDoc para solicitar su número de cuenta. Se enviará el template <strong>estado_amarillo</strong>.',
        templateName: 'estado_amarillo',
        fetchEndpoint: '/admin/api/pending-listo-docusign',
        sendEndpoint: '/admin/api/trigger-bulk-amarillo',
        confirm: n => `¿Estás seguro de enviar el template "estado_amarillo" a ${n} clientes seleccionados?`,
        executeLabel: '🟡 Ejecutar Envío a Seleccionados',
        batchSize: 15,
        features: { empresa: true, soloNuevos: true, lastSentTime: true },
        metrics: {
            endpoint: '/admin/api/amarillo-metrics',
            header: 'Métricas: estado_amarillo',
            cards: [
                { label: 'Total enviados', color: '#d97706', count: m => m.total },
                { label: 'Cuenta propia', color: '#059669', count: m => m.cuenta_propia_count, pct: true },
                { label: 'Cuenta de tercero', color: '#7c3aed', count: m => m.cuenta_tercero_count, pct: true },
                { label: 'Respondieron por chat', color: '#2563eb', count: m => m.respondieron_chat_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Clientes que enviaron su cuenta',
            emptyMsg: 'Sin respuestas aún.',
        },
    },
    {
        id: 'negados',
        icon: '🚫',
        accent: '#6b7280',
        title: 'Envíos Masivos: Créditos Negados',
        description: 'Notifica a los clientes con solicitud en estado <strong>DENEGADO</strong> o <strong>CANCELADO POR LA EMPRESA</strong>. Se enviará el template <strong>estado_negados</strong>. Cada cliente solo recibe esta notificación <strong>una vez</strong>.',
        templateName: 'estado_negados',
        fetchEndpoint: '/admin/api/pending-denegado',
        sendEndpoint: '/admin/api/trigger-bulk-denegado',
        confirm: n => `¿Estás seguro de enviar el template "estado_negados" a ${n} cliente(s) seleccionado(s)?\n\nRecuerda: cada cliente solo debería recibir esta notificación una vez.`,
        executeLabel: '🚫 Enviar a Seleccionados',
        batchSize: 20,
        emptyMsg: 'No hay clientes pendientes por notificar.',
        features: { empresa: true, fechaSolicitud: true },
        metrics: {
            endpoint: '/admin/api/negados-metrics',
            header: 'Métricas: estado_negados',
            cards: [
                { label: 'Total enviados', color: '#6b7280', count: m => m.total },
                { label: 'Consultaron motivo', color: '#d97706', count: m => m.consultaron_motivo_count, pct: true },
                { label: 'Respondieron por chat', color: '#2563eb', count: m => m.respondieron_chat_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Clientes que consultaron el motivo o respondieron',
            emptyMsg: 'Sin respuestas aún.',
        },
    },
    {
        id: 'actualizacion',
        icon: '📝',
        accent: '#9333ea',
        title: 'Envíos Masivos: Actualización Anual de Datos',
        description: 'Notifica a los clientes con préstamo <strong>activo</strong> que no han actualizado sus datos de contacto en los últimos 12 meses. Se enviará el template <strong>actualizacion_datos</strong>, que abre el flujo conversacional para que el cliente confirme cédula, teléfonos, dirección, correo y referencia personal.',
        templateName: 'actualizacion_datos',
        fetchEndpoint: '/admin/api/pending-actualizacion-datos',
        sendEndpoint: '/admin/api/trigger-bulk-actualizacion-datos',
        confirm: n => `¿Enviar el template "actualizacion_datos" a ${n} cliente(s)?\n\nEl cliente verá el bloque legal con la cita contractual y dos botones (Actualizar ahora / Más tarde).`,
        executeLabel: '📝 Enviar a Seleccionados',
        batchSize: 20,
        emptyMsg: 'No hay clientes pendientes por notificar.',
        features: {},
    },
].forEach(cfg => {
    const panel = createCampaignPanel(cfg);
    if (panel) CampaignPanels[cfg.id] = panel;
});

// ── Campañas Familia B (paste/upload + métricas) ────────────────────

[
    {
        id: 'referidosab',
        icon: '🤝',
        accent: '#0f766e',
        title: 'Campaña Referidos A/B',
        templateName: 'plantilla_referidos_v1 / plantilla_referidos_v2',
        unit: 'contactos',
        sendEndpoint: '/admin/api/trigger-bulk-referidos-ab',
        confirm: n => `¿Enviar el test A/B de referidos a ${n} contactos?\n\nEl sistema asignará aleatoriamente 50/50 entre descuento en tasa y aprobación express.`,
        executeLabel: 'Enviar Referidos A/B',
        metrics: {
            endpoint: '/admin/api/referidos-ab-metrics',
            header: 'Métricas: Referidos A/B',
            cards: [
                { label: 'Total enviados', color: '#0f766e', count: m => m.total },
                { label: 'V1 tasa', color: '#0284c7', count: m => m.variant_a_total, pct: true },
                { label: 'V2 express', color: '#7c3aed', count: m => m.variant_b_total, pct: true },
                { label: 'Cómo funciona', color: '#0891b2', count: m => m.como_funciona_count, pct: true },
                { label: 'Quiero beneficio', color: '#059669', count: m => m.quiero_beneficio_count, pct: true },
                { label: 'Quizás después', color: '#dc2626', count: m => m.quizas_despues_count, pct: true },
                { label: 'Referidos', color: '#d97706', count: m => m.referral_count, pct: true },
            ],
            tableTitle: 'Referidos capturados',
            emptyMsg: 'Sin referidos capturados aún.',
            tableColumns: ['Contacto', 'Teléfono', 'Variante', 'Referido', 'Tel. referido', 'Capturado', 'Chat'],
            rowCells: (r, h) => `
                <td>${h.escapeHtml(r.client_name || '—')}</td>
                <td class="pcmp-mono">${h.escapeHtml(r.phone || '')}</td>
                <td>${h.escapeHtml(r.variant_label || '—')}</td>
                <td>${h.escapeHtml(r.referred_name || '—')}</td>
                <td class="pcmp-mono">${h.escapeHtml(r.referred_phone || '—')}</td>
                <td class="cmp-muted">${h.formatDate(r.responded_at)}</td>
                <td class="cmp-c"><button type="button" class="pcmp-chat-btn" onclick="goToChat('${h.escapeHtml(r.phone || '')}')">Chat</button></td>
            `,
            extraSummary: renderReferralAbSummary,
        },
    },
    {
        id: 'leads',
        icon: '🎯',
        accent: '#059669',
        title: 'Campaña Leads: Oferta de Crédito',
        templateName: 'contacto_leads',
        unit: 'leads',
        sendEndpoint: '/admin/api/trigger-bulk-leads',
        confirm: n => `¿Estás seguro de enviar la campaña Leads a ${n} personas?`,
        executeLabel: '🎯 Enviar a Leads',
        metrics: {
            endpoint: '/admin/api/lead-metrics',
            header: 'Métricas: contacto_leads',
            cards: [
                { label: 'Total enviados', color: '#059669', count: m => m.total },
                { label: 'Solicitaron crédito', color: '#0284c7', count: m => m.solicitar_count, pct: true },
                { label: 'Pidieron asesor', color: '#d97706', count: m => m.hablar_asesor_count, pct: true },
                { label: 'Ahora no, gracias', color: '#dc2626', count: m => m.ahora_no_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Leads que solicitaron crédito',
            emptyMsg: 'Sin conversiones aún.',
        },
    },
    {
        id: 'renovados',
        icon: '🔄',
        accent: '#0284c7',
        title: 'Campaña Renovados: Oferta de Renovación',
        templateName: 'contacto_renovados',
        unit: 'renovados',
        sendEndpoint: '/admin/api/trigger-bulk-renovados',
        confirm: n => `¿Estás seguro de enviar la campaña Renovados a ${n} personas?`,
        executeLabel: '🔄 Enviar a Renovados',
        metrics: {
            endpoint: '/admin/api/renovado-metrics',
            header: 'Métricas: estado_renovar',
            cards: [
                { label: 'Total enviados', color: '#0284c7', count: m => m.total },
                { label: 'Renovaron', color: '#059669', count: m => m.solicitar_count, pct: true },
                { label: 'No interesados', color: '#dc2626', count: m => m.no_quiero_count, pct: true },
                { label: 'Más información', color: '#d97706', count: m => m.mas_info_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Clientes que solicitaron renovación',
            emptyMsg: 'Sin renovaciones aún.',
        },
    },
    {
        id: 'anticipos',
        icon: '💰',
        accent: '#7c3aed',
        title: 'Campaña Anticipos: Anticipo de Nómina',
        templateName: 'anticipo_nomina',
        unit: 'anticipos',
        sendEndpoint: '/admin/api/trigger-bulk-anticipos',
        forceOption: 'Reenviar también a quienes indicaron que no estaban interesados',
        confirm: (n, force) => force
            ? `¿Estás seguro de enviar la campaña Anticipos a ${n} personas, incluyendo a quienes ya indicaron que no estaban interesados?`
            : `¿Estás seguro de enviar la campaña Anticipos a ${n} personas?`,
        executeLabel: '💰 Enviar Anticipos',
        metrics: {
            endpoint: '/admin/api/anticipo-metrics',
            header: 'Métricas: anticipo_salario',
            cards: [
                { label: 'Total enviados', color: '#7c3aed', count: m => m.total },
                { label: 'Solicitaron', color: '#059669', count: m => m.solicitar_count, pct: true },
                { label: 'No interesados', color: '#dc2626', count: m => m.no_gracias_count, pct: true },
                { label: 'Respondieron por chat', color: '#2563eb', count: m => m.respondieron_chat_count, pct: true },
                { label: 'Sin respuesta', color: '#9ca3af', count: m => m.sin_respuesta_count, pct: true },
            ],
            tableTitle: 'Interesados — seguimiento de formulario',
            emptyMsg: 'Sin interesados aún.',
            formColumn: true,
        },
    },
].forEach(cfg => {
    const panel = createPasteCampaign(cfg);
    if (panel) CampaignPanels[cfg.id] = panel;
});

// Toggle de "formulario enviado" en la tabla de interesados de Anticipos
async function toggleAnticipioForm(phone, btn) {
    try {
        const res = await fetch(`/admin/api/anticipo-toggle-form/${phone}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            btn.classList.toggle('is-done', data.form_submitted);
            btn.classList.toggle('is-pending', !data.form_submitted);
            btn.innerText = data.form_submitted ? '✅ Enviado' : '⏳ Pendiente';
        }
    } catch (e) {
        console.error('toggleAnticipioForm error:', e);
    }
}
