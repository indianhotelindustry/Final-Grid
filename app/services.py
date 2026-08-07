from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.models import db, BusinessDate, Reservation, NightAuditLog, Payment, Settings, Room

scheduler = BackgroundScheduler()

_night_audit_app = None  # captured by setup_night_audit_scheduler


def run_night_audit(app=None):
    """
    Night audit — called by APScheduler (auto) or manually from a route.

    Guarantees:
    - **Idempotent**: Will not create a second NightAuditLog row for the same
      date.  If any log exists (Pending, Completed, Warning, Reopened), the
      scheduler invocation is silently skipped.  Only the *absence* of a log
      triggers a new run.
    - **Atomic**: All DB writes (log creation, no-show posting, room charges)
      happen in a single transaction.  On any failure the entire batch is
      rolled back and the business date is unchanged.
    - **Row-locked**: BusinessDate is locked with FOR UPDATE to prevent
      concurrent scheduler / manual triggers from racing.
    - **Auto-complete**: When no blockers exist (no pending checkouts, no
      open shifts, no zero-rate rooms) the audit completes and advances the
      business date automatically.  When blockers exist, the log stays
      Pending for manual review.
    """
    import logging as _logging
    _na_logger = _logging.getLogger(__name__)

    # Resolve Flask app: explicit arg > captured global > current_app fallback
    _app = app or _night_audit_app
    if _app is None:
        from flask import current_app
        _app = current_app._get_current_object()

    with _app.app_context():
        try:
            # Lock BusinessDate to prevent concurrent runs
            business_date = (db.session.query(BusinessDate)
                             .with_for_update()
                             .first())
            if not business_date:
                return

            _bd = business_date.current_date

            # Idempotency: skip if ANY log already exists for this date
            # (Pending from a manual start, Completed, Warning, Reopened — all block)
            existing_log = NightAuditLog.query.filter_by(audit_date=_bd).first()
            if existing_log:
                db.session.rollback()
                _na_logger.info(
                    'Night audit skipped for %s — log already exists (status=%s)',
                    _bd, existing_log.status)
                return

            # Calculate metrics using centralized KPI helpers
            from app.kpi_helpers import (get_occupied_count, get_cash_revenue,
                                         get_cash_discount, get_net_cash_revenue,
                                         get_accrual_summary)

            occupied_rooms = get_occupied_count()
            cash_collected = get_cash_revenue(_bd)
            cash_discount = get_cash_discount(_bd)
            cash_net = get_net_cash_revenue(_bd)
            accrual = get_accrual_summary(_bd)

            pending_checkouts = Reservation.query.filter(
                Reservation.status == 'CheckedIn',
                Reservation.departure_date <= _bd
            ).count()

            # Create audit log — single row per date, never overwritten
            audit_log = NightAuditLog(
                audit_date=_bd,
                status='Pending',
                total_revenue=cash_collected,
                net_revenue=cash_net,
                total_discount=cash_discount,
                accrual_revenue=accrual['accrual_net'],
                occupancy_count=occupied_rooms,
                pending_checkouts=pending_checkouts,
            )
            db.session.add(audit_log)
            db.session.flush()   # get audit_log.id before no-show processing

            # Process no-shows
            from app.noshow_service import process_all_noshows
            no_show_count, ota_no_show_count = process_all_noshows(_bd)

            notes_parts = []
            if no_show_count:
                notes_parts.append(f'No-shows posted: {no_show_count}')
            if ota_no_show_count:
                notes_parts.append(f'OTA no-shows (manual handling required): {ota_no_show_count}')

            # ── Post nightly room charges for all in-house guests ────────
            # Phase C.3: use ReservationNightRate when available.
            from app.models import ExtraCharge, Shift, ReservationNightRate
            in_house = Reservation.query.filter_by(status='CheckedIn').all()
            room_charges_posted = 0
            _nightly_used = 0
            _legacy_used = 0
            for res in in_house:
                # Idempotency: skip if room rent already posted for this date
                already_posted = ExtraCharge.query.filter_by(
                    reservation_id=res.id,
                    charge_type='room_rent',
                    charge_date=_bd,
                ).first()
                if already_posted:
                    continue

                # Determine rate for this night
                rate = None
                _nr_row = None
                _post_source = 'legacy'
                try:
                    _nr_row = ReservationNightRate.query.filter_by(
                        reservation_id=res.id, stay_date=_bd).first()
                    if _nr_row:
                        if _nr_row.is_posted:
                            # Already marked posted but no ExtraCharge found
                            # (shouldn't happen — defensive skip)
                            _na_logger.warning(
                                'Night audit: res=%d date=%s nightly row is_posted=True '
                                'but no ExtraCharge found — skipping', res.id, _bd)
                            continue
                        rate = float(_nr_row.final_rate or 0)
                        _post_source = 'nightly_row'
                except Exception as _nr_err:
                    _na_logger.warning(
                        'Night audit: res=%d nightly row lookup failed (%s), '
                        'using legacy', res.id, _nr_err)

                if rate is None or rate <= 0:
                    rate = float(res.rate_per_night or 0)
                    _post_source = 'legacy'

                if rate <= 0:
                    continue

                room_no = res.room.room_number if res.room else '?'
                charge = ExtraCharge(
                    reservation_id=res.id,
                    description=f'Room Rent — {_bd.strftime("%d %b")} (Room {room_no})',
                    amount=rate,
                    charge_date=_bd,
                    charge_type='room_rent',
                    charge_category='Room',
                )
                db.session.add(charge)
                db.session.flush()

                # Link nightly row to posted charge
                if _nr_row and _post_source == 'nightly_row':
                    _nr_row.is_posted = True
                    _nr_row.posted_charge_id = charge.id
                    _nr_row.is_locked = True
                    _nightly_used += 1
                else:
                    _legacy_used += 1

                room_charges_posted += 1
            if room_charges_posted:
                parts = [f'Room charges posted: {room_charges_posted}']
                if _nightly_used:
                    parts.append(f'{_nightly_used} from nightly rows')
                if _legacy_used:
                    parts.append(f'{_legacy_used} from legacy rate')
                notes_parts.append(' | '.join(parts))

            # ── Blocker detection for auto-complete ─────────────────────
            blockers = []
            if pending_checkouts:
                blockers.append(f'{pending_checkouts} pending checkout(s)')
            # Open (unclosed) cashier shifts
            open_shifts = Shift.query.filter_by(status='Open').count()
            if open_shifts:
                blockers.append(f'{open_shifts} unclosed shift(s)')
            # Zero-rate rooms (missing room rent)
            zero_rate = sum(1 for r in in_house
                            if not r.rate_per_night or float(r.rate_per_night) <= 0)
            if zero_rate:
                blockers.append(f'{zero_rate} room(s) with zero rate')

            if blockers:
                # ── Blockers found: leave as Pending for manual review ──
                audit_log.status = 'Pending'
                audit_log.blocker_count = len(blockers)
                notes_parts.append(f'Auto-complete blocked: {"; ".join(blockers)}')
                audit_log.notes = ' | '.join(notes_parts) if notes_parts else None
                db.session.commit()
                _na_logger.info(
                    'Night audit for %s created as Pending — blockers: %s',
                    _bd, '; '.join(blockers))
            else:
                # ── No blockers: auto-complete and advance business date ─
                audit_log.status = 'Completed'
                audit_log.completed_at = datetime.utcnow()
                audit_log.run_at = datetime.utcnow()
                notes_parts.append('Auto-completed (no blockers)')
                audit_log.notes = ' | '.join(notes_parts) if notes_parts else None

                # ── Store frozen snapshot (same as manual /complete path) ─
                try:
                    import json as _snap_json
                    from app.night_audit_service import NightAuditService
                    _snap_svc = NightAuditService(_bd)
                    def _serial(obj):
                        if isinstance(obj, (datetime, date)):
                            return obj.isoformat()
                        if isinstance(obj, Decimal):
                            return float(obj)
                        if hasattr(obj, '__dict__') and hasattr(obj, 'id'):
                            # SQLAlchemy model → minimal dict
                            return {'id': obj.id, '_type': type(obj).__name__}
                        try:
                            return str(obj)
                        except Exception:
                            return None
                    _snap_text = _snap_json.dumps(_snap_svc.full_report(), default=_serial)
                    audit_log.snapshot_json    = _snap_text
                    audit_log.snapshot_valid   = True
                    audit_log.snapshot_hash    = compute_snapshot_hash(_snap_text)
                    try:
                        from app import APP_VERSION as _AV
                        audit_log.snapshot_version = _AV
                    except Exception:
                        pass
                except Exception as _snap_err:
                    _na_logger.warning(
                        'Night audit %s: snapshot storage failed: %s', _bd, _snap_err)
                    audit_log.snapshot_valid = False

                # Advance business date to next day
                business_date.current_date = _bd + timedelta(days=1)
                business_date.is_locked = False
                business_date.updated_at = datetime.utcnow()

                db.session.commit()
                _na_logger.info(
                    'Night audit for %s auto-completed. Business date advanced to %s',
                    _bd, business_date.current_date)

        except Exception as e:
            db.session.rollback()
            _na_logger.error('Night audit failed for business date: %s', e)
            raise


def setup_night_audit_scheduler(app):
    """Configure the night audit cron job. Always starts the scheduler."""
    global _night_audit_app
    _night_audit_app = app

    with app.app_context():
        enabled_setting = Settings.query.filter_by(key='night_audit_enabled').first()
        time_setting = Settings.query.filter_by(key='night_audit_time').first()

    if enabled_setting and enabled_setting.value.lower() == 'true':
        audit_time = time_setting.value if time_setting else '02:00'
        try:
            hour, minute = map(int, audit_time.split(':'))
        except (ValueError, AttributeError):
            hour, minute = 2, 0

        scheduler.add_job(
            func=run_night_audit,
            trigger='cron',
            hour=hour,
            minute=minute,
            id='night_audit_job',
            replace_existing=True,
            misfire_grace_time=3600,
        )
    else:
        # Remove existing job if night audit was disabled
        try:
            scheduler.remove_job('night_audit_job')
        except Exception:
            pass

    # Always start the scheduler — other jobs (backup, notifications,
    # log pruning, predictive maintenance) depend on it running.
    if not scheduler.running:
        scheduler.start()


def reschedule_night_audit(app=None):
    """Re-read settings and update the scheduler job. Call after settings change."""
    _app = app or _night_audit_app
    if not _app:
        from flask import current_app
        _app = current_app._get_current_object()

    with _app.app_context():
        enabled_setting = Settings.query.filter_by(key='night_audit_enabled').first()
        time_setting = Settings.query.filter_by(key='night_audit_time').first()

    enabled = enabled_setting and enabled_setting.value.lower() == 'true'

    if enabled:
        audit_time = time_setting.value if time_setting else '02:00'
        try:
            hour, minute = map(int, audit_time.split(':'))
        except (ValueError, AttributeError):
            hour, minute = 2, 0

        scheduler.add_job(
            func=run_night_audit,
            trigger='cron',
            hour=hour,
            minute=minute,
            id='night_audit_job',
            replace_existing=True,
            misfire_grace_time=3600,
        )
    else:
        try:
            scheduler.remove_job('night_audit_job')
        except Exception:
            pass

def get_business_date():
    bd = BusinessDate.query.first()
    return bd.current_date if bd else date.today()


# ---------------------------------------------------------------------------
# Dashboard date-scope resolver (Apr 2026 fix — single source of truth for
# WHICH date a KPI refers to)
# ---------------------------------------------------------------------------
# The dashboard previously mixed three different time references silently:
#
#     1. business_date — the PMS "current active" date (advances when night
#        audit completes; can lag behind real today if audits are pending /
#        skipped / reopened).
#     2. last closed audit date — the most recent date for which a settled
#        NightAuditLog exists. Numbers from this scope are immutable
#        ledger truth.
#     3. real today — wall-clock calendar day. Numbers from this scope are
#        live, unsettled, and may shift until the audit closes them.
#
# Showing all three in unmarked KPI tiles led to questions like
# "is this revenue today's or yesterday's?" and "why did the dashboard
# change after I refreshed?". This resolver gives every dashboard
# consumer one canonical object so it can label each tile correctly
# and never mix scopes silently.

# ---------------------------------------------------------------------------
# Charges-based "live today" revenue (Apr 2026)
# ---------------------------------------------------------------------------
# Architectural rule, finalised after repeated dashboard confusion:
#
#     PAYMENTS  = settlement (cash arrived).  NOT revenue.
#     CHARGES   = revenue earned (rate × nights + extras).
#
# The dashboard headline must source its "Direct Revenue" from CHARGES
# (or the closed NightAuditLog snapshot which itself recorded a charge-
# basis frozen total). Summing the Payment table to display "today's
# revenue" was wrong: paying ₹1 to test a UPI link or recording a ₹2
# rounding adjustment shouldn't move the revenue tile.
#
# This helper computes today's earned revenue purely from charges:
#   * Room revenue      = Σ rate_per_night for reservations in-house today
#                         (status CheckedIn, arrival ≤ today < departure)
#   * Extras revenue    = Σ ExtraCharge.amount for today, EXCLUDING
#                         room_rent (that's already counted via the
#                         room-revenue line in the night-audit ledger)
# Returns a dict with both components so the UI can show the breakdown.

def compute_live_today_charges(business_date) -> dict:
    """Return today's *earned* revenue computed purely from charges.

    Single source of truth for the dashboard's "Live (Unsettled)"
    revenue secondary line and any other surface that wants today's
    accrual-basis revenue without waiting for the audit to close.

    Output:
        {
          'room_revenue':   float,  # Σ rate_per_night for in-house today
          'extras_revenue': float,  # Σ non-room_rent ExtraCharge today
          'total_revenue':  float,  # room + extras
          'rooms_sold':     int,    # in-house room count for today
        }

    Never raises — on DB error returns zeros so the dashboard still renders.
    """
    from app.models import db, Reservation, ExtraCharge
    from sqlalchemy import func, or_
    try:
        # Room revenue (accrual): one rate_per_night per reservation
        # currently occupying a room on this date.
        in_house = (db.session.query(Reservation.rate_per_night)
                    .filter(Reservation.status == 'CheckedIn',
                            Reservation.arrival_date <= business_date,
                            Reservation.departure_date > business_date)
                    .all())
        room_rev = float(sum(r[0] or 0 for r in in_house))
        rooms_sold = len(in_house)

        # Extras posted today, excluding room_rent (which is the room
        # revenue itself once the audit posts it overnight).
        extras_q = (db.session.query(func.coalesce(func.sum(ExtraCharge.amount), 0))
                    .filter(ExtraCharge.charge_date == business_date,
                            or_(ExtraCharge.charge_type.is_(None),
                                ExtraCharge.charge_type != 'room_rent')))
        extras_rev = float(extras_q.scalar() or 0)

        return {
            'room_revenue':   round(room_rev, 2),
            'extras_revenue': round(extras_rev, 2),
            'total_revenue':  round(room_rev + extras_rev, 2),
            'rooms_sold':     rooms_sold,
        }
    except Exception:
        return {'room_revenue': 0.0, 'extras_revenue': 0.0,
                'total_revenue': 0.0, 'rooms_sold': 0}


def resolve_dashboard_scopes() -> dict:
    """Return the three date scopes the dashboard needs.

    Shape:
      {
        'business_date':         date,    # PMS current_date (operational)
        'today_real':            date,    # wall-clock today
        'last_closed_date':      date | None,  # most recent settled audit
        'last_closed_log':       NightAuditLog | None,  # the row, for KPIs
        'is_business_stale':     bool,    # business_date < today_real
        'is_today_audited':      bool,    # last_closed_date == today_real
        'has_any_closed_audit':  bool,
        'days_since_close':      int | None,  # today_real - last_closed_date
      }

    Never raises — on any error returns a degraded but consistent dict so
    templates can still render.
    """
    from app.models import NightAuditLog
    business_date = get_business_date()
    today_real = date.today()

    last_log = None
    last_closed_date = None
    try:
        # 'Skipped' is an admin force-advance — not a real audit, but the
        # date IS sealed against further posting, so it counts as "closed"
        # for scope purposes (the next real audit picks up from there).
        last_log = (
            NightAuditLog.query
            .filter(NightAuditLog.status.in_(('Completed', 'Warning', 'Skipped')))
            .order_by(NightAuditLog.audit_date.desc())
            .first()
        )
        if last_log:
            last_closed_date = last_log.audit_date
    except Exception:
        # DB hiccup — fall back to scope info that doesn't depend on the log.
        pass

    days_since = None
    if last_closed_date is not None:
        try:
            days_since = (today_real - last_closed_date).days
        except Exception:
            days_since = None

    return {
        'business_date':         business_date,
        'today_real':            today_real,
        'last_closed_date':      last_closed_date,
        'last_closed_log':       last_log,
        'is_business_stale':     business_date < today_real,
        'is_today_audited':      last_closed_date == today_real if last_closed_date else False,
        'has_any_closed_audit':  last_log is not None,
        'days_since_close':      days_since,
    }


# ---------------------------------------------------------------------------
# Hotel timezone / UTC-window helpers
# ---------------------------------------------------------------------------
# The PMS stores all timestamps as UTC (``datetime.utcnow()``) but operates
# in the hotel's local timezone.  When filtering by "today" or a date range,
# we must translate local dates into a UTC datetime window.
#
# Current design: fixed offset (IST, UTC+5:30) — adequate for Indian hotels
# where DST is not observed.  Future-proofed: the internal resolver can be
# upgraded to return a full ``tzinfo`` (e.g. ``ZoneInfo('Asia/Kolkata')``)
# that honours DST without changing the public API of the window helpers.

HOTEL_TZ_OFFSET_HOURS = 5.5          # IST — Indian Standard Time (UTC+5:30)
HOTEL_TZ_NAME = 'Asia/Kolkata'       # IANA zone for future zoneinfo upgrade


def _resolve_hotel_timezone():
    """Internal: resolve the hotel's timezone.

    Currently returns a ``timezone(timedelta)`` — a fixed offset.  When
    multi-city / DST support is needed, this can return a
    ``zoneinfo.ZoneInfo`` without changing any caller.  Callers must use
    the returned object's ``utcoffset(at)`` method if they need the offset
    *at a specific datetime*, so DST transitions are handled correctly.
    """
    from datetime import timezone as _tz
    # TODO(multi-tz): read Settings('hotel_timezone_name') and, if set, use:
    #   from zoneinfo import ZoneInfo
    #   return ZoneInfo(settings_value)
    # Returned ZoneInfo is API-compatible with `tzinfo`, so callers
    # that do `tz.utcoffset(dt)` will automatically get DST-correct offsets.
    return _tz(timedelta(hours=HOTEL_TZ_OFFSET_HOURS), name='IST')


def get_hotel_tz_offset(at=None):
    """Return the hotel's UTC offset as a ``timedelta``.

    Parameters
    ----------
    at : date | datetime, optional
        Moment at which to resolve the offset.  With a fixed-offset zone
        this is ignored; with a ZoneInfo zone it will return the correct
        offset including DST.  Defaults to ``date.today()``.

    Centralised so a future Settings-based override can be added in one
    place without touching every KPI / filter that needs it.
    """
    from datetime import datetime as _dt, date as _date
    import logging as _lg
    _tz_log = _lg.getLogger('app.tz')
    tz = _resolve_hotel_timezone()
    # Build a reference datetime for offset resolution (needed for DST zones).
    if at is None:
        # Convenient default — traceable at DEBUG level but not noisy.
        _tz_log.debug('get_hotel_tz_offset: no "at" supplied, defaulting to today')
        ref = _dt.combine(_date.today(), _dt.min.time())
    elif isinstance(at, _dt):
        ref = at.replace(tzinfo=None)
    elif isinstance(at, _date):
        ref = _dt.combine(at, _dt.min.time())
    else:
        _tz_log.warning(
            'get_hotel_tz_offset: invalid "at" type %s, using today', type(at).__name__)
        ref = _dt.combine(_date.today(), _dt.min.time())
    off = tz.utcoffset(ref)
    # Fallback if utcoffset() returns None (shouldn't with timezone())
    return off if off is not None else timedelta(hours=HOTEL_TZ_OFFSET_HOURS)


def _validate_date_arg(value, name):
    """Assert that *value* is a ``date`` (not ``datetime``) and log if not.

    Returns the coerced ``date`` or raises ``TypeError`` on bad input.
    """
    from datetime import datetime as _dt, date as _date
    import logging as _lg
    _log = _lg.getLogger('app.tz')
    if isinstance(value, _dt):
        _log.warning(
            '%s: received datetime %s — expected date. Coercing to .date().',
            name, value)
        return value.date()
    if isinstance(value, _date):
        return value
    raise TypeError(
        f'{name}: expected date, got {type(value).__name__}: {value!r}')


def get_business_day_utc_window(business_date):
    """
    Return the UTC ``(start, end)`` datetime window that corresponds to
    the local day of *business_date* in the hotel's timezone.

    Use this helper whenever filtering a UTC-stored timestamp
    (``checked_out_at``, ``checked_in_at``, ``created_at``, etc.) by a
    local calendar day.

    ``end`` is exclusive — filter with ``>= start`` and ``< end``.

    Example::

        start, end = get_business_day_utc_window(date(2026, 4, 5))
        # For IST: start = 2026-04-04 18:30 UTC, end = 2026-04-05 18:30 UTC

        Reservation.query.filter(
            Reservation.checked_out_at >= start,
            Reservation.checked_out_at <  end,
        )
    """
    from datetime import datetime as _dt, timedelta as _td
    bd = _validate_date_arg(business_date, 'get_business_day_utc_window.business_date')
    # Resolve offset at the target date (DST-correct when ZoneInfo is used later)
    tz = get_hotel_tz_offset(at=bd)
    start = _dt.combine(bd, _dt.min.time()) - tz
    end   = _dt.combine(bd + _td(days=1), _dt.min.time()) - tz
    return start, end


def get_business_day_utc_range(from_date, to_date):
    """
    Return ``(start, end)`` UTC window covering the local-day range
    ``[from_date, to_date]`` inclusive of both endpoints.

    ``end`` is exclusive.
    """
    from datetime import datetime as _dt, timedelta as _td
    import logging as _lg
    f = _validate_date_arg(from_date, 'get_business_day_utc_range.from_date')
    t = _validate_date_arg(to_date, 'get_business_day_utc_range.to_date')
    if t < f:
        _lg.getLogger('app.tz').warning(
            'get_business_day_utc_range: to_date %s < from_date %s — '
            'range is empty; swapping.', t, f)
        f, t = t, f
    # Use offset at each endpoint; with fixed offset these match, with a
    # DST zone they may differ by ±1 hour across transitions.
    tz_start = get_hotel_tz_offset(at=f)
    tz_end = get_hotel_tz_offset(at=t + _td(days=1))
    start = _dt.combine(f, _dt.min.time()) - tz_start
    end   = _dt.combine(t + _td(days=1), _dt.min.time()) - tz_end
    return start, end


# ---------------------------------------------------------------------------
# Room-availability / conflict-detection helper (Group Stay Phase 1)
# ---------------------------------------------------------------------------

def rooms_held_in_window(
    room_ids,
    from_date,
    to_date,
    exclude_res_id=None,
    active_statuses=('Reserved', 'Confirmed', 'CheckedIn'),
):
    """Return the subset of *room_ids* that are held by at least one
    active reservation overlapping the window [from_date, to_date).

    Bridge-aware (Group Stay Phase 1): checks BOTH ``Reservation.room_id``
    (legacy primary-room pointer, present on every reservation) AND
    ``reservation_rooms.room_id`` (Phase 1+ multi-room bridge). The set
    union deduplicates rooms appearing on both sides.

    Parameters
    ----------
    room_ids : iterable of int
        Candidate rooms to check. Empty input returns an empty set
        without issuing any query.
    from_date, to_date : date
        Overlap window. Half-open: a reservation is considered to
        overlap if ``arrival_date < to_date AND departure_date > from_date``
        — the standard hotel-night convention also used by every
        existing conflict-check in routes.py.
    exclude_res_id : int, optional
        When editing an existing reservation, pass its id so the
        helper does not flag the reservation as conflicting with itself.
    active_statuses : tuple of str, optional
        Which reservation statuses count as "actively holding" the
        room. Default ``('Reserved', 'Confirmed', 'CheckedIn')`` matches
        the broader of the two existing routes.py callsites; the
        narrower set (``'Confirmed', 'CheckedIn'``) is also accepted.

    Returns
    -------
    set of int — the subset of room_ids that are held.

    Performance
    -----------
    Two index-covered SELECTs (one direct, one via bridge). At
    Sukoon-Pearl-Inn scale (~50 rooms, ~30 active reservations) total
    cost is well under 1 ms. See docs/RELEASE.md §"Group Stay" for
    the full performance analysis.
    """
    room_ids = list(room_ids) if room_ids else []
    if not room_ids:
        return set()

    # Local imports keep module-load time fast; services.py is large
    # and we follow the existing pattern of inline model imports.
    from app.models import db, Reservation, ReservationRoom

    statuses = tuple(active_statuses)

    # Direct match via Reservation.room_id (covers every reservation
    # past or present whose primary room is in the candidate set)
    q_direct = (db.session.query(Reservation.room_id)
                .filter(Reservation.room_id.in_(room_ids),
                        Reservation.status.in_(statuses),
                        Reservation.arrival_date  < to_date,
                        Reservation.departure_date > from_date))
    if exclude_res_id is not None:
        q_direct = q_direct.filter(Reservation.id != exclude_res_id)

    # Bridge match via reservation_rooms (covers secondary rooms of
    # multi-room reservations — the case routes.py:8024-8030 misses today)
    q_bridge = (db.session.query(ReservationRoom.room_id)
                .join(Reservation,
                      Reservation.id == ReservationRoom.reservation_id)
                .filter(ReservationRoom.room_id.in_(room_ids),
                        Reservation.status.in_(statuses),
                        Reservation.arrival_date  < to_date,
                        Reservation.departure_date > from_date))
    if exclude_res_id is not None:
        q_bridge = q_bridge.filter(Reservation.id != exclude_res_id)

    return {r[0] for r in q_direct.all()} | {r[0] for r in q_bridge.all()}


# ---------------------------------------------------------------------------
# Business Date Lock Guard
# ---------------------------------------------------------------------------

def is_date_locked(check_date) -> bool:
    """
    Returns True if check_date has a completed (locked) night audit.
    A date is locked when its NightAuditLog.status is 'Completed', 'Warning',
    or 'Skipped'.  Reopened and Pending audits are treated as unlocked.
    """
    from app.models import NightAuditLog
    log = NightAuditLog.query.filter(
        NightAuditLog.audit_date == check_date,
        NightAuditLog.status.in_(['Completed', 'Warning', 'Skipped'])
    ).first()
    return log is not None


def assert_business_date_unlocked(target_date, action: str = 'this action') -> tuple:
    """
    Call before any write that mutates data tied to a specific business date.

    Returns:
        (True, None)           — date is open, proceed
        (False, error_message) — date is locked, block the action

    Usage in a route::
        ok, err = assert_business_date_unlocked(reservation.arrival_date, 'edit reservation')
        if not ok:
            flash(err, 'danger')
            return redirect(...)
    """
    from app.models import NightAuditLog
    log = NightAuditLog.query.filter(
        NightAuditLog.audit_date == target_date,
        NightAuditLog.status.in_(['Completed', 'Warning', 'Skipped'])
    ).first()
    if log:
        return False, (
            f"Locked — this transaction belongs to a closed Night Audit date "
            f"({target_date.strftime('%d %b %Y')}). "
            f"Contact Admin for correction."
        )
    return True, None


def get_locking_audit(target_date):
    """Return the closed NightAuditLog row that locks `target_date`, or None.

    Used by UI to render the "🔒 Locked — closed in Night Audit on
    DD MMM YYYY" banner on folios / payment rows that fall within a
    closed business date.
    """
    from app.models import NightAuditLog
    return NightAuditLog.query.filter(
        NightAuditLog.audit_date == target_date,
        NightAuditLog.status.in_(['Completed', 'Warning', 'Skipped'])
    ).first()


def assert_or_admin_override(target_date, action: str, req, user):
    """Locking guard that allows an Admin to override with a reason.

    Returns ``(True, None, override_used:bool, reason:str|None)`` if the
    action may proceed (either because the date is open OR because the
    Admin supplied a valid override). Otherwise returns
    ``(False, error_message, False, None)``.

    Override contract — the form (or JSON body) of the calling request
    must contain BOTH:
        audit_override          = '1'
        audit_override_reason   = '<non-empty reason>'

    Caller is responsible for writing the `_write_audit` row that names
    the entity affected; this helper only verifies authorisation.
    """
    ok, err = assert_business_date_unlocked(target_date, action)
    if ok:
        return True, None, False, None

    # Date is locked — see if Admin override is in effect.
    is_admin = bool(user and getattr(user, 'is_authenticated', False)
                    and user.has_role('Admin'))
    override_flag = (req.form.get('audit_override') or
                     req.values.get('audit_override') or '').strip() == '1'
    override_reason = (req.form.get('audit_override_reason') or
                       req.values.get('audit_override_reason') or '').strip()

    if override_flag and is_admin and override_reason:
        return True, None, True, override_reason

    if override_flag and not is_admin:
        return False, ('Locked — Admin authorisation is required to override '
                       'a closed Night Audit date.'), False, None
    if override_flag and not override_reason:
        return False, ('Locked — Admin override requires a written reason.'), False, None

    return False, err, False, None


# ---------------------------------------------------------------------------
# Individual Credit recovery — applied to every payment posted on a folio
# that previously underwent a Credit Checkout. credit_amount is the FROZEN
# original snapshot; credit_settled_amount climbs as money comes in. When
# fully cleared, credit_settled_at is stamped and the dashboard tile / aging
# report drop the row.
# ---------------------------------------------------------------------------
def apply_credit_settlement(reservation, payment_amount, *, by_user_id=None,
                            ref_payment_id=None, audit_writer=None):
    """Record `payment_amount` against the reservation's open credit.

    Returns a dict describing what changed::
        {
          'recovered_now': float,          # amount applied to credit (capped)
          'remaining':     float,          # credit balance after this payment
          'fully_settled': bool,
          'status':        'Open'|'Partial'|'Settled'|'NoCredit',
        }

    Pass ``audit_writer`` (e.g. ``app.routes._write_audit``) to have the
    helper record the credit-settlement audit log entries; safe to omit if
    the caller wants to write its own.
    """
    from datetime import datetime as _dt
    if reservation is None:
        return {'recovered_now': 0.0, 'remaining': 0.0,
                'fully_settled': False, 'status': 'NoCredit'}

    original = float(reservation.credit_amount or 0)
    if original <= 0.005:
        return {'recovered_now': 0.0, 'remaining': 0.0,
                'fully_settled': False, 'status': 'NoCredit'}

    already = float(reservation.credit_settled_amount or 0)
    remaining_before = max(0.0, round(original - already, 2))
    if remaining_before <= 0.005:
        # Already fully settled; nothing to do.
        return {'recovered_now': 0.0, 'remaining': 0.0,
                'fully_settled': True, 'status': 'Settled'}

    apply_now = round(min(float(payment_amount or 0), remaining_before), 2)
    if apply_now <= 0.005:
        return {'recovered_now': 0.0, 'remaining': remaining_before,
                'fully_settled': False, 'status':
                'Partial' if already > 0 else 'Open'}

    new_settled = round(already + apply_now, 2)
    reservation.credit_settled_amount = new_settled
    new_remaining = max(0.0, round(original - new_settled, 2))
    fully = new_remaining <= 0.005

    if fully and reservation.credit_settled_at is None:
        reservation.credit_settled_at = _dt.utcnow()

    status = 'Settled' if fully else 'Partial'

    if audit_writer is not None:
        try:
            audit_writer('Reservation', reservation.id,
                         'individual_credit_settled' if fully
                         else 'individual_credit_payment_received',
                         {'credit_settled_amount': already,
                          'remaining': remaining_before},
                         {'credit_settled_amount': new_settled,
                          'remaining': new_remaining,
                          'applied_now': apply_now,
                          'ref_payment_id': ref_payment_id,
                          'by_user_id': by_user_id})
        except Exception:
            pass

    return {'recovered_now': apply_now, 'remaining': new_remaining,
            'fully_settled': fully, 'status': status}


def post_payment_correction(original_payment, *,
                            new_amount=None, new_mode_id=None,
                            new_reference=None, reason, user_id=None,
                            audit_writer=None):
    """Post a reversal (and optional replacement) for a payment in a closed audit.

    Never mutates the original Payment row. Inserts at most two new rows:

      * REVERSAL    — ``is_correction=True``, ``is_reversal=True``,
                      ``amount = original.amount`` (positive — the CHECK
                      amount > 0 stays intact). Callers that compute
                      "paid total" must SUBTRACT this row's amount.
      * REPLACEMENT — only when ``new_amount`` is given and > 0.
                      ``is_correction=True``, ``is_reversal=False``,
                      ``amount = new_amount`` posted to the
                      replacement payment_mode (defaults to original's mode).

    Both rows are linked back to the original via ``corrects_id``.
    Both rows carry the ``correction_reason``. Two AuditLog entries are
    written per correction pair: 'payment_reversed' and (if replaced)
    'payment_corrected'. Caller is responsible for committing the
    transaction.

    Returns ``{'reversal': Payment, 'replacement': Payment | None}``.
    """
    from app.models import Payment, db as _db
    from datetime import date as _date

    if original_payment is None:
        raise ValueError('original_payment is required')
    if not (reason or '').strip():
        raise ValueError('correction reason is required')
    reason = reason.strip()[:300]

    today = _date.today()

    reversal = Payment(
        reservation_id    = original_payment.reservation_id,
        folio_id          = original_payment.folio_id,
        payment_mode_id   = original_payment.payment_mode_id,
        amount            = original_payment.amount,
        payment_date      = today,
        is_correction     = True,
        is_reversal       = True,
        corrects_id       = original_payment.id,
        correction_reason = reason,
    )
    _db.session.add(reversal)
    _db.session.flush()

    if audit_writer is not None:
        try:
            audit_writer('Payment', reversal.id, 'payment_reversed',
                         {'original_payment_id': original_payment.id,
                          'original_amount':     float(original_payment.amount),
                          'original_date':       original_payment.payment_date.isoformat()
                                                  if original_payment.payment_date else None},
                         {'reversal_payment_id': reversal.id,
                          'reversal_amount':     float(reversal.amount),
                          'reason':              reason,
                          'by_user_id':          user_id})
        except Exception:
            pass

    replacement = None
    if new_amount is not None and float(new_amount) > 0.005:
        mode_id = int(new_mode_id) if new_mode_id else int(original_payment.payment_mode_id)
        replacement = Payment(
            reservation_id    = original_payment.reservation_id,
            folio_id          = original_payment.folio_id,
            payment_mode_id   = mode_id,
            amount            = float(new_amount),
            payment_date      = today,
            reference_number  = (new_reference or None),
            is_correction     = True,
            is_reversal       = False,
            corrects_id       = original_payment.id,
            correction_reason = reason,
        )
        _db.session.add(replacement)
        _db.session.flush()

        if audit_writer is not None:
            try:
                audit_writer('Payment', replacement.id, 'payment_corrected',
                             {'original_payment_id': original_payment.id,
                              'original_amount':     float(original_payment.amount)},
                             {'replacement_payment_id': replacement.id,
                              'replacement_amount':     float(replacement.amount),
                              'replacement_mode_id':    mode_id,
                              'reason':                 reason,
                              'by_user_id':             user_id})
            except Exception:
                pass

    return {'reversal': reversal, 'replacement': replacement}


def post_extra_charge_correction(original_charge, *,
                                 new_amount=None, new_description=None,
                                 reason, user_id=None,
                                 audit_writer=None):
    """Post a reversal (and optional replacement) for an ExtraCharge in a closed audit.

    Mirror of ``post_payment_correction`` for the charges side. Never
    mutates the original. Returns ``{'reversal': ExtraCharge,
    'replacement': ExtraCharge | None}``. Caller commits.
    """
    from app.models import ExtraCharge, db as _db
    from datetime import date as _date

    if original_charge is None:
        raise ValueError('original_charge is required')
    if not (reason or '').strip():
        raise ValueError('correction reason is required')
    reason = reason.strip()[:300]

    today = _date.today()
    desc_prefix = '[REVERSAL] '
    rev_desc = (desc_prefix + (original_charge.description or 'extra charge'))[:100]

    reversal = ExtraCharge(
        reservation_id    = original_charge.reservation_id,
        folio_id          = original_charge.folio_id,
        description       = rev_desc,
        amount            = original_charge.amount,
        charge_date       = today,
        charge_type       = original_charge.charge_type,
        charge_category   = original_charge.charge_category,
        is_correction     = True,
        is_reversal       = True,
        corrects_id       = original_charge.id,
        correction_reason = reason,
    )
    _db.session.add(reversal)
    _db.session.flush()

    if audit_writer is not None:
        try:
            audit_writer('ExtraCharge', reversal.id, 'charge_reversed',
                         {'original_charge_id': original_charge.id,
                          'original_amount':    float(original_charge.amount),
                          'original_desc':      original_charge.description,
                          'original_date':      original_charge.charge_date.isoformat()
                                                if original_charge.charge_date else None},
                         {'reversal_charge_id': reversal.id,
                          'reversal_amount':    float(reversal.amount),
                          'reason':             reason,
                          'by_user_id':         user_id})
        except Exception:
            pass

    replacement = None
    if new_amount is not None and float(new_amount) > 0.005:
        repl_desc = (new_description or original_charge.description or 'extra charge')[:100]
        replacement = ExtraCharge(
            reservation_id    = original_charge.reservation_id,
            folio_id          = original_charge.folio_id,
            description       = repl_desc,
            amount            = float(new_amount),
            charge_date       = today,
            charge_type       = original_charge.charge_type,
            charge_category   = original_charge.charge_category,
            is_correction     = True,
            is_reversal       = False,
            corrects_id       = original_charge.id,
            correction_reason = reason,
        )
        _db.session.add(replacement)
        _db.session.flush()

        if audit_writer is not None:
            try:
                audit_writer('ExtraCharge', replacement.id, 'charge_corrected',
                             {'original_charge_id': original_charge.id,
                              'original_amount':    float(original_charge.amount)},
                             {'replacement_charge_id': replacement.id,
                              'replacement_amount':    float(replacement.amount),
                              'replacement_desc':      replacement.description,
                              'reason':                reason,
                              'by_user_id':            user_id})
            except Exception:
                pass

    return {'reversal': reversal, 'replacement': replacement}


def signed_payment_amount(payment) -> float:
    """Return amount with sign applied: -amount for reversal entries,
    +amount otherwise. Voided payments return 0 (caller may also pre-filter).

    Use this in any code path that sums payment.amount across a folio,
    so that REVERSAL entries correctly cancel their originals.
    """
    if payment is None or getattr(payment, 'is_voided', False):
        return 0.0
    amt = float(payment.amount or 0)
    return -amt if getattr(payment, 'is_reversal', False) else amt


def signed_extra_charge_amount(charge) -> float:
    """Return amount with sign applied for an ExtraCharge: -amount for
    reversal entries, +amount otherwise."""
    if charge is None:
        return 0.0
    amt = float(charge.amount or 0)
    return -amt if getattr(charge, 'is_reversal', False) else amt


def advance_summary(reservation) -> dict:
    """Roll up the advance lifecycle for a reservation.

    Returns the gross advance collected, the refund amount issued (via
    ``payment_purpose='refund'`` rows), and the net advance still on the
    folio. Forfeit and credit-voucher figures come from the cancellation
    snapshot columns. Safe to call on any reservation — returns zeros
    when no advance is on file.
    """
    if reservation is None:
        return {'advance_received': 0.0, 'refund_issued': 0.0,
                'net_advance':      0.0, 'forfeit_income': 0.0,
                'credit_voucher':   0.0, 'disposition':   None}

    advance_received = 0.0
    refund_issued    = 0.0
    for p in (reservation.payments or []):
        if getattr(p, 'is_voided', False):
            continue
        purpose = (getattr(p, 'payment_purpose', '') or '').lower()
        amt = float(p.amount or 0)
        if purpose == 'advance':
            advance_received += amt
        elif purpose == 'refund':
            refund_issued += amt

    forfeit = float(getattr(reservation, 'cancellation_amount_forfeited', 0) or 0)
    voucher = float(getattr(reservation, 'cancellation_amount_credit_voucher', 0) or 0)
    return {
        'advance_received': round(advance_received, 2),
        'refund_issued':    round(refund_issued, 2),
        'net_advance':      round(advance_received - refund_issued, 2),
        'forfeit_income':   round(forfeit, 2),
        'credit_voucher':   round(voucher, 2),
        'disposition':      getattr(reservation, 'cancellation_disposition', None),
    }


def build_daily_financial_summary(business_date) -> dict:
    """Build the owner-facing Daily Financial Summary for a single date.

    One pass over today's payments + cancellation snapshots + live credit
    balances. Designed to be cheap enough to call on every dashboard render.

    Returns::

        {
          'business_date':         date,
          # Earned (accrual)
          'revenue_accrual':       float,   # live charges today (preferred)
          'revenue_source':        'audit' | 'live',
          'revenue_audit_id':      int | None,
          # Cash flow today (direct payments only — OTA stays separate)
          'advance_received':      float,
          'refund_issued':         float,
          'net_advance':           float,   # advance - refund
          'settlement_collected':  float,
          'credit_recovered':      float,
          'total_collected':       float,   # advance + settlement + credit_recovery − refund
          # Income recognised today, separate from room revenue
          'forfeit_income':        float,
          # Live receivable / liability snapshot
          'credit_outstanding':    float,
          'individual_credit':     float,
          'company_credit':        float,
          # Headline derivative for the "Cash Flow vs Revenue" tile
          'cash_minus_revenue':    float,   # >0 = collected more than earned (liability up)
                                            # <0 = earned more than collected (receivable up)
        }
    """
    from app.models import NightAuditLog, Payment, Reservation, Company
    from sqlalchemy import func as _func

    # ── Revenue (accrual) ────────────────────────────────────────────
    # Prefer the closed NightAuditLog snapshot for the date if present —
    # otherwise compute live from charges (in-progress day).
    revenue_accrual = 0.0
    revenue_source  = 'live'
    revenue_audit_id = None
    try:
        log = NightAuditLog.query.filter(
            NightAuditLog.audit_date == business_date,
            NightAuditLog.status.in_(['Completed', 'Warning'])
        ).first()
        if log is not None:
            revenue_accrual = float(log.accrual_revenue or 0)
            revenue_source  = 'audit'
            revenue_audit_id = log.id
        else:
            live = compute_live_today_charges(business_date)
            revenue_accrual = float(live.get('total_revenue') or 0)
            revenue_source  = 'live'
    except Exception:
        revenue_accrual = 0.0

    # ── Direct-payment buckets for today ─────────────────────────────
    advance_received     = 0.0
    refund_issued        = 0.0
    settlement_collected = 0.0
    credit_recovered     = 0.0
    try:
        rows = (Payment.query
                .filter(Payment.payment_date == business_date,
                        Payment.is_voided.is_(False))
                .all())
        for p in rows:
            pm = p.payment_mode
            if pm is None:
                continue
            if getattr(pm, 'category', 'direct_payment') != 'direct_payment':
                continue
            amt = float(p.amount or 0)
            purpose = (getattr(p, 'payment_purpose', '') or 'settlement').lower()
            # Reversal entries (correction system) carry positive amount
            # but logically subtract.
            if getattr(p, 'is_reversal', False) and purpose != 'refund':
                amt = -amt
            if purpose == 'advance':
                advance_received     += amt
            elif purpose == 'refund':
                refund_issued        += amt
            elif purpose == 'credit_recovery':
                credit_recovered     += amt
            else:
                settlement_collected += amt
    except Exception:
        pass

    net_advance = round(advance_received - refund_issued, 2)
    total_collected = round(
        advance_received + settlement_collected + credit_recovered - refund_issued, 2
    )

    # ── Forfeit Income today (cancellation snapshot) ─────────────────
    forfeit_income = 0.0
    try:
        rows = (Reservation.query
                .filter(Reservation.cancellation_amount_forfeited > 0,
                        Reservation.cancellation_processed_at.isnot(None))
                .all())
        for r in rows:
            if (r.cancellation_processed_at and
                r.cancellation_processed_at.date() == business_date):
                forfeit_income += float(r.cancellation_amount_forfeited or 0)
    except Exception:
        pass

    # ── Live Credit Outstanding (Receivable) ─────────────────────────
    individual_credit = 0.0
    try:
        for r in (Reservation.query
                  .filter(Reservation.credit_amount > 0).all()):
            original = float(r.credit_amount or 0)
            settled  = float(r.credit_settled_amount or 0)
            remaining = max(0.0, round(original - settled, 2))
            if remaining > 0.005:
                individual_credit += remaining
    except Exception:
        pass

    company_credit = 0.0
    try:
        company_credit = float(
            db.session.query(_func.coalesce(_func.sum(Company.credit_used), 0)).scalar() or 0
        )
    except Exception:
        pass

    credit_outstanding = round(individual_credit + company_credit, 2)
    cash_minus_revenue = round(total_collected - revenue_accrual, 2)

    return {
        'business_date':        business_date,
        'revenue_accrual':      round(revenue_accrual, 2),
        'revenue_source':       revenue_source,
        'revenue_audit_id':     revenue_audit_id,
        'advance_received':     round(advance_received, 2),
        'refund_issued':        round(refund_issued, 2),
        'net_advance':          net_advance,
        'settlement_collected': round(settlement_collected, 2),
        'credit_recovered':     round(credit_recovered, 2),
        'total_collected':      total_collected,
        'forfeit_income':       round(forfeit_income, 2),
        'credit_outstanding':   credit_outstanding,
        'individual_credit':    round(individual_credit, 2),
        'company_credit':       round(company_credit, 2),
        'cash_minus_revenue':   cash_minus_revenue,
    }


def get_forfeit_approval_threshold() -> float:
    """Read the Settings-driven threshold above which a forfeit requires
    explicit Admin approval. Defaults to ₹5,000 if unset."""
    try:
        s = Settings.query.filter_by(key='forfeit_admin_approval_threshold').first()
        if s and s.value is not None:
            v = float(s.value)
            if v >= 0:
                return v
    except Exception:
        pass
    return 5000.0


def compute_snapshot_hash(snapshot_text: str) -> str:
    """Return the SHA-256 hex digest of a snapshot JSON string.

    Used by the night-audit close path to record an immutable fingerprint
    of the frozen report. Re-computed on render to detect any tampering
    or structural drift (e.g. a manual DB edit or a model change that
    changed how the JSON was serialised).
    """
    import hashlib as _hashlib
    if snapshot_text is None:
        return ''
    return _hashlib.sha256(snapshot_text.encode('utf-8')).hexdigest()


def verify_snapshot_integrity(audit_log) -> dict:
    """Recompute the hash of ``audit_log.snapshot_json`` and compare to
    the stored ``snapshot_hash``. Returns::

        {
          'has_snapshot':  bool,
          'has_hash':      bool,
          'matches':       bool,        # True if hashes equal (or no hash)
          'stored_hash':   str | None,
          'current_hash':  str | None,
          'stored_version': str | None,
          'app_version':   str | None,
          'version_match': bool,
        }
    """
    from app import APP_VERSION as _AV
    out = {
        'has_snapshot':  False,
        'has_hash':      False,
        'matches':       True,        # default-True so legacy logs without
        'stored_hash':   None,        # a hash don't trigger a false alarm
        'current_hash':  None,
        'stored_version': None,
        'app_version':   _AV,
        'version_match': True,
    }
    if audit_log is None:
        return out
    sj = getattr(audit_log, 'snapshot_json', None)
    sh = getattr(audit_log, 'snapshot_hash', None)
    sv = getattr(audit_log, 'snapshot_version', None)
    out['has_snapshot']    = bool(sj)
    out['has_hash']        = bool(sh)
    out['stored_hash']     = sh
    out['stored_version']  = sv
    out['version_match']   = (not sv) or (sv == _AV)
    if sj and sh:
        cur = compute_snapshot_hash(sj)
        out['current_hash'] = cur
        out['matches']      = (cur == sh)
    return out


def get_individual_credit_admin_threshold() -> float:
    """Read the Settings-driven threshold above which an Individual Credit
    checkout requires Admin (not just Manager) approval. Default ₹10,000.

    Apr 2026 — Section 4 of the financial-integrity hardening pass.
    """
    try:
        s = Settings.query.filter_by(key='individual_credit_admin_threshold').first()
        if s and s.value is not None:
            v = float(s.value)
            if v >= 0:
                return v
    except Exception:
        pass
    return 10000.0


def get_individual_credit_default_limit() -> float:
    """Hard ceiling on a single Individual Credit transaction. Above this
    the route refuses outright (regardless of role). Default ₹50,000 —
    operators set lower for cautious deployments."""
    try:
        s = Settings.query.filter_by(key='individual_credit_default_limit').first()
        if s and s.value is not None:
            v = float(s.value)
            if v >= 0:
                return v
    except Exception:
        pass
    return 50000.0


def post_cancellation_disposition(reservation, *, disposition, refund_amount=0,
                                  refund_mode_id=None, refund_reference=None,
                                  voucher_amount=0, reason, user_id=None,
                                  approver_user_id=None,
                                  approver_is_admin=False,
                                  approval_reason=None,
                                  audit_writer=None):
    """Apply a cancellation disposition to a reservation that holds an advance.

    Validates the chosen path against the available advance, posts a
    refund Payment (if applicable), stamps the cancellation_* snapshot
    columns, and writes audit rows for every leg. Returns a dict::

        {'refund_payment': Payment | None,
         'forfeit_amount': float,
         'voucher_amount': float,
         'refund_amount':  float,
         'disposition':    str}

    The caller is responsible for setting reservation.status='Cancelled'
    and committing the transaction.
    """
    from app.models import Payment, db as _db
    from datetime import datetime as _dt

    if reservation is None:
        raise ValueError('reservation is required')
    if disposition not in ('refund_full', 'refund_partial',
                           'forfeit', 'credit_voucher', 'no_advance'):
        raise ValueError(f'invalid disposition: {disposition}')
    if not (reason or '').strip():
        raise ValueError('cancellation reason is required')
    reason_clean = reason.strip()[:300]

    summary = advance_summary(reservation)
    advance_total = summary['advance_received']
    already_refunded = summary['refund_issued']
    available = max(0.0, round(advance_total - already_refunded, 2))

    refund_amount  = max(0.0, float(refund_amount or 0))
    voucher_amount = max(0.0, float(voucher_amount or 0))
    forfeit_amount = 0.0
    refund_payment = None

    # ── Per-disposition validation + computation ──────────────────
    if disposition == 'no_advance':
        if advance_total > 0.005:
            raise ValueError('Reservation has an advance — choose refund / forfeit / credit voucher.')
        # Nothing to do beyond stamping snapshot below.
    elif disposition == 'refund_full':
        if advance_total <= 0.005:
            raise ValueError('No advance on file — nothing to refund.')
        refund_amount = available
        if refund_amount <= 0.005:
            raise ValueError('Advance has already been fully refunded.')
    elif disposition == 'refund_partial':
        if advance_total <= 0.005:
            raise ValueError('No advance on file — nothing to refund.')
        if refund_amount <= 0.005:
            raise ValueError('Partial refund amount must be greater than zero.')
        if refund_amount > available + 0.01:
            raise ValueError(f'Refund ₹{refund_amount:,.2f} exceeds available advance ₹{available:,.2f}.')
        forfeit_amount = round(available - refund_amount, 2)
    elif disposition == 'forfeit':
        if advance_total <= 0.005:
            raise ValueError('No advance on file — nothing to forfeit.')
        forfeit_amount = available
    elif disposition == 'credit_voucher':
        if advance_total <= 0.005:
            raise ValueError('No advance on file — cannot issue credit voucher.')
        if voucher_amount <= 0.005:
            voucher_amount = available
        if voucher_amount > available + 0.01:
            raise ValueError(f'Voucher ₹{voucher_amount:,.2f} exceeds available advance ₹{available:,.2f}.')
        # Any remainder is forfeit.
        forfeit_amount = round(available - voucher_amount, 2)

    # ── Forfeit approval gate ─────────────────────────────────────────
    # If this disposition produces ANY forfeit amount AND that amount is
    # above the configured threshold, require Admin approval with a
    # written reason. Below threshold, no extra approval is needed
    # (the existing cancellation reason already covers it).
    if forfeit_amount > 0.005:
        threshold = get_forfeit_approval_threshold()
        if forfeit_amount > threshold + 0.005:
            if not approver_is_admin:
                raise ValueError(
                    f'Forfeit of ₹{forfeit_amount:,.2f} exceeds the '
                    f'₹{threshold:,.0f} approval threshold — Admin authorisation required.'
                )
            if not (approval_reason or '').strip():
                raise ValueError(
                    'Admin approval reason is required when forfeit exceeds the threshold.'
                )

    # ── Refund Payment row (purpose=refund, is_reversal=True so signed
    #    sums net it against advance receipts on the folio) ────────────
    if refund_amount > 0.005:
        if not refund_mode_id:
            raise ValueError('Refund mode is required when issuing a refund.')
        from datetime import date as _date
        refund_payment = Payment(
            reservation_id    = reservation.id,
            amount            = refund_amount,
            payment_mode_id   = int(refund_mode_id),
            payment_date      = _date.today(),
            reference_number  = (refund_reference or None),
            payment_purpose   = 'refund',
            is_reversal       = True,
            correction_reason = f'Cancellation refund | {reason_clean}',
        )
        _db.session.add(refund_payment)
        _db.session.flush()
        if audit_writer is not None:
            try:
                audit_writer('Payment', refund_payment.id, 'cancellation_refund',
                             {'reservation_id': reservation.id,
                              'advance_total': advance_total,
                              'available_before_refund': available},
                             {'refund_amount': refund_amount,
                              'refund_mode_id': int(refund_mode_id),
                              'reason': reason_clean,
                              'by_user_id': user_id})
            except Exception:
                pass

    # ── Stamp cancellation snapshot columns on the reservation ────
    reservation.cancellation_disposition         = disposition
    reservation.cancellation_amount_refunded     = round(refund_amount, 2)
    reservation.cancellation_amount_forfeited    = round(forfeit_amount, 2)
    reservation.cancellation_amount_credit_voucher = round(voucher_amount, 2)
    reservation.cancellation_reason              = reason_clean
    reservation.cancellation_processed_by_user_id = user_id
    reservation.cancellation_processed_at        = _dt.utcnow()
    reservation.cancellation_refund_payment_id   = (refund_payment.id
                                                    if refund_payment else None)

    # ── Issue Credit Voucher row when disposition is credit_voucher ──
    # Real liability — guest can redeem against any future booking. The
    # snapshot column above keeps the amount visible on the reservation;
    # the new CreditVoucher row gives the lifecycle (issue / redeem /
    # expire) its own tracked entity.
    issued_voucher = None
    if disposition == 'credit_voucher' and voucher_amount > 0.005:
        try:
            issued_voucher = issue_credit_voucher(
                guest_id        = reservation.guest_id,
                amount          = voucher_amount,
                reservation_id  = reservation.id,
                expiry_days     = 365,   # default 1 year; admin can override later
                user_id         = user_id,
                notes           = f'Issued from cancellation of booking #{reservation.id} | {reason_clean}',
                audit_writer    = audit_writer,
            )
        except Exception as exc:
            # Never let voucher issuance break the cancellation. Caller
            # rolls back on failure of the parent transaction; the
            # snapshot column still records the intent.
            try:
                if audit_writer is not None:
                    audit_writer('Reservation', reservation.id, 'voucher_issue_failed',
                                 {'voucher_amount': voucher_amount},
                                 {'error': str(exc)[:200]})
            except Exception:
                pass

    # Approval block — captured in audit even when below threshold, so
    # the trail explicitly records who signed off (or the absence of an
    # approver, when none was needed).
    _appr_reason_clean = (approval_reason or '').strip()[:300] or None
    _approval_block = {
        'approver_user_id': approver_user_id,
        'approver_is_admin': bool(approver_is_admin),
        'approval_reason':  _appr_reason_clean,
        'forfeit_threshold': get_forfeit_approval_threshold(),
        'approval_required': forfeit_amount > get_forfeit_approval_threshold() + 0.005,
    }

    if audit_writer is not None:
        try:
            audit_writer('Reservation', reservation.id, 'cancellation_disposition',
                         {'advance_total': advance_total,
                          'previously_refunded': already_refunded},
                         {'disposition':     disposition,
                          'refund_amount':   round(refund_amount, 2),
                          'forfeit_amount':  round(forfeit_amount, 2),
                          'voucher_amount':  round(voucher_amount, 2),
                          'refund_payment_id': (refund_payment.id
                                                 if refund_payment else None),
                          'reason': reason_clean,
                          'by_user_id': user_id,
                          'approval': _approval_block})
            # When forfeit is involved, write a dedicated approval row so
            # filters like action='forfeit_approved' can find it without
            # parsing JSON.
            if forfeit_amount > 0.005:
                audit_writer('Reservation', reservation.id, 'forfeit_approved',
                             {'forfeit_amount': round(forfeit_amount, 2),
                              'threshold': get_forfeit_approval_threshold()},
                             {'approver_user_id':  approver_user_id,
                              'approver_is_admin': bool(approver_is_admin),
                              'approval_reason':   _appr_reason_clean,
                              'cancellation_reason': reason_clean,
                              'reservation_id':    reservation.id})
        except Exception:
            pass

    return {
        'refund_payment':  refund_payment,
        'refund_amount':   round(refund_amount, 2),
        'forfeit_amount':  round(forfeit_amount, 2),
        'voucher_amount':  round(voucher_amount, 2),
        'voucher':         issued_voucher,
        'voucher_code':    (issued_voucher.voucher_code if issued_voucher else None),
        'disposition':     disposition,
    }


def _generate_voucher_code(prefix: str = 'CV') -> str:
    """Return a short, unique-ish voucher code: CV-YYYYMMDD-XXXX (hex)."""
    from datetime import date as _d
    import secrets as _secrets
    return f'{prefix}-{_d.today().strftime("%Y%m%d")}-{_secrets.token_hex(2).upper()}'


def issue_credit_voucher(*, guest_id, amount, reservation_id=None,
                         expiry_days=None, user_id=None, notes=None,
                         audit_writer=None):
    """Create a CreditVoucher row with a unique code and audit-log it.

    Returns the persisted voucher (after flush; caller commits).
    """
    from app.models import CreditVoucher, db as _db
    from datetime import date as _d, timedelta as _td

    if guest_id is None:
        raise ValueError('guest_id is required')
    if amount is None or float(amount) <= 0.005:
        raise ValueError('voucher amount must be > 0')

    expiry = (_d.today() + _td(days=int(expiry_days))) if expiry_days else None

    # Retry on the rare collision — codes are 16 bits of entropy + date.
    for _ in range(5):
        code = _generate_voucher_code()
        if not CreditVoucher.query.filter_by(voucher_code=code).first():
            break
    else:
        raise RuntimeError('Could not allocate a unique voucher code')

    voucher = CreditVoucher(
        voucher_code               = code,
        guest_id                   = int(guest_id),
        issued_amount              = round(float(amount), 2),
        redeemed_amount            = 0,
        issued_date                = _d.today(),
        expiry_date                = expiry,
        status                     = 'active',
        issued_from_reservation_id = reservation_id,
        issued_by_user_id          = user_id,
        notes                      = (notes or None),
    )
    _db.session.add(voucher)
    _db.session.flush()

    if audit_writer is not None:
        try:
            audit_writer('CreditVoucher', voucher.id, 'voucher_created',
                         None,
                         {'voucher_code':   code,
                          'guest_id':       int(guest_id),
                          'issued_amount':  float(voucher.issued_amount),
                          'expiry_date':    expiry.isoformat() if expiry else None,
                          'issued_from_reservation_id': reservation_id,
                          'by_user_id':     user_id})
        except Exception:
            pass

    return voucher


def compute_voucher_status(voucher) -> str:
    """Derive the canonical status: active / fully_redeemed / expired / cancelled.

    Reads the snapshot columns and the calendar; never mutates the row.
    Use ``refresh_voucher_status`` to push a derived state back into the
    column when it has changed.
    """
    if voucher is None:
        return 'cancelled'
    if voucher.cancelled_at is not None:
        return 'cancelled'
    issued = float(voucher.issued_amount or 0)
    redeemed = float(voucher.redeemed_amount or 0)
    if redeemed + 0.005 >= issued:
        return 'fully_redeemed'
    if voucher.expiry_date is not None:
        from datetime import date as _d
        if voucher.expiry_date < _d.today():
            return 'expired'
    return 'active'


def refresh_voucher_status(voucher, *, audit_writer=None) -> str:
    """Recompute the status and persist it if it changed. Returns the new status."""
    from datetime import datetime as _dt
    if voucher is None:
        return 'cancelled'
    new_status = compute_voucher_status(voucher)
    if new_status != voucher.status:
        old = voucher.status
        voucher.status = new_status
        if new_status == 'fully_redeemed' and voucher.fully_redeemed_at is None:
            voucher.fully_redeemed_at = _dt.utcnow()
        if new_status == 'expired' and voucher.expired_at is None:
            voucher.expired_at = _dt.utcnow()
        if audit_writer is not None:
            try:
                action = ('voucher_expired' if new_status == 'expired'
                          else 'voucher_fully_redeemed' if new_status == 'fully_redeemed'
                          else 'voucher_status_changed')
                audit_writer('CreditVoucher', voucher.id, action,
                             {'status': old},
                             {'status': new_status,
                              'redeemed_amount': float(voucher.redeemed_amount or 0),
                              'issued_amount':   float(voucher.issued_amount or 0)})
            except Exception:
                pass
    return new_status


def voucher_remaining(voucher) -> float:
    """Return the live remaining balance (issued − redeemed; never negative)."""
    if voucher is None:
        return 0.0
    return max(0.0, round(float(voucher.issued_amount or 0)
                          - float(voucher.redeemed_amount or 0), 2))


def redeem_credit_voucher(voucher, reservation, amount, *, user_id=None,
                          create_payment=True, payment_mode_id=None,
                          notes=None, audit_writer=None):
    """Redeem ``amount`` from ``voucher`` against ``reservation``.

    Validates expiry / status / available balance. Inserts a
    CreditVoucherRedemption row and (by default) a Payment row tagged
    payment_purpose='settlement' so the booking ledger sees the credit
    as cash. Caller commits the transaction.

    Returns ``{'redemption': CreditVoucherRedemption,
               'payment':    Payment | None,
               'remaining':  float}``.
    """
    from app.models import CreditVoucher, CreditVoucherRedemption, Payment, PaymentMode, db as _db
    from datetime import datetime as _dt, date as _d

    if voucher is None:
        raise ValueError('voucher is required')
    if reservation is None:
        raise ValueError('reservation is required')

    # Refresh status first — surfaces an expiry that hadn't been stamped yet.
    refresh_voucher_status(voucher, audit_writer=audit_writer)

    if voucher.status != 'active':
        raise ValueError(f'Voucher is {voucher.status}; cannot redeem.')
    if voucher.expiry_date is not None and voucher.expiry_date < _d.today():
        raise ValueError(f'Voucher expired on {voucher.expiry_date.isoformat()}.')

    amount = round(float(amount or 0), 2)
    if amount <= 0.005:
        raise ValueError('Redemption amount must be greater than zero.')
    available = voucher_remaining(voucher)
    if amount > available + 0.01:
        raise ValueError(f'Redemption ₹{amount:,.2f} exceeds available '
                         f'voucher balance ₹{available:,.2f}.')

    # Optionally post an offsetting Payment so the folio shows the credit
    # as cash. Use the configured 'Voucher' or 'Credit Voucher' PaymentMode
    # if one exists; otherwise fall back to a direct_payment cash-equivalent.
    payment = None
    if create_payment:
        if payment_mode_id:
            pm = _db.session.get(PaymentMode, int(payment_mode_id))
        else:
            pm = (PaymentMode.query
                  .filter(PaymentMode.is_active.is_(True))
                  .filter(db.func.lower(PaymentMode.name).in_(
                      ['voucher', 'credit voucher', 'voucher redemption']))
                  .first())
            if pm is None:
                # Last-resort fallback — Cash so the row passes the
                # mode FK constraint. Reports filter by purpose, not mode,
                # so this still flows correctly.
                pm = PaymentMode.query.filter_by(name='Cash').first()
        if pm is None:
            raise RuntimeError('No payment mode available for voucher redemption.')
        payment = Payment(
            reservation_id   = reservation.id,
            payment_mode_id  = pm.id,
            amount           = amount,
            payment_date     = _d.today(),
            reference_number = f'VOUCHER:{voucher.voucher_code}',
            payment_purpose  = 'settlement',
            notes            = (notes or f'Voucher {voucher.voucher_code} redemption'),
        )
        _db.session.add(payment)
        _db.session.flush()

    voucher.redeemed_amount = round(float(voucher.redeemed_amount or 0) + amount, 2)
    redemption = CreditVoucherRedemption(
        voucher_id        = voucher.id,
        reservation_id    = reservation.id,
        amount            = amount,
        redeemed_at       = _dt.utcnow(),
        redeemed_by_user_id = user_id,
        payment_id        = (payment.id if payment else None),
        notes             = (notes or None),
    )
    _db.session.add(redemption)
    _db.session.flush()

    new_status = refresh_voucher_status(voucher, audit_writer=audit_writer)
    remaining_after = voucher_remaining(voucher)

    if audit_writer is not None:
        try:
            audit_writer('CreditVoucher', voucher.id, 'voucher_used',
                         {'redeemed_before': round(float(voucher.redeemed_amount) - amount, 2),
                          'remaining_before': available},
                         {'redemption_id':   redemption.id,
                          'amount':          amount,
                          'reservation_id':  reservation.id,
                          'payment_id':      (payment.id if payment else None),
                          'remaining_after': remaining_after,
                          'status_after':    new_status,
                          'by_user_id':      user_id})
        except Exception:
            pass

    return {'redemption': redemption, 'payment': payment, 'remaining': remaining_after}


def expire_credit_voucher(voucher, *, user_id=None, audit_writer=None):
    """Force-mark a voucher expired (admin / scheduled job). Caller commits."""
    from datetime import datetime as _dt
    if voucher is None:
        raise ValueError('voucher is required')
    if voucher.status not in ('active',):
        return voucher
    voucher.status = 'expired'
    voucher.expired_at = _dt.utcnow()
    if audit_writer is not None:
        try:
            audit_writer('CreditVoucher', voucher.id, 'voucher_expired',
                         {'status': 'active'},
                         {'status': 'expired',
                          'remaining': voucher_remaining(voucher),
                          'by_user_id': user_id})
        except Exception:
            pass
    return voucher


def credit_status(reservation):
    """Cheap, side-effect-free derivation: 'Open' / 'Partial' / 'Settled' / 'NoCredit'.

    Apr 2026 final tightening: also returns 'Overdue' when the credit
    has been outstanding for more than the configured aging threshold
    (default 30 days) — derived from credit_approved_at.
    """
    if reservation is None:
        return 'NoCredit'
    original = float(getattr(reservation, 'credit_amount', 0) or 0)
    if original <= 0.005:
        return 'NoCredit'
    settled = float(getattr(reservation, 'credit_settled_amount', 0) or 0)
    remaining = round(original - settled, 2)
    if remaining <= 0.005:
        return 'Settled'
    # Aging — Overdue takes precedence over Partial / Open
    try:
        from datetime import date as _date_cls
        approved_at = getattr(reservation, 'credit_approved_at', None)
        if approved_at is not None:
            days_open = (_date_cls.today() - approved_at.date()).days
            if days_open > 30:
                return 'Overdue'
    except Exception:
        pass
    if settled > 0.005:
        return 'Partial'
    return 'Open'


def credit_lifecycle_summary(reservation) -> dict:
    """Lifecycle visibility for the Credit Ledger UI.

    Returns the full view that the front desk needs to triage receivables
    at a glance — without joining tables in the template.

    Returns::
        {
          'status':            'Open' | 'Partial' | 'Settled' | 'Overdue' | 'NoCredit',
          'original':          float,
          'recovered':         float,
          'remaining':         float,
          'days_outstanding':  int | None,
          'last_payment_date': date | None,
          'last_payment_amount': float | None,
          'aging_bucket':      '0-7' | '8-15' | '16-30' | '30+' | None,
        }
    """
    out = {
        'status':              credit_status(reservation),
        'original':            0.0,
        'recovered':           0.0,
        'remaining':           0.0,
        'days_outstanding':    None,
        'last_payment_date':   None,
        'last_payment_amount': None,
        'aging_bucket':        None,
    }
    if reservation is None or out['status'] == 'NoCredit':
        return out
    out['original']  = float(reservation.credit_amount or 0)
    out['recovered'] = float(reservation.credit_settled_amount or 0)
    out['remaining'] = max(0.0, round(out['original'] - out['recovered'], 2))

    from datetime import date as _date_cls
    approved_at = getattr(reservation, 'credit_approved_at', None)
    if approved_at is not None:
        days = (_date_cls.today() - approved_at.date()).days
        out['days_outstanding'] = days
        if days <= 7:
            out['aging_bucket'] = '0-7'
        elif days <= 15:
            out['aging_bucket'] = '8-15'
        elif days <= 30:
            out['aging_bucket'] = '16-30'
        else:
            out['aging_bucket'] = '30+'

    # Most recent credit_recovery payment on this folio
    try:
        last_pmt = None
        for p in (reservation.payments or []):
            if getattr(p, 'is_voided', False):
                continue
            if (getattr(p, 'payment_purpose', '') or '').lower() != 'credit_recovery':
                continue
            if last_pmt is None or (p.payment_date and last_pmt.payment_date
                                    and p.payment_date > last_pmt.payment_date):
                last_pmt = p
        if last_pmt is not None:
            out['last_payment_date']   = last_pmt.payment_date
            out['last_payment_amount'] = float(last_pmt.amount or 0)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Double-billing guard (Phase-fix)
# ---------------------------------------------------------------------------
# The night audit posts one ExtraCharge per reservation per night with
# charge_type='room_rent'. That same nightly amount is ALSO captured by
# ReservationNightRate.final_rate (or the rate_per_night × nights legacy
# fallback) and is what calculate_stay_amount uses as room_charges.
#
# Historically we summed ALL ExtraCharges into extra_charges — which
# meant room revenue was counted twice (once in room_charges, once in
# extra_charges), with matching double-GST on the invoice.
#
# The fix: treat ReservationNightRate / rate×nights as the single room-
# revenue source and EXCLUDE room_rent ExtraCharges from the "extras"
# aggregation. The underlying rows are preserved on disk (data safety);
# we just stop re-counting them.
ROOM_RENT_CHARGE_TYPE = 'room_rent'

# Charge types that represent ROOM REVENUE on the ExtraCharge ledger and
# must therefore be:
#   * SUMMED into get_room_revenue() (CASE A)
#   * EXCLUDED from extras aggregation in calculate_stay_amount
#   * EXCLUDED from generate_extra_charge_tax_lines (their GST is produced
#     once via the room-revenue path)
# 'room_upsell' is the corrective row posted by
# convert_overpayment_to_upsell when the front desk/admin reclassifies an
# above-tariff overpayment as recognised upsell revenue.
ROOM_REVENUE_CHARGE_TYPES = frozenset({'room_rent', 'room_upsell'})


def _non_room_rent_charges(charges):
    """Filter an iterable of ExtraCharge to skip night-audit room_rent rows.

    Accepts any iterable of ExtraCharge-like objects (ORM instances). Uses
    ``getattr`` defensively so legacy rows without charge_type (NULL) fall
    through as extras — only explicit room_rent rows are excluded.
    """
    return [c for c in charges
            if (getattr(c, 'charge_type', None) or '') not in ROOM_REVENUE_CHARGE_TYPES]


def is_room_rent_charge(ec) -> bool:
    """Return True iff `ec` is part of room revenue on the ledger.

    Includes night-audit-posted ``room_rent`` rows AND the corrective
    ``room_upsell`` rows produced by ``convert_overpayment_to_upsell``.
    Both must be summed as room revenue (not extras) so that the bill
    grand_total reconciles with what the guest actually paid.
    """
    return (getattr(ec, 'charge_type', None) or '') in ROOM_REVENUE_CHARGE_TYPES


# ---------------------------------------------------------------------------
# Single source of truth for room revenue (CASE A / CASE B normaliser)
# ---------------------------------------------------------------------------
# The PMS has two competing ways of representing room revenue:
#
#   * "Room Accommodation"  — rate_per_night × nights, backed by
#     ReservationNightRate rows for per-night granularity.
#   * "Room Rent"           — one ExtraCharge per night with
#     charge_type='room_rent', posted by the night audit.
#
# Historically the two coexisted, causing double-billing on invoices,
# KPI inflation, and doubled GST. The resolution is a strict priority:
#
#   CASE A (AUDITED RESERVATION)
#     At least one room_rent ExtraCharge exists  →  use the SUM of those
#     rows as the authoritative room revenue. This is the ledger truth
#     — what was actually posted and what every downstream report /
#     invoice / tax line was calculated against at audit time.
#
#   CASE B (PRE-AUDIT / LEGACY)
#     No room_rent rows exist yet  →  fall back to
#     ReservationNightRate.final_rate (per-night if populated), else
#     rate_per_night × nights. This path keeps same-day check-outs and
#     legacy data usable before / without night audit.
#
# In audited reservations CASE A and CASE B should agree to the rupee;
# the priority only matters when they drift (mid-stay rate override,
# audit reopen, etc.) — in which case ledger truth wins.

def get_room_revenue(reservation) -> 'Decimal':
    """Return the authoritative room revenue for `reservation`.

    Prefers the sum of posted room_rent ExtraCharges (CASE A). Falls
    back to ReservationNightRate / rate_per_night × nights (CASE B).
    Always returns a rounded Decimal; never raises.
    """
    from app.financial import money, ZERO
    # CASE A: audit-posted room_rent rows take priority.
    room_rent_total = ZERO
    has_room_rent = False
    try:
        for ec in getattr(reservation, 'extra_charges', None) or []:
            if is_room_rent_charge(ec):
                room_rent_total += money(ec.amount)
                has_room_rent = True
    except Exception:
        # Defensive: a detached ORM instance shouldn't break billing.
        has_room_rent = False
    if has_room_rent:
        return money(room_rent_total)

    # CASE B: pre-audit / legacy fallback. Use per-night rows if present,
    # else the reservation's flat tariff × nights.
    nights = max(0, (reservation.departure_date - reservation.arrival_date).days)
    try:
        from app.nightly_rate_service import validate_nightly_rows
        validation = validate_nightly_rows(reservation)
        if validation['rows']:
            blocking = [w for w in validation['warnings']
                        if w.startswith(('MISSING_DATES', 'DUPLICATE_DATES'))]
            if not blocking:
                return money(sum(money(r.final_rate)
                                 for r in validation['rows']))
    except Exception:
        pass
    return money(money(getattr(reservation, 'rate_per_night', 0) or 0) * nights)


def get_room_charge_lines(reservation) -> list:
    """Return a list of per-night display lines for the "Room Charges"
    section of invoices / folio prints.

    Each entry is a dict ``{date, description, amount, source}`` where:
      * ``source`` is 'room_rent' (CASE A — from ExtraCharge rows) or
        'tariff'     (CASE B — synthesised from nightly rates / rate×nights).
      * ``amount``   is a float (2dp), ready for template rendering.

    Single-source priority matches ``get_room_revenue`` so invoice row
    totals and the headline Room Charges figure always reconcile.
    """
    from app.financial import money
    lines: list = []

    # CASE A — iterate posted room_rent rows in date order.
    rr = sorted(
        (ec for ec in (getattr(reservation, 'extra_charges', None) or [])
         if is_room_rent_charge(ec)),
        key=lambda e: (e.charge_date, e.id),
    )
    if rr:
        for ec in rr:
            lines.append({
                'date':        ec.charge_date,
                'description': ec.description or f'Room Rent — {ec.charge_date.strftime("%d %b")}',
                'amount':      float(money(ec.amount)),
                'source':      'room_rent',
                'extra_charge_id': ec.id,
            })
        return lines

    # CASE B — synthesise from nightly rates if present, else flat rate.
    try:
        from app.nightly_rate_service import validate_nightly_rows
        validation = validate_nightly_rows(reservation)
        if validation['rows']:
            blocking = [w for w in validation['warnings']
                        if w.startswith(('MISSING_DATES', 'DUPLICATE_DATES'))]
            if not blocking:
                for row in validation['rows']:
                    lines.append({
                        'date':        row.stay_date,
                        'description': f'Room Accommodation — {row.stay_date.strftime("%d %b")}',
                        'amount':      float(money(row.final_rate)),
                        'source':      'tariff',
                        'extra_charge_id': None,
                    })
                return lines
    except Exception:
        pass

    # Final fallback — one aggregate line (pre-nightly-rows era).
    nights = max(0, (reservation.departure_date - reservation.arrival_date).days)
    rate = float(money(getattr(reservation, 'rate_per_night', 0) or 0))
    if nights and rate:
        lines.append({
            'date':        reservation.arrival_date,
            'description': f'Room Accommodation ({nights} night'
                           f'{"s" if nights != 1 else ""} × ₹{rate:,.0f})',
            'amount':      float(money(rate * nights)),
            'source':      'tariff',
            'extra_charge_id': None,
        })
    return lines


# ---------------------------------------------------------------------------
# Invoice rate-breakdown (transparency section, not guest-facing by default)
# ---------------------------------------------------------------------------

def build_rate_breakdown(reservation, gst_summary=None) -> dict:
    """Compute the transparency block shown under "Rate Breakdown" on the
    invoice. Pure derivation — no DB writes, never raises.

    Returns a dict with:
      * published_rate   — rack rate (room_type.base_rate, pre-tax)
      * offered_rate     — rate actually applied (reservation.rate_per_night)
      * discount_per_night  — max(0, published - offered)
      * discount_total      — full-stay reservation discount_amount
      * gst_type         — 'Inclusive' or 'Exclusive' (per room_type flag)
      * taxable_amount   — from the already-aggregated FolioGSTSummary
      * gst_amount       — sum of CGST + SGST + IGST on the reservation
      * grand_total      — taxable + tax (mirrors invoice grand total)
      * nights           — stay length (for context)
      * currency         — 'INR'
      * source           — 'room_rent' (audit ledger) or 'tariff' (pre-audit)

    Safe to call with or without a gst_summary — falls back to zero
    aggregates when the summary isn't supplied (so callers who don't
    need tax figures can still get rate comparison).
    """
    from app.financial import money, round2, ZERO
    from decimal import Decimal

    rt = getattr(reservation, 'room_type', None)
    published = money(getattr(rt, 'base_rate', None) or 0) if rt else ZERO
    # Prefer reservation.standard_tariff (captured at booking time — the
    # authoritative "rack rate at point of sale"); fall back to the
    # current room_type.base_rate only if the reservation wasn't tagged.
    snapshot = money(getattr(reservation, 'standard_tariff', None) or 0)
    if snapshot > ZERO:
        published = snapshot

    offered = money(getattr(reservation, 'rate_per_night', None) or 0)
    # Per-night discount is only meaningful when published > offered.
    # A negative diff (an upsell) is reported as 0 here — upsell shows
    # up separately on the adjustment tracker.
    disc_per_night = published - offered if published > offered else ZERO

    disc_total = money(getattr(reservation, 'discount_amount', None) or 0)

    is_incl = bool(getattr(rt, 'is_gst_inclusive', False)) if rt else False
    gst_type = 'Inclusive' if is_incl else 'Exclusive'

    nights = max(0, (reservation.departure_date - reservation.arrival_date).days)

    # Pull aggregated tax figures from the caller-supplied summary; zero
    # if not provided so the block still renders.
    if gst_summary is not None:
        taxable = money(getattr(gst_summary, 'taxable_amount', 0) or 0)
        total_tax = money(getattr(gst_summary, 'total_tax', 0) or 0)
        grand = money(getattr(gst_summary, 'grand_total', 0) or 0)
    else:
        taxable = total_tax = grand = ZERO

    has_room_rent = any(is_room_rent_charge(ec)
                        for ec in (reservation.extra_charges or []))
    source = 'room_rent' if has_room_rent else 'tariff'

    return {
        'published_rate':    round2(published),
        'offered_rate':      round2(offered),
        'discount_per_night':round2(disc_per_night),
        'discount_total':    round2(disc_total),
        'gst_type':          gst_type,
        'is_gst_inclusive':  is_incl,
        'taxable_amount':    round2(taxable),
        'gst_amount':        round2(total_tax),
        'grand_total':       round2(grand),
        'nights':            nights,
        'currency':          'INR',
        'source':            source,
    }


def calculate_stay_amount(reservation):
    from app.financial import money, round2, ZERO
    import logging as _csa_logging
    _csa_log = _csa_logging.getLogger('app.services')

    nights = (reservation.departure_date - reservation.arrival_date).days

    # ── Room revenue: single source via get_room_revenue() ──────────
    # CASE A: room_rent ExtraCharges present → sum them.
    # CASE B: fall back to ReservationNightRate / rate_per_night × nights.
    # See the docstring on get_room_revenue for the full rationale.
    room_charges = get_room_revenue(reservation)
    has_room_rent = any(is_room_rent_charge(ec)
                        for ec in (reservation.extra_charges or []))
    _csa_source = 'room_rent_extras' if has_room_rent else 'tariff'
    _csa_log.debug(
        'calculate_stay_amount: res=%d source=%s room_charges=%s',
        reservation.id, _csa_source, room_charges)
    # ────────────────────────────────────────────────────────────────

    # Exclude night-audit room_rent rows — they ARE room_charges (CASE A)
    # or a duplicate (CASE B where a stray row got posted). Never sum
    # them into extras.
    # Reversal entries (is_reversal=True) carry POSITIVE amounts in the
    # column (CHECK amount>=0 stays intact) but logically subtract — sign
    # is applied here via signed_extra_charge_amount.
    extra_charges = sum(
        (money(signed_extra_charge_amount(ec)) for ec in reservation.extra_charges
         if not is_room_rent_charge(ec)),
        ZERO,
    )

    # Discount handling:
    #   CASE A — room_rent is the authoritative ledger and already
    #            reflects any discount applied at posting time.
    #   CASE B (nightly rows) — final_rate has discount baked in.
    #   CASE B (flat rate)    — apply the reservation-level discount.
    # The simplest invariant: only apply reservation.discount_amount
    # when we fell back to the flat rate path (no nightly rows, no
    # room_rent). Detected by checking both collections.
    _nightly_rows_present = False
    try:
        from app.nightly_rate_service import validate_nightly_rows
        _v = validate_nightly_rows(reservation)
        _nightly_rows_present = bool(_v['rows']) and not any(
            w.startswith(('MISSING_DATES', 'DUPLICATE_DATES'))
            for w in _v['warnings']
        )
    except Exception:
        pass
    if has_room_rent or _nightly_rows_present:
        discount = ZERO
    else:
        discount = money(getattr(reservation, 'discount_amount', None))

    total = money(room_charges + extra_charges - discount)

    # Reversal entries (is_reversal=True) keep amount > 0 to satisfy the
    # CHECK constraint but contribute -amount to the paid total.
    paid = sum(
        (money(signed_payment_amount(p)) for p in reservation.payments
         if not p.is_voided),
        ZERO
    )

    # Company credit posted at checkout (stored on CheckInRecord)
    company_credit = ZERO
    if hasattr(reservation, 'checkin_record') and reservation.checkin_record:
        company_credit = money(getattr(reservation.checkin_record, 'company_credit_posted', None))

    # ── GST & grand total ──────────────────────────────────────────────
    # `total` above is PRE-TAX. Guests pay GRAND TOTAL. The settlement
    # comparison must therefore use grand_total, not the pre-tax base —
    # otherwise an inclusive-priced ₹1200 tariff (pre-tax ₹1142.86)
    # paid ₹1200 would render as "Overpaid ₹57.14" (the bug this fix
    # addresses). Works identically for exclusive quoting: the GST is
    # always computed on top of the pre-tax base, and the guest always
    # pays the grand_total.
    #
    # compute_stay_gst is pure math — no DB writes, no TaxLine flushes —
    # so it's safe to call from every calculate_stay_amount caller
    # (dashboards, reports, hot loops).
    try:
        from app.gst_service import compute_stay_gst
        gst_amount = money(compute_stay_gst(reservation))
    except Exception:
        # Never break billing math over a GST calc hiccup — fall back
        # to zero GST (equivalent to pre-tax behaviour, matches legacy).
        _csa_log.exception('calculate_stay_amount: compute_stay_gst failed '
                           'for res=%d; falling back to 0 GST', reservation.id)
        gst_amount = ZERO
    grand_total = money(total + gst_amount)

    # ── Apr 2026 Section 5: rounding reconciliation ──
    # Guest-facing invoices show whole rupees. Settlement must compare
    # against that rounded amount — otherwise a ₹1800.50 invoice
    # displayed as ₹1801 and paid ₹1801 would appear "Overpaid 0.50".
    # We compute both the unrounded and rounded grand totals and the
    # round-off delta; settlement_balance uses the rounded value.
    _gt_unrounded = float(grand_total)
    if _gt_unrounded >= 0:
        _gt_rounded = int(_gt_unrounded + 0.5)
    else:
        _gt_rounded = -int(-_gt_unrounded + 0.5)
    _round_off = round(_gt_rounded - _gt_unrounded, 2)
    settlement_balance = money(_gt_rounded - paid - company_credit)

    # Balance is the live amount the guest STILL OWES (> 0) or has
    # OVERPAID (< 0). Measured against grand_total so it matches both
    # the invoice grand total and what the guest was actually quoted.
    balance = money(grand_total - paid - company_credit)

    # Return floats rounded to exactly 2dp for template/JSON compatibility.
    # All intermediate math was in Decimal — precision is preserved.
    return {
        'nights': nights,
        'room_charges': round2(room_charges),
        'extra_charges': round2(extra_charges),
        'discount': round2(discount),
        # Pre-tax base — kept for backward compat and for invoice GST
        # breakdown where taxable amount is shown separately from tax.
        'total': round2(total),
        # NEW: GST and tax-inclusive grand total.
        'gst_amount': round2(gst_amount),
        'grand_total': round2(grand_total),
        'paid': round2(paid),
        'company_credit': round2(company_credit),
        # Settlement balance — now grand_total-based (see comment above).
        'balance': round2(balance),
        # Apr 2026 Section 5 — rounding reconciliation snapshot.
        # Settlement comparisons + invoice display use these instead of
        # the paise-level `grand_total` so guest-facing totals tie out.
        'rounded_grand_total': round2(_gt_rounded),
        'round_off':           round2(_round_off),
        'settlement_balance':  round2(settlement_balance),
    }


def calculate_folio_amount(folio):
    """Calculate totals for a specific folio.

    Returns a dict with the same shape as calculate_stay_amount() but scoped
    to charges/payments routed to *folio*.  Room charges are NOT included here
    because they belong to the reservation level; only extra charges and
    payments explicitly assigned to the folio are counted.
    """
    from app.financial import money, round2, ZERO

    # Defensive: exclude any room_rent charges even though the night
    # audit today posts them with folio_id=NULL. Keeps this safe if the
    # audit ever assigns a folio later. Reversal sign applied in helper.
    extra_charges = sum(
        (money(signed_extra_charge_amount(ec)) for ec in folio.charges
         if not is_room_rent_charge(ec)),
        ZERO,
    )

    paid = sum(
        (money(signed_payment_amount(p)) for p in folio.payments
         if not p.is_voided),
        ZERO
    )

    balance = money(extra_charges - paid)

    return {
        'extra_charges': round2(extra_charges),
        'paid': round2(paid),
        'balance': round2(balance),
    }


def apply_tariff_adjustment(reservation, *, authorized_by_user_id=None):
    """Compute and store tariff adjustment fields on a reservation.

    Compares rate_per_night against room_type.base_rate (standard tariff).
    Must be called after reservation.room_type is accessible and rate_per_night is set.

    Apr 2026 — also stamps source-captured leakage classification when
    the actual rate falls below standard, so reports can show the
    AUTHORITATIVE leakage_type instead of guessing later.
    """
    from datetime import datetime as _dt
    if not reservation.room_type:
        return
    standard = Decimal(str(reservation.room_type.base_rate or 0))
    actual   = Decimal(str(reservation.rate_per_night or 0))
    reservation.standard_tariff = standard
    if standard <= 0 or actual == standard:
        reservation.adjustment_type   = None
        reservation.adjustment_amount = Decimal('0')
    elif actual < standard:
        reservation.adjustment_type   = 'LEAKAGE'
        reservation.adjustment_amount = standard - actual
        # Source-captured leakage classification — only set when not
        # already populated (don't overwrite a more specific type that
        # was set elsewhere, e.g. DISCOUNT at checkout).
        if not getattr(reservation, 'leakage_type', None):
            reservation.leakage_type = 'RATE_OVERRIDE'
            # RATE_OVERRIDE at check-in is a deliberate operator choice
            # (you can't accidentally book below standard); intent is
            # INTENTIONAL by default. UNINTENTIONAL only fires when the
            # audit detects a missing charge after the fact.
            if not getattr(reservation, 'leakage_intent', None):
                reservation.leakage_intent = 'INTENTIONAL'
            if not reservation.leakage_reason:
                reservation.leakage_reason = (
                    f'Rate ₹{float(actual):,.0f} below standard ₹{float(standard):,.0f}')
            reservation.leakage_authorized_by_user_id = authorized_by_user_id
            reservation.leakage_created_at = _dt.utcnow()
    else:
        reservation.adjustment_type   = 'UPSELL'
        reservation.adjustment_amount = actual - standard


def convert_overpayment_to_upsell(reservation, *, overpay_gross=None, reason=None,
                                   authorized_by_user_id=None):
    """Convert a guest overpayment into recognised UPSELL revenue.

    Used when the room was sold above standard tariff and the guest paid
    the higher offered rate, but the system was checked in / billed at
    the lower standard tariff — leaving a false 'Overpayment' state and
    blocking checkout. The result is a reservation whose:
      * rate_per_night reflects the agreed (sold) rate
      * room revenue includes the upsell amount
      * adjustment_type is stamped 'UPSELL' with the correct delta
      * settlement balance settles to ~0 against what the guest paid

    Parameters
    ----------
    reservation : Reservation
    overpay_gross : numeric, optional
        Gross (tax-inclusive) overpayment to convert. Derived from the
        live billing snapshot when omitted (so the Admin repair route
        works without passing anything).
    reason : str, optional
        Free-text justification, recorded on the corrective row /
        sync audit trail.
    authorized_by_user_id : int, optional
        User who authorised the conversion (for audit).

    Returns
    -------
    dict
        {ok: bool, error?: str, ... full repair snapshot ...}

    Notes
    -----
    Caller is responsible for the surrounding transaction (this helper
    only flushes — does not commit). Two-branch implementation:
      * **CASE A** (room_rent rows posted by night audit): post a single
        corrective ExtraCharge with charge_type='room_upsell' for the
        pre-tax delta. ``is_room_rent_charge`` recognises this as room
        revenue, so the existing per-night rows + the corrective sum to
        the new total.
      * **CASE B** (no audit yet): bump rate_per_night and re-sync
        ReservationNightRate rows so per-night truth matches the new
        total. NO corrective ExtraCharge is posted (would activate
        CASE A wrongly and lose the original implicit revenue).
    """
    from app.financial import money, round2, ZERO
    from app.gst_service import get_room_gst_rate
    from app.models import ExtraCharge

    if reservation is None:
        return {'ok': False, 'error': 'Reservation not found.'}
    if not reservation.room_type:
        return {'ok': False, 'error': 'Reservation has no room type.'}

    nights = max(1, (reservation.departure_date - reservation.arrival_date).days)

    # Derive current overpayment from the live billing snapshot when the
    # caller hasn't supplied one (so the Admin repair button works without
    # needing to pass anything).
    if overpay_gross is None:
        _bill = calculate_stay_amount(reservation)
        _bal  = float(_bill.get('settlement_balance',
                                _bill.get('balance', 0.0)))
        overpay_gross = -_bal if _bal < 0 else 0.0
    overpay_gross = max(0.0, float(overpay_gross))

    if overpay_gross < 0.01:
        return {'ok': False, 'error': 'No overpayment to convert.'}

    # Back out GST: the overpayment is *gross* (tax-inclusive); the
    # pre-tax portion feeds room_charges. GST is then recomputed on top
    # so the new grand_total = old grand_total + overpay_gross.
    room_type = reservation.room_type
    tariff = Decimal(str(reservation.rate_per_night or 0))
    gst_rate = get_room_gst_rate(tariff, room_type)
    pretax_increment = (Decimal(str(overpay_gross)) /
                        (Decimal('1') + gst_rate / Decimal('100'))
                        ).quantize(Decimal('0.01'))
    per_night_inc = (pretax_increment / Decimal(nights)
                    ).quantize(Decimal('0.01'))

    # CASE A test — any audit-posted (or previously-converted) room
    # revenue rows on the ledger?
    has_room_rent = any(is_room_rent_charge(ec)
                        for ec in (reservation.extra_charges or []))

    # Bump rate_per_night (the new offered/sold rate) and re-stamp
    # UPSELL on the reservation. standard_tariff is preserved by the
    # apply_tariff_adjustment call which uses room_type.base_rate.
    old_rate = Decimal(str(reservation.rate_per_night or 0))
    new_rate = old_rate + per_night_inc
    reservation.rate_per_night = new_rate
    apply_tariff_adjustment(
        reservation, authorized_by_user_id=authorized_by_user_id)

    charge_id = None
    branch    = None

    if has_room_rent:
        # CASE A — room_rent ledger is the source of truth. Post a
        # single corrective room_upsell row for the pre-tax delta;
        # get_room_revenue (CASE A) sums all room_rent + room_upsell
        # rows = original nights + delta = new total.
        label = 'Upsell Rate Adjustment — sold above tariff'
        if reason:
            label = f'{label} ({reason})'
        charge = ExtraCharge(
            reservation_id=reservation.id,
            description=label,
            amount=float(pretax_increment),
            charge_date=get_business_date(),
            charge_type='room_upsell',
            charge_category='Room',
        )
        db.session.add(charge)
        db.session.flush()
        charge_id = charge.id
        branch    = 'case_a_corrective_extracharge'
    else:
        # CASE B — no audit yet. Re-sync ReservationNightRate rows so
        # per-night final_rate matches the new total. get_room_revenue
        # (CASE B) reads those rows; rate_per_night × nights is the
        # ultimate fallback if sync fails.
        try:
            from app.nightly_rate_service import safe_sync_nightly_rates
            new_total = float(new_rate) * nights
            safe_sync_nightly_rates(
                reservation,
                reason='upsell_conversion',
                override_final_total=new_total,
            )
            branch = 'case_b_resync_nightly'
        except Exception:
            # Non-fatal — rate_per_night × nights fallback still holds.
            branch = 'case_b_rate_fallback'

    db.session.flush()

    return {
        'ok':                  True,
        'overpay_gross':       round2(Decimal(str(overpay_gross))),
        'pretax_increment':    round2(pretax_increment),
        'per_night_increment': round2(per_night_inc),
        'old_rate_per_night':  round2(old_rate),
        'new_rate_per_night':  round2(new_rate),
        'gst_rate_applied':    round2(gst_rate),
        'charge_id':           charge_id,
        'branch':              branch,
    }


class CheckInException(Exception):
    pass

class CheckInService:
    
    @staticmethod
    def express_checkin(reservation_id, room_id, staff_user_id, request_ip):
        """Create EXPRESS check-in with minimal data"""
        from app.models import CheckInRecord, Room, Reservation
        try:
            # Business date lock guard (defense-in-depth — routes also check)
            ok, lock_err = assert_business_date_unlocked(get_business_date(), 'check in')
            if not ok:
                raise CheckInException(lock_err)

            reservation = db.session.get(Reservation, reservation_id)
            if not reservation:
                raise CheckInException('Reservation not found')
            if reservation.status not in ['Reserved', 'Confirmed']:
                raise CheckInException('Invalid reservation status')
            
            room = db.session.query(Room).with_for_update().filter_by(id=room_id).first()
            if not room or room.status != 'Vacant':
                raise CheckInException('Room not available')

            # Block if another reservation already holds this room in today's window.
            # Bridge-aware via rooms_held_in_window (Group Stay R2A) — also catches
            # secondary rooms of multi-room reservations once Phase 1 UI ships.
            _held = rooms_held_in_window(
                [room_id],
                get_business_date(),
                get_business_date() + timedelta(days=1),
                exclude_res_id=reservation_id,
                active_statuses=('CheckedIn',),
            )
            if room_id in _held:
                raise CheckInException(
                    f'Room {room.room_number} is already occupied'
                )

            checkin = CheckInRecord(
                reservation_id=reservation_id,
                guest_id=reservation.guest_id,
                room_id=room_id,
                checkin_mode='EXPRESS',
                is_profile_complete=False,
                staff_user_id=staff_user_id,
                ip_address=request_ip
            )
            db.session.add(checkin)
            db.session.flush()

            reservation.status = 'CheckedIn'
            reservation.room_id = room_id
            reservation.checked_in_at = datetime.utcnow()
            room.status = 'Occupied'

            # R2A: bridge-write invariant — ensure reservation_rooms has a
            # primary row for this room. Idempotent (back-compat for already-
            # bridged Reserved/Confirmed rows that backfilled at v2.2.10).
            from app.services_group_stay import mirror_room_to_bridge
            mirror_room_to_bridge(reservation, user_id=staff_user_id, ip_address=request_ip)

            db.session.commit()

            # Audit log
            try:
                from app.models import AuditLog
                db.session.add(AuditLog(
                    entity_type='Reservation', entity_id=reservation_id,
                    action='checkin_express',
                    before_state={'status': 'Reserved'},
                    after_state={'status': 'CheckedIn', 'room_id': room_id, 'mode': 'EXPRESS'},
                    staff_user_id=staff_user_id,
                    ip_address=request_ip,
                ))
                db.session.commit()
            except Exception:
                pass

            return checkin
        except CheckInException:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise CheckInException(f'Express check-in failed: {str(e)}')

    @staticmethod
    def get_checkin_record(reservation_id):
        """Get existing check-in record or None"""
        from app.models import CheckInRecord
        return CheckInRecord.query.filter_by(reservation_id=reservation_id).first()
    
    @staticmethod
    def complete_full_checkin(reservation_id, form_data, staff_user_id, request_ip):
        """Complete FULL check-in - works for new or existing EXPRESS records"""
        from app.models import CheckInRecord, Room, Reservation, Payment, Company
        try:
            # Business date lock guard (defense-in-depth — routes also check)
            ok, lock_err = assert_business_date_unlocked(get_business_date(), 'check in')
            if not ok:
                raise CheckInException(lock_err)

            reservation = db.session.get(Reservation, reservation_id)
            if not reservation:
                raise CheckInException('Reservation not found')
            
            room_id = form_data.get('room_id')
            if room_id is not None:
                try:
                    room_id = int(room_id)
                except (ValueError, TypeError):
                    room_id = None
            room = db.session.query(Room).with_for_update().filter_by(id=room_id).first() if room_id else None
            if not room:
                raise CheckInException('Please select a room')
            # Allow room already assigned to this reservation (express → full upgrade)
            already_assigned = reservation.room_id == room.id
            if room.status != 'Vacant' and not already_assigned:
                raise CheckInException(f'Room {room.room_number} is not available (status: {room.status})')

            # Block if another reservation already holds this room in today's window.
            # Bridge-aware via rooms_held_in_window (Group Stay R2A) — also catches
            # secondary rooms of multi-room reservations once Phase 1 UI ships.
            _held = rooms_held_in_window(
                [room.id],
                get_business_date(),
                get_business_date() + timedelta(days=1),
                exclude_res_id=reservation_id,
                active_statuses=('CheckedIn',),
            )
            if room.id in _held:
                raise CheckInException(
                    f'Room {room.room_number} is already occupied'
                )

            company_id = form_data.get('company_id')
            if company_id is not None:
                try:
                    company_id = int(company_id) if company_id else None
                except (ValueError, TypeError):
                    company_id = None
            credit_warning = None
            if company_id:
                total_amount = float(form_data.get('total_amount', 0))
                credit_result = CheckInService.check_corporate_credit(company_id, total_amount)
                if isinstance(credit_result, dict) and credit_result.get('warning'):
                    credit_warning = credit_result  # passed to caller for UI display
            
            # Get or create check-in record
            checkin = CheckInRecord.query.filter_by(reservation_id=reservation_id).first()
            if not checkin:
                checkin = CheckInRecord(
                    reservation_id=reservation_id,
                    guest_id=reservation.guest_id,
                    room_id=room_id,
                    staff_user_id=staff_user_id,
                    ip_address=request_ip
                )
                db.session.add(checkin)
            else:
                # Update existing record
                checkin.room_id = room_id
                checkin.updated_at = datetime.utcnow()
            
            # Update with full data
            checkin.checkin_mode = 'FULL'
            checkin.is_profile_complete = reservation.guest.is_kyc_complete()
            checkin.guest_photo_path = form_data.get('guest_photo_path')
            checkin.signature_path = form_data.get('signature_path')
            checkin.billing_responsibility = form_data.get('billing_responsibility', 'Guest')
            checkin.company_id = company_id
            checkin.company_billing_ref = form_data.get('company_billing_ref')
            _raw_deposit = float(form_data.get('deposit_amount', 0) or 0)
            if _raw_deposit < 0:
                raise CheckInException('Deposit amount cannot be negative.')
            checkin.deposit_amount = round(_raw_deposit, 2)
            _dpm = form_data.get('deposit_payment_mode_id')
            if _dpm:
                from app.models import PaymentMode
                _dpm_int = int(_dpm)
                _dpm_obj = PaymentMode.query.filter_by(id=_dpm_int, is_active=True).first()
                if not _dpm_obj:
                    raise CheckInException('Invalid or inactive deposit payment mode selected.')
                checkin.deposit_payment_mode_id = _dpm_int
            else:
                checkin.deposit_payment_mode_id = None
            checkin.device_info = form_data.get('device_info')
            
            db.session.flush()
            
            # Update reservation
            if reservation.status != 'CheckedIn':
                reservation.status = 'CheckedIn'
                reservation.checked_in_at = datetime.utcnow()
            reservation.room_id = room_id

            # Update room
            if room.status != 'Occupied':
                room.status = 'Occupied'

            # R2A: bridge-write invariant — ensure reservation_rooms has a
            # primary row for this room. Idempotent.
            from app.services_group_stay import mirror_room_to_bridge
            mirror_room_to_bridge(reservation, user_id=staff_user_id, ip_address=request_ip)
            
            # Process deposit payment
            if checkin.deposit_amount > 0 and checkin.deposit_payment_mode_id:
                payment = Payment(
                    reservation_id=reservation_id,
                    payment_mode_id=checkin.deposit_payment_mode_id,
                    amount=checkin.deposit_amount,
                    payment_date=get_business_date()
                )
                db.session.add(payment)
            
            # company.credit_used is updated at checkout once the actual bill is known;
            # the deposit is already recorded in the Payment table above.
            
            db.session.commit()

            # Audit log
            try:
                from app.models import AuditLog
                db.session.add(AuditLog(
                    entity_type='Reservation', entity_id=reservation_id,
                    action='checkin_full',
                    before_state={'status': 'Reserved'},
                    after_state={
                        'status': 'CheckedIn', 'room_id': room_id, 'mode': 'FULL',
                        'billing': checkin.billing_responsibility,
                        'deposit': float(checkin.deposit_amount or 0),
                    },
                    staff_user_id=staff_user_id,
                    ip_address=request_ip,
                ))
                db.session.commit()
            except Exception:
                pass

            return checkin
        except CheckInException:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            raise CheckInException(f'Full check-in failed: {str(e)}')

    @staticmethod
    def check_corporate_credit(company_id, total_amount):
        """Validate corporate credit at check-in.

        Returns True if credit is sufficient.  Logs a warning if the estimated
        stay exceeds available credit but does NOT block check-in — the hard
        limit is enforced at checkout when the final bill is known.
        Raises CheckInException only if the company does not exist.
        """
        from app.models import Company
        import logging as _cc_log
        if not company_id:
            return True
        company = Company.query.get(company_id)
        if not company:
            raise CheckInException('Company not found')
        if float(company.credit_limit or 0) == 0:
            return True  # no limit set
        available_credit = float(company.credit_limit or 0) - float(company.credit_used or 0)
        if total_amount > available_credit:
            # Log by ID only — company name is PII-adjacent B2B data that
            # shouldn't appear in log files. Name can be looked up from
            # company_id if needed for incident investigation.
            _cc_log.getLogger(__name__).warning(
                'Corporate credit warning: company_id=%s available=%.2f, estimated_stay=%.2f',
                company.id, available_credit, total_amount)
            # Return warning info instead of blocking
            return {
                'warning': True,
                'available_credit': available_credit,
                'estimated_total': total_amount,
                'company_name': company.name,
            }
        return True
