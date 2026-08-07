class GuestSearchForm {
    constructor(searchInputId, formPrefix) {
        this.searchInput = document.getElementById(searchInputId);
        this.formPrefix  = formPrefix;
        this.debounceTimer  = null;
        this.selectedGuest  = null;

        if (!this.searchInput) return;

        this.searchInput.addEventListener('input',   e => this.handleInput(e));
        this.searchInput.addEventListener('keydown', e => this.handleKeydown(e));
        document.addEventListener('click',           e => this.handleClickOutside(e));

        // Wire clear button
        const clearBtn = document.getElementById(`${this.formPrefix}_clear_guest`);
        if (clearBtn) clearBtn.addEventListener('click', () => this.clearGuest());
    }

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value.trim();
        if (query.length < 2) { this.hideDropdown(); return; }
        this.debounceTimer = setTimeout(() => this.search(query), 300);
    }

    search(query) {
        fetch(`/api/search-guests?q=${encodeURIComponent(query)}`)
            .then(r => r.json())
            .then(guests => this.renderResults(guests))
            .catch(() => this.hideDropdown());
    }

    renderResults(guests) {
        const dropdown = this.getDropdown();
        if (guests.length === 0) {
            dropdown.innerHTML = '<div class="guest-search-item text-muted small px-3 py-2">No existing guest found — enter details below to create new</div>';
            this.showDropdown();
            return;
        }
        dropdown.innerHTML = guests.map(g =>
            `<div class="guest-search-item" onclick="window['guestSearchForm_${this.formPrefix}'].selectGuest(${JSON.stringify(g).replace(/"/g, '&quot;')})">
                <div class="guest-search-name">${this._esc(g.name)} &nbsp;<span class="text-muted">${this._esc(g.phone)}</span></div>
                <div class="guest-search-details">${this._esc(g.company || '')}${g.company ? ' · ' : ''}${this._esc(g.folio_no || '')}</div>
            </div>`
        ).join('');
        this.showDropdown();
    }

    selectGuest(guest) {
        this.selectedGuest = guest;

        // Set hidden guest_id
        const gid = document.getElementById(`${this.formPrefix}_guest_id`);
        if (gid) gid.value = guest.id;

        // Split stored name → first / last
        const parts     = (guest.name || '').trim().split(/\s+/);
        const firstName = parts[0] || '';
        const lastName  = parts.slice(1).join(' ') || '';

        this._set(`${this.formPrefix}_first_name`,   firstName);
        this._set(`${this.formPrefix}_last_name`,    lastName);
        this._set(`${this.formPrefix}_guest_phone`,  guest.phone);
        this._set(`${this.formPrefix}_guest_email`,  guest.email || '');

        this.searchInput.value = `${guest.name}  (${guest.phone})`;
        this.hideDropdown();
        this.showSelectedCard(guest);
    }

    showSelectedCard(guest) {
        const card   = document.getElementById(`${this.formPrefix}_selected_card`);
        const fields = document.getElementById(`${this.formPrefix}_new_guest_fields`);
        if (card) {
            this._txt(`${this.formPrefix}_sc_name`,    guest.name);
            this._txt(`${this.formPrefix}_sc_phone`,   guest.phone);
            this._txt(`${this.formPrefix}_sc_email`,   guest.email    || '—');
            this._txt(`${this.formPrefix}_sc_company`, guest.company  || '—');
            card.style.display = '';
        }
        if (fields) fields.style.opacity = '0.45';
    }

    clearGuest() {
        this.selectedGuest = null;

        const gid = document.getElementById(`${this.formPrefix}_guest_id`);
        if (gid) gid.value = '';

        this._set(`${this.formPrefix}_first_name`,  '');
        this._set(`${this.formPrefix}_last_name`,   '');
        this._set(`${this.formPrefix}_guest_phone`, '');
        this._set(`${this.formPrefix}_guest_email`, '');

        this.searchInput.value = '';

        const card   = document.getElementById(`${this.formPrefix}_selected_card`);
        const fields = document.getElementById(`${this.formPrefix}_new_guest_fields`);
        if (card)   card.style.display = 'none';
        if (fields) fields.style.opacity = '';

        this.searchInput.focus();
    }

    // ── Dropdown helpers ──────────────────────────────────────────────
    getDropdown() {
        let d = document.getElementById(`${this.formPrefix}_dropdown`);
        if (!d) {
            d = document.createElement('div');
            d.id        = `${this.formPrefix}_dropdown`;
            d.className = 'guest-search-dropdown';
            this.searchInput.parentElement.appendChild(d);
        }
        return d;
    }
    showDropdown() { this.getDropdown().classList.add('show'); }
    hideDropdown() {
        const d = document.getElementById(`${this.formPrefix}_dropdown`);
        if (d) d.classList.remove('show');
    }

    handleKeydown(e) { if (e.key === 'Escape') this.hideDropdown(); }
    handleClickOutside(e) {
        if (this.searchInput.contains(e.target)) return;
        const d = document.getElementById(`${this.formPrefix}_dropdown`);
        if (d && d.contains(e.target)) return;
        this.hideDropdown();
    }

    // ── Private ───────────────────────────────────────────────────────
    _set(id, val)  { const el = document.getElementById(id); if (el) el.value = val; }
    _txt(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }
    _esc(s)        { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
}
