/**
 * CEO Dashboard — Phase B
 * ------------------------
 * Fetches /api/ceo/kpi-pack and /api/ai/insights?mode=ceo on page load
 * and binds the refresh button. The Flask shell renders only
 * placeholders; everything visible here is painted by this script.
 *
 * Owner-only — but the route already 403's anonymous users, so this
 * file does no client-side gating beyond being absent for non-owners.
 */
(function () {
    'use strict';

    const root = document.getElementById('ceoDashboard');
    if (!root) return;

    const kpiEndpoint            = root.dataset.kpiEndpoint;
    const insightsEndpoint       = root.dataset.insightsEndpoint;
    const insightsRefreshEndpoint = root.dataset.insightsRefreshEndpoint;

    // ── Helpers ──────────────────────────────────────────────────────
    function escapeHTML(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function fmtINR(v) {
        const n = Number(v || 0);
        if (!isFinite(n)) return '0';
        return Math.round(n).toLocaleString('en-IN');
    }

    function fmtTime(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            if (isNaN(d.getTime())) return '';
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (_) { return ''; }
    }

    function setKpiValue(card, value, klass) {
        if (!card) return;
        const valEl = card.querySelector('.ceo-kpi-value');
        if (valEl) valEl.textContent = value;
        card.classList.remove('healthy', 'warn', 'danger');
        if (klass) card.classList.add(klass);
    }

    // ── KPI top strip + sections ─────────────────────────────────────
    function renderKpiPack(data) {
        if (!data) return;

        // Business date + load time
        const bdEl = document.getElementById('ceoBusinessDate');
        if (bdEl) bdEl.textContent = data.business_date || '—';
        const ltEl = document.getElementById('ceoLoadedAt');
        if (ltEl) ltEl.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        const headline = data.headline || {};
        const funnel = data.funnel || {};
        const channelMix = data.channel_mix || {};
        const pipeline = data.pipeline || {};
        const aging = data.receivable_aging || {};
        const audit = data.audit_health || {};

        // ── Top KPI strip ──
        const cardBookings = root.querySelector('[data-kpi="bookings"]');
        setKpiValue(cardBookings, headline.ota_bookings_today ?? 0,
                    headline.ota_bookings_today > 0 ? 'healthy' : null);

        const cardArrivals = root.querySelector('[data-kpi="arrivals"]');
        setKpiValue(cardArrivals, headline.ota_arrivals_today ?? 0, null);

        const cardCheckins = root.querySelector('[data-kpi="checkins"]');
        const checkedIn = headline.ota_checked_in_today ?? 0;
        const expected = headline.ota_arrivals_today ?? 0;
        const conv = funnel.conversion_pct ?? 0;
        setKpiValue(cardCheckins, `${checkedIn}/${expected}`,
                    conv >= 80 ? 'healthy' : (conv >= 50 ? 'warn' : 'danger'));
        const convEl = cardCheckins ? cardCheckins.querySelector('[data-conv]') : null;
        if (convEl) convEl.textContent = conv;

        const cardRevenue = root.querySelector('[data-kpi="revenue"]');
        // "OTA Revenue Today" = sum of today's channel mix accruals
        const todayRows = (channelMix.today || []);
        const todayRev = todayRows.reduce((s, r) => s + Number(r.revenue_accrued || 0), 0);
        setKpiValue(cardRevenue, '₹' + fmtINR(todayRev),
                    todayRev > 0 ? 'healthy' : null);

        const cardOutstanding = root.querySelector('[data-kpi="outstanding"]');
        const out = headline.ota_receivable_outstanding ?? 0;
        const aged30 = ((aging.buckets || []).find(b => b.label === '30+ days') || {}).total || 0;
        const oldShare = out > 0 ? (aged30 / out) : 0;
        setKpiValue(cardOutstanding, '₹' + fmtINR(out),
                    out === 0 ? 'healthy' : (oldShare >= 0.30 ? 'danger' : 'warn'));

        const cardAudit = root.querySelector('[data-kpi="audit"]');
        const auditStatus = audit.last_audit_status || '—';
        const daysBehind = audit.days_behind ?? 0;
        setKpiValue(cardAudit, auditStatus,
                    daysBehind === 0 && auditStatus === 'Completed' ? 'healthy'
                        : (daysBehind >= 2 ? 'danger' : 'warn'));
        const auditDateEl = cardAudit ? cardAudit.querySelector('[data-audit-date]') : null;
        if (auditDateEl) {
            auditDateEl.textContent = audit.last_completed_audit_date
                ? `last completed ${audit.last_completed_audit_date}`
                : 'no completed audit';
        }

        // ── Funnel ──
        const funnelEl = document.getElementById('ceoFunnel');
        if (funnelEl) {
            const cells = [
                ['Bookings',   funnel.bookings_received ?? 0],
                ['Arrivals',   funnel.arrivals_expected ?? 0],
                ['Checked In', funnel.checked_in        ?? 0],
                ['Checked Out',funnel.checked_out       ?? 0],
                ['No-shows',   funnel.no_shows          ?? 0],
                ['Cancelled',  funnel.cancellations     ?? 0],
            ];
            funnelEl.innerHTML = cells.map(([label, n]) =>
                `<div class="ceo-funnel-step"><div class="fnum">${n}</div><div class="flabel">${label}</div></div>`
            ).join('');
        }

        // ── Channel mix tables ──
        renderChannelTable('ceoChannelToday', channelMix.today || []);
        renderChannelTable('ceoChannelMtd', channelMix.mtd || []);

        // ── Pipeline ──
        const pipeBookings = document.getElementById('ceoPipeBookings');
        if (pipeBookings) pipeBookings.textContent = pipeline.total_bookings ?? 0;
        const pipeNights = document.getElementById('ceoPipeNights');
        if (pipeNights) pipeNights.textContent = pipeline.total_room_nights ?? 0;
        const pipeRevenue = document.getElementById('ceoPipeRevenue');
        if (pipeRevenue) pipeRevenue.textContent = fmtINR(pipeline.total_projected_revenue);

        const pipeBySource = document.getElementById('ceoPipeBySource');
        if (pipeBySource) {
            const rows = pipeline.by_source || [];
            if (rows.length === 0) {
                pipeBySource.innerHTML = '<tr><td colspan="4" class="text-muted small">No forward bookings.</td></tr>';
            } else {
                pipeBySource.innerHTML = rows.map(r =>
                    `<tr>
                        <td>${escapeHTML(r.source)}</td>
                        <td class="num">${r.bookings}</td>
                        <td class="num">${r.room_nights}</td>
                        <td class="num">₹${fmtINR(r.revenue)}</td>
                    </tr>`
                ).join('');
            }
        }

        // ── Payout Status (Phase 2) ──
        renderPayoutStatus(data.payout_status || {});

        // ── Aging ──
        const agingEl = document.getElementById('ceoAging');
        if (agingEl) {
            const buckets = aging.buckets || [];
            agingEl.innerHTML = buckets.map(b => {
                const klass = b.label === '30+ days' ? 'ceo-aging-card bucket-30plus' : 'ceo-aging-card';
                return `<div class="${klass}">
                    <div class="alabel">${escapeHTML(b.label)}</div>
                    <div class="aval">₹${fmtINR(b.total)}</div>
                    <div class="text-muted" style="font-size:0.6rem;">${b.count || 0} entries</div>
                </div>`;
            }).join('');
        }
        const agingTotal = document.getElementById('ceoAgingTotal');
        if (agingTotal) agingTotal.textContent = fmtINR(aging.total_outstanding);
    }

    function renderPayoutStatus(status) {
        const summaryEl = document.getElementById('ceoPayoutSummary');
        const tbody = document.getElementById('ceoPayoutRows');

        if (summaryEl) {
            const totalPending = Number(status.total_pending || 0);
            const maxDelay = Number(status.max_delay_days || 0);
            if (totalPending <= 0) {
                summaryEl.innerHTML = '<span class="text-success">All channels reconciled — nothing pending.</span>';
            } else {
                const delayBit = maxDelay > 0
                    ? ` · max delay <strong>${maxDelay}</strong> day(s)`
                    : '';
                summaryEl.innerHTML =
                    `Total pending: <strong>₹${fmtINR(totalPending)}</strong>${delayBit}`;
            }
        }

        if (!tbody) return;
        const rows = status.channels || [];
        if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-muted small">' +
                'No OTA channels with revenue or payouts yet.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            const statusKlass = r.status === 'healthy' ? 'badge bg-success'
                              : (r.status === 'warn'   ? 'badge bg-warning text-dark'
                              : (r.status === 'danger' ? 'badge bg-danger'
                              : 'badge bg-secondary'));
            const statusLabel = r.status === 'healthy' ? 'On time'
                              : (r.status === 'warn'   ? 'Warning'
                              : (r.status === 'danger' ? 'Overdue'
                              : escapeHTML(r.status)));
            return '<tr>' +
                '<td>' + escapeHTML(r.channel) + '</td>' +
                '<td class="num">₹' + fmtINR(r.pending) + '</td>' +
                '<td class="num">' + escapeHTML(r.last_payout_date || '—') + '</td>' +
                '<td class="num">' + (r.cycle_days || 0) + ' d</td>' +
                '<td class="num">' + (r.delay_days || 0) + ' d</td>' +
                '<td class="num"><span class="' + statusKlass +
                  '" style="font-size:0.62rem;">' + statusLabel + '</span></td>' +
            '</tr>';
        }).join('');
    }

    function renderChannelTable(id, rows) {
        const tbody = document.getElementById(id);
        if (!tbody) return;
        if (!rows || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted small">No bookings in this period.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(r =>
            `<tr>
                <td>${escapeHTML(r.source)}</td>
                <td class="num">${r.bookings}</td>
                <td class="num">${r.room_nights}</td>
                <td class="num">₹${fmtINR(r.revenue_accrued)}</td>
            </tr>`
        ).join('');
    }

    // ── AI Insights panel ────────────────────────────────────────────
    const elSummary  = document.getElementById('ceoAiSummary');
    const elIssues   = document.getElementById('ceoAiIssues');
    const elActions  = document.getElementById('ceoAiActions');
    const elSource   = document.getElementById('ceoAiSource');
    const elTime     = document.getElementById('ceoAiTime');
    const btnAiRefresh = document.getElementById('ceoAiRefreshBtn');

    function renderInsights(insights) {
        if (!insights) return;
        elSummary.textContent = insights.summary || '(no summary)';

        const src = insights.source || 'unknown';
        elSource.textContent = src === 'gemini' ? 'Gemini'
                          : (src === 'heuristic' ? 'Offline rules' : src);
        elSource.className = 'ai-source-badge' + (src === 'heuristic' ? ' heuristic' : '');
        elSource.title = insights.model
            ? `Generated by ${insights.model}`
            : 'Generated locally without an LLM';
        elTime.textContent = insights.generated_at
            ? `at ${fmtTime(insights.generated_at)}`
            : '';

        const issues = insights.issues || [];
        if (issues.length === 0) {
            elIssues.innerHTML = '<div class="ceo-ai-empty">No issues detected — the business looks healthy.</div>';
        } else {
            elIssues.innerHTML = issues.map(it => {
                const title  = escapeHTML(it.title || '');
                const reason = escapeHTML(it.reason || '');
                return `<div class="ceo-ai-item">
                    <i class="bi bi-dot bullet"></i>
                    <div>
                        <div class="issue-title">${title}</div>
                        ${reason ? `<div class="issue-reason">${reason}</div>` : ''}
                    </div>
                </div>`;
            }).join('');
        }

        const actions = insights.actions || [];
        if (actions.length === 0) {
            elActions.innerHTML = '<div class="ceo-ai-empty">No specific actions needed right now.</div>';
        } else {
            elActions.innerHTML = actions.map(a =>
                `<div class="ceo-ai-item">
                    <i class="bi bi-arrow-right-circle bullet"></i>
                    <div>${escapeHTML(a)}</div>
                </div>`
            ).join('');
        }
    }

    function showInsightsError(msg) {
        elSource.textContent = 'error';
        elSource.className = 'ai-source-badge heuristic';
        elSummary.innerHTML = `<span class="ceo-ai-error">${escapeHTML(msg)}</span>`;
        elIssues.innerHTML = '';
        elActions.innerHTML = '';
    }

    // ── Network ──────────────────────────────────────────────────────
    function jsonFetch(url, method) {
        method = method || 'GET';
        const opts = { method: method, headers: { 'Accept': 'application/json' } };
        if (method === 'POST') {
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            if (csrfMeta) opts.headers['X-CSRFToken'] = csrfMeta.getAttribute('content');
        }
        return fetch(url, opts).then(r => {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    }

    function loadKpis() {
        return jsonFetch(kpiEndpoint)
            .then(body => {
                if (body.status !== 'ok' || !body.data) {
                    throw new Error(body.error || 'Bad response');
                }
                renderKpiPack(body.data);
            })
            .catch(err => {
                console.error('CEO KPI load failed:', err);
                const ltEl = document.getElementById('ceoLoadedAt');
                if (ltEl) ltEl.textContent = 'failed';
            });
    }

    function loadInsights(refresh) {
        const url = refresh ? insightsRefreshEndpoint : insightsEndpoint;
        const method = refresh ? 'POST' : 'GET';
        if (refresh) {
            elSummary.innerHTML = '<span class="text-muted">Regenerating insights…</span>';
            elIssues.innerHTML = '<div class="ceo-ai-empty">Loading…</div>';
            elActions.innerHTML = '<div class="ceo-ai-empty">Loading…</div>';
        }
        return jsonFetch(url, method)
            .then(body => {
                if (body.status !== 'ok' || !body.insights) {
                    throw new Error(body.error || 'Bad response');
                }
                renderInsights(body.insights);
            })
            .catch(err => {
                console.error('CEO insights load failed:', err);
                showInsightsError('Could not load insights — ' + (err.message || 'unknown error'));
            });
    }

    // ── Wire up refresh buttons ──────────────────────────────────────
    const btnRefresh = document.getElementById('ceoRefreshBtn');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', function () {
            btnRefresh.disabled = true;
            Promise.all([loadKpis(), loadInsights(false)])
                .then(() => { btnRefresh.disabled = false; });
        });
    }
    if (btnAiRefresh) {
        btnAiRefresh.addEventListener('click', function () {
            btnAiRefresh.disabled = true;
            loadInsights(true).then(() => { btnAiRefresh.disabled = false; });
        });
    }

    // ── Initial paint ────────────────────────────────────────────────
    function init() {
        loadKpis();
        loadInsights(false);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
