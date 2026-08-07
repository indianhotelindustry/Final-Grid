"""
OTA Payout Reconciliation — Phase 2
=====================================
Sits ON TOP of the existing OTA receivable system. This module is
purely additive — it does not modify ``ota_settlement_service``,
``compute_ota_outstanding``, ``Payment``, or any night-audit code.

What this layer adds
--------------------
The existing system tracks receivable POSTINGS (sum of OTA
receivable Payment rows = "we are owed this much"). What it cannot
answer is "did the OTA actually pay us?". This module records the
**actual payouts** received via ``OTAPayout`` rows, and computes:

    pending(channel) = receivable_posted(channel) - payouts_received(channel)
    delay(channel)   = today - (last_payout_date + cycle_days)

Reconciliation is per-channel (using ``Reservation.ota_channel`` —
the authoritative column from migration 7.3.0).

Public API
----------
    record_payout(...)                          -> OTAPayout
    validate_payout_amounts(...)                -> list[str]
    get_ota_payouts_total(channel, start, end)  -> dict
    get_ota_revenue_total(channel, start, end)  -> dict
    get_ota_pending(channel=None)               -> dict | list[dict]
    get_payout_cycle_days(channel)              -> int
    get_expected_payout_date(payment_date, channel) -> date
    get_reconciliation_summary(start, end)      -> list[dict]
    get_payout_status_for_ceo()                 -> list[dict]

All money is returned as plain ``float`` (rupees). All dates are
``date`` objects.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from app.models import (
    db, OTAPayout, Payment, PaymentMode, Reservation, Settings,
)

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _f(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _channel_slug(channel: str) -> str:
    """Convert a channel name to a Settings-key suffix.

    'Booking.com' → 'booking_com', 'MakeMyTrip' → 'makemytrip', etc.
    """
    if not channel:
        return 'default'
    s = channel.strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != '_':
            out.append('_')
    return ''.join(out).strip('_') or 'default'


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────

def validate_payout_amounts(gross: Any, commission: Any,
                            tax: Any, net: Any) -> list[str]:
    """Service-level validation. Returns a list of error strings.
    Empty list means the inputs are valid. The DB has CHECK constraints
    that mirror these rules — this exists to fail fast with friendly
    messages before we hit the database.
    """
    errors: list[str] = []
    g = _f(gross, default=-1)
    c = _f(commission, default=-1)
    t = _f(tax, default=-1)
    n = _f(net, default=-1)

    if g < 0:
        errors.append('Gross amount must be a non-negative number.')
    if c < 0:
        errors.append('Commission amount must be a non-negative number.')
    if t < 0:
        errors.append('Tax deducted must be a non-negative number.')
    if n < 0:
        errors.append('Net paid must be a non-negative number.')
    if g >= 0 and n >= 0 and n > g:
        errors.append('Net paid cannot exceed gross amount.')
    return errors


def validate_payout_date(payout_date: Any) -> str | None:
    """Return an error string or None if the date is valid."""
    if payout_date is None:
        return 'Payout date is required.'
    if isinstance(payout_date, str):
        try:
            payout_date = date.fromisoformat(payout_date)
        except ValueError:
            return 'Payout date must be a valid date (YYYY-MM-DD).'
    if not isinstance(payout_date, date):
        return 'Payout date must be a valid date.'
    if payout_date > date.today() + timedelta(days=1):
        # Tolerate same-day off-by-one for timezone slop, but block
        # obviously-future entries — usually a typo.
        return 'Payout date cannot be in the future.'
    return None


# ──────────────────────────────────────────────────────────────────────
# Payout entry
# ──────────────────────────────────────────────────────────────────────

def record_payout(*, ota_channel: str, payout_date,
                  gross_amount, commission_amount=0,
                  tax_deducted=0, net_paid=None,
                  reference_number: str | None = None,
                  remarks: str | None = None,
                  created_by_user_id: int | None = None) -> OTAPayout:
    """Persist a new ``OTAPayout``. Caller is responsible for catching
    ``ValueError`` (validation failure) and rolling back if needed.

    If ``net_paid`` is omitted, it is computed as
    ``gross_amount - commission_amount - tax_deducted`` and clamped
    to 0 (defensive — the DB CHECK still enforces non-negative).
    """
    if not ota_channel or not str(ota_channel).strip():
        raise ValueError('OTA channel is required.')

    date_err = validate_payout_date(payout_date)
    if date_err:
        raise ValueError(date_err)
    if isinstance(payout_date, str):
        payout_date = date.fromisoformat(payout_date)

    if net_paid is None:
        net_paid = max(0.0, _f(gross_amount) - _f(commission_amount)
                       - _f(tax_deducted))

    errors = validate_payout_amounts(gross_amount, commission_amount,
                                     tax_deducted, net_paid)
    if errors:
        raise ValueError('; '.join(errors))

    payout = OTAPayout(
        ota_channel=ota_channel.strip(),
        payout_date=payout_date,
        reference_number=(reference_number or '').strip() or None,
        gross_amount=Decimal(str(_f(gross_amount))),
        commission_amount=Decimal(str(_f(commission_amount))),
        tax_deducted=Decimal(str(_f(tax_deducted))),
        net_paid=Decimal(str(_f(net_paid))),
        remarks=(remarks or '').strip() or None,
        created_by_user_id=created_by_user_id,
    )
    db.session.add(payout)
    db.session.flush()
    return payout


# ──────────────────────────────────────────────────────────────────────
# Aggregations — payouts (this layer)
# ──────────────────────────────────────────────────────────────────────

def get_ota_payouts_total(channel: str | None = None,
                          start: date | None = None,
                          end: date | None = None) -> dict:
    """Sum of payouts for ``channel`` within ``[start, end]``.

    All filters are optional. ``channel=None`` means all channels;
    omitting ``start`` or ``end`` skips the date filter on that side.
    """
    q = db.session.query(
        func.coalesce(func.sum(OTAPayout.gross_amount), 0),
        func.coalesce(func.sum(OTAPayout.commission_amount), 0),
        func.coalesce(func.sum(OTAPayout.tax_deducted), 0),
        func.coalesce(func.sum(OTAPayout.net_paid), 0),
        func.count(OTAPayout.id),
    )
    if channel:
        q = q.filter(OTAPayout.ota_channel == channel)
    if start:
        q = q.filter(OTAPayout.payout_date >= start)
    if end:
        q = q.filter(OTAPayout.payout_date <= end)

    g, c, t, n, count = q.one()
    return {
        'gross': _f(g),
        'commission': _f(c),
        'tax': _f(t),
        'net': _f(n),
        'count': int(count or 0),
    }


# ──────────────────────────────────────────────────────────────────────
# Aggregations — receivable revenue (read-only over existing system)
# ──────────────────────────────────────────────────────────────────────

def get_ota_revenue_total(channel: str | None = None,
                          start: date | None = None,
                          end: date | None = None) -> dict:
    """Sum of OTA RECEIVABLE postings for ``channel`` within range.

    Reads the existing Payment table (category='ota_receivable') and
    joins to Reservation to get the canonical ``ota_channel``. Does
    not modify any existing data — purely a read query that lives in
    this new module to keep the reconciliation layer self-contained.

    Voided payments are excluded.
    """
    q = (db.session.query(func.coalesce(func.sum(Payment.amount), 0),
                          func.count(Payment.id))
         .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
         .join(Reservation, Payment.reservation_id == Reservation.id)
         .filter(PaymentMode.category == 'ota_receivable',
                 Payment.is_voided == False))
    if channel:
        q = q.filter(Reservation.ota_channel == channel)
    if start:
        q = q.filter(Payment.payment_date >= start)
    if end:
        q = q.filter(Payment.payment_date <= end)

    total, count = q.one()
    return {'total': _f(total), 'count': int(count or 0)}


# ──────────────────────────────────────────────────────────────────────
# Pending = receivable - payouts (lifetime, per channel)
# ──────────────────────────────────────────────────────────────────────

def _all_known_channels() -> list[str]:
    """Channels that have at least one receivable posting OR one payout.

    Used so the reconciliation report still shows a row for a channel
    that hasn't been paid out at all (pending = full revenue).
    """
    rev_channels = (
        db.session.query(Reservation.ota_channel)
        .join(Payment, Payment.reservation_id == Reservation.id)
        .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
        .filter(PaymentMode.category == 'ota_receivable',
                Payment.is_voided == False,
                Reservation.ota_channel.isnot(None))
        .distinct().all())
    payout_channels = (db.session.query(OTAPayout.ota_channel)
                       .distinct().all())
    seen = set()
    out = []
    for (ch,) in rev_channels + payout_channels:
        if ch and ch not in seen:
            seen.add(ch)
            out.append(ch)
    return sorted(out)


def get_ota_pending(channel: str | None = None) -> dict:
    """Lifetime pending = receivable - net_paid_payouts.

    If ``channel`` is given → returns one dict for that channel.
    If ``channel`` is None → returns ``{'by_channel': [...], 'total_pending': float}``.
    """
    if channel:
        rev = get_ota_revenue_total(channel=channel)['total']
        pay = get_ota_payouts_total(channel=channel)['net']
        return {
            'channel': channel,
            'revenue': round(rev, 2),
            'paid': round(pay, 2),
            'pending': round(rev - pay, 2),
        }

    rows = []
    total = 0.0
    for ch in _all_known_channels():
        rev = get_ota_revenue_total(channel=ch)['total']
        pay = get_ota_payouts_total(channel=ch)['net']
        pending = round(rev - pay, 2)
        rows.append({
            'channel': ch,
            'revenue': round(rev, 2),
            'paid': round(pay, 2),
            'pending': pending,
        })
        total += pending
    rows.sort(key=lambda r: r['pending'], reverse=True)
    return {'by_channel': rows, 'total_pending': round(total, 2)}


# ──────────────────────────────────────────────────────────────────────
# Payout cycle (configurable, per channel)
# ──────────────────────────────────────────────────────────────────────

DEFAULT_CYCLE_DAYS = 30


def get_payout_cycle_days(channel: str | None) -> int:
    """Read the configured payout cycle for ``channel`` from Settings.

    Looks up ``ota_cycle_<slug>`` first, then ``ota_cycle_default``,
    finally falls back to ``DEFAULT_CYCLE_DAYS``. Returns an int.
    """
    keys = []
    if channel:
        keys.append(f'ota_cycle_{_channel_slug(channel)}')
    keys.append('ota_cycle_default')

    for k in keys:
        try:
            row = Settings.query.filter_by(key=k).first()
            if row and (row.value or '').strip():
                try:
                    return int(row.value)
                except (TypeError, ValueError):
                    log.warning('Settings key %s has non-int value %r',
                                k, row.value)
        except Exception as exc:
            log.warning('Settings lookup for %s failed: %s', k, exc)
    return DEFAULT_CYCLE_DAYS


def get_expected_payout_date(payment_date: date,
                             channel: str | None) -> date:
    """Given a receivable-posting date, when does the OTA owe us payment?"""
    return payment_date + timedelta(days=get_payout_cycle_days(channel))


# ──────────────────────────────────────────────────────────────────────
# Per-channel reconciliation summary (used by report + CEO dashboard)
# ──────────────────────────────────────────────────────────────────────

def _last_payout_date(channel: str) -> date | None:
    row = (db.session.query(func.max(OTAPayout.payout_date))
           .filter(OTAPayout.ota_channel == channel)
           .one())
    return row[0] if row and row[0] else None


def _oldest_unreconciled_payment_date(channel: str) -> date | None:
    """Best-effort watermark for the oldest receivable that has not
    been paid. Phase 2 simplification: we don't link payouts to
    individual Payment rows, so we use the OLDEST payment_date for the
    channel as the watermark whenever pending > 0. Good enough for
    delay reporting; precise reconciliation is Phase 3."""
    row = (db.session.query(func.min(Payment.payment_date))
           .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
           .join(Reservation, Payment.reservation_id == Reservation.id)
           .filter(PaymentMode.category == 'ota_receivable',
                   Payment.is_voided == False,
                   Reservation.ota_channel == channel)
           .one())
    return row[0] if row and row[0] else None


def _delay_days_for_channel(channel: str, pending: float,
                            today: date) -> int:
    """Days late on the next expected payout for this channel.

    - pending <= 0  → 0 (we're square)
    - last payout exists → expected = last_payout + cycle; delay = max(0, today - expected)
    - no payouts ever → expected = oldest_payment + cycle; delay = max(0, today - expected)
    """
    if pending <= 0:
        return 0
    cycle = get_payout_cycle_days(channel)
    last_pay = _last_payout_date(channel)
    if last_pay:
        expected = last_pay + timedelta(days=cycle)
    else:
        oldest = _oldest_unreconciled_payment_date(channel)
        if not oldest:
            return 0
        expected = oldest + timedelta(days=cycle)
    return max(0, (today - expected).days)


def get_reconciliation_summary(start: date | None = None,
                               end: date | None = None,
                               today: date | None = None) -> dict:
    """One row per channel with revenue, paid, pending, and delay.

    The ``start``/``end`` filter applies to the in-range revenue and
    payout columns ONLY — pending and delay are always lifetime
    figures so the report stays meaningful even when filtered to a
    short window.
    """
    if today is None:
        today = date.today()

    rows = []
    total_revenue_range = 0.0
    total_paid_range = 0.0
    total_pending = 0.0
    max_delay = 0

    for channel in _all_known_channels():
        rev_range = get_ota_revenue_total(channel, start, end)['total']
        pay_range = get_ota_payouts_total(channel, start, end)['net']

        rev_life = get_ota_revenue_total(channel)['total']
        pay_life = get_ota_payouts_total(channel)['net']
        pending = round(rev_life - pay_life, 2)

        delay = _delay_days_for_channel(channel, pending, today)
        cycle = get_payout_cycle_days(channel)
        last_pay = _last_payout_date(channel)

        rows.append({
            'channel': channel,
            'cycle_days': cycle,
            'revenue_in_range': round(rev_range, 2),
            'paid_in_range': round(pay_range, 2),
            'revenue_lifetime': round(rev_life, 2),
            'paid_lifetime': round(pay_life, 2),
            'pending': pending,
            'last_payout_date': last_pay.isoformat() if last_pay else None,
            'delay_days': delay,
            # Health colour for the UI
            'status': ('healthy' if pending <= 0
                       else ('warn' if delay <= 7
                             else ('danger' if delay > 0 else 'warn'))),
        })

        total_revenue_range += rev_range
        total_paid_range += pay_range
        total_pending += pending
        if delay > max_delay:
            max_delay = delay

    rows.sort(key=lambda r: (r['delay_days'], r['pending']), reverse=True)

    return {
        'as_of': today.isoformat(),
        'from': start.isoformat() if start else None,
        'to': end.isoformat() if end else None,
        'rows': rows,
        'totals': {
            'revenue_in_range': round(total_revenue_range, 2),
            'paid_in_range': round(total_paid_range, 2),
            'pending': round(total_pending, 2),
            'max_delay_days': max_delay,
            'channel_count': len(rows),
        },
    }


def get_payout_status_for_ceo() -> dict:
    """Lightweight roll-up for the CEO dashboard "OTA Payout Status"
    section. Excludes the date-range columns and only ships what the
    dashboard renders, so the JSON over the wire stays small.
    """
    summary = get_reconciliation_summary()
    cleaned = []
    for r in summary['rows']:
        cleaned.append({
            'channel': r['channel'],
            'pending': r['pending'],
            'last_payout_date': r['last_payout_date'],
            'cycle_days': r['cycle_days'],
            'delay_days': r['delay_days'],
            'status': r['status'],
        })
    return {
        'as_of': summary['as_of'],
        'channels': cleaned,
        'total_pending': summary['totals']['pending'],
        'max_delay_days': summary['totals']['max_delay_days'],
    }
