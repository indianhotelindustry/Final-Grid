/**
 * dashboard_modals.js — Dashboard card preview modals + tab switching
 *
 * Loaded from /static/js/ (CSP: script-src 'self') — no inline nonce needed.
 * Runs after Bootstrap JS (loaded in base.html before {% block scripts %}).
 */
(function () {
    'use strict';

    // ── Defensive guard ─────────────────────────────────────────────────────
    if (typeof bootstrap === 'undefined') {
        console.error(
            'Bootstrap JS not loaded: dashboard modal cannot open. ' +
            'Ensure bootstrap.bundle.min.js is included before dashboard_modals.js.'
        );
        return;
    }

    // ── Dashboard tab switching (Overview / Analytics) ───────────────────────
    var dashboardTabs = document.getElementById('dashboardTabs');
    if (dashboardTabs) {
        dashboardTabs.querySelectorAll('.nav-link').forEach(function (link) {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                dashboardTabs.querySelectorAll('.nav-link').forEach(function (l) {
                    l.classList.remove('active');
                });
                this.classList.add('active');

                var tab      = this.dataset.tab;
                var overview  = document.getElementById('dashboardOverview');
                var analytics = document.getElementById('dashboardAnalytics');
                var commandC  = document.getElementById('dashboardCommandCenter');

                // Helper: hide every tab container before showing the selected one.
                function hideAll() {
                    if (overview)  overview.style.display  = 'none';
                    if (analytics) analytics.style.display = 'none';
                    if (commandC)  commandC.style.display  = 'none';
                }

                // Helper: one-time lazy load of a tab's HTML partial, mirroring the
                // Analytics pattern — re-executes inline scripts so the partial can
                // bring its own JS.
                function lazyLoad(container, url, friendlyError) {
                    if (!container || container.dataset.loaded) return;
                    container.innerHTML = '<div class="text-center py-5">' +
                        '<div class="spinner-border text-primary"></div></div>';
                    fetch(url)
                        .then(function (res) { return res.text(); })
                        .then(function (html) {
                            container.innerHTML     = html;
                            container.dataset.loaded = '1';
                            container.querySelectorAll('script').forEach(function (old) {
                                var s = document.createElement('script');
                                Array.from(old.attributes).forEach(function (a) {
                                    s.setAttribute(a.name, a.value);
                                });
                                s.textContent = old.textContent;
                                old.parentNode.replaceChild(s, old);
                            });
                        })
                        .catch(function () {
                            container.innerHTML =
                                '<p class="text-muted text-center py-4">' + friendlyError + '</p>';
                        });
                }

                if (tab === 'overview') {
                    hideAll();
                    if (overview) overview.style.display = '';
                } else if (tab === 'analytics') {
                    hideAll();
                    if (analytics) {
                        analytics.style.display = '';
                        lazyLoad(analytics, '/api/dashboard/analytics', 'Analytics unavailable.');
                    }
                } else if (tab === 'command-center') {
                    hideAll();
                    if (commandC) {
                        commandC.style.display = '';
                        lazyLoad(commandC, '/api/dashboard/command-center', 'KPI Command Center unavailable.');
                    }
                }
            });
        });
    }

    // ── Card preview modal ───────────────────────────────────────────────────
    var previewModal = document.getElementById('cardPreviewModal');
    if (!previewModal) return;

    var bsModal     = new bootstrap.Modal(previewModal, { backdrop: true, keyboard: true });
    var titleEl     = document.getElementById('cardPreviewTitle');
    var bodyEl      = document.getElementById('cardPreviewBody');
    var gotoEl      = document.getElementById('cardPreviewGoTo');
    var gotoLabelEl = document.getElementById('cardPreviewGoToLabel');
    var goto2El     = document.getElementById('cardPreviewGoTo2');
    var lastFocused = null;

    // Cards that get the secondary "Go to Dashboard" button
    var SHOW_GOTO2 = { 'in_house': true };

    function openCard(cardType, title, gotoUrl, gotoLabel) {
        if (titleEl)     titleEl.textContent     = title;
        if (gotoEl)      gotoEl.href             = gotoUrl;
        if (gotoLabelEl) gotoLabelEl.textContent = 'Go To ' + gotoLabel;
        if (goto2El)     goto2El.classList.toggle('d-none', !SHOW_GOTO2[cardType]);
        if (bodyEl)      bodyEl.innerHTML        =
            '<div class="text-center py-5">' +
            '<div class="spinner-border text-primary"></div></div>';

        bsModal.show();

        fetch('/api/dashboard/card-preview/' + encodeURIComponent(cardType))
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.text();
            })
            .then(function (html) {
                if (bodyEl) bodyEl.innerHTML = html;
            })
            .catch(function (err) {
                console.error('card preview fetch failed:', err);
                if (bodyEl) bodyEl.innerHTML =
                    '<p class="text-muted text-center py-4">' +
                    '<i class="bi bi-exclamation-circle me-1"></i>Preview unavailable.</p>';
            });
    }

    function reloadDirtyModal() {
        if (bodyEl) bodyEl.innerHTML =
            '<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>';
        fetch('/api/dashboard/card-preview/dirty')
            .then(function (r) { return r.text(); })
            .then(function (html) { if (bodyEl) bodyEl.innerHTML = html; })
            .catch(function () {
                if (bodyEl) bodyEl.innerHTML =
                    '<p class="text-muted text-center py-4">Could not reload list.</p>';
            });
    }

    // ── Update the Dirty KPI card count on the dashboard ────────────────────
    function updateDirtyKpiCard(count) {
        var card = document.querySelector('[data-card-modal="dirty"]');
        if (!card) return;
        var valEl = card.querySelector('.kpi-val');
        if (valEl) valEl.textContent = count;
        // Toggle warning border
        card.classList.toggle('border-warning', count > 0);
        card.classList.toggle('border-2',       count > 0);
    }

    // ── Toast notification ───────────────────────────────────────────────────
    function showToast(message, type) {
        var containerId = 'dmToastContainer';
        var container = document.getElementById(containerId);
        if (!container) {
            container = document.createElement('div');
            container.id = containerId;
            container.style.cssText =
                'position:fixed;bottom:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
            document.body.appendChild(container);
        }
        var bg = type === 'success' ? 'bg-success' : (type === 'error' ? 'bg-danger' : 'bg-secondary');
        var toast = document.createElement('div');
        toast.className = 'toast show align-items-center text-white border-0 ' + bg;
        toast.setAttribute('role', 'alert');
        toast.innerHTML =
            '<div class="d-flex"><div class="toast-body">' + escapeHtml(message) + '</div>' +
            '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
        container.appendChild(toast);
        toast.querySelector('[data-bs-dismiss="toast"]').addEventListener('click', function () {
            toast.remove();
        });
        setTimeout(function () { if (toast.parentNode) toast.remove(); }, 4000);
    }

    // ── Dirty rooms: event delegation on modal body ──────────────────────────
    previewModal.addEventListener('click', function (e) {
        // Single room Mark Clean
        var cleanBtn = e.target.closest('.js-mark-clean');
        if (cleanBtn) {
            e.preventDefault();
            var roomId     = cleanBtn.dataset.roomId;
            var roomNumber = cleanBtn.dataset.roomNumber;
            cleanBtn.disabled = true;
            cleanBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            fetch('/api/dashboard/rooms/' + roomId + '/mark-clean', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.ok) {
                        // Remove the row from the table
                        var row = cleanBtn.closest('tr[data-room-id]');
                        if (row) row.remove();
                        updateDirtyKpiCard(data.dirty_count);
                        showToast('Room ' + roomNumber + ' marked as clean.', 'success');
                        // If no rows left, reload modal to show "all clean" message
                        var tbody = bodyEl ? bodyEl.querySelector('tbody') : null;
                        if (!tbody || !tbody.querySelector('tr')) {
                            reloadDirtyModal();
                        }
                    } else {
                        cleanBtn.disabled = false;
                        cleanBtn.innerHTML = '<i class="bi bi-check2"></i> Mark Clean';
                        showToast(data.error || 'Could not update room.', 'error');
                    }
                })
                .catch(function () {
                    cleanBtn.disabled = false;
                    cleanBtn.innerHTML = '<i class="bi bi-check2"></i> Mark Clean';
                    showToast('Network error. Please try again.', 'error');
                });
            return;
        }

        // Mark All Rooms Clean
        var allBtn = e.target.closest('.js-mark-all-clean');
        if (allBtn) {
            e.preventDefault();
            if (!confirm('Are you sure you want to mark all dirty rooms as clean?')) return;
            allBtn.disabled = true;
            allBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Updating…';

            fetch('/api/dashboard/rooms/mark-all-clean', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.ok) {
                        updateDirtyKpiCard(data.dirty_count);
                        reloadDirtyModal();
                        var msg = data.updated + ' room' + (data.updated !== 1 ? 's' : '') + ' marked as clean.';
                        if (data.errors && data.errors.length) {
                            msg += ' ' + data.errors.length + ' error(s).';
                            showToast(msg, 'error');
                        } else {
                            showToast(msg, 'success');
                        }
                    } else {
                        allBtn.disabled = false;
                        allBtn.innerHTML = '<i class="bi bi-check2-all me-1"></i>Mark All Rooms Clean';
                        showToast(data.error || 'Could not update rooms.', 'error');
                    }
                })
                .catch(function () {
                    allBtn.disabled = false;
                    allBtn.innerHTML = '<i class="bi bi-check2-all me-1"></i>Mark All Rooms Clean';
                    showToast('Network error. Please try again.', 'error');
                });
        }
    });

    // ── Bind click + keyboard events on every card with data-card-modal ──────
    document.querySelectorAll('[data-card-modal]').forEach(function (card) {
        card.addEventListener('click', function (e) {
            e.preventDefault();
            lastFocused = this;
            openCard(
                this.dataset.cardModal,
                this.dataset.cardTitle  || this.dataset.cardModal,
                this.dataset.gotoUrl    || '#',
                this.dataset.gotoLabel  || 'Page'
            );
        });
        card.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.click();
            }
        });
    });

    // Return focus to the triggering card after modal closes
    previewModal.addEventListener('hidden.bs.modal', function () {
        if (lastFocused) { lastFocused.focus(); lastFocused = null; }
    });

    // Lock background scroll while modal is open
    previewModal.addEventListener('show.bs.modal',   function () {
        document.body.style.overflowY = 'hidden';
    });
    previewModal.addEventListener('hidden.bs.modal', function () {
        document.body.style.overflowY = '';
    });

}());
