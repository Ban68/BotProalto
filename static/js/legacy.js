        let currentActivePhone = null;
        let lastFetchTime = 0;
        let knownAgentModes = {};
        let currentTab = 'activas'; // 'activas' | 'prospectos' | 'archivadas'
        let advisorName = localStorage.getItem('proalto_advisor_name');
        let currentStatus = 'bot';
        let latestActiveAdvisors = []; // To store the list from heartbeat

        function toggleOnlinePanel() {
            const panel = document.getElementById('onlineAdvisorsContainer');
            const chevron = document.getElementById('onlineChevron');
            const isOpen = panel.style.display !== 'none';
            panel.style.display = isOpen ? 'none' : 'block';
            if (chevron) chevron.textContent = isOpen ? '▾' : '▴';
        }

        // Close online panel when clicking outside
        document.addEventListener('click', function(e) {
            const toggle = document.getElementById('btnOnlineToggle');
            const panel = document.getElementById('onlineAdvisorsContainer');
            if (panel && toggle && !toggle.contains(e.target) && !panel.contains(e.target)) {
                panel.style.display = 'none';
                const chevron = document.getElementById('onlineChevron');
                if (chevron) chevron.textContent = '▾';
            }
        });

        function toggleCustomAdvisor() {
            const select = document.getElementById('advisorSelect');
            const custom = document.getElementById('customAdvisor');
            if (select.value === 'otro') {
                custom.classList.remove('hidden');
            } else {
                custom.classList.add('hidden');
            }
        }

        function showAdvisorModal(callback) {
            const modal = document.getElementById('advisorModal');
            modal.classList.remove('hidden');
            window.pendingAdvisorCallback = callback;
        }

        function confirmAdvisor() {
            const select = document.getElementById('advisorSelect');
            const customInput = document.getElementById('customAdvisor');
            let name = select.value;
            if (name === 'otro') name = customInput.value.trim();

            if (!name) {
                alert('Por favor selecciona o escribe tu nombre');
                return;
            }

            advisorName = name;
            localStorage.setItem('proalto_advisor_name', name);
            document.getElementById('advisorModal').classList.add('hidden');

            if (window.pendingAdvisorCallback) {
                const cb = window.pendingAdvisorCallback;
                window.pendingAdvisorCallback = null;
                cb();
            }
        }

        function showNewChatModal() {
            document.getElementById('newChatModal').classList.remove('hidden');
        }

        let editEmailCurrentPhone = null;

        function escapeHtmlAttr(str) {
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function openEditEmailModal(phone, currentEmail) {
            editEmailCurrentPhone = phone;
            document.getElementById('editEmailPhone').innerText = phone;
            document.getElementById('editEmailInput').value = currentEmail;
            document.getElementById('editEmailModal').classList.remove('hidden');
        }

        function openEditEmailModalFromRow(btn) {
            const row = btn.closest('tr');
            const phone = row.dataset.phone;
            const email = row.dataset.email;
            if (!phone || !email) {
                alert('Error: no se pudo obtener los datos del registro.');
                return;
            }
            openEditEmailModal(phone, email);
        }

        function closeEditEmailModal() {
            document.getElementById('editEmailModal').classList.add('hidden');
            editEmailCurrentPhone = null;
        }

        async function confirmEditEmail() {
            const newEmail = document.getElementById('editEmailInput').value.trim();
            if (!newEmail) { alert('Ingresa un email válido.'); return; }
            try {
                const res = await fetch(`/admin/api/captured-emails/${editEmailCurrentPhone}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: newEmail })
                });
                const data = await res.json();
                if (res.ok) {
                    closeEditEmailModal();
                    fetchCapturedEmails();
                } else {
                    alert('Error: ' + (data.message || 'No se pudo actualizar.'));
                }
            } catch (e) {
                alert('Error de conexión.');
            }
        }

        function closeNewChatModal() {
            document.getElementById('newChatModal').classList.add('hidden');
            document.getElementById('newChatPhone').value = '';
        }

        async function confirmNewChat() {
            const phoneInput = document.getElementById('newChatPhone').value.trim();
            if (!phoneInput) {
                alert("Por favor ingresa un número de teléfono.");
                return;
            }

            try {
                const res = await fetch('/admin/api/create-chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone: phoneInput })
                });

                if (res.ok) {
                    const data = await res.json();
                    closeNewChatModal();

                    // Switch to active tab if not already on it
                    if (currentTab !== 'activas' && currentTab !== 'prospectos') {
                        switchTab('activas');
                    } else {
                        await fetchList();
                    }

                    // Small delay to ensure the UI updates before selecting
                    setTimeout(() => {
                        selectConversation(data.phone);
                    }, 500);
                } else {
                    const errorData = await res.json();
                    alert(errorData.error || 'Error al iniciar conversación');
                }
            } catch (err) {
                console.error(err);
                alert('Error de conexión');
            }
        }

        // Nav group toggle (click-based dropdowns, position: fixed to escape overflow clipping)
        function toggleNavGroup(btn) {
            const wrapper = btn.closest('.tool-nav-group');
            if (!wrapper) return;
            const dropdown = wrapper.querySelector('.tool-nav-dropdown');
            if (!dropdown) return;
            const isOpen = wrapper.classList.contains('open');
            // Close all other open groups first
            document.querySelectorAll('.tool-nav-group.open').forEach(el => el.classList.remove('open'));
            if (!isOpen) {
                const rect = btn.getBoundingClientRect();
                dropdown.style.top  = rect.bottom + 'px';
                dropdown.style.left = rect.left + 'px';
                wrapper.classList.add('open');
            }
        }

        // Close nav dropdowns when clicking outside
        document.addEventListener('click', function(e) {
            if (!e.target.closest('.tool-nav-group')) {
                document.querySelectorAll('.tool-nav-group.open').forEach(el => el.classList.remove('open'));
            }
        });

        function switchTab(tab) {
            currentTab = tab;
            currentActivePhone = null;
            // Close any open nav group dropdowns
            document.querySelectorAll('.tool-nav-group.open').forEach(el => el.classList.remove('open'));
            document.getElementById('emptyState').style.display = (tab === 'activas' || tab === 'prospectos' || tab === 'renovadoschat' || tab === 'anticiposchat' || tab === 'archivadas') ? 'flex' : 'none';
            if (tab === 'envios' || tab === 'leads' || tab === 'renovados' || tab === 'anticipos' || tab === 'correos' || tab === 'rojo' || tab === 'docrecibidos' || tab === 'llmrequests' || tab === 'docrequests' || tab === 'analytics') {
                document.getElementById('emptyState').style.display = 'none';
            }
            document.getElementById('mainChat').style.display = 'none';
            
            const enviosState = document.getElementById('enviosState');
            if(enviosState) {
                enviosState.style.display = tab === 'envios' ? 'flex' : 'none';
                enviosState.style.flexDirection = 'column';
            }

            const leadsState = document.getElementById('leadsState');
            if(leadsState) {
                leadsState.style.display = tab === 'leads' ? 'flex' : 'none';
                leadsState.style.flexDirection = 'column';
            }

            const renovadosState = document.getElementById('renovadosState');
            if(renovadosState) {
                renovadosState.style.display = tab === 'renovados' ? 'flex' : 'none';
                renovadosState.style.flexDirection = 'column';
            }

            const anticiposState = document.getElementById('anticiposState');
            if(anticiposState) {
                anticiposState.style.display = tab === 'anticipos' ? 'flex' : 'none';
                anticiposState.style.flexDirection = 'column';
            }

            const correosState = document.getElementById('correosState');
            if(correosState) {
                correosState.style.display = tab === 'correos' ? 'flex' : 'none';
                correosState.style.flexDirection = 'column';
            }

            // Update tab styles
            document.getElementById('tabActivas').classList.toggle('active-tab', tab === 'activas');
            document.getElementById('tabProspectos').classList.toggle('active-tab', tab === 'prospectos');
            document.getElementById('tabRenovadosChat').classList.toggle('active-tab', tab === 'renovadoschat');
            document.getElementById('tabAnticiposChat').classList.toggle('active-tab', tab === 'anticiposchat');
            document.getElementById('tabArchivadas').classList.toggle('active-tab', tab === 'archivadas');
            
            // Tool nav button active states (inactive → clear inline styles so CSS takes over)
            const toolColors = {
                tabEnvios:      { active: '#4f46e5', tab: 'envios',       isDropdown: true  },
                tabLeads:       { active: '#059669', tab: 'leads',        isDropdown: false },
                tabRenovados:   { active: '#0284c7', tab: 'renovados',    isDropdown: false },
                tabAnticipos:   { active: '#7c3aed', tab: 'anticipos',    isDropdown: false },
                tabCorreos:     { active: '#3b82f6', tab: 'correos',      isDropdown: true  },
                tabAmarillo:    { active: '#d97706', tab: 'amarillo',     isDropdown: false },
                tabNegados:     { active: '#6b7280', tab: 'negados',      isDropdown: false },
                tabActualizacion:{ active: '#9333ea', tab: 'actualizacion', isDropdown: false },
                tabRojo:        { active: '#dc2626', tab: 'rojo',         isDropdown: true  },
                tabDocRecibidos:{ active: '#b45309', tab: 'docrecibidos', isDropdown: true  },
                tabLLMRequests: { active: '#7c3aed', tab: 'llmrequests',  isDropdown: false },
                tabDocRequests: { active: '#2563eb', tab: 'docrequests',  isDropdown: false },
                tabAnalytics:   { active: '#0891b2', tab: 'analytics',    isDropdown: false },
            };
            for (const [id, cfg] of Object.entries(toolColors)) {
                const el = document.getElementById(id);
                if (!el) continue;
                el.classList.toggle('active-tab', tab === cfg.tab);
                if (tab === cfg.tab) {
                    if (cfg.isDropdown) {
                        el.style.background  = cfg.active + '18';
                        el.style.borderLeft  = `3px solid ${cfg.active}`;
                        el.style.color       = cfg.active;
                        el.style.border      = '';
                    } else {
                        el.style.background  = cfg.active;
                        el.style.border      = `1px solid ${cfg.active}`;
                        el.style.color       = 'white';
                    }
                } else {
                    el.style.background  = '';
                    el.style.border      = '';
                    el.style.borderLeft  = '';
                    el.style.color       = '';
                }
            }

            // Update group button active states
            const grupoComEl = document.getElementById('tabGrupoComunicaciones');
            if (grupoComEl) {
                const comActive = (tab === 'envios' || tab === 'correos');
                const comColor  = '#16a34a'; // verde estado_verde
                grupoComEl.classList.toggle('active-group', comActive);
                grupoComEl.style.color            = comActive ? comColor : '';
                grupoComEl.style.borderBottomColor = comActive ? comColor : '';
                grupoComEl.style.fontWeight        = comActive ? '700' : '';
            }
            const grupoDocEl = document.getElementById('tabGrupoDocumentos');
            if (grupoDocEl) {
                const docActive = (tab === 'rojo' || tab === 'docrecibidos');
                const docColor  = tab === 'rojo' ? '#dc2626' : '#b45309';
                grupoDocEl.classList.toggle('active-group', docActive);
                grupoDocEl.style.color            = docActive ? docColor : '';
                grupoDocEl.style.borderBottomColor = docActive ? docColor : '';
                grupoDocEl.style.fontWeight        = docActive ? '700' : '';
            }

            const amarilloState = document.getElementById('amarilloState');
            if(amarilloState) {
                amarilloState.style.display = tab === 'amarillo' ? 'flex' : 'none';
                amarilloState.style.flexDirection = 'column';
            }

            const negadosState = document.getElementById('negadosState');
            if(negadosState) {
                negadosState.style.display = tab === 'negados' ? 'flex' : 'none';
                negadosState.style.flexDirection = 'column';
            }

            const actualizacionState = document.getElementById('actualizacionState');
            if(actualizacionState) {
                actualizacionState.style.display = tab === 'actualizacion' ? 'flex' : 'none';
                actualizacionState.style.flexDirection = 'column';
            }

            const rojoState = document.getElementById('rojoState');
            if(rojoState) {
                rojoState.style.display = tab === 'rojo' ? 'flex' : 'none';
                rojoState.style.flexDirection = 'column';
            }

            const docRecibidosState = document.getElementById('docRecibidosState');
            if(docRecibidosState) {
                docRecibidosState.style.display = tab === 'docrecibidos' ? 'flex' : 'none';
                docRecibidosState.style.flexDirection = 'column';
            }

            const llmRequestsState = document.getElementById('llmRequestsState');
            if(llmRequestsState) {
                llmRequestsState.style.display = tab === 'llmrequests' ? 'flex' : 'none';
                llmRequestsState.style.flexDirection = 'column';
            }

            const docRequestsState = document.getElementById('docRequestsState');
            if(docRequestsState) {
                docRequestsState.style.display = tab === 'docrequests' ? 'flex' : 'none';
                docRequestsState.style.flexDirection = 'column';
            }

            const analyticsState = document.getElementById('analyticsState');
            if(analyticsState) {
                analyticsState.style.display = tab === 'analytics' ? 'flex' : 'none';
                analyticsState.style.flexDirection = 'column';
            }

            if (tab === 'activas') {
                fetchList();
            } else if (tab === 'prospectos') {
                fetchList();
            } else if (tab === 'renovadoschat') {
                fetchList();
            } else if (tab === 'anticiposchat') {
                fetchList();
            } else if (tab === 'leads') {
                fetchLeadMetrics();
            } else if (tab === 'renovados') {
                fetchRenovadoMetrics();
            } else if (tab === 'anticipos') {
                fetchAnticiposMetrics();
            } else if (tab === 'archivadas') {
                fetchArchivedList();
            } else if (tab === 'envios') {
                fetchPendingEnvios();
            } else if (tab === 'correos') {
                fetchCapturedEmails();
            } else if (tab === 'amarillo') {
                fetchPendingAmarillo();
                fetchCapturedCuentas();
            } else if (tab === 'negados') {
                fetchPendingNegados();
            } else if (tab === 'actualizacion') {
                fetchPendingActualizacion();
            } else if (tab === 'rojo') {
                fetchPendingRojo();
            } else if (tab === 'docrecibidos') {
                fetchReceivedDocuments();
            } else if (tab === 'llmrequests') {
                fetchLLMRequests();
            } else if (tab === 'docrequests') {
                fetchDocumentRequests();
            } else if (tab === 'analytics') {
                initAnalyticsDates();
                fetchAnalytics();
                fetchAuditReports();
            }
        }

        let capturedEmailsData = [];

        function toggleEmailProcessed(checkbox) {
            const row = checkbox.closest('tr');
            const recordId = row.dataset.id;
            if (!recordId) {
                alert('Error: no se pudo obtener el ID del registro.');
                checkbox.checked = !checkbox.checked;
                return;
            }
            checkbox.disabled = true;
            fetch(`/admin/api/captured-emails/by-id/${encodeURIComponent(recordId)}/toggle-processed`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'ok') {
                    // Update local data so re-render reflects DB state without a full reload
                    const item = capturedEmailsData.find(e => String(e.id) === recordId);
                    if (item) item.processed = data.processed;
                    renderEmailsTable(capturedEmailsData);
                } else {
                    alert('Error al guardar el estado. Intenta de nuevo.');
                    checkbox.checked = !checkbox.checked; // revert
                    checkbox.disabled = false;
                }
            })
            .catch(() => {
                alert('Error de conexión. Intenta de nuevo.');
                checkbox.checked = !checkbox.checked; // revert
                checkbox.disabled = false;
            });
        }

        function renderEmailsTable(emails) {
            const tbody = document.getElementById('correosTableBody');
            if (emails.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="padding: 15px; text-align: center; color: #777;">No se han capturado correos aún.</td></tr>';
                document.getElementById('correosCount').innerText = 0;
                return;
            }
            // Sort: pendientes primero, luego por fecha más vieja primero
            const sorted = [...emails].sort((a, b) => {
                const ap = !!a.processed, bp = !!b.processed;
                if (ap !== bp) return ap ? 1 : -1;
                return new Date(a.created_at) - new Date(b.created_at);
            });
            let rows = '';
            sorted.forEach(item => {
                const isDone = !!item.processed;
                const strike = isDone ? 'text-decoration: line-through; color: #9ca3af;' : '';
                const rowBg = isDone ? 'background: #f9fafb;' : '';
                rows += `<tr style="border-bottom: 1px solid #eee; ${rowBg}" data-id="${item.id}" data-phone="${escapeHtmlAttr(item.phone)}" data-email="${escapeHtmlAttr(item.email)}">
                    <td style="padding: 10px; text-align: center;">
                        <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleEmailProcessed(this)" style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary-dark);">
                    </td>
                    <td style="padding: 10px; font-size: 0.85rem; ${strike}">${formatTime(item.created_at)}</td>
                    <td style="padding: 10px; ${strike}">${item.name || '---'}</td>
                    <td style="padding: 10px; ${strike}">${item.phone}</td>
                    <td style="padding: 10px; font-weight: 600; ${isDone ? 'color: #9ca3af;' : 'color: var(--primary-dark);'} ${strike}">${item.email}</td>
                    <td style="padding: 10px;"><button onclick="openEditEmailModalFromRow(this)" style="padding: 4px 10px; font-size: 0.8rem; background: #f0f9ff; border: 1px solid #3b82f6; color: #1d4ed8; border-radius: 4px; cursor: pointer;">Editar</button></td>
                </tr>`;
            });
            tbody.innerHTML = rows;
            document.getElementById('correosCount').innerText = emails.length;
        }

        function copyEmailsToClipboard() {
            if (capturedEmailsData.length === 0) { alert('No hay correos para copiar.'); return; }
            const header = 'Fecha\tNombre\tTeléfono\tEmail';
            const rows = capturedEmailsData.map(item =>
                `${formatTime(item.created_at)}\t${item.name || ''}\t${item.phone}\t${item.email}`
            );
            navigator.clipboard.writeText([header, ...rows].join('\n'))
                .then(() => alert(`✅ ${capturedEmailsData.length} registros copiados. Pega directamente en Excel o Google Sheets.`))
                .catch(() => alert('Error al copiar. Intenta exportar como CSV.'));
        }

        function exportEmailsCSV() {
            if (capturedEmailsData.length === 0) { alert('No hay correos para exportar.'); return; }
            const header = 'Fecha,Nombre,Teléfono,Email';
            const rows = capturedEmailsData.map(item => {
                const fecha = formatTime(item.created_at);
                const nombre = `"${(item.name || '').replace(/"/g, '""')}"`;
                return `${fecha},${nombre},${item.phone},${item.email}`;
            });
            const csv = '\uFEFF' + [header, ...rows].join('\n'); // BOM for Excel UTF-8
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `correos_capturados_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        }

        function copyRojoExcludedToClipboard() {
            if (!pendingExcludedRojoData || pendingExcludedRojoData.length === 0) { alert('No hay excluidos para copiar.'); return; }
            const header = 'Teléfono\tNombre\tEmpresa\tEnvíos\tRazón de exclusión';
            const rows = pendingExcludedRojoData.map(u =>
                `${u.phone}\t${u.name || ''}\t${u.empresa || ''}\t${u.send_count || 0}\t${(u.excluded_reasons || []).join(', ')}`
            );
            navigator.clipboard.writeText([header, ...rows].join('\n'))
                .then(() => alert(`✅ ${pendingExcludedRojoData.length} excluidos copiados. Pega directamente en Excel o Google Sheets.`))
                .catch(() => alert('Error al copiar. Intenta exportar como CSV.'));
        }

        function exportRojoExcludedCSV() {
            if (!pendingExcludedRojoData || pendingExcludedRojoData.length === 0) { alert('No hay excluidos para exportar.'); return; }
            const header = 'Teléfono,Nombre,Empresa,Envíos,Razón de exclusión';
            const rows = pendingExcludedRojoData.map(u => {
                const nombre = `"${(u.name || '').replace(/"/g, '""')}"`;
                const empresa = `"${(u.empresa || '').replace(/"/g, '""')}"`;
                const razones = `"${(u.excluded_reasons || []).join(', ').replace(/"/g, '""')}"`;
                return `${u.phone},${nombre},${empresa},${u.send_count || 0},${razones}`;
            });
            const csv = '\uFEFF' + [header, ...rows].join('\n'); // BOM for Excel UTF-8
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `excluidos_falta_documento_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        }

        async function fetchCapturedEmails() {
            const tbody = document.getElementById('correosTableBody');
            tbody.innerHTML = '<tr><td colspan="6" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando correos...</td></tr>';
            try {
                const res = await fetch('/admin/api/captured-emails');
                const data = await res.json();
                if (res.ok && data.emails) {
                    capturedEmailsData = data.emails;
                    renderEmailsTable(data.emails);
                } else {
                    tbody.innerHTML = `<tr><td colspan="6" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="6" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión.</td></tr>';
            }
        }

        // ── Shared helpers for excluded users sections ────────────────
        function toggleExcludedSection(panel) {
            const content = document.getElementById(`${panel}ExcludedContent`);
            const label = document.getElementById(`${panel}ExcludedToggleLabel`);
            const open = content.style.display !== 'none';
            content.style.display = open ? 'none' : 'block';
            const count = label.textContent.match(/\d+/)?.[0] || '0';
            label.textContent = (open ? '▶' : '▼') + ` Ver excluidos (${count})`;
        }

        function renderExcludedSection(panel, excludedData) {
            const section = document.getElementById(`${panel}ExcludedSection`);
            const body = document.getElementById(`${panel}ExcludedBody`);
            const label = document.getElementById(`${panel}ExcludedToggleLabel`);
            const statLine = document.getElementById(`${panel}StatLine`);

            const eligibleCount = {
                'envios': () => document.querySelectorAll('.envio-check').length,
                'rojo': () => document.querySelectorAll('.rojo-check').length,
                'amarillo': () => document.querySelectorAll('.amarillo-check').length,
                'negados':  () => document.querySelectorAll('.negados-check').length,
                'actualizacion': () => document.querySelectorAll('.actualizacion-check').length
            }[panel]?.() || 0;

            const totalCount = eligibleCount + (excludedData ? excludedData.length : 0);

            if (statLine) {
                if (totalCount > 0) {
                    statLine.innerHTML = `Total en estado: <strong>${totalCount}</strong> &nbsp;·&nbsp; <span style="color:#16a34a;font-weight:600;">${eligibleCount} aplican</span> &nbsp;·&nbsp; <span style="color:#dc2626;font-weight:600;">${excludedData ? excludedData.length : 0} excluidos</span>`;
                } else {
                    statLine.innerHTML = '';
                }
            }

            if (!excludedData || excludedData.length === 0) {
                if (section) section.style.display = 'none';
                return;
            }

            if (section) section.style.display = 'block';
            if (label) label.textContent = `▶ Ver excluidos (${excludedData.length})`;
            if (document.getElementById(`${panel}ExcludedContent`)) {
                document.getElementById(`${panel}ExcludedContent`).style.display = 'none';
            }

            let rows = '';
            excludedData.forEach((user, idx) => {
                const empresaLabel = user.empresa ? `<br><span style="font-size:0.75rem;color:#9ca3af;">${user.empresa}</span>` : '';
                const sendCount = user.send_count || 0;
                const reasons = (user.excluded_reasons || []).map(r =>
                    `<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:#fef2f2;color:#991b1b;font-size:0.75rem;border:1px solid #fecaca;margin-right:4px;">${r}</span>`
                ).join('');
                rows += `<tr style="border-bottom:1px solid #f3f4f6;">
                    <td style="padding:8px 10px;text-align:center;">
                        <input type="checkbox" class="${panel}-excl-check" data-excl-idx="${idx}"
                            title="Incluir en el envío (requiere confirmación)"
                            style="cursor:pointer;accent-color:#dc2626;">
                    </td>
                    <td style="padding:8px 10px;color:#9ca3af;font-size:0.85rem;">${user.phone}</td>
                    <td style="padding:8px 10px;color:#6b7280;font-size:0.85rem;">${user.name}${empresaLabel}</td>
                    <td style="padding:8px 10px;text-align:center;color:#9ca3af;font-size:0.85rem;">${sendCount}</td>
                    <td style="padding:8px 10px;">${reasons}</td>
                </tr>`;
            });
            if (body) body.innerHTML = rows;
        }

        // ── Excluded data storage (for force-send feature) ───────────
        let pendingExcludedEnviosData = [];
        let pendingExcludedRojoData = [];
        let pendingExcludedAmarilloData = [];
        let pendingExcludedNegadosData = [];
        let pendingExcludedActualizacionData = [];
        let _excludedConfirmCallback = null;

        function showExcludedConfirmModal(excludedUsers, callback) {
            _excludedConfirmCallback = callback;
            const tbody = document.getElementById('excludedConfirmTableBody');
            let rows = '';
            excludedUsers.forEach(u => {
                const reasons = (u.excluded_reasons || []).join(', ');
                rows += `<tr style="border-bottom:1px solid #fecaca;">
                    <td style="padding:7px 12px; font-size:0.85rem; color:#374151;">${u.name}<br><span style="color:#9ca3af;font-size:0.78rem;">${u.phone}</span></td>
                    <td style="padding:7px 12px; font-size:0.82rem; color:#991b1b;">${reasons}</td>
                </tr>`;
            });
            tbody.innerHTML = rows;
            const modal = document.getElementById('excludedConfirmModal');
            modal.style.display = 'flex';
        }

        function closeExcludedConfirmModal() {
            document.getElementById('excludedConfirmModal').style.display = 'none';
            _excludedConfirmCallback = null;
        }

        function confirmExcludedSend() {
            document.getElementById('excludedConfirmModal').style.display = 'none';
            if (_excludedConfirmCallback) {
                const cb = _excludedConfirmCallback;
                _excludedConfirmCallback = null;
                cb();
            }
        }

        // ── Estado Rojo: Falta Documento ──────────────────────────────
        let pendingRojoData = [];

        async function fetchPendingRojo(hideResults = true) {
            const tbody = document.getElementById('rojoTableBody');
            const btn = document.getElementById('btnExecuteRojo');
            if (hideResults) {
                document.getElementById('rojoResults').style.display = 'none';
            }
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando clientes elegibles...</td></tr>';
            btn.disabled = true;
            pendingRojoData = [];
            pendingExcludedRojoData = [];
            document.getElementById('rojoExcludedSection').style.display = 'none';
            document.getElementById('rojoStatLine').innerHTML = '';

            try {
                const res = await fetch('/admin/api/pending-falta-documento');
                const data = await res.json();

                if (res.ok && data.pending) {
                    pendingRojoData = data.pending;

                    if (pendingRojoData.length === 0) {
                        document.getElementById('rojoCount').innerText = '0';
                        tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--success); font-weight: bold;">✅ No hay clientes pendientes por notificar hoy.</td></tr>';
                    } else {
                        let rows = '';
                        pendingRojoData.forEach((user, idx) => {
                            const lastSent = user.last_sent
                                ? new Date(user.last_sent).toLocaleString('es-CO', {timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'})
                                : 'Nunca';
                            const sendCount = user.send_count || 0;
                            const countColor = sendCount >= 3 ? 'color:#dc2626;font-weight:bold;' : sendCount >= 1 ? 'color:#d97706;' : '';
                            const empresaLabel = user.empresa ? `<br><span style="font-size:0.75rem;color:#6b7280;">${user.empresa}</span>` : '';
                            const fincaBadge = (user.tipo_empleador || '').toUpperCase() === 'FINCA'
                                ? '<span style="margin-left:6px;padding:1px 6px;border-radius:10px;background:#d1fae5;color:#065f46;font-size:0.7rem;font-weight:600;">FINCA</span>'
                                : '';
                            rows += `<tr style="border-bottom: 1px solid #eee;" data-empresa="${(user.empresa||'').toLowerCase()}">
                                <td style="padding: 10px; text-align: center;"><input type="checkbox" class="rojo-check" data-idx="${idx}" checked onchange="updateSelectedCountRojo()"></td>
                                <td style="padding: 10px;">${user.phone}</td>
                                <td style="padding: 10px;">${user.name}${fincaBadge}${empresaLabel}</td>
                                <td style="padding: 10px; text-align: center; ${countColor}">${sendCount}</td>
                                <td style="padding: 10px; font-size: 0.85rem; color: var(--text-muted);">${lastSent}</td>
                            </tr>`;
                        });
                        tbody.innerHTML = rows;
                        populatePanelEmpresaFilter(pendingRojoData, 'rojoEmpresaDrop');
                        updateSelectedCountRojo();
                    }
                    pendingExcludedRojoData = data.excluded || [];
                    renderExcludedSection('rojo', pendingExcludedRojoData);
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión al cargar.</td></tr>';
            }
        }

        function selectOnlyNewClientsRojo() {
            document.querySelectorAll('.rojo-check').forEach(cb => {
                const idx = parseInt(cb.dataset.idx);
                cb.checked = pendingRojoData[idx].send_count === 0;
            });
            updateSelectedCountRojo();
        }

        function toggleAllChecksRojo(masterCb) {
            document.querySelectorAll('.rojo-check').forEach(cb => cb.checked = masterCb.checked);
            updateSelectedCountRojo();
        }

        function updateSelectedCountRojo() {
            const total = document.querySelectorAll('.rojo-check').length;
            const selected = document.querySelectorAll('.rojo-check:checked').length;
            const exclSelected = document.querySelectorAll('.rojo-excl-check:checked').length;
            document.getElementById('rojoCount').innerText = `${selected} / ${total}`;
            document.getElementById('btnExecuteRojo').disabled = (selected + exclSelected) === 0;
            const masterCb = document.getElementById('checkAllRojo');
            if (masterCb) {
                masterCb.indeterminate = selected > 0 && selected < total;
                masterCb.checked = total > 0 && selected === total;
            }
        }

        async function executeBulkRojo() {
            const checked = document.querySelectorAll('.rojo-check:checked');
            const selectedEligible = Array.from(checked).map(cb => pendingRojoData[parseInt(cb.dataset.idx)]);
            const exclChecked = document.querySelectorAll('.rojo-excl-check:checked');
            const selectedExcluded = Array.from(exclChecked).map(cb => pendingExcludedRojoData[parseInt(cb.dataset.exclIdx)]);

            if (selectedEligible.length === 0 && selectedExcluded.length === 0) return;

            const doSend = () => _doExecuteBulkRojo([...selectedEligible, ...selectedExcluded]);

            if (selectedExcluded.length > 0) {
                showExcludedConfirmModal(selectedExcluded, doSend);
                return;
            }
            if (!confirm(`¿Estás seguro de enviar el template "estado_rojo" a ${selectedEligible.length} clientes seleccionados?`)) return;
            doSend();
        }

        async function _doExecuteBulkRojo(selectedUsers) {
            const btn = document.getElementById('btnExecuteRojo');
            btn.disabled = true;
            btn.innerText = '⌛ Procesando...';

            let totalSuccess = 0, totalFailed = 0, allErrors = [];
            const batchSize = 15;
            const totalUsers = selectedUsers.length;

            document.getElementById('rojoResults').style.display = 'block';

            for (let i = 0; i < totalUsers; i += batchSize) {
                const chunk = selectedUsers.slice(i, i + batchSize);
                btn.innerText = `⌛ Enviando ${i + 1} - ${Math.min(i + batchSize, totalUsers)} de ${totalUsers}...`;

                try {
                    const res = await fetch('/admin/api/trigger-bulk-rojo', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });
                    const data = await res.json();

                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFailed += data.results.fail || 0;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);

                        document.getElementById('rojoSuccessCount').innerText = totalSuccess;
                        document.getElementById('rojoFailCount').innerText = totalFailed;

                        const errorList = document.getElementById('rojoErrorList');
                        errorList.innerHTML = allErrors.length > 0
                            ? allErrors.map(err => `<li>${err}</li>`).join('')
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

            btn.innerText = '🔴 Ejecutar Envío a Seleccionados';
            btn.disabled = false;
            await fetchPendingRojo(false);
            alert(`Proceso finalizado.\nÉxitos: ${totalSuccess}\nFallos: ${totalFailed}`);
        }

        // ── Estado Amarillo: Listo en DocuSign ───────────────────────
        let pendingAmarilloData = [];
        let capturedCuentasData = [];

        async function fetchPendingAmarillo(hideResults = true) {
            const tbody = document.getElementById('amarilloTableBody');
            const btn = document.getElementById('btnExecuteAmarillo');
            if (hideResults) {
                document.getElementById('amarilloResults').style.display = 'none';
            }
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando clientes elegibles...</td></tr>';
            btn.disabled = true;
            pendingAmarilloData = [];
            pendingExcludedAmarilloData = [];
            document.getElementById('amarilloExcludedSection').style.display = 'none';
            document.getElementById('amarilloStatLine').innerHTML = '';

            try {
                const res = await fetch('/admin/api/pending-listo-docusign');
                const data = await res.json();

                if (res.ok && data.pending) {
                    pendingAmarilloData = data.pending;

                    if (pendingAmarilloData.length === 0) {
                        document.getElementById('amarilloCount').innerText = '0';
                        tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--success); font-weight: bold;">✅ No hay clientes pendientes por notificar hoy.</td></tr>';
                    } else {
                        let rows = '';
                        pendingAmarilloData.forEach((user, idx) => {
                            const lastSent = user.last_sent
                                ? new Date(user.last_sent).toLocaleString('es-CO', {timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'})
                                : 'Nunca';
                            const sendCount = user.send_count || 0;
                            const countColor = sendCount >= 3 ? 'color:#dc2626;font-weight:bold;' : sendCount >= 1 ? 'color:#d97706;' : '';
                            const empresaLabel = user.empresa ? `<br><span style="font-size:0.75rem;color:#6b7280;">${user.empresa}</span>` : '';
                            rows += `<tr style="border-bottom: 1px solid #eee;" data-empresa="${(user.empresa||'').toLowerCase()}">
                                <td style="padding: 10px; text-align: center;"><input type="checkbox" class="amarillo-check" data-idx="${idx}" checked onchange="updateSelectedCountAmarillo()"></td>
                                <td style="padding: 10px;">${user.phone}</td>
                                <td style="padding: 10px;">${user.name}${empresaLabel}</td>
                                <td style="padding: 10px; text-align: center; ${countColor}">${sendCount}</td>
                                <td style="padding: 10px; font-size: 0.85rem; color: var(--text-muted);">${lastSent}</td>
                            </tr>`;
                        });
                        tbody.innerHTML = rows;
                        populatePanelEmpresaFilter(pendingAmarilloData, 'amarilloEmpresaDrop');
                        updateSelectedCountAmarillo();
                    }
                    pendingExcludedAmarilloData = data.excluded || [];
                    renderExcludedSection('amarillo', pendingExcludedAmarilloData);
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión al cargar.</td></tr>';
            }
        }

        function selectOnlyNewClientsAmarillo() {
            document.querySelectorAll('.amarillo-check').forEach(cb => {
                const idx = parseInt(cb.dataset.idx);
                cb.checked = pendingAmarilloData[idx].send_count === 0;
            });
            updateSelectedCountAmarillo();
        }

        function toggleAllChecksAmarillo(masterCb) {
            document.querySelectorAll('.amarillo-check').forEach(cb => cb.checked = masterCb.checked);
            updateSelectedCountAmarillo();
        }

        function updateSelectedCountAmarillo() {
            const total = document.querySelectorAll('.amarillo-check').length;
            const selected = document.querySelectorAll('.amarillo-check:checked').length;
            const exclSelected = document.querySelectorAll('.amarillo-excl-check:checked').length;
            document.getElementById('amarilloCount').innerText = `${selected} / ${total}`;
            document.getElementById('btnExecuteAmarillo').disabled = (selected + exclSelected) === 0;
            const masterCb = document.getElementById('checkAllAmarillo');
            if (masterCb) {
                masterCb.indeterminate = selected > 0 && selected < total;
                masterCb.checked = total > 0 && selected === total;
            }
        }

        async function executeBulkAmarillo() {
            const checked = document.querySelectorAll('.amarillo-check:checked');
            const selectedEligible = Array.from(checked).map(cb => pendingAmarilloData[parseInt(cb.dataset.idx)]);
            const exclChecked = document.querySelectorAll('.amarillo-excl-check:checked');
            const selectedExcluded = Array.from(exclChecked).map(cb => pendingExcludedAmarilloData[parseInt(cb.dataset.exclIdx)]);

            if (selectedEligible.length === 0 && selectedExcluded.length === 0) return;

            const doSend = () => _doExecuteBulkAmarillo([...selectedEligible, ...selectedExcluded]);

            if (selectedExcluded.length > 0) {
                showExcludedConfirmModal(selectedExcluded, doSend);
                return;
            }
            if (!confirm(`¿Estás seguro de enviar el template "estado_amarillo" a ${selectedEligible.length} clientes seleccionados?`)) return;
            doSend();
        }

        async function _doExecuteBulkAmarillo(selectedUsers) {
            const btn = document.getElementById('btnExecuteAmarillo');
            btn.disabled = true;
            btn.innerText = '⌛ Procesando...';

            let totalSuccess = 0, totalFailed = 0, allErrors = [];
            const batchSize = 15;
            const totalUsers = selectedUsers.length;

            document.getElementById('amarilloResults').style.display = 'block';

            for (let i = 0; i < totalUsers; i += batchSize) {
                const chunk = selectedUsers.slice(i, i + batchSize);
                btn.innerText = `⌛ Enviando ${i + 1} - ${Math.min(i + batchSize, totalUsers)} de ${totalUsers}...`;

                try {
                    const res = await fetch('/admin/api/trigger-bulk-amarillo', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });
                    const data = await res.json();

                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFailed += data.results.fail || 0;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);

                        document.getElementById('amarilloSuccessCount').innerText = totalSuccess;
                        document.getElementById('amarilloFailCount').innerText = totalFailed;

                        const errorList = document.getElementById('amarilloErrorList');
                        errorList.innerHTML = allErrors.length > 0
                            ? allErrors.map(err => `<li>${err}</li>`).join('')
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

            btn.innerText = '🟡 Ejecutar Envío a Seleccionados';
            btn.disabled = false;
            await fetchPendingAmarillo(false);
            alert(`Proceso finalizado.\nÉxitos: ${totalSuccess}\nFallos: ${totalFailed}`);
        }

        // ── Estado Negados: Créditos Denegados / Cancelados ───────────────────────
        let pendingNegadosData = [];

        async function fetchPendingNegados(hideResults = true) {
            const tbody = document.getElementById('negadosTableBody');
            const btn = document.getElementById('btnExecuteNegados');
            if (hideResults) {
                document.getElementById('negadosResults').style.display = 'none';
            }
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando clientes elegibles...</td></tr>';
            if (btn) btn.disabled = true;
            pendingNegadosData = [];
            pendingExcludedNegadosData = [];
            document.getElementById('negadosExcludedSection').style.display = 'none';
            document.getElementById('negadosStatLine').innerHTML = '';

            try {
                const res = await fetch('/admin/api/pending-denegado');
                const data = await res.json();

                if (res.ok && data.pending) {
                    pendingNegadosData = data.pending;

                    if (pendingNegadosData.length === 0) {
                        document.getElementById('negadosCount').innerText = '0';
                        tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--success); font-weight: bold;">✅ No hay clientes pendientes por notificar.</td></tr>';
                    } else {
                        let rows = '';
                        pendingNegadosData.forEach((user, idx) => {
                            const lastSent = user.last_sent
                                ? new Date(user.last_sent).toLocaleDateString('es-CO')
                                : '—';
                            const fechaSolicitud = user.fecha_solicitud || '—';
                            const empresaLabel = user.empresa ? `<br><span style="font-size:0.75rem;color:#6b7280;">${user.empresa}</span>` : '';
                            rows += `<tr style="border-bottom: 1px solid #eee;" data-empresa="${(user.empresa||'').toLowerCase()}">
                                <td style="padding: 10px; text-align: center;"><input type="checkbox" class="negados-check" data-idx="${idx}" checked onchange="updateSelectedCountNegados()"></td>
                                <td style="padding: 10px;">${user.phone}</td>
                                <td style="padding: 10px;">${user.name}${empresaLabel}</td>
                                <td style="padding: 10px; white-space: nowrap;">${fechaSolicitud}</td>
                                <td style="padding: 10px; text-align: center;">${user.send_count}</td>
                                <td style="padding: 10px;">${lastSent}</td>
                            </tr>`;
                        });
                        tbody.innerHTML = rows;
                        populatePanelEmpresaFilter(pendingNegadosData, 'negadosEmpresaDrop');
                        updateSelectedCountNegados();
                    }
                    pendingExcludedNegadosData = data.excluded || [];
                    renderExcludedSection('negados', pendingExcludedNegadosData);
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión</td></tr>';
            }
        }

        function toggleAllChecksNegados(masterCb) {
            document.querySelectorAll('.negados-check').forEach(cb => cb.checked = masterCb.checked);
            updateSelectedCountNegados();
        }

        function updateSelectedCountNegados() {
            const total = document.querySelectorAll('.negados-check').length;
            const selected = document.querySelectorAll('.negados-check:checked').length;
            const exclSelected = document.querySelectorAll('.negados-excl-check:checked').length;
            document.getElementById('negadosCount').innerText = `${selected} / ${total}`;
            document.getElementById('btnExecuteNegados').disabled = (selected + exclSelected) === 0;
            const masterCb = document.getElementById('checkAllNegados');
            if (masterCb) masterCb.indeterminate = selected > 0 && selected < total;
        }

        async function executeBulkNegados() {
            const checked = document.querySelectorAll('.negados-check:checked');
            const selectedEligible = Array.from(checked).map(cb => pendingNegadosData[parseInt(cb.dataset.idx)]);
            const exclChecked = document.querySelectorAll('.negados-excl-check:checked');
            const selectedExcluded = Array.from(exclChecked).map(cb => pendingExcludedNegadosData[parseInt(cb.dataset.exclIdx)]);
            const selectedUsers = [...selectedEligible, ...selectedExcluded];

            if (selectedUsers.length === 0) {
                alert('No hay clientes seleccionados.');
                return;
            }
            if (!confirm(`¿Estás seguro de enviar el template "estado_negados" a ${selectedUsers.length} cliente(s) seleccionado(s)?\n\nRecuerda: cada cliente solo debería recibir esta notificación una vez.`)) return;

            const btn = document.getElementById('btnExecuteNegados');
            btn.innerText = '⏳ Enviando...';
            btn.disabled = true;

            const batchSize = 20;
            let totalSuccess = 0, totalFailed = 0, allErrors = [];

            document.getElementById('negadosResults').style.display = 'block';

            for (let i = 0; i < selectedUsers.length; i += batchSize) {
                const chunk = selectedUsers.slice(i, i + batchSize);
                try {
                    const res = await fetch('/admin/api/trigger-bulk-denegado', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });
                    const data = await res.json();
                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFailed += data.results.fail;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);

                        document.getElementById('negadosSuccessCount').innerText = totalSuccess;
                        document.getElementById('negadosFailCount').innerText = totalFailed;

                        const errorList = document.getElementById('negadosErrorList');
                        errorList.innerHTML = allErrors.length > 0
                            ? allErrors.map(err => `<li>${err}</li>`).join('')
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

            btn.innerText = '🚫 Enviar a Seleccionados';
            btn.disabled = false;
            await fetchPendingNegados(false);
            alert(`Proceso finalizado.\nÉxitos: ${totalSuccess}\nFallos: ${totalFailed}`);
        }

        // ── Actualización Anual de Datos de Contacto ──────────────────────────────
        let pendingActualizacionData = [];

        async function fetchPendingActualizacion(hideResults = true) {
            const tbody = document.getElementById('actualizacionTableBody');
            const btn = document.getElementById('btnExecuteActualizacion');
            if (hideResults) {
                document.getElementById('actualizacionResults').style.display = 'none';
            }
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando clientes activos sin actualizar...</td></tr>';
            if (btn) btn.disabled = true;
            pendingActualizacionData = [];
            pendingExcludedActualizacionData = [];
            document.getElementById('actualizacionExcludedSection').style.display = 'none';
            document.getElementById('actualizacionStatLine').innerHTML = '';

            try {
                const res = await fetch('/admin/api/pending-actualizacion-datos');
                const data = await res.json();

                if (res.ok && data.pending) {
                    pendingActualizacionData = data.pending;

                    if (pendingActualizacionData.length === 0) {
                        document.getElementById('actualizacionCount').innerText = '0';
                        tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--success); font-weight: bold;">✅ No hay clientes pendientes por notificar.</td></tr>';
                    } else {
                        let rows = '';
                        pendingActualizacionData.forEach((user, idx) => {
                            const lastSent = user.last_sent
                                ? new Date(user.last_sent).toLocaleDateString('es-CO')
                                : '—';
                            rows += `<tr style="border-bottom: 1px solid #eee;">
                                <td style="padding: 10px; text-align: center;"><input type="checkbox" class="actualizacion-check" data-idx="${idx}" checked onchange="updateSelectedCountActualizacion()"></td>
                                <td style="padding: 10px;">${user.phone}</td>
                                <td style="padding: 10px;">${user.name}</td>
                                <td style="padding: 10px; text-align: center;">${user.send_count}</td>
                                <td style="padding: 10px;">${lastSent}</td>
                            </tr>`;
                        });
                        tbody.innerHTML = rows;
                        updateSelectedCountActualizacion();
                    }
                    pendingExcludedActualizacionData = data.excluded || [];
                    renderExcludedSection('actualizacion', pendingExcludedActualizacionData);
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión</td></tr>';
            }
        }

        function filterActualizacionTable() {
            const q = (document.getElementById('actualizacionSearch').value || '').trim().toLowerCase();
            document.querySelectorAll('#actualizacionTableBody tr').forEach(tr => {
                const text = tr.innerText.toLowerCase();
                tr.style.display = !q || text.includes(q) ? '' : 'none';
            });
        }

        function toggleAllChecksActualizacion(masterCb) {
            document.querySelectorAll('.actualizacion-check').forEach(cb => {
                // respeta filtro de búsqueda: solo afecta filas visibles
                const row = cb.closest('tr');
                if (!row || row.style.display !== 'none') cb.checked = masterCb.checked;
            });
            updateSelectedCountActualizacion();
        }

        function updateSelectedCountActualizacion() {
            const total = document.querySelectorAll('.actualizacion-check').length;
            const selected = document.querySelectorAll('.actualizacion-check:checked').length;
            const exclSelected = document.querySelectorAll('.actualizacion-excl-check:checked').length;
            document.getElementById('actualizacionCount').innerText = `${selected} / ${total}`;
            document.getElementById('btnExecuteActualizacion').disabled = (selected + exclSelected) === 0;
            const masterCb = document.getElementById('checkAllActualizacion');
            if (masterCb) masterCb.indeterminate = selected > 0 && selected < total;
        }

        async function executeBulkActualizacion() {
            const checked = document.querySelectorAll('.actualizacion-check:checked');
            const selectedEligible = Array.from(checked).map(cb => pendingActualizacionData[parseInt(cb.dataset.idx)]);
            const exclChecked = document.querySelectorAll('.actualizacion-excl-check:checked');
            const selectedExcluded = Array.from(exclChecked).map(cb => pendingExcludedActualizacionData[parseInt(cb.dataset.exclIdx)]);
            const selectedUsers = [...selectedEligible, ...selectedExcluded];

            if (selectedUsers.length === 0) {
                alert('No hay clientes seleccionados.');
                return;
            }
            if (!confirm(`¿Enviar el template "actualizacion_datos" a ${selectedUsers.length} cliente(s)?\n\nEl cliente verá el bloque legal con la cita contractual y dos botones (Actualizar ahora / Más tarde).`)) return;

            const btn = document.getElementById('btnExecuteActualizacion');
            btn.innerText = '⏳ Enviando...';
            btn.disabled = true;

            const batchSize = 20;
            let totalSuccess = 0, totalFailed = 0, allErrors = [];

            document.getElementById('actualizacionResults').style.display = 'block';

            for (let i = 0; i < selectedUsers.length; i += batchSize) {
                const chunk = selectedUsers.slice(i, i + batchSize);
                try {
                    const res = await fetch('/admin/api/trigger-bulk-actualizacion-datos', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });
                    const data = await res.json();
                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFailed += data.results.fail;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);

                        document.getElementById('actualizacionSuccessCount').innerText = totalSuccess;
                        document.getElementById('actualizacionFailCount').innerText = totalFailed;

                        const errorList = document.getElementById('actualizacionErrorList');
                        errorList.innerHTML = allErrors.length > 0
                            ? allErrors.map(err => `<li>${err}</li>`).join('')
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

            btn.innerText = '📝 Enviar a Seleccionados';
            btn.disabled = false;
            await fetchPendingActualizacion(false);
            alert(`Proceso finalizado.\nÉxitos: ${totalSuccess}\nFallos: ${totalFailed}`);
        }

        async function fetchCapturedCuentas() {
            const tbody = document.getElementById('cuentasTableBody');
            tbody.innerHTML = '<tr><td colspan="7" style="padding: 15px; text-align: center; color: var(--text-muted);">Cargando...</td></tr>';

            try {
                const res = await fetch('/admin/api/captured-cuentas');
                const data = await res.json();

                if (res.ok && data.cuentas) {
                    capturedCuentasData = data.cuentas;
                    document.getElementById('cuentasCount').innerText = `(${capturedCuentasData.length})`;

                    if (capturedCuentasData.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="7" style="padding: 15px; text-align: center; color: var(--text-muted);">Aún no se han recibido números de cuenta.</td></tr>';
                    } else {
                        tbody.innerHTML = capturedCuentasData.map(item => {
                            let titularCell;
                            if (item.es_tercero) {
                                const cedLink = item.cedula_tercero_url
                                    ? ` <a href="${item.cedula_tercero_url}" target="_blank" style="font-size:0.8rem; color:#d97706;">Ver cédula</a>`
                                    : '';
                                titularCell = `<span style="background:#fef3c7; color:#92400e; padding:2px 6px; border-radius:4px; font-size:0.8rem; font-weight:bold;">Tercero</span><br><span style="font-size:0.85rem;">${item.nombre_tercero || ''}${cedLink}</span>`;
                            } else {
                                titularCell = '<span style="color:#6b7280; font-size:0.85rem;">Propia</span>';
                            }
                            return `
                            <tr style="border-bottom: 1px solid #eee;">
                                <td style="padding: 10px; font-size: 0.85rem; color: var(--text-muted);">${formatTime(item.created_at)}</td>
                                <td style="padding: 10px;">${item.name || ''}</td>
                                <td style="padding: 10px;">${item.phone}</td>
                                <td style="padding: 10px; font-size: 0.85rem; color: var(--text-muted);">${item.empresa || '<span style="color:#aaa;">—</span>'}</td>
                                <td style="padding: 10px;">${titularCell}</td>
                                <td style="padding: 10px; font-weight: bold;">${item.numero_cuenta || '<span style="color:#aaa;">Pendiente</span>'}</td>
                                <td style="padding: 10px;">${item.banco || '<span style="color:#aaa;">Pendiente</span>'}</td>
                            </tr>`;
                        }).join('');
                    }
                } else {
                    tbody.innerHTML = `<tr><td colspan="7" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="7" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión.</td></tr>';
            }
        }

        function copyCuentasToClipboard() {
            if (capturedCuentasData.length === 0) { alert('No hay cuentas para copiar.'); return; }
            const header = 'Fecha\tNombre\tTeléfono\tEmpresa\tTitular\tNúmero de Cuenta\tBanco';
            const rows = capturedCuentasData.map(item => {
                const titular = item.es_tercero ? `Tercero: ${item.nombre_tercero || ''}` : 'Propia';
                return `${formatTime(item.created_at)}\t${item.name || ''}\t${item.phone}\t${item.empresa || ''}\t${titular}\t${item.numero_cuenta || ''}\t${item.banco || ''}`;
            });
            navigator.clipboard.writeText([header, ...rows].join('\n'))
                .then(() => alert(`✅ ${capturedCuentasData.length} registros copiados. Pega directamente en Excel o Google Sheets.`))
                .catch(() => alert('Error al copiar. Intenta exportar como CSV.'));
        }

        function exportCuentasCSV() {
            if (capturedCuentasData.length === 0) { alert('No hay cuentas para exportar.'); return; }
            const header = 'Fecha,Nombre,Teléfono,Empresa,Titular,Número de Cuenta,Banco,Cédula Titular';
            const rows = capturedCuentasData.map(item => {
                const fecha = formatTime(item.created_at);
                const nombre = (item.name || '').replace(/,/g, ' ');
                const empresa = (item.empresa || '').replace(/,/g, ' ');
                const titular = item.es_tercero ? `Tercero: ${(item.nombre_tercero || '').replace(/,/g, ' ')}` : 'Propia';
                const numero = (item.numero_cuenta || '').replace(/,/g, ' ');
                const banco = (item.banco || '').replace(/,/g, ' ');
                const cedula = item.cedula_tercero_url || '';
                return `${fecha},${nombre},${item.phone},${empresa},${titular},${numero},${banco},${cedula}`;
            });
            const csv = [header, ...rows].join('\n');
            const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `cuentas_docusign_${new Date().toISOString().slice(0,10)}.csv`;
            a.click();
            URL.revokeObjectURL(url);
        }

        // ── Documentos Recibidos ──────────────────────────────────────
        async function fetchReceivedDocuments() {
            const tbody = document.getElementById('docsTableBody');
            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando documentos...</td></tr>';

            try {
                const res = await fetch('/admin/api/received-documents');
                const data = await res.json();

                if (res.ok && data.documents !== undefined) {
                    const docs = data.documents;
                    document.getElementById('docsCount').innerText = docs.length;

                    const pendientes = docs.filter(d => !d.reviewed).length;
                    document.getElementById('docsPendientesCount').innerText = pendientes;

                    const badge = document.getElementById('badgeDocsPendientes');
                    if (pendientes > 0) {
                        badge.style.display = 'inline';
                        badge.innerText = pendientes;
                    } else {
                        badge.style.display = 'none';
                    }

                    if (docs.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: #777;">No se han recibido documentos aún.</td></tr>';
                        return;
                    }

                    // Group docs by phone
                    const groups = {};
                    docs.forEach(doc => {
                        if (!groups[doc.phone]) groups[doc.phone] = { info: doc, docs: [] };
                        groups[doc.phone].docs.push(doc);
                    });

                    let rows = '';
                    const sortedGroups = Object.values(groups).sort((a, b) => {
                        const aCompleto = a.info.docs_completos ? 1 : 0;
                        const bCompleto = b.info.docs_completos ? 1 : 0;
                        return aCompleto - bCompleto;
                    });
                    sortedGroups.forEach(group => {
                        const { info, docs: clientDocs } = group;
                        const docsCompletos = info.docs_completos;
                        const completosBadge = docsCompletos
                            ? `<span style="background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;">✓ Docs completos</span>
                               <button onclick="unmarkDocsCompletos('${info.phone}', this)" style="background:transparent;color:#9ca3af;border:1px solid #d1d5db;padding:3px 8px;border-radius:4px;cursor:pointer;font-size:0.75rem;margin-left:6px;" title="Desmarcar">✕ Desmarcar</button>`
                            : `<button onclick="markDocsCompletos('${info.phone}', this)" style="background:#7c3aed;color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem;">☑ Marcar docs completos</button>`;

                        const allReviewed = clientDocs.every(d => d.reviewed);
                        const revisarTodosBtn = allReviewed
                            ? '<span style="color:#9ca3af;font-size:0.8rem;margin-right:10px;">✓ Todos revisados</span>'
                            : `<button onclick="markAllDocsReviewed('${info.phone}', this)" style="background:#0891b2;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.8rem;margin-right:10px;">Revisar todos</button>`;

                        // Client header row
                        const empresaLabel = info.empresa
                            ? `&nbsp;&nbsp;<span style="font-size:0.78rem;color:#6b7280;font-weight:400;">🏢 ${info.empresa}</span>`
                            : '';
                        rows += `<tr style="background:#fef3c7; border-top: 2px solid #b45309;" data-empresa="${(info.empresa || '').toLowerCase()}">
                            <td colspan="3" style="padding: 10px 12px; font-weight: 600;">
                                👤 ${info.client_name || '---'} &nbsp;·&nbsp; <span style="color:#666;font-weight:400;">${info.phone}</span>
                                &nbsp;&nbsp; <span style="background:#e5e7eb;color:#374151;padding:2px 8px;border-radius:999px;font-size:0.8rem;">${clientDocs.length} archivo${clientDocs.length > 1 ? 's' : ''}</span>${empresaLabel}
                            </td>
                            <td colspan="2" style="padding: 10px 12px; text-align: right;">${revisarTodosBtn}${completosBadge}</td>
                        </tr>`;

                        // Individual doc rows
                        clientDocs.forEach(doc => {
                            const fecha = doc.received_at
                                ? new Date(doc.received_at).toLocaleString('es-CO', {timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'})
                                : '---';
                            const tipoLabel = doc.mime_type
                                ? (doc.mime_type.startsWith('image') ? '🖼️ Imagen' : '📄 Documento')
                                : '📎 Archivo';
                            const estadoBadge = doc.reviewed
                                ? '<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:999px;font-size:0.8rem;">Revisado</span>'
                                : '<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:999px;font-size:0.8rem;">Pendiente</span>';
                            const accionBtn = doc.reviewed
                                ? '<span style="color:#9ca3af;font-size:0.8rem;">—</span>'
                                : `<button onclick="markDocReviewed('${doc.id}', this)" style="background:#10b981;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.8rem;">Marcar revisado</button>`;
                            const downloadUrl = doc.storage_url
                                ? `/admin/api/download-doc?url=${encodeURIComponent(doc.storage_url)}&filename=${encodeURIComponent(doc.filename || 'archivo')}`
                                : null;
                            const archivoLink = doc.storage_url
                                ? `<a href="${doc.storage_url}" target="_blank" style="color:var(--primary-dark);text-decoration:underline;font-size:0.85rem;">${doc.filename || 'Ver archivo'}</a>
                                   <a href="${downloadUrl}" download style="margin-left:8px;background:#e0e7ff;color:#3730a3;border:none;padding:3px 8px;border-radius:4px;cursor:pointer;font-size:0.78rem;text-decoration:none;display:inline-block;" title="Descargar">⬇ Descargar</a>`
                                : (doc.filename || '---');

                            rows += `<tr style="border-bottom: 1px solid #eee; ${doc.reviewed ? 'opacity:0.6;' : ''}">
                                <td style="padding: 8px 10px 8px 24px; font-size: 0.85rem; color:#666;">${fecha}</td>
                                <td style="padding: 8px 10px;">${archivoLink}</td>
                                <td style="padding: 8px 10px;">${tipoLabel}</td>
                                <td style="padding: 8px 10px; text-align: center;">${estadoBadge}</td>
                                <td style="padding: 8px 10px; text-align: center;">${accionBtn}</td>
                            </tr>`;
                        });
                    });
                    tbody.innerHTML = rows;

                    // Populate empresa multi-select dropdown
                    populatePanelEmpresaFilter(docs, 'docsEmpresaDrop');
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión.</td></tr>';
            }
        }

        async function markDocReviewed(docId, btn) {
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch('/admin/api/mark-document-reviewed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: docId })
                });
                if (res.ok) {
                    await fetchReceivedDocuments();
                } else {
                    alert('Error al marcar como revisado.');
                    btn.disabled = false;
                    btn.innerText = 'Marcar revisado';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = 'Marcar revisado';
            }
        }

        async function markAllDocsReviewed(phone, btn) {
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch('/admin/api/mark-all-docs-reviewed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone })
                });
                if (res.ok) {
                    await fetchReceivedDocuments();
                } else {
                    alert('Error al marcar todos como revisados.');
                    btn.disabled = false;
                    btn.innerText = 'Revisar todos';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = 'Revisar todos';
            }
        }

        async function markDocsCompletos(phone, btn) {
            if (!confirm(`¿Confirmas que ${phone} ya envió todos los documentos requeridos? No recibirá más notificaciones de documentos faltantes.`)) return;
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch('/admin/api/mark-docs-completos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone, value: true })
                });
                if (res.ok) {
                    btn.outerHTML = `<span style="background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;">✓ Docs completos</span>
                                    <button onclick="unmarkDocsCompletos('${phone}', this)" style="background:transparent;color:#9ca3af;border:1px solid #d1d5db;padding:3px 8px;border-radius:4px;cursor:pointer;font-size:0.75rem;margin-left:6px;" title="Desmarcar">✕ Desmarcar</button>`;
                } else {
                    alert('Error al marcar docs completos.');
                    btn.disabled = false;
                    btn.innerText = '☑ Marcar docs completos';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = '☑ Marcar docs completos';
            }
        }

        async function unmarkDocsCompletos(phone, btn) {
            if (!confirm(`¿Desmarcar a ${phone}? Volverá a aparecer como pendiente de docs completos.`)) return;
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch('/admin/api/mark-docs-completos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone, value: false })
                });
                if (res.ok) {
                    // Reemplazar el badge + botón desmarcar por el botón de marcar
                    const cell = btn.closest('td');
                    cell.innerHTML = `<button onclick="markDocsCompletos('${phone}', this)" style="background:#7c3aed;color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem;">☑ Marcar docs completos</button>`;
                } else {
                    alert('Error al desmarcar.');
                    btn.disabled = false;
                    btn.innerText = '✕ Desmarcar';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = '✕ Desmarcar';
            }
        }

        // ── Solicitudes LLM ───────────────────────────────────────────
        const LLM_TIPO_LABELS = {
            desembolso_pendiente: { label: 'Desembolso pendiente', color: '#dc2626' },
            paz_salvo:            { label: 'Paz y salvo',          color: '#2563eb' },
            compra_cartera:       { label: 'Compra de cartera',    color: '#d97706' },
            error_descuento:      { label: 'Error en descuentos',  color: '#7c3aed' },
            prepago:              { label: 'Prepago/Abono',        color: '#059669' },
            cambio_cuenta:        { label: 'Cambio de cuenta',     color: '#0891b2' },
            urgente:              { label: 'Urgente',              color: '#dc2626' },
            reclamo:              { label: 'Reclamo formal',       color: '#b45309' },
            general:              { label: 'Consulta general',     color: '#6b7280' },
        };

        async function fetchLLMRequests() {
            const tbody = document.getElementById('llmReqTableBody');
            if (!tbody) return;
            const onlyPending = document.getElementById('llmOnlyPending')?.checked;
            tbody.innerHTML = '<tr><td colspan="7" style="padding:15px;text-align:center;color:var(--text-muted);">Cargando...</td></tr>';
            try {
                const url = '/admin/api/llm-requests' + (onlyPending ? '?pending=true' : '');
                const res = await fetch(url);
                const data = await res.json();
                const items = data.requests || [];
                const pending = items.filter(r => !r.resolved).length;
                document.getElementById('llmReqCount').innerText = items.length;
                document.getElementById('llmReqPendingCount').innerText = pending;
                const badge = document.getElementById('badgeLLMPendientes');
                if (badge) { badge.style.display = pending > 0 ? 'inline' : 'none'; badge.innerText = pending; }
                if (items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" style="padding:15px;text-align:center;color:var(--text-muted);">No hay solicitudes registradas.</td></tr>';
                    return;
                }
                tbody.innerHTML = items.map(r => {
                    const tipoInfo = LLM_TIPO_LABELS[r.tipo] || { label: r.tipo, color: '#6b7280' };
                    const badge = `<span style="background:${tipoInfo.color}1a;color:${tipoInfo.color};border:1px solid ${tipoInfo.color}44;padding:2px 8px;border-radius:999px;font-size:0.78rem;font-weight:600;white-space:nowrap;">${tipoInfo.label}</span>`;
                    const fecha = r.created_at ? new Date(r.created_at).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}) : '';
                    const detalle = (r.detalle || '').slice(0, 120) + ((r.detalle || '').length > 120 ? '…' : '');
                    const estadoBadge = r.resolved
                        ? `<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:999px;font-size:0.8rem;">✓ Resuelto</span>`
                        : `<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:999px;font-size:0.8rem;">Pendiente</span>`;
                    const actionBtn = r.resolved
                        ? ''
                        : `<button onclick="resolveLLMRequest('${r.id}', this)" style="background:#7c3aed;color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem;">✓ Resolver</button>`;
                    return `<tr style="border-bottom:1px solid #eee;">
                        <td style="padding:10px;white-space:nowrap;font-size:0.85rem;">${fecha}</td>
                        <td style="padding:10px;font-size:0.85rem;">${r.phone}</td>
                        <td style="padding:10px;font-size:0.85rem;">${r.client_name || ''}</td>
                        <td style="padding:10px;">${badge}</td>
                        <td style="padding:10px;font-size:0.85rem;color:var(--text-muted);max-width:260px;">${detalle}</td>
                        <td style="padding:10px;text-align:center;">${estadoBadge}</td>
                        <td style="padding:10px;text-align:center;">${actionBtn}</td>
                    </tr>`;
                }).join('');
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="7" style="padding:15px;text-align:center;color:#dc2626;">Error al cargar solicitudes.</td></tr>';
            }
        }

        async function resolveLLMRequest(id, btn) {
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch(`/admin/api/llm-requests/${id}/resolve`, { method: 'POST' });
                if (res.ok) {
                    fetchLLMRequests();
                } else {
                    alert('Error al resolver la solicitud.');
                    btn.disabled = false;
                    btn.innerText = '✓ Resolver';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = '✓ Resolver';
            }
        }

        // ── Solicitudes de Documentos (Paz y Salvos) ──────────────────
        const DOC_TYPE_LABELS = {
            paz_salvo: { label: 'Paz y salvo', color: '#2563eb' },
        };
        const DOC_SOURCE_LABELS = {
            menu: 'Menú del bot',
            llm:  'Agente LLM',
        };

        async function fetchDocumentRequests() {
            const tbody = document.getElementById('docReqTableBody');
            if (!tbody) return;
            const onlyPending = document.getElementById('docReqOnlyPending')?.checked;
            tbody.innerHTML = '<tr><td colspan="8" style="padding:15px;text-align:center;color:var(--text-muted);">Cargando...</td></tr>';
            try {
                const url = '/admin/api/document-requests' + (onlyPending ? '?pending=true' : '');
                const res = await fetch(url);
                const data = await res.json();
                const items = data.requests || [];
                const pending = items.filter(r => !r.completed).length;
                document.getElementById('docReqCount').innerText = items.length;
                document.getElementById('docReqPendingCount').innerText = pending;
                updateDocReqBadge(pending);
                if (items.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="8" style="padding:15px;text-align:center;color:var(--text-muted);">No hay solicitudes registradas.</td></tr>';
                    return;
                }
                tbody.innerHTML = items.map(r => {
                    const tipoInfo = DOC_TYPE_LABELS[r.doc_type] || { label: r.doc_type, color: '#6b7280' };
                    const badge = `<span style="background:${tipoInfo.color}1a;color:${tipoInfo.color};border:1px solid ${tipoInfo.color}44;padding:2px 8px;border-radius:999px;font-size:0.78rem;font-weight:600;white-space:nowrap;">${tipoInfo.label}</span>`;
                    const fecha = r.created_at ? new Date(r.created_at).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}) : '';
                    const origen = DOC_SOURCE_LABELS[r.source] || r.source || '';
                    const detalle = (r.detalle || '').slice(0, 120) + ((r.detalle || '').length > 120 ? '…' : '');
                    const estadoBadge = r.completed
                        ? `<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:999px;font-size:0.8rem;">✓ Completado</span>`
                        : `<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:999px;font-size:0.8rem;">Pendiente</span>`;
                    const actionBtn = r.completed
                        ? `<button onclick="reopenDocumentRequest('${r.id}', this)" style="background:none;color:#6b7280;border:1px solid #d1d5db;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.78rem;">↩ Reabrir</button>`
                        : `<button onclick="completeDocumentRequest('${r.id}', this)" style="background:#16a34a;color:white;border:none;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem;">✓ Completado</button>`;
                    return `<tr style="border-bottom:1px solid #eee;">
                        <td style="padding:10px;white-space:nowrap;font-size:0.85rem;">${fecha}</td>
                        <td style="padding:10px;font-size:0.85rem;">${r.phone}</td>
                        <td style="padding:10px;font-size:0.85rem;">${r.client_name || ''}</td>
                        <td style="padding:10px;">${badge}</td>
                        <td style="padding:10px;font-size:0.85rem;white-space:nowrap;">${origen}</td>
                        <td style="padding:10px;font-size:0.85rem;color:var(--text-muted);max-width:260px;">${detalle}</td>
                        <td style="padding:10px;text-align:center;">${estadoBadge}</td>
                        <td style="padding:10px;text-align:center;">${actionBtn}</td>
                    </tr>`;
                }).join('');
            } catch (e) {
                tbody.innerHTML = '<tr><td colspan="8" style="padding:15px;text-align:center;color:#dc2626;">Error al cargar solicitudes.</td></tr>';
            }
        }

        function updateDocReqBadge(pendingCount) {
            const badge = document.getElementById('badgeDocReqPendientes');
            if (!badge) return;
            if (pendingCount === null || pendingCount === undefined) return;
            badge.style.display = pendingCount > 0 ? 'inline' : 'none';
            badge.innerText = pendingCount;
        }

        // Carga inicial del contador de pendientes para que la pestaña
        // muestre el badge sin necesidad de abrirla.
        (async () => {
            try {
                const res = await fetch('/admin/api/document-requests?pending=true');
                const data = await res.json();
                updateDocReqBadge((data.requests || []).length);
            } catch (e) { /* sin conexión: el badge se actualiza al abrir la pestaña */ }
        })();

        async function completeDocumentRequest(id, btn) {
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch(`/admin/api/document-requests/${id}/complete`, { method: 'POST' });
                if (res.ok) {
                    fetchDocumentRequests();
                } else {
                    alert('Error al marcar como completado.');
                    btn.disabled = false;
                    btn.innerText = '✓ Completado';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = '✓ Completado';
            }
        }

        async function reopenDocumentRequest(id, btn) {
            btn.disabled = true;
            btn.innerText = '...';
            try {
                const res = await fetch(`/admin/api/document-requests/${id}/reopen`, { method: 'POST' });
                if (res.ok) {
                    fetchDocumentRequests();
                } else {
                    alert('Error al reabrir la solicitud.');
                    btn.disabled = false;
                    btn.innerText = '↩ Reabrir';
                }
            } catch (e) {
                alert('Error de conexión.');
                btn.disabled = false;
                btn.innerText = '↩ Reabrir';
            }
        }

        // ── Buscadores ────────────────────────────────────────────────
        function filterRows(inputId, tbodyId) {
            const query = document.getElementById(inputId).value.toLowerCase().trim();
            const rows = document.getElementById(tbodyId).querySelectorAll('tr');
            rows.forEach(row => {
                const text = row.innerText.toLowerCase();
                row.style.display = (!query || text.includes(query)) ? '' : 'none';
            });
        }

        function toggleEmpresaDrop(dropId) {
            document.querySelectorAll('.empresa-drop').forEach(d => {
                if (d.id !== dropId) d.style.display = 'none';
            });
            const drop = document.getElementById(dropId);
            drop.style.display = drop.style.display === 'none' ? 'block' : 'none';
        }

        document.addEventListener('click', function(e) {
            if (!e.target.closest('.empresa-multi-wrap')) {
                document.querySelectorAll('.empresa-drop').forEach(d => d.style.display = 'none');
            }
        });

        function getEmpresaChecked(dropId) {
            const drop = document.getElementById(dropId);
            if (!drop) return [];
            return Array.from(drop.querySelectorAll('input[type=checkbox]:checked')).map(cb => cb.value);
        }

        function updateEmpresaBtn(dropId) {
            const drop = document.getElementById(dropId);
            if (!drop) return;
            const span = drop.closest('.empresa-multi-wrap')?.querySelector('.empresa-btn span');
            if (!span) return;
            const n = drop.querySelectorAll('input:checked').length;
            span.textContent = n === 0 ? '🏢 Todas las empresas' : `🏢 ${n} empresa${n > 1 ? 's' : ''}`;
        }

        function onEmpresaChange(cb) {
            const drop = cb.closest('.empresa-drop');
            const wrap = drop.closest('.empresa-multi-wrap');
            updateEmpresaBtn(drop.id);
            if (wrap && wrap.dataset.search) {
                applyPanelFilter(wrap.dataset.search, wrap.dataset.tbody, drop.id);
            } else {
                applyDocsFilters();
            }
        }

        function applyPanelFilter(searchId, tbodyId, dropId) {
            const query    = (document.getElementById(searchId).value || '').toLowerCase().trim();
            const selected = getEmpresaChecked(dropId);
            const rows     = document.getElementById(tbodyId).querySelectorAll('tr');
            rows.forEach(row => {
                const text       = row.innerText.toLowerCase();
                const rowEmpresa = (row.getAttribute('data-empresa') || '').toLowerCase();
                const matchText    = !query    || text.includes(query);
                const matchEmpresa = selected.length === 0 || selected.includes(rowEmpresa);
                row.style.display = (matchText && matchEmpresa) ? '' : 'none';
            });
        }

        function populatePanelEmpresaFilter(data, dropId) {
            const drop = document.getElementById(dropId);
            if (!drop) return;
            const checked = new Set(Array.from(drop.querySelectorAll('input:checked')).map(cb => cb.value));
            const empresas = [...new Set(data.map(u => u.empresa || '').filter(Boolean))].sort();
            drop.innerHTML = empresas.map(e => {
                const val = e.toLowerCase();
                return `<label style="display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;font-size:0.9rem;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background=''">
                    <input type="checkbox" value="${val}" ${checked.has(val)?'checked':''} onchange="onEmpresaChange(this)">
                    ${e}
                </label>`;
            }).join('');
            updateEmpresaBtn(dropId);
        }

        let allDocsData = [];

        function applyDocsFilters() {
            const query    = (document.getElementById('docsSearch').value || '').toLowerCase().trim();
            const selected = getEmpresaChecked('docsEmpresaDrop');
            const tbody    = document.getElementById('docsTableBody');
            let showGroup  = true;
            tbody.querySelectorAll('tr').forEach(row => {
                const isHeader = row.hasAttribute('data-empresa');
                if (isHeader) {
                    const text       = row.innerText.toLowerCase();
                    const rowEmpresa = (row.getAttribute('data-empresa') || '').toLowerCase();
                    const matchText    = !query    || text.includes(query);
                    const matchEmpresa = selected.length === 0 || selected.includes(rowEmpresa);
                    showGroup = matchText && matchEmpresa;
                }
                row.style.display = showGroup ? '' : 'none';
            });
        }

        function filterDocsGroups(query) { applyDocsFilters(); }

        async function fetchArchivedList() {
            try {
                const res = await fetch('/admin/api/archived-conversations');
                const data = await res.json();
                renderArchivedList(data);
            } catch (err) {
                console.error('Error fetching archived:', err);
            }
        }

        function renderArchivedList(conversations) {
            const listEl = document.getElementById('convList');
            if (conversations.length === 0) {
                listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #777;">No hay conversaciones archivadas</div>';
                return;
            }
            let html = '';
            conversations.forEach(c => {
                const activeClass = currentActivePhone === c.phone ? 'active' : '';
                html += `
                    <div class="conv-item ${activeClass}" id="conv-item-${c.phone}" onclick="selectConversation('${c.phone}')">
                        <div class="conv-header">
                            <span class="conv-phone">${c.phone}</span>
                            <span class="conv-time">${formatTime(c.updated_at)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 5px;">
                            <span class="conv-preview">${c.last_message || '...'}</span>
                            <span class="archived-badge">ARCHIVADA</span>
                        </div>
                    </div>
                `;
            });
            listEl.innerHTML = html;
            filterList();
        }

        async function restoreChat() {
            if (!currentActivePhone) return;
            if (!confirm('¿Restaurar esta conversación a la lista activa del panel?')) return;
            try {
                const res = await fetch(`/admin/api/restore-chat/${currentActivePhone}`, { method: 'POST' });
                if (res.ok) {
                    currentActivePhone = null;
                    document.getElementById('emptyState').style.display = 'flex';
                    document.getElementById('mainChat').style.display = 'none';
                    fetchArchivedList();
                }
            } catch (e) {
                console.error(e);
            }
        }

        let pendingUsersData = [];
        
        async function fetchPendingEnvios(hideResults = true) {
            const tbody = document.getElementById('enviosTableBody');
            const btn = document.getElementById('btnExecuteEnvios');
            if (hideResults) {
                document.getElementById('enviosResults').style.display = 'none';
            }

            tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--text-muted);">Consultando clientes elegibles...</td></tr>';
            btn.disabled = true;
            pendingUsersData = [];
            pendingExcludedEnviosData = [];
            document.getElementById('enviosExcludedSection').style.display = 'none';
            document.getElementById('enviosStatLine').innerHTML = '';

            try {
                const res = await fetch('/admin/api/pending-notifications');
                const data = await res.json();

                if (res.ok && data.pending) {
                    pendingUsersData = data.pending;

                    if (pendingUsersData.length === 0) {
                        document.getElementById('enviosCount').innerText = '0';
                        tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--success); font-weight: bold;">✅ No hay clientes pendientes por notificar hoy.</td></tr>';
                    } else {
                        let rows = '';
                        pendingUsersData.forEach((user, idx) => {
                            const lastSent = user.last_sent
                                ? new Date(user.last_sent).toLocaleString('es-CO', {timeZone: 'America/Bogota', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'})
                                : 'Nunca';
                            const sendCount = user.send_count || 0;
                            const countColor = sendCount >= 3 ? 'color:#dc2626;font-weight:bold;' : sendCount >= 1 ? 'color:#d97706;' : '';
                            const empresaLabel = user.empresa ? `<br><span style="font-size:0.75rem;color:#6b7280;">${user.empresa}</span>` : '';
                            rows += `<tr style="border-bottom: 1px solid #eee;" data-empresa="${(user.empresa||'').toLowerCase()}">
                                <td style="padding: 10px; text-align: center;"><input type="checkbox" class="envio-check" data-idx="${idx}" checked onchange="updateSelectedCount()"></td>
                                <td style="padding: 10px;">${user.phone}</td>
                                <td style="padding: 10px;">${user.name}${empresaLabel}</td>
                                <td style="padding: 10px; text-align: center; ${countColor}">${sendCount}</td>
                                <td style="padding: 10px; font-size: 0.85rem; color: var(--text-muted);">${lastSent}</td>
                            </tr>`;
                        });
                        tbody.innerHTML = rows;
                        populatePanelEmpresaFilter(pendingUsersData, 'enviosEmpresaDrop');
                        updateSelectedCount();
                    }
                    pendingExcludedEnviosData = data.excluded || [];
                    renderExcludedSection('envios', pendingExcludedEnviosData);
                } else {
                    tbody.innerHTML = `<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error: ${data.message || 'Desconocido'}</td></tr>`;
                }
            } catch (e) {
                console.error(e);
                tbody.innerHTML = '<tr><td colspan="5" style="padding: 15px; text-align: center; color: var(--danger);">Error de conexión al cargar.</td></tr>';
            }
        }

        function selectOnlyNewClients() {
            document.querySelectorAll('.envio-check').forEach(cb => {
                const idx = parseInt(cb.dataset.idx);
                cb.checked = pendingUsersData[idx].send_count === 0;
            });
            updateSelectedCount();
        }

        function toggleAllChecks(masterCb) {
            document.querySelectorAll('.envio-check').forEach(cb => cb.checked = masterCb.checked);
            updateSelectedCount();
        }

        function updateSelectedCount() {
            const total = document.querySelectorAll('.envio-check').length;
            const selected = document.querySelectorAll('.envio-check:checked').length;
            const exclSelected = document.querySelectorAll('.envios-excl-check:checked').length;
            document.getElementById('enviosCount').innerText = `${selected} / ${total}`;
            document.getElementById('btnExecuteEnvios').disabled = (selected + exclSelected) === 0;
            const masterCb = document.getElementById('checkAll');
            if (masterCb) {
                masterCb.indeterminate = selected > 0 && selected < total;
                masterCb.checked = total > 0 && selected === total;
            }
        }
        
        async function executeBulkSend() {
            const checked = document.querySelectorAll('.envio-check:checked');
            const selectedEligible = Array.from(checked).map(cb => pendingUsersData[parseInt(cb.dataset.idx)]);
            const exclChecked = document.querySelectorAll('.envios-excl-check:checked');
            const selectedExcluded = Array.from(exclChecked).map(cb => pendingExcludedEnviosData[parseInt(cb.dataset.exclIdx)]);

            if (selectedEligible.length === 0 && selectedExcluded.length === 0) return;

            const doSend = () => _doExecuteBulkSend([...selectedEligible, ...selectedExcluded]);

            if (selectedExcluded.length > 0) {
                showExcludedConfirmModal(selectedExcluded, doSend);
                return;
            }
            if (!confirm(`¿Estás seguro de enviar la notificación de Aprobado a ${selectedEligible.length} clientes seleccionados?`)) return;
            doSend();
        }

        async function _doExecuteBulkSend(selectedUsers) {
            const btn = document.getElementById('btnExecuteEnvios');
            btn.disabled = true;
            btn.innerText = '⌛ Procesando...';

            let totalSuccess = 0;
            let totalFailed = 0;
            let allErrors = [];

            const batchSize = 15;
            const totalUsers = selectedUsers.length;
            
            document.getElementById('enviosResults').style.display = 'block';

            for (let i = 0; i < totalUsers; i += batchSize) {
                const chunk = selectedUsers.slice(i, i + batchSize);
                btn.innerText = `⌛ Enviando ${i + 1} - ${Math.min(i + batchSize, totalUsers)} de ${totalUsers}...`;
                
                try {
                    const res = await fetch('/admin/api/trigger-bulk-send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });
                    
                    const data = await res.json();
                    
                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFailed += data.results.fail || data.results.failed;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);
                        
                        // Update UI counts live
                        document.getElementById('enviosSuccessCount').innerText = totalSuccess;
                        document.getElementById('enviosFailCount').innerText = totalFailed;
                        
                        const errorList = document.getElementById('enviosErrorList');
                        if (allErrors.length > 0) {
                            errorList.innerHTML = allErrors.map(err => {
                                const p = err.phone || "Error";
                                const e = err.error || "Desconocido";
                                return `<li>${p}: ${e}</li>`;
                            }).join('');
                        } else {
                            errorList.innerHTML = '<li>Sin errores reportados en este lote.</li>';
                        }
                    } else {
                        console.error('Error en lote:', data.message);
                        totalFailed += chunk.length;
                        allErrors.push({ phone: 'Lote', error: data.message || 'Error de servidor' });
                    }
                } catch (e) {
                    console.error('Error de red en lote:', e);
                    totalFailed += chunk.length;
                    allErrors.push({ phone: 'Red', error: 'Error de conexión' });
                }
                
                // Pequeña pausa para no saturar
                await new Promise(r => setTimeout(r, 500));
            }
            
            btn.innerText = '🚀 Ejecutar Envío a Seleccionados';
            btn.disabled = false;
            
            // Refresh list at the end
            await fetchPendingEnvios(false);
            alert(`Proceso finalizado.\nÉxitos: ${totalSuccess}\nFallos: ${totalFailed}`);
        }

        async function executeBulkLeads() {
            const inputText = document.getElementById('leadsInputArea').value;
            if (!inputText.trim()) {
                alert("Por favor, ingresa al menos un número y nombre en el formato indicado.");
                return;
            }

            const lines = inputText.trim().split('\n');
            const allUsers = [];

            for (const line of lines) {
                if (!line.trim()) continue;
                let parts = line.includes('\t') ? line.split('\t') : (line.includes(',') ? line.split(',') : line.split(';'));
                if (parts.length >= 2) {
                    const phone = parts[0].replace(/\D/g, '').trim();
                    const name = parts.slice(1).join(' ').trim(); 
                    if (phone && name) {
                        allUsers.push({ phone, name });
                    }
                }
            }

            if (allUsers.length === 0) {
                alert("No se detectaron usuarios válidos. Revisa el formato.");
                return;
            }

            if (!confirm(`¿Estás seguro de enviar la campaña Leads a ${allUsers.length} personas?`)) return;

            const btn = document.getElementById('btnExecuteLeads');
            const statusText = document.getElementById('leadsStatusText');
            
            btn.disabled = true;
            
            let totalSuccess = 0;
            let totalFail = 0;
            let allErrors = [];
            const batchSize = 15;
            
            document.getElementById('leadsResults').style.display = 'block';

            for (let i = 0; i < allUsers.length; i += batchSize) {
                const chunk = allUsers.slice(i, i + batchSize);
                btn.innerText = `⌛ ${i + 1} - ${Math.min(i + batchSize, allUsers.length)} de ${allUsers.length}...`;
                statusText.innerText = `Enviando lote de ${chunk.length} leads...`;

                try {
                    const res = await fetch('/admin/api/trigger-bulk-leads', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });

                    const data = await res.json();

                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFail += data.results.fail;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);
                        
                        document.getElementById('leadsSuccessCount').innerText = totalSuccess;
                        document.getElementById('leadsFailCount').innerText = totalFail;
                        
                        const errorList = document.getElementById('leadsErrorList');
                        if (allErrors.length > 0) {
                            errorList.innerHTML = allErrors.map(err => `<li>${err}</li>`).join('');
                        } else {
                            errorList.innerHTML = '<li>Sin errores reportados.</li>';
                        }
                    } else {
                        totalFail += chunk.length;
                    }
                } catch (e) {
                    console.error(e);
                    totalFail += chunk.length;
                }
                
                await new Promise(r => setTimeout(r, 500));
            }

            btn.innerText = '🎯 Enviar a Leads';
            btn.disabled = false;
            statusText.innerText = "Campaña finalizada.";
            alert(`Campaña terminada.\nÉxitos: ${totalSuccess}\nFallos: ${totalFail}`);
        }

        function handleLeadsFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            const statusText = document.getElementById('leadsStatusText');
            statusText.innerText = "Leyendo archivo...";

            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, { type: 'array' });
                    
                    const firstSheetName = workbook.SheetNames[0];
                    const worksheet = workbook.Sheets[firstSheetName];
                    const json = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
                    
                    let resultText = "";
                    let count = 0;
                    for (let i = 0; i < json.length; i++) {
                        const row = json[i];
                        if (row.length >= 2) {
                            let phone = String(row[0] || "").replace(/\D/g, '').trim();
                            let name = String(row[1] || "").trim();
                            if (i === 0 && (phone === "telefono" || phone === "phone" || isNaN(phone))) continue;
                            if (phone && name) {
                                resultText += `${phone}, ${name}\n`;
                                count++;
                            }
                        }
                    }
                    document.getElementById('leadsInputArea').value = resultText;
                    statusText.innerText = `Se cargaron ${count} leads exitosamente.`;
                    event.target.value = '';
                } catch (err) {
                    console.error("Error al leer Excel:", err);
                    alert("Error al leer el archivo.");
                    statusText.innerText = "Error de lectura.";
                }
            };
            reader.readAsArrayBuffer(file);
        }

        async function executeBulkRenovados() {
            const inputText = document.getElementById('renovadosInputArea').value;
            if (!inputText.trim()) {
                alert("Por favor, ingresa al menos un número y nombre en el formato indicado.");
                return;
            }

            const lines = inputText.trim().split('\n');
            const allUsers = [];

            for (const line of lines) {
                if (!line.trim()) continue;
                let parts = line.includes('\t') ? line.split('\t') : (line.includes(',') ? line.split(',') : line.split(';'));
                if (parts.length >= 2) {
                    const phone = parts[0].replace(/\D/g, '').trim();
                    const name = parts.slice(1).join(' ').trim();
                    if (phone && name) {
                        allUsers.push({ phone, name });
                    }
                }
            }

            if (allUsers.length === 0) {
                alert("No se detectaron usuarios válidos. Revisa el formato.");
                return;
            }

            if (!confirm(`¿Estás seguro de enviar la campaña Renovados a ${allUsers.length} personas?`)) return;

            const btn = document.getElementById('btnExecuteRenovados');
            const statusText = document.getElementById('renovadosStatusText');

            btn.disabled = true;

            let totalSuccess = 0;
            let totalFail = 0;
            let allErrors = [];
            const batchSize = 15;

            document.getElementById('renovadosResults').style.display = 'block';

            for (let i = 0; i < allUsers.length; i += batchSize) {
                const chunk = allUsers.slice(i, i + batchSize);
                btn.innerText = `⌛ ${i + 1} - ${Math.min(i + batchSize, allUsers.length)} de ${allUsers.length}...`;
                statusText.innerText = `Enviando lote de ${chunk.length} renovados...`;

                try {
                    const res = await fetch('/admin/api/trigger-bulk-renovados', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk })
                    });

                    const data = await res.json();

                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFail += data.results.fail;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);

                        document.getElementById('renovadosSuccessCount').innerText = totalSuccess;
                        document.getElementById('renovadosFailCount').innerText = totalFail;

                        const errorList = document.getElementById('renovadosErrorList');
                        if (allErrors.length > 0) {
                            errorList.innerHTML = allErrors.map(err => `<li>${err}</li>`).join('');
                        } else {
                            errorList.innerHTML = '<li>Sin errores reportados.</li>';
                        }
                    } else {
                        totalFail += chunk.length;
                    }
                } catch (e) {
                    console.error(e);
                    totalFail += chunk.length;
                }

                await new Promise(r => setTimeout(r, 500));
            }

            btn.innerText = '🔄 Enviar a Renovados';
            btn.disabled = false;
            statusText.innerText = "Campaña finalizada.";
            alert(`Campaña terminada.\nÉxitos: ${totalSuccess}\nFallos: ${totalFail}`);
        }

        function handleRenovadosFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            const statusText = document.getElementById('renovadosStatusText');
            statusText.innerText = "Leyendo archivo...";

            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, { type: 'array' });

                    const firstSheetName = workbook.SheetNames[0];
                    const worksheet = workbook.Sheets[firstSheetName];
                    const json = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

                    let resultText = "";
                    let count = 0;
                    for (let i = 0; i < json.length; i++) {
                        const row = json[i];
                        if (row.length >= 2) {
                            let phone = String(row[0] || "").replace(/\D/g, '').trim();
                            let name = String(row[1] || "").trim();
                            if (i === 0 && (phone === "telefono" || phone === "phone" || isNaN(phone))) continue;
                            if (phone && name) {
                                resultText += `${phone}, ${name}\n`;
                                count++;
                            }
                        }
                    }
                    document.getElementById('renovadosInputArea').value = resultText;
                    statusText.innerText = `Se cargaron ${count} renovados exitosamente.`;
                    event.target.value = '';
                } catch (err) {
                    console.error("Error al leer Excel:", err);
                    alert("Error al leer el archivo.");
                    statusText.innerText = "Error de lectura.";
                }
            };
            reader.readAsArrayBuffer(file);
        }

        async function fetchLeadMetrics() {
            try {
                const res = await fetch('/admin/api/lead-metrics');
                const data = await res.json();
                if (!res.ok || !data.metrics) return;
                const m = data.metrics;
                const total = m.total || 0;

                document.getElementById('leadMetricTotal').innerText = total || '0';
                document.getElementById('leadMetricSolicitar').innerText = m.solicitar_count || 0;
                document.getElementById('leadMetricAsesor').innerText = m.hablar_asesor_count || 0;
                document.getElementById('leadMetricAhoraNo').innerText = m.ahora_no_count || 0;
                document.getElementById('leadMetricSinRespuesta').innerText = m.sin_respuesta_count || 0;

                if (total > 0) {
                    document.getElementById('leadMetricSolicitarPct').innerText = Math.round((m.solicitar_count / total) * 100) + '%';
                    document.getElementById('leadMetricAsesorPct').innerText = Math.round((m.hablar_asesor_count / total) * 100) + '%';
                    document.getElementById('leadMetricAhoraNosPct').innerText = Math.round((m.ahora_no_count / total) * 100) + '%';
                    document.getElementById('leadMetricSinRespuestaPct').innerText = Math.round((m.sin_respuesta_count / total) * 100) + '%';
                }

                const tbody = document.getElementById('leadMetricsTableBody');
                if (!m.solicitar || m.solicitar.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="padding:14px;text-align:center;color:#9ca3af;">Sin conversiones aún.</td></tr>';
                    return;
                }
                tbody.innerHTML = m.solicitar.map(r => {
                    const fecha = r.responded_at ? new Date(r.responded_at).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}) : '—';
                    return `<tr style="border-bottom:1px solid #f3f4f6;">
                        <td style="padding:7px 10px;">${r.client_name || '—'}</td>
                        <td style="padding:7px 10px;font-family:monospace;font-size:0.79rem;">${r.phone}</td>
                        <td style="padding:7px 10px;color:#6b7280;font-size:0.78rem;">${fecha}</td>
                        <td style="padding:7px 10px;text-align:center;">
                            <button onclick="goToChat('${r.phone}')"
                                style="background:#dcfce7;border:none;border-radius:4px;padding:3px 10px;font-size:0.78rem;cursor:pointer;color:#065f46;">
                                Chat
                            </button>
                        </td>
                    </tr>`;
                }).join('');
            } catch(e) { console.error('fetchLeadMetrics error:', e); }
        }

        async function fetchRenovadoMetrics() {
            try {
                const res = await fetch('/admin/api/renovado-metrics');
                const data = await res.json();
                if (!res.ok || !data.metrics) return;
                const m = data.metrics;
                const total = m.total || 0;

                document.getElementById('renovadoMetricTotal').innerText = total || '0';
                document.getElementById('renovadoMetricSolicitar').innerText = m.solicitar_count || 0;
                document.getElementById('renovadoMetricNoQuiero').innerText = m.no_quiero_count || 0;
                document.getElementById('renovadoMetricMasInfo').innerText = m.mas_info_count || 0;
                document.getElementById('renovadoMetricSinRespuesta').innerText = m.sin_respuesta_count || 0;

                if (total > 0) {
                    document.getElementById('renovadoMetricSolicitarPct').innerText = Math.round((m.solicitar_count / total) * 100) + '%';
                    document.getElementById('renovadoMetricNoQuieroPct').innerText = Math.round((m.no_quiero_count / total) * 100) + '%';
                    document.getElementById('renovadoMetricMasInfoPct').innerText = Math.round((m.mas_info_count / total) * 100) + '%';
                    document.getElementById('renovadoMetricSinRespuestaPct').innerText = Math.round((m.sin_respuesta_count / total) * 100) + '%';
                }

                const tbody = document.getElementById('renovadoMetricsTableBody');
                if (!m.solicitar || m.solicitar.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="padding:14px;text-align:center;color:#9ca3af;">Sin renovaciones aún.</td></tr>';
                    return;
                }
                tbody.innerHTML = m.solicitar.map(r => {
                    const fecha = r.responded_at ? new Date(r.responded_at).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}) : '—';
                    return `<tr style="border-bottom:1px solid #f3f4f6;">
                        <td style="padding:7px 10px;">${r.client_name || '—'}</td>
                        <td style="padding:7px 10px;font-family:monospace;font-size:0.79rem;">${r.phone}</td>
                        <td style="padding:7px 10px;color:#6b7280;font-size:0.78rem;">${fecha}</td>
                        <td style="padding:7px 10px;text-align:center;">
                            <button onclick="goToChat('${r.phone}')"
                                style="background:#e0f2fe;border:none;border-radius:4px;padding:3px 10px;font-size:0.78rem;cursor:pointer;color:#075985;">
                                Chat
                            </button>
                        </td>
                    </tr>`;
                }).join('');
            } catch(e) { console.error('fetchRenovadoMetrics error:', e); }
        }

        async function fetchAnticiposMetrics() {
            try {
                const res = await fetch('/admin/api/anticipo-metrics');
                const data = await res.json();
                if (!res.ok || !data.metrics) return;

                const m = data.metrics;
                const total = m.total || 0;

                document.getElementById('metricTotal').innerText = total || '0';
                document.getElementById('metricSolicitar').innerText = m.solicitar_count || 0;
                document.getElementById('metricNoGracias').innerText = m.no_gracias_count || 0;
                document.getElementById('metricChat').innerText = m.respondieron_chat_count || 0;
                document.getElementById('metricSinRespuesta').innerText = m.sin_respuesta_count || 0;

                if (total > 0) {
                    document.getElementById('metricSolicitarPct').innerText = Math.round((m.solicitar_count / total) * 100) + '%';
                    document.getElementById('metricNoGraciasPct').innerText = Math.round((m.no_gracias_count / total) * 100) + '%';
                    document.getElementById('metricChatPct').innerText = Math.round(((m.respondieron_chat_count || 0) / total) * 100) + '%';
                    document.getElementById('metricSinRespuestaPct').innerText = Math.round((m.sin_respuesta_count / total) * 100) + '%';
                }

                const tbody = document.getElementById('anticiposMetricsTableBody');
                if (!m.solicitar || m.solicitar.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="padding:14px;text-align:center;color:#9ca3af;">Sin interesados aún.</td></tr>';
                    return;
                }

                tbody.innerHTML = m.solicitar.map(r => {
                    const fecha = r.responded_at ? new Date(r.responded_at).toLocaleString('es-CO', {dateStyle:'short', timeStyle:'short'}) : '—';
                    const submitted = r.form_submitted;
                    const btnBg    = submitted ? '#d1fae5' : '#fef3c7';
                    const btnBdr   = submitted ? '#6ee7b7' : '#fcd34d';
                    const btnColor = submitted ? '#065f46' : '#78350f';
                    const btnLabel = submitted ? '✅ Enviado' : '⏳ Pendiente';
                    return `<tr style="border-bottom:1px solid #f3f4f6;">
                        <td style="padding:7px 10px;">${r.client_name || '—'}</td>
                        <td style="padding:7px 10px;font-family:monospace;font-size:0.79rem;">${r.phone}</td>
                        <td style="padding:7px 10px;color:#6b7280;font-size:0.78rem;">${fecha}</td>
                        <td style="padding:7px 10px;text-align:center;">
                            <button onclick="toggleAnticipioForm('${r.phone}', this)"
                                style="background:${btnBg};border:1px solid ${btnBdr};border-radius:4px;padding:3px 10px;font-size:0.78rem;cursor:pointer;color:${btnColor};">
                                ${btnLabel}
                            </button>
                        </td>
                        <td style="padding:7px 10px;text-align:center;">
                            <button onclick="goToChat('${r.phone}')"
                                style="background:#ede9fe;border:none;border-radius:4px;padding:3px 10px;font-size:0.78rem;cursor:pointer;color:#7c3aed;">
                                Chat
                            </button>
                        </td>
                    </tr>`;
                }).join('');
            } catch(e) {
                console.error('fetchAnticiposMetrics error:', e);
            }
        }

        async function toggleAnticipioForm(phone, btn) {
            try {
                const res = await fetch(`/admin/api/anticipo-toggle-form/${phone}`, { method: 'POST' });
                const data = await res.json();
                if (data.status === 'ok') {
                    const submitted = data.form_submitted;
                    btn.style.background = submitted ? '#d1fae5' : '#fef3c7';
                    btn.style.border = `1px solid ${submitted ? '#6ee7b7' : '#fcd34d'}`;
                    btn.style.color = submitted ? '#065f46' : '#78350f';
                    btn.innerText = submitted ? '✅ Enviado' : '⏳ Pendiente';
                }
            } catch(e) {
                console.error('toggleAnticipioForm error:', e);
            }
        }

        async function executeBulkAnticipos() {
            const inputText = document.getElementById('anticiposInputArea').value;
            if (!inputText.trim()) {
                alert("Por favor, ingresa al menos un número y nombre en el formato indicado.");
                return;
            }

            const lines = inputText.trim().split('\n');
            const allUsers = [];

            for (const line of lines) {
                if (!line.trim()) continue;
                let parts = line.includes('\t') ? line.split('\t') : (line.includes(',') ? line.split(',') : line.split(';'));
                if (parts.length >= 2) {
                    const phone = parts[0].replace(/\D/g, '').trim();
                    const name = parts.slice(1).join(' ').trim();
                    if (phone && name) {
                        allUsers.push({ phone, name });
                    }
                }
            }

            if (allUsers.length === 0) {
                alert("No se detectaron usuarios válidos. Revisa el formato.");
                return;
            }

            const forceSend = document.getElementById('anticiposForceSend').checked;

            const confirmMsg = forceSend
                ? `¿Estás seguro de enviar la campaña Anticipos a ${allUsers.length} personas, incluyendo a quienes ya indicaron que no estaban interesados?`
                : `¿Estás seguro de enviar la campaña Anticipos a ${allUsers.length} personas?`;
            if (!confirm(confirmMsg)) return;

            const btn = document.getElementById('btnExecuteAnticipos');
            const statusText = document.getElementById('anticiposStatusText');

            btn.disabled = true;

            let totalSuccess = 0;
            let totalFail = 0;
            let allErrors = [];
            const batchSize = 15;

            document.getElementById('anticiposResults').style.display = 'block';

            for (let i = 0; i < allUsers.length; i += batchSize) {
                const chunk = allUsers.slice(i, i + batchSize);
                btn.innerText = `⌛ ${i + 1} - ${Math.min(i + batchSize, allUsers.length)} de ${allUsers.length}...`;
                statusText.innerText = `Enviando lote de ${chunk.length} anticipos...`;

                try {
                    const res = await fetch('/admin/api/trigger-bulk-anticipos', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ users: chunk, force: forceSend })
                    });

                    const data = await res.json();

                    if (res.ok && data.results) {
                        totalSuccess += data.results.success;
                        totalFail += data.results.fail;
                        if (data.results.errors) allErrors = allErrors.concat(data.results.errors);

                        document.getElementById('anticiposSuccessCount').innerText = totalSuccess;
                        document.getElementById('anticiposFailCount').innerText = totalFail;

                        const errorList = document.getElementById('anticiposErrorList');
                        if (allErrors.length > 0) {
                            errorList.innerHTML = allErrors.map(err => `<li>${err}</li>`).join('');
                        } else {
                            errorList.innerHTML = '<li>Sin errores reportados.</li>';
                        }
                    } else {
                        totalFail += chunk.length;
                    }
                } catch (e) {
                    console.error(e);
                    totalFail += chunk.length;
                }

                await new Promise(r => setTimeout(r, 500));
            }

            btn.innerText = '💰 Enviar Anticipos';
            btn.disabled = false;
            statusText.innerText = "Campaña finalizada.";
            alert(`Campaña terminada.\nÉxitos: ${totalSuccess}\nFallos: ${totalFail}`);
        }

        function handleAnticiposFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            const statusText = document.getElementById('anticiposStatusText');
            statusText.innerText = "Leyendo archivo...";

            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, { type: 'array' });

                    const firstSheetName = workbook.SheetNames[0];
                    const worksheet = workbook.Sheets[firstSheetName];
                    const json = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

                    let resultText = "";
                    let count = 0;
                    for (let i = 0; i < json.length; i++) {
                        const row = json[i];
                        if (row.length >= 2) {
                            let phone = String(row[0] || "").replace(/\D/g, '').trim();
                            let name = String(row[1] || "").trim();
                            if (i === 0 && (phone === "telefono" || phone === "phone" || isNaN(phone))) continue;
                            if (phone && name) {
                                resultText += `${phone}, ${name}\n`;
                                count++;
                            }
                        }
                    }
                    document.getElementById('anticiposInputArea').value = resultText;
                    statusText.innerText = `Se cargaron ${count} anticipos exitosamente.`;
                    event.target.value = '';
                } catch (err) {
                    console.error("Error al leer Excel:", err);
                    alert("Error al leer el archivo.");
                    statusText.innerText = "Error de lectura.";
                }
            };
            reader.readAsArrayBuffer(file);
        }

        document.getElementById('anticiposInputArea').addEventListener('paste', (e) => {
            const clipboardData = e.clipboardData || window.clipboardData;
            const pastedData = clipboardData.getData('Text');

            if (pastedData.includes('\t')) {
                e.preventDefault();
                const lines = pastedData.split(/\r?\n/);
                const formatted = lines.map(line => {
                    if (!line.trim()) return "";
                    const parts = line.split('\t');
                    if (parts.length >= 2) {
                        return `${parts[0].trim()}, ${parts.slice(1).join(' ').trim()}`;
                    }
                    return line;
                }).filter(l => l !== "").join('\n');

                const textarea = e.target;
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const value = textarea.value;
                textarea.value = value.substring(0, start) + formatted + value.substring(end);

                document.getElementById('anticiposStatusText').innerText = "Datos de Excel pegados y formateados.";
            }
        });

        document.getElementById('renovadosInputArea').addEventListener('paste', (e) => {
            const clipboardData = e.clipboardData || window.clipboardData;
            const pastedData = clipboardData.getData('Text');

            if (pastedData.includes('\t')) {
                e.preventDefault();
                const lines = pastedData.split(/\r?\n/);
                const formatted = lines.map(line => {
                    if (!line.trim()) return "";
                    const parts = line.split('\t');
                    if (parts.length >= 2) {
                        return `${parts[0].trim()}, ${parts.slice(1).join(' ').trim()}`;
                    }
                    return line;
                }).filter(l => l !== "").join('\n');

                const textarea = e.target;
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const value = textarea.value;
                textarea.value = value.substring(0, start) + formatted + value.substring(end);

                document.getElementById('renovadosStatusText').innerText = "Datos de Excel pegados y formateados.";
            }
        });

        // Detectar pegado desde Excel (Tabs) y convertir a formato Comma
        document.getElementById('leadsInputArea').addEventListener('paste', (e) => {
            const clipboardData = e.clipboardData || window.clipboardData;
            const pastedData = clipboardData.getData('Text');

            if (pastedData.includes('\t')) {
                e.preventDefault();
                const lines = pastedData.split(/\r?\n/);
                const formatted = lines.map(line => {
                    if (!line.trim()) return "";
                    const parts = line.split('\t');
                    if (parts.length >= 2) {
                        return `${parts[0].trim()}, ${parts.slice(1).join(' ').trim()}`;
                    }
                    return line;
                }).filter(l => l !== "").join('\n');

                const textarea = e.target;
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const value = textarea.value;
                textarea.value = value.substring(0, start) + formatted + value.substring(end);
                
                document.getElementById('leadsStatusText').innerText = "Datos de Excel pegados y formateados.";
            }
        });


        function playBeep() {
            try {
                const AudioContext = window.AudioContext || window.webkitAudioContext;
                if (!AudioContext) return;
                const ctx = new AudioContext();
                const current = ctx.currentTime;
                // Double chime
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.type = 'sine';

                // First chime
                osc.frequency.setValueAtTime(880, current);
                gain.gain.setValueAtTime(0.3, current);
                gain.gain.exponentialRampToValueAtTime(0.01, current + 0.2);

                // Second chime
                osc.frequency.setValueAtTime(1046, current + 0.2);
                gain.gain.setValueAtTime(0.3, current + 0.2);
                gain.gain.exponentialRampToValueAtTime(0.01, current + 0.5);

                osc.start(current);
                osc.stop(current + 0.5);
            } catch (e) {
                console.error("Audio beep failed", e);
            }
        }

        function formatTime(isoString) {
            if (!isoString) return "";
            const date = new Date(isoString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' - ' + date.toLocaleDateString();
        }

        function scrollToBottom() {
            const h = document.getElementById('chatHistory');
            h.scrollTop = h.scrollHeight;
        }

        async function fetchList() {
            const tabAtFetch = currentTab; // recordar la pestaña que pidió la lista
            try {
                const endpoint = currentTab === 'prospectos'
                    ? '/admin/api/lead-conversations'
                    : currentTab === 'renovadoschat'
                    ? '/admin/api/renovado-conversations'
                    : currentTab === 'anticiposchat'
                    ? '/admin/api/anticipos-conversations'
                    : '/admin/api/conversations';
                const res = await fetch(endpoint);
                const data = await res.json();
                if (currentTab !== tabAtFetch) return; // cambió de pestaña mientras llegaba: descartar resultado obsoleto
                renderList(data);
            } catch (err) {
                console.error("Error fetching list:", err);
            }
        }

        function getAvatarColor(phone) {
            const colors = ['#ef4444','#f97316','#d97706','#16a34a','#0891b2','#7c3aed','#db2777','#0284c7'];
            const idx = phone.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % colors.length;
            return colors[idx];
        }

        function renderList(conversations) {
            const listEl = document.getElementById('convList');
            const isLeadsTab = currentTab === 'prospectos';
            const isRenovadosTab = currentTab === 'renovadoschat';
            const isAnticiposTab = currentTab === 'anticiposchat';

            if (conversations.length === 0) {
                const emptyMsg = isLeadsTab ? 'No hay leads registrados'
                    : isRenovadosTab ? 'No hay renovados registrados'
                    : isAnticiposTab ? 'No hay anticipos registrados'
                    : 'No hay conversaciones registradas';
                listEl.innerHTML = `<div style="padding: 20px; text-align: center; color: #777;">${emptyMsg}</div>`;
                return;
            }

            // Save scroll pos
            const scrollPos = listEl.scrollTop;

            let html = '';
            let newAgentDetected = false;

            // Ordenar: Primero los que están en modo ASESOR o BOT HUMANO, luego el resto por fecha de actualización
            conversations.sort((a, b) => {
                const priorityStatus = ['agent', 'agent_silent', 'agent_llm'];
                const aIsPriority = priorityStatus.includes(a.status);
                const bIsPriority = priorityStatus.includes(b.status);

                if (aIsPriority && !bIsPriority) return -1;
                if (!aIsPriority && bIsPriority) return 1;

                // Si ambos tienen la misma prioridad, ordenar por fecha de actualización (más reciente primero)
                return new Date(b.updated_at) - new Date(a.updated_at);
            });

            conversations.forEach(c => {
                let statusClass = 'status-bot';
                let statusLabel = 'BOT';

                if (c.status === 'agent') {
                    statusClass = 'status-agent';
                    statusLabel = '🔴 ASESOR';
                } else if (c.status === 'agent_silent') {
                    statusClass = 'status-silent';
                    statusLabel = '🔇 BOT HUMANO';
                } else if (c.status === 'agent_llm') {
                    statusClass = 'status-llm';
                    statusLabel = '🤖 AGENTE LLM';
                } else {
                    if (c.status === 'pending_consent') statusLabel = 'BOT (Habeas Data)';
                    else if (c.status === 'waiting_for_cedula') statusLabel = 'BOT (Ced. Solicitud)';
                    else if (c.status === 'waiting_for_cedula_saldo') statusLabel = 'BOT (Ced. Saldo)';
                    else if (c.status === 'lead_notified') { statusClass = 'status-lead'; statusLabel = 'LEAD'; }
                    else if (c.status === 'renovado_notified') { statusClass = 'status-renovado'; statusLabel = 'RENOVADO'; }
                    else if (c.status === 'anticipos_notified') { statusClass = 'status-anticipo'; statusLabel = 'ANTICIPO'; }
                }

                const activeClass = currentActivePhone === c.phone ? 'active' : '';

                // Check who is active here
                const activeInChat = latestActiveAdvisors.filter(a => a.current_chat === c.phone);
                let advisorIcons = '';
                if (activeInChat.length > 0) {
                    advisorIcons = `<div style="font-size: 0.75rem; color: #22c55e; margin-top: 6px; font-weight: 600; display: flex; gap: 6px; flex-wrap: wrap;">
                        ${activeInChat.map(a => '<span>🟢 ' + (a.name === advisorName ? a.name + ' (Tú)' : a.name) + '</span>').join('')}
                    </div>`;
                }

                // Notification Logic (only for normal agent mode)
                if (c.status === 'agent' && !knownAgentModes[c.phone]) {
                    if (Object.keys(knownAgentModes).length > 0) {
                        newAgentDetected = true;
                    }
                    knownAgentModes[c.phone] = true;
                } else if (c.status !== 'agent' && knownAgentModes[c.phone]) {
                    knownAgentModes[c.phone] = false;
                }

                const nameRow = c.client_name ? `<div style="font-size: 0.78rem; font-weight: 600; color: var(--text-primary); margin-bottom: 2px;">${c.client_name}</div>` : '';

                html += `
    <div class="conv-item ${activeClass}" id="conv-item-${c.phone}" data-name="${(c.client_name || '').toLowerCase()}" onclick="selectConversation('${c.phone}')">
        <div class="conv-avatar" style="background: ${getAvatarColor(c.phone)}">${c.phone.slice(-3)}</div>
        <div class="conv-body">
            <div class="conv-header">
                <span class="conv-phone">${c.phone}</span>
                <span class="conv-time">${formatTime(c.updated_at)}</span>
            </div>
            ${nameRow}
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-top: 2px;">
                <span class="conv-preview">${c.last_message || '...'}</span>
                <span class="conv-status ${statusClass}">${statusLabel.replace('🔴 ','').replace('🔇 ','').replace('🤖 ','')}</span>
            </div>
            ${advisorIcons}
        </div>
    </div>
    `;
            });
            listEl.innerHTML = html;
            listEl.scrollTop = scrollPos;

            if (newAgentDetected) {
                playBeep();
            }

            filterList(); // Re-apply filter if any
        }

        let searchDebounce = null;

        function filterList() {
            const val = document.getElementById('searchInput').value.toLowerCase().trim();
            const items = document.querySelectorAll('#convList .conv-item');
            let visibleCount = 0;
            items.forEach(item => {
                const phone = item.querySelector('.conv-phone').innerText.toLowerCase();
                const name = item.dataset.name || '';
                if (phone.includes(val) || name.includes(val)) {
                    item.style.display = 'flex';
                    visibleCount++;
                } else {
                    item.style.display = 'none';
                }
            });

            const serverResult = document.getElementById('serverSearchResult');
            serverResult.innerHTML = '';
            clearTimeout(searchDebounce);
            if (visibleCount === 0 && val.length >= 5) {
                serverResult.innerHTML = '<div style="padding: 12px; text-align: center; color: #888; font-size: 0.85rem;">Buscando...</div>';
                searchDebounce = setTimeout(() => searchServer(val), 500);
            }
        }

        async function searchServer(phone) {
            const serverResult = document.getElementById('serverSearchResult');
            try {
                const res = await fetch(`/admin/api/conversations/${phone}`);
                if (!res.ok) {
                    serverResult.innerHTML = '<div style="padding: 12px; text-align: center; color: #888; font-size: 0.85rem;">No encontrado</div>';
                    return;
                }
                const data = await res.json();
                if (data.error) {
                    serverResult.innerHTML = '<div style="padding: 12px; text-align: center; color: #888; font-size: 0.85rem;">No encontrado</div>';
                    return;
                }
                const lastMsg = data.messages && data.messages.length > 0
                    ? data.messages[data.messages.length - 1].text
                    : '...';
                const preview = lastMsg.length > 60 ? lastMsg.substring(0, 60) + '…' : lastMsg;
                let statusClass = 'status-bot';
                let statusLabel = 'BOT';
                if (data.status === 'agent') { statusClass = 'status-agent'; statusLabel = '🔴 ASESOR'; }
                else if (data.status === 'agent_silent') { statusClass = 'status-silent'; statusLabel = '🔇 BOT HUMANO'; }
                else if (data.status === 'agent_llm') { statusClass = 'status-llm'; statusLabel = '🤖 AGENTE LLM'; }
                const activeClass = currentActivePhone === phone ? 'active' : '';
                serverResult.innerHTML = `
                    <div style="padding: 6px 10px; font-size: 0.72rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;">Resultado de búsqueda</div>
                    <div class="conv-item ${activeClass}" onclick="selectConversation('${phone}')">
                        <div class="conv-header">
                            <span class="conv-phone">${phone}</span>
                            <span class="conv-time">${formatTime(data.updated_at)}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 5px;">
                            <span class="conv-preview">${preview}</span>
                            <span class="conv-status ${statusClass}">${statusLabel}</span>
                        </div>
                    </div>`;
            } catch (e) {
                serverResult.innerHTML = '<div style="padding: 12px; text-align: center; color: #888; font-size: 0.85rem;">Error al buscar</div>';
            }
        }

        function goToChat(phone) {
            switchTab('activas');
            selectConversation(phone);
        }

        async function selectConversation(phone) {
            currentActivePhone = phone;
            document.getElementById('emptyState').style.display = 'none';
            document.getElementById('enviosState').style.display = 'none';
            document.getElementById('amarilloState').style.display = 'none';
            document.getElementById('negadosState').style.display = 'none';
            document.getElementById('rojoState').style.display = 'none';
            document.getElementById('docRecibidosState').style.display = 'none';
            document.getElementById('mainChat').style.display = 'flex';
            document.getElementById('currentPhone').innerText = phone;

            // Re-render list to show active state
            await fetchList();

            // Fetch history (force scroll to bottom on initial select)
            await fetchHistory(phone, true);
        }

        async function fetchHistory(phone, forceScroll = false) {
            if (!phone) return;
            try {
                const res = await fetch(`/admin/api/conversations/${phone}`);
                const data = await res.json();

                const historyEl = document.getElementById('chatHistory');
                const isAtBottom = historyEl.scrollHeight - historyEl.scrollTop - historyEl.clientHeight < 100;
                const oldScrollTop = historyEl.scrollTop;

                let html = '';

                data.messages.forEach(m => {
                    const isOut = m.direction === 'outbound';
                    const isAgentMsg = isOut && (m.text.includes('Asesor ProAlto') || m.text.includes('👨‍💼'));
                    const isLlmMsg = isOut && m.type === 'llm';

                    let classes = `message ${isOut ? 'msg-outbound' : 'msg-inbound'}`;
                    if (isAgentMsg) classes += ' msg-agent';
                    if (isLlmMsg) classes += ' msg-llm';

                    let text = (m.text || "").replace(/\n/g, '<br>');

                    const llmBadge = isLlmMsg ? `<span class="msg-llm-badge">🤖 Agente IA</span>` : '';
                    let content = `<div>${llmBadge}${text || '<i>(Mensaje vacío o sin formato)</i>'}</div>`;

                    if (m.type === 'image') {
                        content = `
                            <img src="${m.text}" class="msg-media" onclick="window.open('${m.text}', '_blank')" alt="Imagen">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 5px;">
                                <div style="font-size: 0.8rem; color: var(--text-muted);">📷 Imagen recibida</div>
                                <a href="${m.text}" download target="_blank" style="font-size: 0.75rem; color: var(--primary-dark); text-decoration: underline; cursor: pointer;">Descargar</a>
                            </div>
                        `;
                    } else if (m.type === 'document') {
                        const filename = m.text.split('/').pop();
                        content = `
                            <a href="${m.text}" target="_blank" class="doc-link">
                                <span class="doc-icon">📄</span>
                                <span>${filename}</span>
                            </a>
                            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 4px;">📎 Documento recibido</div>
                        `;
                    }

                    let deleteBtn = '';
                    if (isOut && m.wamid && m.type !== 'deleted') {
                        // DB id is a UUID string, must be quoted
                        deleteBtn = `<button class="delete-msg-btn" title="Eliminar para todos" onclick="deleteMessage('${m.id}', '${m.wamid}')">×</button>`;
                    }

                    html += `
    <div class="${classes}" id="msg-${m.id}">
        ${deleteBtn}
        ${content}
        <div class="msg-meta">${formatTime(m.timestamp)}</div>
    </div>
    `;
                });

                if (historyEl.innerHTML !== html || forceScroll) {
                    historyEl.innerHTML = html;
                    if (forceScroll || isAtBottom) {
                        scrollToBottom();
                    } else {
                        historyEl.scrollTop = oldScrollTop;
                    }
                }

                currentStatus = data.status;
                updateInputState(data.status);

            } catch (err) {
                console.error("Error fetching history:", err);
            }
        }

        function updateInputState(status) {
            const isArchived = currentTab === 'archivadas';
            const isActiveAgent = (status === 'agent' || status === 'agent_silent' || status === 'agent_llm') && !isArchived;

            // Check if another advisor is in this chat
            const otherAdvisorInChat = latestActiveAdvisors.find(a => a.name !== advisorName && a.current_chat === currentActivePhone);

            const msgInput = document.getElementById('msgInput');
            const btnSend = document.getElementById('btnSend');
            const btnUpload = document.getElementById('btnUpload');
            const btnClose = document.getElementById('btnCloseAgent');
            const btnForce = document.getElementById('btnForceAgent');
            const btnBotHumano = document.getElementById('btnBotHumano');
            const btnLLMAgent = document.getElementById('btnLLMAgent');
            const btnHumanTakeover = document.getElementById('btnHumanTakeover');
            const btnLLMRetrigger = document.getElementById('btnLLMRetrigger');
            const btnRestore = document.getElementById('btnRestore');
            const dropdown = document.getElementById('dropdownDelete');
            const ind = document.getElementById('currentStatusIndicator');

            if (otherAdvisorInChat) {
                // Lock the chat
                msgInput.disabled = true;
                btnSend.disabled = true;
                btnUpload.disabled = true;
                btnForce.disabled = true;
                btnBotHumano.disabled = true;
                btnLLMAgent.disabled = true;
                btnHumanTakeover.disabled = true;
                btnLLMRetrigger.disabled = true;
                btnClose.disabled = true;
                dropdown.classList.add('hidden'); // Better to hide it to avoid accidents
                
                ind.className = 'conv-status';
                ind.style.background = '#f59e0b'; // Warning color
                ind.style.color = 'white';
                ind.innerText = `⚠️ OCUPADO POR ${otherAdvisorInChat.name.toUpperCase()}`;
                msgInput.placeholder = `Este chat está siendo atendido por ${otherAdvisorInChat.name}. Espera a que termine.`;
                return;
            }

            msgInput.disabled = !isActiveAgent;
            btnSend.disabled = !isActiveAgent;
            btnUpload.disabled = !isActiveAgent;

            if (isArchived) {
                btnRestore.classList.remove('hidden');
                btnForce.classList.add('hidden');
                btnBotHumano.classList.add('hidden');
                btnClose.classList.add('hidden');
                dropdown.classList.add('hidden');
                ind.className = 'conv-status';
                ind.style.background = '#888';
                ind.style.color = 'white';
                ind.innerText = 'ARCHIVADA';
                document.getElementById('msgInput').placeholder = 'Solo lectura. Restaura la conversación para interactuar.';
            } else if (status === 'agent' || status === 'agent_silent' || status === 'agent_llm') {
                btnRestore.classList.add('hidden');
                btnClose.classList.remove('hidden');
                btnForce.classList.add('hidden');
                btnBotHumano.classList.add('hidden');
                dropdown.classList.remove('hidden');

                if (status === 'agent_llm') {
                    // In LLM mode: hide LLM button, show human takeover + retrigger buttons
                    btnLLMAgent.classList.add('hidden');
                    btnHumanTakeover.classList.remove('hidden');
                    btnLLMRetrigger.classList.remove('hidden');
                    ind.className = 'conv-status status-llm';
                    ind.style = '';
                    ind.innerText = '🤖 AGENTE LLM ACTIVO';
                    msgInput.disabled = false;
                    btnSend.disabled = false;
                    document.getElementById('msgInput').placeholder = 'El Agente LLM está respondiendo. Puedes escribir para intervenir manualmente.';
                } else {
                    // In agent or agent_silent mode: show LLM button, hide takeover + retrigger
                    btnLLMAgent.classList.remove('hidden');
                    btnHumanTakeover.classList.add('hidden');
                    btnLLMRetrigger.classList.add('hidden');

                    if (status === 'agent_silent') {
                        ind.className = 'conv-status status-silent';
                        ind.style = '';
                        ind.innerText = '🔇 MODO BOT HUMANO';
                        document.getElementById('msgInput').placeholder = 'Modo Bot Humano Activo. El cliente no sabrá que eres tú.';
                    } else {
                        ind.className = 'conv-status status-agent';
                        ind.style = '';
                        ind.innerText = '🔴 ESPERANDO ASESOR';
                        document.getElementById('msgInput').placeholder = 'Modo Asesor Activo. Escribe acá tu respuesta...';
                    }
                }
            } else {
                btnRestore.classList.add('hidden');
                btnClose.classList.add('hidden');
                btnForce.classList.remove('hidden');
                btnBotHumano.classList.remove('hidden');
                btnLLMAgent.classList.remove('hidden');
                btnHumanTakeover.classList.add('hidden');
                btnLLMRetrigger.classList.add('hidden');
                dropdown.classList.remove('hidden');
                ind.className = 'conv-status status-bot';
                ind.style = '';
                ind.innerText = 'CONTROLADO POR BOT';
                document.getElementById('msgInput').placeholder = 'Solo puedes escribir si tomas el control.';
            }
        }


        async function handleFileSelected(input) {
            const file = input.files[0];
            if (!file) return;

            const phone = document.getElementById('currentPhone').innerText.replace(/\s+/g, '');
            if (!phone) {
                alert("Por favor selecciona un chat primero.");
                input.value = "";
                return;
            }

            // Show loading or disable buttons
            const btnUpload = document.getElementById('btnUpload');
            const originalContent = btnUpload.innerHTML;
            btnUpload.disabled = true;
            btnUpload.innerHTML = '...';

            try {
                // 1. Upload to server (then to Supabase)
                const formData = new FormData();
                formData.append('file', file);
                formData.append('phone', phone);

                const uploadRes = await fetch('/admin/api/upload-media', {
                    method: 'POST',
                    body: formData
                });

                const uploadData = await uploadRes.json();
                if (!uploadRes.ok) throw new Error(uploadData.error || "Error al subir archivo");

                const mediaUrl = uploadData.url;
                const contentType = uploadData.content_type;
                const filename = uploadData.filename;

                // 2. Determine type (image or document)
                let mediaType = 'document';
                if (contentType.startsWith('image/')) mediaType = 'image';

                // 3. Send via WhatsApp
                const sendRes = await fetch('/admin/api/send-media', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone: phone,
                        url: mediaUrl,
                        type: mediaType,
                        filename: filename
                    })
                });

                const sendData = await sendRes.json();
                if (!sendRes.ok) throw new Error(sendData.error || "Error al enviar mensaje");

                // Success! Refresh history
                fetchHistory(phone);
                input.value = ""; // clear file input
            } catch (err) {
                console.error(err);
                alert("Error: " + err.message);
            } finally {
                btnUpload.disabled = false;
                btnUpload.innerHTML = originalContent;
            }
        }

        async function sendMessage() {
            if (!currentActivePhone) return;
            if (!advisorName) {
                showAdvisorModal(sendMessage);
                return;
            }

            const input = document.getElementById('msgInput');
            const text = input.value.trim();
            if (!text) return;

            input.disabled = true;
            document.getElementById('btnSend').disabled = true;

            const isSilent = currentStatus === 'agent_silent';

            try {
                const res = await fetch('/admin/api/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone: currentActivePhone,
                        text: text,
                        advisor_name: advisorName,
                        silent: isSilent
                    })
                });

                if (res.ok) {
                    input.value = '';
                    input.style.height = '48px';
                    await fetchHistory(currentActivePhone);
                    await fetchList();
                } else {
                    alert('Error al enviar el mensaje');
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión');
            } finally {
                input.disabled = false;
                document.getElementById('btnSend').disabled = false;
                input.focus();
            }
        }

        async function forceAgentSession(silent = false) {
            if (!currentActivePhone) return;
            if (!advisorName) {
                showAdvisorModal(() => forceAgentSession(silent));
                return;
            }

            let msg = silent
                ? '¿Quieres entrar en Modo Bot Humano? Podrás responder sin que el cliente reciba notificación de intervención.'
                : '¿Seguro quieres interrumpir al bot y tomar el control de la conversación? Se enviará un mensaje de bienvenida al cliente.';

            if (!confirm(msg)) return;

            try {
                const res = await fetch(`/admin/api/force-agent/${currentActivePhone}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ advisor_name: advisorName, silent: silent })
                });
                if (res.ok) {
                    await fetchHistory(currentActivePhone);
                    await fetchList();
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function humanTakeover() {
            if (!currentActivePhone) return;
            try {
                const res = await fetch(`/admin/api/human-takeover/${currentActivePhone}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    await fetchHistory(currentActivePhone);
                    await fetchList();
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function llmRetrigger() {
            if (!currentActivePhone) return;
            const btn = document.getElementById('btnLLMRetrigger');
            const original = btn.innerHTML;
            btn.innerHTML = '⌛ Procesando...';
            btn.disabled = true;
            try {
                const res = await fetch(`/admin/api/llm-retrigger/${currentActivePhone}`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (res.ok) {
                    await fetchHistory(currentActivePhone);
                } else {
                    alert('Error: ' + (data.error || 'No se pudo generar respuesta'));
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión');
            } finally {
                btn.innerHTML = original;
                btn.disabled = false;
            }
        }

        async function activateLLMAgent() {
            if (!currentActivePhone) return;
            if (!confirm('¿Activar el Agente LLM para esta conversación? El cliente será atendido por Claude hasta que termines la intervención o el LLM solicite un asesor humano.')) return;

            try {
                const res = await fetch(`/admin/api/set-llm-agent/${currentActivePhone}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    await fetchHistory(currentActivePhone);
                    await fetchList();
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function closeAgentSession() {
            if (!currentActivePhone) return;
            if (!confirm('¿Seguro quieres terminar la intervención y devolver el control al bot?')) return;

            try {
                const res = await fetch(`/admin/api/close-agent/${currentActivePhone}`, {
                    method: 'POST'
                });
                if (res.ok) {
                    await fetchHistory(currentActivePhone);
                    await fetchList();
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function deleteMessage(dbId, wamid) {
            if (!confirm('¿Seguro quieres eliminar este mensaje para todos en WhatsApp? Esta acción es irreversible.')) return;

            try {
                const res = await fetch('/admin/api/delete-message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: dbId, wamid: wamid })
                });

                if (res.ok) {
                    await fetchHistory(currentActivePhone);
                } else {
                    const err = await res.json();
                    alert(err.error || 'Error al eliminar el mensaje');
                }
            } catch (e) {
                console.error(e);
                alert('Error de conexión al intentar eliminar el mensaje');
            }
        }


        async function deleteChat(permanent) {
            if (!currentActivePhone) return;

            const msg = permanent
                ? 'ATENCIÓN: ¿Seguro quieres eliminar este chat de la base de datos permanentemente? No se puede deshacer.'
                : '¿Seguro quieres ocultar este chat de tu panel? Se mantendrá en la base de datos por si lo necesitas.';

            if (!confirm(msg)) return;

            try {
                const res = await fetch(`/admin/api/delete-chat/${currentActivePhone}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ permanent: permanent })
                });

                if (res.ok) {
                    currentActivePhone = null;
                    document.getElementById('emptyState').style.display = 'flex';
                    document.getElementById('mainChat').style.display = 'none';
                    await fetchList();
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function exportConversation() {
            if (!currentActivePhone) return;
            const btn = document.getElementById('btnExport');
            const originalText = btn.innerHTML;

            try {
                btn.innerHTML = '⌛ Generando...';
                btn.disabled = true;

                const res = await fetch(`/admin/api/conversations/${currentActivePhone}`);
                const data = await res.json();

                let content = `========================================================\n`;
                content += `      REPORTE DE CONVERSACIÓN - PROALTO BOT\n`;
                content += `========================================================\n`;
                content += `TELÉFONO: ${currentActivePhone}\n`;
                content += `ESTADO ACTUAL: ${data.status.toUpperCase()}\n`;
                content += `FECHA DE EXPORTACIÓN: ${new Date().toLocaleString()}\n`;
                content += `--------------------------------------------------------\n\n`;

                if (!data.messages || data.messages.length === 0) {
                    content += `(No hay mensajes en esta conversación)\n`;
                } else {
                    data.messages.forEach(m => {
                        const time = new Date(m.timestamp).toLocaleString();
                        const isOut = m.direction === 'outbound';
                        let sender = isOut ? 'BOT/SISTEMA' : 'CLIENTE';

                        if (isOut && (m.text.includes('Asesor ProAlto') || m.text.includes('👨‍💼'))) {
                            sender = 'ASESOR HUMANO';
                        }

                        content += `[${time}] ${sender}:\n`;
                        content += `${m.text}\n`;
                        content += `--------------------------------------------------------\n`;
                    });
                }

                content += `\nFin del reporte.\nGenerado por ProAlto Admin Dashboard.`;

                const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Conversacion_ProAlto_${currentActivePhone}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);

            } catch (err) {
                console.error("Error exporting:", err);
                alert("Hubo un problema al exportar la conversación. Por favor intenta de nuevo.");
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }

        function handleKeyPress(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }

            const target = e.target;
            target.style.height = '48px';
            target.style.height = (target.scrollHeight) + 'px';
        }

        setInterval(async () => {
            if (currentTab === 'activas' || currentTab === 'prospectos' || currentTab === 'renovadoschat' || currentTab === 'anticiposchat') {
                await fetchList();
            } else if (currentTab === 'archivadas') {
                await fetchArchivedList();
            }
            if (currentActivePhone && currentTab !== 'envios') {
                await fetchHistory(currentActivePhone, false);
            }
        }, 5000);

        // Presence Logic
        async function sendHeartbeat() {
            if (!advisorName) return; 
            
            try {
                const res = await fetch('/admin/api/presence', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        advisor_name: advisorName,
                        current_chat: currentActivePhone
                    })
                });
                
                if (res.ok) {
                    const data = await res.json();
                    latestActiveAdvisors = data.active_advisors || [];
                    const listEl = document.getElementById('onlineAdvisorsList');
                    const countEl = document.getElementById('onlineCount');
                    if (latestActiveAdvisors.length > 0) {
                        listEl.innerHTML = latestActiveAdvisors.map(a => {
                            return `<div style="margin-bottom: 4px; padding: 3px 6px; background: rgba(255,255,255,0.05); border-radius: 4px;">
                                🟢 ${a.name === advisorName ? '<b>' + a.name + ' (Tú)</b>' : a.name}
                            </div>`;
                        }).join('');
                        if (countEl) countEl.textContent = `🟢 ${latestActiveAdvisors.length} conectado${latestActiveAdvisors.length > 1 ? 's' : ''}`;
                    } else {
                        listEl.innerHTML = "<em style='opacity:0.6;'>Solo tú</em>";
                        if (countEl) countEl.textContent = '🟢 Solo tú';
                    }

                    // Dynamic update of current view if someone else enters
                    if (currentActivePhone) {
                        updateInputState(currentStatus);
                    }
                }
            } catch (err) {
                console.error("Error sending heartbeat:", err);
            }
        }

        // Send heartbeat every 15 seconds for faster synchronization
        setInterval(sendHeartbeat, 10000);

        // Initial setup
        fetchList();

        // Enforce advisor name on load
        if (!advisorName) {
            showAdvisorModal(() => {
                sendHeartbeat(); // Send first heartbeat immediately after picking name
            });
        } else {
            sendHeartbeat(); // Send first heartbeat if already logged in using localStorage
        }

        // ── Sidebar resize ────────────────────────────────────────────
        (function() {
            const STORAGE_KEY = 'sidebarWidth';
            const MIN = 220, MAX = 520;
            const sidebar = document.querySelector('.sidebar');
            const handle  = document.getElementById('sidebarResizeHandle');

            const saved = parseInt(localStorage.getItem(STORAGE_KEY));
            if (saved && saved >= MIN && saved <= MAX) sidebar.style.width = saved + 'px';

            handle.addEventListener('mousedown', function(e) {
                const startX = e.clientX;
                const startW = sidebar.offsetWidth;
                handle.classList.add('dragging');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';

                function onMove(e) {
                    const w = Math.min(MAX, Math.max(MIN, startW + e.clientX - startX));
                    sidebar.style.width = w + 'px';
                }
                function onUp() {
                    localStorage.setItem(STORAGE_KEY, sidebar.offsetWidth);
                    handle.classList.remove('dragging');
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                }
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
                e.preventDefault();
            });
        })();

        // ══════════════════════════════════════════════════════════════
        // ══  ANALYTICS  ══════════════════════════════════════════════
        // ══════════════════════════════════════════════════════════════

        let chartFunnel = null, chartVolume = null, chartResponse = null, chartTemplates = null;

        function initAnalyticsDates() {
            const today = new Date();
            const toEl = document.getElementById('analyticsTo');
            const fromEl = document.getElementById('analyticsFrom');
            if (toEl && !toEl.value) {
                toEl.value = today.toISOString().slice(0, 10);
                const from = new Date(today);
                from.setDate(from.getDate() - 30);
                fromEl.value = from.toISOString().slice(0, 10);
            }
        }

        function applyDateChip(btn, days) {
            document.querySelectorAll('.date-chip').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            if (days === 0) { toggleCustomRange(btn); return; }
            const custom = document.getElementById('customDateRange');
            if (custom) custom.style.display = 'none';
            const today = new Date();
            let from, to;
            if (days === -1) {
                // Ayer: from = ayer, to = ayer
                const yesterday = new Date(today);
                yesterday.setDate(yesterday.getDate() - 1);
                const y = yesterday.toISOString().slice(0, 10);
                from = y; to = y;
            } else {
                to = today.toISOString().slice(0, 10);
                const fromDate = new Date(today);
                fromDate.setDate(fromDate.getDate() - days);
                from = fromDate.toISOString().slice(0, 10);
            }
            document.getElementById('analyticsFrom').value = from;
            document.getElementById('analyticsTo').value = to;
            fetchAnalytics();
        }

        function toggleCustomRange(btn) {
            const custom = document.getElementById('customDateRange');
            const isHidden = !custom.style.display || custom.style.display === 'none';
            custom.style.display = isHidden ? 'flex' : 'none';
        }

        function getAnalyticsDates() {
            return {
                from: document.getElementById('analyticsFrom').value,
                to: document.getElementById('analyticsTo').value,
            };
        }

        async function fetchAnalytics() {
            const { from, to } = getAnalyticsDates();
            const qs = `from=${from}&to=${to}`;
            try {
                const [funnelRes, volumeRes, responseRes] = await Promise.all([
                    fetch(`/admin/api/analytics/funnel?${qs}`, { credentials: 'same-origin' }),
                    fetch(`/admin/api/analytics/volume?${qs}`, { credentials: 'same-origin' }),
                    fetch(`/admin/api/analytics/response-times?${qs}`, { credentials: 'same-origin' }),
                ]);
                const funnelData = await funnelRes.json();
                const volumeData = await volumeRes.json();
                const responseData = await responseRes.json();

                renderKPICards(volumeData, responseData);
                renderFunnelChart(funnelData.funnel);
                renderVolumeChart(volumeData.daily_breakdown);
                renderResponseChart(responseData);
                renderTemplatesChart(volumeData.templates_sent);

                const now = new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
                const el = document.getElementById('analyticsLastUpdated');
                if (el) el.textContent = `Actualizado a las ${now}`;

                fetchAuditReports();
            } catch (e) {
                console.error('Analytics fetch error:', e);
            }
        }

        function renderKPICards(vol, resp) {
            document.getElementById('kpiTotalChats').textContent = (vol.unique_users || 0).toLocaleString('es-CO');
            document.getElementById('kpiNewUsers').textContent = (vol.new_conversations || 0).toLocaleString('es-CO');
            document.getElementById('kpiEmails').textContent = (vol.emails_captured || 0).toLocaleString('es-CO');
            document.getElementById('kpiDocs').textContent = (vol.documents_received || 0).toLocaleString('es-CO');
            document.getElementById('kpiCuentas').textContent = (vol.cuentas_captured || 0).toLocaleString('es-CO');
            const avgSecs = resp.avg_response_seconds || 0;
            document.getElementById('kpiAvgResponse').textContent = avgSecs > 0 ? formatSeconds(avgSecs) : 'N/A';
        }

        function formatSeconds(s) {
            if (s < 60) return Math.round(s) + 's';
            if (s < 3600) return Math.round(s / 60) + 'min';
            return (s / 3600).toFixed(1) + 'h';
        }

        function renderFunnelChart(funnel) {
            const ctx = document.getElementById('funnelChart').getContext('2d');
            if (chartFunnel) chartFunnel.destroy();

            const buttons = funnel.buttons || [];
            const labels = buttons.map(b => b.label);
            const clicks = buttons.map(b => b.clicks);
            const total = funnel.total_button_clicks || 1;

            const totalEl = document.getElementById('funnelTotal');
            if (totalEl) totalEl.innerHTML = `<strong style="color:#1e293b;">${total.toLocaleString('es-CO')}</strong><br><span>clicks totales</span>`;

            const colors = ['#0891b2', '#059669', '#fec05c', '#ef4444', '#7c3aed', '#3b82f6', '#d97706', '#dc2626'];

            chartFunnel = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Clicks',
                        data: clicks,
                        backgroundColor: buttons.map((_, i) => colors[i % colors.length] + 'cc'),
                        borderColor: buttons.map((_, i) => colors[i % colors.length]),
                        borderWidth: 1.5,
                        borderRadius: 5,
                        borderSkipped: false,
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (tipCtx) => {
                                    const idx = tipCtx.dataIndex;
                                    const pct = ((clicks[idx] / total) * 100).toFixed(1);
                                    const u = buttons[idx]?.unique_users || 0;
                                    return [`${clicks[idx].toLocaleString('es-CO')} clicks (${pct}%)`, `${u} usuarios únicos`];
                                }
                            }
                        }
                    },
                    scales: {
                        x: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 11 }, color: '#94a3b8' } },
                        y: { grid: { display: false }, ticks: { font: { size: 12 }, color: '#374151' } }
                    }
                }
            });
        }

        function renderVolumeChart(daily) {
            const ctx = document.getElementById('volumeChart').getContext('2d');
            if (chartVolume) chartVolume.destroy();

            const labels = (daily || []).map(d => d.date.slice(5));
            const inbound = (daily || []).map(d => d.inbound);
            const outbound = (daily || []).map(d => d.outbound);
            const users = (daily || []).map(d => d.unique_users);

            const totalIn = inbound.reduce((a, b) => a + b, 0);
            const totalOut = outbound.reduce((a, b) => a + b, 0);
            const summaryEl = document.getElementById('volumeSummary');
            if (summaryEl) summaryEl.innerHTML = `<strong style="color:#3b82f6;">${totalIn.toLocaleString('es-CO')}</strong> entrantes<br><strong style="color:#b45309;">${totalOut.toLocaleString('es-CO')}</strong> salientes`;

            const gradIn = ctx.createLinearGradient(0, 0, 0, 280);
            gradIn.addColorStop(0, 'rgba(59,130,246,0.22)');
            gradIn.addColorStop(1, 'rgba(59,130,246,0.02)');

            const gradOut = ctx.createLinearGradient(0, 0, 0, 280);
            gradOut.addColorStop(0, 'rgba(254,192,92,0.22)');
            gradOut.addColorStop(1, 'rgba(254,192,92,0.02)');

            chartVolume = new Chart(ctx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'Entrantes',
                            data: inbound,
                            borderColor: '#3b82f6',
                            backgroundColor: gradIn,
                            fill: true,
                            tension: 0.4,
                            pointRadius: daily && daily.length <= 14 ? 3 : 0,
                            pointHoverRadius: 5,
                            borderWidth: 2,
                        },
                        {
                            label: 'Salientes',
                            data: outbound,
                            borderColor: '#fec05c',
                            backgroundColor: gradOut,
                            fill: true,
                            tension: 0.4,
                            pointRadius: daily && daily.length <= 14 ? 3 : 0,
                            pointHoverRadius: 5,
                            borderWidth: 2,
                        },
                        {
                            label: 'Usuarios',
                            data: users,
                            borderColor: '#059669',
                            backgroundColor: 'transparent',
                            borderDash: [6, 3],
                            fill: false,
                            tension: 0.4,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            borderWidth: 1.5,
                        }
                    ]
                },
                options: {
                    responsive: true,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, padding: 14, font: { size: 11 } } },
                        tooltip: { padding: 10, cornerRadius: 6 }
                    },
                    scales: {
                        x: { grid: { display: false }, ticks: { maxRotation: 0, font: { size: 10 }, color: '#94a3b8' } },
                        y: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 }, color: '#94a3b8' } }
                    }
                }
            });
        }

        function renderResponseChart(data) {
            const ctx = document.getElementById('responseChart').getContext('2d');
            if (chartResponse) chartResponse.destroy();

            chartResponse = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.histogram_labels,
                    datasets: [{
                        label: 'Respuestas',
                        data: data.histogram,
                        backgroundColor: ['#059669cc', '#10b981cc', '#f59e0bcc', '#f97316cc', '#ef4444cc', '#dc2626cc'],
                        borderColor: ['#059669', '#10b981', '#f59e0b', '#f97316', '#ef4444', '#dc2626'],
                        borderWidth: 1.5,
                        borderRadius: 5,
                        borderSkipped: false,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false }, tooltip: { cornerRadius: 6 } },
                    scales: {
                        x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#94a3b8' } },
                        y: { beginAtZero: true, grid: { color: '#f1f5f9' }, ticks: { font: { size: 10 }, color: '#94a3b8' } }
                    }
                }
            });

            const statsEl = document.getElementById('responseStats');
            statsEl.innerHTML = `
                <div class="bi-stat-pill"><div class="bi-stat-pill-label">Promedio</div><div class="bi-stat-pill-value">${formatSeconds(data.avg_response_seconds)}</div></div>
                <div class="bi-stat-pill"><div class="bi-stat-pill-label">Mediana</div><div class="bi-stat-pill-value">${formatSeconds(data.median_response_seconds)}</div></div>
                <div class="bi-stat-pill"><div class="bi-stat-pill-label">P90</div><div class="bi-stat-pill-value">${formatSeconds(data.p90_response_seconds)}</div></div>
                <div class="bi-stat-pill"><div class="bi-stat-pill-label">Sesiones</div><div class="bi-stat-pill-value">${data.total_agent_conversations}</div></div>
            `;
        }

        function renderTemplatesChart(templates) {
            const ctx = document.getElementById('templatesChart').getContext('2d');
            if (chartTemplates) chartTemplates.destroy();

            const values = [
                templates.estado_verde || 0,
                templates.estado_rojo || 0,
                templates.estado_amarillo || 0,
                templates.estado_negados || 0,
            ];
            const templateLabels = ['Aprobados', 'Falta Doc', 'PandaDoc', 'Negados'];
            const colors = ['#22c55e', '#ef4444', '#f59e0b', '#6b7280'];
            const total = values.reduce((a, b) => a + b, 0);

            const totalEl = document.getElementById('templatesTotalNum');
            if (totalEl) totalEl.textContent = total.toLocaleString('es-CO');

            chartTemplates = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: templateLabels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors.map(c => c + 'dd'),
                        borderColor: colors,
                        borderWidth: 2,
                        hoverOffset: 6,
                    }]
                },
                options: {
                    responsive: true,
                    cutout: '68%',
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (tipCtx) => {
                                    const v = tipCtx.raw;
                                    const pct = total > 0 ? ((v / total) * 100).toFixed(1) : 0;
                                    return `${v.toLocaleString('es-CO')} (${pct}%)`;
                                }
                            }
                        }
                    }
                }
            });

            const legend = document.getElementById('templatesLegend');
            if (legend) {
                legend.innerHTML = templateLabels.map((label, i) => `
                    <div style="display: flex; align-items: center; justify-content: space-between; font-size: 0.78rem;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span style="width: 10px; height: 10px; border-radius: 2px; background: ${colors[i]}; flex-shrink: 0;"></span>
                            <span style="color: #374151;">${label}</span>
                        </div>
                        <span style="font-weight: 700; color: #1e293b;">${values[i].toLocaleString('es-CO')}</span>
                    </div>
                `).join('');
            }
        }

        // ── AI Audit ──────────────────────────────────────────────
        let selectedAuditDepth = 'standard';
        let selectedFocusCategories = [];
        const AUDIT_DEPTH_DEFAULTS = {
            quick:    { sample: 5,  hint: 'Análisis rápido de 6 dimensiones. ~5 seg por muestra.' },
            standard: { sample: 10, hint: 'Analiza 6 dimensiones por conversación. ~10 seg por muestra.' },
            deep:     { sample: 8,  hint: 'Análisis exhaustivo de 11 dimensiones con puntuación. ~20 seg por muestra.' },
        };
        const AUDIT_CATEGORIES = [
            { key: 'status_check', label: 'Consulta Estado' },
            { key: 'email_capture', label: 'Captura Email' },
            { key: 'document_upload', label: 'Documentos' },
            { key: 'account_capture', label: 'Captura Cuenta' },
            { key: 'credit_request', label: 'Solicitud Crédito' },
            { key: 'support', label: 'Soporte' },
            { key: 'balance_check', label: 'Consulta Saldo' },
        ];

        function openAuditModal() {
            const { from, to } = getAnalyticsDates();
            document.getElementById('auditDateFrom').value = from;
            document.getElementById('auditDateTo').value = to;
            document.getElementById('auditType').value = 'general';
            document.getElementById('auditAdvisorPicker').classList.add('hidden');
            selectedAuditDepth = 'standard';
            selectedFocusCategories = [];
            document.getElementById('auditSampleSize').value = 10;
            document.getElementById('auditMinMessages').value = 3;
            // Reset depth chips
            document.querySelectorAll('#auditConfigModal .date-chip[data-depth]').forEach(c => {
                c.classList.toggle('active', c.dataset.depth === 'standard');
            });
            document.getElementById('depthHint').textContent = AUDIT_DEPTH_DEFAULTS.standard.hint;
            renderAuditCategoryChips();
            fetchAuditAdvisors(from, to);
            document.getElementById('auditConfigModal').classList.remove('hidden');
        }

        function closeAuditModal() {
            document.getElementById('auditConfigModal').classList.add('hidden');
        }

        function onAuditTypeChange() {
            const type = document.getElementById('auditType').value;
            const picker = document.getElementById('auditAdvisorPicker');
            if (type === 'specific_advisor') {
                picker.classList.remove('hidden');
            } else {
                picker.classList.add('hidden');
            }
        }

        function selectAuditDepth(btn, depth) {
            btn.parentElement.querySelectorAll('.date-chip').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            selectedAuditDepth = depth;
            document.getElementById('auditSampleSize').value = AUDIT_DEPTH_DEFAULTS[depth].sample;
            document.getElementById('depthHint').textContent = AUDIT_DEPTH_DEFAULTS[depth].hint;
        }

        function renderAuditCategoryChips() {
            const container = document.getElementById('auditCategoryChips');
            container.innerHTML = AUDIT_CATEGORIES.map(cat =>
                `<button class="date-chip" data-cat="${cat.key}" onclick="toggleAuditCategory(this,'${cat.key}')"
                 style="font-size:0.72rem; padding:3px 9px; color:#374151; border-color:#d1d5db;">${cat.label}</button>`
            ).join('');
        }

        function toggleAuditCategory(btn, cat) {
            btn.classList.toggle('active');
            if (selectedFocusCategories.includes(cat)) {
                selectedFocusCategories = selectedFocusCategories.filter(c => c !== cat);
            } else {
                selectedFocusCategories.push(cat);
            }
        }

        async function fetchAuditAdvisors(from, to) {
            try {
                const res = await fetch(`/admin/api/analytics/advisors?from=${from}&to=${to}`, { credentials: 'same-origin' });
                const data = await res.json();
                const select = document.getElementById('auditAdvisorName');
                select.innerHTML = '<option value="">-- Seleccionar Asesor --</option>';
                for (const name of (data.advisors || [])) {
                    select.innerHTML += `<option value="${name}">${name}</option>`;
                }
            } catch (e) {
                console.error('Error fetching advisors:', e);
            }
        }

        function toggleSampleAll(cb) {
            const input = document.getElementById('auditSampleSize');
            const note = document.getElementById('auditSampleAllNote');
            if (cb.checked) {
                input.disabled = true;
                input.style.opacity = '0.4';
                note.style.display = 'block';
            } else {
                input.disabled = false;
                input.style.opacity = '1';
                note.style.display = 'none';
            }
        }

        async function executeConfiguredAudit() {
            const auditType = document.getElementById('auditType').value;
            const advisorName = document.getElementById('auditAdvisorName').value;
            const sampleAll = document.getElementById('auditSampleAll').checked;
            const sampleSize = sampleAll ? 0 : (parseInt(document.getElementById('auditSampleSize').value) || 10);
            const minMessages = parseInt(document.getElementById('auditMinMessages').value) || 3;
            const dateFrom = document.getElementById('auditDateFrom').value;
            const dateTo = document.getElementById('auditDateTo').value;

            if (auditType === 'specific_advisor' && !advisorName) {
                alert('Selecciona un asesor para este tipo de auditoría.');
                return;
            }

            closeAuditModal();

            const btn = document.getElementById('btnRunAudit');
            btn.disabled = true;
            btn.textContent = '⏳ Ejecutando...';

            try {
                const res = await fetch('/admin/api/analytics/audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        sample_size: sampleSize,
                        from: dateFrom,
                        to: dateTo,
                        audit_type: auditType,
                        advisor_name: auditType === 'specific_advisor' ? advisorName : null,
                        depth: selectedAuditDepth,
                        min_messages: minMessages,
                        focus_categories: selectedFocusCategories.length > 0 ? selectedFocusCategories : null,
                    }),
                });
                const data = await res.json();
                if (data.audit_id) {
                    pollAudit(data.audit_id);
                }
            } catch (e) {
                console.error('Audit error:', e);
                btn.disabled = false;
                btn.textContent = '🤖 Auditoría AI';
            }
        }

        async function pollAudit(auditId) {
            const btn = document.getElementById('btnRunAudit');
            let attempts = 0;
            const interval = setInterval(async () => {
                attempts++;
                try {
                    const res = await fetch(`/admin/api/analytics/audit/${auditId}`, { credentials: 'same-origin' });
                    const data = await res.json();
                    if (data.status === 'completed' || data.status === 'failed' || attempts > 60) {
                        clearInterval(interval);
                        btn.disabled = false;
                        btn.textContent = '🤖 Auditoría AI';
                        fetchAuditReports();
                    }
                } catch {
                    clearInterval(interval);
                    btn.disabled = false;
                    btn.textContent = '🤖 Auditoría AI';
                }
            }, 5000);
        }

        async function fetchAuditReports() {
            try {
                const res = await fetch('/admin/api/analytics/audits', { credentials: 'same-origin' });
                const audits = await res.json();
                renderAuditList(audits);
            } catch (e) {
                console.error('Fetch audits error:', e);
            }
        }

        const _auditData = {};
        const _auditFilters = {};

        function toggleAuditDetail(auditId, cardEl) {
            const detailDiv = cardEl.querySelector('.audit-detail');
            const arrow = cardEl.querySelector('.audit-arrow-icon');
            if (detailDiv.style.display === 'block') {
                detailDiv.style.display = 'none';
                if (arrow) arrow.style.transform = 'rotate(0deg)';
                cardEl.style.boxShadow = '0 1px 3px rgba(0,0,0,0.06)';
            } else if (_auditData[auditId] !== undefined) {
                detailDiv.style.display = 'block';
                cardEl.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)';
                if (arrow) arrow.style.transform = 'rotate(180deg)';
            } else {
                loadAuditDetail(auditId, cardEl);
            }
        }

        function toggleAuditSection(btnEl, bodyId) {
            const body = document.getElementById(bodyId);
            if (!body) return;
            const isHidden = body.style.display === 'none';
            body.style.display = isHidden ? '' : 'none';
            if (btnEl) btnEl.style.transform = isHidden ? 'rotate(0deg)' : 'rotate(-90deg)';
        }

        function clearAuditFilter(auditId) {
            _auditFilters[auditId] = {};
            _renderAuditConvs(auditId);
            _updateAuditPills(auditId);
            _updateAuditFilterLabel(auditId);
        }

        function filterAuditConvs(auditId, type, value) {
            const cur = _auditFilters[auditId] || {};
            if (cur.type === type && cur.value === value) {
                _auditFilters[auditId] = {};
            } else {
                _auditFilters[auditId] = { type, value };
            }
            _renderAuditConvs(auditId);
            _updateAuditPills(auditId);
            _updateAuditFilterLabel(auditId);
            // Ensure conversations section is open and scroll to it
            const convBodyId = `audit-sec-${auditId}-convs-body`;
            const convBody = document.getElementById(convBodyId);
            if (convBody && convBody.style.display === 'none') {
                convBody.style.display = '';
                const arrow = convBody.previousElementSibling && convBody.previousElementSibling.querySelector('.sec-arrow');
                if (arrow) arrow.style.transform = 'rotate(0deg)';
            }
            const convContainer = document.getElementById(`audit-convs-${auditId}`);
            if (convContainer) {
                setTimeout(() => convContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 60);
            }
        }

        function _updateAuditPills(auditId) {
            const filter = _auditFilters[auditId] || {};
            document.querySelectorAll(`[data-audit-pill="${auditId}"]`).forEach(el => {
                const active = el.dataset.filterType === filter.type && el.dataset.filterValue === filter.value;
                el.style.transform = active ? 'translateY(-2px) scale(1.04)' : '';
                el.style.boxShadow = active ? '0 4px 12px rgba(0,0,0,0.2)' : '';
                el.style.outline = active ? '2px solid currentColor' : '';
                el.style.outlineOffset = active ? '2px' : '';
            });
        }

        function _updateAuditFilterLabel(auditId) {
            const label = document.getElementById(`audit-filter-label-${auditId}`);
            if (!label) return;
            const filter = _auditFilters[auditId] || {};
            if (filter.type && filter.value) {
                const names = { resolved:'Resueltas', unresolved:'No resueltas', partial:'Parciales',
                                positive:'Positivo', neutral:'Neutral', negative:'Negativo',
                                baja:'Complejidad baja', media:'Complejidad media', alta:'Complejidad alta',
                                rapido:'Velocidad rápida', normal:'Velocidad normal', lento:'Velocidad lenta',
                                'true':'Protocolo: Sí', 'false':'Protocolo: No' };
                const vl = names[filter.value] || filter.value;
                label.innerHTML = `<span style="font-size:0.72rem; color:#0369a1; background:#e0f2fe; padding:3px 10px; border-radius:999px; display:inline-flex; align-items:center; gap:6px;">
                    Filtro activo: <strong>${vl}</strong>
                    <button onclick="clearAuditFilter('${auditId}')" style="background:none;border:none;color:#0369a1;cursor:pointer;font-size:0.82rem;padding:0;font-weight:700;" title="Quitar filtro">✕</button>
                </span>`;
                label.style.display = 'block';
            } else {
                label.style.display = 'none';
            }
        }

        function _renderAuditConvs(auditId) {
            const container = document.getElementById(`audit-convs-${auditId}`);
            if (!container) return;
            const allData = _auditData[auditId] || [];
            const filter = _auditFilters[auditId] || {};
            const results = (filter.type && filter.value)
                ? allData.filter(r => String(r[filter.type]) === String(filter.value))
                : allData;
            const resLabel = { resolved:'Resuelta', unresolved:'No resuelta', partial:'Parcial', error:'Error' };
            const resColor = { resolved:'#22c55e', unresolved:'#ef4444', partial:'#f59e0b', error:'#94a3b8' };
            const sentIcon  = { positive:'😊', neutral:'😐', negative:'😞' };
            if (!results.length) {
                container.innerHTML = `<div style="padding:14px; text-align:center; color:#94a3b8; font-size:0.8rem;">Sin conversaciones para este filtro.</div>`;
                return;
            }
            container.innerHTML = results.map(r => {
                const rc = resColor[r.resolucion] || '#94a3b8';
                const rl = resLabel[r.resolucion] || r.resolucion;
                const si = sentIcon[r.sentimiento] || '😐';
                const advisorTag = r.has_advisor && r.advisor_names && r.advisor_names.length
                    ? `<span style="background:#ede9fe;color:#7c3aed;padding:1px 6px;border-radius:999px;font-size:0.68rem;font-weight:600;">Asesor: ${r.advisor_names[0]}</span>` : '';
                const scoreTag = typeof r.puntuacion === 'number'
                    ? `<span style="background:${r.puntuacion>=7?'#dcfce7':r.puntuacion>=4?'#fef3c7':'#fee2e2'};color:${r.puntuacion>=7?'#16a34a':r.puntuacion>=4?'#d97706':'#dc2626'};padding:1px 6px;border-radius:999px;font-size:0.68rem;font-weight:700;">${r.puntuacion}/10</span>` : '';
                return `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 10px;border-bottom:1px solid var(--border);font-size:0.78rem;gap:8px;transition:background 0.1s;" onmouseover="this.style.background='#f0f9ff'" onmouseout="this.style.background=''">
                    <div style="min-width:0;flex:1;display:flex;flex-wrap:wrap;align-items:center;gap:4px;">
                        <span style="font-weight:600;">${r.client_name||'Cliente'}</span>
                        <span style="color:#94a3b8;">${r.message_count} msgs</span>
                        <span style="background:${rc}22;color:${rc};padding:1px 6px;border-radius:999px;font-size:0.68rem;font-weight:600;">${rl}</span>
                        <span>${si}</span>${scoreTag}${advisorTag}
                    </div>
                    <button onclick="goToChat('${r.phone}')" style="flex-shrink:0;padding:3px 10px;font-size:0.72rem;background:#eff6ff;border:1px solid #3b82f6;color:#1d4ed8;border-radius:4px;cursor:pointer;white-space:nowrap;">Ver chat →</button>
                </div>`;
            }).join('');
        }

        function renderAuditList(audits) {
            const container = document.getElementById('auditReportsList');
            if (!audits || audits.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted);">No hay auditorías aún. Haz clic en "Auditoría AI" para generar una.</p>';
                return;
            }
            const typeLabels = { general: 'General', bot_only: 'Solo Bot', advisor_only: 'Con Asesor', specific_advisor: 'Por Asesor' };
            const depthLabels = { quick: 'Rápida', standard: 'Estándar', deep: 'Profunda' };
            let html = '';
            for (const a of audits) {
                const date = new Date(a.created_at).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                const statusBadge = a.status === 'completed'
                    ? '<span style="background:#22c55e;color:white;padding:2px 9px;border-radius:999px;font-size:0.7rem;font-weight:600;">Completado</span>'
                    : a.status === 'running'
                    ? '<span style="background:#f59e0b;color:white;padding:2px 9px;border-radius:999px;font-size:0.7rem;font-weight:600;">En proceso...</span>'
                    : '<span style="background:#ef4444;color:white;padding:2px 9px;border-radius:999px;font-size:0.7rem;font-weight:600;">Error</span>';
                const cfg = a.config || {};
                const typeLabel = cfg.audit_type === 'specific_advisor' && cfg.advisor_name
                    ? `Asesor: ${cfg.advisor_name}` : (typeLabels[cfg.audit_type] || 'General');
                const depthLabel = depthLabels[cfg.depth] || '';
                const typeBadge = `<span style="background:#ede9fe;color:#7c3aed;padding:2px 8px;border-radius:999px;font-size:0.68rem;font-weight:600;">${typeLabel}</span>`;
                const depthBadge = depthLabel ? `<span style="background:#e0f2fe;color:#0369a1;padding:2px 8px;border-radius:999px;font-size:0.68rem;font-weight:600;">${depthLabel}</span>` : '';
                html += `
                    <div id="audit-card-${a.id}" style="border:1px solid var(--border);border-radius:10px;margin-bottom:10px;background:white;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06);transition:box-shadow 0.2s;">
                        <div style="padding:12px 14px;cursor:pointer;user-select:none;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;transition:background 0.15s;"
                             onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background=''"
                             onclick="toggleAuditDetail('${a.id}', this.parentElement)">
                            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                                <strong style="font-size:0.85rem;">${date}</strong>
                                ${typeBadge}${depthBadge}
                                <span style="color:var(--text-muted);font-size:0.8rem;">${a.date_from} → ${a.date_to} · ${a.sample_size === 0 ? 'Todas las conv.' : a.sample_size + ' conv.'}</span>
                            </div>
                            <div style="display:flex;align-items:center;gap:8px;">
                                ${statusBadge}
                                <span class="audit-arrow-icon" style="color:#94a3b8;font-size:0.85rem;transition:transform 0.25s;display:inline-block;">▾</span>
                            </div>
                        </div>
                        <div class="audit-detail" style="display:none;border-top:1px solid var(--border);" onclick="event.stopPropagation()"></div>
                    </div>`;
            }
            container.innerHTML = html;
        }

        async function loadAuditDetail(auditId, cardEl) {
            const detailDiv = cardEl.querySelector('.audit-detail');
            const arrow = cardEl.querySelector('.audit-arrow-icon');
            detailDiv.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:0.85rem;">Cargando...</div>';
            detailDiv.style.display = 'block';
            cardEl.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)';
            if (arrow) arrow.style.transform = 'rotate(180deg)';
            try {
                const res = await fetch(`/admin/api/analytics/audit/${auditId}`, { credentials: 'same-origin' });
                const data = await res.json();
                if (data.status === 'running') {
                    detailDiv.innerHTML = '<div style="padding:16px;text-align:center;color:#f59e0b;font-size:0.85rem;">Auditoría en proceso, intenta de nuevo en unos segundos...</div>';
                    return;
                }
                if (data.status === 'failed') {
                    detailDiv.innerHTML = `<div style="padding:16px;color:#ef4444;font-size:0.85rem;">Error: ${data.error || 'desconocido'}</div>`;
                    return;
                }
                const report = data.report;
                if (!report || !report.summary) {
                    detailDiv.innerHTML = '<div style="padding:16px;color:var(--text-muted);font-size:0.85rem;">Sin datos.</div>';
                    return;
                }

                _auditData[auditId] = report.individual_results || [];
                _auditFilters[auditId] = {};

                const s = report.summary;
                const resCounts = s.resolucion || {};
                const sent = s.sentimiento || {};
                const dm = report.deep_metrics;

                // Collapsible section builder
                const sId = (n) => `audit-sec-${auditId}-${n}`;
                const collapsible = (id, title, color, bg, content) => `
                    <div style="border-radius:8px;border:1px solid ${color}33;overflow:hidden;margin-bottom:10px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 12px;background:${bg};cursor:pointer;user-select:none;transition:filter 0.15s;"
                             onmouseover="this.style.filter='brightness(0.96)'" onmouseout="this.style.filter=''"
                             onclick="toggleAuditSection(this.querySelector('.sec-arrow'),'${id}-body')">
                            <span style="font-size:0.8rem;font-weight:700;color:${color};">${title}</span>
                            <span class="sec-arrow" style="color:${color};font-size:0.75rem;transition:transform 0.2s;display:inline-block;">▾</span>
                        </div>
                        <div id="${id}-body" style="padding:10px 12px;background:white;">${content}</div>
                    </div>`;

                // Filterable stat pill
                const makePill = (label, value, count, color, ftype) =>
                    `<div class="bi-stat-pill" data-audit-pill="${auditId}" data-filter-type="${ftype}" data-filter-value="${value}"
                          style="border-left:3px solid ${color};cursor:pointer;transition:transform 0.15s,box-shadow 0.15s,outline 0.1s;"
                          onclick="filterAuditConvs('${auditId}','${ftype}','${value}')" title="Filtrar: ${label}">
                        <div class="bi-stat-pill-label">${label}</div>
                        <div class="bi-stat-pill-value" style="color:${color};">${count}</div>
                    </div>`;

                let html = `<div style="padding:14px;">
                    <div id="audit-filter-label-${auditId}" style="display:none;margin-bottom:10px;"></div>`;

                // Stat pills (filterable)
                html += `<div style="display:grid;grid-template-columns:repeat(3,1fr) 2px repeat(3,1fr);gap:8px;margin-bottom:14px;align-items:stretch;">`;
                html += makePill('Resueltas',    'resolved',   resCounts.resolved   || 0, '#22c55e', 'resolucion');
                html += makePill('Parciales',    'partial',    resCounts.partial    || 0, '#f59e0b', 'resolucion');
                html += makePill('No Resueltas', 'unresolved', resCounts.unresolved || 0, '#ef4444', 'resolucion');
                html += `<div style="background:var(--border);width:2px;align-self:stretch;border-radius:1px;"></div>`;
                html += makePill('😊 Positivo', 'positive', sent.positive || 0, '#22c55e', 'sentimiento');
                html += makePill('😐 Neutral',  'neutral',  sent.neutral  || 0, '#64748b', 'sentimiento');
                html += makePill('😞 Negativo', 'negative', sent.negative || 0, '#ef4444', 'sentimiento');
                html += `</div>`;

                // Deep metrics row
                if (dm && dm.avg_puntuacion != null) {
                    const sc = dm.avg_puntuacion;
                    const sc_c = sc >= 7 ? '#22c55e' : sc >= 4 ? '#f59e0b' : '#ef4444';
                    const proto = dm.cumplimiento_protocolo || {};
                    const pTotal = (proto.si||0) + (proto.no||0);
                    const pPct = pTotal > 0 ? Math.round(((proto.si||0)/pTotal)*100) : 0;
                    const p_c = pPct >= 80 ? '#22c55e' : pPct >= 50 ? '#f59e0b' : '#ef4444';
                    const comp = dm.complejidad || {};
                    const tiempo = dm.tiempo_resolucion || {};
                    const fChip = (aid, ftype, fval, lbl, count, bg, color) =>
                        `<span data-audit-pill="${aid}" data-filter-type="${ftype}" data-filter-value="${fval}"
                               onclick="filterAuditConvs('${aid}','${ftype}','${fval}')"
                               style="background:${bg};color:${color};padding:1px 7px;border-radius:999px;font-size:0.7rem;font-weight:600;cursor:pointer;transition:transform 0.12s,outline 0.1s;"
                               title="Filtrar: ${lbl}">${lbl} ${count}</span>`;
                    html += `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px;">`;
                    html += `<div class="bi-stat-pill" style="border-left:3px solid ${sc_c};"><div class="bi-stat-pill-label">Puntuación prom.</div><div class="bi-stat-pill-value" style="color:${sc_c};">${sc}/10</div></div>`;
                    html += `<div class="bi-stat-pill" style="border-left:3px solid ${p_c};">
                        <div class="bi-stat-pill-label">Protocolo</div>
                        <div style="display:flex;gap:4px;margin-top:3px;flex-wrap:wrap;">
                            ${fChip(auditId,'cumplimiento_protocolo','true','Sí',proto.si||0,'#dcfce7','#16a34a')}
                            ${fChip(auditId,'cumplimiento_protocolo','false','No',proto.no||0,'#fee2e2','#dc2626')}
                        </div></div>`;
                    html += `<div class="bi-stat-pill">
                        <div class="bi-stat-pill-label">Complejidad</div>
                        <div style="display:flex;gap:4px;margin-top:3px;flex-wrap:wrap;">
                            ${fChip(auditId,'complejidad','baja','B',comp.baja||0,'#dcfce7','#16a34a')}
                            ${fChip(auditId,'complejidad','media','M',comp.media||0,'#fef3c7','#d97706')}
                            ${fChip(auditId,'complejidad','alta','A',comp.alta||0,'#fee2e2','#dc2626')}
                        </div></div>`;
                    html += `<div class="bi-stat-pill">
                        <div class="bi-stat-pill-label">Velocidad</div>
                        <div style="display:flex;gap:4px;margin-top:3px;flex-wrap:wrap;">
                            ${fChip(auditId,'tiempo_resolucion_estimado','rapido','R',tiempo.rapido||0,'#dcfce7','#16a34a')}
                            ${fChip(auditId,'tiempo_resolucion_estimado','normal','N',tiempo.normal||0,'#f1f5f9','#64748b')}
                            ${fChip(auditId,'tiempo_resolucion_estimado','lento','L',tiempo.lento||0,'#fee2e2','#dc2626')}
                        </div></div>`;
                    html += `</div>`;
                }

                // Category chips (filterable)
                if (s.categoria) {
                    const cats = Object.entries(s.categoria).sort((a,b) => b[1]-a[1]);
                    const catTotal = cats.reduce((sum,[,v]) => sum+v, 0);
                    html += `<div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:14px;">`;
                    for (const [k,v] of cats) {
                        const pct = catTotal > 0 ? Math.round((v/catTotal)*100) : 0;
                        html += `<span data-audit-pill="${auditId}" data-filter-type="categoria" data-filter-value="${k}"
                                      onclick="filterAuditConvs('${auditId}','categoria','${k}')"
                                      style="background:#e0f2fe;color:#0369a1;padding:3px 10px;border-radius:999px;font-size:0.72rem;font-weight:600;cursor:pointer;transition:transform 0.15s,box-shadow 0.15s;"
                                      onmouseover="this.style.background='#bae6fd'" onmouseout="this.style.background='#e0f2fe'"
                                      >${k}: ${v} (${pct}%)</span>`;
                    }
                    html += `</div>`;
                }

                // List items helper
                const listItems = (items, color) => (items||[]).slice(0,5).map(f => `
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:0.8rem;">
                        <span style="color:#374151;line-height:1.4;">${f.text}</span>
                        <span style="background:${color}22;color:${color};padding:1px 8px;border-radius:999px;font-weight:700;font-size:0.7rem;white-space:nowrap;flex-shrink:0;">${f.count}x</span>
                    </div>`).join('');

                if (report.top_friction_points && report.top_friction_points.length)
                    html += collapsible(sId('friction'), `⚠️ Puntos de Fricción (${report.top_friction_points.length})`, '#dc2626', '#fff5f5', listItems(report.top_friction_points, '#dc2626'));
                if (report.top_improvements && report.top_improvements.length)
                    html += collapsible(sId('improve'), `💡 Oportunidades de Mejora (${report.top_improvements.length})`, '#059669', '#f0fdf4', listItems(report.top_improvements, '#059669'));
                if (report.notable_findings && report.notable_findings.length)
                    html += collapsible(sId('notable'), `✨ Hallazgos Notables (${report.notable_findings.length})`, '#7c3aed', '#faf5ff',
                        report.notable_findings.map(n => `<div style="font-size:0.8rem;color:#374151;padding:5px 0;border-bottom:1px solid #f3e8ff;line-height:1.4;">· ${n}</div>`).join(''));

                // Deep: individual analyses (sorted worst first)
                if (dm) {
                    const analyses = (_auditData[auditId]||[]).filter(r => r.detalle_analisis).sort((a,b) => (a.puntuacion??99)-(b.puntuacion??99));
                    if (analyses.length > 0) {
                        const analysisContent = analyses.map(r => {
                            const sb = typeof r.puntuacion === 'number'
                                ? `<span style="background:${r.puntuacion>=7?'#dcfce7':r.puntuacion>=4?'#fef3c7':'#fee2e2'};color:${r.puntuacion>=7?'#16a34a':r.puntuacion>=4?'#d97706':'#dc2626'};padding:1px 7px;border-radius:999px;font-size:0.7rem;font-weight:700;">${r.puntuacion}/10</span>` : '';
                            return `<div style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:0.78rem;background:#fafafa;">
                                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
                                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                                        <strong>${r.client_name||'Cliente'}</strong>
                                        <button onclick="goToChat('${r.phone}')" style="padding:2px 9px;font-size:0.7rem;background:#eff6ff;border:1px solid #3b82f6;color:#1d4ed8;border-radius:4px;cursor:pointer;white-space:nowrap;">Ver chat →</button>
                                    </div>${sb}
                                </div>
                                <div style="color:#64748b;line-height:1.5;">${r.detalle_analisis}</div>
                            </div>`;
                        }).join('');
                        html += collapsible(sId('analyses'), `🔍 Análisis Detallados (${analyses.length})`, '#0891b2', '#f0f9ff', analysisContent);
                    }
                }

                // Conversations list (filterable, all audit types)
                if (_auditData[auditId].length > 0) {
                    const convContent = `<div id="audit-convs-${auditId}" style="border-radius:6px;overflow:hidden;border:1px solid var(--border);"></div>`;
                    html += collapsible(sId('convs'), `📋 Conversaciones Analizadas (${_auditData[auditId].length})`, '#374151', '#f8fafc', convContent);
                }

                html += `</div>`;
                detailDiv.innerHTML = html;
                if (_auditData[auditId].length > 0) _renderAuditConvs(auditId);

            } catch (e) {
                detailDiv.innerHTML = `<div style="padding:16px;color:#ef4444;font-size:0.85rem;">Error: ${e.message}</div>`;
                if (arrow) arrow.style.transform = 'rotate(0deg)';
                cardEl.style.boxShadow = '0 1px 3px rgba(0,0,0,0.06)';
            }
        }
