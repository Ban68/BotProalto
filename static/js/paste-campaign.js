// ── PasteCampaign: factory para campañas "paste/upload" (Familia B) ─
// Leads, Renovados y Anticipos: panel de métricas del template + lista
// de destinatarios pegada (tab/coma/;) o subida por Excel/CSV (SheetJS)
// + envío por lotes. Reemplaza los 3 bloques casi idénticos de legacy.js.
//
// Depende en runtime de: XLSX (CDN), goToChat (legacy.js) y, para
// anticipos, toggleAnticipioForm (campaigns.js).

function createPasteCampaign(cfg) {
    const mount = document.querySelector(`[data-campaign="${cfg.id}"]`);
    if (!mount) { console.error(`PasteCampaign: no existe mount para "${cfg.id}"`); return null; }

    const m = cfg.metrics;
    const tableCols = ['Nombre', 'Teléfono', 'Respondió', ...(m.formColumn ? ['Formulario'] : []), 'Chat'];
    const renderTableCols = m.tableColumns || tableCols;
    const colCount = renderTableCols.length;

    mount.innerHTML = `
    <div class="cmp-panel" style="--accent:${cfg.accent};">
        <h2 class="cmp-title">${cfg.icon || ''} ${cfg.title}</h2>

        <div class="pcmp-metrics card-x">
            <div class="pcmp-metrics-head">
                <strong>${m.header}</strong>
                <button type="button" data-ref="metricsRefresh">🔄 Actualizar</button>
            </div>
            <div class="pcmp-timeline" data-ref="timeline"></div>
            <div class="pcmp-cards" style="grid-template-columns: repeat(${m.cards.length}, 1fr);">
                ${m.cards.map((c, i) => `
                <div class="pcmp-card">
                    <div class="pcmp-card-value" style="color:${c.color};" data-card="${i}">—</div>
                    <div class="pcmp-card-label">${c.label}</div>
                    <div class="pcmp-card-pct" style="color:${c.color};" data-card-pct="${i}"></div>
                </div>`).join('')}
            </div>
            <div class="pcmp-extra" data-ref="metricsExtra" style="display:none;"></div>
            <div class="pcmp-table-block">
                <div class="pcmp-table-title">${m.tableTitle}</div>
                <div class="pcmp-table-wrap">
                    <table class="table-x pcmp-table">
                        <thead><tr>${renderTableCols.map(c => `<th${c === 'Formulario' || c === 'Chat' ? ' class="cmp-c"' : ''}>${c}</th>`).join('')}</tr></thead>
                        <tbody data-ref="metricsBody">
                            <tr><td colspan="${colCount}" class="cmp-empty">Haz clic en Actualizar para cargar.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <p class="cmp-desc">
            Ingresa la lista de personas a las que deseas enviar la plantilla "${cfg.templateName}".
            <strong>Formato:</strong> Un cliente por línea, teléfono seguido de coma y nombre (Ej: <em>573001234567, Juan Pérez</em>).
        </p>

        <div class="cmp-card card-x">
            <div class="cmp-card-head">
                <h3 class="cmp-count-line">Lista de Destinatarios</h3>
                <div class="cmp-actions">
                    <input type="file" data-ref="file" accept=".csv, .xlsx, .xls" style="display:none;">
                    <button type="button" class="btn-x btn-x-outline" data-ref="fileBtn" style="border-color:${cfg.accent}; color:${cfg.accent};">📂 Cargar Excel/CSV</button>
                    <button type="button" class="btn-x btn-x-outline" data-ref="clear">🗑️ Limpiar</button>
                </div>
            </div>
            <textarea data-ref="input" rows="10" class="pcmp-textarea" placeholder="573001234567, Carlos García&#10;573109876543, Maria Lopez"></textarea>
            ${cfg.forceOption ? `
            <label class="pcmp-force">
                <input type="checkbox" data-ref="force">
                ${cfg.forceOption}
            </label>` : ''}
            <div class="pcmp-footer">
                <span class="pcmp-status" data-ref="status">Listo para procesar.</span>
                <button type="button" class="btn-x cmp-execute" data-ref="execute">${cfg.executeLabel}</button>
            </div>
        </div>

        <div class="cmp-results" data-ref="results" style="display:none;">
            <h3>Resultados de la Campaña:</h3>
            <div class="cmp-result cmp-result-ok"><strong>Éxitos:</strong> <span data-ref="okCount">0</span></div>
            <div class="cmp-result cmp-result-fail"><strong>Fallos:</strong> <span data-ref="failCount">0</span><ul data-ref="errList"></ul></div>
        </div>
    </div>`;

    const $ = ref => mount.querySelector(`[data-ref="${ref}"]`);
    const escapeHtml = value => String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    const formatDate = value => value
        ? new Date(value).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' })
        : '-';

    // ── Timeline (filtro de intervalo de tiempo) ───────────────────
    const timeline = createMetricsTimeline(() => fetchMetrics());
    $('timeline').appendChild(timeline.el);

    // ── Métricas ───────────────────────────────────────────────────
    async function fetchMetrics() {
        try {
            const res = await fetch(m.endpoint + timeline.params());
            const data = await res.json();
            if (!res.ok || !data.metrics) {
                throw new Error(data.message || `No se pudieron cargar métricas (${res.status})`);
            }
            const mt = data.metrics;
            const total = mt.total || 0;

            m.cards.forEach((c, i) => {
                const value = c.count(mt) || 0;
                const displayValue = c.format ? c.format(value, mt) : value;
                mount.querySelector(`[data-card="${i}"]`).innerText = (i === 0 && !value) ? '0' : displayValue;
                const pctEl = mount.querySelector(`[data-card-pct="${i}"]`);
                pctEl.innerText = (c.pct && total > 0) ? Math.round((value / total) * 100) + '%' : '';
            });

            const extra = $('metricsExtra');
            if (m.extraSummary) {
                extra.innerHTML = m.extraSummary(mt, { escapeHtml });
                extra.style.display = 'block';
            } else {
                extra.style.display = 'none';
            }

            const tbody = $('metricsBody');
            const rows = mt[m.rowsKey || 'solicitar'] || [];
            if (rows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="${colCount}" class="cmp-empty">${m.emptyMsg}</td></tr>`;
                return;
            }
            tbody.innerHTML = rows.map(r => {
                if (m.rowCells) {
                    return `<tr>${m.rowCells(r, { escapeHtml, formatDate })}</tr>`;
                }
                const fecha = r.responded_at ? new Date(r.responded_at).toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'short' }) : '—';
                const formCell = m.formColumn ? `
                    <td class="cmp-c">
                        <button type="button" class="pcmp-form-btn ${r.form_submitted ? 'is-done' : 'is-pending'}" onclick="toggleAnticipioForm('${r.phone}', this)">
                            ${r.form_submitted ? '✅ Enviado' : '⏳ Pendiente'}
                        </button>
                    </td>` : '';
                return `<tr>
                    <td>${r.client_name || '—'}</td>
                    <td class="pcmp-mono">${r.phone}</td>
                    <td class="cmp-muted">${fecha}</td>
                    ${formCell}
                    <td class="cmp-c"><button type="button" class="pcmp-chat-btn" onclick="goToChat('${r.phone}')">Chat</button></td>
                </tr>`;
            }).join('');
        } catch (e) {
            console.error(`fetchMetrics ${cfg.id} error:`, e);
            $('metricsBody').innerHTML = `<tr><td colspan="${colCount}" class="cmp-empty cmp-empty-err">No se pudieron cargar las métricas: ${escapeHtml(e.message || e)}</td></tr>`;
        }
    }

    // ── Parse de destinatarios ─────────────────────────────────────
    function parseUsers() {
        const lines = $('input').value.trim().split('\n');
        const users = [];
        for (const line of lines) {
            if (!line.trim()) continue;
            const parts = line.includes('\t') ? line.split('\t') : (line.includes(',') ? line.split(',') : line.split(';'));
            if (parts.length >= 2) {
                const phone = parts[0].replace(/\D/g, '').trim();
                const name = parts.slice(1).join(' ').trim();
                if (phone && name) users.push({ phone, name });
            }
        }
        return users;
    }

    // ── Envío ──────────────────────────────────────────────────────
    async function execute() {
        if (!$('input').value.trim()) {
            alert('Por favor, ingresa al menos un número y nombre en el formato indicado.');
            return;
        }
        const allUsers = parseUsers();
        if (allUsers.length === 0) {
            alert('No se detectaron usuarios válidos. Revisa el formato.');
            return;
        }
        const force = cfg.forceOption ? $('force').checked : false;
        if (!confirm(cfg.confirm(allUsers.length, force))) return;

        const btn = $('execute');
        const statusText = $('status');
        btn.disabled = true;

        let totalSuccess = 0, totalFail = 0, allErrors = [];
        const batchSize = 15;

        $('results').style.display = 'block';

        for (let i = 0; i < allUsers.length; i += batchSize) {
            const chunk = allUsers.slice(i, i + batchSize);
            btn.innerText = `⌛ ${i + 1} - ${Math.min(i + batchSize, allUsers.length)} de ${allUsers.length}...`;
            statusText.innerText = `Enviando lote de ${chunk.length} ${cfg.unit}...`;
            try {
                const body = cfg.forceOption ? { users: chunk, force } : { users: chunk };
                const res = await fetch(cfg.sendEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                if (res.ok && data.results) {
                    totalSuccess += data.results.success;
                    totalFail += data.results.fail;
                    if (data.results.errors) allErrors = allErrors.concat(data.results.errors);
                    $('okCount').innerText = totalSuccess;
                    $('failCount').innerText = totalFail;
                    $('errList').innerHTML = allErrors.length > 0
                        ? allErrors.map(err => `<li>${err}</li>`).join('')
                        : '<li>Sin errores reportados.</li>';
                } else {
                    totalFail += chunk.length;
                }
            } catch (e) {
                console.error(e);
                totalFail += chunk.length;
            }
            await new Promise(r => setTimeout(r, 500));
        }

        btn.innerText = cfg.executeLabel;
        btn.disabled = false;
        statusText.innerText = 'Campaña finalizada.';
        alert(`Campaña terminada.\nÉxitos: ${totalSuccess}\nFallos: ${totalFail}`);
    }

    // ── Upload de Excel/CSV ────────────────────────────────────────
    function handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        const statusText = $('status');
        statusText.innerText = 'Leyendo archivo...';
        const reader = new FileReader();
        reader.onload = function (e) {
            try {
                const data = new Uint8Array(e.target.result);
                const workbook = XLSX.read(data, { type: 'array' });
                const worksheet = workbook.Sheets[workbook.SheetNames[0]];
                const json = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
                let resultText = '';
                let count = 0;
                for (let i = 0; i < json.length; i++) {
                    const row = json[i];
                    if (row.length >= 2) {
                        const phone = String(row[0] || '').replace(/\D/g, '').trim();
                        const name = String(row[1] || '').trim();
                        if (i === 0 && (phone === 'telefono' || phone === 'phone' || isNaN(phone))) continue;
                        if (phone && name) {
                            resultText += `${phone}, ${name}\n`;
                            count++;
                        }
                    }
                }
                $('input').value = resultText;
                statusText.innerText = `Se cargaron ${count} ${cfg.unit} exitosamente.`;
                event.target.value = '';
            } catch (err) {
                console.error('Error al leer Excel:', err);
                alert('Error al leer el archivo.');
                statusText.innerText = 'Error de lectura.';
            }
        };
        reader.readAsArrayBuffer(file);
    }

    // Pegado desde Excel (tabs) → convertir a formato "teléfono, nombre"
    function handlePaste(e) {
        const pastedData = (e.clipboardData || window.clipboardData).getData('Text');
        if (!pastedData.includes('\t')) return;
        e.preventDefault();
        const formatted = pastedData.split(/\r?\n/).map(line => {
            if (!line.trim()) return '';
            const parts = line.split('\t');
            return parts.length >= 2 ? `${parts[0].trim()}, ${parts.slice(1).join(' ').trim()}` : line;
        }).filter(l => l !== '').join('\n');
        const ta = e.target;
        const start = ta.selectionStart, end = ta.selectionEnd;
        ta.value = ta.value.substring(0, start) + formatted + ta.value.substring(end);
        $('status').innerText = 'Datos de Excel pegados y formateados.';
    }

    // ── Eventos ────────────────────────────────────────────────────
    $('metricsRefresh').addEventListener('click', fetchMetrics);
    $('fileBtn').addEventListener('click', () => $('file').click());
    $('file').addEventListener('change', handleFileUpload);
    $('clear').addEventListener('click', () => { $('input').value = ''; });
    $('input').addEventListener('paste', handlePaste);
    $('execute').addEventListener('click', execute);

    return { refresh: fetchMetrics };
}
