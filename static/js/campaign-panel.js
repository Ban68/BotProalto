// ── CampaignPanel: factory para campañas "pending-list" (Familia A) ─
// Genera el DOM completo del panel y toda su lógica: fetch de elegibles
// + excluidos, selección con checkAll, filtro búsqueda+empresa, sección
// de excluidos con confirmación forzada, envío por lotes y resultados.
// Reemplaza los 5 bloques casi idénticos que vivían en legacy.js
// (envios, rojo, amarillo, negados, actualizacion).
//
// Depende de helpers globales de legacy.js (cargado después, pero solo
// se invocan en runtime): toggleEmpresaDrop, populatePanelEmpresaFilter,
// applyPanelFilter, showExcludedConfirmModal.

function createCampaignPanel(cfg) {
    const f = cfg.features || {};
    const mount = document.querySelector(`[data-campaign="${cfg.id}"]`);
    if (!mount) { console.error(`CampaignPanel: no existe mount para "${cfg.id}"`); return null; }

    let pendingData = [];
    let excludedData = [];

    // ── DOM ────────────────────────────────────────────────────────
    const empresaWrap = f.empresa ? `
        <div class="empresa-multi-wrap cmp-empresa" data-search="${cfg.id}Search" data-tbody="${cfg.id}TableBody">
            <button type="button" class="empresa-btn" onclick="toggleEmpresaDrop('${cfg.id}EmpresaDrop')">
                <span>🏢 Todas las empresas</span><span class="cmp-chevron">▾</span>
            </button>
            <div id="${cfg.id}EmpresaDrop" class="empresa-drop" style="display:none;"></div>
        </div>` : '';

    const fechaSolCol = f.fechaSolicitud ? '<th>Fecha Solicitud</th>' : '';
    const colCount = 5 + (f.fechaSolicitud ? 1 : 0);

    mount.innerHTML = `
    <div class="cmp-panel" style="--accent:${cfg.accent};">
        <h2 class="cmp-title">${cfg.icon || ''} ${cfg.title}</h2>
        <p class="cmp-desc">${cfg.description}</p>
        <div class="cmp-card card-x">
            <div class="cmp-card-head">
                <div>
                    <h3 class="cmp-count-line">Clientes listos para notificar: <span data-ref="count">0</span></h3>
                    <div class="cmp-statline" data-ref="statline"></div>
                </div>
                <div class="cmp-actions">
                    ${f.soloNuevos ? '<button type="button" class="btn-x btn-x-outline" data-ref="soloNuevos" title="Marcar solo los que nunca han recibido el template">☑️ Solo nuevos (0 envíos)</button>' : ''}
                    <button type="button" class="btn-x btn-x-outline cmp-refresh" data-ref="refresh">🔄 Refrescar Lista</button>
                </div>
            </div>
            <div class="cmp-toolbar">
                <input type="text" id="${cfg.id}Search" class="input-x cmp-search" placeholder="🔍 Buscar por nombre o teléfono...">
                ${empresaWrap}
            </div>
            <div class="cmp-table-wrap">
                <table class="table-x cmp-table">
                    <thead>
                        <tr>
                            <th class="cmp-c cmp-check-col"><input type="checkbox" data-ref="checkAll" checked title="Seleccionar todos (filas visibles)"></th>
                            <th>Teléfono</th>
                            <th>Nombre</th>
                            ${fechaSolCol}
                            <th class="cmp-c" title="Veces que se ha enviado el template ${cfg.templateName}">Envíos</th>
                            <th>Último Envío</th>
                        </tr>
                    </thead>
                    <tbody id="${cfg.id}TableBody">
                        <tr><td colspan="${colCount}" class="cmp-empty">Cargando clientes...</td></tr>
                    </tbody>
                </table>
            </div>
            <div class="cmp-excluded" data-ref="exclSection" style="display:none;">
                <div class="cmp-excluded-bar">
                    <button type="button" class="cmp-excluded-toggle" data-ref="exclToggle">▶ Ver excluidos (0)</button>
                    <button type="button" class="btn-x btn-x-outline cmp-mini" data-ref="exclCopy" title="Copiar para pegar en Excel o Google Sheets">📋 Copiar</button>
                    <button type="button" class="btn-x btn-x-outline cmp-mini" data-ref="exclCsv" title="Descargar como archivo CSV">⬇️ CSV</button>
                </div>
                <div class="cmp-excluded-content" data-ref="exclContent" style="display:none;">
                    <table class="table-x cmp-excl-table">
                        <thead>
                            <tr>
                                <th class="cmp-c cmp-check-col" title="Forzar envío (requiere confirmación)">✉️</th>
                                <th>Teléfono</th>
                                <th>Nombre</th>
                                <th class="cmp-c">Envíos</th>
                                <th>Razón de exclusión</th>
                            </tr>
                        </thead>
                        <tbody data-ref="exclBody"></tbody>
                    </table>
                </div>
            </div>
            <p class="cmp-hint">Puedes incluir excluidos marcando su casilla en "Ver excluidos". Se pedirá confirmación explícita antes de enviar.</p>
        </div>
        <div class="cmp-execute-bar">
            <button type="button" class="btn-x cmp-execute" data-ref="execute" disabled>${cfg.executeLabel}</button>
        </div>
        <div class="cmp-results" data-ref="results" style="display:none;">
            <h3>Resultados del Envío:</h3>
            <div class="cmp-result cmp-result-ok"><strong>Éxitos:</strong> <span data-ref="okCount">0</span></div>
            <div class="cmp-result cmp-result-fail"><strong>Fallos:</strong> <span data-ref="failCount">0</span><ul data-ref="errList"></ul></div>
        </div>
    </div>`;

    const $ = ref => mount.querySelector(`[data-ref="${ref}"]`);
    const tbody = mount.querySelector(`#${cfg.id}TableBody`);
    const searchInput = mount.querySelector(`#${cfg.id}Search`);

    // ── Selección ──────────────────────────────────────────────────
    function rowChecks() { return tbody.querySelectorAll('input[data-idx]'); }

    function updateCount() {
        const total = rowChecks().length;
        const selected = tbody.querySelectorAll('input[data-idx]:checked').length;
        const exclSelected = $('exclBody').querySelectorAll('input[data-excl-idx]:checked').length;
        $('count').innerText = `${selected} / ${total}`;
        $('execute').disabled = (selected + exclSelected) === 0;
        const master = $('checkAll');
        master.indeterminate = selected > 0 && selected < total;
        master.checked = total > 0 && selected === total;
    }

    function renderStatLine() {
        const eligibleCount = rowChecks().length;
        const totalCount = eligibleCount + excludedData.length;
        $('statline').innerHTML = totalCount > 0
            ? `Total en estado: <strong>${totalCount}</strong> &nbsp;·&nbsp; <span class="cmp-stat-ok">${eligibleCount} aplican</span> &nbsp;·&nbsp; <span class="cmp-stat-excl">${excludedData.length} excluidos</span>`
            : '';
    }

    // ── Render de filas ────────────────────────────────────────────
    function fmtLastSent(user) {
        if (!user.last_sent) return f.lastSentTime ? 'Nunca' : '—';
        const d = new Date(user.last_sent);
        return f.lastSentTime
            ? d.toLocaleString('es-CO', { timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
            : d.toLocaleDateString('es-CO');
    }

    function renderRows() {
        let rows = '';
        pendingData.forEach((user, idx) => {
            const sendCount = user.send_count || 0;
            const countClass = sendCount >= 3 ? 'cmp-sends-high' : sendCount >= 1 ? 'cmp-sends-mid' : '';
            const empresaLabel = (f.empresa && user.empresa) ? `<br><span class="cmp-empresa-sub">${user.empresa}</span>` : '';
            const fincaBadge = (f.finca && (user.tipo_empleador || '').toUpperCase() === 'FINCA')
                ? '<span class="cmp-finca-badge">FINCA</span>' : '';
            const fechaSolCell = f.fechaSolicitud ? `<td class="cmp-nowrap">${user.fecha_solicitud || '—'}</td>` : '';
            rows += `<tr data-empresa="${(user.empresa || '').toLowerCase()}">
                <td class="cmp-c"><input type="checkbox" data-idx="${idx}" checked></td>
                <td>${user.phone}</td>
                <td>${user.name}${fincaBadge}${empresaLabel}</td>
                ${fechaSolCell}
                <td class="cmp-c ${countClass}">${sendCount}</td>
                <td class="cmp-muted">${fmtLastSent(user)}</td>
            </tr>`;
        });
        tbody.innerHTML = rows;
    }

    function renderExcluded() {
        if (excludedData.length === 0) {
            $('exclSection').style.display = 'none';
            return;
        }
        $('exclSection').style.display = 'block';
        $('exclToggle').textContent = `▶ Ver excluidos (${excludedData.length})`;
        $('exclContent').style.display = 'none';
        $('exclBody').innerHTML = excludedData.map((user, idx) => {
            const empresaLabel = user.empresa ? `<br><span class="cmp-empresa-sub">${user.empresa}</span>` : '';
            const reasons = (user.excluded_reasons || []).map(r => `<span class="cmp-reason-pill">${r}</span>`).join('');
            return `<tr>
                <td class="cmp-c"><input type="checkbox" data-excl-idx="${idx}" title="Incluir en el envío (requiere confirmación)"></td>
                <td class="cmp-muted">${user.phone}</td>
                <td class="cmp-muted">${user.name}${empresaLabel}</td>
                <td class="cmp-c cmp-muted">${user.send_count || 0}</td>
                <td>${reasons}</td>
            </tr>`;
        }).join('');
    }

    // ── Fetch ──────────────────────────────────────────────────────
    async function refresh(hideResults = true) {
        if (hideResults) $('results').style.display = 'none';
        tbody.innerHTML = `<tr><td colspan="${colCount}" class="cmp-empty">Consultando clientes elegibles...</td></tr>`;
        $('execute').disabled = true;
        pendingData = [];
        excludedData = [];
        $('exclSection').style.display = 'none';
        $('statline').innerHTML = '';

        try {
            const res = await fetch(cfg.fetchEndpoint);
            const data = await res.json();
            if (res.ok && data.pending) {
                pendingData = data.pending;
                if (pendingData.length === 0) {
                    $('count').innerText = '0';
                    tbody.innerHTML = `<tr><td colspan="${colCount}" class="cmp-empty cmp-empty-ok">✅ ${cfg.emptyMsg || 'No hay clientes pendientes por notificar hoy.'}</td></tr>`;
                } else {
                    renderRows();
                    if (f.empresa) populatePanelEmpresaFilter(pendingData, `${cfg.id}EmpresaDrop`);
                    updateCount();
                }
                excludedData = data.excluded || [];
                renderExcluded();
                renderStatLine();
            } else {
                tbody.innerHTML = `<tr><td colspan="${colCount}" class="cmp-empty cmp-empty-err">Error: ${data.message || 'Desconocido'}</td></tr>`;
            }
        } catch (e) {
            console.error(e);
            tbody.innerHTML = `<tr><td colspan="${colCount}" class="cmp-empty cmp-empty-err">Error de conexión al cargar.</td></tr>`;
        }
    }

    // ── Envío por lotes ────────────────────────────────────────────
    function normalizeError(err) {
        if (typeof err === 'string') return err;
        return `${err.phone || 'Error'}: ${err.error || 'Desconocido'}`;
    }

    async function doExecute(selectedUsers) {
        const btn = $('execute');
        btn.disabled = true;
        btn.innerText = '⌛ Procesando...';

        let totalSuccess = 0, totalFailed = 0, allErrors = [];
        const batchSize = cfg.batchSize || 15;
        const totalUsers = selectedUsers.length;

        $('results').style.display = 'block';

        for (let i = 0; i < totalUsers; i += batchSize) {
            const chunk = selectedUsers.slice(i, i + batchSize);
            btn.innerText = `⌛ Enviando ${i + 1} - ${Math.min(i + batchSize, totalUsers)} de ${totalUsers}...`;
            try {
                const res = await fetch(cfg.sendEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ users: chunk })
                });
                const data = await res.json();
                if (res.ok && data.results) {
                    totalSuccess += data.results.success;
                    totalFailed += (data.results.fail ?? data.results.failed ?? 0);
                    if (data.results.errors) allErrors = allErrors.concat(data.results.errors);
                    $('okCount').innerText = totalSuccess;
                    $('failCount').innerText = totalFailed;
                    $('errList').innerHTML = allErrors.length > 0
                        ? allErrors.map(err => `<li>${normalizeError(err)}</li>`).join('')
                        : '<li>Sin errores en este lote.</li>';
                } else {
                    totalFailed += chunk.length;
                    allErrors.push(`Lote: ${data.message || 'Error de servidor'}`);
                }
            } catch (e) {
                totalFailed += chunk.length;
                allErrors.push('Red: Error de conexión');
            }
            await new Promise(r => setTimeout(r, 500));
        }

        btn.innerText = cfg.executeLabel;
        btn.disabled = false;
        await refresh(false);
        alert(`Proceso finalizado.\nÉxitos: ${totalSuccess}\nFallos: ${totalFailed}`);
    }

    function execute() {
        const selectedEligible = Array.from(tbody.querySelectorAll('input[data-idx]:checked'))
            .map(cb => pendingData[parseInt(cb.dataset.idx)]);
        const selectedExcluded = Array.from($('exclBody').querySelectorAll('input[data-excl-idx]:checked'))
            .map(cb => excludedData[parseInt(cb.dataset.exclIdx)]);

        if (selectedEligible.length === 0 && selectedExcluded.length === 0) return;

        const doSend = () => doExecute([...selectedEligible, ...selectedExcluded]);

        if (selectedExcluded.length > 0) {
            showExcludedConfirmModal(selectedExcluded, doSend);
            return;
        }
        if (!confirm(cfg.confirm(selectedEligible.length))) return;
        doSend();
    }

    // ── Export de excluidos ────────────────────────────────────────
    function exclRowsForExport() {
        return excludedData.map(u => [u.phone, u.name || '', u.empresa || '', u.send_count || 0, (u.excluded_reasons || []).join(', ')]);
    }

    function copyExcluded() {
        if (excludedData.length === 0) { alert('No hay excluidos para copiar.'); return; }
        const header = 'Teléfono\tNombre\tEmpresa\tEnvíos\tRazón de exclusión';
        const rows = exclRowsForExport().map(r => r.join('\t'));
        navigator.clipboard.writeText([header, ...rows].join('\n'))
            .then(() => alert(`✅ ${excludedData.length} excluidos copiados. Pega directamente en Excel o Google Sheets.`))
            .catch(() => alert('Error al copiar. Intenta exportar como CSV.'));
    }

    function exportExcludedCSV() {
        if (excludedData.length === 0) { alert('No hay excluidos para exportar.'); return; }
        const esc = v => `"${String(v).replace(/"/g, '""')}"`;
        const header = 'Teléfono,Nombre,Empresa,Envíos,Razón de exclusión';
        const rows = exclRowsForExport().map(r => [r[0], esc(r[1]), esc(r[2]), r[3], esc(r[4])].join(','));
        const csv = '﻿' + [header, ...rows].join('\n'); // BOM para Excel UTF-8
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `excluidos_${cfg.id}_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ── Eventos ────────────────────────────────────────────────────
    tbody.addEventListener('change', e => { if (e.target.matches('input[data-idx]')) updateCount(); });
    $('exclBody').addEventListener('change', e => { if (e.target.matches('input[data-excl-idx]')) updateCount(); });
    $('checkAll').addEventListener('change', e => {
        rowChecks().forEach(cb => {
            // solo afecta filas visibles (respeta filtros de búsqueda/empresa)
            const row = cb.closest('tr');
            if (!row || row.style.display !== 'none') cb.checked = e.target.checked;
        });
        updateCount();
    });
    $('refresh').addEventListener('click', () => refresh());
    $('execute').addEventListener('click', execute);
    if (f.soloNuevos) {
        $('soloNuevos').addEventListener('click', () => {
            rowChecks().forEach(cb => { cb.checked = pendingData[parseInt(cb.dataset.idx)].send_count === 0; });
            updateCount();
        });
    }
    $('exclToggle').addEventListener('click', () => {
        const content = $('exclContent');
        const open = content.style.display !== 'none';
        content.style.display = open ? 'none' : 'block';
        $('exclToggle').textContent = `${open ? '▶' : '▼'} Ver excluidos (${excludedData.length})`;
    });
    $('exclCopy').addEventListener('click', copyExcluded);
    $('exclCsv').addEventListener('click', exportExcludedCSV);
    searchInput.addEventListener('input', () => applyPanelFilter(`${cfg.id}Search`, `${cfg.id}TableBody`, `${cfg.id}EmpresaDrop`));

    return { refresh };
}
