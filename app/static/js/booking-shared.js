/**
 * booking-shared.js
 * Shared utilities for check-in, reservation, and bulk-booking modals.
 * Loaded once globally; each modal calls the relevant helpers.
 */

/* ── Date helpers ─────────────────────────────────────────────── */

/**
 * Calculate nights between two ISO date strings (YYYY-MM-DD).
 * Returns 0 if invalid or departure ≤ arrival.
 */
function bsCalcNights(arrival, departure) {
    if (!arrival || !departure) return 0;
    const a = new Date(arrival + 'T00:00:00');
    const d = new Date(departure + 'T00:00:00');
    const diff = Math.round((d - a) / 86400000);
    return diff > 0 ? diff : 0;
}

/* ── Room-rate registry ──────────────────────────────────────── */

let _BS_RATES = {}; // { room_type_id (str): base_rate (number) }

/** Called once per page with server-side room type rates. */
function bsSetRoomRates(ratesObj) {
    _BS_RATES = ratesObj;
}

/** Return base rate for a room type id (falls back to 0). */
function bsGetRate(roomTypeId) {
    return Number(_BS_RATES[String(roomTypeId)] || 0);
}

/* ── Price helpers ───────────────────────────────────────────── */

/** Row subtotal = qty × rate × nights. */
function bsRowSubtotal(qty, rate, nights) {
    const q = Math.max(0, Number(qty) || 0);
    const r = Math.max(0, Number(rate) || 0);
    const n = Math.max(0, Number(nights) || 0);
    return q * r * n;
}

/* ── Formatting ──────────────────────────────────────────────── */

function bsFmtRupee(amount) {
    return '₹' + Number(amount).toLocaleString('en-IN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    });
}

/* ── Validation helpers ──────────────────────────────────────── */

/**
 * Show or hide an inline error element.
 * @param {string} elId - element id to show/hide
 * @param {string|null} msg - message to show, or null/'' to hide
 */
function bsShowError(elId, msg) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (msg) {
        el.textContent = msg;
        el.classList.remove('d-none');
    } else {
        el.classList.add('d-none');
        el.textContent = '';
    }
}

/* ── GuestSearchForm extension: fill extra fields ────────────── */

/**
 * After selecting a guest, optionally populate extra fields beyond
 * the standard first_name / last_name / phone / email.
 * Pass a map of { fieldId: guestPropOrCallback }.
 */
function bsFillGuestExtras(guest, extraMap) {
    for (const [elId, prop] of Object.entries(extraMap)) {
        const el = document.getElementById(elId);
        if (!el) continue;
        const val = typeof prop === 'function' ? prop(guest) : guest[prop];
        if (val !== undefined && val !== null) el.value = val;
    }
}
