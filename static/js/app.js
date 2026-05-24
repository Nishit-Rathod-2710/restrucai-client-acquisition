// ── Constants (single source of truth, loaded from backend on init) ──────────
let CALL_STATUSES = [
    'Need to Call',
    'Called NIL',
    'Not Answered',
    'Interested',
    'Follow-Up',
];

const STATUS_COLORS = {
    'Need to Call': '#8f95b2',
    'Called NIL':   '#ff4d4f',
    'Not Answered': '#ffbd2e',
    'Interested':   '#00e676',
    'Follow-Up':    '#C8F135',
};

// ── App ───────────────────────────────────────────────────────────────────────
const app = {
    state: {
        campaigns: [],
        activeCampaignId: null,
        activeCampaignData: null,
        pollingInterval: null,
        enrichPollInterval: null,
        realtimeChannel: null,
        supabase: null,
    },

    // ── Init ──────────────────────────────────────────────────────────────────

    async init() {
        // Load config (statuses + supabase creds) from backend
        try {
            const res = await fetch('/api/config');
            if (res.ok) {
                const cfg = await res.json();
                if (cfg.call_statuses?.length) CALL_STATUSES = cfg.call_statuses;
                if (cfg.supabase_url && cfg.supabase_key) {
                    this.state.supabase = supabase.createClient(cfg.supabase_url, cfg.supabase_key);
                    this._startRealtime();
                }
            }
        } catch (e) {
            console.warn('Config load failed, using defaults', e);
        }
        await this.fetchCampaigns();
    },

    // ── Supabase Realtime ─────────────────────────────────────────────────────

    _startRealtime() {
        const sb = this.state.supabase;
        if (!sb) return;

        this.state.realtimeChannel = sb
            .channel('leads-realtime')
            .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'leads' }, (payload) => {
                this._onLeadUpdate(payload.new);
            })
            .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'leads' }, (payload) => {
                this._onLeadInsert(payload.new);
            })
            .subscribe((status) => {
                const dot = document.getElementById('realtime-indicator');
                if (!dot) return;
                if (status === 'SUBSCRIBED') {
                    dot.className = 'realtime-dot connected';
                    dot.title = 'Realtime: connected';
                } else {
                    dot.className = 'realtime-dot disconnected';
                    dot.title = `Realtime: ${status}`;
                }
            });
    },

    _onLeadUpdate(updated) {
        const data = this.state.activeCampaignData;
        if (!data || updated.campaign_id !== this.state.activeCampaignId) {
            // Refresh sidebar pill counts for the right campaign
            this.fetchCampaigns();
            return;
        }

        // Update local state
        const lead = data.leads.find(l => l.id === updated.id);
        if (!lead) return;
        Object.assign(lead, updated);

        // Re-render only the affected cells — no full table rebuild
        this.renderStatusCell(updated.id, updated.call_status || 'Need to Call');
        this.renderNotesCell(updated.id, updated.notes || '');
        this.renderEmailCell(updated.id, updated.email || '');

        // Refresh sidebar status pills
        this._refreshSidebarPills(this.state.activeCampaignId, data.leads);
    },

    _onLeadInsert(newLead) {
        const data = this.state.activeCampaignData;
        if (!data || newLead.campaign_id !== this.state.activeCampaignId) {
            this.fetchCampaigns();
            return;
        }
        // Full re-fetch so new row appears correctly
        this.fetchCampaignDetails(this.state.activeCampaignId);
        this.fetchCampaigns();
    },

    _refreshSidebarPills(campaignId, leads) {
        const summary = {};
        leads.forEach(l => {
            const s = l.call_status || 'Need to Call';
            summary[s] = (summary[s] || 0) + 1;
        });
        const camp = this.state.campaigns.find(c => c.id === campaignId);
        if (camp) {
            camp.status_summary = summary;
            this.renderSidebar();
        }
    },

    // ── Auth ──────────────────────────────────────────────────────────────────

    async logout() {
        if (this.state.realtimeChannel && this.state.supabase) {
            await this.state.supabase.removeChannel(this.state.realtimeChannel);
        }
        await fetch('/api/auth/logout', { method: 'POST' });
        window.location.href = '/login';
    },

    // ── Navigation ────────────────────────────────────────────────────────────

    showNewSearch() {
        this.state.activeCampaignId = null;
        document.getElementById('view-campaign').classList.remove('active');
        document.getElementById('view-new-search').classList.add('active');
        this.renderSidebar();
        setTimeout(() => document.getElementById('nl-input').focus(), 100);
    },

    async showCampaign(id) {
        this.state.activeCampaignId = id;
        document.getElementById('view-new-search').classList.remove('active');
        document.getElementById('view-campaign').classList.add('active');
        this.renderSidebar();
        await this.fetchCampaignDetails(id);
    },

    // ── API ───────────────────────────────────────────────────────────────────

    async fetchCampaigns() {
        try {
            const res = await fetch('/api/campaigns');
            if (res.status === 401) { window.location.href = '/login'; return; }
            const data = await res.json();
            this.state.campaigns = data.campaigns;
            this.renderSidebar();
            const running = this.state.campaigns.filter(c => c.status === 'running');
            if (running.length > 0 && !this.state.pollingInterval) this.startPolling();
        } catch (err) {
            console.error('Failed to fetch campaigns', err);
        }
    },

    async runSearch() {
        const input = document.getElementById('nl-input').value.trim();
        if (!input) return;

        const btn = document.getElementById('run-btn');
        btn.disabled = true;
        btn.innerHTML = '[ EXECUTING... ]';

        const toast = document.getElementById('status-toast');
        const statusText = document.getElementById('status-text');
        toast.classList.remove('hidden');
        statusText.innerText = 'Parsing intent & initiating extraction...';

        try {
            const res = await fetch('/api/campaigns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ requirement: input }),
            });
            const data = await res.json();
            if (data.success) {
                statusText.innerText = 'Directive parsed. Extractor active.';
                document.getElementById('nl-input').value = '';
                await this.fetchCampaigns();
                this.showCampaign(data.campaign_id);
                this.startPolling();
            } else {
                toast.classList.add('hidden');
                alert(data.error || 'Failed to start query');
            }
        } catch (err) {
            console.error('Failed to run search', err);
            toast.classList.add('hidden');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '[ EXECUTE ]';
            setTimeout(() => toast.classList.add('hidden'), 5000);
        }
    },

    async fetchCampaignDetails(id) {
        try {
            const res = await fetch(`/api/campaigns/${id}/leads`);
            const data = await res.json();
            if (data.campaign) {
                this.state.activeCampaignData = data;
                this.renderCampaignData();
            }
        } catch (err) {
            console.error('Failed to fetch campaign details', err);
        }
    },

    async deleteCampaign() {
        if (!this.state.activeCampaignId) return;
        if (!confirm('Are you sure you want to purge this dataset?')) return;
        try {
            await fetch(`/api/campaigns/${this.state.activeCampaignId}`, { method: 'DELETE' });
            this.state.activeCampaignId = null;
            this.state.activeCampaignData = null;
            await this.fetchCampaigns();
            this.showNewSearch();
        } catch (err) {
            console.error('Failed to delete campaign', err);
        }
    },

    exportCsv() {
        if (!this.state.activeCampaignId) return;
        window.location.href = `/api/campaigns/${this.state.activeCampaignId}/export`;
    },

    // ── Enrichment ────────────────────────────────────────────────────────────

    async startEnrichment() {
        const cid = this.state.activeCampaignId;
        if (!cid) return;

        const btn = document.getElementById('enrich-btn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spin-icon">⟳</span> ENRICHING...';

        try {
            const res = await fetch(`/api/campaigns/${cid}/enrich`, { method: 'POST' });
            const data = await res.json();

            if (res.status === 409) {
                alert('Enrichment already running for this campaign.');
                btn.disabled = false;
                btn.innerHTML = '<i data-lucide="zap"></i> FIND EMAILS';
                lucide.createIcons();
                return;
            }
            if (data.total === 0) {
                alert(data.message || 'No leads need enrichment.');
                btn.disabled = false;
                btn.innerHTML = '<i data-lucide="zap"></i> FIND EMAILS';
                lucide.createIcons();
                return;
            }
            document.getElementById('enrich-progress-bar').classList.remove('hidden');
            this.pollEnrichment(cid);
        } catch (e) {
            console.error('Failed to start enrichment', e);
            btn.disabled = false;
        }
    },

    pollEnrichment(cid) {
        if (this.state.enrichPollInterval) clearInterval(this.state.enrichPollInterval);
        this.state.enrichPollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/campaigns/${cid}/enrich/status`);
                const job = await res.json();
                const { status, processed, found, total } = job;
                const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

                document.getElementById('enrich-bar-fill').style.width = pct + '%';
                document.getElementById('enrich-counter').innerText =
                    `${processed} / ${total} processed  •  ${found} found`;

                if (status === 'done') {
                    this.stopEnrichmentPoll();
                    await this.fetchCampaignDetails(cid);
                    const btn = document.getElementById('enrich-btn');
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = '<i data-lucide="zap"></i> FIND EMAILS';
                        lucide.createIcons();
                    }
                    setTimeout(() => {
                        const bar = document.getElementById('enrich-progress-bar');
                        if (bar) bar.classList.add('hidden');
                        document.getElementById('enrich-bar-fill').style.width = '0%';
                    }, 3000);
                }
            } catch (e) {
                console.error('Enrichment poll error', e);
            }
        }, 2000);
    },

    stopEnrichmentPoll() {
        if (this.state.enrichPollInterval) {
            clearInterval(this.state.enrichPollInterval);
            this.state.enrichPollInterval = null;
        }
    },

    // ── Campaign scrape polling (for running campaigns) ────────────────────────

    startPolling() {
        if (this.state.pollingInterval) clearInterval(this.state.pollingInterval);
        this.state.pollingInterval = setInterval(async () => {
            let hasRunning = false;
            for (const camp of this.state.campaigns) {
                if (camp.status === 'running') {
                    hasRunning = true;
                    try {
                        const res = await fetch(`/api/campaigns/${camp.id}/status`);
                        const stat = await res.json();
                        if (stat.status !== 'running') {
                            await this.fetchCampaigns();
                            if (this.state.activeCampaignId === camp.id) {
                                await this.fetchCampaignDetails(camp.id);
                            }
                        } else if (this.state.activeCampaignId === camp.id && this.state.activeCampaignData) {
                            if (stat.leads_count > this.state.activeCampaignData.leads.length) {
                                await this.fetchCampaignDetails(camp.id);
                            }
                        }
                    } catch (e) { console.error('Poll err', e); }
                }
            }
            if (!hasRunning) {
                clearInterval(this.state.pollingInterval);
                this.state.pollingInterval = null;
            }
        }, 5000);
    },

    // ── Rendering ─────────────────────────────────────────────────────────────

    renderSidebar() {
        const list = document.getElementById('campaign-list');
        list.innerHTML = '';

        this.state.campaigns.forEach(c => {
            const div = document.createElement('div');
            div.className = `campaign-item ${this.state.activeCampaignId === c.id ? 'active' : ''}`;
            div.onclick = () => this.showCampaign(c.id);

            const date = c.created_at
                ? new Date(c.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
                : '';

            const summary = c.status_summary || {};
            const pillsHtml = Object.entries(summary)
                .filter(([, count]) => count > 0)
                .map(([status, count]) => {
                    const color = STATUS_COLORS[status] || '#8f95b2';
                    return `<span class="sidebar-status-pill" style="color:${color};border-color:${color}40;">${count} ${status}</span>`;
                }).join('');

            div.innerHTML = `
                <div class="camp-item-title">${c.name}</div>
                <div class="camp-item-date">
                    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                    ${date}
                </div>
                <div class="camp-item-meta">
                    <span style="display:flex;align-items:center;gap:4px;">
                        <span class="status-dot ${c.status}"></span>
                        ${c.status.toUpperCase()}
                    </span>
                    <span>${c.lead_count} leads</span>
                </div>
                ${pillsHtml ? `<div class="camp-item-pills">${pillsHtml}</div>` : ''}`;
            list.appendChild(div);
        });
    },

    renderCampaignData() {
        const data = this.state.activeCampaignData;
        if (!data || !data.campaign) return;

        const c = data.campaign;
        const leads = data.leads || [];

        document.getElementById('camp-title').innerText = c.name;
        document.getElementById('camp-query').innerText = c.search_query;
        document.getElementById('camp-loc').innerText = c.location || 'Global';

        const sc = document.getElementById('camp-status');
        sc.innerText = c.status.toUpperCase();
        sc.className = `badge ${c.status}`;

        document.getElementById('stat-total').innerText = leads.length;

        let totalRating = 0, withWeb = 0, withEmail = 0, ratedCount = 0;
        leads.forEach(l => {
            if (l.rating > 0) { totalRating += l.rating; ratedCount++; }
            if (l.website) withWeb++;
            if (l.email) withEmail++;
        });

        document.getElementById('stat-rating').innerText = ratedCount ? (totalRating / ratedCount).toFixed(1) : '0.0';
        document.getElementById('stat-website').innerText = leads.length ? Math.round((withWeb / leads.length) * 100) + '%' : '0%';
        document.getElementById('stat-email').innerText = leads.length ? Math.round((withEmail / leads.length) * 100) + '%' : '0%';

        const tbody = document.getElementById('leads-tbody');
        tbody.innerHTML = '';

        leads.forEach(l => {
            const tr = document.createElement('tr');
            tr.id = `lead-row-${l.id}`;
            tr.onclick = (e) => {
                if (!e.target.closest('.email-cell') &&
                    !e.target.closest('.status-cell') &&
                    !e.target.closest('.notes-cell')) {
                    this.showLeadDetail(l);
                }
            };

            const hasPhone = l.phone && l.phone !== '-';
            tr.innerHTML = `
                <td>${l.name || '-'}</td>
                <td>${l.category || '-'}</td>
                <td class="rating">${l.rating > 0 ? l.rating.toFixed(1) : '-'}</td>
                <td>${l.reviews || 0}</td>
                <td class="phone-cell">${hasPhone
                    ? `<a href="tel:${l.phone}" onclick="event.stopPropagation()" class="phone-link">${l.phone}</a>`
                    : '-'}</td>
                <td class="email-cell" id="email-cell-${l.id}"></td>
                <td>${l.website
                    ? `<a href="${l.website}" target="_blank" onclick="event.stopPropagation()">Link</a>`
                    : '-'}</td>
                <td class="status-cell" id="status-cell-${l.id}"></td>
                <td class="notes-cell" id="notes-cell-${l.id}"></td>`;
            tbody.appendChild(tr);
            this.renderEmailCell(l.id, l.email);
            this.renderStatusCell(l.id, l.call_status || 'Need to Call');
            this.renderNotesCell(l.id, l.notes || '');
        });

        lucide.createIcons();
    },

    // ── Email cell ────────────────────────────────────────────────────────────

    renderEmailCell(leadId, email) {
        const cell = document.getElementById(`email-cell-${leadId}`);
        if (!cell) return;
        if (email) {
            const safe = email.replace(/'/g, "\\'");
            cell.innerHTML = `
                <div class="email-display">
                    <a href="mailto:${email}" onclick="event.stopPropagation()" title="${email}">${email}</a>
                    <button class="email-edit-btn" onclick="event.stopPropagation(); app.editLeadEmail(${leadId}, '${safe}')" title="Edit email">
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                </div>`;
        } else {
            cell.innerHTML = `<button class="email-add-btn" onclick="event.stopPropagation(); app.editLeadEmail(${leadId}, '')">+ Add</button>`;
        }
    },

    editLeadEmail(leadId, currentEmail) {
        const cell = document.getElementById(`email-cell-${leadId}`);
        if (!cell) return;
        const safe = currentEmail.replace(/'/g, "\\'");
        cell.innerHTML = `
            <div class="email-edit-form" onclick="event.stopPropagation()">
                <input id="email-input-${leadId}" type="email" class="email-input" value="${currentEmail}"
                    placeholder="email@example.com"
                    onkeydown="if(event.key==='Enter') app.saveLeadEmail(${leadId}); if(event.key==='Escape') app.cancelEmailEdit(${leadId}, '${safe}')" />
                <button class="email-save-btn" onclick="app.saveLeadEmail(${leadId})" title="Save">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </button>
                <button class="email-cancel-btn" onclick="app.cancelEmailEdit(${leadId}, '${safe}')" title="Cancel">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
            </div>`;
        const input = document.getElementById(`email-input-${leadId}`);
        if (input) { input.focus(); input.select(); }
    },

    async saveLeadEmail(leadId) {
        const input = document.getElementById(`email-input-${leadId}`);
        if (!input) return;
        const newEmail = input.value.trim();
        try {
            const res = await fetch(`/api/leads/${leadId}/email`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: newEmail }),
            });
            const data = await res.json();
            if (data.success) {
                if (this.state.activeCampaignData) {
                    const lead = this.state.activeCampaignData.leads.find(l => l.id === leadId);
                    if (lead) lead.email = data.email;
                    const leads = this.state.activeCampaignData.leads;
                    const withEmail = leads.filter(l => l.email).length;
                    document.getElementById('stat-email').innerText =
                        leads.length ? Math.round((withEmail / leads.length) * 100) + '%' : '0%';
                }
                this.renderEmailCell(leadId, data.email);
            }
        } catch (e) {
            console.error('Failed to save email', e);
        }
    },

    cancelEmailEdit(leadId, originalEmail) {
        this.renderEmailCell(leadId, originalEmail);
    },

    // ── Status cell ───────────────────────────────────────────────────────────

    renderStatusCell(leadId, currentStatus) {
        const cell = document.getElementById(`status-cell-${leadId}`);
        if (!cell) return;
        // Guard: if a select is open and user is interacting, don't re-render
        const existing = cell.querySelector('select');
        if (existing && document.activeElement === existing) return;

        const color = STATUS_COLORS[currentStatus] || '#8f95b2';
        const options = CALL_STATUSES.map(s =>
            `<option value="${s}" ${s === currentStatus ? 'selected' : ''} style="color:${STATUS_COLORS[s] || '#8f95b2'};background:#12141d;">${s}</option>`
        ).join('');
        cell.innerHTML = `
            <select class="status-select"
                onclick="event.stopPropagation()"
                onchange="app.saveLeadStatus(${leadId}, this.value)"
                style="color:${color};border-color:${color};box-shadow:0 0 6px ${color}33;">
                ${options}
            </select>`;
    },

    async saveLeadStatus(leadId, newStatus) {
        // Instant visual feedback
        const sel = document.querySelector(`#status-cell-${leadId} .status-select`);
        if (sel) {
            const c = STATUS_COLORS[newStatus] || '#8f95b2';
            sel.style.color = c;
            sel.style.borderColor = c;
            sel.style.boxShadow = `0 0 6px ${c}33`;
        }
        // Update local state immediately so sidebar pills stay in sync
        if (this.state.activeCampaignData) {
            const lead = this.state.activeCampaignData.leads.find(l => l.id === leadId);
            if (lead) {
                lead.call_status = newStatus;
                this._refreshSidebarPills(this.state.activeCampaignId, this.state.activeCampaignData.leads);
            }
        }
        try {
            const res = await fetch(`/api/leads/${leadId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ call_status: newStatus }),
            });
            const data = await res.json();
            if (!data.success) {
                // Revert on failure
                await this.fetchCampaignDetails(this.state.activeCampaignId);
            }
        } catch (e) {
            console.error('Failed to save status', e);
        }
    },

    // ── Notes cell ────────────────────────────────────────────────────────────

    renderNotesCell(leadId, notes) {
        const cell = document.getElementById(`notes-cell-${leadId}`);
        if (!cell) return;
        if (notes) {
            const safeHtml = notes.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
            cell.innerHTML = `<div class="notes-display" onclick="event.stopPropagation(); app.openNotesModal(${leadId})" title="Click to edit">${safeHtml}</div>`;
        } else {
            cell.innerHTML = `<button class="notes-add-btn" onclick="event.stopPropagation(); app.openNotesModal(${leadId})">+ Note</button>`;
        }
    },

    openNotesModal(leadId) {
        const lead = this.state.activeCampaignData?.leads?.find(l => l.id === leadId);
        if (!lead) return;
        this._notesModalLeadId = leadId;

        document.getElementById('notes-modal-lead-name').textContent = lead.name || 'Note';
        const ta = document.getElementById('notes-modal-textarea');
        ta.value = lead.notes || '';
        document.getElementById('notes-modal-overlay').classList.add('open');

        setTimeout(() => {
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);
        }, 80);

        ta._notesKeyHandler = (e) => {
            if (e.key === 'Escape') { e.preventDefault(); this.closeNotesModal(); }
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this.saveNotesModal(); }
        };
        ta.addEventListener('keydown', ta._notesKeyHandler);
    },

    closeNotesModal() {
        const ta = document.getElementById('notes-modal-textarea');
        document.getElementById('notes-modal-overlay').classList.remove('open');
        if (ta._notesKeyHandler) {
            ta.removeEventListener('keydown', ta._notesKeyHandler);
            delete ta._notesKeyHandler;
        }
        this._notesModalLeadId = null;
    },

    async saveNotesModal() {
        const leadId = this._notesModalLeadId;
        if (!leadId) return;
        const ta  = document.getElementById('notes-modal-textarea');
        const notes = ta.value.trim();
        const btn = document.querySelector('.notes-btn-save');
        btn.disabled = true;
        btn.textContent = 'Saving...';
        try {
            const res = await fetch(`/api/leads/${leadId}/notes`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ notes }),
            });
            const data = await res.json();
            if (data.success) {
                if (this.state.activeCampaignData) {
                    const lead = this.state.activeCampaignData.leads.find(l => l.id === leadId);
                    if (lead) lead.notes = data.notes;
                }
                this.renderNotesCell(leadId, data.notes);
                this.closeNotesModal();
            }
        } catch (e) {
            console.error('Failed to save notes', e);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Save Note';
        }
    },

    // ── Lead detail drawer ────────────────────────────────────────────────────

    showLeadDetail(lead) {
        const statusColor = STATUS_COLORS[lead.call_status] || '#8f95b2';
        document.getElementById('drawer-content').innerHTML = `
            <div class="detail-group">
                <div class="detail-label">ENTITY NAME</div>
                <div class="detail-value" style="font-size:1.25rem;font-weight:bold;color:var(--accent);">${lead.name || '-'}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">CATEGORY</div>
                <div class="detail-value">${lead.category || 'N/A'}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">ADDRESS</div>
                <div class="detail-value">${lead.address || 'N/A'}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">PHONE</div>
                <div class="detail-value">${lead.phone
                    ? `<a href="tel:${lead.phone}" style="color:var(--accent);font-family:var(--font-mono);font-size:1.1rem;">${lead.phone}</a>`
                    : '<span style="color:var(--text-dim)">Not available</span>'}
                </div>
            </div>
            <div class="detail-group">
                <div class="detail-label">EMAIL</div>
                <div class="detail-value">${lead.email
                    ? `<a href="mailto:${lead.email}">${lead.email}</a>`
                    : '<span style="color:var(--text-dim)">Not found</span>'}
                </div>
            </div>
            <div class="detail-group">
                <div class="detail-label">WEBSITE</div>
                <div class="detail-value">${lead.website ? `<a href="${lead.website}" target="_blank">${lead.website}</a>` : 'N/A'}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">GOOGLE MAPS</div>
                <div class="detail-value">${lead.google_url ? `<a href="${lead.google_url}" target="_blank">View on Maps</a>` : 'N/A'}</div>
            </div>
            <div class="detail-group" style="display:flex;gap:2rem;">
                <div>
                    <div class="detail-label">RATING</div>
                    <div class="detail-value" style="color:#ffbd2e;font-size:1.5rem;">${lead.rating || 'N/A'}</div>
                </div>
                <div>
                    <div class="detail-label">REVIEWS</div>
                    <div class="detail-value" style="font-size:1.5rem;">${lead.reviews || '0'}</div>
                </div>
            </div>
            <div class="detail-group">
                <div class="detail-label">CALL STATUS</div>
                <div class="detail-value" style="color:${statusColor};font-weight:600;">${lead.call_status || 'Need to Call'}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">NOTES</div>
                <div class="detail-value">${lead.notes || '<span style="color:var(--text-dim)">No notes</span>'}</div>
            </div>`;

        document.getElementById('side-drawer').classList.add('open');
        document.getElementById('drawer-overlay').classList.add('open');
    },

    closeDrawer() {
        document.getElementById('side-drawer').classList.remove('open');
        document.getElementById('drawer-overlay').classList.remove('open');
    },
};

document.addEventListener('DOMContentLoaded', () => { app.init(); });
