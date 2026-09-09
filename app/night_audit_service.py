"""
Night Audit Service
===================
Aggregates all end-of-day audit metrics for a single business date.

Sections:
  1.  audit_header()           — Property info, status, run metadata
  2.  occupancy_position()     — Room counts, occ%, arrivals/departures
  3.  reservation_reconciliation() — Status breakdown, no-shows, exceptions
  4.  revenue_summary()        — Room rev, extras, discounts, tax, gross
  5.  payment_summary()        — By mode, totals, refunds, net collection
  6.  folio_control()          — Open/closed folios, outstanding balances
  7.  room_charge_audit()      — Missing/incorrect rate detection
  8.  exception_report()       — Blockers (red) + Warnings (orange)
  9.  tax_snapshot()           — TaxLine aggregation by rate
  10. staff_shift_summary()    — Shift open/close, cash variance
  11. final_control()          — Reconciliation, can_close flag

Usage:
    svc = NightAuditService(date(2025, 3, 18))
    report = svc.full_report()
"""

from datetime import date, datetime
from sqlalchemy.orm import subqueryload
from app.models import (
    db, Room, RoomType, Reservation, Payment, ExtraCharge,
    TaxLine, Shift, ShiftAdjustment, NightAuditLog, NoShowLog,
    Settings, User, Guest, CheckInRecord
)
from app.services import calculate_stay_amount, get_business_date


# ---------------------------------------------------------------------------
# Reconciliation policy (DEF-005)
# ---------------------------------------------------------------------------

#: Single source of truth for the reconciliation tolerance, in rupees.
#:
#: Referenced by ``final_control`` (close reasons), by the Complete Audit
#: route, and by the executable invariant INV-R01. It was previously a bare
#: ``1.00`` repeated at each site, so the invariant could not honestly call it
#: "configured" and changing it meant finding every literal.
#:
#: The value is unchanged at 1.00 and deliberately so. ``tax_amount`` sums
#: TaxLine rows each quantised to 0.01, so worst-case drift is n x 0.005 for
#: n lines in a day; breaching 1.00 needs 200 tax lines on one date. The
#: property has 39 rooms and its busiest date on record carries 4. Widening
#: this widens the blind spot for no measured benefit.
RECONCILIATION_TOLERANCE = 1.00

#: Bumped whenever the meaning of ``reconciliation_difference`` changes, so a
#: stored snapshot can be told apart from one written under a different rule
#: without inferring it from the application version.
#:   1 - pre-W1-R9: accrual_net (pre-tax) compared against cash (tax-inclusive)
#:   2 - W1-R9 onwards: accrual_gross compared against cash, like for like
RECONCILIATION_ALGORITHM_VERSION = 2

#: Version of the reconciliation invariant contract (INV-R01).
RECONCILIATION_INVARIANT_VERSION = 'INV-R01@1.0'

#: Diagnostic codes returned by :func:`evaluate_reconciliation`.
RECON_OK = 'OK'
RECON_GAP = 'RECONCILIATION_GAP'
RECON_GROSS_NET = 'LIKELY_GROSS_NET_REGRESSION'


def evaluate_reconciliation(control, revenue, tolerance=None) -> dict:
    """Judge a day's reconciliation and name the probable cause.

    The single decision point for "does this day reconcile". ``final_control``
    calls it for its close reasons, the Complete Audit route calls it for its
    hard blocks, and INV-R01 calls it for historical verification, so the three
    cannot drift apart.

    The gross/net diagnostic exists because that regression has a signature.
    When revenue is compared pre-tax against tax-inclusive cash, the residual
    is not an arbitrary number - it is exactly the day's tax. Reporting
    "reconciliation gap Rs 57.15" sends someone hunting for a missing payment;
    reporting LIKELY_GROSS_NET_REGRESSION points at the accounting basis,
    which is where the fault actually is. This is the W1-R9 defect, and the
    check is what stops it reappearing unrecognised.

    Args:
        control: the dict returned by ``final_control()``
        revenue: the dict returned by ``revenue_summary()``
        tolerance: override in rupees; defaults to RECONCILIATION_TOLERANCE

    Returns a dict carrying ``code``, the figures behind the verdict, and a
    human-readable ``message``.
    """
    tol = RECONCILIATION_TOLERANCE if tolerance is None else float(tolerance)
    diff = _f(control.get('reconciliation_difference'))
    tax = _f(revenue.get('tax_amount')) if revenue else 0.0
    magnitude = abs(diff)

    out = {
        'code': RECON_OK,
        'difference': diff,
        'abs_difference': magnitude,
        'tolerance': tol,
        'tax_amount': tax,
        'within_tolerance': magnitude <= tol,
        'message': '',
    }
    if magnitude <= tol:
        out['message'] = f'Reconciled within Rs {tol:,.2f}'
        return out

    # A residual equal to the day's tax is the fingerprint of a net-vs-gross
    # comparison, not of missing money. Guard on tax > tol so a zero-tax day
    # (GST-exempt property) can never match this by arithmetic accident.
    if tax > tol and abs(magnitude - tax) <= tol:
        out['code'] = RECON_GROSS_NET
        out['message'] = (
            f'Reconciliation difference Rs {magnitude:,.2f} equals the day\'s '
            f'tax of Rs {tax:,.2f}. This is the signature of comparing pre-tax '
            f'revenue against tax-inclusive cash (the W1-R9 defect), not of a '
            f'missing payment. Check the accounting basis in '
            f'NightAuditService.final_control before investigating payments.')
        return out

    out['code'] = RECON_GAP
    out['message'] = f'Reconciliation difference Rs {magnitude:,.2f} — must be zero'
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _f(val) -> float:
    """Safe float conversion from Numeric/None."""
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _hotel_name() -> str:
    s = Settings.query.filter_by(key='hotel_name').first()
    return s.value if s else 'Hotel'


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------

class NightAuditService:
    """
    All data is loaded once in __init__ and reused across section methods.
    Call full_report() to get a single dict with all 11 sections.
    """

    def __init__(self, business_date: date):
        self.date = business_date

        # --- Rooms ---
        self._rooms = (Room.query
                       .options(subqueryload(Room.room_type))
                       .all())
        self._total_rooms = len(self._rooms)
        # Out-of-order rooms: belt-and-suspenders — the is_out_of_order
        # boolean OR a status text of Maintenance/Out of Order. The live
        # probe (KPI Phase 1) proved the two can drift apart.
        self._oor = [r for r in self._rooms
                     if r.is_out_of_order
                     or r.status in ('Maintenance', 'Out of Order', 'OutOfOrder')]
        # Sellable denominator: the canonical occupancy engine is the
        # single source so the Night Audit, Dashboard and every report
        # use the same number. (KPI Phase 1, Step 3.)
        from app.occupancy_engine import sellable_rooms as _engine_sellable_rooms
        self._sellable = _engine_sellable_rooms()

        # --- In-house reservations: arrival <= date AND departure > date ---
        _res_opts = [
            subqueryload(Reservation.payments).subqueryload(Payment.payment_mode),
            subqueryload(Reservation.extra_charges),
            subqueryload(Reservation.room),
            subqueryload(Reservation.guest),
            subqueryload(Reservation.room_type),
            subqueryload(Reservation.checkin_record),
            # Bridge rows — preloaded so occupancy_engine.count_distinct_rooms()
            # does not trigger an N+1 query per reservation.
            subqueryload(Reservation.room_links),
        ]
        self._inhouse = (Reservation.query
                         .options(*_res_opts)
                         .filter(Reservation.status.in_(['CheckedIn', 'CheckedOut']),
                                 Reservation.arrival_date <= business_date,
                                 Reservation.departure_date > business_date)
                         .all())

        # --- Today's expected arrivals ---
        self._arrivals = (Reservation.query
                          .options(*_res_opts)
                          .filter(Reservation.arrival_date == business_date)
                          .all())

        # --- Today's expected departures (only guests who actually checked in) ---
        self._departures = (Reservation.query
                            .options(*_res_opts)
                            .filter(Reservation.departure_date == business_date,
                                    Reservation.status.in_(['CheckedIn', 'CheckedOut']))
                            .all())

        # --- Payments posted on business date ---
        self._payments = (Payment.query
                          .options(subqueryload(Payment.payment_mode),
                                   subqueryload(Payment.reservation))
                          .filter(Payment.payment_date == business_date,
                                  Payment.is_voided == False)
                          .all())

        # --- Voided on business date ---
        from sqlalchemy import func as sqlfunc
        self._voided = (Payment.query
                        .filter(sqlfunc.date(Payment.voided_at) == business_date,
                                Payment.is_voided == True)
                        .all())

        # --- Extra charges posted on business date ---
        # Exclude night-audit room_rent rows — those are accounted for
        # in the room-revenue section. Including them here would double-
        # count room revenue in the night audit's "extras" breakdown.
        from sqlalchemy import or_ as _or_rr
        self._extra_charges = (ExtraCharge.query
                               .filter(ExtraCharge.charge_date == business_date,
                                       _or_rr(ExtraCharge.charge_type.is_(None),
                                              ExtraCharge.charge_type != 'room_rent'))
                               .all())

        # --- Tax lines for business date ---
        self._tax_lines = (TaxLine.query
                           .filter(TaxLine.charge_date == business_date)
                           .all())

        # --- Shifts that started on business date ---
        from sqlalchemy import func as sqlfunc2
        # Note: Shift.adjustments uses lazy='dynamic' so subqueryload cannot be applied.
        # Adjustments are fetched via .all() per shift in staff_shift_summary().
        self._shifts = (Shift.query
                        .options(subqueryload(Shift.user))
                        .filter(sqlfunc2.date(Shift.start_time) == business_date)
                        .all())

        # --- No-show logs for business date ---
        self._noshows = NoShowLog.query.filter_by(audit_date=business_date).all()

        # --- Cached section results (populated on first call) ---
        self._cache: dict = {}

    # -----------------------------------------------------------------------
    # Internal: deduplicated union of in-house + departures
    # -----------------------------------------------------------------------
    def _all_active(self):
        seen = set()
        result = []
        for r in self._inhouse + self._departures:
            if r.id not in seen:
                seen.add(r.id)
                result.append(r)
        return result

    # -----------------------------------------------------------------------
    # 1. Audit Header
    # -----------------------------------------------------------------------
    def audit_header(self) -> dict:
        log = NightAuditLog.query.filter_by(audit_date=self.date).order_by(
            NightAuditLog.run_at.desc()).first()
        return {
            'hotel_name': _hotel_name(),
            'business_date': self.date,
            'generated_at': datetime.now(),
            'audit_status': log.status if log else 'Pending',
            'run_at': log.run_at if log else None,
            'run_by': log.run_by.full_name if log and log.run_by else None,
            'blocker_count': log.blocker_count if log else 0,
            'warning_count': log.warning_count if log else 0,
            'completed_at': log.completed_at if log else None,
            'reopen_reason': log.reopen_reason if log else None,
            'log_id': log.id if log else None,
        }

    # -----------------------------------------------------------------------
    # 2. Occupancy and Room Position
    # -----------------------------------------------------------------------
    def occupancy_position(self) -> dict:
        checked_in = [r for r in self._inhouse if r.status == 'CheckedIn']
        # v2.2.15 — BUSINESS-DATE occupancy correction.
        # The Night Audit is a business-date close document: "occupied"
        # must mean "distinct physical rooms that held a guest on the
        # night of self.date". self._inhouse is ALREADY that population
        # (status in CheckedIn ∪ CheckedOut, arrival <= date < departure).
        # The pre-v2.2.15 code counted only the CheckedIn subset, which
        # dropped guests who occupied a room that night but have since
        # checked out — so occupancy collapsed to 0 once departures
        # completed, and revenue_summary() (which bills the full in-house
        # set) was then divided by that under-count, zeroing/inflating ADR.
        # Counting the full in-house set aligns occupancy with the
        # revenue basis. count_distinct_rooms() still dedupes by
        # room_id ∪ bridge, so this remains a DISTINCT physical-room
        # count, never a reservation-row count.
        from app.occupancy_engine import count_distinct_rooms
        occ_count = count_distinct_rooms(self._inhouse)
        occ_pct = round(occ_count / self._sellable * 100, 1) if self._sellable else 0.0

        vacant = [r for r in self._rooms if r.status == 'Vacant']
        dirty = [r for r in self._rooms if r.status == 'Dirty']

        # Count arrivals who checked in — include CheckedOut (checked in and departed same day)
        new_arrivals = [r for r in self._arrivals
                        if r.status in ('CheckedIn', 'CheckedOut')]
        checked_out_today = [r for r in self._departures if r.status == 'CheckedOut']
        stayovers = [r for r in checked_in
                     if r.arrival_date < self.date and r.departure_date > self.date]
        expected_not_checkedin = [r for r in self._arrivals
                                  if r.status in ('Reserved', 'Confirmed')]
        expected_not_checkedout = [r for r in self._departures
                                   if r.status == 'CheckedIn']

        return {
            'total_rooms': self._total_rooms,
            'sellable_rooms': self._sellable,
            'occupied': occ_count,
            'occ_pct': occ_pct,
            'vacant': len(vacant),
            'dirty': len(dirty),
            'out_of_order': len(self._oor),
            'new_arrivals_count': len(new_arrivals),
            'checked_out_today_count': len(checked_out_today),
            'stayovers': len(stayovers),
            'expected_not_checkedin': expected_not_checkedin,
            'expected_not_checkedout': expected_not_checkedout,
            'new_arrivals': new_arrivals,
            'checked_out_today': checked_out_today,
        }

    # -----------------------------------------------------------------------
    # 3. Reservation Reconciliation
    # -----------------------------------------------------------------------
    def reservation_reconciliation(self) -> dict:
        all_res = self._all_active()
        by_status: dict = {}
        for r in all_res:
            by_status[r.status] = by_status.get(r.status, 0) + 1

        missing_room = [r for r in self._arrivals
                        if r.status in ('Reserved', 'Confirmed') and not r.room_id]
        cancelled_today = [r for r in self._arrivals if r.status == 'Cancelled']
        no_shows = [r for r in self._arrivals if r.status == 'NoShow']

        # Reservations with status mismatch: room says Occupied but no CheckedIn res
        room_with_checkedin = {r.room_id for r in self._inhouse
                               if r.status == 'CheckedIn' and r.room_id}
        occupied_rooms_no_res = [
            rm for rm in self._rooms
            if rm.status == 'Occupied' and rm.id not in room_with_checkedin
        ]

        # v2.2.18 — classify ACTUAL arrivals (those that actually arrived
        # today, status CheckedIn or CheckedOut) by booking source so
        # reports stop labelling every checked-in guest as a "walk-in".
        # Pure aggregation over existing reservation.source field; no
        # change to booking, classification or accounting logic.
        _OTA_TOKENS = ('ota', 'mmt', 'easemytrip', 'booking',
                       'goibibo', 'agoda', 'expedia', 'cleartrip')
        _WALKIN_VALUES = ('walk-in', 'walkin', 'walk in')
        _actual_arrivals = [r for r in self._arrivals
                            if r.status in ('CheckedIn', 'CheckedOut')]
        arrivals_by_source = {'walk_in': 0, 'ota': 0, 'direct': 0}
        for r in _actual_arrivals:
            src = (getattr(r, 'source', None) or '').strip().lower()
            if src in _WALKIN_VALUES:
                arrivals_by_source['walk_in'] += 1
            elif any(tok in src for tok in _OTA_TOKENS):
                arrivals_by_source['ota'] += 1
            else:
                arrivals_by_source['direct'] += 1

        return {
            'by_status': by_status,
            'arrivals_today': len(self._arrivals),
            'arrivals_actual': len(_actual_arrivals),
            'arrivals_by_source': arrivals_by_source,
            'departures_today': len(self._departures),
            'noshows_count': len(no_shows) + len(self._noshows),
            'noshows': no_shows,
            'noshow_logs': self._noshows,
            'cancellations_today': len(cancelled_today),
            'missing_room_assignment': missing_room,
            'occupied_rooms_no_reservation': occupied_rooms_no_res,
        }

    # -----------------------------------------------------------------------
    # 4. Revenue Summary
    # -----------------------------------------------------------------------
    def revenue_summary(self) -> dict:
        # Room revenue: rate × 1 night for every reservation that was in-house
        # this night — includes CheckedOut guests (checked in AND out same day).
        billed_rooms = [r for r in self._inhouse
                        if r.status in ('CheckedIn', 'CheckedOut')]
        room_rev = sum(_f(r.rate_per_night) for r in billed_rooms)

        # Extra charges by category (using description as proxy for category)
        extra_by_cat: dict = {}
        early_ci_total = 0.0
        late_co_total  = 0.0
        for ec in self._extra_charges:
            ct = getattr(ec, 'charge_type', None)
            if ct == 'early_checkin':
                early_ci_total += _f(ec.amount)
            elif ct == 'late_checkout':
                late_co_total += _f(ec.amount)
            desc = (ec.description or 'Other').strip()
            cat = desc.split(' - ')[0].split(':')[0].strip() if desc else 'Other'
            extra_by_cat[cat] = extra_by_cat.get(cat, 0) + _f(ec.amount)
        extra_total = sum(extra_by_cat.values())

        # ── Tariff Adjustments (LEAKAGE / UPSELL) ────────────────────────────
        # Tracks deviation from standard tariff at booking time.
        # Uses stored DB fields; falls back to dynamic comparison for old records.
        leakage_total = 0.0
        leakage_list  = []
        upsell_total  = 0.0
        upsell_list   = []
        total_standard_tariff = 0.0

        for r in billed_rooms:
            adj_type = getattr(r, 'adjustment_type', None)
            adj_amt  = _f(getattr(r, 'adjustment_amount', None))
            standard = _f(getattr(r, 'standard_tariff', None))
            actual   = _f(r.rate_per_night)

            # If no stored adjustment (old record), compute dynamically
            if adj_type is None and standard == 0.0 and r.room_type:
                standard = _f(r.room_type.base_rate)
                if standard > 0 and actual < standard:
                    adj_type = 'LEAKAGE'
                    adj_amt  = standard - actual
                elif standard > 0 and actual > standard:
                    adj_type = 'UPSELL'
                    adj_amt  = actual - standard

            # Accumulate standard tariff total for Revenue Control Summary
            total_standard_tariff += standard if standard > 0 else actual

            room_num = r.room.room_number if r.room else '—'
            # Resolve check-in staff name from staff_user_id — safe N+1 acceptable for audit
            _ci_uid = (r.checkin_record.staff_user_id
                       if r.checkin_record and r.checkin_record.staff_user_id else None)
            if _ci_uid:
                _ci_user = db.session.get(User, _ci_uid)
                user_name = _ci_user.username if _ci_user else f'#{_ci_uid}'
            else:
                user_name = '—'

            if adj_type == 'LEAKAGE' and adj_amt > 0:
                leakage_total += adj_amt
                # ── Apr 2026 hardening: PREFER source-captured type ──
                # The financial action that created the leakage is now
                # responsible for stamping reservation.leakage_type at
                # the moment it happens (DISCOUNT at checkout discount,
                # RATE_OVERRIDE at check-in rate-below-standard, etc).
                # Only fall back to heuristic for legacy rows that
                # predate the source-capture columns. Heuristic-derived
                # types are flagged with `leakage_type_inferred=True`
                # so the UI can label them "Legacy inferred".
                _stored_ltype = (getattr(r, 'leakage_type', None) or '').strip()
                _disc = _f(getattr(r, 'discount_amount', None))
                _exp_tariff = _f(getattr(r, 'expected_tariff', None))
                _reason = (getattr(r, 'leakage_reason', '') or '').strip()
                if _stored_ltype:
                    _ltype = _stored_ltype
                    _ltype_inferred = False
                else:
                    # Legacy heuristic — only for rows without stored type
                    if _reason.lower().startswith('manual'):
                        _ltype = 'MANUAL_ADJUSTMENT'
                    elif _disc > 0 and abs((actual + _disc) - standard) < 1.0:
                        _ltype = 'DISCOUNT'
                    elif _exp_tariff > 0 and actual < _exp_tariff:
                        _ltype = 'RATE_OVERRIDE'
                    else:
                        _ltype = 'PRICING_GAP'
                    _ltype_inferred = True

                # ── Apr 2026 final tightening: leakage intent ─────
                # INTENTIONAL  — operator chose to give up revenue
                # UNINTENTIONAL — system / process gap
                _stored_intent = (getattr(r, 'leakage_intent', None) or '').strip()
                if _stored_intent:
                    _lintent = _stored_intent
                else:
                    # Map from type
                    if _ltype in ('DISCOUNT', 'WAIVER', 'MANUAL_ADJUSTMENT', 'RATE_OVERRIDE'):
                        _lintent = 'INTENTIONAL'
                    else:  # PRICING_GAP, MISSING_CHARGE
                        _lintent = 'UNINTENTIONAL'
                # Resolve authorized_by + folio_no for the row
                _folio_no = (f'F{r.guest_id:04d}' if r.guest_id else '—')
                # Resolve "authorized by" — prefer the source-captured
                # leakage_authorized_by_user_id; fall back to the older
                # discount_authorized_by free-text field for legacy rows.
                _auth_label = '—'
                _auth_uid = getattr(r, 'leakage_authorized_by_user_id', None)
                if _auth_uid:
                    try:
                        _au = db.session.get(User, _auth_uid)
                        _auth_label = _au.username if _au else f'#{_auth_uid}'
                    except Exception:
                        _auth_label = f'#{_auth_uid}'
                elif getattr(r, 'discount_authorized_by', None):
                    _auth_label = r.discount_authorized_by
                leakage_list.append({
                    'reservation': r,
                    'reservation_id': r.id,
                    'folio_no':       _folio_no,
                    'guest_name':     r.guest.name if r.guest else '—',
                    'room_no':        room_num,
                    'room':           room_num,    # legacy alias
                    'room_type':      r.room_type.name if r.room_type else '—',
                    'arrival_date':   r.arrival_date,
                    'standard_tariff': standard,
                    'offered_tariff': actual,
                    'actual_rate':    actual,      # legacy alias
                    'charged_amount': actual,
                    'leakage_amount': adj_amt,
                    'amount':         adj_amt,     # legacy alias
                    'leakage_type':   _ltype,
                    'leakage_type_inferred': _ltype_inferred,
                    'leakage_intent': _lintent,
                    'leakage_reason': _reason or None,
                    'leakage_created_at': getattr(r, 'leakage_created_at', None),
                    'authorized_by':  _auth_label,
                    'created_by':     user_name,
                    'user':           user_name,   # legacy alias
                })
            elif adj_type == 'UPSELL' and adj_amt > 0:
                upsell_total += adj_amt
                upsell_list.append({
                    'reservation': r,
                    'room': room_num,
                    'standard_tariff': standard,
                    'actual_rate': actual,
                    'amount': adj_amt,
                    'user': user_name,
                })

        # ── Post-billing Discounts ────────────────────────────────────────────
        # Explicit reductions authorised by management — reduces net revenue.
        discount_total = 0.0
        discount_list  = []
        for r in billed_rooms:
            disc = _f(getattr(r, 'discount_amount', None))
            if disc > 0:
                discount_total += disc
                discount_list.append({
                    'reservation': r,
                    'room': r.room.room_number if r.room else '—',
                    'discount': disc,
                    'reason': getattr(r, 'discount_reason', None) or '—',
                    'authorized_by': getattr(r, 'discount_authorized_by', None) or '—',
                    'given_by': getattr(r, 'discount_given_by', None) or '—',
                })

        tax_total = sum(_f(t.tax_amount) for t in self._tax_lines)
        # Accrual net = room rates + extras - discounts (pre-tax earned revenue)
        # Accrual gross = accrual net + tax liability
        accrual_net   = room_rev + extra_total - discount_total
        accrual_gross = accrual_net + tax_total

        return {
            'room_revenue': room_rev,
            'extra_charges_total': extra_total,
            'extra_by_category': extra_by_cat,
            'early_checkin_total': early_ci_total,
            'late_checkout_total': late_co_total,
            # Tariff adjustments
            'leakage_total': leakage_total,
            'leakage_list': leakage_list,
            'leakage_count': len(leakage_list),
            'upsell_total': upsell_total,
            'upsell_list': upsell_list,
            'upsell_count': len(upsell_list),
            'total_standard_tariff': total_standard_tariff,
            # Post-billing discounts
            'discount_total': discount_total,
            'discount_list': discount_list,
            'discount_count': len(discount_list),
            # Tax and revenue totals
            'tax_amount': tax_total,
            'accrual_net': accrual_net,           # earned revenue pre-tax
            'accrual_gross': accrual_gross,       # earned revenue incl. tax
            # Backward-compat aliases (remove once all templates migrated)
            'net_revenue': accrual_net,
            'gross_revenue': accrual_gross,
            'checked_in_count': len(billed_rooms),
        }

    # -----------------------------------------------------------------------
    # 5. Payment Summary
    # -----------------------------------------------------------------------
    def payment_summary(self) -> dict:
        # Split payments into direct vs OTA receivable based on
        # PaymentMode.category.  Direct payments are the only ones that
        # contribute to today's "cash collection" — OTA settlements are
        # tracked separately as receivables.
        #
        # Apr 2026 hardening: also bucket DIRECT payments by
        # ``payment_purpose`` so the audit clearly separates:
        #   * advance (liability — guest deposit on a future stay)
        #   * settlement (cash for stay-period revenue earned today)
        #   * credit_recovery (cash against post-checkout receivable)
        # Legacy NULL purpose is treated as 'settlement' so historical
        # rows are never re-bucketed retroactively.
        by_mode: dict = {}                # direct-payment modes only (for back-compat)
        direct_by_mode: dict = {}
        ota_by_head: dict = {}
        direct_total = 0.0
        ota_total = 0.0
        # Purpose buckets (DIRECT payments only — OTA stays separate)
        advance_received_total      = 0.0
        settlement_collected_total  = 0.0
        credit_recovered_total      = 0.0
        refund_issued_total         = 0.0

        for p in self._payments:
            pm = p.payment_mode
            mode_name = pm.name if pm else 'Unknown'
            category = getattr(pm, 'category', 'direct_payment') if pm else 'direct_payment'
            # Reversal entries (correction system) carry positive amount but
            # logically subtract; honour the sign here too.
            amt_signed = (-_f(p.amount)
                          if getattr(p, 'is_reversal', False) else _f(p.amount))
            amt = _f(p.amount)  # legacy aggregations keep gross

            if category == 'ota_receivable':
                slot = ota_by_head.setdefault(mode_name, {
                    'amount': 0.0, 'count': 0,
                    'code': getattr(pm, 'code', None) or ''})
                slot['amount'] += amt_signed
                slot['count'] += 1
                ota_total += amt_signed
            else:
                slot = direct_by_mode.setdefault(mode_name, {'amount': 0.0, 'count': 0})
                slot['amount'] += amt_signed
                slot['count'] += 1
                direct_total += amt_signed
                # Preserve legacy by_mode (direct-only for back-compat)
                by_mode.setdefault(mode_name, {'amount': 0.0, 'count': 0})
                by_mode[mode_name]['amount'] += amt_signed
                by_mode[mode_name]['count'] += 1
                purpose = (getattr(p, 'payment_purpose', None) or 'settlement').lower()
                if purpose == 'advance':
                    advance_received_total     += amt_signed
                elif purpose == 'credit_recovery':
                    credit_recovered_total     += amt_signed
                elif purpose == 'refund':
                    # Refund payments carry positive amount but is_reversal=True
                    # so amt_signed is already negative — flip it to a positive
                    # "refund issued" total for human reading.
                    refund_issued_total        += -amt_signed
                else:
                    settlement_collected_total += amt_signed

        total_refunds = sum(_f(p.amount) for p in self._voided)

        # Legacy advance_received fallback — keep the old computation as a
        # secondary signal in case the new payment_purpose column is
        # NULL across the historical payment table.
        advance_total_legacy = 0.0
        for r in self._all_active():
            if r.checkin_record and r.checkin_record.deposit_amount:
                ci = r.checkin_record
                if ci.checkin_date == self.date:
                    advance_total_legacy += _f(ci.deposit_amount)
        # Prefer the purpose-tagged number; fall back to legacy if zero.
        advance_total = (advance_received_total
                         if advance_received_total > 0 else advance_total_legacy)

        # Lifetime OTA outstanding (all non-voided OTA settlements to date)
        ota_outstanding = 0.0
        try:
            from app.ota_settlement_service import compute_ota_outstanding
            _ota_out = compute_ota_outstanding()
            ota_outstanding = float(_ota_out['total_amount'])
        except Exception:
            pass

        return {
            'by_mode': by_mode,                     # direct-payment only (legacy key)
            'direct_by_mode': direct_by_mode,
            'ota_by_head': ota_by_head,
            'total_collected': direct_total,        # DIRECT payments only
            'total_ota_settled': ota_total,         # NEW: OTA settlements today
            'ota_outstanding_lifetime': ota_outstanding,  # NEW: running OTA receivable
            'total_refunds': total_refunds,
            'net_collection': direct_total - total_refunds,
            # Legacy alias kept for templates that reference it.
            'advance_received': advance_total,
            # Apr 2026 — purpose-bucketed numbers (live + reportable).
            'advance_received_total':     advance_received_total,
            'settlement_collected_total': settlement_collected_total,
            'credit_recovered_total':     credit_recovered_total,
            'refund_issued_total':        refund_issued_total,
            'net_advance_today':          round(advance_received_total - refund_issued_total, 2),
            'payment_count': len(self._payments),
            'refund_count': len(self._voided),
            'payments': self._payments,
        }

    # -----------------------------------------------------------------------
    # 6. Folio and Ledger Control
    # -----------------------------------------------------------------------
    def attribution_control(self) -> dict:
        """Reservation-level and folio-attributed views of the same money.

        Phase 1 unit 1.7. The reservation remains the operational source for
        the stay; the folio is the financial owner of the transaction
        (AR-002 / ADR-003). Under Level 2 the two views must total the same,
        which is exactly what INV-A03 asserts — so this control shows them
        side by side rather than replacing one with the other.

        Rows carrying no folio are reported in their **own** bucket. They are
        never netted into the folio view and never presented as compliant
        folio activity: on the production database the unattributed rows are
        the eight D11 commissioning/test rows, preserved unchanged under
        FD-010 Option A. A non-zero unattributed bucket is surfaced as a
        warning, not silently averaged away (P11).
        """
        from app.models import Payment, ExtraCharge, Folio
        from app.services import (signed_payment_amount,
                                  signed_extra_charge_amount)

        folio_owner = dict(db.session.query(Folio.id, Folio.reservation_id).all())

        def split(rows, signed):
            reservation_view = 0.0
            folio_view = 0.0
            unattributed = 0.0
            unattributed_ids = []
            misrouted_ids = []
            for row in rows:
                amt = float(signed(row))
                reservation_view += amt
                if row.folio_id is None:
                    unattributed += amt
                    unattributed_ids.append(row.id)
                    continue
                folio_view += amt
                if folio_owner.get(row.folio_id) != row.reservation_id:
                    misrouted_ids.append(row.id)
            return {
                'reservation_view': round(reservation_view, 2),
                'folio_view': round(folio_view, 2),
                'unattributed': round(unattributed, 2),
                'unattributed_count': len(unattributed_ids),
                'unattributed_ids': unattributed_ids[:50],
                'misrouted_count': len(misrouted_ids),
                'misrouted_ids': misrouted_ids[:50],
            }

        payments = split([p for p in db.session.query(Payment).all()
                          if not p.is_voided], signed_payment_amount)
        charges = split(db.session.query(ExtraCharge).all(),
                        signed_extra_charge_amount)

        def agrees(b):
            return (abs(b['reservation_view'] - (b['folio_view'] + b['unattributed']))
                    < 0.01) and b['misrouted_count'] == 0

        unattributed_total = round(payments['unattributed'] + charges['unattributed'], 2)
        unattributed_count = payments['unattributed_count'] + charges['unattributed_count']
        misrouted_count = payments['misrouted_count'] + charges['misrouted_count']
        views_agree = agrees(payments) and agrees(charges)

        if misrouted_count:
            state, note = 'danger', (
                '%d financial row(s) are attributed to a folio belonging to a '
                'different reservation.' % misrouted_count)
        elif not views_agree:
            state, note = 'danger', (
                'The reservation-level and folio-attributed views of the same '
                'money do not reconcile.')
        elif unattributed_count:
            state, note = 'warning', (
                '%d historical financial row(s) totalling %.2f carry no folio '
                'attribution. These are preserved unchanged as commissioning / '
                'test activity (D11-F2, FD-010 Option A) and are NOT folio '
                'activity. INV-A02 continues to report them.'
                % (unattributed_count, unattributed_total))
        else:
            state, note = 'success', (
                'Every financial row is attributed to its reservation\'s '
                'billing folio; both views reconcile.')

        return {
            'payments': payments,
            'charges': charges,
            'views_agree': views_agree,
            'unattributed_total': unattributed_total,
            'unattributed_count': unattributed_count,
            'misrouted_count': misrouted_count,
            'state': state,
            'note': note,
        }

    def folio_control(self) -> dict:
        open_folios = []
        closed_folios = []
        checkout_outstanding = []

        for r in self._all_active():
            amounts = calculate_stay_amount(r)
            balance = amounts['balance']

            if r.status == 'CheckedIn':
                open_folios.append({'reservation': r, 'balance': balance,
                                    'total': amounts['total'], 'paid': amounts['paid']})
            elif r.status == 'CheckedOut':
                closed_folios.append({'reservation': r, 'balance': balance,
                                      'total': amounts['total'], 'paid': amounts['paid']})
                if balance > 0.01:
                    checkout_outstanding.append({'reservation': r, 'balance': balance,
                                                 'total': amounts['total'], 'paid': amounts['paid']})

        in_house_outstanding = sum(f['balance'] for f in open_folios if f['balance'] > 0)
        checkout_outstanding_total = sum(f['balance'] for f in checkout_outstanding)
        negative_folios = [f for f in open_folios + closed_folios if f['balance'] < -0.01]

        # ── Apr 2026 — Credit visibility ──────────────────────────────
        # Surface Individual Credit (post-checkout receivable) and
        # Company Credit (corporate receivable) as separate buckets so
        # the Night Audit makes it explicit:
        #     RECEIVABLE ≠ REVENUE.
        # Also count credit created today and credit recovered today.
        from app.models import Reservation, Payment, Company

        # Live Individual Credit (open + partial)
        ind_credit_total = 0.0
        ind_credit_count = 0
        # Apr 2026 final micro-gap: aging buckets for the Credit Risk
        # Summary panel. Computed against the audit date (NOT system
        # today) so the summary is correctly date-scoped.
        overdue_30_total  = 0.0
        overdue_30_count  = 0
        overdue_15_total  = 0.0
        overdue_15_count  = 0
        try:
            for r in (Reservation.query
                      .filter(Reservation.credit_amount > 0)
                      .all()):
                original  = float(r.credit_amount or 0)
                settled   = float(r.credit_settled_amount or 0)
                remaining = max(0.0, round(original - settled, 2))
                if remaining > 0.005:
                    ind_credit_total += remaining
                    ind_credit_count += 1
                    # Aging — days outstanding vs the audit date
                    approved_at = getattr(r, 'credit_approved_at', None)
                    approved_d  = approved_at.date() if approved_at else None
                    if approved_d is not None:
                        days_open = (self.date - approved_d).days
                        if days_open > 30:
                            overdue_30_total += remaining
                            overdue_30_count += 1
                        elif days_open > 15:
                            overdue_15_total += remaining
                            overdue_15_count += 1
        except Exception:
            pass

        # Company Credit (lifetime credit_used)
        company_credit_total = 0.0
        company_credit_count = 0
        try:
            for c in Company.query.filter(Company.credit_used > 0).all():
                amt = float(c.credit_used or 0)
                if amt > 0.005:
                    company_credit_total += amt
                    company_credit_count += 1
        except Exception:
            pass

        # Credit RECOVERED today — payments tagged credit_recovery posted today
        credit_recovered_today = 0.0
        try:
            for p in self._payments:
                if (getattr(p, 'payment_purpose', '') or '').lower() == 'credit_recovery':
                    credit_recovered_today += _f(p.amount)
        except Exception:
            pass

        # Credit CREATED today — Reservations whose credit was approved today
        credit_created_today = 0.0
        credit_created_count = 0
        try:
            for r in (Reservation.query
                      .filter(Reservation.credit_amount > 0,
                              Reservation.credit_approved_at.isnot(None))
                      .all()):
                if r.credit_approved_at and r.credit_approved_at.date() == self.date:
                    credit_created_today += float(r.credit_amount or 0)
                    credit_created_count += 1
        except Exception:
            pass

        total_credit_outstanding = ind_credit_total + company_credit_total

        # ── Forfeit Income today (advance-booking cancellations) ─────
        # Sum cancellation_amount_forfeited for reservations whose
        # cancellation_processed_at is on this audit date. Reported
        # SEPARATE from room revenue.
        forfeit_income_today = 0.0
        forfeit_count_today  = 0
        try:
            for r in (Reservation.query
                      .filter(Reservation.cancellation_amount_forfeited > 0,
                              Reservation.cancellation_processed_at.isnot(None))
                      .all()):
                if r.cancellation_processed_at and r.cancellation_processed_at.date() == self.date:
                    forfeit_income_today += float(r.cancellation_amount_forfeited or 0)
                    forfeit_count_today  += 1
        except Exception:
            pass

        return {
            'open_folios_count': len(open_folios),
            'closed_folios_count': len(closed_folios),
            'in_house_outstanding': in_house_outstanding,
            'checkout_outstanding_total': checkout_outstanding_total,
            'total_outstanding': in_house_outstanding + checkout_outstanding_total,
            'checkout_outstanding_list': checkout_outstanding,
            'negative_folios': negative_folios,
            'open_folio_list': open_folios,
            # Apr 2026 — credit (receivable) visibility
            'individual_credit_outstanding': ind_credit_total,
            'individual_credit_count':       ind_credit_count,
            'company_credit_outstanding':    company_credit_total,
            'company_credit_count':          company_credit_count,
            'total_credit_outstanding':      total_credit_outstanding,
            'credit_recovered_today':        credit_recovered_today,
            'credit_created_today':          credit_created_today,
            'credit_created_count_today':    credit_created_count,
            # Apr 2026 final micro-gap: Credit Risk Summary (aging)
            'credit_overdue_30_total':       overdue_30_total,
            'credit_overdue_30_count':       overdue_30_count,
            'credit_overdue_15_total':       overdue_15_total,
            'credit_overdue_15_count':       overdue_15_count,
            'credit_risky_account_count':    overdue_30_count + overdue_15_count,
            # Apr 2026 — Forfeit Income from advance-booking cancellations
            'forfeit_income_today':          forfeit_income_today,
            'forfeit_count_today':           forfeit_count_today,
        }

    # -----------------------------------------------------------------------
    # 7. Room Charge Posting Audit
    # -----------------------------------------------------------------------
    def room_charge_audit(self) -> dict:
        # Audit all billed rooms — CheckedIn (still in-house) and CheckedOut (departed today)
        billed_rooms = [r for r in self._inhouse
                        if r.status in ('CheckedIn', 'CheckedOut')]

        missing_rent = [r for r in billed_rooms
                        if not r.rate_per_night or _f(r.rate_per_night) == 0.0]

        # Incorrect tariff: >50% below base rate (significant variance)
        incorrect_tariff = []
        for r in billed_rooms:
            if r.room_type and r.rate_per_night:
                base = _f(r.room_type.base_rate)
                actual = _f(r.rate_per_night)
                if base > 0 and actual < base * 0.50:
                    incorrect_tariff.append({
                        'reservation': r,
                        'base_rate': base,
                        'actual_rate': actual,
                        'variance_pct': round((base - actual) / base * 100, 1),
                    })

        posted_count = len(billed_rooms) - len(missing_rent)

        return {
            'expected_count': len(billed_rooms),
            'posted_count': posted_count,
            'missing_count': len(missing_rent),
            'missing_rent': missing_rent,
            'incorrect_tariff': incorrect_tariff,
            'audit_ok': len(missing_rent) == 0 and len(incorrect_tariff) == 0,
        }

    # -----------------------------------------------------------------------
    # 8. Exception Report
    # -----------------------------------------------------------------------
    def exception_report(self) -> dict:
        blockers = []
        warnings = []

        # ── Blockers ──────────────────────────────────────────────────────

        # B1: Unsettled departures (departure date = today, still CheckedIn)
        for r in self._departures:
            if r.status == 'CheckedIn':
                room_num = r.room.room_number if r.room else '?'
                blockers.append({
                    'type': 'Unsettled Departure',
                    'icon': 'bi-door-open',
                    'detail': (f"Room {room_num} — {r.guest.name} "
                               f"(Booking {r.booking_reference}) — due out today, still checked in"),
                    'reservation_id': r.id,
                })

        # B2: Open bill after checkout
        for r in self._departures:
            if r.status == 'CheckedOut':
                amounts = calculate_stay_amount(r)
                if amounts['balance'] > 0.01:
                    blockers.append({
                        'type': 'Open Bill After Checkout',
                        'icon': 'bi-receipt-cutoff',
                        'detail': (f"Booking {r.booking_reference} — {r.guest.name} "
                                   f"— Outstanding ₹{amounts['balance']:,.0f}"),
                        'reservation_id': r.id,
                    })

        # B3: Missing room rent posting (CheckedIn or CheckedOut in-house)
        for r in self._inhouse:
            if r.status in ('CheckedIn', 'CheckedOut') and (not r.rate_per_night or _f(r.rate_per_night) == 0):
                room_num = r.room.room_number if r.room else '?'
                blockers.append({
                    'type': 'Missing Room Rent',
                    'icon': 'bi-tag-x',
                    'detail': (f"Room {room_num} — {r.guest.name} — Rate not set"),
                    'reservation_id': r.id,
                })

        # ── Warnings ──────────────────────────────────────────────────────

        # W1: Expected arrivals not checked in
        # Date-scope rule: every audit warning references the AUDIT date,
        # not the system "today". Wording matters — staff viewing a past
        # audit must see "Arrival on 26 Apr 2026", not the misleading
        # "Arrival today" which suggested the warning was live.
        for r in self._arrivals:
            if r.status in ('Reserved', 'Confirmed'):
                warnings.append({
                    'type': 'Expected Arrival Not Checked In',
                    'icon': 'bi-person-check',
                    'detail': (f"Booking {r.booking_reference} — {r.guest.name} "
                               f"— Arrival on {self.date.strftime('%d %b %Y')}, "
                               f"not yet checked in"),
                    'reservation_id': r.id,
                })

        # W2: High manual discount (>30% off base rate)
        for r in self._inhouse:
            if r.status == 'CheckedIn' and r.room_type and r.rate_per_night:
                base = _f(r.room_type.base_rate)
                actual = _f(r.rate_per_night)
                if base > 0 and actual < base * 0.70:
                    room_num = r.room.room_number if r.room else '?'
                    pct = round((base - actual) / base * 100, 1)
                    warnings.append({
                        'type': 'High Manual Discount',
                        'icon': 'bi-percent',
                        'detail': (f"Room {room_num} — ₹{actual:,.0f} vs base ₹{base:,.0f} "
                                   f"({pct}% off)"),
                        'reservation_id': r.id,
                    })

        # W3: Unclosed cashier shifts
        open_shifts = Shift.query.filter_by(status='Open').all()
        for s in open_shifts:
            user_name = s.user.full_name if s.user else f'User #{s.user_id}'
            warnings.append({
                'type': 'Unclosed Cashier Shift',
                'icon': 'bi-clock-history',
                'detail': f"Shift #{s.id} — {user_name} — {s.shift_type} — still open",
            })

        # W4: Room status mismatch
        room_with_checkedin = {r.room_id for r in self._inhouse
                               if r.status == 'CheckedIn' and r.room_id}
        for room in self._rooms:
            if room.id in room_with_checkedin and room.status in ('Vacant', 'Dirty'):
                warnings.append({
                    'type': 'Room Status Mismatch',
                    'icon': 'bi-house-exclamation',
                    'detail': (f"Room {room.room_number} — Has active CheckedIn reservation "
                               f"but room status is '{room.status}'"),
                })
            elif room.status == 'Occupied' and room.id not in room_with_checkedin:
                warnings.append({
                    'type': 'Room Status Mismatch',
                    'icon': 'bi-house-exclamation',
                    'detail': (f"Room {room.room_number} — Marked Occupied but no active "
                               f"reservation found"),
                })

        # W5/W6/W7: Staff revenue control alerts — leakage, high discount, frequent discount
        staff_ctrl = self._get('staff_revenue_control')
        _alert_type_labels = {
            'leakage':           'Staff Revenue — High Leakage',
            'discount_high':     'Staff Revenue — High Discount',
            'discount_frequent': 'Staff Revenue — Frequent Discounts',
        }
        for _a in staff_ctrl['alerts']:
            warnings.append({
                'type': _alert_type_labels.get(_a['type'], 'Staff Revenue Alert'),
                'icon': _a['icon'],
                'detail': _a['message'],
            })

        return {
            'blockers': blockers,
            'warnings': warnings,
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'can_close': len(blockers) == 0,
        }

    # -----------------------------------------------------------------------
    # 9. Tax Snapshot
    # -----------------------------------------------------------------------
    def tax_snapshot(self) -> dict:
        by_rate: dict = {}
        for t in self._tax_lines:
            key = f"{t.tax_type} @ {_f(t.tax_rate):.0f}%"
            by_rate.setdefault(key, {'taxable': 0.0, 'tax': 0.0, 'count': 0,
                                     'tax_type': t.tax_type, 'rate': _f(t.tax_rate)})
            by_rate[key]['taxable'] += _f(t.taxable_amount)
            by_rate[key]['tax'] += _f(t.tax_amount)
            by_rate[key]['count'] += 1

        total_taxable = sum(_f(t.taxable_amount) for t in self._tax_lines)
        total_tax = sum(_f(t.tax_amount) for t in self._tax_lines)
        exempt_count = sum(1 for t in self._tax_lines if t.is_exempted)

        return {
            'by_rate': dict(sorted(by_rate.items())),
            'total_taxable': total_taxable,
            'total_tax': total_tax,
            'total_lines': len(self._tax_lines),
            'exempt_lines': exempt_count,
            'has_data': len(self._tax_lines) > 0,
        }

    # -----------------------------------------------------------------------
    # 10. Staff / Shift Summary
    # -----------------------------------------------------------------------
    def staff_shift_summary(self) -> dict:
        shift_rows = []
        for s in self._shifts:
            adj_total = sum(_f(a.amount) for a in s.adjustments.all())
            variance = _f(s.variance)
            shift_rows.append({
                'shift': s,
                'user_name': s.user.full_name if s.user else f'User #{s.user_id}',
                'shift_type': s.shift_type or '—',
                'status': s.status,
                'opening_cash': _f(s.opening_cash),
                'expected_cash': _f(s.expected_cash),
                'declared_cash': _f(s.declared_closing_cash),
                'variance': variance,
                'variance_flag': abs(variance) > 50,  # flag if >₹50 variance
                'adjustments_total': adj_total,
                'close_notes': s.close_notes or '',
            })

        open_shifts = [r for r in shift_rows if r['status'] == 'Open']
        closed_shifts = [r for r in shift_rows if r['status'] in ('Closed', 'PendingApproval')]

        return {
            'shifts': shift_rows,
            'open_shifts': open_shifts,
            'closed_shifts': closed_shifts,
            'total_variance': sum(r['variance'] for r in shift_rows),
            'has_open_shifts': len(open_shifts) > 0,
        }

    # -----------------------------------------------------------------------
    # 11. Final Audit Control Block
    # -----------------------------------------------------------------------
    def final_control(self) -> dict:
        """Daily audit control block: does today's cash tie to today's charges?

        FINANCIAL INVARIANT (W1-R9)
            For a fully settled day, the reconciliation calculation MUST
            compare gross accrual with gross payments. Where both represent
            the same financial obligation, ``reconciliation_difference``
            shall be within the configured rounding tolerance (currently
            ₹1.00, the literal in the ``close_reasons`` check below).

        The invariant exists because the two operands are quoted on
        different bases elsewhere in the system: revenue is reported net of
        tax, cash is received gross of it. Any future edit that reintroduces
        a net-vs-gross comparison here will make every taxable day fail to
        close, and the failure amount will be that day's GST. If you are
        reading this because reconciliation is off by exactly the tax, that
        is the bug.
        """
        rev = self._get('revenue_summary')
        pay = self._get('payment_summary')
        folio = self._get('folio_control')
        exc = self._get('exception_report')

        # ── Daily Reconciliation ──────────────────────────────────────────
        # Reconciliation checks ONLY today's transactions:
        #   accrual_net  = revenue earned TODAY (room charges + extras - discounts)
        #   collected    = payments received TODAY
        #   today_outstanding = today's revenue not yet collected
        #
        # Formula: recon_diff = accrual_net - collected - today_outstanding
        # Where today_outstanding = accrual_net - collected (by definition)
        # So recon_diff should always be ~0 if the daily accounting is clean.
        #
        # However, payments can also be received for PREVIOUS days' balances
        # (advance payments, settling old dues). These make collected > accrual_net,
        # creating a negative "outstanding" which is actually correct.
        #
        # The correct daily check: does today's cash + today's charge postings
        # match up? We compare today's charges vs today's payments to detect
        # unposted charges or unrecorded payments.
        accrual_net = rev['accrual_net']
        total_payments = pay['total_collected']
        tax_liability = rev['tax_amount']

        # ── W1-R9: reconciliation basis ──────────────────────────────────
        # Cash received is GST-inclusive; accrual_net is pre-tax by
        # definition (see revenue_summary: accrual_gross = accrual_net +
        # tax_total). Comparing them mixed the bases, so the residual was
        # always the day's GST and every fully-settled taxable day reported
        # a reconciliation gap it could not close. accrual_gross is the
        # like-for-like comparand and is already computed upstream — no GST
        # is recalculated here.
        #
        # Both uses below must stay on the gross basis. Moving only the
        # recon_diff line would leave today_outstanding on the net basis and
        # yield recon_diff = accrual_gross - accrual_net = tax on every
        # PARTIALLY settled day — a positive false gap on days that are
        # currently clean. They are one correction, not two.
        #
        # Revenue reporting is unaffected: total_posted_revenue below stays
        # accrual_net, because revenue is reported net of tax.
        accrual_gross = rev['accrual_gross']

        # Today's outstanding = what was earned today but not paid today.
        # This is the DAILY delta, not the cumulative lifetime outstanding.
        today_outstanding = max(0, accrual_gross - total_payments)

        # Reconciliation difference: should be zero if balanced.
        # Negative = excess payments beyond today's revenue (settling old dues — OK)
        #
        # Known limitation, deliberately NOT addressed in W1-R9: because
        # today_outstanding is max(0, ...), this expression is identically 0
        # whenever accrual >= payments and negative otherwise, so it can
        # never report a positive value. Making the sign meaningful changes
        # what today_outstanding reports and is a separate semantic change.
        recon_diff = accrual_gross - total_payments - today_outstanding

        # Lifetime outstanding (for management reporting, NOT reconciliation)
        lifetime_outstanding = folio['total_outstanding']

        close_reasons = []
        if exc['blocker_count'] > 0:
            close_reasons.append(f"{exc['blocker_count']} blocker(s) unresolved")
        # Only block if there's a genuine reconciliation gap (not lifetime
        # balance). DEF-005: the verdict and the tolerance both come from
        # evaluate_reconciliation, so this site, the Complete Audit route and
        # INV-R01 cannot disagree about whether a day reconciles.
        _recon_verdict = evaluate_reconciliation(
            {'reconciliation_difference': recon_diff}, rev)
        if exc['can_close'] and not _recon_verdict['within_tolerance']:
            close_reasons.append(f"Reconciliation gap ₹{abs(recon_diff):,.2f}")

        return {
            'reconciliation_verdict': _recon_verdict,
            'total_posted_revenue': accrual_net,
            'tax_liability': tax_liability,
            'total_collected': total_payments,
            'total_outstanding': today_outstanding,
            'lifetime_outstanding': lifetime_outstanding,
            'reconciliation_difference': recon_diff,
            'blocker_count': exc['blocker_count'],
            'warning_count': exc['warning_count'],
            'can_close': len(close_reasons) == 0,
            'close_reasons': close_reasons,
        }

    # -----------------------------------------------------------------------
    # 12. Staff-wise Revenue Control
    # -----------------------------------------------------------------------
    def staff_revenue_control(self) -> dict:
        """Per-staff aggregation: leakage, upsell, discount, net_impact for the audit date."""
        LEAKAGE_THRESHOLD  = 3000.0   # ₹ per user — flag in alerts
        DISCOUNT_THRESHOLD = 1000.0   # ₹ per user — flag in alerts
        DISCOUNT_FREQ      = 3        # rooms — flag if same user gave discount to N+ rooms

        billed_rooms = [r for r in self._inhouse if r.status in ('CheckedIn', 'CheckedOut')]
        user_stats: dict = {}

        def _row(uname: str) -> dict:
            if uname not in user_stats:
                user_stats[uname] = {
                    'username': uname,
                    'checkin_rooms': 0,
                    'leakage': 0.0, 'leakage_rooms': 0,
                    'upsell': 0.0,  'upsell_rooms': 0,
                    'discount': 0.0, 'discount_rooms': 0,
                }
            return user_stats[uname]

        for r in billed_rooms:
            # Resolve check-in user — prefer stored checkin_by, fallback to CheckInRecord
            ci_by = getattr(r, 'checkin_by', None)
            if not ci_by:
                _ci_uid = (r.checkin_record.staff_user_id
                           if r.checkin_record and r.checkin_record.staff_user_id else None)
                if _ci_uid:
                    _ci_u = db.session.get(User, _ci_uid)
                    ci_by = _ci_u.username if _ci_u else f'#{_ci_uid}'
            ci_by = (ci_by or '—').strip() or '—'

            # Tariff adjustment — stored fields with fallback for old records
            adj_type = getattr(r, 'adjustment_type', None)
            adj_amt  = _f(getattr(r, 'adjustment_amount', None))
            standard = _f(getattr(r, 'standard_tariff', None))
            actual   = _f(r.rate_per_night)
            if adj_type is None and standard == 0.0 and r.room_type:
                standard = _f(r.room_type.base_rate)
                if standard > 0 and actual < standard:
                    adj_type = 'LEAKAGE'; adj_amt = standard - actual
                elif standard > 0 and actual > standard:
                    adj_type = 'UPSELL';  adj_amt = actual - standard

            u = _row(ci_by)
            u['checkin_rooms'] += 1
            if adj_type == 'LEAKAGE' and adj_amt > 0:
                u['leakage']       += adj_amt
                u['leakage_rooms'] += 1
            elif adj_type == 'UPSELL' and adj_amt > 0:
                u['upsell']       += adj_amt
                u['upsell_rooms'] += 1

            # Discount attributed to discount_given_by (may differ from ci_by)
            disc = _f(getattr(r, 'discount_amount', None))
            if disc > 0:
                disc_by = (getattr(r, 'discount_given_by', None) or ci_by or '—').strip() or '—'
                du = _row(disc_by)
                du['discount']       += disc
                du['discount_rooms'] += 1

        rows = []
        for u in user_stats.values():
            u['leakage']         = round(u['leakage'],  2)
            u['upsell']          = round(u['upsell'],   2)
            u['discount']        = round(u['discount'], 2)
            u['net_impact']      = round(u['upsell'] - u['leakage'] - u['discount'], 2)
            u['highest_leakage'] = False
            u['highest_upsell']  = False
            rows.append(u)

        rows.sort(key=lambda x: x['net_impact'])  # worst (most negative) first

        if rows:
            _hl = max(rows, key=lambda x: x['leakage'])
            _hu = max(rows, key=lambda x: x['upsell'])
            if _hl['leakage'] > 0:
                _hl['highest_leakage'] = True
            if _hu['upsell'] > 0:
                _hu['highest_upsell'] = True

        # Build alerts
        alerts = []
        for u in rows:
            if u['leakage'] >= LEAKAGE_THRESHOLD:
                alerts.append({
                    'type': 'leakage',
                    'level': 'danger',
                    'icon': 'bi-arrow-down-circle-fill',
                    'message': (f"{u['username']} has revenue leakage of "
                                f"₹{u['leakage']:,.0f} across "
                                f"{u['leakage_rooms']} room{'s' if u['leakage_rooms'] != 1 else ''}."),
                })
            if u['discount'] >= DISCOUNT_THRESHOLD:
                alerts.append({
                    'type': 'discount_high',
                    'level': 'warning',
                    'icon': 'bi-tag-fill',
                    'message': (f"{u['username']} gave total discounts of "
                                f"₹{u['discount']:,.0f} today."),
                })
            if u['discount_rooms'] >= DISCOUNT_FREQ:
                alerts.append({
                    'type': 'discount_frequent',
                    'level': 'warning',
                    'icon': 'bi-repeat',
                    'message': (f"{u['username']} applied discounts to "
                                f"{u['discount_rooms']} rooms today — review authorisation."),
                })

        return {
            'rows': rows,
            'alerts': alerts,
            'has_data': bool(rows),
            'leakage_threshold': LEAKAGE_THRESHOLD,
            'discount_threshold': DISCOUNT_THRESHOLD,
            'discount_freq_threshold': DISCOUNT_FREQ,
            'total_users': len(rows),
        }

    # -----------------------------------------------------------------------
    # Internal cache helper (prevents recomputing sections used by multiple callers)
    # -----------------------------------------------------------------------
    def _get(self, method_name: str):
        if method_name not in self._cache:
            self._cache[method_name] = getattr(self, method_name)()
        return self._cache[method_name]

    # -----------------------------------------------------------------------
    # 13. Revenue Risk Summary — merges RevenueAlert records for audit date
    # -----------------------------------------------------------------------
    def revenue_risk_summary(self) -> dict:
        """
        Section 13: pulls RevenueAlert records created on the audit date,
        summarises by type/severity and highlights top risk staff.
        """
        alerts_by_type  = {}
        alerts_by_staff = {}
        raw_alerts      = []

        try:
            from app.models import RevenueAlert
            from datetime import datetime, time as time_t
            day_start = datetime.combine(self.date, time_t.min)
            day_end   = datetime.combine(self.date, time_t.max)

            alerts = (
                RevenueAlert.query
                .filter(
                    RevenueAlert.created_at >= day_start,
                    RevenueAlert.created_at <= day_end,
                )
                .order_by(RevenueAlert.created_at.desc())
                .all()
            )

            for a in alerts:
                uname = a.user.username if a.user else 'unknown'
                # by type
                alerts_by_type.setdefault(a.alert_type, {'count': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0})
                alerts_by_type[a.alert_type]['count'] += 1
                alerts_by_type[a.alert_type][a.severity] = alerts_by_type[a.alert_type].get(a.severity, 0) + 1
                # by staff
                alerts_by_staff.setdefault(uname, {'total': 0, 'HIGH': 0})
                alerts_by_staff[uname]['total'] += 1
                if a.severity == 'HIGH':
                    alerts_by_staff[uname]['HIGH'] += 1
                # raw list (capped at 50 for the report)
                if len(raw_alerts) < 50:
                    raw_alerts.append({
                        'id':             a.id,
                        'alert_type':     a.alert_type,
                        'severity':       a.severity,
                        'message':        a.message,
                        'username':       uname,
                        'reservation_id': a.reservation_id,
                        'created_at':     a.created_at.strftime('%H:%M:%S'),
                        'resolved':       a.resolved,
                    })
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error('revenue_risk_summary failed: %s', exc)

        # Top risk staff (most HIGH alerts)
        top_risk = sorted(
            [{'username': k, **v} for k, v in alerts_by_staff.items()],
            key=lambda x: (-x['HIGH'], -x['total'])
        )[:5]

        total_alerts = sum(v['count'] for v in alerts_by_type.values())
        high_alerts  = sum(a['HIGH'] for a in (alerts_by_staff.values() if alerts_by_staff else []))

        return {
            'total_alerts':    total_alerts,
            'high_alerts':     high_alerts,
            'alerts_by_type':  alerts_by_type,
            'top_risk_staff':  top_risk,
            'raw_alerts':      raw_alerts,
        }

    # -----------------------------------------------------------------------
    # UI State presenter — state-driven labels/classes for the audit screen
    # -----------------------------------------------------------------------
    @staticmethod
    def ui_state(report: dict) -> dict:
        """
        Compute all UI display state for the Night Audit screen.

        Returns a flat dict consumed directly by the Jinja2 template.
        Every status-bearing element on the screen derives its colour,
        icon, label and badge class from this single function — so the
        template contains ZERO hard-coded colour decisions.

        State vocabulary: 'success' | 'warning' | 'danger'
        """
        control    = report.get('control', {})
        exceptions = report.get('exceptions', {})
        folio      = report.get('folio', {})
        revenue    = report.get('revenue', {})
        rev_risk   = report.get('revenue_risk', {})

        recon_diff      = float(control.get('reconciliation_difference', 0))
        recon_abs       = abs(recon_diff)
        blocker_count   = int(control.get('blocker_count', 0))
        warning_count   = int(control.get('warning_count', 0))
        outstanding     = float(control.get('total_outstanding', 0))
        leakage_total   = float(revenue.get('leakage_total', 0))
        high_alerts     = int(rev_risk.get('high_alerts', 0))
        total_alerts    = int(rev_risk.get('total_alerts', 0))

        # Overpayments = reservations with negative balance (overpaid)
        neg_folios    = folio.get('negative_folios', [])
        overpay_count = len(neg_folios) if isinstance(neg_folios, list) else 0

        # Unsettled checkout folios
        co_list          = folio.get('checkout_outstanding_list', [])
        unsettled_count  = len(co_list) if isinstance(co_list, list) else 0

        # Exception warning count may differ from control warning count — use max
        _ex_warning = int(report.get('exceptions', {}).get('warning_count', 0))
        _eff_warning = max(warning_count, _ex_warning)

        # ── Internal helper ────────────────────────────────────────────────────
        _ICONS    = {'success': 'bi-check-circle-fill',
                     'warning': 'bi-exclamation-triangle-fill',
                     'danger':  'bi-x-circle-fill'}
        _BADGE    = {'success': 'bg-success',
                     'warning': 'bg-warning text-dark',
                     'danger':  'bg-danger'}
        _TEXT     = {'success': 'text-success',
                     'warning': 'text-warning',
                     'danger':  'text-danger'}
        _BORDER   = {'success': 'border-success',
                     'warning': 'border-warning',
                     'danger':  'border-danger'}
        _HDR_BG   = {'success': 'bg-success text-white',
                     'warning': 'bg-warning text-dark',
                     'danger':  'bg-danger text-white'}
        # Success icons are intentionally muted so real issues stand out visually
        _ICON_CLS = {'success': 'text-success opacity-50',
                     'warning': 'text-warning',
                     'danger':  'text-danger'}

        def _row(state, label):
            return {
                'state':        state,
                'label':        label,
                'icon':         _ICONS[state],
                'icon_cls':     _ICON_CLS[state],
                'badge_class':  _BADGE[state],
                'text_class':   _TEXT[state],
                'border_class': _BORDER[state],
                'hdr_class':    _HDR_BG[state],
            }

        # ── Recon human-readable direction string ──────────────────────────────
        if recon_abs < 1:
            recon_display = '₹0 — Balanced'
        elif recon_diff < 0:
            recon_display = f'−₹{recon_abs:,.2f} (shortfall — check payments)'
        else:
            recon_display = f'+₹{recon_abs:,.2f} (surplus — unmatched collection)'

        # ── A. Reconciliation ──────────────────────────────────────────────────
        if recon_abs < 1:
            recon_row = _row('success', 'Reconciliation balanced')
        elif recon_diff < 0:
            recon_row = _row('danger',
                             f'Shortfall ₹{recon_abs:,.2f} — check payments')
        else:
            recon_row = _row('danger',
                             f'Surplus ₹{recon_abs:,.2f} — unmatched collection')

        # ── B. Overpayments ────────────────────────────────────────────────────
        if overpay_count == 0:
            overpay_row = _row('success', 'No overpayments pending')
        else:
            overpay_row = _row('danger',
                               f'{overpay_count} overpayment case(s) pending')

        # ── C. Checkout folio settlement ───────────────────────────────────────
        if unsettled_count == 0:
            checkout_row = _row('success', 'All checkout folios settled')
        else:
            checkout_row = _row('danger',
                                f'{unsettled_count} checkout folio(s) unsettled')

        # ── D. Blockers ────────────────────────────────────────────────────────
        if blocker_count == 0:
            blockers_row = _row('success', 'No unresolved blockers')
        else:
            blockers_row = _row('danger',
                                f'{blocker_count} unresolved blocker(s)')

        # ── E. Warnings ────────────────────────────────────────────────────────
        # v2.2.x operational-confidence: warnings are non-fatal REVIEW NOTES,
        # not closure blockers. Wording only — the threshold logic is unchanged.
        if _eff_warning == 0:
            warnings_row = _row('success', 'No review notes')
        else:
            warnings_row = _row('warning',
                                f'{_eff_warning} review note(s) to acknowledge')

        # ── F. Folio attribution (Phase 1 unit 1.7) ────────────────────────────
        # The folio-attributed view of the money beside the reservation-level
        # one. A disagreement is a danger row; historical unattributed rows
        # (D11, preserved under FD-010) are a review note, never presented as
        # compliant folio activity.
        _attr = report.get('attribution') or {}
        _attr_state = _attr.get('state', 'warning')
        attribution_row = _row(
            _attr_state,
            _attr.get('note', 'Folio attribution control unavailable'))

        # ── Aggregate danger / warning condition counts ────────────────────────
        danger_conditions = sum([
            1 if recon_abs >= 1      else 0,
            1 if overpay_count > 0   else 0,
            1 if unsettled_count > 0 else 0,
            1 if blocker_count > 0   else 0,
            1 if _attr_state == 'danger' else 0,
        ])
        warn_conditions = sum([
            1 if _eff_warning > 0  else 0,
            1 if leakage_total > 0 else 0,
            1 if _attr_state == 'warning' else 0,
        ])
        total_issues = danger_conditions + warn_conditions

        # ── Bottom summary banner ──────────────────────────────────────────────
        if danger_conditions > 0:
            banner = {
                'state':   'danger',
                'icon':    'bi-exclamation-octagon-fill',
                'message': (f'Audit not ready — {danger_conditions} '
                            f'issue(s) require action.'),
                'cls':     'alert-danger',
            }
        elif warn_conditions > 0:
            banner = {
                'state':   'warning',
                'icon':    'bi-info-circle-fill',
                'message': ('Financials balanced — review the notes below, '
                            'then complete the audit.'),
                'cls':     'alert-warning',
            }
        else:
            banner = {
                'state':   'success',
                'icon':    'bi-check-circle-fill',
                'message': 'All checks passed — financials balanced. Ready to close.',
                'cls':     'alert-success',
            }

        # ── Complete Audit button ──────────────────────────────────────────────
        if total_issues == 0:
            complete_btn = {
                'label': 'Complete Audit',
                'cls':   'btn-success',
                'state': 'ready',
            }
        elif danger_conditions == 0:
            complete_btn = {
                'label': f'Complete Audit ({total_issues} review note'
                         f'{"s" if total_issues != 1 else ""})',
                'cls':   'btn-success',
                'state': 'warnings',
            }
        else:
            complete_btn = {
                'label': f'Complete Audit ({danger_conditions} issue'
                         f'{"s" if danger_conditions != 1 else ""})',
                'cls':   'btn-dark',
                'state': 'issues',
            }

        # ── Revenue advisory badge ─────────────────────────────────────────────
        # Revenue-risk alerts are operational ADVISORIES — they never block
        # audit closure. Presented in amber (advisory), never red (blocker).
        # Wording/colour only; alert counts and thresholds are unchanged.
        if high_alerts > 0:
            risk_badge = {'state': 'warning',
                          'label': f'Revenue Advisory — High ({high_alerts})',
                          'cls':   'bg-warning text-dark'}
        elif total_alerts > 0:
            risk_badge = {'state': 'warning',
                          'label': f'Revenue Advisory ({total_alerts})',
                          'cls':   'bg-warning text-dark'}
        else:
            risk_badge = {'state': 'success',
                          'label': 'Revenue: Clear',
                          'cls':   'bg-success'}

        # ── Recon badge for top strip ──────────────────────────────────────────
        if recon_abs < 1:
            recon_badge = {'state': 'success',
                           'label': 'Recon: Balanced',
                           'cls':   'bg-success'}
        else:
            recon_badge = {'state': 'danger',
                           'label': f'Recon: ₹{recon_abs:,.0f}',
                           'cls':   'bg-danger'}

        # ── KPI card background classes ────────────────────────────────────────
        # Outstanding is informational (in-house guests owe this — expected).
        # Never color it danger/warning; use a neutral secondary chip.
        if leakage_total == 0:
            _leakage_cls = 'bg-success'
        elif leakage_total < 5000:
            _leakage_cls = 'bg-warning text-dark'
        else:
            _leakage_cls = 'bg-danger'

        kpi_classes = {
            'recon_diff':  'bg-success' if recon_abs < 1 else 'bg-danger',
            'outstanding': 'bg-secondary text-white',   # informational — never red/yellow
            'leakage':     _leakage_cls,
            'blockers':    'bg-success' if blocker_count == 0 else 'bg-danger',
            'warnings':    'bg-success' if _eff_warning == 0 else 'bg-warning text-dark',
        }

        # ── Risk tab colours ───────────────────────────────────────────────────
        total_alerts_cls = 'text-success' if total_alerts == 0 else 'text-danger'
        high_alerts_cls  = 'text-success' if high_alerts  == 0 else 'text-danger'

        # ── Outstanding colour — informational, not state-driven ───────────────
        outstanding_txt = 'text-secondary'

        # ── Readiness label near Complete Audit button ─────────────────────────
        if danger_conditions > 0:
            readiness = {
                'label': 'Audit Not Ready',
                'cls':   'text-danger fw-semibold',
                'icon':  'bi-x-circle-fill',
            }
        elif warn_conditions > 0:
            readiness = {
                'label': 'Audit Ready — Review Notes',
                'cls':   'text-success fw-semibold',
                'icon':  'bi-check-circle-fill',
            }
        else:
            readiness = {
                'label': 'Audit Ready',
                'cls':   'text-success fw-semibold',
                'icon':  'bi-check-circle-fill',
            }

        # ── Modal summary chip colours ─────────────────────────────────────────
        # Outstanding in modal = informational
        modal_outstanding_cls = 'text-secondary'
        modal_blockers_cls    = ('text-danger'  if blocker_count  > 0 else 'text-success')
        modal_warnings_cls    = ('text-warning' if _eff_warning   > 0 else 'text-success')

        return {
            # ── Row states (A–E) ──────────────────────────────────────────────
            'recon':    recon_row,
            'overpay':  overpay_row,
            'checkout': checkout_row,
            'attribution': attribution_row,
            'blockers': blockers_row,
            'warnings': warnings_row,
            # ── Banner ────────────────────────────────────────────────────────
            'banner':   banner,
            # ── Button ────────────────────────────────────────────────────────
            'complete_btn': complete_btn,
            # ── Readiness label ───────────────────────────────────────────────
            'readiness': readiness,
            # ── Top-strip badges ──────────────────────────────────────────────
            'risk_badge':   risk_badge,
            'recon_badge':  recon_badge,
            # ── KPI grid ──────────────────────────────────────────────────────
            'kpi': kpi_classes,
            # ── Counts (convenience) ──────────────────────────────────────────
            'danger_conditions': danger_conditions,
            'warn_conditions':   warn_conditions,
            'total_issues':      total_issues,
            'overpay_count':     overpay_count,
            'unsettled_count':   unsettled_count,
            # ── Inline text colours ───────────────────────────────────────────
            'total_alerts_cls':       total_alerts_cls,
            'high_alerts_cls':        high_alerts_cls,
            'outstanding_txt':        outstanding_txt,
            'recon_diff_txt':         'text-success' if recon_abs < 1 else 'text-danger',
            'recon_display':          recon_display,
            # ── Modal convenience classes ─────────────────────────────────────
            'modal_outstanding_cls':  modal_outstanding_cls,
            'modal_blockers_cls':     modal_blockers_cls,
            'modal_warnings_cls':     modal_warnings_cls,
        }

    # -----------------------------------------------------------------------
    # Full report — all 13 sections, cached
    # -----------------------------------------------------------------------
    def full_report(self) -> dict:
        return {
            'header': self._get('audit_header'),
            'occupancy': self._get('occupancy_position'),
            'reservations': self._get('reservation_reconciliation'),
            'revenue': self._get('revenue_summary'),
            'payments': self._get('payment_summary'),
            'folio': self._get('folio_control'),
            # Phase 1 unit 1.7 — the folio-attributed view of the money beside
            # the reservation-level one. Deliberately a section of its own
            # rather than a key inside folio_control: the D3 replay ledger
            # captures the figures of the sections named in
            # verification/replay/engines.py::NAS_SECTIONS, and adding a key
            # inside one of those would change every stored historical figure
            # set. This keeps the stored replay identical while still putting
            # the figure on the night-audit screen.
            'attribution': self._get('attribution_control'),
            'room_charges': self._get('room_charge_audit'),
            'exceptions': self._get('exception_report'),
            'tax': self._get('tax_snapshot'),
            'shifts': self._get('staff_shift_summary'),
            'control': self._get('final_control'),
            'staff_revenue': self._get('staff_revenue_control'),
            'revenue_risk':  self._get('revenue_risk_summary'),
            # Phase A — CEO OTA summary. Wrapped so a failure here can
            # never break the core audit; the extra section is optional
            # context for the CEO dashboard historical view.
            'ota_summary':   self._ota_summary_section(),
        }

    def _ota_summary_section(self) -> dict:
        """CEO-style OTA roll-up for this audit's business_date.

        Delegates to ``app.ceo_kpis`` so there is exactly one source of
        truth for funnel / channel mix / aging computations. Returns an
        empty dict on any failure so a stale/broken CEO helper cannot
        block night audit completion.
        """
        try:
            from app.ceo_kpis import (
                get_ota_funnel,
                get_ota_channel_mix,
                get_ota_receivable_aging,
            )
            return {
                'funnel': get_ota_funnel(self.date),
                'channel_mix': get_ota_channel_mix(self.date, mtd=True),
                'receivable_aging': get_ota_receivable_aging(as_of=self.date),
            }
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                'night_audit_service: ota_summary section failed: %s', exc)
            return {}
