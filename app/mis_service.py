"""
Front Office MIS Report — Aggregation Service
=============================================
Computes all KPIs and aggregations for the Front Office Management
Information System report.  Accepts a date range and returns a
fully-computed data dict that the Jinja template can render directly.

Calculation notes
-----------------
  Occupancy %  = occupied_room_nights / sellable_room_nights × 100
  ARR          = room_revenue / occupied_room_nights
  RevPAR       = room_revenue / sellable_room_nights
  Revenue      = Σ rate_per_night × nights_in_range  (CheckedIn / CheckedOut)
  Outstanding  = (room_total + extras) − non-voided payments collected
  Sellable rms = total_rooms − maintenance rooms
"""

from datetime import date, datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import subqueryload

from app.models import (
    db, Reservation, Room, RoomType, Guest,
    Payment, ExtraCharge, NightAuditLog, PaymentMode,
    CheckInRecord, GuestFeedback, User,
)
from app.services import get_business_date


class FrontOfficeMISService:
    """
    Compute all MIS report sections for the given date range.

    Usage::

        svc  = FrontOfficeMISService(start_date, end_date)
        data = svc.full_report()   # → dict with 10 section keys
    """

    def __init__(self, start_date: date, end_date: date):
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        self.start = start_date
        self.end   = end_date
        self.days  = (end_date - start_date).days + 1

        # ── Room inventory — single query, reused across sections ──────────
        self._rooms      = Room.query.order_by(Room.floor, Room.room_number).all()
        self._total_rms  = len(self._rooms)
        # OOO/maintenance count — boolean AND status text, because the two
        # can drift apart (the live probe proved it).
        self._oor_rms    = sum(1 for r in self._rooms
                               if r.is_out_of_order
                               or r.status in ('Maintenance', 'Out of Order', 'OutOfOrder'))
        # Sellable denominator from the canonical occupancy engine — the
        # single source of truth shared by every KPI surface.
        from app.occupancy_engine import sellable_rooms as _engine_sellable_rooms
        self._sellable   = _engine_sellable_rooms()

        # ── Reservations overlapping [start, end] — eager-loaded ────────────
        # Includes all statuses; filtering happens per section.
        self._res = (
            Reservation.query
            .options(
                subqueryload(Reservation.payments).subqueryload(Payment.payment_mode),
                subqueryload(Reservation.extra_charges),
                subqueryload(Reservation.room_type),
                subqueryload(Reservation.guest),
                subqueryload(Reservation.room),
            )
            .filter(
                Reservation.arrival_date   <= self.end,
                Reservation.departure_date >  self.start,
            )
            .all()
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _nights_in(self, res) -> int:
        """Night-count for a reservation that falls within [start, end]."""
        eff_start = max(res.arrival_date,   self.start)
        eff_end   = min(res.departure_date, self.end + timedelta(days=1))
        return max(0, (eff_end - eff_start).days)

    def _room_rev(self, res) -> float:
        """Room revenue attributed to the report period."""
        return float(res.rate_per_night) * self._nights_in(res)

    def _paid(self, res) -> float:
        return sum(float(p.amount) for p in (res.payments or []) if not p.is_voided)

    def _extras(self, res) -> float:
        # Exclude night-audit room_rent rows — those are already counted
        # as room revenue via rate_per_night × nights. Summing them here
        # would double-book room revenue into the MIS "extras" line.
        return sum(float(c.amount) for c in (res.extra_charges or [])
                   if (getattr(c, 'charge_type', None) or '') != 'room_rent')

    def _rev_res(self):
        """Reservations that generate room revenue (checked-in or checked-out)."""
        return [r for r in self._res if r.status in ('CheckedIn', 'CheckedOut')]

    # ─────────────────────────────────────────────────────────────────────────
    # Section 1 — Daily Business Summary
    # ─────────────────────────────────────────────────────────────────────────

    def business_summary(self) -> dict:
        """Total rooms, occupancy, ARR, RevPAR, revenue breakdown."""
        counts = {}
        for r in self._rooms:
            counts[r.status] = counts.get(r.status, 0) + 1

        rr = self._rev_res()
        # Room-nights from the canonical engine: distinct (room, night)
        # pairs, bridge-aware, deduped — never a raw per-reservation sum.
        from app.occupancy_engine import (
            occupied_room_nights as _engine_room_nights,
            occupied_rooms as _engine_occupied_rooms,
        )
        occ_nights  = _engine_room_nights(self.start, self.end)
        sell_rn     = self._sellable * self.days
        room_rev    = sum(self._room_rev(r) for r in rr)

        # Extra charges in range for revenue reservations.
        # Exclude night-audit room_rent rows — they are already counted
        # in room_rev (via rate_per_night × nights). Without this filter
        # MIS total_rev would double-count room revenue.
        from sqlalchemy import or_ as _or
        extra_q = (
            db.session
            .query(func.coalesce(func.sum(ExtraCharge.amount), 0))
            .join(Reservation, ExtraCharge.reservation_id == Reservation.id)
            .filter(
                ExtraCharge.charge_date >= self.start,
                ExtraCharge.charge_date <= self.end,
                Reservation.status.in_(('CheckedIn', 'CheckedOut')),
                _or(ExtraCharge.charge_type.is_(None),
                    ExtraCharge.charge_type != 'room_rent'),
            )
            .scalar()
        )
        extra_rev = float(extra_q)
        total_rev = room_rev + extra_rev

        occ_pct = round(occ_nights / sell_rn   * 100, 1) if sell_rn   else 0.0
        arr     = round(room_rev   / occ_nights,       2) if occ_nights else 0.0
        revpar  = round(room_rev   / sell_rn,          2) if sell_rn   else 0.0

        return {
            'total_rooms':     self._total_rms,
            'sellable_rooms':  self._sellable,
            'oor_rooms':       self._oor_rms,
            'occupied_rooms':  _engine_occupied_rooms(),
            'vacant_rooms':    counts.get('Vacant',      0),
            'dirty_rooms':     counts.get('Dirty',       0),
            'occ_room_nights': occ_nights,
            'sellable_rn':     sell_rn,
            'occupancy_pct':   occ_pct,
            'arr':             arr,
            'revpar':          revpar,
            'room_revenue':    round(room_rev,   2),
            'extra_revenue':   round(extra_rev,  2),
            'total_revenue':   round(total_rev,  2),
            'house_use':       0,   # not tracked in current schema
            'complimentary':   0,   # not tracked in current schema
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 2 — Check-in / Check-out Movement
    # ─────────────────────────────────────────────────────────────────────────

    def movement_summary(self) -> dict:
        """Arrivals, departures, no-shows, walk-ins, early/late."""

        def in_range(d):
            return self.start <= d <= self.end

        arr_exp  = sum(1 for r in self._res if in_range(r.arrival_date)
                       and r.status in ('Reserved', 'Confirmed', 'CheckedIn', 'NoShow', 'Cancelled'))
        arr_done = sum(1 for r in self._res if in_range(r.arrival_date)
                       and r.status == 'CheckedIn')
        dep_exp  = sum(1 for r in self._res if in_range(r.departure_date)
                       and r.status in ('CheckedIn', 'CheckedOut'))
        dep_done = sum(1 for r in self._res if in_range(r.departure_date)
                       and r.status == 'CheckedOut')
        no_shows = sum(1 for r in self._res if in_range(r.arrival_date)
                       and r.status == 'NoShow')
        cancels  = sum(1 for r in self._res if in_range(r.arrival_date)
                       and r.status == 'Cancelled')
        walk_ins = sum(1 for r in self._res if in_range(r.arrival_date)
                       and r.status in ('CheckedIn', 'CheckedOut')
                       and (r.source or '').lower() == 'walk-in')
        stayovers = sum(1 for r in self._res if r.status == 'CheckedIn'
                        and r.arrival_date < self.start and r.departure_date > self.end)
        inhouse   = sum(1 for r in self._res if r.status == 'CheckedIn')

        # Early check-in / late check-out via CheckInRecord timestamps
        early_ci = late_co = 0
        for r in self._res:
            ci = getattr(r, 'checkin_record', None)
            if not ci:
                continue
            if ci.checkin_date and ci.checkin_date.date() < r.arrival_date:
                early_ci += 1
            if ci.checkout_date and ci.checkout_date.date() > r.departure_date:
                late_co += 1

        return {
            'arrivals_expected':   arr_exp,
            'arrivals_done':       arr_done,
            'departures_expected': dep_exp,
            'departures_done':     dep_done,
            'no_shows':            no_shows,
            'cancellations':       cancels,
            'walk_ins':            walk_ins,
            'stayovers':           stayovers,
            'inhouse':             inhouse,
            'early_checkins':      early_ci,
            'late_checkouts':      late_co,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 3 — Booking Source Analysis
    # ─────────────────────────────────────────────────────────────────────────

    def source_analysis(self) -> list:
        """Per-source: bookings, room-nights, revenue, ADR."""
        src_map: dict = {}
        for r in self._rev_res():
            src = r.source or 'Other'
            if src not in src_map:
                src_map[src] = {'bookings': 0, 'room_nights': 0, 'revenue': 0.0}
            src_map[src]['bookings']    += 1
            n = self._nights_in(r)
            src_map[src]['room_nights'] += n
            src_map[src]['revenue']     += self._room_rev(r)

        rows = []
        for src, d in sorted(src_map.items()):
            rn = d['room_nights']
            rows.append({
                'source':      src,
                'bookings':    d['bookings'],
                'room_nights': rn,
                'revenue':     round(d['revenue'], 2),
                'adr':         round(d['revenue'] / rn, 2) if rn else 0.0,
            })
        return rows

    # ─────────────────────────────────────────────────────────────────────────
    # Section 4 — Room Status Report
    # ─────────────────────────────────────────────────────────────────────────

    def room_status(self) -> dict:
        """Current room inventory by status and by type."""
        by_type: dict = {}
        for r in self._rooms:
            rt = r.room_type.name if r.room_type else 'Unknown'
            if rt not in by_type:
                by_type[rt] = {
                    'total': 0, 'occupied': 0, 'vacant': 0,
                    'dirty': 0, 'oor': 0,
                    'base_rate': float(r.room_type.base_rate) if r.room_type else 0.0,
                }
            by_type[rt]['total'] += 1
            s = r.status
            if   s == 'Occupied':    by_type[rt]['occupied'] += 1
            elif s == 'Vacant':      by_type[rt]['vacant']   += 1
            elif s == 'Dirty':       by_type[rt]['dirty']    += 1
            elif s == 'Maintenance': by_type[rt]['oor']      += 1

        return {
            'vacant_clean': sum(1 for r in self._rooms if r.status == 'Vacant'),
            'vacant_dirty': sum(1 for r in self._rooms if r.status == 'Dirty'),
            'occupied':     sum(1 for r in self._rooms if r.status == 'Occupied'),
            'out_of_order': sum(1 for r in self._rooms if r.status == 'Maintenance'),
            'by_type':      by_type,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 5 — Cash & Billing Summary
    # ─────────────────────────────────────────────────────────────────────────

    def cash_billing(self) -> dict:
        """Payment collection by mode, billed vs collected, efficiency."""
        pmts = (
            Payment.query
            .filter(
                Payment.payment_date >= self.start,
                Payment.payment_date <= self.end,
                Payment.is_voided    == False,
            )
            .all()
        )

        by_mode: dict = {}
        from app.financial import money, round2, ZERO
        _total_collected = ZERO
        for p in pmts:
            mode = p.payment_mode.name if p.payment_mode else 'Unknown'
            _amt = money(p.amount)
            by_mode[mode]     = by_mode.get(mode, 0.0) + round2(_amt)
            _total_collected += _amt
        total_collected = round2(_total_collected)

        rr           = self._rev_res()
        total_billed = sum(self._room_rev(r) + self._extras(r) for r in rr)

        # Deposits received (from CheckInRecord) for arrivals in range
        deposits = float(
            db.session
            .query(func.coalesce(func.sum(CheckInRecord.deposit_amount), 0))
            .join(Reservation, CheckInRecord.reservation_id == Reservation.id)
            .filter(
                Reservation.arrival_date >= self.start,
                Reservation.arrival_date <= self.end,
            )
            .scalar()
        )

        # Refunds = voided payments in range
        refunds = float(
            db.session
            .query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.payment_date >= self.start,
                Payment.payment_date <= self.end,
                Payment.is_voided    == True,
            )
            .scalar()
        )

        # Pending = all outstanding balances on active/recent reservations
        pending = sum(
            max(0.0, self._room_rev(r) + self._extras(r) - self._paid(r))
            for r in rr
        )

        eff = round(total_collected / total_billed * 100, 1) if total_billed else 0.0

        return {
            'by_mode':         {k: round(v, 2) for k, v in sorted(by_mode.items())},
            'total_collected': round(total_collected, 2),
            'total_billed':    round(total_billed,    2),
            'deposits':        round(deposits,         2),
            'refunds':         round(refunds,          2),
            'pending_amount':  round(pending,          2),
            'collection_eff':  eff,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 6 — Guest Ledger & Outstanding
    # ─────────────────────────────────────────────────────────────────────────

    def guest_ledger(self) -> dict:
        """In-house and checked-out outstanding balances."""
        inhouse_rows, checkout_rows = [], []

        for r in self._rev_res():
            nights     = (r.departure_date - r.arrival_date).days
            room_total = float(r.rate_per_night) * nights
            extras     = self._extras(r)
            paid       = self._paid(r)
            balance    = round(room_total + extras - paid, 2)
            if balance <= 0:
                continue

            entry = {
                'reservation_id': r.id,
                'guest':    r.guest.name  if r.guest else 'Unknown',
                'phone':    r.guest.phone if r.guest else '',
                'room':     r.room.room_number if r.room else '—',
                'checkin':  r.arrival_date,
                'checkout': r.departure_date,
                'total':    round(room_total + extras, 2),
                'paid':     round(paid,    2),
                'balance':  balance,
                'source':   r.source or 'Other',
            }
            if r.status == 'CheckedIn':
                inhouse_rows.append(entry)
            else:
                checkout_rows.append(entry)

        t_in  = sum(e['balance'] for e in inhouse_rows)
        t_co  = sum(e['balance'] for e in checkout_rows)

        return {
            'inhouse':           sorted(inhouse_rows,  key=lambda x: x['balance'], reverse=True),
            'checkout':          sorted(checkout_rows, key=lambda x: x['balance'], reverse=True),
            'total_inhouse':     round(t_in,  2),
            'total_checkout':    round(t_co,  2),
            'grand_outstanding': round(t_in + t_co, 2),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 7 — Discount & Rate Variance
    # ─────────────────────────────────────────────────────────────────────────

    def discount_variance(self) -> dict:
        """Bookings sold below rack rate; total discount given."""
        rows = []
        total_disc = 0.0

        for r in self._res:
            if r.status not in ('CheckedIn', 'CheckedOut', 'Reserved', 'Confirmed'):
                continue
            if not r.room_type:
                continue
            rack   = float(r.room_type.base_rate)
            actual = float(r.rate_per_night)
            if rack <= 0 or actual >= rack:
                continue

            nights       = self._nights_in(r)
            disc_night   = rack - actual
            disc_total   = disc_night * nights
            total_disc  += disc_total

            rows.append({
                'reservation_id': r.id,
                'guest':     r.guest.name if r.guest else 'Unknown',
                'room':      r.room.room_number if r.room else '—',
                'room_type': r.room_type.name,
                'rack_rate': rack,
                'sold_at':   actual,
                'disc_pct':  round(disc_night / rack * 100, 1),
                'nights':    nights,
                'disc_amt':  round(disc_total, 2),
                'source':    r.source or 'Other',
            })

        return {
            'rows':   sorted(rows, key=lambda x: x['disc_amt'], reverse=True),
            'total':  round(total_disc, 2),
            'count':  len(rows),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 8 — Night Audit / Revenue Reconciliation
    # ─────────────────────────────────────────────────────────────────────────

    def night_audit_summary(self) -> dict:
        """Audit log vs system revenue; unclosed folios."""
        logs = (
            NightAuditLog.query
            .filter(
                NightAuditLog.audit_date >= self.start,
                NightAuditLog.audit_date <= self.end,
            )
            .order_by(NightAuditLog.audit_date)
            .all()
        )

        audit_rev  = sum(float(l.total_revenue) for l in logs)
        system_rev = float(
            db.session
            .query(func.coalesce(func.sum(Payment.amount), 0))
            .filter(
                Payment.payment_date >= self.start,
                Payment.payment_date <= self.end,
                Payment.is_voided    == False,
            )
            .scalar()
        )

        unclosed = sum(
            1 for r in self._res
            if r.status == 'CheckedOut'
            and (self._room_rev(r) + self._extras(r) - self._paid(r)) > 0.01
        )

        return {
            'logs':           logs,
            'dates_audited':  len(logs),
            'dates_missing':  self.days - len(logs),
            'audit_revenue':  round(audit_rev,  2),
            'system_revenue': round(system_rev, 2),
            'variance':       round(audit_rev - system_rev, 2),
            'unclosed_folios': unclosed,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Section 9 — Guest Feedback Snapshot
    # ─────────────────────────────────────────────────────────────────────────

    def feedback_snapshot(self) -> dict:
        """Aggregate guest ratings for reservations checked out in range."""
        try:
            fb = (
                GuestFeedback.query
                .join(Reservation, GuestFeedback.reservation_id == Reservation.id)
                .filter(
                    Reservation.departure_date >= self.start,
                    Reservation.departure_date <= self.end,
                )
                .all()
            )
            if not fb:
                return {'available': False}

            n   = len(fb)
            avg = round(sum(f.rating for f in fb) / n, 1)
            neg = sum(1 for f in fb if f.negative_flag)
            rec = sum(1 for f in fb if f.would_recommend)

            return {
                'available':  True,
                'total':      n,
                'avg_rating': avg,
                'negative':   neg,
                'rec_count':  rec,
                'rec_pct':    round(rec / n * 100, 1),
                'neg_pct':    round(neg / n * 100, 1),
            }
        except Exception:
            return {'available': False}

    # ─────────────────────────────────────────────────────────────────────────
    # Section 10 — Staff Performance Snapshot
    # ─────────────────────────────────────────────────────────────────────────

    def staff_performance(self) -> dict:
        """Check-ins handled per staff member."""
        try:
            rows = (
                db.session
                .query(
                    CheckInRecord.staff_user_id,
                    func.count(CheckInRecord.id).label('checkins'),
                )
                .join(Reservation, CheckInRecord.reservation_id == Reservation.id)
                .filter(
                    Reservation.arrival_date >= self.start,
                    Reservation.arrival_date <= self.end,
                )
                .group_by(CheckInRecord.staff_user_id)
                .all()
            )
            if not rows:
                return {'available': False}

            staff = []
            for uid, ci in rows:
                u = User.query.get(uid)
                staff.append({
                    'name':     u.full_name if u else f'User #{uid}',
                    'role':     u.role      if u else '—',
                    'checkins': ci,
                })

            return {
                'available': True,
                'staff': sorted(staff, key=lambda x: x['checkins'], reverse=True),
            }
        except Exception:
            return {'available': False}

    # ─────────────────────────────────────────────────────────────────────────
    # Full report
    # ─────────────────────────────────────────────────────────────────────────

    def full_report(self) -> dict:
        """Compute and return all 10 MIS sections as a structured dict."""
        return {
            'meta': {
                'start_date':   self.start,
                'end_date':     self.end,
                'days':         self.days,
                'generated_at': datetime.utcnow(),
            },
            'business':  self.business_summary(),
            'movement':  self.movement_summary(),
            'sources':   self.source_analysis(),
            'rooms':     self.room_status(),
            'billing':   self.cash_billing(),
            'ledger':    self.guest_ledger(),
            'discounts': self.discount_variance(),
            'audit':     self.night_audit_summary(),
            'feedback':  self.feedback_snapshot(),
            'staff':     self.staff_performance(),
        }
