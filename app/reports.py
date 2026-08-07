"""
Reports Export Blueprint
=========================
All reports are available in two formats:
  - HTML (screen view, with Print-to-PDF button)
  - Excel (.xlsx) download via openpyxl

Reports:
  GET /reports/                             — Report hub
  GET /reports/flash                        — Manager Flash Report (daily summary)
  GET /reports/inhouse                      — In-House Guest List
  GET /reports/arrivals?date=YYYY-MM-DD     — Arrivals list
  GET /reports/departures?date=YYYY-MM-DD   — Departures list
  GET /reports/occupancy?date=YYYY-MM-DD    — Occupancy summary
  GET /reports/revenue?from=&to=            — Revenue by date range
  GET /reports/payments?from=&to=           — Payment collection by mode
  GET /reports/guest-history?q=             — Guest stays search
  GET /reports/shift-reconciliation?date=   — Shift cash reconciliation
  GET /reports/front-office-mis?from=&to=  — Front Office MIS Report (HTML / Excel / JSON)
  GET /reports/guest-report?from=&to=      — Guest Report (billing, payments, balance)
  GET /reports/room-revenue?from=&to=      — Room Revenue Report (ARR, RevPAR, occupancy, discount audit)

All routes accept ?format=excel to return an .xlsx file.
"""

import io
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, send_file, Response, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app.models import (db, Reservation, Room, RoomType, Guest, Payment, ExtraCharge,
                        NightAuditLog, PaymentMode, VoidRequest, MaintenanceRequest,
                        Company, CheckInRecord, NoShowLog, OverpaymentLog, User,
                        CICOChargeLog)
from app.services import get_business_date, calculate_stay_amount

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.before_request
@login_required
def guard():
    pass


def _require_accountant():
    return current_user.has_role('Admin', 'Manager', 'Accountant')


# ---------------------------------------------------------------------------
# Excel helper
# ---------------------------------------------------------------------------

def _excel_response(filename: str, headers: list, rows: list, title: str = '') -> Response:
    """Build an in-memory .xlsx and return it as a download."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        return Response('openpyxl not installed. Run: pip install openpyxl', status=500)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31] if title else 'Report'

    header_fill = PatternFill('solid', fgColor='1F4E79')
    header_font = Font(color='FFFFFF', bold=True)

    # Title row
    if title:
        ws.append([title])
        ws.cell(1, 1).font = Font(bold=True, size=13)
        ws.append([f'Generated: {datetime.now().strftime("%d %b %Y %H:%M")}'])
        ws.append([])

    # Headers
    header_row = ws.max_row + 1
    ws.append(headers)
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(header_row, col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Data rows
    for row in rows:
        ws.append(row)

    # Auto column width
    for col_idx in range(1, len(headers) + 1):
        max_len = max(
            (len(str(ws.cell(r, col_idx).value or '')) for r in range(1, ws.max_row + 1)),
            default=10
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, download_name=filename, as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ---------------------------------------------------------------------------
# Report Hub
# ---------------------------------------------------------------------------

@reports_bp.route('/')
def index():
    today = get_business_date()
    return render_template('reports/index.html', today=today, timedelta=timedelta)


# ---------------------------------------------------------------------------
# Arrivals
# ---------------------------------------------------------------------------

@reports_bp.route('/arrivals')
def arrivals():
    date_str = request.args.get('date', get_business_date().isoformat())
    fmt = request.args.get('format', 'html')
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = get_business_date()

    records = Reservation.query.filter(
        Reservation.arrival_date == report_date,
        Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn'])
    ).order_by(Reservation.status).all()

    if fmt == 'excel':
        headers = ['Ref', 'Guest Name', 'Phone', 'Room Type', 'Room', 'Nights', 'Adults',
                   'Children', 'Rate/Night', 'Advance Paid', 'Source', 'Status', 'Special Requests']
        rows = []
        for r in records:
            nights = (r.departure_date - r.arrival_date).days
            rows.append([
                r.booking_reference or r.id,
                r.guest.name if r.guest else '',
                r.guest.phone if r.guest else '',
                r.room_type.name if r.room_type else '',
                r.room.room_number if r.room else 'Unassigned',
                nights,
                r.adults,
                r.children,
                float(r.rate_per_night),
                float(r.advance_payment or 0),
                r.source or '',
                r.status,
                r.special_requests or '',
            ])
        return _excel_response(
            f'arrivals_{date_str}.xlsx',
            headers, rows,
            f'Arrivals — {report_date.strftime("%d %B %Y")}'
        )

    return render_template('reports/arrivals.html', records=records, report_date=report_date,
                           today=get_business_date(), timedelta=timedelta)


# ---------------------------------------------------------------------------
# Departures
# ---------------------------------------------------------------------------

@reports_bp.route('/departures')
def departures():
    date_str = request.args.get('date', get_business_date().isoformat())
    fmt = request.args.get('format', 'html')
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = get_business_date()

    records = Reservation.query.filter(
        Reservation.departure_date == report_date,
        Reservation.status.in_(['CheckedIn', 'CheckedOut'])
    ).order_by(Reservation.status).all()

    if fmt == 'excel':
        headers = ['Ref', 'Guest Name', 'Phone', 'Room', 'Room Type', 'Check-in', 'Nights',
                   'Rate/Night', 'Extra Charges', 'Total', 'Amount Paid', 'Balance', 'Status']
        rows = []
        for r in records:
            nights = (r.departure_date - r.arrival_date).days
            from app.financial import money, round2, ZERO
            # Exclude room_rent — it duplicates rate_per_night × nights.
            extras = round2(sum(
                (money(c.amount) for c in r.extra_charges
                 if (c.charge_type or '') != 'room_rent'),
                ZERO,
            )) if r.extra_charges else 0
            total = round2(money(r.rate_per_night) * nights + money(extras))
            paid = round2(sum((money(p.amount) for p in r.payments if not p.is_voided), ZERO)) if r.payments else 0
            rows.append([
                r.booking_reference or r.id,
                r.guest.name if r.guest else '',
                r.guest.phone if r.guest else '',
                r.room.room_number if r.room else '',
                r.room_type.name if r.room_type else '',
                r.arrival_date.isoformat(),
                nights,
                float(r.rate_per_night),
                extras,
                total,
                paid,
                total - paid,
                r.status,
            ])
        return _excel_response(
            f'departures_{date_str}.xlsx',
            headers, rows,
            f'Departures — {report_date.strftime("%d %B %Y")}'
        )

    return render_template('reports/departures.html', records=records, report_date=report_date,
                           today=get_business_date(), timedelta=timedelta)


# ---------------------------------------------------------------------------
# Occupancy
# ---------------------------------------------------------------------------

@reports_bp.route('/occupancy')
def occupancy():
    date_str = request.args.get('date', get_business_date().isoformat())
    fmt = request.args.get('format', 'html')
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = get_business_date()

    rooms = Room.query.order_by(Room.floor, Room.room_number).all()
    total = len(rooms)
    # Occupancy from Reservation.status (source of truth), not Room.status
    from app.kpi_helpers import get_occupancy as _report_get_occ
    _rocc = _report_get_occ()
    occupied_count = _rocc['occupied']
    # Room physical states for the breakdown panel
    vacant_count = sum(1 for r in rooms if r.status == 'Vacant')
    dirty_count = sum(1 for r in rooms if r.status == 'Dirty')
    maint_count = sum(1 for r in rooms if r.status == 'Maintenance')
    occupancy_pct = _rocc['pct']

    if fmt == 'excel':
        headers = ['Room', 'Floor', 'Type', 'Status', 'Current Guest', 'Check-out Date']
        rows = []
        for room in rooms:
            active_res = next(
                (r for r in room.reservations if r.status == 'CheckedIn'), None
            ) if hasattr(room, 'reservations') else None
            rows.append([
                room.room_number,
                room.floor,
                room.room_type.name if room.room_type else '',
                room.status,
                active_res.guest.name if active_res and active_res.guest else '',
                active_res.departure_date.isoformat() if active_res else '',
            ])
        return _excel_response(
            f'occupancy_{date_str}.xlsx',
            headers, rows,
            f'Occupancy — {report_date.strftime("%d %B %Y")} | {occupied_count}/{total} ({occupancy_pct}%)'
        )

    return render_template('reports/occupancy.html',
                           rooms=rooms, report_date=report_date,
                           total=total, occupied=occupied_count, vacant=vacant_count,
                           dirty=dirty_count, maintenance=maint_count,
                           occupancy_pct=occupancy_pct)


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------

@reports_bp.route('/revenue')
def revenue():
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    today = get_business_date()
    from_str = request.args.get('from', (today - timedelta(days=29)).isoformat())
    to_str = request.args.get('to', today.isoformat())
    fmt = request.args.get('format', 'html')

    try:
        from_date = date.fromisoformat(from_str)
        to_date = date.fromisoformat(to_str)
    except ValueError:
        from_date = today - timedelta(days=29)
        to_date = today

    # All completed + in-house reservations that overlap the date range
    checked_out = Reservation.query.filter(
        Reservation.departure_date >= from_date,
        Reservation.departure_date <= to_date + timedelta(days=1),
        Reservation.status.in_(['CheckedOut', 'CheckedIn']),
    ).all()

    # Revenue summary by room type
    by_type: dict = {}
    from app.financial import money, round2, ZERO
    by_source: dict = {}
    by_mode: dict = {}
    _total_room = ZERO
    _total_extra = ZERO
    _total_paid = ZERO
    daily_trend: dict = {}

    for r in checked_out:
        nights = (r.departure_date - r.arrival_date).days
        room_rev = money(r.rate_per_night) * nights
        # Exclude room_rent rows — they duplicate room_rev.
        extras = sum(
            (money(c.amount) for c in r.extra_charges
             if (c.charge_type or '') != 'room_rent'),
            ZERO,
        ) if r.extra_charges else ZERO
        paid = sum((money(p.amount) for p in r.payments if not p.is_voided), ZERO) if r.payments else ZERO

        _total_room += room_rev
        _total_extra += extras
        _total_paid += paid

        _rev_sum = room_rev + extras
        rt_name = r.room_type.name if r.room_type else 'Unknown'
        by_type[rt_name] = by_type.get(rt_name, 0.0) + round2(_rev_sum)

        src = r.source or 'Unknown'
        by_source[src] = by_source.get(src, 0.0) + round2(_rev_sum)

        for p in r.payments:
            if not p.is_voided:
                mode_name = p.payment_mode.name if p.payment_mode else 'Unknown'
                by_mode[mode_name] = by_mode.get(mode_name, 0.0) + round2(p.amount)

        day_key = r.departure_date.isoformat()
        daily_trend[day_key] = daily_trend.get(day_key, 0.0) + round2(_rev_sum)

    total_room_revenue = round2(_total_room)
    total_extra_revenue = round2(_total_extra)
    total_payments = round2(_total_paid)

    # Sort daily trend by date
    daily_trend = dict(sorted(daily_trend.items()))

    if fmt == 'excel':
        headers = ['Ref', 'Guest', 'Room Type', 'Room', 'Check-in', 'Check-out', 'Nights',
                   'Rate/Night', 'Room Revenue', 'Extra Charges', 'Total', 'Amount Paid',
                   'Balance', 'Source']
        rows = []
        for r in checked_out:
            nights = (r.departure_date - r.arrival_date).days
            room_rev = float(r.rate_per_night) * nights
            # Exclude room_rent rows — already counted in room_rev.
            extras = sum(
                float(c.amount) for c in r.extra_charges
                if (c.charge_type or '') != 'room_rent'
            ) if r.extra_charges else 0
            paid = sum(float(p.amount) for p in r.payments if not p.is_voided) if r.payments else 0
            rows.append([
                r.booking_reference or r.id,
                r.guest.name if r.guest else '',
                r.room_type.name if r.room_type else '',
                r.room.room_number if r.room else '',
                r.arrival_date.isoformat(),
                r.departure_date.isoformat(),
                nights,
                float(r.rate_per_night),
                room_rev,
                extras,
                room_rev + extras,
                paid,
                (room_rev + extras) - paid,
                r.source or '',
            ])
        return _excel_response(
            f'revenue_{from_str}_{to_str}.xlsx',
            headers, rows,
            f'Revenue Report — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'
        )

    return render_template('reports/revenue.html',
                           checked_out=checked_out,
                           from_date=from_date, to_date=to_date,
                           total_room_revenue=total_room_revenue,
                           total_extra_revenue=total_extra_revenue,
                           total_payments=total_payments,
                           by_type=by_type, by_source=by_source,
                           by_mode=by_mode, daily_trend=daily_trend)


# ---------------------------------------------------------------------------
# Guest History
# ---------------------------------------------------------------------------

@reports_bp.route('/guest-history')
def guest_history():
    q = request.args.get('q', '').strip()
    fmt = request.args.get('format', 'html')

    query = Guest.query
    if q:
        query = query.filter(
            db.or_(
                Guest.name.ilike(f'%{q}%'),
                Guest.phone.ilike(f'%{q}%'),
                Guest.email.ilike(f'%{q}%'),
            )
        )
    guests = query.order_by(Guest.name).limit(200).all()

    if fmt == 'excel':
        headers = ['Guest Name', 'Phone', 'Email', 'ID Type', 'ID Number',
                   'Total Stays', 'Last Stay', 'Total Revenue']
        rows = []
        for g in guests:
            stays = [r for r in g.reservations if r.status in ('CheckedOut', 'CheckedIn')] if g.reservations else []
            # Exclude room_rent — it duplicates rate_per_night × nights.
            total_rev = sum(
                float(r.rate_per_night) * (r.departure_date - r.arrival_date).days
                + sum(float(c.amount) for c in r.extra_charges
                      if (c.charge_type or '') != 'room_rent')
                for r in stays
            )
            last_stay = max((r.departure_date for r in stays), default=None)
            rows.append([
                g.name, g.phone, g.email or '',
                g.id_type or '', g.id_number or '',
                len(stays),
                last_stay.isoformat() if last_stay else '',
                total_rev,
            ])
        return _excel_response('guest_history.xlsx', headers, rows, 'Guest History')

    return render_template('reports/guest_history.html', guests=guests, q=q)


# ---------------------------------------------------------------------------
# Shift Cash Reconciliation
# ---------------------------------------------------------------------------

@reports_bp.route('/shift-reconciliation')
def shift_reconciliation():
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.models import Shift, PaymentMode

    today = get_business_date()
    date_str = request.args.get('date', today.isoformat())
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = today

    # All closed shifts for the date (by shift start date)
    shifts = (
        Shift.query
        .filter(
            db.func.date(Shift.start_time) == report_date,
            Shift.status == 'Closed',
        )
        .order_by(Shift.start_time)
        .all()
    )

    cash_mode = PaymentMode.query.filter_by(name='Cash').first()

    reconciliation = []
    for shift in shifts:
        # Expected cash: opening_cash + cash payments received during this shift
        if cash_mode:
            cash_received = float(db.session.query(func.sum(Payment.amount)).filter(
                Payment.payment_mode_id == cash_mode.id,
                Payment.created_at >= shift.start_time,
                Payment.created_at <= (shift.end_time or datetime.utcnow()),
            ).scalar() or 0)
        else:
            cash_received = 0.0

        from app.financial import money, round2
        expected_closing = round2(money(shift.opening_cash) + money(cash_received))
        declared_closing = round2(shift.closing_cash)
        variance = round(declared_closing - expected_closing, 2)

        reconciliation.append({
            'shift': shift,
            'cash_received': cash_received,
            'expected_closing': expected_closing,
            'declared_closing': declared_closing,
            'variance': variance,
        })

    return render_template(
        'reports/shift_reconciliation.html',
        reconciliation=reconciliation,
        report_date=report_date,
    )


# ---------------------------------------------------------------------------
# Manager Flash Report
# ---------------------------------------------------------------------------

@reports_bp.route('/flash')
def flash_report():
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    today = get_business_date()
    date_str = request.args.get('date', today.isoformat())
    fmt = request.args.get('format', 'html')
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = today

    # --- Room stats (source of truth: Reservation.status='CheckedIn') ---
    from app.kpi_helpers import get_occupancy, get_sellable_room_count
    _occ = get_occupancy()
    total_rooms = _occ['total']
    sellable    = _occ['sellable']
    occupied    = _occ['occupied']
    occ_pct     = _occ['pct']
    # Physical room states (for housekeeping section — these are operational,
    # not occupancy-based, so they come from Room.status).
    vacant   = Room.query.filter_by(status='Vacant', is_active=True).count()
    dirty    = Room.query.filter_by(status='Dirty', is_active=True).count()
    maint    = Room.query.filter(
        Room.is_active == True,
        db.or_(Room.is_out_of_order == True,
               Room.status.in_(['Maintenance', 'Out of Order'])),
    ).count()

    # --- Arrivals / Departures / In-house ---
    arrivals_due = Reservation.query.filter(
        Reservation.arrival_date == report_date,
        Reservation.status.in_(['Reserved', 'Confirmed', 'CheckedIn'])
    ).count()
    arrivals_done = Reservation.query.filter(
        Reservation.arrival_date == report_date,
        Reservation.status == 'CheckedIn'
    ).count()
    departures_due = Reservation.query.filter(
        Reservation.departure_date == report_date,
        Reservation.status.in_(['CheckedIn', 'CheckedOut'])
    ).count()
    departures_done = Reservation.query.filter(
        Reservation.departure_date == report_date,
        Reservation.status == 'CheckedOut'
    ).count()
    inhouse = Reservation.query.filter_by(status='CheckedIn').count()
    stayovers = Reservation.query.filter(
        Reservation.status == 'CheckedIn',
        Reservation.arrival_date < report_date,
        Reservation.departure_date > report_date
    ).count()
    no_shows = Reservation.query.filter(
        Reservation.arrival_date == report_date,
        Reservation.status == 'NoShow'
    ).count()
    cancellations = Reservation.query.filter(
        Reservation.arrival_date == report_date,
        Reservation.status == 'Cancelled'
    ).count()

    # --- Revenue for the day (cash + accrual) ---
    from app.kpi_helpers import get_daily_revenue, get_adr, get_revpar, get_accrual_revenue
    day_revenue = get_daily_revenue(report_date)
    accrual = get_accrual_revenue(report_date)

    # v2.2.11: payment-by-mode + MTD + previous-day + last-year revenue now
    # route through canonical helpers (cash basis, direct_payment category
    # only). Matches the dashboard's MTD / payment-mode tiles, eliminating
    # the prior dashboard-vs-flash-report drift.
    from app.kpi_helpers import (
        get_payment_by_mode, get_monthly_revenue, get_revenue_on_date,
    )
    by_mode = get_payment_by_mode(report_date)
    # Preserve the (name, amount) list shape for any downstream consumer
    # that iterates mode_rows directly.
    mode_rows = list(by_mode.items())

    # --- MTD revenue ---
    month_start = report_date.replace(day=1)
    mtd_revenue = get_monthly_revenue(month_start, report_date)

    # --- ARR / RevPAR (standardized: rate-based ADR, ARR*occ RevPAR) ---
    arr = get_adr()
    revpar = get_revpar(adr=arr, occ_pct=occ_pct)

    # --- Previous day comparison ---
    prev_date = report_date - timedelta(days=1)
    prev_revenue = get_revenue_on_date(prev_date)
    prev_occupied = NightAuditLog.query.filter_by(audit_date=prev_date).first()
    prev_occ_count = prev_occupied.occupancy_count if prev_occupied else 0
    # Occupancy denominator is the canonical sellable-room count, NOT the
    # raw inventory total (which includes OOO/maintenance rooms). prev_occ_count
    # is a settled NightAuditLog rooms-sold figure.
    prev_occ_pct = round(prev_occ_count / sellable * 100, 1) if sellable else 0

    # --- Same day last year ---
    ly_date = report_date.replace(year=report_date.year - 1)
    ly_revenue = get_revenue_on_date(ly_date)
    ly_audit = NightAuditLog.query.filter_by(audit_date=ly_date).first()
    ly_occ_pct = round((ly_audit.occupancy_count / sellable * 100), 1) if ly_audit and sellable else 0

    if fmt == 'excel':
        headers = ['Metric', 'Today', 'Yesterday', 'Same Day Last Year']
        rows = [
            ['Date', report_date.isoformat(), prev_date.isoformat(), ly_date.isoformat()],
            ['Occupancy %', f'{occ_pct}%', f'{prev_occ_pct}%', f'{ly_occ_pct}%'],
            ['Occupied Rooms', occupied, prev_occ_count, ly_audit.occupancy_count if ly_audit else ''],
            ['Total Rooms', total_rooms, total_rooms, total_rooms],
            ['ARR (₹)', arr, '', ''],
            ['RevPAR (₹)', revpar, '', ''],
            ['Revenue (₹)', float(day_revenue), float(prev_revenue), float(ly_revenue)],
            ['MTD Revenue (₹)', float(mtd_revenue), '', ''],
            ['Arrivals Due', arrivals_due, '', ''],
            ['Arrivals Done', arrivals_done, '', ''],
            ['Departures Due', departures_due, '', ''],
            ['Departures Done', departures_done, '', ''],
            ['In-House', inhouse, '', ''],
            ['Stayovers', stayovers, '', ''],
            ['No-Shows', no_shows, '', ''],
            ['Cancellations', cancellations, '', ''],
        ] + [[f'  {mode}', f'₹{amt:,.0f}', '', ''] for mode, amt in by_mode.items()]
        return _excel_response(
            f'flash_report_{date_str}.xlsx', headers, rows,
            f'Manager Flash Report — {report_date.strftime("%d %B %Y")}'
        )

    return render_template('reports/flash.html',
                           report_date=report_date, today=today,
                           total_rooms=total_rooms, occupied=occupied,
                           vacant=vacant, dirty=dirty, maint=maint, occ_pct=occ_pct,
                           arrivals_due=arrivals_due, arrivals_done=arrivals_done,
                           departures_due=departures_due, departures_done=departures_done,
                           inhouse=inhouse, stayovers=stayovers,
                           no_shows=no_shows, cancellations=cancellations,
                           day_revenue=day_revenue, by_mode=by_mode,
                           mtd_revenue=mtd_revenue, arr=arr, revpar=revpar,
                           accrual=accrual,
                           prev_date=prev_date, prev_revenue=prev_revenue,
                           prev_occ_pct=prev_occ_pct,
                           ly_date=ly_date, ly_revenue=ly_revenue, ly_occ_pct=ly_occ_pct,
                           timedelta=timedelta)


# ---------------------------------------------------------------------------
# In-House Guest List
# ---------------------------------------------------------------------------

@reports_bp.route('/inhouse')
def inhouse():
    fmt = request.args.get('format', 'html')
    today = get_business_date()

    from sqlalchemy.orm import subqueryload
    records = (
        Reservation.query
        .filter_by(status='CheckedIn')
        .options(
            subqueryload(Reservation.payments),
            subqueryload(Reservation.extra_charges),
        )
        .order_by(Reservation.departure_date, Reservation.room_id)
        .all()
    )

    # Flag overdue checkouts
    for r in records:
        r._overdue = r.departure_date < today
        nights_stayed = (today - r.arrival_date).days
        r._nights_stayed = nights_stayed
        nights_remaining = (r.departure_date - today).days
        r._nights_remaining = nights_remaining
        from app.services import calculate_stay_amount
        billing = calculate_stay_amount(r)
        # Apr 2026 Section 4: report displays must show the SAME rounded
        # value the guest sees on the invoice. Falls back to plain
        # balance for legacy callers that don't know about the new key.
        r._balance = billing.get('settlement_balance', billing['balance'])
        r._balance_unrounded = billing['balance']
        r._rounded_grand_total = billing.get('rounded_grand_total')

    # Occupancy from the canonical engine — NOT len(records)/Room.query.count().
    # len(records) is a reservation-row count (can exceed the room inventory
    # and yield an impossible >100%); the engine returns distinct occupied
    # rooms over the canonical sellable denominator.
    from app.occupancy_engine import occupancy_snapshot
    _occ = occupancy_snapshot()
    total_rooms = _occ['total']
    occ_pct = _occ['pct']

    if fmt == 'excel':
        headers = ['Room', 'Guest Name', 'Phone', 'Room Type', 'Check-in', 'Check-out',
                   'Nights Stayed', 'Nights Left', 'Rate/Night', 'Balance (₹)', 'Source', 'Status']
        rows = []
        for r in records:
            rows.append([
                r.room.room_number if r.room else '',
                r.guest.name if r.guest else '',
                r.guest.phone if r.guest else '',
                r.room_type.name if r.room_type else '',
                r.arrival_date.isoformat(),
                r.departure_date.isoformat(),
                r._nights_stayed,
                r._nights_remaining,
                float(r.rate_per_night),
                round(r._balance, 2),
                r.source or '',
                'OVERDUE' if r._overdue else 'In-House',
            ])
        return _excel_response(
            f'inhouse_{today.isoformat()}.xlsx', headers, rows,
            f'In-House Guest List — {today.strftime("%d %B %Y")} ({len(records)} guests)'
        )

    return render_template('reports/inhouse.html',
                           records=records, today=today,
                           occ_pct=occ_pct, total_rooms=total_rooms)


# ---------------------------------------------------------------------------
# Payment Collection Report
# ---------------------------------------------------------------------------

@reports_bp.route('/payments')
def payment_collection():
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    today = get_business_date()
    from_str = request.args.get('from', today.isoformat())
    to_str   = request.args.get('to',   today.isoformat())
    fmt      = request.args.get('format', 'html')
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = today

    payments = (
        Payment.query
        .filter(
            Payment.payment_date >= from_date,
            Payment.payment_date <= to_date,
            Payment.is_voided == False,
        )
        .order_by(Payment.payment_date, Payment.created_at)
        .all()
    )

    # Summary by mode — split direct vs OTA, and (Apr 2026) by purpose
    # so the report makes Advance ≠ Revenue explicit.
    by_mode: dict = {}
    by_mode_direct: dict = {}
    by_mode_ota: dict = {}
    by_date: dict = {}
    grand_total = 0.0
    direct_total = 0.0
    ota_total = 0.0
    advance_total = 0.0
    settlement_total = 0.0
    credit_recovery_total = 0.0
    refund_total = 0.0
    for p in payments:
        mode = p.payment_mode.name if p.payment_mode else 'Unknown'
        cat = p.payment_mode.category if p.payment_mode else 'direct_payment'
        amt = float(p.amount)
        by_mode[mode] = by_mode.get(mode, 0.0) + amt
        day_key = p.payment_date.isoformat()
        by_date[day_key] = by_date.get(day_key, 0.0) + amt
        grand_total += amt
        if cat == 'ota_receivable':
            by_mode_ota[mode] = by_mode_ota.get(mode, 0.0) + amt
            ota_total += amt
        else:
            by_mode_direct[mode] = by_mode_direct.get(mode, 0.0) + amt
            direct_total += amt
            purpose = (getattr(p, 'payment_purpose', '') or 'settlement').lower()
            if purpose == 'advance':
                advance_total += amt
            elif purpose == 'credit_recovery':
                credit_recovery_total += amt
            elif purpose == 'refund':
                refund_total += amt
            else:
                settlement_total += amt

    by_date = dict(sorted(by_date.items()))

    if fmt == 'excel':
        headers = ['Date', 'Reservation Ref', 'Guest', 'Room', 'Payment Mode',
                   'Purpose', 'Reference No.', 'Amount (₹)']
        rows = []
        for p in payments:
            res = p.reservation
            rows.append([
                p.payment_date.isoformat(),
                res.booking_reference or res.id if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                p.payment_mode.name if p.payment_mode else '',
                (getattr(p, 'payment_purpose', '') or 'settlement'),
                p.reference_number or '',
                float(p.amount),
            ])
        return _excel_response(
            f'payments_{from_str}_{to_str}.xlsx', headers, rows,
            f'Payment Collection — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'
        )

    # Forfeit income for the same date range — sourced from the cancellation
    # snapshot on Reservation. NOT room revenue; reported separately.
    forfeit_income_total = 0.0
    forfeit_count = 0
    try:
        forfeit_rows = (Reservation.query
                        .filter(Reservation.cancellation_amount_forfeited > 0,
                                Reservation.cancellation_processed_at.isnot(None))
                        .all())
        for r in forfeit_rows:
            d = r.cancellation_processed_at.date() if r.cancellation_processed_at else None
            if d is not None and from_date <= d <= to_date:
                forfeit_income_total += float(r.cancellation_amount_forfeited or 0)
                forfeit_count += 1
    except Exception:
        pass

    # Net Advance = Advance Received − Refund Issued
    # (Forfeit Income reported separately so the front desk doesn't double-count.)
    net_advance = round(advance_total - refund_total, 2)

    return render_template('reports/payments.html',
                           payments=payments, from_date=from_date, to_date=to_date,
                           by_mode=by_mode, by_date=by_date, grand_total=grand_total,
                           by_mode_direct=by_mode_direct, direct_total=direct_total,
                           by_mode_ota=by_mode_ota, ota_total=ota_total,
                           advance_total=advance_total,
                           settlement_total=settlement_total,
                           credit_recovery_total=credit_recovery_total,
                           refund_total=refund_total,
                           net_advance=net_advance,
                           forfeit_income_total=forfeit_income_total,
                           forfeit_count=forfeit_count)


# ---------------------------------------------------------------------------
# OTA Receivable Report
# ---------------------------------------------------------------------------

@reports_bp.route('/ota-receivables')
def ota_receivables():
    """OTA channel-wise outstanding and settlement report."""
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    today = get_business_date()
    from_str = request.args.get('from', today.isoformat())
    to_str   = request.args.get('to',   today.isoformat())
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = today

    from app.ota_settlement_service import (
        compute_ota_outstanding, compute_ota_settlements_today,
        get_ota_receivable_heads,
    )

    # Outstanding by channel (lifetime gross)
    _ota_raw = compute_ota_outstanding()
    # compute_ota_outstanding returns {'by_head': {name: {amount, count, code}}, 'total_amount': Decimal, ...}
    _by_head = _ota_raw.get('by_head', {}) if isinstance(_ota_raw, dict) else {}
    outstanding = {k: float(v.get('amount', 0) if isinstance(v, dict) else v) for k, v in _by_head.items()}
    outstanding_total = float(_ota_raw.get('total_amount', 0) if isinstance(_ota_raw, dict) else 0)

    # Settlements in date range
    from app.models import PaymentMode
    ota_payments = (
        Payment.query
        .join(PaymentMode, Payment.payment_mode_id == PaymentMode.id)
        .filter(
            Payment.payment_date >= from_date,
            Payment.payment_date <= to_date,
            Payment.is_voided == False,
            PaymentMode.category == 'ota_receivable',
        )
        .order_by(Payment.payment_date.desc())
        .all()
    )

    # Aggregate by head
    settled_by_head: dict = {}
    settled_total = 0.0
    for p in ota_payments:
        head = p.payment_mode.name if p.payment_mode else 'Unknown'
        settled_by_head[head] = settled_by_head.get(head, 0.0) + float(p.amount)
        settled_total += float(p.amount)

    return render_template('reports/ota_receivables.html',
                           from_date=from_date, to_date=to_date,
                           outstanding=outstanding,
                           outstanding_total=outstanding_total,
                           settled_by_head=settled_by_head,
                           settled_total=settled_total,
                           ota_payments=ota_payments,
                           ota_heads=get_ota_receivable_heads())


# ---------------------------------------------------------------------------
# OTA Payout Reconciliation (Phase 2)
# ---------------------------------------------------------------------------
# Sits ON TOP of the existing OTA receivable report — does not replace
# it. The receivable report tells the hotel what they ARE owed; this
# one tells them what has actually been PAID and what's overdue.

@reports_bp.route('/ota-reconciliation')
def ota_reconciliation():
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    today = get_business_date()
    from_str = request.args.get('from', (today - timedelta(days=30)).isoformat())
    to_str = request.args.get('to', today.isoformat())
    try:
        from_date = date.fromisoformat(from_str)
        to_date = date.fromisoformat(to_str)
    except ValueError:
        from_date = today - timedelta(days=30)
        to_date = today

    from app.ota_reconciliation import get_reconciliation_summary
    from app.ota import OTA_SOURCES
    from app.models import OTAPayout

    summary = get_reconciliation_summary(from_date, to_date, today=today)

    # Recent payouts (latest 50) for the data-entry table at the bottom
    recent_payouts = (OTAPayout.query
                      .order_by(OTAPayout.payout_date.desc(),
                                OTAPayout.id.desc())
                      .limit(50)
                      .all())

    return render_template('reports/ota_reconciliation.html',
                           from_date=from_date,
                           to_date=to_date,
                           summary=summary,
                           ota_sources=OTA_SOURCES,
                           recent_payouts=recent_payouts)


@reports_bp.route('/ota-payouts/add', methods=['POST'])
def add_ota_payout():
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.ota_reconciliation import record_payout
    from flask import flash, redirect, url_for

    try:
        payout = record_payout(
            ota_channel=request.form.get('ota_channel', '').strip(),
            payout_date=request.form.get('payout_date', '').strip(),
            gross_amount=request.form.get('gross_amount', 0),
            commission_amount=request.form.get('commission_amount', 0),
            tax_deducted=request.form.get('tax_deducted', 0),
            net_paid=(request.form.get('net_paid') or None),
            reference_number=request.form.get('reference_number', ''),
            remarks=request.form.get('remarks', ''),
            created_by_user_id=current_user.id if current_user.is_authenticated else None,
        )
        db.session.commit()
        flash(f'Payout of ₹{float(payout.net_paid):,.0f} recorded for '
              f'{payout.ota_channel}.', 'success')
    except ValueError as ve:
        db.session.rollback()
        flash(f'Could not record payout: {ve}', 'danger')
    except Exception as exc:
        db.session.rollback()
        flash(f'Unexpected error recording payout: {exc}', 'danger')

    return redirect(url_for('reports.ota_reconciliation'))


@reports_bp.route('/ota-payouts/<int:payout_id>/delete', methods=['POST'])
def delete_ota_payout(payout_id: int):
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.models import OTAPayout
    from flask import flash, redirect, url_for, abort
    payout = db.session.get(OTAPayout, payout_id)
    if not payout:
        abort(404)
    db.session.delete(payout)
    db.session.commit()
    flash('Payout deleted.', 'success')
    return redirect(url_for('reports.ota_reconciliation'))


@reports_bp.route('/api/ota-reconciliation/summary')
def api_ota_reconciliation_summary():
    if not _require_accountant():
        return jsonify({'status': 'error',
                        'error': 'Access restricted'}), 403
    from app.ota_reconciliation import get_reconciliation_summary
    today = get_business_date()
    return jsonify({
        'status': 'ok',
        'data': get_reconciliation_summary(today=today),
    })


# ---------------------------------------------------------------------------
# Front Office MIS Report
# ---------------------------------------------------------------------------

@reports_bp.route('/front-office-mis')
def front_office_mis():
    """
    Front Office MIS Report — full 10-section executive summary.
    Supports ?format=html (default), ?format=excel, ?format=json.
    Date range via ?from=YYYY-MM-DD&to=YYYY-MM-DD (defaults to today).
    Capped at 366 days to prevent timeouts.
    """
    if not _require_accountant():
        from flask import flash as _flash, redirect, url_for
        _flash('Access restricted to Accountant / Manager / Admin.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.mis_service import FrontOfficeMISService

    today    = get_business_date()
    from_str = request.args.get('from', today.isoformat())
    to_str   = request.args.get('to',   today.isoformat())
    fmt      = request.args.get('format', 'html')

    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = today

    # Sanitise
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    if (to_date - from_date).days > 365:
        to_date = from_date + timedelta(days=365)

    svc  = FrontOfficeMISService(from_date, to_date)
    data = svc.full_report()

    if fmt == 'excel':
        return _mis_excel(data, from_str, to_str)

    if fmt == 'json':
        import json
        def _ser(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            raise TypeError(type(obj))
        return Response(json.dumps(data, default=_ser), mimetype='application/json')

    return render_template(
        'reports/mis.html',
        meta      = data['meta'],
        business  = data['business'],
        movement  = data['movement'],
        sources   = data['sources'],
        rooms     = data['rooms'],
        billing   = data['billing'],
        ledger    = data['ledger'],
        discounts = data['discounts'],
        audit     = data['audit'],
        feedback  = data['feedback'],
        staff     = data['staff'],
        from_date = from_date,
        to_date   = to_date,
        today     = today,
        timedelta = timedelta,
    )


def _mis_excel(data: dict, from_str: str, to_str: str) -> Response:
    """Build a multi-sheet Excel workbook for the MIS report."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        return Response('openpyxl not installed.', status=500)

    wb = openpyxl.Workbook()
    HDR_FILL = PatternFill('solid', fgColor='1F4E79')
    HDR_FONT = Font(color='FFFFFF', bold=True)
    TTL_FONT = Font(bold=True, size=12)
    period   = f'{from_str} to {to_str}'
    gentime  = datetime.now().strftime('%d %b %Y %H:%M')

    def _sheet(name, headers, rows, title=''):
        ws = wb.create_sheet(title=name[:31])
        if title:
            ws.append([title])
            ws.cell(ws.max_row, 1).font = TTL_FONT
            ws.append([f'Period: {period}'])
            ws.append([f'Generated: {gentime}'])
            ws.append([])
        hr = ws.max_row + 1
        ws.append(headers)
        for ci in range(1, len(headers) + 1):
            c = ws.cell(hr, ci)
            c.fill = HDR_FILL
            c.font = HDR_FONT
            c.alignment = Alignment(horizontal='center')
        for row in rows:
            ws.append(row)
        for ci in range(1, len(headers) + 1):
            ml = max(
                (len(str(ws.cell(r, ci).value or '')) for r in range(1, ws.max_row + 1)),
                default=10,
            )
            ws.column_dimensions[get_column_letter(ci)].width = min(ml + 4, 40)
        return ws

    # Remove the default empty sheet
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']

    # Sheet 1 — Business Summary
    bs = data['business']
    _sheet('Business Summary', ['Metric', 'Value'], [
        ['Total Rooms',             bs['total_rooms']],
        ['Sellable Rooms',          bs['sellable_rooms']],
        ['Out of Order Rooms',      bs['oor_rooms']],
        ['Occupied (snapshot)',     bs['occupied_rooms']],
        ['Vacant (snapshot)',       bs['vacant_rooms']],
        ['Dirty (snapshot)',        bs['dirty_rooms']],
        ['Occupied Room-Nights',    bs['occ_room_nights']],
        ['Sellable Room-Nights',    bs['sellable_rn']],
        ['Occupancy %',             f"{bs['occupancy_pct']}%"],
        ['ARR (₹)',                 bs['arr']],
        ['RevPAR (₹)',              bs['revpar']],
        ['Room Revenue (₹)',        bs['room_revenue']],
        ['Other Revenue (₹)',       bs['extra_revenue']],
        ['Total Revenue (₹)',       bs['total_revenue']],
    ], 'Daily Business Summary')

    # Sheet 2 — Guest Movement
    mv = data['movement']
    _sheet('Guest Movement', ['Metric', 'Count'], [
        ['Arrivals Expected',   mv['arrivals_expected']],
        ['Arrivals Done',       mv['arrivals_done']],
        ['Departures Expected', mv['departures_expected']],
        ['Departures Done',     mv['departures_done']],
        ['In-House',            mv['inhouse']],
        ['Stayovers',           mv['stayovers']],
        ['No-Shows',            mv['no_shows']],
        ['Cancellations',       mv['cancellations']],
        ['Walk-ins',            mv['walk_ins']],
        ['Early Check-ins',     mv['early_checkins']],
        ['Late Check-outs',     mv['late_checkouts']],
    ], 'Check-in / Check-out Summary')

    # Sheet 3 — Booking Sources
    _sheet('Booking Sources',
           ['Source', 'Bookings', 'Room Nights', 'Revenue (₹)', 'ADR (₹)'],
           [[s['source'], s['bookings'], s['room_nights'], s['revenue'], s['adr']]
            for s in data['sources']],
           'Booking Source Analysis')

    # Sheet 4 — Room Status
    rm = data['rooms']
    _sheet('Room Status',
           ['Room Type', 'Total', 'Occupied', 'Vacant', 'Dirty', 'Out of Order', 'Base Rate (₹)'],
           [[k, v['total'], v['occupied'], v['vacant'], v['dirty'], v['oor'], v['base_rate']]
            for k, v in rm['by_type'].items()],
           'Room Status Report')

    # Sheet 5 — Cash & Billing
    bl = data['billing']
    billing_rows = [[m, a] for m, a in bl['by_mode'].items()]
    billing_rows += [
        ['', ''],
        ['Total Collected (₹)',     bl['total_collected']],
        ['Total Billed (₹)',        bl['total_billed']],
        ['Deposits Received (₹)',   bl['deposits']],
        ['Refunds Issued (₹)',      bl['refunds']],
        ['Pending Amount (₹)',      bl['pending_amount']],
        ['Collection Efficiency %', f"{bl['collection_eff']}%"],
    ]
    _sheet('Cash & Billing', ['Category / Mode', 'Amount (₹)'], billing_rows,
           'Cash and Billing Summary')

    # Sheet 6 — Guest Ledger
    ld = data['ledger']
    ledger_rows = []
    for e in ld['inhouse']:
        ledger_rows.append([e['guest'], e['phone'], e['room'],
                             str(e['checkin']), str(e['checkout']),
                             e['total'], e['paid'], e['balance'], 'In-House'])
    for e in ld['checkout']:
        ledger_rows.append([e['guest'], e['phone'], e['room'],
                             str(e['checkin']), str(e['checkout']),
                             e['total'], e['paid'], e['balance'], 'Checked Out'])
    _sheet('Guest Ledger',
           ['Guest', 'Phone', 'Room', 'Check-in', 'Check-out',
            'Total (₹)', 'Paid (₹)', 'Balance (₹)', 'Status'],
           ledger_rows, 'Guest Ledger & Outstanding')

    # Sheet 7 — Discounts
    disc = data['discounts']
    _sheet('Discounts',
           ['Res. ID', 'Guest', 'Room', 'Type', 'Rack Rate', 'Sold At',
            'Disc %', 'Nights', 'Disc Amt (₹)', 'Source'],
           [[r['reservation_id'], r['guest'], r['room'], r['room_type'],
             r['rack_rate'], r['sold_at'], f"{r['disc_pct']}%",
             r['nights'], r['disc_amt'], r['source']]
            for r in disc['rows']],
           'Discounts & Rate Variance')

    # Sheet 8 — Night Audit
    aud = data['audit']
    audit_rows = [[str(l.audit_date), float(l.total_revenue),
                   l.occupancy_count, l.pending_checkouts, l.notes or '']
                  for l in aud['logs']]
    audit_rows += [
        ['', '', '', '', ''],
        ['Audit Revenue Total (₹)',  aud['audit_revenue'],  '', '', ''],
        ['System Revenue Total (₹)', aud['system_revenue'], '', '', ''],
        ['Variance (₹)',             aud['variance'],        '', '', ''],
        ['Unclosed Folios',          aud['unclosed_folios'], '', '', ''],
        ['Dates Audited',            aud['dates_audited'],   '', '', ''],
        ['Dates Missing Audit',      aud['dates_missing'],   '', '', ''],
    ]
    _sheet('Night Audit',
           ['Audit Date', 'Revenue (₹)', 'Occupancy', 'Pending CO', 'Notes'],
           audit_rows, 'Night Audit / Revenue Reconciliation')

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        download_name=f'mis_{from_str}_{to_str}.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ===========================================================================
# Room Status Report
# ===========================================================================

@reports_bp.route('/room-status')
def room_status_report():
    rooms = (Room.query
             .options(
                 db.joinedload(Room.room_type),
             )
             .order_by(Room.floor, Room.room_number)
             .all())

    biz_date = get_business_date()
    # Map room_id → active reservation
    active = (Reservation.query
              .filter(Reservation.status == 'CheckedIn')
              .all())
    res_by_room = {r.room_id: r for r in active if r.room_id}

    by_status = {}
    for r in rooms:
        by_status.setdefault(r.status, []).append(r)

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = [[r.room_number, r.floor or '', r.room_type.name if r.room_type else '',
                 r.status,
                 res_by_room[r.id].guest.name if r.id in res_by_room and res_by_room[r.id].guest else '']
                for r in rooms]
        return _excel_response(f'room_status_{biz_date}.xlsx',
                               ['Room', 'Floor', 'Type', 'Status', 'Guest'],
                               rows, f'Room Status — {biz_date.strftime("%d %b %Y")}')

    return render_template('reports/room_status.html',
                           rooms=rooms, by_status=by_status,
                           res_by_room=res_by_room, report_date=biz_date)


# ===========================================================================
# Walk-in Report
# ===========================================================================

@reports_bp.route('/walkin')
def walkin_report():
    date_str = request.args.get('date', get_business_date().isoformat())
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = get_business_date()

    records = (Reservation.query
               .join(Guest)
               .filter(Reservation.source == 'Walk-in',
                       Reservation.arrival_date == report_date)
               .order_by(Reservation.created_at.desc())
               .all())

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = [[r.booking_reference,
                 r.guest.name if r.guest else '',
                 r.guest.phone if r.guest else '',
                 r.room.room_number if r.room else '',
                 r.room_type.name if r.room_type else '',
                 str(r.arrival_date), str(r.departure_date),
                 float(r.rate_per_night), r.status]
                for r in records]
        return _excel_response(f'walkin_{report_date}.xlsx',
                               ['Booking Ref', 'Guest', 'Phone', 'Room', 'Type',
                                'Arrival', 'Departure', 'Rate/Night', 'Status'],
                               rows, f'Walk-in Report — {report_date.strftime("%d %b %Y")}')

    return render_template('reports/walkin_report.html',
                           records=records, report_date=report_date)


# ===========================================================================
# Cancellation Report
# ===========================================================================

@reports_bp.route('/cancellations')
def cancellation_report():
    from_str = request.args.get('from', get_business_date().replace(day=1).isoformat())
    to_str   = request.args.get('to',   get_business_date().isoformat())
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = get_business_date()

    records = (Reservation.query
               .filter(Reservation.status == 'Cancelled',
                       Reservation.arrival_date >= from_date,
                       Reservation.arrival_date <= to_date)
               .order_by(Reservation.arrival_date.desc())
               .all())

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = [[r.booking_reference,
                 r.guest.name if r.guest else '',
                 str(r.arrival_date), str(r.departure_date),
                 r.source or '', r.room_type.name if r.room_type else '',
                 float(r.rate_per_night)]
                for r in records]
        return _excel_response(f'cancellations_{from_str}_{to_str}.xlsx',
                               ['Booking Ref', 'Guest', 'Arrival', 'Departure',
                                'Source', 'Room Type', 'Rate/Night'],
                               rows, f'Cancellations {from_str} to {to_str}')

    return render_template('reports/cancellation_report.html',
                           records=records, from_date=from_date, to_date=to_date)


# ===========================================================================
# Reservation by Source Report
# ===========================================================================

@reports_bp.route('/source-analysis')
def source_analysis_report():
    from_str = request.args.get('from', get_business_date().replace(day=1).isoformat())
    to_str   = request.args.get('to',   get_business_date().isoformat())
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = get_business_date()

    rows_q = (db.session.query(
                  Reservation.source,
                  func.count(Reservation.id).label('count'),
                  func.sum(Reservation.rate_per_night).label('total_rate'))
              .filter(Reservation.arrival_date >= from_date,
                      Reservation.arrival_date <= to_date,
                      Reservation.status.notin_(['Cancelled']))
              .group_by(Reservation.source)
              .order_by(func.count(Reservation.id).desc())
              .all())

    detail = (Reservation.query
              .filter(Reservation.arrival_date >= from_date,
                      Reservation.arrival_date <= to_date,
                      Reservation.status.notin_(['Cancelled']))
              .order_by(Reservation.source, Reservation.arrival_date)
              .all())

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        xrows = [[r.source or 'Unknown', r.count, round(float(r.total_rate or 0), 2)]
                 for r in rows_q]
        return _excel_response(f'source_analysis_{from_str}_{to_str}.xlsx',
                               ['Source', 'Bookings', 'Total Rate'],
                               xrows, f'Source Analysis {from_str} to {to_str}')

    return render_template('reports/source_analysis.html',
                           summary=rows_q, detail=detail,
                           from_date=from_date, to_date=to_date)


# ===========================================================================
# Future Bookings Report
# ===========================================================================

@reports_bp.route('/future-bookings')
def future_bookings_report():
    from_date = get_business_date()
    to_str = request.args.get('to', (from_date + timedelta(days=30)).isoformat())
    try:
        to_date = date.fromisoformat(to_str)
    except ValueError:
        to_date = from_date + timedelta(days=30)

    records = (Reservation.query
               .filter(Reservation.arrival_date > from_date,
                       Reservation.arrival_date <= to_date,
                       Reservation.status.in_(['Reserved', 'Confirmed']))
               .order_by(Reservation.arrival_date)
               .all())

    # Daily count for mini-chart
    daily: dict = {}
    for r in records:
        k = r.arrival_date.isoformat()
        daily[k] = daily.get(k, 0) + 1

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = [[r.booking_reference,
                 r.guest.name if r.guest else '',
                 r.guest.phone if r.guest else '',
                 str(r.arrival_date), str(r.departure_date),
                 r.source or '', r.room_type.name if r.room_type else '',
                 float(r.rate_per_night), r.status]
                for r in records]
        return _excel_response(f'future_bookings_{to_str}.xlsx',
                               ['Booking Ref', 'Guest', 'Phone', 'Arrival', 'Departure',
                                'Source', 'Room Type', 'Rate/Night', 'Status'],
                               rows, f'Future Bookings — up to {to_date.strftime("%d %b %Y")}')

    return render_template('reports/future_bookings.html',
                           records=records, from_date=from_date,
                           to_date=to_date, daily=daily)


# ===========================================================================
# Company / Direct Billing Report
# ===========================================================================

@reports_bp.route('/company-billing')
def company_billing_report():
    if not _require_accountant():
        from flask import abort; abort(403)

    companies = (Company.query
                 .filter_by(is_active=True)
                 .order_by(Company.name)
                 .all())

    # For each company, find CheckInRecords billed to it
    company_id_filter = request.args.get('company_id', type=int)
    from_str = request.args.get('from', get_business_date().replace(day=1).isoformat())
    to_str   = request.args.get('to',   get_business_date().isoformat())
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = get_business_date()

    q = (CheckInRecord.query
         .filter(CheckInRecord.billing_responsibility == 'Company',
                 CheckInRecord.checkin_date >= from_date,
                 CheckInRecord.checkin_date <= to_date))
    if company_id_filter:
        q = q.filter(CheckInRecord.company_id == company_id_filter)
    checkins = q.order_by(CheckInRecord.checkin_date.desc()).all()

    # Enrich with stay amounts. Report displays the rounded settlement
    # balance so it ties out to the guest invoice; raw balance is kept
    # alongside for analytics callers (none today, future-proof).
    rows = []
    for ci in checkins:
        if ci.reservation:
            amt = calculate_stay_amount(ci.reservation)
            rows.append({'checkin': ci, 'reservation': ci.reservation,
                         'total': amt['total'], 'paid': amt['paid'],
                         'balance':            amt.get('settlement_balance', amt['balance']),
                         'balance_unrounded':  amt['balance'],
                         'rounded_grand_total': amt.get('rounded_grand_total')})

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        xrows = [[r['reservation'].booking_reference,
                  r['reservation'].guest.name if r['reservation'].guest else '',
                  r['checkin'].company.name if r['checkin'].company else '',
                  str(r['checkin'].checkin_date),
                  round(r['total'], 2), round(r['paid'], 2), round(r['balance'], 2)]
                 for r in rows]
        return _excel_response(f'company_billing_{from_str}_{to_str}.xlsx',
                               ['Booking Ref', 'Guest', 'Company', 'Check-in',
                                'Total', 'Paid', 'Balance'],
                               xrows, f'Company Billing {from_str} to {to_str}')

    return render_template('reports/company_billing.html',
                           rows=rows, companies=companies,
                           company_id_filter=company_id_filter,
                           from_date=from_date, to_date=to_date)


# ===========================================================================
# Housekeeping Status Report
# ===========================================================================

@reports_bp.route('/housekeeping')
def housekeeping_report():
    rooms = (Room.query
             .options(db.joinedload(Room.room_type))
             .order_by(Room.floor, Room.room_number)
             .all())

    biz_date = get_business_date()
    # Map room_id → reservation (CheckedIn or expected checkout today)
    active = (Reservation.query
              .filter(Reservation.status.in_(['CheckedIn']))
              .all())
    checkouts_today = (Reservation.query
                       .filter(Reservation.departure_date == biz_date,
                               Reservation.status == 'CheckedIn')
                       .all())
    arrivals_today = (Reservation.query
                      .filter(Reservation.arrival_date == biz_date,
                              Reservation.status.in_(['Reserved', 'Confirmed']))
                      .all())

    res_by_room = {r.room_id: r for r in active if r.room_id}
    checkout_rooms = {r.room_id for r in checkouts_today if r.room_id}
    arrival_rooms  = {r.room_id for r in arrivals_today if r.room_id}

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = []
        for r in rooms:
            priority = 'Checkout Due' if r.id in checkout_rooms else (
                       'Arrival Due' if r.id in arrival_rooms else '')
            rows.append([r.room_number, r.floor or '', r.room_type.name if r.room_type else '',
                         r.status, priority,
                         res_by_room[r.id].guest.name if r.id in res_by_room and res_by_room[r.id].guest else ''])
        return _excel_response(f'housekeeping_{biz_date}.xlsx',
                               ['Room', 'Floor', 'Type', 'Status', 'Priority', 'Guest'],
                               rows, f'Housekeeping — {biz_date.strftime("%d %b %Y")}')

    return render_template('reports/housekeeping_report.html',
                           rooms=rooms, res_by_room=res_by_room,
                           checkout_rooms=checkout_rooms, arrival_rooms=arrival_rooms,
                           report_date=biz_date)


# ===========================================================================
# Maintenance / Work Order Report
# ===========================================================================

@reports_bp.route('/maintenance')
def maintenance_report():
    status_filter = request.args.get('status', '')
    records = MaintenanceRequest.query
    if status_filter:
        records = records.filter_by(status=status_filter)
    records = (records
               .options(db.joinedload(MaintenanceRequest.room))
               .order_by(MaintenanceRequest.created_at.desc())
               .all())

    by_status = {}
    for r in records:
        by_status.setdefault(r.status, []).append(r)

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = [[r.room.room_number if r.room else '',
                 r.category, r.description or '', r.priority,
                 r.status, r.reported_by or '', r.assigned_to or '',
                 str(r.created_at.date())]
                for r in records]
        return _excel_response('maintenance_report.xlsx',
                               ['Room', 'Category', 'Description', 'Priority',
                                'Status', 'Reported By', 'Assigned To', 'Date'],
                               rows, 'Maintenance Work Order Report')

    return render_template('reports/maintenance_report.html',
                           records=records, by_status=by_status,
                           status_filter=status_filter)


# ===========================================================================
# Pending Payments (Outstanding Balances) Report
# ===========================================================================

@reports_bp.route('/pending-payments')
def pending_payments_report():
    if not _require_accountant():
        from flask import abort; abort(403)

    status_filter = request.args.get('status', 'all')  # all / inhouse / checkout

    q = Reservation.query.filter(
        Reservation.status.in_(['CheckedIn', 'CheckedOut'])
    )
    if status_filter == 'inhouse':
        q = q.filter(Reservation.status == 'CheckedIn')
    elif status_filter == 'checkout':
        q = q.filter(Reservation.status == 'CheckedOut')

    reservations = q.order_by(Reservation.departure_date).all()

    rows = []
    total_outstanding = 0.0
    for r in reservations:
        amt = calculate_stay_amount(r)
        # Use the rounded settlement balance — matches the guest invoice.
        _bal = amt.get('settlement_balance', amt['balance'])
        if _bal > 0.01:
            rows.append({'reservation': r, 'total': amt['total'],
                         'paid': amt['paid'], 'balance': _bal,
                         'balance_unrounded': amt['balance']})
            total_outstanding += _bal

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        xrows = [[r['reservation'].booking_reference,
                  r['reservation'].guest.name if r['reservation'].guest else '',
                  r['reservation'].room.room_number if r['reservation'].room else '',
                  str(r['reservation'].departure_date),
                  r['reservation'].status,
                  round(r['total'], 2), round(r['paid'], 2), round(r['balance'], 2)]
                 for r in rows]
        return _excel_response('pending_payments.xlsx',
                               ['Booking Ref', 'Guest', 'Room', 'Departure',
                                'Status', 'Total', 'Paid', 'Outstanding'],
                               xrows, 'Pending Payments / Outstanding Balances')

    return render_template('reports/pending_payments.html',
                           rows=rows, total_outstanding=total_outstanding,
                           status_filter=status_filter)


# ===========================================================================
# Guest Report
# ===========================================================================

@reports_bp.route('/guest-report')
def guest_report():
    from sqlalchemy import text as sa_text

    today = get_business_date()
    default_from = today.replace(day=1).isoformat()
    default_to   = today.isoformat()

    from_str     = request.args.get('from', default_from)
    to_str       = request.args.get('to',   default_to)
    rt_filter    = request.args.get('room_type', '')
    src_filter   = request.args.get('source', '')
    mode_filter  = request.args.get('payment_mode', '')
    status_filter= request.args.get('status', '')
    fmt          = request.args.get('format', 'html')

    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = today.replace(day=1)
        to_date   = today

    # Build dynamic WHERE clause from a CLOSED allowlist of literal fragments.
    # User input is bound exclusively through named parameters (:name) — no
    # filter value ever flows into the SQL string. Fragments are selected
    # into `where_parts` by the presence of a filter, never constructed from
    # request data, which makes SQL injection structurally impossible here.
    _WHERE_FRAGMENTS = {
        'base_from':    "r.arrival_date >= :from_date",
        'base_to':      "r.arrival_date <= :to_date",
        'base_status':  "r.status NOT IN ('Blocked')",
        'room_type':    "rt.name = :rt_name",
        'source':       "COALESCE(NULLIF(r.source,''), 'Walk-in') = :src",
        'status':       "r.status = :status",
    }
    where_keys = ['base_from', 'base_to', 'base_status']
    params: dict = {'from_date': from_date, 'to_date': to_date}

    if rt_filter:
        where_keys.append('room_type')
        params['rt_name'] = rt_filter
    if src_filter:
        where_keys.append('source')
        params['src'] = src_filter
    if status_filter:
        where_keys.append('status')
        params['status'] = status_filter

    where_sql = ' AND '.join(_WHERE_FRAGMENTS[k] for k in where_keys)

    # v2.2.12 Q5=c correction: each CTE narrows to the report's date window
    # on its respective date column. Pre-v2.2.12 these CTEs aggregated ALL
    # payments/extras/tax for matched reservations regardless of when they
    # were posted — a reservation arriving in window with payment posted
    # outside the window showed the outside payment in this report, which
    # breaks cash-basis alignment with the rest of the v2.2.11 reconciliation
    # surfaces. Each CTE now filters by:
    #   pay_agg: payments.payment_date BETWEEN :from_date AND :to_date
    #   ext_agg: extra_charges.charge_date BETWEEN :from_date AND :to_date
    #   tax_agg: tax_lines.charge_date BETWEEN :from_date AND :to_date
    # The outer SELECT continues to filter reservations by r.arrival_date.
    #
    # v2.2.12a SQLite-compat hotfix: replaced PostgreSQL-only constructs.
    #   ILIKE / NOT ILIKE   -> LOWER(col) LIKE / NOT LIKE
    #   ~* / !~* regex      -> OR-chains of LOWER(col) LIKE
    #   LPAD(::TEXT)        -> printf('%04d', g.id)
    #   0::numeric          -> 0
    #   false               -> 0
    #   (date - date)       -> CAST(julianday(d2) - julianday(d1) AS INTEGER)
    # Semantic preservation: the date-window narrowing introduced in v2.2.12
    # is unaffected (the WHERE clauses on each CTE were already standard SQL).
    sql = sa_text(f"""
        WITH pay_agg AS (
            SELECT p.reservation_id,
                SUM(CASE WHEN LOWER(pm.name) LIKE '%cash%' THEN p.amount ELSE 0 END)    AS cash,
                SUM(CASE WHEN LOWER(pm.name) LIKE '%card%' OR LOWER(pm.name) LIKE '%debit%'
                                                       THEN p.amount ELSE 0 END)        AS card,
                SUM(CASE WHEN LOWER(pm.name) LIKE '%upi%'   OR LOWER(pm.name) LIKE '%gpay%'
                          OR LOWER(pm.name) LIKE '%phone%'  OR LOWER(pm.name) LIKE '%paytm%'
                                                       THEN p.amount ELSE 0 END)        AS upi,
                SUM(CASE WHEN LOWER(pm.name) LIKE '%bank%'  OR LOWER(pm.name) LIKE '%neft%'
                          OR LOWER(pm.name) LIKE '%rtgs%'   OR LOWER(pm.name) LIKE '%imps%'
                                                       THEN p.amount ELSE 0 END)        AS bank_transfer,
                SUM(CASE WHEN LOWER(pm.name) LIKE '%credit%' AND LOWER(pm.name) NOT LIKE '%card%'
                                                       THEN p.amount ELSE 0 END)        AS hotel_credit,
                SUM(p.amount) AS total_paid
            FROM payments p
            JOIN payment_modes pm ON pm.id = p.payment_mode_id
            WHERE p.is_voided = 0
              AND p.payment_date >= :from_date
              AND p.payment_date <= :to_date
            GROUP BY p.reservation_id
        ),
        ext_agg AS (
            SELECT reservation_id,
                SUM(CASE WHEN (LOWER(description) LIKE '%f&b%'
                            OR LOWER(description) LIKE '%food%'
                            OR LOWER(description) LIKE '%restaur%'
                            OR LOWER(description) LIKE '%beverage%'
                            OR LOWER(description) LIKE '%meal%'
                            OR LOWER(description) LIKE '%dining%'
                            OR LOWER(description) LIKE '%bar%'
                            OR LOWER(description) LIKE '%breakfast%'
                            OR LOWER(description) LIKE '%lunch%'
                            OR LOWER(description) LIKE '%dinner%'
                            OR LOWER(description) LIKE '%snack%'
                            OR LOWER(description) LIKE '%drink%')
                          THEN amount ELSE 0 END)                                       AS fnb,
                SUM(CASE WHEN (LOWER(description) LIKE '%laundry%'
                            OR LOWER(description) LIKE '%washing%'
                            OR LOWER(description) LIKE '%ironing%'
                            OR LOWER(description) LIKE '%dryclean%'
                            OR LOWER(description) LIKE '%dry clean%'
                            OR LOWER(description) LIKE '%dry-clean%')
                          THEN amount ELSE 0 END)                                       AS laundry,
                SUM(CASE WHEN NOT (LOWER(description) LIKE '%f&b%'
                                OR LOWER(description) LIKE '%food%'
                                OR LOWER(description) LIKE '%restaur%'
                                OR LOWER(description) LIKE '%beverage%'
                                OR LOWER(description) LIKE '%meal%'
                                OR LOWER(description) LIKE '%dining%'
                                OR LOWER(description) LIKE '%bar%'
                                OR LOWER(description) LIKE '%breakfast%'
                                OR LOWER(description) LIKE '%lunch%'
                                OR LOWER(description) LIKE '%dinner%'
                                OR LOWER(description) LIKE '%snack%'
                                OR LOWER(description) LIKE '%drink%'
                                OR LOWER(description) LIKE '%laundry%'
                                OR LOWER(description) LIKE '%washing%'
                                OR LOWER(description) LIKE '%ironing%'
                                OR LOWER(description) LIKE '%dryclean%'
                                OR LOWER(description) LIKE '%dry clean%'
                                OR LOWER(description) LIKE '%dry-clean%')
                          THEN amount ELSE 0 END)                                       AS other_charges,
                SUM(amount) AS total_extra
            FROM extra_charges
            WHERE charge_date >= :from_date
              AND charge_date <= :to_date
            GROUP BY reservation_id
        ),
        tax_agg AS (
            SELECT reservation_id,
                SUM(tax_amount) AS total_tax
            FROM tax_lines
            WHERE charge_date >= :from_date
              AND charge_date <= :to_date
            GROUP BY reservation_id
        )
        SELECT
            r.id,
            'F' || printf('%04d', g.id)                          AS folio_no,
            g.name                                               AS guest_name,
            g.phone                                              AS mobile,
            g.id_proof_type                                      AS id_type,
            g.id_proof_number                                    AS id_no,
            g.city,
            r.arrival_date,
            r.departure_date,
            CAST(julianday(r.departure_date) - julianday(r.arrival_date) AS INTEGER) AS nights,
            rm.room_number,
            rt.name                                              AS room_type,
            (r.adults + r.children)                              AS pax,
            COALESCE(NULLIF(r.source,''), 'Walk-in')             AS source,
            r.status,
            (r.rate_per_night *
             CAST(julianday(r.departure_date) - julianday(r.arrival_date) AS INTEGER)) AS room_charges,
            COALESCE(ex.fnb,        0)                           AS fnb,
            COALESCE(ex.laundry,    0)                           AS laundry,
            COALESCE(ex.other_charges, 0)                        AS other_charges,
            COALESCE(ex.total_extra,0)                           AS extra_charges,
            0                                                    AS discount,
            COALESCE(tx.total_tax,  0)                           AS tax,
            (r.rate_per_night *
             CAST(julianday(r.departure_date) - julianday(r.arrival_date) AS INTEGER)
             + COALESCE(ex.total_extra, 0)
             + COALESCE(tx.total_tax,   0))                      AS total_bill,
            COALESCE(pa.total_paid, 0)                           AS paid_amount,
            (r.rate_per_night *
             CAST(julianday(r.departure_date) - julianday(r.arrival_date) AS INTEGER)
             + COALESCE(ex.total_extra, 0)
             + COALESCE(tx.total_tax,   0)
             - COALESCE(pa.total_paid,  0))                      AS balance,
            COALESCE(pa.cash,         0)                         AS cash,
            COALESCE(pa.card,         0)                         AS card,
            COALESCE(pa.upi,          0)                         AS upi,
            COALESCE(pa.bank_transfer,0)                         AS bank_transfer,
            COALESCE(pa.hotel_credit, 0)                         AS hotel_credit
        FROM reservations r
        JOIN guests g ON g.id = r.guest_id
        LEFT JOIN rooms rm ON rm.id = r.room_id
        LEFT JOIN room_types rt ON rt.id = r.room_type_id
        LEFT JOIN pay_agg pa ON pa.reservation_id = r.id
        LEFT JOIN ext_agg ex ON ex.reservation_id = r.id
        LEFT JOIN tax_agg tx ON tx.reservation_id = r.id
        WHERE {where_sql}
        ORDER BY r.arrival_date DESC, r.id DESC
    """)

    rows_raw = db.session.execute(sql, params).fetchall()

    # payment_mode filter is applied in Python (needs aggregated pay data)
    if mode_filter:
        mode_lower = mode_filter.lower()
        def _matches_mode(row):
            m = mode_lower
            if m == 'cash':         return float(row.cash or 0) > 0
            if m == 'card':         return float(row.card or 0) > 0
            if m == 'upi':          return float(row.upi  or 0) > 0
            if m == 'bank_transfer':return float(row.bank_transfer or 0) > 0
            if m == 'hotel_credit': return float(row.hotel_credit  or 0) > 0
            return True
        rows_raw = [r for r in rows_raw if _matches_mode(r)]

    # Summary aggregates
    total_guests  = len(rows_raw)
    total_revenue = sum(float(r.total_bill   or 0) for r in rows_raw)
    total_tax     = sum(float(r.tax          or 0) for r in rows_raw)
    total_paid    = sum(float(r.paid_amount  or 0) for r in rows_raw)
    total_balance = sum(float(r.balance      or 0) for r in rows_raw)
    pay_cash      = sum(float(r.cash         or 0) for r in rows_raw)
    pay_card      = sum(float(r.card         or 0) for r in rows_raw)
    pay_upi       = sum(float(r.upi          or 0) for r in rows_raw)
    pay_bank      = sum(float(r.bank_transfer or 0) for r in rows_raw)
    pay_credit    = sum(float(r.hotel_credit  or 0) for r in rows_raw)

    # Room types + sources for filter dropdowns
    room_types = db.session.execute(
        sa_text("SELECT DISTINCT name FROM room_types ORDER BY name")
    ).fetchall()
    sources = db.session.execute(
        sa_text("SELECT DISTINCT COALESCE(NULLIF(source,''),'Walk-in') AS src FROM reservations ORDER BY 1")
    ).fetchall()

    if fmt in ('excel', 'pdf'):
        from app.models import Settings as _Sett
        def _setting(key, default=''):
            s = _Sett.query.filter_by(key=key).first()
            return s.value if s else default
        hotel_name    = _setting('hotel_name',    'Hotel')
        hotel_address = _setting('hotel_address', '')
        generated_at  = datetime.now().strftime('%d %b %Y  %H:%M')

    if fmt == 'pdf':
        return render_template(
            'reports/guest_report_print.html',
            rows=rows_raw,
            from_date=from_date, to_date=to_date,
            hotel_name=hotel_name, hotel_address=hotel_address,
            generated_at=generated_at,
            total_guests=total_guests, total_revenue=total_revenue,
            total_tax=total_tax, total_paid=total_paid, total_balance=total_balance,
            pay_cash=pay_cash, pay_card=pay_card, pay_upi=pay_upi,
            pay_bank=pay_bank, pay_credit=pay_credit,
        )

    if fmt == 'excel':
        try:
            import openpyxl
            from openpyxl.styles import (Font, PatternFill, Alignment,
                                         Border, Side, numbers)
            from openpyxl.utils import get_column_letter
            from openpyxl.worksheet.page import PageMargins
        except ImportError:
            from flask import Response as _R
            return _R('openpyxl not installed.', status=500)

        COL_HEADERS = [
            'Folio No', 'Guest Name', 'Mobile',
            'Check-in', 'Check-out', 'Room No', 'Room Type',
            'Nights', 'Pax', 'Source',
            'Total Bill (₹)', 'Paid (₹)', 'Balance (₹)',
            'Payment Mode', 'Status',
        ]
        NUM_COLS = len(COL_HEADERS)
        last_col = get_column_letter(NUM_COLS)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Guest Report'

        # ── Page setup: A4 portrait, fit to 1 page wide, narrow margins ──────
        ws.page_setup.paperSize   = ws.PAPERSIZE_A4
        ws.page_setup.orientation = 'portrait'
        ws.page_setup.fitToPage   = True
        ws.page_setup.fitToWidth  = 1
        ws.page_setup.fitToHeight = 0          # unlimited height pages
        ws.page_margins = PageMargins(
            left=0.4, right=0.4, top=0.6, bottom=0.6,
            header=0.3, footer=0.3
        )
        ws.print_title_rows = None

        # ── Print header / footer ──────────────────────────────────────────
        ws.oddHeader.center.text = f'&B&14{hotel_name}&B'
        ws.oddFooter.left.text   = 'Prepared by: ___________________'
        ws.oddFooter.center.text = 'Verified by: ___________________'
        ws.oddFooter.right.text  = 'Page &P of &N'

        # ── Style helpers ──────────────────────────────────────────────────
        def _fill(hex_color):
            return PatternFill('solid', fgColor=hex_color)

        def _font(bold=False, size=10, color='000000', italic=False):
            return Font(bold=bold, size=size, color=color, italic=italic)

        def _align(h='left', v='center', wrap=False):
            return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

        def _border():
            thin = Side(style='thin', color='CCCCCC')
            return Border(left=thin, right=thin, top=thin, bottom=thin)

        def _currency_fmt():
            return '₹#,##0'

        # ── Row helpers ────────────────────────────────────────────────────
        def _add_row(values, fill=None, font=None, alignment=None,
                     border=False, height=None):
            ws.append(values)
            row_n = ws.max_row
            if height:
                ws.row_dimensions[row_n].height = height
            for col_i in range(1, len(values) + 1):
                cell = ws.cell(row_n, col_i)
                if fill:      cell.fill      = fill
                if font:      cell.font      = font
                if alignment: cell.alignment = alignment
                if border:    cell.border    = _border()
            return row_n

        def _merge_full(row_n, value, fill=None, font=None, alignment=None):
            ws.merge_cells(f'A{row_n}:{last_col}{row_n}')
            cell = ws.cell(row_n, 1)
            cell.value = value
            if fill:      cell.fill      = fill
            if font:      cell.font      = font
            if alignment: cell.alignment = alignment

        # ════════════════════════════════════════════════════════════════
        # SECTION 1 — Document header
        # ════════════════════════════════════════════════════════════════
        ws.append([''] * NUM_COLS)                       # row 1 spacer
        _merge_full(1, hotel_name,
                    font=_font(bold=True, size=16),
                    alignment=_align('center'))
        ws.row_dimensions[1].height = 26

        ws.append([''] * NUM_COLS)                       # row 2 address
        _merge_full(2, hotel_address,
                    font=_font(size=10, color='555555', italic=True),
                    alignment=_align('center'))
        ws.row_dimensions[2].height = 16

        ws.append([''] * NUM_COLS)                       # row 3 spacer

        ws.append([''] * NUM_COLS)                       # row 4 title
        _merge_full(4, 'GUEST REPORT',
                    fill=_fill('1F4E79'),
                    font=_font(bold=True, size=14, color='FFFFFF'),
                    alignment=_align('center'))
        ws.row_dimensions[4].height = 22

        ws.append([''] * NUM_COLS)                       # row 5 period
        period_txt = (f'Period: {from_date.strftime("%d %b %Y")} — '
                      f'{to_date.strftime("%d %b %Y")}   |   '
                      f'Generated: {generated_at}')
        _merge_full(5, period_txt,
                    font=_font(size=9, italic=True, color='444444'),
                    alignment=_align('center'))
        ws.row_dimensions[5].height = 14

        ws.append([''] * NUM_COLS)                       # row 6 spacer

        # ════════════════════════════════════════════════════════════════
        # SECTION 2 — Summary block
        # ════════════════════════════════════════════════════════════════
        summary_fill = _fill('EFF6FF')
        summary_lbl  = _font(bold=True, size=9,  color='1E3A5F')
        summary_val  = _font(bold=True, size=10, color='1E3A5F')

        ws.append([''] * NUM_COLS)                       # row 7 section heading
        _merge_full(7, '  SUMMARY',
                    fill=_fill('DBEAFE'),
                    font=_font(bold=True, size=10, color='1E3A5F'),
                    alignment=_align('left'))
        ws.row_dimensions[7].height = 16

        # Two-column summary rows
        def _summary_pair(label1, val1, label2='', val2=''):
            row = [''] * NUM_COLS
            row[0] = label1
            row[1] = val1
            if label2: row[3] = label2
            if val2:   row[4] = val2
            rn = _add_row(row, fill=summary_fill, height=14)
            ws.cell(rn, 1).font = summary_lbl
            ws.cell(rn, 2).font = summary_val
            if label2:
                ws.cell(rn, 4).font = summary_lbl
                ws.cell(rn, 5).font = summary_val

        _summary_pair('Total Guests',   total_guests,
                      'Total Revenue',  f'₹{total_revenue:,.0f}')
        _summary_pair('Total Tax',      f'₹{total_tax:,.0f}',
                      'Total Discount', '₹0')
        _summary_pair('Amount Paid',    f'₹{total_paid:,.0f}',
                      'Balance Due',    f'₹{total_balance:,.0f}')

        ws.append([''] * NUM_COLS)                       # spacer
        _merge_full(ws.max_row, '  PAYMENT BREAKDOWN',
                    fill=_fill('DBEAFE'),
                    font=_font(bold=True, size=10, color='1E3A5F'),
                    alignment=_align('left'))
        ws.row_dimensions[ws.max_row].height = 16

        _summary_pair('Cash',        f'₹{pay_cash:,.0f}',
                      'Card',        f'₹{pay_card:,.0f}')
        _summary_pair('UPI',         f'₹{pay_upi:,.0f}',
                      'Bank Transfer', f'₹{pay_bank:,.0f}')
        _summary_pair('Hotel Credit', f'₹{pay_credit:,.0f}')

        ws.append([''] * NUM_COLS)                       # spacer

        # ════════════════════════════════════════════════════════════════
        # SECTION 3 — Column headers
        # ════════════════════════════════════════════════════════════════
        hdr_row = _add_row(
            COL_HEADERS,
            fill=_fill('374151'),
            font=_font(bold=True, size=9, color='FFFFFF'),
            alignment=_align('center', wrap=True),
            border=True,
            height=28,
        )
        # Enable auto-filter on header row
        ws.auto_filter.ref = f'A{hdr_row}:{last_col}{hdr_row}'

        # ════════════════════════════════════════════════════════════════
        # SECTION 4 — Data rows
        # ════════════════════════════════════════════════════════════════
        ROW_FILL_ODD  = _fill('F9FAFB')
        ROW_FILL_EVEN = _fill('FFFFFF')
        BAL_RED_FILL  = _fill('FEE2E2')
        BAL_RED_FONT  = _font(size=9, color='991B1B', bold=True)
        BAL_GRN_FILL  = _fill('D1FAE5')
        BAL_GRN_FONT  = _font(size=9, color='065F46', bold=True)

        for idx, r in enumerate(rows_raw, start=1):
            bal     = float(r.balance or 0)
            row_fill = ROW_FILL_ODD if idx % 2 else ROW_FILL_EVEN

            # Build payment-mode summary string
            modes = []
            if float(r.cash         or 0) > 0: modes.append(f'Cash ₹{float(r.cash):,.0f}')
            if float(r.card         or 0) > 0: modes.append(f'Card ₹{float(r.card):,.0f}')
            if float(r.upi          or 0) > 0: modes.append(f'UPI ₹{float(r.upi):,.0f}')
            if float(r.bank_transfer or 0) > 0: modes.append(f'Bank ₹{float(r.bank_transfer):,.0f}')
            if float(r.hotel_credit  or 0) > 0: modes.append(f'Credit ₹{float(r.hotel_credit):,.0f}')
            mode_str = ', '.join(modes) if modes else '—'

            values = [
                r.folio_no,
                r.guest_name,
                r.mobile or '',
                r.arrival_date.strftime('%d %b %Y')   if r.arrival_date   else '',
                r.departure_date.strftime('%d %b %Y') if r.departure_date else '',
                r.room_number or '',
                r.room_type   or '',
                int(r.nights  or 0),
                int(r.pax     or 0),
                r.source,
                float(r.total_bill   or 0),
                float(r.paid_amount  or 0),
                bal,
                mode_str,
                r.status,
            ]
            data_rn = _add_row(
                values, fill=row_fill,
                font=_font(size=9),
                alignment=_align('left', wrap=False),
                border=True,
                height=14,
            )

            # Currency formatting for money columns (11, 12, 13 = 1-indexed)
            for col_i in (11, 12):
                ws.cell(data_rn, col_i).number_format = '₹#,##0'
                ws.cell(data_rn, col_i).alignment = _align('right')

            # Balance column — conditional fill + font
            bal_cell = ws.cell(data_rn, 13)
            bal_cell.number_format = '₹#,##0'
            bal_cell.alignment     = _align('right')
            if bal > 0.01:
                bal_cell.fill = BAL_RED_FILL
                bal_cell.font = BAL_RED_FONT
            else:
                bal_cell.fill = BAL_GRN_FILL
                bal_cell.font = BAL_GRN_FONT

            # Center align certain cols
            for col_i in (1, 4, 5, 6, 8, 9, 10, 15):
                ws.cell(data_rn, col_i).alignment = _align('center')

        # ── Totals footer row ─────────────────────────────────────────────
        totals = [''] * NUM_COLS
        totals[0]  = f'TOTAL  ({total_guests} guests)'
        totals[10] = total_revenue
        totals[11] = total_paid
        totals[12] = total_balance
        tot_rn = _add_row(
            totals,
            fill=_fill('E5E7EB'),
            font=_font(bold=True, size=9),
            border=True,
            height=16,
        )
        for col_i in (11, 12):
            ws.cell(tot_rn, col_i).number_format = '₹#,##0'
            ws.cell(tot_rn, col_i).alignment = _align('right')
        bal_tot = ws.cell(tot_rn, 13)
        bal_tot.number_format = '₹#,##0'
        bal_tot.alignment     = _align('right')
        bal_tot.font          = _font(bold=True, size=9,
                                      color='991B1B' if total_balance > 0 else '065F46')

        # ── Spacer + prepared/verified footer rows ────────────────────────
        ws.append([''] * NUM_COLS)
        ws.append([''] * NUM_COLS)
        sig_rn = _add_row(
            ['Prepared by: ___________________', '', '',
             'Verified by: ___________________'] + [''] * (NUM_COLS - 4),
            font=_font(size=9, italic=True),
            height=18,
        )

        # ── Column widths ──────────────────────────────────────────────────
        col_widths = {
            1: 10,   # Folio
            2: 22,   # Guest Name
            3: 14,   # Mobile
            4: 12,   # Check-in
            5: 12,   # Check-out
            6: 8,    # Room No
            7: 14,   # Room Type
            8: 7,    # Nights
            9: 6,    # Pax
            10: 10,  # Source
            11: 13,  # Total Bill
            12: 13,  # Paid
            13: 13,  # Balance
            14: 28,  # Payment Mode
            15: 11,  # Status
        }
        for col_i, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_i)].width = width

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(
            buf,
            download_name=f'guest_report_{from_str}_{to_str}.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    return render_template(
        'reports/guest_report.html',
        rows=rows_raw,
        from_date=from_date, to_date=to_date,
        rt_filter=rt_filter, src_filter=src_filter,
        mode_filter=mode_filter, status_filter=status_filter,
        room_types=[r.name for r in room_types],
        sources=[r.src for r in sources],
        total_guests=total_guests,
        total_revenue=total_revenue,
        total_tax=total_tax,
        total_paid=total_paid,
        total_balance=total_balance,
        pay_cash=pay_cash, pay_card=pay_card, pay_upi=pay_upi,
        pay_bank=pay_bank, pay_credit=pay_credit,
    )


# ===========================================================================
# Void & Adjustment Report
# ===========================================================================

@reports_bp.route('/void-adjustments')
def void_adjustments_report():
    if not _require_accountant():
        from flask import abort; abort(403)

    from_str = request.args.get('from', get_business_date().replace(day=1).isoformat())
    to_str   = request.args.get('to',   get_business_date().isoformat())
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = get_business_date()

    void_reqs = (VoidRequest.query
                 .filter(func.date(VoidRequest.requested_at) >= from_date,
                         func.date(VoidRequest.requested_at) <= to_date)
                 .order_by(VoidRequest.requested_at.desc())
                 .all())

    voided_payments = (Payment.query
                       .filter(Payment.is_voided == True,
                               func.date(Payment.voided_at) >= from_date,
                               func.date(Payment.voided_at) <= to_date)
                       .order_by(Payment.voided_at.desc())
                       .all())

    total_voided = sum(float(p.amount) for p in voided_payments)

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        rows = [[p.reservation.booking_reference if p.reservation else '',
                 p.reservation.guest.name if p.reservation and p.reservation.guest else '',
                 p.payment_mode.name if p.payment_mode else '',
                 float(p.amount),
                 str(p.voided_at.date()) if p.voided_at else '',
                 p.void_reason or '']
                for p in voided_payments]
        return _excel_response(f'void_adjustments_{from_str}_{to_str}.xlsx',
                               ['Booking Ref', 'Guest', 'Mode', 'Amount',
                                'Voided On', 'Reason'],
                               rows, f'Void & Adjustments {from_str} to {to_str}')

    return render_template('reports/void_adjustments.html',
                           void_reqs=void_reqs, voided_payments=voided_payments,
                           total_voided=total_voided,
                           from_date=from_date, to_date=to_date)


# ===========================================================================
# Night Audit Report
# ===========================================================================

@reports_bp.route('/night-audit')
def night_audit():
    if not current_user.has_role('Admin', 'Manager', 'Accountant'):
        from flask import abort
        abort(403)

    from app.night_audit_service import NightAuditService
    from app.models import NightAuditLog
    import json as _json

    business_date = get_business_date()

    # Date filter — when no date is given, default to the most recent audit
    # log entry rather than today's business date.  This prevents the report
    # landing on an empty day when the business date was just force-advanced.
    date_str = request.args.get('date', '')
    if date_str:
        try:
            audit_date = date.fromisoformat(date_str)
        except ValueError:
            audit_date = business_date
    else:
        last_log = (NightAuditLog.query
                    .filter(NightAuditLog.audit_date <= business_date)
                    .order_by(NightAuditLog.audit_date.desc())
                    .first())
        audit_date = last_log.audit_date if last_log else business_date

    fmt = request.args.get('format', 'html')

    svc = NightAuditService(audit_date)

    # --- JSON API ---
    if fmt == 'json':
        report = svc.full_report()
        def _serial(obj):
            from decimal import Decimal as _Dec
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            if isinstance(obj, _Dec):
                return float(obj)
            if hasattr(obj, '__dict__') and hasattr(obj, 'id'):
                return {'id': obj.id, '_type': type(obj).__name__}
            try:
                return str(obj)
            except Exception:
                return None
        return Response(
            _json.dumps(report, default=_serial, indent=2),
            mimetype='application/json'
        )

    # --- Excel ---
    if fmt == 'excel':
        return _night_audit_excel(svc, audit_date)

    # --- Redirect HTML to the centralized Night Audit module ---
    if fmt == 'html':
        redirect_args = {'tab': 'analytics'}
        if date_str:
            redirect_args['date'] = date_str
        from flask import redirect as _redirect, url_for as _url_for
        return _redirect(_url_for('main.night_audit', **redirect_args))

    # --- HTML (default) and Print ---
    report = svc.full_report()

    # --- Print / PDF (standalone A4 page) ---
    if fmt == 'print':
        from app.models import Settings as _Sett, Reservation as _Res
        from datetime import timedelta

        def _setting(key, default=''):
            s = _Sett.query.filter_by(key=key).first()
            return s.value if s else default

        occ   = report['occupancy']
        rev   = report['revenue']
        pay   = report['payments']
        folio = report['folio']
        exc   = report['exceptions']
        ctrl  = report['control']

        adr    = round(rev['room_revenue'] / occ['occupied'], 2) if occ['occupied'] else 0.0
        revpar = round(rev['room_revenue'] / occ['sellable_rooms'], 2) if occ['sellable_rooms'] else 0.0

        # Tomorrow's forecast
        tomorrow = audit_date + timedelta(days=1)
        tom_arr = _Res.query.filter(
            _Res.arrival_date == tomorrow,
            _Res.status.in_(['Reserved', 'Confirmed'])
        ).count()
        tom_dep = _Res.query.filter(
            _Res.departure_date == tomorrow,
            _Res.status == 'CheckedIn'
        ).count()
        forecast_occ = max(0, occ['occupied'] - tom_dep + tom_arr)
        forecast_pct = round(forecast_occ / occ['sellable_rooms'] * 100, 1) if occ['sellable_rooms'] else 0.0

        # Housekeeping breakdown from room statuses
        from app.models import Room as _Room
        all_rooms = _Room.query.all()
        hk = {
            'vacant_clean':   sum(1 for r in all_rooms if r.status == 'Vacant'),
            'vacant_dirty':   sum(1 for r in all_rooms if r.status == 'Dirty'),
            'occupied':       sum(1 for r in all_rooms if r.status == 'Occupied'),
            'out_of_order':   sum(1 for r in all_rooms if r.status == 'Maintenance'),
        }

        return render_template(
            'reports/night_audit_print.html',
            audit_date=audit_date,
            report=report,
            header=report['header'],
            occupancy=occ,
            reservations=report['reservations'],
            revenue=rev,
            payments=pay,
            folio=folio,
            exceptions=exc,
            tax=report['tax'],
            shifts=report['shifts'],
            control=ctrl,
            staff_revenue=report['staff_revenue'],
            revenue_risk=report['revenue_risk'],
            adr=adr,
            revpar=revpar,
            hk=hk,
            tomorrow=tomorrow,
            tom_arr=tom_arr,
            tom_dep=tom_dep,
            forecast_occ=forecast_occ,
            forecast_pct=forecast_pct,
            hotel_address=_setting('hotel_address'),
            hotel_gstin=_setting('hotel_gstin'),
        )

    # Historical audit log list (last 30 days) for the date picker sidebar
    from app.models import NightAuditLog
    recent_logs = (NightAuditLog.query
                   .order_by(NightAuditLog.audit_date.desc())
                   .limit(30).all())

    # CICO drilldown — per-reservation breakdown for the audit date
    _cico_logs = (CICOChargeLog.query
                  .filter(CICOChargeLog.outcome == 'posted')
                  .join(CICOChargeLog.reservation)
                  .filter(Reservation.arrival_date <= audit_date,
                          Reservation.departure_date >= audit_date)
                  .order_by(CICOChargeLog.id)
                  .all())
    cico_drilldown = {
        'early_ci':  [lg for lg in _cico_logs if lg.charge_type == 'early_checkin'],
        'late_co':   [lg for lg in _cico_logs if lg.charge_type == 'late_checkout'],
    }

    from app.night_audit_service import NightAuditService as _NAS
    from app.audit_explanation_service import AuditExplanationService as _AES
    from app.services import build_daily_financial_summary as _bdfs
    ui          = _NAS.ui_state(report)
    explanation = _AES.explain(report)
    try:
        daily_financial_summary = _bdfs(audit_date)
    except Exception:
        daily_financial_summary = None

    # ── Date-scope mode (Apr 2026 critical correction) ─────────────────
    # Strict two-mode contract — the template + UI must NEVER mix:
    #
    #   mode='current'  — audit_date == business_date AND audit not closed
    #     • Live operational data, blockers, warnings
    #     • Unsettled-Checkout actions enabled
    #     • Live KPIs allowed
    #
    #   mode='snapshot' — audit_date < business_date OR audit closed
    #     • Read-only frozen view of NightAuditLog.snapshot_json
    #     • If snapshot_valid is False (reopened) → show "Snapshot
    #       invalid" banner, refuse to render live recompute
    #     • Live KPI panels suppressed
    #     • Unsettled-Checkout actions disabled
    #     • Warnings labelled "Snapshot as of <date>"
    audit_log_for_date = (NightAuditLog.query
                          .filter(NightAuditLog.audit_date == audit_date)
                          .order_by(NightAuditLog.id.desc())
                          .first())
    is_audit_closed = bool(audit_log_for_date and
                           audit_log_for_date.status in ('Completed', 'Warning'))
    is_audit_reopened = bool(audit_log_for_date and
                             audit_log_for_date.status == 'Reopened')

    # ── Apr 2026 final tightening: surface last-reopen details ──
    # When this audit was reopened, pull the most recent NightAuditReopenLog
    # entry so the UI banner can show "Reopened on DD MMM by USER".
    last_reopen_event = None
    if audit_log_for_date:
        try:
            from app.models import NightAuditReopenLog
            last_reopen_event = (NightAuditReopenLog.query
                                 .filter_by(audit_log_id=audit_log_for_date.id)
                                 .order_by(NightAuditReopenLog.id.desc())
                                 .first())
        except Exception:
            last_reopen_event = None

    # ── Apr 2026 final polish: deltas vs the previous closed audit ──
    # Pulls the IMMEDIATELY-PRIOR closed audit log and computes the day's
    # net movement. Uses snapshot columns directly so values come from
    # the frozen state, not live recomputation.
    audit_deltas = None
    try:
        prev_log = (NightAuditLog.query
                    .filter(NightAuditLog.audit_date < audit_date,
                            NightAuditLog.status.in_(['Completed', 'Warning']))
                    .order_by(NightAuditLog.audit_date.desc())
                    .first())
        if prev_log and report and report.get('revenue') and report.get('payments'):
            cur_rev   = float(report['revenue'].get('accrual_net') or 0)
            cur_coll  = float(report['payments'].get('total_collected') or 0)
            cur_recv  = float(report.get('folio', {}).get('total_credit_outstanding') or 0)
            prev_rev  = float(prev_log.accrual_revenue or 0)
            prev_coll = float(prev_log.total_payments  or 0)
            audit_deltas = {
                'prev_date':           prev_log.audit_date,
                'revenue_delta':       round(cur_rev  - prev_rev,  2),
                'collection_delta':    round(cur_coll - prev_coll, 2),
                # Receivable doesn't have a frozen prior column today;
                # exposing absolute current value as "Receivable now" so
                # the card stays useful even without delta math.
                'receivable_now':      round(cur_recv, 2),
            }
    except Exception:
        audit_deltas = None

    # ── Apr 2026 final polish: Top 3 Risks summary ──
    # Each risk now carries (score, label, icon, link, impact, action_label)
    # so the UI can show WHY IT MATTERS + a one-click Review Now button.
    top_risks = []
    try:
        # 1. Credit overdue > 30 days
        _ovd_amt   = float(report.get('folio', {}).get('credit_overdue_30_total') or 0)
        _ovd_count = int(report.get('folio', {}).get('credit_overdue_30_count') or 0)
        if _ovd_amt > 0.005:
            top_risks.append({
                'score':  _ovd_amt,
                'label':  f'₹{_ovd_amt:,.0f} credit > 30 days '
                          f'({_ovd_count} account{"s" if _ovd_count != 1 else ""})',
                'impact': 'May impact cash-flow recovery — write-off probability rises after 60 days.',
                'icon':   'bi-shield-exclamation',
                'link':   url_for('reports.credit_aging'),
                'action_label': 'Open Aging',
            })
        # 2. Unsettled checkouts (financial blocker)
        _unsettled = report.get('folio', {}).get('checkout_outstanding_total') or 0
        _unsettled_n = len(report.get('folio', {}).get('checkout_outstanding_list') or [])
        if _unsettled > 0.005:
            top_risks.append({
                'score':  float(_unsettled) * 1.5,   # weight blocker higher
                'label':  f'₹{float(_unsettled):,.0f} unsettled at checkout '
                          f'({_unsettled_n} folio{"s" if _unsettled_n != 1 else ""})',
                'impact': 'Blocks audit close — settle, mark as receivable, or collect before locking the day.',
                'icon':   'bi-receipt-cutoff',
                'link':   url_for('reports.night_audit'),
                'action_label': 'Review Folios',
                'jumpto': 'folio',   # also activate the Folio tab on this page
            })
        # 3. High discounts (>15% off rate)
        _disc_total = float(report.get('revenue', {}).get('discount_total') or 0)
        _disc_count = int(report.get('revenue', {}).get('discount_count') or 0)
        if _disc_count >= 3 and _disc_total > 1000:
            top_risks.append({
                'score':  _disc_total * 0.5,
                'label':  f'{_disc_count} discount bookings totalling ₹{_disc_total:,.0f}',
                'impact': 'Reduces net revenue. Verify approver and discount-policy compliance.',
                'icon':   'bi-tag',
                'link':   None,
                'action_label': 'Review Discounts',
                'jumpto': 'revenue',
            })
        # 4. Missed check-ins
        _missed_ci = len(report.get('occupancy', {}).get('expected_not_checkedin') or [])
        if _missed_ci >= 1:
            top_risks.append({
                'score':  _missed_ci * 8000,
                'label':  f'{_missed_ci} expected arrival{"s" if _missed_ci != 1 else ""} not checked in',
                'impact': 'Possible no-show — confirm arrival or release inventory before audit close.',
                'icon':   'bi-person-exclamation',
                'link':   None,
                'action_label': 'Review Arrivals',
                'jumpto': 'occupancy',
            })
        # 5. Missed checkouts
        _missed_co = len(report.get('occupancy', {}).get('expected_not_checkedout') or [])
        if _missed_co >= 1:
            top_risks.append({
                'score':  _missed_co * 10000,
                'label':  f'{_missed_co} expected departure{"s" if _missed_co != 1 else ""} not checked out',
                'impact': 'Room status will not flip to dirty. Late-checkout fee may apply — check folios.',
                'icon':   'bi-door-open',
                'link':   None,
                'action_label': 'Review Departures',
                'jumpto': 'occupancy',
            })
        # 6. Leakage > ₹2k
        _leak_total = float(report.get('revenue', {}).get('leakage_total') or 0)
        _leak_count = int(report.get('revenue', {}).get('leakage_count') or 0)
        if _leak_total > 2000:
            top_risks.append({
                'score':  _leak_total * 0.4,
                'label':  f'₹{_leak_total:,.0f} revenue leakage across {_leak_count} room(s)',
                'impact': 'Lost revenue — review rate-override policy and tariff configuration.',
                'icon':   'bi-currency-exchange',
                'link':   None,
                'action_label': 'View Leakage',
                'jumpto': 'revenue',
            })
        top_risks.sort(key=lambda r: r['score'], reverse=True)
        top_risks = top_risks[:3]
    except Exception:
        top_risks = []

    # ── Apr 2026 final polish: Audit Completion Confidence ──
    # Score 0-100. Each risk class deducts a weighted amount; floors at 0.
    # Keeps the math transparent so the operator can see WHY the score is
    # what it is (deductions list rendered in the UI alongside the badge).
    try:
        confidence = 100.0
        deductions = []
        # Hard blockers
        if exceptions and getattr(exceptions, 'get', None):
            _b = int(exceptions.get('blocker_count') or 0)
            _w = int(exceptions.get('warning_count') or 0)
            if _b > 0:
                _d = min(40, _b * 12)
                confidence -= _d
                deductions.append({'reason': f'{_b} blocker(s)', 'points': _d})
            if _w > 0:
                _d = min(15, _w * 3)
                confidence -= _d
                deductions.append({'reason': f'{_w} warning(s)', 'points': _d})
        # Snapshot integrity
        if snapshot_integrity and snapshot_integrity.get('has_hash') and not snapshot_integrity.get('matches'):
            confidence -= 30
            deductions.append({'reason': 'Snapshot hash mismatch', 'points': 30})
        # Reconciliation difference > ₹100
        _rd = abs(float(report.get('control', {}).get('reconciliation_difference') or 0))
        if _rd > 100:
            _d = min(15, int(_rd / 1000) + 5)
            confidence -= _d
            deductions.append({'reason': f'₹{_rd:,.0f} reconciliation difference', 'points': _d})
        # Overdue credit > ₹5k
        if _ovd_amt > 5000:
            _d = min(10, int(_ovd_amt / 5000))
            confidence -= _d
            deductions.append({'reason': f'₹{_ovd_amt:,.0f} overdue credit', 'points': _d})
        # Leakage > 5% of revenue
        _rev_net = float(report.get('revenue', {}).get('accrual_net') or 0)
        if _rev_net > 0 and _leak_total > 0:
            _leak_pct = _leak_total / _rev_net * 100
            if _leak_pct >= 5:
                _d = min(10, int(_leak_pct))
                confidence -= _d
                deductions.append({'reason': f'Leakage {_leak_pct:.1f}% of net revenue', 'points': _d})
        # Unsettled checkouts
        if _unsettled > 0.005:
            _d = min(15, max(5, int(_unsettled / 5000)))
            confidence -= _d
            deductions.append({'reason': f'₹{_unsettled:,.0f} unsettled at checkout', 'points': _d})
        confidence = max(0, min(100, round(confidence)))
        if confidence >= 90:
            confidence_band = {'state': 'excellent', 'cls': 'success', 'label': 'Excellent'}
        elif confidence >= 75:
            confidence_band = {'state': 'good',      'cls': 'info',    'label': 'Good'}
        elif confidence >= 50:
            confidence_band = {'state': 'needs',     'cls': 'warning text-dark', 'label': 'Needs Review'}
        else:
            confidence_band = {'state': 'risky',     'cls': 'danger',  'label': 'High Risk'}
        audit_confidence = {
            'score':      confidence,
            'band':       confidence_band,
            'deductions': deductions,
        }
    except Exception:
        audit_confidence = None
    if audit_date == business_date and not is_audit_closed:
        audit_mode = 'current'
    else:
        audit_mode = 'snapshot'

    # Snapshot validity contract: in snapshot mode, snapshot_valid must
    # be True AND snapshot_json must exist. Otherwise the UI shows the
    # "unavailable" banner and the operator must re-run the audit to
    # produce a fresh frozen snapshot.
    snapshot_valid = bool(audit_log_for_date and
                          getattr(audit_log_for_date, 'snapshot_valid', True) and
                          audit_log_for_date.snapshot_json)
    snapshot_unavailable_in_history = (audit_mode == 'snapshot' and
                                       not snapshot_valid)
    # ── Snapshot tamper-detection (Apr 2026 final tightening) ────
    # Re-hash the stored snapshot_json and compare to snapshot_hash.
    # Mismatch surfaces a "Snapshot integrity warning" banner so a
    # silent DB edit / version drift can never go unnoticed.
    from app.services import verify_snapshot_integrity as _vsi
    snapshot_integrity = _vsi(audit_log_for_date)

    # Legacy alias kept for templates not yet migrated.
    is_history_view = (audit_mode == 'snapshot')

    return render_template(
        'reports/night_audit.html',
        audit_date=audit_date,
        business_date=business_date,
        today=date.today(),
        report=report,
        header=report['header'],
        occupancy=report['occupancy'],
        reservations=report['reservations'],
        revenue=report['revenue'],
        payments=report['payments'],
        folio=report['folio'],
        room_charges=report['room_charges'],
        exceptions=report['exceptions'],
        tax=report['tax'],
        shifts=report['shifts'],
        control=report['control'],
        staff_revenue=report['staff_revenue'],
        revenue_risk=report['revenue_risk'],
        recent_logs=recent_logs,
        cico_drilldown=cico_drilldown,
        ui=ui,
        explanation=explanation,
        daily_financial_summary=daily_financial_summary,
        is_history_view=is_history_view,
        is_audit_closed=is_audit_closed,
        is_audit_reopened=is_audit_reopened,
        last_reopen_event=last_reopen_event,
        audit_deltas=audit_deltas,
        top_risks=top_risks,
        audit_confidence=audit_confidence,
        snapshot_valid=snapshot_valid,
        snapshot_unavailable_in_history=snapshot_unavailable_in_history,
        snapshot_integrity=snapshot_integrity,
        audit_log_for_date=audit_log_for_date,
        audit_mode=audit_mode,
    )


@reports_bp.route('/night-audit/run', methods=['POST'])
def night_audit_run():
    """Stage 2 — Run pre-audit checks and mark audit as InProgress."""
    if not current_user.has_role('Admin', 'Manager', 'Accountant'):
        from flask import abort
        abort(403)

    from flask import redirect, url_for, flash
    from app.models import NightAuditLog, db
    from app.night_audit_service import NightAuditService
    import json as _json

    date_str = request.form.get('audit_date', '')
    try:
        audit_date = date.fromisoformat(date_str)
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('main.night_audit', tab='dashboard'))

    svc = NightAuditService(audit_date)
    exc = svc.exception_report()
    rev = svc.revenue_summary()
    pay = svc.payment_summary()
    folio = svc.folio_control()
    occ = svc.occupancy_position()
    shifts = svc.staff_shift_summary()

    # v2.2.16 FIX 2 — duplicate-date guard. Production carries legacy
    # duplicate NightAuditLog rows for some dates (2026-05-04 / 2026-05-07).
    # order_by(id.desc()) makes this lookup deterministic so the run path
    # and the complete path always reuse the SAME (latest) row for a date
    # instead of an arbitrary one — never a blind second insert.
    log = (NightAuditLog.query.filter_by(audit_date=audit_date)
           .order_by(NightAuditLog.id.desc()).first())
    if not log:
        log = NightAuditLog(audit_date=audit_date)
        db.session.add(log)

    # Only move to InProgress if not already completed
    if log.status in ('Pending', 'Reopened', None):
        log.status = 'InProgress'
        log.started_by_user_id = current_user.id
        log.started_at = datetime.utcnow()

    log.blocker_count = exc['blocker_count']
    log.warning_count = exc['warning_count']
    log.total_revenue = pay['total_collected']              # cash collected
    log.net_revenue = pay['total_collected'] - rev['discount_total']  # cash net
    log.accrual_revenue = rev['accrual_net']                # accrual net (earned)
    log.total_discount = rev['discount_total']
    log.total_payments = pay['total_collected']
    log.outstanding_amount = folio['total_outstanding']
    log.occupancy_count = occ['occupied']
    log.pending_checkouts = len(occ['expected_not_checkedout'])
    # Cash from shifts
    log.expected_cash = sum(s['expected_cash'] for s in shifts['shifts'])
    log.actual_cash = sum(s['declared_cash'] for s in shifts['shifts'])
    log.cash_variance = float(log.actual_cash) - float(log.expected_cash)

    db.session.commit()
    flash(f'Audit checks run for {audit_date.strftime("%d %b %Y")}. '
          f'{exc["blocker_count"]} blocker(s), {exc["warning_count"]} warning(s).', 'info')
    return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))


@reports_bp.route('/night-audit/complete', methods=['POST'])
def night_audit_complete():
    """Stage 3 — Complete the audit. Override allowed for Admin/Manager with mandatory remark."""
    if not current_user.has_role('Admin', 'Manager'):
        from flask import abort
        abort(403)

    from flask import redirect, url_for, flash
    from app.models import NightAuditLog, db
    from app.night_audit_service import NightAuditService
    import json as _json

    date_str        = request.form.get('audit_date', '')
    override_reason = request.form.get('override_reason', '').strip()
    manager_name    = request.form.get('manager_name', '').strip()
    override_ts     = request.form.get('override_timestamp', '').strip()
    # Embed manager attribution into the override_reason for the audit log
    if manager_name and override_reason:
        override_reason = f'[Manager: {manager_name}] {override_reason}'
    elif manager_name:
        override_reason = f'[Manager: {manager_name}]'
    if override_ts and override_reason:
        override_reason += f' [at {override_ts[:19].replace("T"," ")} UTC]'
    try:
        audit_date = date.fromisoformat(date_str)
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('main.night_audit', tab='dashboard'))

    svc = NightAuditService(audit_date)
    exc = svc.exception_report()
    ctrl = svc.final_control()
    rev = svc.revenue_summary()
    pay = svc.payment_summary()
    folio = svc.folio_control()
    occ = svc.occupancy_position()
    shifts = svc.staff_shift_summary()

    # ── Hard validations (CEO-level controls) ────────────────────────────
    hard_blocks = []

    if exc['blocker_count'] > 0:
        hard_blocks.append(f"{exc['blocker_count']} unresolved blocker(s)")

    recon_diff = float(ctrl['reconciliation_difference'])
    if abs(recon_diff) > 1.0:
        hard_blocks.append(
            f"Reconciliation difference ₹{abs(recon_diff):,.2f} — must be zero"
        )

    if folio['checkout_outstanding_total'] > 0.01:
        hard_blocks.append(
            f"Pending folios outstanding — ₹{folio['checkout_outstanding_total']:,.2f} uncollected"
        )

    if folio['negative_folios']:
        overpay_total = sum(abs(float(f['balance'])) for f in folio['negative_folios'])
        hard_blocks.append(
            f"{len(folio['negative_folios'])} overpayment(s) unresolved — ₹{overpay_total:,.2f}"
        )

    if hard_blocks and not override_reason:
        issues = '; '.join(hard_blocks)
        flash(f'Cannot complete audit: {issues}. '
              'Provide an override reason to proceed.', 'danger')
        return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))

    try:
        # Lock the audit log row to prevent concurrent completion.
        # v2.2.16 FIX 2 — order_by(id.desc()) so that, when a duplicate
        # row already exists for this date, completion deterministically
        # acts on the SAME (latest) row the run path used — not an
        # arbitrary duplicate. Find-or-reuse, never a blind second insert.
        log = (db.session.query(NightAuditLog)
               .with_for_update()
               .filter_by(audit_date=audit_date)
               .order_by(NightAuditLog.id.desc())
               .first())
        if not log:
            log = NightAuditLog(audit_date=audit_date, status='Pending')
            db.session.add(log)
            db.session.flush()

        # Idempotency guard: reject if already completed
        if log.status in ('Completed', 'Warning'):
            db.session.rollback()
            flash(f'Audit for {audit_date.strftime("%d %b %Y")} is already completed '
                  f'(status: {log.status}). Reopen it first if changes are needed.', 'warning')
            return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))

        # Validate override reason is not whitespace-only
        if hard_blocks and not override_reason.strip():
            db.session.rollback()
            issues = '; '.join(hard_blocks)
            flash(f'Cannot complete audit: {issues}. '
                  'Provide a meaningful override reason (not blank).', 'danger')
            return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))

        def _serial(obj):
            from decimal import Decimal as _Dec
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            if isinstance(obj, _Dec):
                return float(obj)
            if hasattr(obj, '__dict__') and hasattr(obj, 'id'):
                return {'id': obj.id, '_type': type(obj).__name__}
            try:
                return str(obj)
            except Exception:
                return None

        log.status = 'Warning' if hard_blocks else 'Completed'
        log.run_by_user_id = current_user.id
        log.run_at = datetime.utcnow()
        log.completed_at = datetime.utcnow()
        # Cash-basis fields
        log.total_revenue = pay['total_collected']              # cash collected
        log.total_payments = pay['total_collected']
        log.net_revenue = pay['total_collected'] - rev['discount_total']  # cash net
        log.total_discount = rev['discount_total']
        # Accrual-basis field
        log.accrual_revenue = rev['accrual_net']                # accrual net (earned)
        log.outstanding_amount = folio['total_outstanding']
        log.reconciliation_difference = ctrl['reconciliation_difference']
        log.blocker_count = exc['blocker_count']
        log.warning_count = exc['warning_count']
        log.occupancy_count = occ['occupied']
        log.pending_checkouts = len(occ['expected_not_checkedout'])
        log.expected_cash = sum(s['expected_cash'] for s in shifts['shifts'])
        log.actual_cash = sum(s['declared_cash'] for s in shifts['shifts'])
        log.cash_variance = float(log.actual_cash) - float(log.expected_cash)
        if override_reason:
            log.override_used = True
            log.override_reason = override_reason

        # Save immutable snapshot + mark valid + tamper-detection hash
        try:
            from app.services import compute_snapshot_hash as _csh
            from app import APP_VERSION as _AV
            _snap_text = _json.dumps(svc.full_report(), default=_serial)
            log.snapshot_json    = _snap_text
            log.snapshot_valid   = True
            log.snapshot_hash    = _csh(_snap_text)
            log.snapshot_version = _AV
        except Exception:
            log.snapshot_valid = False

        # Advance the PMS business date to the next day
        from app.models import BusinessDate
        bd = (db.session.query(BusinessDate)
              .with_for_update()
              .first())
        if bd and bd.current_date == audit_date:
            bd.current_date = audit_date + timedelta(days=1)
            bd.is_locked = False
            bd.updated_at = datetime.utcnow()

        db.session.commit()
        status_label = log.status
        override_note = ' (Override used)' if override_reason else ''
        flash(f'Night audit for {audit_date.strftime("%d %b %Y")} {status_label.lower()}.{override_note} '
              f'Business date advanced to {(audit_date + timedelta(days=1)).strftime("%d %b %Y")}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Night audit completion failed: {str(e)}', 'danger')
    return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))


@reports_bp.route('/night-audit/reopen', methods=['POST'])
def night_audit_reopen():
    """Stage 6 — Reopen a completed audit with reason. Admin/Manager only."""
    if not current_user.has_role('Admin', 'Manager'):
        from flask import abort
        abort(403)

    from flask import redirect, url_for, flash
    from app.models import NightAuditLog, NightAuditReopenLog, db

    date_str = request.form.get('audit_date', '')
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('A reason is required to reopen the audit.', 'danger')
        return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))

    try:
        audit_date = date.fromisoformat(date_str)
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('main.night_audit', tab='dashboard'))

    try:
        # Lock the audit log row to prevent concurrent reopen/complete
        log = (db.session.query(NightAuditLog)
               .with_for_update()
               .filter_by(audit_date=audit_date)
               .first())
        if not log:
            db.session.rollback()
            flash('No audit record found for this date.', 'danger')
            return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))

        if log.status not in ('Completed', 'Warning'):
            db.session.rollback()
            flash(f'Audit is not completed (status: {log.status}) — nothing to reopen.', 'warning')
            return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))

        # Write immutable reopen trail entry
        _previous_status = log.status
        reopen_entry = NightAuditReopenLog(
            audit_log_id=log.id,
            audit_date=audit_date,
            reopened_by_user_id=current_user.id,
            reason=reason,
            previous_status=_previous_status,
        )
        db.session.add(reopen_entry)
        log.status = 'Reopened'
        log.reopen_reason = reason
        log.completed_at = None
        # ── Invalidate the frozen snapshot (Apr 2026 critical correction) ──
        # Reopen means the closed figures are no longer authoritative —
        # the audit must be re-run to produce a fresh snapshot. We keep
        # snapshot_json intact for forensic comparison but flip
        # snapshot_valid=False so every reader (UI, API, history view)
        # treats it as stale.
        log.snapshot_valid = False

        # ── Apr 2026 final tightening: AuditLog event for reopen ──
        # The existing NightAuditReopenLog is a domain-specific table;
        # this AuditLog row is the cross-entity trail that already powers
        # the governance alert engine and admin debug panels.
        try:
            from app.routes import _write_audit
            _write_audit(
                'NightAuditLog', log.id, 'audit_reopened',
                {'status':              _previous_status,
                 'audit_date':          audit_date.isoformat(),
                 'snapshot_was_valid':  True},
                {'status':              'Reopened',
                 'reason':              reason[:300] if reason else None,
                 'reopened_by_user_id': current_user.id,
                 'snapshot_valid':      False},
            )
        except Exception:
            # Audit-log write must never block the reopen action itself.
            pass

        # Roll back business date if it was advanced by the completion
        from app.models import BusinessDate
        bd = (db.session.query(BusinessDate)
              .with_for_update()
              .first())
        if bd and bd.current_date == audit_date + timedelta(days=1):
            bd.current_date = audit_date
            bd.updated_at = datetime.utcnow()

        db.session.commit()
        flash(f'Audit for {audit_date.strftime("%d %b %Y")} reopened. '
              f'Business date rolled back to {audit_date.strftime("%d %b %Y")}.', 'warning')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to reopen audit: {str(e)}', 'danger')

    return redirect(url_for('main.night_audit', tab='dashboard', date=date_str))


# ---------------------------------------------------------------------------
# Skipped-Audit Recovery
# ---------------------------------------------------------------------------
# When an admin presses "Force Close" (night_audit_advance_date), any
# pending dates get a NightAuditLog row with status='Skipped' and no
# room_rent ExtraCharges. That leaves the accounting inconsistent:
# reservations that spanned the skipped date carry no room revenue for
# that night, and is_date_locked treats 'Skipped' as sealed so checkout
# can be blocked depending on which date comparison hits it first.
#
# The recovery flow re-runs the normal audit computations for a given
# historical date, posts the missing room_rent charges (idempotently),
# and rewrites the existing log in place — preserving a NightAuditReopenLog
# trail entry so the correction is auditable. BusinessDate is untouched;
# this is a historical-date correction, not a date walk.

def _rerun_skipped_audit(target_date, user_id: int, reason: str) -> tuple[bool, str]:
    """Convert a 'Skipped' NightAuditLog for `target_date` into a proper
    Completed / Warning log.

    Parameters
    ----------
    target_date : date
        The calendar date whose audit was previously skipped.
    user_id : int
        Admin user performing the recovery (written to the reopen trail).
    reason : str
        Mandatory explanation — stored on NightAuditReopenLog and on
        NightAuditLog.override_reason so both sides remember WHY.

    Returns
    -------
    (ok, message) — ok=False when validation fails or the rerun couldn't
    complete. The caller is responsible for flashing the message.

    Rules
    -----
    * Status must be 'Skipped' — otherwise refuse (normal reopen flow
      handles Completed/Warning entries).
    * Idempotent against already-posted room_rent rows (skip dupes).
    * Never mutates BusinessDate.current_date.
    * Writes both an immutable NightAuditReopenLog row AND updates
      override_reason so "why was this fixed?" is queryable from
      either side.
    """
    from app.models import (
        db, NightAuditLog, NightAuditReopenLog, Reservation, ExtraCharge,
        ReservationNightRate, Shift,
    )
    try:
        # ── Lock the log row — prevent concurrent rerun / reopen.
        log = (db.session.query(NightAuditLog)
               .with_for_update()
               .filter_by(audit_date=target_date)
               .first())
        if not log:
            db.session.rollback()
            return False, f'No audit record exists for {target_date.isoformat()}.'
        if log.status != 'Skipped':
            db.session.rollback()
            return (False, f'Audit is "{log.status}", not "Skipped". Use the '
                           f'Reopen flow for Completed/Warning audits.')

        # ── Record the recovery in the immutable reopen trail first.
        db.session.add(NightAuditReopenLog(
            audit_log_id=log.id,
            audit_date=target_date,
            reopened_by_user_id=user_id,
            reason=f'[Re-run skipped] {reason}',
            previous_status='Skipped',
        ))

        # ── KPI metrics for the date (reuses the same helpers the live
        #    audit runs against). All are safe for historical dates.
        from app.kpi_helpers import (
            get_cash_revenue, get_cash_discount, get_net_cash_revenue,
            get_accrual_summary,
        )
        cash_collected = get_cash_revenue(target_date)
        cash_discount  = get_cash_discount(target_date)
        cash_net       = get_net_cash_revenue(target_date)
        accrual        = get_accrual_summary(target_date)

        # ── Occupancy + pending checkouts snapshot AS OF target_date.
        from sqlalchemy.orm import subqueryload as _sql_subqueryload
        in_house = Reservation.query.options(
            _sql_subqueryload(Reservation.room_links)
        ).filter(
            Reservation.status.in_(('CheckedIn', 'CheckedOut')),
            Reservation.arrival_date <= target_date,
            Reservation.departure_date > target_date,
        ).all()
        # v2.2.15 — BUSINESS-DATE occupancy correction (mirrors Patch A
        # in night_audit_service.occupancy_position). `in_house` above is
        # already the correct business-date population (CheckedIn ∪
        # CheckedOut, arrival <= target < departure). Count DISTINCT
        # physical rooms over that whole set — counting only the
        # CheckedIn subset dropped guests who occupied a room that night
        # but have since departed, under-counting the figure frozen into
        # NightAuditLog.occupancy_count. count_distinct_rooms() dedupes
        # by room_id ∪ bridge, so this is a distinct-room count, never a
        # reservation-row count.
        from app.occupancy_engine import count_distinct_rooms as _count_rooms
        occupied_rooms = _count_rooms(in_house)
        pending_checkouts = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.departure_date <= target_date,
        ).count()

        # ── Post any MISSING room_rent ExtraCharges for the target date.
        #    Idempotent: skip any reservation that already has a
        #    room_rent row for that exact date (no double-posting).
        room_charges_posted = 0
        for res in in_house:
            already = ExtraCharge.query.filter_by(
                reservation_id=res.id,
                charge_type='room_rent',
                charge_date=target_date,
            ).first()
            if already:
                continue

            # Rate resolution mirrors services.run_night_audit: prefer
            # the pre-computed nightly row, fall back to rate_per_night.
            rate = None
            nr_row = None
            try:
                nr_row = ReservationNightRate.query.filter_by(
                    reservation_id=res.id, stay_date=target_date).first()
                if nr_row and not nr_row.is_posted:
                    rate = float(nr_row.final_rate or 0)
            except Exception:
                nr_row = None
            if rate is None or rate <= 0:
                rate = float(res.rate_per_night or 0)
            if rate <= 0:
                continue

            room_no = res.room.room_number if res.room else '?'
            ec = ExtraCharge(
                reservation_id=res.id,
                description=(f'Room Rent — {target_date.strftime("%d %b")} '
                             f'(Room {room_no})  [recovered]'),
                amount=rate,
                charge_date=target_date,
                charge_type='room_rent',
                charge_category='Room',
            )
            db.session.add(ec)
            db.session.flush()
            if nr_row and not nr_row.is_posted:
                nr_row.is_posted = True
                nr_row.posted_charge_id = ec.id
                nr_row.is_locked = True
            room_charges_posted += 1

        # ── Blockers: same three the live audit checks (informational
        #    only for a historical rerun — we complete regardless, but
        #    surface the count so History shows the quality signal).
        blockers = []
        if pending_checkouts:
            blockers.append(f'{pending_checkouts} pending checkout(s) as of {target_date}')
        zero_rate = sum(1 for r in in_house
                        if not r.rate_per_night or float(r.rate_per_night) <= 0)
        if zero_rate:
            blockers.append(f'{zero_rate} room(s) with zero rate on {target_date}')
        # Historical shift-open check is meaningless after the fact; skip.

        # ── Rewrite the log in place: Skipped → Completed/Warning.
        log.status              = 'Warning' if blockers else 'Completed'
        log.total_revenue       = cash_collected
        log.net_revenue         = cash_net
        log.total_discount      = cash_discount
        log.accrual_revenue     = accrual['accrual_net']
        log.occupancy_count     = occupied_rooms
        log.pending_checkouts   = pending_checkouts
        log.run_at              = datetime.utcnow()
        log.completed_at        = datetime.utcnow()
        log.run_by_user_id      = user_id
        log.override_used       = True
        log.override_reason     = (
            (log.override_reason or '') +
            f' | RE-RUN by uid={user_id} at {datetime.utcnow().isoformat()}: {reason}'
        )
        log.blocker_count       = len(blockers)
        if blockers:
            log.notes = 'Re-run from Skipped. Blockers: ' + '; '.join(blockers)
        else:
            log.notes = (f'Re-run from Skipped. Posted {room_charges_posted} '
                         f'room_rent charge(s).')

        # ── Store frozen snapshot so later views don't recompute.
        try:
            import json as _snap_json
            from decimal import Decimal as _Dec
            from app.night_audit_service import NightAuditService
            _snap_svc = NightAuditService(target_date)
            def _serial(obj):
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                if isinstance(obj, _Dec):
                    return float(obj)
                if hasattr(obj, '__dict__') and hasattr(obj, 'id'):
                    return {'id': obj.id, '_type': type(obj).__name__}
                try:
                    return str(obj)
                except Exception:
                    return None
            from app.services import compute_snapshot_hash as _csh
            from app import APP_VERSION as _AV
            _snap_text = _snap_json.dumps(_snap_svc.full_report(), default=_serial)
            log.snapshot_json    = _snap_text
            log.snapshot_valid   = True
            log.snapshot_hash    = _csh(_snap_text)
            log.snapshot_version = _AV
        except Exception:
            # Snapshot is a nice-to-have; never block the recovery on it.
            log.snapshot_valid = False

        db.session.commit()
        return True, (
            f'Audit for {target_date.strftime("%d %b %Y")} re-run successfully. '
            f'Posted {room_charges_posted} missing room_rent charge(s); '
            f'status is now "{log.status}".'
        )
    except Exception as exc:
        db.session.rollback()
        import logging as _rr_log
        _rr_log.getLogger(__name__).exception('rerun skipped audit failed')
        return False, f'Re-run failed: {exc}'


@reports_bp.route('/night-audit/rerun-skipped', methods=['POST'])
def night_audit_rerun_skipped():
    """Admin-only: re-run a previously Skipped audit for a specific date.

    Converts the Skipped log into a Completed/Warning one and posts any
    missing room_rent ExtraCharges. Mandatory reason is written to the
    immutable reopen trail. Does NOT touch BusinessDate — this is a
    historical-date correction, not a rollback.
    """
    if not current_user.has_role('Admin'):
        from flask import abort
        abort(403)

    from flask import redirect, url_for, flash

    date_str = request.form.get('audit_date', '').strip()
    reason   = request.form.get('reason', '').strip()
    if not reason:
        flash('A reason is required to re-run a skipped audit.', 'danger')
        return redirect(url_for('reports.night_audit_history'))
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('reports.night_audit_history'))

    ok, msg = _rerun_skipped_audit(target_date, current_user.id, reason)
    flash(msg, 'success' if ok else 'danger')

    # If later-dated audits already exist, surface an advisory so the
    # operator knows downstream totals may have shifted.
    try:
        from app.models import NightAuditLog
        later_count = (NightAuditLog.query
                       .filter(NightAuditLog.audit_date > target_date,
                               NightAuditLog.status.in_(
                                   ('Completed', 'Warning', 'Reopened')))
                       .count())
        if ok and later_count:
            flash(
                f'Note: {later_count} audit(s) exist after {target_date}. '
                f'Revenue & outstanding figures on those later days may '
                f'need review because room_rent was posted retroactively.',
                'warning',
            )
    except Exception:
        pass

    return redirect(url_for('reports.night_audit_history'))


@reports_bp.route('/night-audit/advance-date', methods=['POST'])
def night_audit_advance_date():
    """Admin-only: force-advance the PMS business date to today's real calendar date.
    Used when the date gets stuck due to a Reopened audit that was never completed.
    Writes an audit trail entry for every skipped day."""
    if not current_user.has_role('Admin'):
        from flask import abort
        abort(403)

    from flask import redirect, url_for, flash
    from app.models import BusinessDate, NightAuditLog
    from datetime import date as _date_cls

    bd = BusinessDate.query.first()
    if not bd:
        flash('Business date record not found.', 'danger')
        return redirect(url_for('main.night_audit', tab='dashboard'))

    today = _date_cls.today()
    if bd.current_date >= today:
        flash(f'Business date ({bd.current_date}) is already current.', 'info')
        return redirect(url_for('main.night_audit', tab='dashboard'))

    try:
        # Lock BusinessDate to prevent concurrent advances
        bd = (db.session.query(BusinessDate)
              .with_for_update()
              .first())

        skipped = []
        cursor = bd.current_date
        while cursor < today:
            log = NightAuditLog.query.filter_by(audit_date=cursor).first()
            if not log:
                log = NightAuditLog(audit_date=cursor)
                db.session.add(log)
            # Mark as 'Skipped' (not 'Completed') so these are visually
            # distinct from real audits in history and reports
            if log.status not in ('Completed', 'Warning'):
                log.status = 'Skipped'
                log.run_by_user_id = current_user.id
                log.run_at = datetime.utcnow()
                log.completed_at = datetime.utcnow()
                log.override_used = True
                log.override_reason = (
                    f'Force-advanced by admin ({current_user.full_name}) '
                    f'to catch up to {today}. No audit was performed for this date.'
                )
            skipped.append(cursor.strftime('%d %b'))
            cursor += timedelta(days=1)

        bd.current_date = today
        bd.is_locked = False
        bd.updated_at = datetime.utcnow()
        db.session.commit()

        flash(f'Business date advanced to {today.strftime("%d %b %Y")}. '
              f'Skipped dates: {", ".join(skipped)}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to advance date: {str(e)}', 'danger')
    return redirect(url_for('main.night_audit', tab='dashboard'))


@reports_bp.route('/night-audit/history')
def night_audit_history():
    """Stage 7 — Full audit history list."""
    if not current_user.has_role('Admin', 'Manager', 'Accountant'):
        from flask import abort
        abort(403)

    from app.models import NightAuditLog
    logs = (NightAuditLog.query
            .order_by(NightAuditLog.audit_date.desc())
            .all())
    return render_template('reports/night_audit_history.html', logs=logs)


@reports_bp.route('/night-audit/<int:log_id>')
def night_audit_snapshot(log_id):
    """View a historical audit snapshot exactly as it was stored at completion."""
    if not current_user.has_role('Admin', 'Manager', 'Accountant'):
        from flask import abort
        abort(403)

    from app.models import NightAuditLog
    import json as _json

    log = NightAuditLog.query.get_or_404(log_id)
    snapshot = None
    if log.snapshot_json:
        try:
            snapshot = _json.loads(log.snapshot_json)
        except Exception:
            snapshot = None

    fmt = request.args.get('format', 'html')
    if fmt == 'json' and snapshot:
        return Response(_json.dumps(snapshot, indent=2), mimetype='application/json')

    return render_template(
        'reports/night_audit_snapshot.html',
        log=log,
        snapshot=snapshot,
        audit_date=log.audit_date,
    )


# ---------------------------------------------------------------------------
# Night Audit Excel helper
# ---------------------------------------------------------------------------

def _night_audit_excel(svc, audit_date: date) -> Response:
    try:
        import openpyxl
        from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                                     GradientFill)
        from openpyxl.utils import get_column_letter
    except ImportError:
        return Response('openpyxl not installed.', status=500)

    from datetime import timedelta
    from app.models import Settings as _Sett, Reservation as _Res, Room as _Room

    def _setting(key, default=''):
        s = _Sett.query.filter_by(key=key).first()
        return s.value if s else default

    report    = svc.full_report()
    hdr       = report['header']
    occ       = report['occupancy']
    rev       = report['revenue']
    pay       = report['payments']
    folio     = report['folio']
    exc       = report['exceptions']
    tax_snap  = report['tax']
    shifts    = report['shifts']
    ctrl      = report['control']
    res_rec   = report['reservations']
    rc        = report['room_charges']

    hotel_name    = hdr['hotel_name']
    hotel_address = _setting('hotel_address', '')
    hotel_gstin   = _setting('hotel_gstin', '')
    generated_at  = hdr['generated_at']

    # ── KPI calculations ───────────────────────────────────────────────────
    adr    = round(rev['room_revenue'] / occ['occupied'], 2) if occ['occupied'] else 0.0
    revpar = round(rev['room_revenue'] / occ['sellable_rooms'], 2) if occ['sellable_rooms'] else 0.0

    # ── Tomorrow forecast ──────────────────────────────────────────────────
    tomorrow = audit_date + timedelta(days=1)
    tom_arr  = _Res.query.filter(_Res.arrival_date == tomorrow,
                                  _Res.status.in_(['Reserved', 'Confirmed'])).count()
    tom_dep  = _Res.query.filter(_Res.departure_date == tomorrow,
                                  _Res.status == 'CheckedIn').count()
    forecast_occ = max(0, occ['occupied'] - tom_dep + tom_arr)
    forecast_pct = round(forecast_occ / occ['sellable_rooms'] * 100, 1) if occ['sellable_rooms'] else 0.0

    # ── Housekeeping room breakdown ────────────────────────────────────────
    all_rooms = _Room.query.all()
    hk_vacant_clean = sum(1 for r in all_rooms if r.status == 'Vacant')
    hk_vacant_dirty = sum(1 for r in all_rooms if r.status == 'Dirty')
    hk_occupied     = sum(1 for r in all_rooms if r.status == 'Occupied')
    hk_oor          = sum(1 for r in all_rooms if r.status == 'Maintenance')

    # ── Style helpers ──────────────────────────────────────────────────────
    NAVY        = '1A3A6B'
    MID_BLUE    = '2D5FA8'
    LIGHT_BLUE  = 'D6E4F7'
    PALE_BLUE   = 'EEF4FC'
    PALE_GREY   = 'F2F2F2'
    DARK_GREY   = '404040'
    TOTAL_FILL  = 'C5D9F1'
    GRAND_FILL  = '1A3A6B'
    WARN_FILL   = 'FFF3CD'
    ERR_FILL    = 'FFCCCC'
    GREEN_FILL  = 'D6F0E0'
    WHITE       = 'FFFFFF'

    def _fill(hex_color):
        return PatternFill('solid', fgColor=hex_color)

    def _font(bold=False, size=10, color='000000', italic=False):
        return Font(name='Calibri', bold=bold, size=size, color=color, italic=italic)

    def _align(h='left', v='center', wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    def _border(style='thin'):
        s = Side(style=style)
        return Border(left=s, right=s, top=s, bottom=s)

    THIN  = _border('thin')
    THICK = _border('medium')

    CURRENCY_FMT = '₹#,##0.00'
    INT_FMT      = '#,##0'
    PCT_FMT      = '0.0"%"'

    # ── Workbook setup ─────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Night Audit Report'

    # A4 Portrait page setup
    ws.page_setup.paperSize   = ws.PAPERSIZE_A4
    ws.page_setup.orientation = ws.ORIENTATION_PORTRAIT
    ws.page_setup.fitToWidth  = 1
    ws.page_setup.fitToHeight = 0          # auto height (may span 2 pages)
    ws.page_setup.horizontalDpi = 300
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    # Narrow margins (in inches)
    ws.page_margins.left   = 0.55
    ws.page_margins.right  = 0.55
    ws.page_margins.top    = 0.75
    ws.page_margins.bottom = 0.75
    ws.page_margins.header = 0.3
    ws.page_margins.footer = 0.3

    # Print header/footer
    ws.oddHeader.center.text = f"&B{hotel_name}&B — Night Audit Report"
    ws.oddHeader.center.size = 9
    ws.oddFooter.left.text   = f"Confidential — For Internal Use Only"
    ws.oddFooter.center.text = f"Business Date: {audit_date.strftime('%d %b %Y')}"
    ws.oddFooter.right.text  = "Page &P of &N  |  Printed &D"
    ws.oddFooter.left.size = ws.oddFooter.center.size = ws.oddFooter.right.size = 8

    # Repeat header rows 1-8 on every printed page
    ws.print_title_rows = '1:8'

    # Column widths  A  B    C    D    E    F
    col_widths = {'A': 3, 'B': 32, 'C': 18, 'D': 4, 'E': 32, 'F': 18}
    for col, w in col_widths.items():
        ws.column_dimensions[col].width = w

    # Set print area A:F
    ws.print_area = 'A1:F200'

    # ── Helper: write a cell ───────────────────────────────────────────────
    def _c(row, col, value='', font=None, fill=None, alignment=None,
           border=None, number_format=None):
        cell = ws.cell(row=row, column=col, value=value)
        if font:        cell.font = font
        if fill:        cell.fill = fill
        if alignment:   cell.alignment = alignment
        if border:      cell.border = border
        if number_format: cell.number_format = number_format
        return cell

    def _merge(row, c1, c2, value='', font=None, fill=None,
               alignment=None, border=None):
        ws.merge_cells(start_row=row, start_column=c1,
                       end_row=row,   end_column=c2)
        cell = ws.cell(row=row, column=c1, value=value)
        if font:      cell.font = font
        if fill:      cell.fill = fill
        if alignment: cell.alignment = alignment
        # Apply border to every cell in merged range
        if border:
            for col in range(c1, c2 + 1):
                ws.cell(row=row, column=col).border = border
        return cell

    def _section_header(row, title, col_start=2, col_end=6, icon=''):
        _merge(row, col_start, col_end,
               value=f'  {icon}  {title}'.strip(),
               font=_font(bold=True, size=10, color=WHITE),
               fill=_fill(MID_BLUE),
               alignment=_align('left', 'center'),
               border=THICK)
        ws.row_dimensions[row].height = 16

    def _table_header(row, labels, cols):
        """labels: list of str, cols: list of int (1-based)"""
        for label, col in zip(labels, cols):
            _c(row, col, label,
               font=_font(bold=True, size=9, color='1A1A1A'),
               fill=_fill(LIGHT_BLUE),
               alignment=_align('center', 'center'),
               border=THIN)
        ws.row_dimensions[row].height = 14

    def _data_row(row, values, cols, formats=None, bold=False,
                  fill_hex=None, align_right_cols=None):
        align_right_cols = align_right_cols or []
        for i, (val, col) in enumerate(zip(values, cols)):
            fmt  = formats[i] if formats else None
            h    = 'right' if col in align_right_cols else 'left'
            cell = _c(row, col, val,
                      font=_font(bold=bold, size=9),
                      fill=_fill(fill_hex) if fill_hex else _fill(WHITE if row % 2 == 0 else PALE_BLUE),
                      alignment=_align(h, 'center'),
                      border=THIN,
                      number_format=fmt)
        ws.row_dimensions[row].height = 13

    def _total_row(row, values, cols, formats=None, grand=False):
        f_hex = GRAND_FILL if grand else TOTAL_FILL
        f_col = WHITE if grand else '1A1A1A'
        for i, (val, col) in enumerate(zip(values, cols)):
            fmt = formats[i] if formats else None
            _c(row, col, val,
               font=_font(bold=True, size=9, color=f_col),
               fill=_fill(f_hex),
               alignment=_align('right' if isinstance(val, (int, float)) else 'left', 'center'),
               border=THICK,
               number_format=fmt)
        ws.row_dimensions[row].height = 14

    def _blank(row, height=6):
        ws.row_dimensions[row].height = height

    # ══════════════════════════════════════════════════════════════════════
    # HOTEL HEADER  (rows 1-7)
    # ══════════════════════════════════════════════════════════════════════
    r = 1

    # Logo placeholder (B1:B3)
    ws.merge_cells(start_row=r, start_column=2, end_row=r+2, end_column=2)
    logo_cell = ws.cell(row=r, column=2, value='LOGO')
    logo_cell.font      = _font(bold=True, size=9, color='888888')
    logo_cell.fill      = _fill('E8EEF7')
    logo_cell.alignment = _align('center', 'center')
    logo_cell.border    = THIN

    # Hotel Name  (C1:F1)
    _merge(r, 3, 6, hotel_name,
           font=_font(bold=True, size=18, color=NAVY),
           fill=_fill(WHITE),
           alignment=_align('left', 'center'))
    ws.row_dimensions[r].height = 26; r += 1

    # Address (C2:F2)
    _merge(r, 3, 6, hotel_address or ' ',
           font=_font(size=9, color='444444'),
           alignment=_align('left', 'center'))
    ws.row_dimensions[r].height = 14; r += 1

    # GSTIN (C3:F3)
    _merge(r, 3, 6, f'GSTIN: {hotel_gstin}' if hotel_gstin else ' ',
           font=_font(size=8, color='666666'),
           alignment=_align('left', 'center'))
    ws.row_dimensions[r].height = 13; r += 1

    # Report Title banner (B4:F4)
    _merge(r, 2, 6, '  NIGHT AUDIT REPORT  —  CONSOLIDATED STATEMENT',
           font=_font(bold=True, size=13, color=WHITE),
           fill=_fill(NAVY),
           alignment=_align('center', 'center'),
           border=THICK)
    ws.row_dimensions[r].height = 22; r += 1

    # Meta row 1: Business Date | Audit Date | Status
    _c(r, 2, 'Business Date',  font=_font(bold=True, size=9), fill=_fill(PALE_GREY), border=THIN, alignment=_align('right'))
    _c(r, 3, audit_date.strftime('%d %B %Y'),
       font=_font(bold=True, size=10, color=MID_BLUE), fill=_fill(PALE_GREY), border=THIN)
    _c(r, 5, 'Audit Status',  font=_font(bold=True, size=9), fill=_fill(PALE_GREY), border=THIN, alignment=_align('right'))
    status_color = '1a7a3c' if hdr['audit_status'] == 'Completed' else 'a06000'
    _c(r, 6, hdr['audit_status'],
       font=_font(bold=True, size=10, color=status_color), fill=_fill(PALE_GREY), border=THIN)
    ws.row_dimensions[r].height = 14; r += 1

    # Meta row 2: Generated | Prepared By
    _c(r, 2, 'Generated',     font=_font(bold=True, size=9), fill=_fill(PALE_GREY), border=THIN, alignment=_align('right'))
    _c(r, 3, generated_at.strftime('%d %b %Y  %H:%M'),
       font=_font(size=9), fill=_fill(PALE_GREY), border=THIN)
    _c(r, 5, 'Prepared By',   font=_font(bold=True, size=9), fill=_fill(PALE_GREY), border=THIN, alignment=_align('right'))
    _c(r, 6, hdr.get('run_by') or '—',
       font=_font(size=9), fill=_fill(PALE_GREY), border=THIN)
    ws.row_dimensions[r].height = 14; r += 1

    _blank(r); r += 1     # row 8 — spacer

    ws.freeze_panes = f'B9'     # freeze header

    # ══════════════════════════════════════════════════════════════════════
    # LEFT COLUMN SECTIONS start at row 9
    # Two-column layout: cols B-C (left) │ cols E-F (right)
    # ══════════════════════════════════════════════════════════════════════

    # ── Occupancy Summary (LEFT) & Front Office Activity (RIGHT) ──────────
    left_start = r

    _section_header(r, 'OCCUPANCY SUMMARY', 2, 3, '📊'); _section_header(r, 'FRONT OFFICE ACTIVITY', 5, 6, '🛎️'); r += 1
    _table_header(r, ['Metric', 'Value'], [2, 3]); _table_header(r, ['Metric', 'Count'], [5, 6]); r += 1

    occ_left = [
        ('Total Rooms Available',    occ['total_rooms'],             INT_FMT,  False),
        ('Sellable Rooms',           occ['sellable_rooms'],          INT_FMT,  False),
        ('Rooms Sold (Occupied)',     occ['occupied'],                INT_FMT,  True),
        ('Occupancy %',              occ['occ_pct'] / 100,           '0.0%',   True),
        ('Vacant Rooms',             occ['vacant'],                  INT_FMT,  False),
        ('Dirty / Under Service',    occ['dirty'],                   INT_FMT,  False),
        ('Out of Order',             occ['out_of_order'],            INT_FMT,  False),
    ]
    fo_right = [
        ('Total Arrivals Expected',  res_rec['arrivals_today'],      INT_FMT,  False),
        ('Arrivals Checked In',      occ['new_arrivals_count'],      INT_FMT,  True),
        ('Departures Expected',      res_rec['departures_today'],    INT_FMT,  False),
        ('Departures Checked Out',   occ['checked_out_today_count'], INT_FMT,  True),
        ('No-Shows',                 res_rec['noshows_count'],       INT_FMT,  False),
        ('Cancellations Today',      res_rec['cancellations_today'], INT_FMT,  False),
        ('Stay-overs',               occ['stayovers'],               INT_FMT,  False),
    ]

    max_lr = max(len(occ_left), len(fo_right))
    for i in range(max_lr):
        bg = PALE_BLUE if r % 2 == 0 else WHITE
        if i < len(occ_left):
            lbl, val, fmt, bold = occ_left[i]
            _c(r, 2, lbl, font=_font(bold=bold, size=9), fill=_fill(bg), border=THIN, alignment=_align('left', 'center'))
            _c(r, 3, val, font=_font(bold=bold, size=9), fill=_fill(bg), border=THIN, alignment=_align('right', 'center'), number_format=fmt)
        if i < len(fo_right):
            lbl, val, fmt, bold = fo_right[i]
            _c(r, 5, lbl, font=_font(bold=bold, size=9), fill=_fill(bg), border=THIN, alignment=_align('left', 'center'))
            _c(r, 6, val, font=_font(bold=bold, size=9), fill=_fill(bg), border=THIN, alignment=_align('right', 'center'), number_format=fmt)
        ws.row_dimensions[r].height = 13; r += 1

    _blank(r); r += 1

    # ── KPI Metrics (LEFT) & Housekeeping Status (RIGHT) ──────────────────
    _section_header(r, 'KPI METRICS', 2, 3, '📈'); _section_header(r, 'HOUSEKEEPING STATUS', 5, 6, '🧹'); r += 1
    _table_header(r, ['KPI', 'Value'], [2, 3]); _table_header(r, ['Status', 'Rooms'], [5, 6]); r += 1

    kpi_left = [
        ('ADR (Avg Daily Rate)',          adr,     CURRENCY_FMT),
        ('RevPAR',                         revpar,  CURRENCY_FMT),
        ('ARR (Avg Room Rate)',            adr,     CURRENCY_FMT),
        ('GOP (Manual Entry)',             '—',     None),
    ]
    hk_right = [
        ('Vacant Clean',      hk_vacant_clean, INT_FMT),
        ('Vacant Dirty',      hk_vacant_dirty, INT_FMT),
        ('Occupied',          hk_occupied,     INT_FMT),
        ('Out of Order',      hk_oor,          INT_FMT),
        ('Total Rooms',       len(all_rooms),  INT_FMT),
    ]

    max_lr2 = max(len(kpi_left), len(hk_right))
    for i in range(max_lr2):
        bg = PALE_BLUE if r % 2 == 0 else WHITE
        if i < len(kpi_left):
            lbl, val, fmt = kpi_left[i]
            _c(r, 2, lbl, font=_font(size=9), fill=_fill(bg), border=THIN, alignment=_align('left'))
            _c(r, 3, val if isinstance(val, str) else val,
               font=_font(bold=True, size=10, color=MID_BLUE), fill=_fill(bg),
               border=THIN, alignment=_align('right'), number_format=fmt)
        if i < len(hk_right):
            lbl, val, fmt = hk_right[i]
            _c(r, 5, lbl, font=_font(size=9), fill=_fill(bg), border=THIN, alignment=_align('left'))
            _c(r, 6, val, font=_font(bold=True, size=9), fill=_fill(bg), border=THIN, alignment=_align('right'), number_format=fmt)
        ws.row_dimensions[r].height = 13; r += 1

    _blank(r); r += 1

    # ══════════════════════════════════════════════════════════════════════
    # FULL-WIDTH SECTIONS
    # ══════════════════════════════════════════════════════════════════════

    # ── Revenue Summary ────────────────────────────────────────────────────
    _section_header(r, 'REVENUE SUMMARY', 2, 6, '💰'); r += 1
    _table_header(r, ['Revenue Head', '', 'Amount (₹)', '', ''], [2, 3, 4, 5, 6]); r += 1

    # Merge label across B-E, value in F
    def _rev_row(label, value, fmt=CURRENCY_FMT, bold=False, fill_hex=None):
        nonlocal r
        bg = fill_hex or (PALE_BLUE if r % 2 == 0 else WHITE)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        _c(r, 2, label, font=_font(bold=bold, size=9), fill=_fill(bg), border=THIN, alignment=_align('left'))
        for col in [3, 4, 5]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        _c(r, 6, value, font=_font(bold=bold, size=9), fill=_fill(bg), border=THIN,
           alignment=_align('right'), number_format=fmt)
        ws.row_dimensions[r].height = 13; r += 1

    _rev_row('Room Revenue',           rev['room_revenue'])
    for cat, amt in rev['extra_by_category'].items():
        _rev_row(cat,                  amt)
    if not rev['extra_by_category']:
        _rev_row('F&B / Other Revenue', 0.0)
    _rev_row('Accrual Net Revenue (Pre-Tax)', rev['accrual_net'], bold=True, fill_hex=TOTAL_FILL)
    _rev_row('Taxes (GST etc.)',       rev['tax_amount'])
    if rev['discount_total'] > 0:
        _rev_row(f"Discounts / Rate Overrides", -rev['discount_total'], fill_hex=WARN_FILL)
    _rev_row('GROSS REVENUE (incl. Tax)', rev['gross_revenue'], bold=True, fill_hex=GRAND_FILL)
    # Fix: grand total row colour and font for merged cells
    for col in [2, 3, 4, 5, 6]:
        ws.cell(r - 1, col).font = _font(bold=True, size=10, color=WHITE)
        ws.cell(r - 1, col).fill = _fill(GRAND_FILL)

    _blank(r); r += 1

    # ── Payment Summary ────────────────────────────────────────────────────
    _section_header(r, 'PAYMENT SUMMARY', 2, 6, '🧾'); r += 1
    _table_header(r, ['Payment Mode', '', 'Transactions', 'Amount (₹)', ''], [2, 3, 4, 5, 6]); r += 1

    for mode, info in pay['by_mode'].items():
        bg = PALE_BLUE if r % 2 == 0 else WHITE
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        _c(r, 2, mode, font=_font(size=9), fill=_fill(bg), border=THIN, alignment=_align('left'))
        ws.cell(r, 3).border = THIN; ws.cell(r, 3).fill = _fill(bg)
        _c(r, 4, info['count'], font=_font(size=9), fill=_fill(bg), border=THIN,
           alignment=_align('right'), number_format=INT_FMT)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        _c(r, 5, info['amount'], font=_font(size=9), fill=_fill(bg), border=THIN,
           alignment=_align('right'), number_format=CURRENCY_FMT)
        ws.cell(r, 6).border = THIN; ws.cell(r, 6).fill = _fill(bg)
        ws.row_dimensions[r].height = 13; r += 1

    if not pay['by_mode']:
        bg = PALE_BLUE
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        _c(r, 2, 'No payments recorded', font=_font(italic=True, size=9, color='888888'),
           fill=_fill(bg), border=THIN, alignment=_align('center'))
        for col in [3, 4, 5, 6]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        ws.row_dimensions[r].height = 13; r += 1

    if pay['total_refunds'] > 0:
        bg = WARN_FILL
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        _c(r, 2, 'Voided / Refunds', font=_font(bold=True, size=9, color='900000'), fill=_fill(bg), border=THIN)
        for col in [3, 4]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        _c(r, 5, -pay['total_refunds'], font=_font(bold=True, color='900000'), fill=_fill(bg),
           border=THIN, alignment=_align('right'), number_format=CURRENCY_FMT)
        ws.cell(r, 6).border = THIN; ws.cell(r, 6).fill = _fill(bg)
        ws.row_dimensions[r].height = 13; r += 1

    # Net Collection total row
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
    _c(r, 2, 'NET COLLECTION', font=_font(bold=True, size=10, color=WHITE), fill=_fill(GRAND_FILL), border=THICK)
    for col in [3, 4]: ws.cell(r, col).border = THICK; ws.cell(r, col).fill = _fill(GRAND_FILL)
    ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
    _c(r, 5, pay['net_collection'], font=_font(bold=True, size=10, color=WHITE), fill=_fill(GRAND_FILL),
       border=THICK, alignment=_align('right'), number_format=CURRENCY_FMT)
    ws.cell(r, 6).border = THICK; ws.cell(r, 6).fill = _fill(GRAND_FILL)
    ws.row_dimensions[r].height = 15; r += 1

    _blank(r); r += 1

    # ── Accounts & Ledger Summary ──────────────────────────────────────────
    _section_header(r, 'ACCOUNTS & LEDGER SUMMARY', 2, 6, '📚'); r += 1
    _table_header(r, ['Account', '', 'Value', '', ''], [2, 3, 4, 5, 6]); r += 1

    accounts = [
        ('In-house Outstanding',       folio['in_house_outstanding'],       folio['in_house_outstanding'] > 0),
        ('Checkout Outstanding',        folio['checkout_outstanding_total'], folio['checkout_outstanding_total'] > 0),
        ('Open Folios (In-house)',       folio['open_folios_count'],         False),
        ('Closed Folios (Departed)',     folio['closed_folios_count'],       False),
        ('Total Outstanding Balance',   folio['total_outstanding'],         folio['total_outstanding'] > 0),
    ]
    for lbl, val, is_alert in accounts:
        bg = ERR_FILL if is_alert else (PALE_BLUE if r % 2 == 0 else WHITE)
        is_total = lbl.startswith('Total')
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        _c(r, 2, lbl, font=_font(bold=is_total, size=9), fill=_fill(bg), border=THIN)
        for col in [3, 4, 5]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        fmt = CURRENCY_FMT if isinstance(val, float) else INT_FMT
        _c(r, 6, val, font=_font(bold=is_total, size=9), fill=_fill(bg), border=THIN,
           alignment=_align('right'), number_format=fmt)
        ws.row_dimensions[r].height = 13; r += 1

    _blank(r); r += 1

    # ── Tax Snapshot ────────────────────────────────────────────────────────
    if tax_snap['has_data']:
        _section_header(r, 'TAX SNAPSHOT', 2, 6, '🧮'); r += 1
        _table_header(r, ['Tax Type', '', 'Taxable Amount (₹)', 'Tax Amount (₹)', 'Lines'], [2, 3, 4, 5, 6]); r += 1
        for key, t in tax_snap['by_rate'].items():
            bg = PALE_BLUE if r % 2 == 0 else WHITE
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
            _c(r, 2, key, font=_font(size=9), fill=_fill(bg), border=THIN)
            ws.cell(r, 3).border = THIN; ws.cell(r, 3).fill = _fill(bg)
            _c(r, 4, t['taxable'], font=_font(size=9), fill=_fill(bg), border=THIN,
               alignment=_align('right'), number_format=CURRENCY_FMT)
            _c(r, 5, t['tax'],     font=_font(size=9), fill=_fill(bg), border=THIN,
               alignment=_align('right'), number_format=CURRENCY_FMT)
            _c(r, 6, t['count'],   font=_font(size=9), fill=_fill(bg), border=THIN,
               alignment=_align('right'), number_format=INT_FMT)
            ws.row_dimensions[r].height = 13; r += 1
        # Total
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
        _c(r, 2, 'TOTAL TAX', font=_font(bold=True, color=WHITE), fill=_fill(GRAND_FILL), border=THICK)
        ws.cell(r, 3).border = THICK; ws.cell(r, 3).fill = _fill(GRAND_FILL)
        _c(r, 4, tax_snap['total_taxable'], font=_font(bold=True, color=WHITE), fill=_fill(GRAND_FILL),
           border=THICK, alignment=_align('right'), number_format=CURRENCY_FMT)
        _c(r, 5, tax_snap['total_tax'], font=_font(bold=True, color=WHITE), fill=_fill(GRAND_FILL),
           border=THICK, alignment=_align('right'), number_format=CURRENCY_FMT)
        _c(r, 6, tax_snap['total_lines'], font=_font(bold=True, color=WHITE), fill=_fill(GRAND_FILL),
           border=THICK, alignment=_align('right'), number_format=INT_FMT)
        ws.row_dimensions[r].height = 14; r += 1
        _blank(r); r += 1

    # ── Exceptions & Alerts ────────────────────────────────────────────────
    _section_header(r, 'EXCEPTIONS & ALERTS', 2, 6, '⚠️'); r += 1
    _table_header(r, ['Type', 'Severity', 'Detail', '', ''], [2, 3, 4, 5, 6]); r += 1

    all_exc = ([(e['type'], 'BLOCKER', e['detail'], ERR_FILL) for e in exc['blockers']] +
               [(w['type'], 'WARNING', w['detail'], WARN_FILL) for w in exc['warnings']])

    for exc_type, sev, detail, bg in all_exc:
        _c(r, 2, exc_type, font=_font(bold=(sev == 'BLOCKER'), size=9, color='900000' if sev == 'BLOCKER' else '7a5800'),
           fill=_fill(bg), border=THIN)
        _c(r, 3, sev, font=_font(bold=True, size=9, color='900000' if sev == 'BLOCKER' else '7a5800'),
           fill=_fill(bg), border=THIN, alignment=_align('center'))
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
        _c(r, 4, detail, font=_font(size=9), fill=_fill(bg), border=THIN, alignment=_align('left', wrap=True))
        for col in [5, 6]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        ws.row_dimensions[r].height = 15; r += 1

    if not all_exc:
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        _c(r, 2, '✔  No Exceptions — Audit is Clean', font=_font(bold=True, size=9, color='1a7a3c'),
           fill=_fill(GREEN_FILL), border=THIN, alignment=_align('center'))
        for col in [3, 4, 5, 6]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(GREEN_FILL)
        ws.row_dimensions[r].height = 13; r += 1

    _blank(r); r += 1

    # ── Audit Reconciliation Control ───────────────────────────────────────
    _section_header(r, 'AUDIT RECONCILIATION CONTROL', 2, 6, '⚖️'); r += 1
    _table_header(r, ['Metric', '', 'Amount (₹)', '', ''], [2, 3, 4, 5, 6]); r += 1

    ctrl_rows = [
        ('Total Posted Revenue',     ctrl['total_posted_revenue'],       False),
        ('Total Collected',          ctrl['total_collected'],             False),
        ('Total Outstanding',        ctrl['total_outstanding'],           False),
        ('Reconciliation Difference',ctrl['reconciliation_difference'],   abs(ctrl['reconciliation_difference']) > 1),
    ]
    for lbl, val, alert in ctrl_rows:
        bg = ERR_FILL if alert else (PALE_BLUE if r % 2 == 0 else WHITE)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        _c(r, 2, lbl, font=_font(size=9), fill=_fill(bg), border=THIN)
        for col in [3, 4, 5]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        _c(r, 6, val, font=_font(bold=alert, size=9), fill=_fill(bg), border=THIN,
           alignment=_align('right'), number_format=CURRENCY_FMT)
        ws.row_dimensions[r].height = 13; r += 1

    can_close_color = '1a7a3c' if ctrl['can_close'] else '900000'
    can_close_text  = '✔  YES — All checks passed' if ctrl['can_close'] else f"✘  NO — {', '.join(ctrl['close_reasons'])}"
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    _c(r, 2, 'Can Audit Close?', font=_font(bold=True, size=9, color=WHITE), fill=_fill(NAVY), border=THICK)
    ws.cell(r, 3).fill = _fill(NAVY); ws.cell(r, 3).border = THICK
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
    _c(r, 4, can_close_text, font=_font(bold=True, size=10, color=can_close_color),
       fill=_fill(GREEN_FILL if ctrl['can_close'] else ERR_FILL), border=THICK, alignment=_align('center'))
    for col in [5, 6]: ws.cell(r, col).fill = _fill(GREEN_FILL if ctrl['can_close'] else ERR_FILL); ws.cell(r, col).border = THICK
    ws.row_dimensions[r].height = 15; r += 1

    _blank(r); r += 1

    # ── Forecast Snapshot (Next Day) ───────────────────────────────────────
    _section_header(r, f'FORECAST — {tomorrow.strftime("%d %B %Y")}  (Next Day)', 2, 6, '📅'); r += 1
    _table_header(r, ['Metric', '', 'Value', '', ''], [2, 3, 4, 5, 6]); r += 1

    forecast_rows = [
        ('Expected Arrivals',          tom_arr,        INT_FMT),
        ('Expected Departures',         tom_dep,        INT_FMT),
        ('Forecast Occupied Rooms',     forecast_occ,   INT_FMT),
        ('Forecast Occupancy %',        forecast_pct / 100, '0.0%'),
        ('Sellable Rooms',              occ['sellable_rooms'], INT_FMT),
    ]
    for lbl, val, fmt in forecast_rows:
        bg = PALE_BLUE if r % 2 == 0 else WHITE
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        _c(r, 2, lbl, font=_font(size=9), fill=_fill(bg), border=THIN)
        for col in [3, 4, 5]: ws.cell(r, col).border = THIN; ws.cell(r, col).fill = _fill(bg)
        _c(r, 6, val, font=_font(bold=True, size=9, color=MID_BLUE), fill=_fill(bg),
           border=THIN, alignment=_align('right'), number_format=fmt)
        ws.row_dimensions[r].height = 13; r += 1

    _blank(r); r += 1

    # ── Notes & Remarks ────────────────────────────────────────────────────
    _section_header(r, 'NOTES & REMARKS', 2, 6, '📝'); r += 1
    for _ in range(5):
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        _c(r, 2, '', fill=_fill(WHITE), border=THIN, alignment=_align('left'))
        for col in [3, 4, 5, 6]: ws.cell(r, col).border = THIN
        ws.row_dimensions[r].height = 18; r += 1

    _blank(r, 8); r += 1

    # ── Signatures ─────────────────────────────────────────────────────────
    _section_header(r, 'AUTHORISATION & SIGNATURES', 2, 6, '✍️'); r += 1

    sig_labels = ['Night Auditor', 'Duty Manager', 'General Manager']
    sig_cols   = [(2, 3), (4, 4), (5, 6)]
    for lbl, (c1, c2) in zip(sig_labels, sig_cols):
        if c1 != c2:
            ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        _c(r, c1, lbl, font=_font(bold=True, size=9, color=NAVY),
           fill=_fill(LIGHT_BLUE), border=THIN, alignment=_align('center'))
        if c1 != c2:
            ws.cell(r, c2).border = THIN; ws.cell(r, c2).fill = _fill(LIGHT_BLUE)
    ws.row_dimensions[r].height = 14; r += 1

    # Signature lines
    for label in ['Signature:', 'Name:', 'Date / Time:']:
        for c1, c2 in sig_cols:
            if c1 != c2:
                ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
            _c(r, c1, label if label != 'Signature:' else '',
               font=_font(size=8, color='444444' if label != 'Signature:' else WHITE),
               fill=_fill(WHITE),
               border=Border(bottom=Side(style='thin')),
               alignment=_align('left', 'bottom'))
            if c1 != c2:
                ws.cell(r, c2).border = Border(bottom=Side(style='thin'))
        ws.row_dimensions[r].height = 20; r += 1

    # ══════════════════════════════════════════════════════════════════════
    # DETAIL SHEETS (separate tabs for drilldown)
    # ══════════════════════════════════════════════════════════════════════
    hdr_fill_d = PatternFill('solid', fgColor=NAVY)
    hdr_font_d = Font(name='Calibri', color=WHITE, bold=True, size=9)

    def _detail_sheet(title, headers, rows, warn_col=None):
        wsd = wb.create_sheet(title[:31])
        wsd.page_setup.paperSize = ws.PAPERSIZE_A4
        wsd.page_setup.orientation = ws.ORIENTATION_PORTRAIT
        wsd.page_setup.fitToWidth = 1
        wsd.sheet_properties.pageSetUpPr.fitToPage = True
        # Title
        wsd.append([title])
        wsd.cell(1, 1).font = Font(name='Calibri', bold=True, size=12, color=NAVY)
        wsd.append([f'Business Date: {audit_date.strftime("%d %b %Y")}   Generated: {generated_at.strftime("%d %b %Y %H:%M")}'])
        wsd.append([])
        # Headers
        hr = 4
        wsd.append(headers)
        for ci, h in enumerate(headers, 1):
            c = wsd.cell(hr, ci)
            c.fill = hdr_fill_d; c.font = hdr_font_d
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                              top=Side(style='thin'), bottom=Side(style='thin'))
        wsd.row_dimensions[hr].height = 15
        # Data
        for ri, row in enumerate(rows, hr + 1):
            bg_hex = ERR_FILL if warn_col and len(row) > warn_col and row[warn_col] == 'BLOCKER' else (
                     WARN_FILL if warn_col and len(row) > warn_col and row[warn_col] == 'WARNING' else
                     ('EEF4FC' if ri % 2 == 0 else 'FFFFFF'))
            wsd.append(row)
            for ci in range(1, len(row) + 1):
                c = wsd.cell(ri, ci)
                c.fill = PatternFill('solid', fgColor=bg_hex)
                c.font = Font(name='Calibri', size=9)
                c.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                  top=Side(style='thin'), bottom=Side(style='thin'))
                if isinstance(c.value, float):
                    c.number_format = '₹#,##0.00'
                    c.alignment = Alignment(horizontal='right')
            wsd.row_dimensions[ri].height = 13
        for col in wsd.columns:
            max_len = max((len(str(c.value)) for c in col if c.value), default=8)
            wsd.column_dimensions[col[0].column_letter].width = min(max_len + 4, 45)
        return wsd

    # Detail: Payments by mode
    _detail_sheet(
        'Payments Detail',
        ['Payment Mode', 'Amount (₹)', 'Transactions'],
        [[m, round(v['amount'], 2), v['count']] for m, v in pay['by_mode'].items()] +
        [['', '', ''], ['Total Collected', round(pay['total_collected'], 2), ''],
         ['Voided / Refunds', round(pay['total_refunds'], 2), ''],
         ['Net Collection', round(pay['net_collection'], 2), '']]
    )

    # Detail: Exceptions
    _detail_sheet(
        'Exceptions Detail',
        ['Type', 'Severity', 'Detail'],
        [[e['type'], 'BLOCKER', e['detail']] for e in exc['blockers']] +
        [[w['type'], 'WARNING', w['detail']] for w in exc['warnings']],
        warn_col=1
    )

    # Detail: Outstanding Folios
    folio_rows_d = []
    for f in folio['checkout_outstanding_list']:
        rr = f['reservation']
        folio_rows_d.append([
            rr.booking_reference,
            rr.guest.name if rr.guest else '',
            rr.room.room_number if rr.room else '',
            round(f['total'], 2), round(f['paid'], 2), round(f['balance'], 2)
        ])
    _detail_sheet(
        'Outstanding Folios',
        ['Booking Ref', 'Guest', 'Room', 'Total (₹)', 'Paid (₹)', 'Balance (₹)'],
        folio_rows_d
    )

    # Detail: Room Charge Audit
    rc_rows_d = []
    for rr in rc['missing_rent']:
        rc_rows_d.append([rr.booking_reference, rr.guest.name if rr.guest else '',
                          rr.room.room_number if rr.room else '', 'MISSING', 0.0, ''])
    for item in rc['incorrect_tariff']:
        rr = item['reservation']
        rc_rows_d.append([rr.booking_reference, rr.guest.name if rr.guest else '',
                          rr.room.room_number if rr.room else '', 'LOW RATE',
                          round(item['actual_rate'], 2), f"{item['variance_pct']}% below base"])
    _detail_sheet(
        'Room Charge Audit',
        ['Booking Ref', 'Guest', 'Room', 'Issue', 'Rate (₹)', 'Note'],
        rc_rows_d
    )

    # ══════════════════════════════════════════════════════════════════════
    # Save & return
    # ══════════════════════════════════════════════════════════════════════
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        download_name=f'night_audit_{audit_date.isoformat()}.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


# ===========================================================================
# Overstay Control Report
# ===========================================================================

@reports_bp.route('/overstay-control')
def overstay_control():
    """
    Management report for all hourly overstay actions (charges, waivers, extensions).
    Data source: audit_logs filtered to overstay_charged / overstay_waived / hourly_extended.
    Accessible to Manager, Admin, Accountant.
    """
    if not _require_accountant():
        from flask import abort
        abort(403)

    from app.models import AuditLog, User as _User

    today         = get_business_date()
    from_str      = request.args.get('from',   today.replace(day=1).isoformat())
    to_str        = request.args.get('to',     today.isoformat())
    action_filter = request.args.get('action', 'all').strip()
    room_filter   = request.args.get('room',   '').strip()
    guest_filter  = request.args.get('q',      '').strip()
    fmt           = request.args.get('format', 'html')

    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = to_date = today

    OVERSTAY_ACTIONS = ('overstay_charged', 'overstay_waived', 'hourly_extended')

    q = (db.session.query(AuditLog, Reservation, Room, Guest, _User)
         .filter(AuditLog.entity_type == 'Reservation',
                 AuditLog.action.in_(OVERSTAY_ACTIONS),
                 func.date(AuditLog.timestamp) >= from_date,
                 func.date(AuditLog.timestamp) <= to_date)
         .join(Reservation, AuditLog.entity_id == Reservation.id)
         .outerjoin(Room,  Reservation.room_id  == Room.id)
         .outerjoin(Guest, Reservation.guest_id == Guest.id)
         .outerjoin(_User, AuditLog.staff_user_id == _User.id))

    if action_filter != 'all':
        _action_map = {
            'charge': 'overstay_charged',
            'waive':  'overstay_waived',
            'extend': 'hourly_extended',
        }
        _mapped = _action_map.get(action_filter)
        if _mapped:
            q = q.filter(AuditLog.action == _mapped)

    if room_filter:
        q = q.filter(Room.room_number.ilike(f'%{room_filter}%'))

    if guest_filter:
        _like = f'%{guest_filter}%'
        q = q.filter(db.or_(Guest.name.ilike(_like), Guest.phone.ilike(_like)))

    raw = q.order_by(AuditLog.timestamp.desc()).all()

    # ── GST slab from rate_per_night (India hotel GST per Notification 11/2017) ──
    def _gst_pct(rate):
        r = float(rate or 0)
        if r <= 1000: return 0
        if r <= 7500: return 12
        return 18

    # ── Build display rows ────────────────────────────────────────────────────
    rows = []
    total_charge_excl = 0.0
    total_gst_amount  = 0.0
    total_waived_excl = 0.0
    charge_count = waive_count = extend_count = 0

    for log, res, room, guest, user in raw:
        state     = log.after_state  or {}
        pre_state = log.before_state or {}
        action    = log.action

        gst_pct     = _gst_pct(res.rate_per_night) if res else 0
        charge_excl = 0.0
        gst_amt     = 0.0
        total_amt   = 0.0
        waive_reason = ''
        hourly_rate  = float(state.get('hourly_rate',     0))
        overdue_min  = state.get('overdue_minutes',        0)
        bill_hours   = state.get('billable_hours',         0)
        billed_from  = state.get('billed_from',           '')
        billed_until = state.get('billed_until',          '')
        action_label = {'overstay_charged': 'Charge',
                        'overstay_waived':  'Waive',
                        'hourly_extended':  'Extend'}.get(action, action)

        if action == 'overstay_charged':
            charge_excl        = float(state.get('charge_excl_gst', 0))
            gst_amt            = round(charge_excl * gst_pct / 100, 2)
            total_amt          = round(charge_excl + gst_amt, 2)
            total_charge_excl += charge_excl
            total_gst_amount  += gst_amt
            charge_count      += 1
        elif action == 'overstay_waived':
            charge_excl        = float(state.get('waived_amount', 0))
            gst_amt            = round(charge_excl * gst_pct / 100, 2)
            total_amt          = round(charge_excl + gst_amt, 2)
            waive_reason       = state.get('waive_reason', '')
            total_waived_excl += charge_excl
            waive_count       += 1
        elif action == 'hourly_extended':
            extend_count += 1
            # For extends: billed_from = old checkout, billed_until = new checkout
            old_dep  = pre_state.get('departure_date', '')
            old_time = pre_state.get('checkout_time',  '')
            new_dep  = state.get('departure_date',  '')
            new_time = state.get('checkout_time',   '')
            billed_from  = f'{old_dep} {old_time}'.strip() if old_dep else ''
            billed_until = f'{new_dep} {new_time}'.strip() if new_dep else ''

        planned_co = ''
        if res:
            planned_co = str(res.departure_date or '')
            if res.checkout_time:
                planned_co += ' ' + res.checkout_time

        rows.append({
            'timestamp':    log.timestamp,
            'res_id':       log.entity_id,
            'booking_ref':  res.booking_reference if res else '',
            'room_number':  room.room_number if room else '—',
            'guest_name':   guest.name  if guest else '—',
            'guest_phone':  guest.phone if guest else '',
            'booking_type': res.booking_type if res else '',
            'planned_co':   planned_co,
            'action':       action,
            'action_label': action_label,
            'billed_from':  billed_from,
            'billed_until': billed_until,
            'overdue_min':  overdue_min,
            'bill_hours':   bill_hours,
            'hourly_rate':  hourly_rate,
            'charge_excl':  charge_excl,
            'gst_pct':      gst_pct,
            'gst_amt':      gst_amt,
            'total_amt':    total_amt,
            'waive_reason': waive_reason,
            'actioned_by':  user.full_name if user else '—',
            'actioned_role': user.role if user else '',
        })

    summary = {
        'total_charge_excl': round(total_charge_excl, 2),
        'total_gst':         round(total_gst_amount,  2),
        'total_charge_incl': round(total_charge_excl + total_gst_amount, 2),
        'total_waived_excl': round(total_waived_excl, 2),
        'charge_count':      charge_count,
        'waive_count':       waive_count,
        'extend_count':      extend_count,
        'total_records':     len(rows),
    }

    if fmt == 'excel':
        headers = [
            'Date / Time', 'Res ID', 'Booking Ref', 'Room', 'Guest Name', 'Guest Phone',
            'Booking Type', 'Planned Checkout', 'Action', 'Billed From', 'Billed Until',
            'Overdue Min', 'Billable Hrs', 'Hourly Rate (₹)',
            'Charge Excl GST (₹)', 'GST %', 'GST Amount (₹)', 'Total (₹)',
            'Waive Reason', 'Actioned By',
        ]
        excel_rows = []
        for r in rows:
            excel_rows.append([
                r['timestamp'].strftime('%d %b %Y %H:%M') if r['timestamp'] else '',
                r['res_id'],
                r['booking_ref'] or '',
                r['room_number'],
                r['guest_name'],
                r['guest_phone'],
                r['booking_type'],
                r['planned_co'],
                r['action_label'],
                r['billed_from'],
                r['billed_until'],
                r['overdue_min'],
                r['bill_hours'],
                r['hourly_rate'],
                r['charge_excl'],
                r['gst_pct'],
                r['gst_amt'],
                r['total_amt'],
                r['waive_reason'],
                r['actioned_by'],
            ])
        excel_rows += [
            [],
            ['SUMMARY'],
            ['Total Overstay Charges (excl. GST)', '', '', '', '',
             '', '', '', '', '', '', '', '', '', summary['total_charge_excl']],
            ['GST on Charges', '', '', '', '', '', '', '', '', '', '', '', '', '',
             '', '', summary['total_gst']],
            ['Total Charges (incl. GST)', '', '', '', '', '', '', '', '', '', '', '', '', '',
             '', '', '', summary['total_charge_incl']],
            ['Total Waived (excl. GST)', '', '', '', '', '', '', '', '', '', '', '', '', '',
             summary['total_waived_excl']],
            ['Charge Actions', summary['charge_count']],
            ['Waive Actions',  summary['waive_count']],
            ['Extend Actions', summary['extend_count']],
        ]
        return _excel_response(
            f'overstay_control_{from_str}_{to_str}.xlsx',
            headers, excel_rows,
            f'Overstay Control Report — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'
        )

    return render_template(
        'reports/overstay_control.html',
        rows=rows, summary=summary,
        from_date=from_date, to_date=to_date,
        action_filter=action_filter,
        room_filter=room_filter,
        guest_filter=guest_filter,
    )


# ---------------------------------------------------------------------------
# Room Revenue Report
# ---------------------------------------------------------------------------

def _room_revenue_data(from_date, to_date, rt_filter=''):
    """
    Compute all six sections of the Room Revenue Report for [from_date, to_date].
    Returns a dict: summary, room_rows, date_rows, rt_rows, src_rows, discount_rows.

    Revenue attribution: nights that fall within the requested date window.
    Discounts are prorated by (nights_in_window / total_stay_nights).
    """
    num_days = (to_date - from_date).days + 1
    total_rooms = Room.query.count()

    # Canonical occupancy denominator: sellable rooms, NOT the raw
    # inventory count. occupancy_engine is the single source of truth;
    # Room.query.count() includes OOO/maintenance rooms that can never
    # be sold and must not inflate the room-night denominator.
    from app.occupancy_engine import (
        occupied_room_nights as _engine_room_nights,
        sellable_rooms as _engine_sellable_rooms,
    )
    sellable_rooms_count = _engine_sellable_rooms()
    available_room_nights = sellable_rooms_count * num_days

    # All reservations (CheckedOut + CheckedIn) that overlap the window
    reservations = (Reservation.query
                    .filter(
                        Reservation.status.in_(['CheckedOut', 'CheckedIn']),
                        Reservation.arrival_date   < to_date + timedelta(days=1),
                        Reservation.departure_date > from_date,
                    )
                    .all())

    if rt_filter:
        reservations = [r for r in reservations
                        if r.room_type and r.room_type.name == rt_filter]

    # ── Per-reservation helpers ──────────────────────────────────────────────
    def _nights(r):
        start = max(r.arrival_date, from_date)
        end   = min(r.departure_date, to_date + timedelta(days=1))
        return max(0, (end - start).days)

    def _revenue(r):
        return float(r.rate_per_night) * _nights(r)

    def _discount(r):
        total_nights = (r.departure_date - r.arrival_date).days
        if total_nights <= 0:
            return 0.0
        return float(r.discount_amount or 0) * (_nights(r) / total_nights)

    # ── Summary KPIs ─────────────────────────────────────────────────────────
    # Room-nights come from the canonical engine: distinct (room, night)
    # pairs, bridge-aware, deduped — never a raw per-reservation sum that
    # can double-count a room claimed by both room_id and a bridge row.
    # The engine has no room-type filter; when rt_filter is active the
    # figure must be type-scoped, so the filtered set is summed for that
    # case only.
    if rt_filter:
        occupied_room_nights = sum(_nights(r) for r in reservations)
    else:
        occupied_room_nights = _engine_room_nights(from_date, to_date)
    total_revenue        = sum(_revenue(r)  for r in reservations)
    discount_total       = sum(_discount(r) for r in reservations)
    net_revenue          = total_revenue - discount_total
    occupancy_pct        = (occupied_room_nights / available_room_nights * 100) if available_room_nights else 0.0
    arr                  = (total_revenue / occupied_room_nights)    if occupied_room_nights    else 0.0
    revpar               = (total_revenue / available_room_nights)   if available_room_nights   else 0.0

    summary = {
        'total_rooms':           total_rooms,
        'num_days':              num_days,
        'available_room_nights': available_room_nights,
        'occupied_room_nights':  occupied_room_nights,
        'occupancy_pct':         round(occupancy_pct, 1),
        'total_revenue':         round(total_revenue, 2),
        'net_revenue':           round(net_revenue, 2),
        'arr':                   round(arr, 2),
        'revpar':                round(revpar, 2),
        'discount_total':        round(discount_total, 2),
    }

    # ── Room-wise ─────────────────────────────────────────────────────────────
    # v2.2.15 — row-level occupancy dedupe. `nights` is tracked as a
    # DISTINCT set of calendar dates per room, never a raw per-reservation
    # sum. A physical room can be sold at most one night per calendar
    # night; summing _nights(r) across overlapping reservations (a
    # double-booked room, or the aggregated 'Unassigned' bucket) produced
    # nights_sold > num_days and occupancy_pct > 100% (the observed
    # "2 nights => 200%"). The distinct-night set bounds the figure to
    # its true basis with no clamp.
    room_map = {}
    for r in reservations:
        room_no   = r.room.room_number if r.room else 'Unassigned'
        room_type = r.room_type.name   if r.room_type else '—'
        if room_no not in room_map:
            room_map[room_no] = {'room_no': room_no, 'room_type': room_type,
                                 'nights': set(), 'total_revenue': 0.0, 'discount': 0.0}
        n   = max(r.arrival_date, from_date)
        end = min(r.departure_date, to_date + timedelta(days=1))
        while n < end:
            room_map[room_no]['nights'].add(n)
            n += timedelta(days=1)
        room_map[room_no]['total_revenue']  += _revenue(r)
        room_map[room_no]['discount']       += _discount(r)

    room_rows = []
    for room_no in sorted(room_map):
        d      = room_map[room_no]
        nights = len(d['nights'])
        rev    = d['total_revenue']
        disc   = d['discount']
        # 'Unassigned' is a pseudo-room aggregating every roomless
        # reservation; a utilisation percentage for it is meaningless, so
        # it is surfaced as None (rendered '—') rather than a misleading
        # figure. nights_sold for it remains a true distinct-night count.
        is_unassigned = (room_no == 'Unassigned')
        room_rows.append({
            'room_no':       room_no,
            'room_type':     d['room_type'],
            'nights_sold':   nights,
            'occupancy_pct': (None if is_unassigned
                              else (round(nights / num_days * 100, 1) if num_days else 0)),
            'total_revenue': round(rev,  2),
            'avg_rate':      round(rev / nights, 2) if nights else 0,
            'discount':      round(disc, 2),
            'net_revenue':   round(rev - disc, 2),
        })

    # ── Date-wise ─────────────────────────────────────────────────────────────
    date_map = {from_date + timedelta(days=i): {'rooms_sold': 0, 'revenue': 0.0}
                for i in range(num_days)}

    for r in reservations:
        start = max(r.arrival_date, from_date)
        end   = min(r.departure_date, to_date + timedelta(days=1))
        d     = start
        while d < end:
            date_map[d]['rooms_sold'] += 1
            date_map[d]['revenue']    += float(r.rate_per_night)
            d += timedelta(days=1)

    date_rows = []
    for d in sorted(date_map):
        rooms   = date_map[d]['rooms_sold']
        rev     = date_map[d]['revenue']
        date_rows.append({
            'date':       d,
            'rooms_sold': rooms,
            'revenue':    round(rev, 2),
            'arr':        round(rev / rooms,             2) if rooms                else 0,
            # RevPAR denominator is sellable rooms (KPI Phase 1, Step 4),
            # never the raw inventory count — total_rooms includes OOO /
            # maintenance rooms that can never earn revenue.
            'revpar':     round(rev / sellable_rooms_count, 2) if sellable_rooms_count else 0,
        })

    # ── Room-type performance ─────────────────────────────────────────────────
    # v2.2.15 — same distinct-night dedupe as the room-wise section, keyed
    # by (room, night) pairs so two reservations colliding on the same
    # room+night count once. Reservations with no room linkage key on
    # their own id so each still contributes its nights without a false
    # collision.
    all_rt   = RoomType.query.order_by(RoomType.name).all()
    rt_map   = {}
    rt_counts = {}
    for rt in all_rt:
        cnt = Room.query.filter_by(room_type_id=rt.id).count()
        rt_counts[rt.name] = cnt
        rt_map[rt.name] = {'room_type': rt.name, 'rooms_available': cnt * num_days,
                           'nights': set(), 'revenue': 0.0}

    for r in reservations:
        rt_name = r.room_type.name if r.room_type else 'Unknown'
        if rt_name not in rt_map:
            rt_map[rt_name] = {'room_type': rt_name, 'rooms_available': 0,
                               'nights': set(), 'revenue': 0.0}
        room_key = r.room_id if r.room_id is not None else ('res', r.id)
        n   = max(r.arrival_date, from_date)
        end = min(r.departure_date, to_date + timedelta(days=1))
        while n < end:
            rt_map[rt_name]['nights'].add((room_key, n))
            n += timedelta(days=1)
        rt_map[rt_name]['revenue']     += _revenue(r)

    rt_rows = []
    for rt_name in sorted(rt_map):
        d      = rt_map[rt_name]
        nights = len(d['nights'])
        rev    = d['revenue']
        avail  = d['rooms_available']
        rt_rows.append({
            'room_type':     rt_name,
            'rooms_available': avail,
            'nights_sold':   nights,
            'occupancy_pct': round(nights / avail * 100, 1) if avail else 0,
            'revenue':       round(rev,  2),
            'avg_rate':      round(rev / nights, 2) if nights else 0,
        })

    # ── Source-wise ───────────────────────────────────────────────────────────
    src_map = {}
    for r in reservations:
        src = r.source or 'Walk-in'
        if src not in src_map:
            src_map[src] = {'source': src, 'nights_sold': 0, 'revenue': 0.0}
        src_map[src]['nights_sold'] += _nights(r)
        src_map[src]['revenue']     += _revenue(r)

    src_rows = sorted([
        {'source':      s,
         'nights_sold': d['nights_sold'],
         'revenue':     round(d['revenue'], 2),
         'avg_rate':    round(d['revenue'] / d['nights_sold'], 2) if d['nights_sold'] else 0}
        for s, d in src_map.items()
    ], key=lambda x: x['revenue'], reverse=True)

    # ── Discount audit ────────────────────────────────────────────────────────
    discount_rows = []
    for r in reservations:
        if float(r.discount_amount or 0) <= 0:
            continue
        nights = _nights(r)
        total_nights = (r.departure_date - r.arrival_date).days
        # Prorated discount for nights in window
        disc_window = _discount(r)
        discount_rows.append({
            'room_no':          r.room.room_number if r.room else '—',
            'guest_name':       r.guest.name        if r.guest else '—',
            'arrival':          r.arrival_date,
            'departure':        r.departure_date,
            'nights_in_window': nights,
            'original_tariff':  round(float(r.standard_tariff or r.rate_per_night), 2),
            'discount_total':   round(float(r.discount_amount), 2),
            'discount_window':  round(disc_window, 2),
            'final_rate':       round(float(r.rate_per_night), 2),
            'discount_reason':  r.discount_reason or '—',
            'approved_by':      r.discount_authorized_by or '—',
        })

    return dict(summary=summary, room_rows=room_rows, date_rows=date_rows,
                rt_rows=rt_rows, src_rows=src_rows, discount_rows=discount_rows,
                all_rt_names=[rt.name for rt in all_rt])


def _room_revenue_excel(data, from_date, to_date):
    """Multi-sheet Excel workbook for Room Revenue Report."""
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.page import PageMargins
    except ImportError:
        return Response('openpyxl not installed.', status=500)

    wb = openpyxl.Workbook()
    period   = f'{from_date.strftime("%d %b %Y")} — {to_date.strftime("%d %b %Y")}'
    gentime  = datetime.now().strftime('%d %b %Y %H:%M')

    HDR_FILL  = PatternFill('solid', fgColor='1F4E79')
    HDR_FONT  = Font(color='FFFFFF', bold=True)
    TTL_FONT  = Font(bold=True, size=12)
    SUMM_FILL = PatternFill('solid', fgColor='E8F0FE')
    THIN      = Side(style='thin', color='BBBBBB')
    BORDER    = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

    def _make_sheet(name, headers, rows, title=''):
        ws = wb.create_sheet(title=name[:31])
        ws.page_setup.paperSize   = ws.PAPERSIZE_A4
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.fitToPage   = True
        ws.page_setup.fitToWidth  = 1
        ws.page_setup.fitToHeight = 0
        ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        if title:
            ws.append([title]);         ws.cell(ws.max_row, 1).font = TTL_FONT
            ws.append([f'Period: {period}'])
            ws.append([f'Generated: {gentime}'])
            ws.append([])
        hr = ws.max_row + 1
        ws.append(headers)
        for ci in range(1, len(headers) + 1):
            c = ws.cell(hr, ci)
            c.fill = HDR_FILL; c.font = HDR_FONT
            c.alignment = Alignment(horizontal='center')
            c.border = BORDER
        for row in rows:
            ws.append(row)
            for ci in range(1, len(headers) + 1):
                ws.cell(ws.max_row, ci).border = BORDER
        for ci in range(1, len(headers) + 1):
            ml = max((len(str(ws.cell(r, ci).value or ''))
                      for r in range(1, ws.max_row + 1)), default=10)
            ws.column_dimensions[get_column_letter(ci)].width = min(ml + 4, 38)
        return ws

    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']

    s = data['summary']

    # Sheet 1 — Summary KPIs
    _make_sheet('Summary', ['Metric', 'Value'], [
        ['Total Rooms',              s['total_rooms']],
        ['Report Days',              s['num_days']],
        ['Available Room Nights',    s['available_room_nights']],
        ['Room Nights Sold',         s['occupied_room_nights']],
        ['Utilisation %',            f"{s['occupancy_pct']}%"],
        ['Total Revenue (₹)',        s['total_revenue']],
        ['Discount Total (₹)',       s['discount_total']],
        ['Net Revenue (₹)',          s['net_revenue']],
        ['ADR — Avg Daily Rate (₹)', s['arr']],
        ['RevPAR (₹)',               s['revpar']],
    ], 'Room Revenue Report — Summary')

    # Sheet 2 — Room-wise
    _make_sheet('Room-wise', [
        'Room No', 'Room Type', 'Nights Sold', 'Utilisation %',
        'Total Revenue (₹)', 'Avg Rate (₹)', 'Discount (₹)', 'Net Revenue (₹)'
    ], [
        [r['room_no'], r['room_type'], r['nights_sold'],
         ('—' if r['occupancy_pct'] is None else f"{r['occupancy_pct']}%"),
         r['total_revenue'], r['avg_rate'], r['discount'], r['net_revenue']]
        for r in data['room_rows']
    ], 'Room-wise Performance')

    # Sheet 3 — Date-wise
    _make_sheet('Date-wise', ['Date', 'Rooms Sold', 'Revenue (₹)', 'ADR (₹)', 'RevPAR (₹)'], [
        [r['date'].strftime('%d %b %Y'), r['rooms_sold'], r['revenue'], r['arr'], r['revpar']]
        for r in data['date_rows']
    ], 'Daily Revenue Breakdown')

    # Sheet 4 — Room Type
    _make_sheet('Room Type', [
        'Room Type', 'Available Nights', 'Nights Sold', 'Utilisation %', 'Revenue (₹)', 'Avg Rate (₹)'
    ], [
        [r['room_type'], r['rooms_available'], r['nights_sold'], f"{r['occupancy_pct']}%",
         r['revenue'], r['avg_rate']]
        for r in data['rt_rows']
    ], 'Room Type Performance')

    # Sheet 5 — Source-wise
    _make_sheet('Source-wise', ['Source', 'Nights Sold', 'Revenue (₹)', 'Avg Rate (₹)'], [
        [r['source'], r['nights_sold'], r['revenue'], r['avg_rate']]
        for r in data['src_rows']
    ], 'Booking Source Analysis')

    # Sheet 6 — Discount Audit
    _make_sheet('Discount Audit', [
        'Room No', 'Guest Name', 'Arrival', 'Departure', 'Nights in Period',
        'Original Tariff (₹)', 'Total Discount (₹)', 'Discount This Period (₹)',
        'Final Rate (₹)', 'Reason', 'Approved By'
    ], [
        [r['room_no'], r['guest_name'],
         r['arrival'].strftime('%d %b %Y'), r['departure'].strftime('%d %b %Y'),
         r['nights_in_window'], r['original_tariff'], r['discount_total'],
         r['discount_window'], r['final_rate'], r['discount_reason'], r['approved_by']]
        for r in data['discount_rows']
    ], 'Discount Audit')

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f'room_revenue_{from_date.isoformat()}_{to_date.isoformat()}.xlsx'
    return send_file(buf, download_name=filename, as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/room-revenue')
def room_revenue():
    today        = get_business_date()
    default_from = today.replace(day=1).isoformat()
    default_to   = today.isoformat()

    from_str  = request.args.get('from',       default_from)
    to_str    = request.args.get('to',         default_to)
    rt_filter = request.args.get('room_type',  '')
    fmt       = request.args.get('format',     'html')

    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = today.replace(day=1)
        to_date   = today

    if to_date < from_date:
        to_date = from_date

    data = _room_revenue_data(from_date, to_date, rt_filter)

    if fmt == 'excel':
        return _room_revenue_excel(data, from_date, to_date)

    return render_template(
        'reports/room_revenue.html',
        **data,
        from_date=from_date,
        to_date=to_date,
        from_str=from_str,
        to_str=to_str,
        rt_filter=rt_filter,
        now=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Refund Report
# ---------------------------------------------------------------------------

@reports_bp.route('/refund-report')
def refund_report():
    if not _require_accountant():
        from flask import abort
        abort(403)
    today    = get_business_date()
    from_str = request.args.get('from', today.replace(day=1).isoformat())
    to_str   = request.args.get('to',   today.isoformat())
    fmt      = request.args.get('format', 'html')
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = today.replace(day=1)
        to_date   = today

    rows = (OverpaymentLog.query
            .filter(
                OverpaymentLog.resolution == 'refund',
                func.date(OverpaymentLog.created_at) >= from_date,
                func.date(OverpaymentLog.created_at) <= to_date,
            )
            .order_by(OverpaymentLog.created_at.desc())
            .all())
    total = sum(float(r.overpaid_amount) for r in rows)

    if fmt == 'excel':
        headers = ['Date', 'Folio', 'Guest', 'Room', 'Amount (₹)',
                   'Refund Mode', 'Reason', 'Remarks', 'Processed By']
        excel_rows = []
        for r in rows:
            res = r.reservation
            excel_rows.append([
                r.created_at.strftime('%d %b %Y'),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                float(r.overpaid_amount),
                r.refund_mode.name if r.refund_mode else '',
                (r.reason or '').replace('_', ' ').title(),
                r.remarks or '',
                r.resolved_by.username if r.resolved_by else '',
            ])
        return _excel_response(
            f'refund_report_{from_str}_{to_str}.xlsx',
            headers, excel_rows,
            f'Refund Report — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'
        )

    return render_template('reports/refund_report.html',
                           rows=rows, total=total,
                           from_date=from_date, to_date=to_date,
                           from_str=from_str, to_str=to_str)


# ---------------------------------------------------------------------------
# Tip Report
# ---------------------------------------------------------------------------

@reports_bp.route('/tip-report')
def tip_report():
    if not _require_accountant():
        from flask import abort
        abort(403)
    today    = get_business_date()
    from_str = request.args.get('from', today.replace(day=1).isoformat())
    to_str   = request.args.get('to',   today.isoformat())
    fmt      = request.args.get('format', 'html')
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = today.replace(day=1)
        to_date   = today

    rows = (OverpaymentLog.query
            .filter(
                OverpaymentLog.resolution == 'tip',
                func.date(OverpaymentLog.created_at) >= from_date,
                func.date(OverpaymentLog.created_at) <= to_date,
            )
            .order_by(OverpaymentLog.created_at.desc())
            .all())
    total = sum(float(r.overpaid_amount) for r in rows)

    if fmt == 'excel':
        headers = ['Date', 'Folio', 'Guest', 'Room', 'Amount (₹)',
                   'Waiter / Staff Name', 'Remarks', 'Processed By']
        excel_rows = []
        for r in rows:
            res = r.reservation
            excel_rows.append([
                r.created_at.strftime('%d %b %Y'),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                float(r.overpaid_amount),
                r.waiter_name or '',
                r.remarks or '',
                r.resolved_by.username if r.resolved_by else '',
            ])
        return _excel_response(
            f'tip_report_{from_str}_{to_str}.xlsx',
            headers, excel_rows,
            f'Tip Report — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'
        )

    return render_template('reports/tip_report.html',
                           rows=rows, total=total,
                           from_date=from_date, to_date=to_date,
                           from_str=from_str, to_str=to_str)


# ---------------------------------------------------------------------------
# Other Income Report
# ---------------------------------------------------------------------------

@reports_bp.route('/other-income-report')
def other_income_report():
    if not _require_accountant():
        from flask import abort
        abort(403)
    today    = get_business_date()
    from_str = request.args.get('from', today.replace(day=1).isoformat())
    to_str   = request.args.get('to',   today.isoformat())
    fmt      = request.args.get('format', 'html')
    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from_date = today.replace(day=1)
        to_date   = today

    rows = (OverpaymentLog.query
            .filter(
                OverpaymentLog.resolution == 'income',
                func.date(OverpaymentLog.created_at) >= from_date,
                func.date(OverpaymentLog.created_at) <= to_date,
            )
            .order_by(OverpaymentLog.created_at.desc())
            .all())
    total = sum(float(r.overpaid_amount) for r in rows)

    if fmt == 'excel':
        headers = ['Date', 'Folio', 'Guest', 'Room', 'Amount (₹)',
                   'Category', 'Remarks', 'Processed By']
        excel_rows = []
        for r in rows:
            res = r.reservation
            excel_rows.append([
                r.created_at.strftime('%d %b %Y'),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                float(r.overpaid_amount),
                'Other Income',
                r.remarks or '',
                r.resolved_by.username if r.resolved_by else '',
            ])
        return _excel_response(
            f'other_income_report_{from_str}_{to_str}.xlsx',
            headers, excel_rows,
            f'Other Income Report — {from_date.strftime("%d %b %Y")} to {to_date.strftime("%d %b %Y")}'
        )

    return render_template('reports/other_income_report.html',
                           rows=rows, total=total,
                           from_date=from_date, to_date=to_date,
                           from_str=from_str, to_str=to_str)


# ---------------------------------------------------------------------------
# Daily Cash Reconciliation
# ---------------------------------------------------------------------------

@reports_bp.route('/daily-reconciliation')
def daily_reconciliation():
    if not _require_accountant():
        from flask import abort
        abort(403)
    today      = get_business_date()
    date_str   = request.args.get('date',   today.isoformat())
    mode_filter  = request.args.get('mode',  '').strip()
    staff_filter = request.args.get('staff', '').strip()
    fmt        = request.args.get('format', 'html')
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = today

    # ── 1. All non-voided payments for the day ──────────────────────────────
    payments_q = (Payment.query
                  .filter(Payment.payment_date == report_date,
                          Payment.is_voided == False)
                  .all())
    if mode_filter:
        payments_q = [p for p in payments_q
                      if p.payment_mode and p.payment_mode.name.lower() == mode_filter.lower()]

    # ── 2. Collection by mode ───────────────────────────────────────────────
    by_mode: dict = {}
    for p in payments_q:
        mn = p.payment_mode.name if p.payment_mode else 'Unknown'
        by_mode[mn] = by_mode.get(mn, 0.0) + float(p.amount)
    total_collection = sum(by_mode.values())

    # ── 3. Refunds ──────────────────────────────────────────────────────────
    refund_q = (OverpaymentLog.query
                .filter(OverpaymentLog.resolution == 'refund',
                        func.date(OverpaymentLog.created_at) == report_date)
                .all())
    if staff_filter:
        refund_q = [r for r in refund_q
                    if r.resolved_by and r.resolved_by.username.lower() == staff_filter.lower()]
    total_refunds = sum(float(r.overpaid_amount) for r in refund_q)

    # ── 4. Tips ─────────────────────────────────────────────────────────────
    tip_q = (OverpaymentLog.query
             .filter(OverpaymentLog.resolution == 'tip',
                     func.date(OverpaymentLog.created_at) == report_date)
             .all())
    total_tips = sum(float(t.overpaid_amount) for t in tip_q)

    # ── 5. Other Income ─────────────────────────────────────────────────────
    income_q = (OverpaymentLog.query
                .filter(OverpaymentLog.resolution == 'income',
                        func.date(OverpaymentLog.created_at) == report_date)
                .all())
    total_other_income = sum(float(o.overpaid_amount) for o in income_q)

    # ── 6. Net Collection ────────────────────────────────────────────────────
    net_collection = total_collection - total_refunds

    # ── 7. Staff list for filter dropdown ────────────────────────────────────
    staff_list = [row[0] for row in
                  db.session.query(User.username)
                  .join(OverpaymentLog, OverpaymentLog.resolved_by_user_id == User.id)
                  .filter(func.date(OverpaymentLog.created_at) == report_date)
                  .distinct().all()]

    # ── 8. All payment modes for filter dropdown ─────────────────────────────
    mode_list = [m.name for m in PaymentMode.query.filter_by(is_active=True).all()]

    if fmt == 'excel':
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils import get_column_letter
        except ImportError:
            return Response('openpyxl not installed.', status=500)

        wb = openpyxl.Workbook()

        # Sheet 1 — Summary
        ws = wb.active
        ws.title = 'Summary'
        dark_fill = PatternFill('solid', fgColor='1F4E79')
        dark_font = Font(color='FFFFFF', bold=True)
        green_fill = PatternFill('solid', fgColor='1E8449')
        red_fill   = PatternFill('solid', fgColor='C0392B')

        ws.append([f'Daily Cash Reconciliation — {report_date.strftime("%d %B %Y")}'])
        ws.cell(1, 1).font = Font(bold=True, size=14)
        ws.append([f'Generated: {datetime.now().strftime("%d %b %Y %H:%M")}'])
        ws.append([])

        def _section(label, value, fill=None):
            ws.append([label, f'₹{value:,.2f}'])
            r = ws.max_row
            if fill:
                for c in [1, 2]:
                    ws.cell(r, c).fill = fill
                    ws.cell(r, c).font = Font(bold=True, color='FFFFFF')

        ws.append(['Collection by Mode', ''])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        for mode, amt in by_mode.items():
            ws.append([f'  {mode}', f'₹{amt:,.2f}'])
        ws.append([])
        _section('Total Collection', total_collection, dark_fill)
        _section('Total Refunds', total_refunds, red_fill)
        ws.append(['Net Collection', f'₹{net_collection:,.2f}'])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
        ws.cell(ws.max_row, 2).font = Font(bold=True)
        ws.append([])
        ws.append(['Tips (not room revenue)', f'₹{total_tips:,.2f}'])
        ws.append(['Other Income (not room revenue)', f'₹{total_other_income:,.2f}'])
        ws.column_dimensions['A'].width = 40
        ws.column_dimensions['B'].width = 20

        # Sheet 2 — Payments
        ws2 = wb.create_sheet('Payments')
        hdr = ['Date', 'Folio', 'Guest', 'Room', 'Mode', 'Reference', 'Amount (₹)']
        ws2.append(hdr)
        for col_idx, _ in enumerate(hdr, 1):
            ws2.cell(1, col_idx).fill = dark_fill
            ws2.cell(1, col_idx).font = dark_font
        for p in payments_q:
            res = p.reservation
            ws2.append([
                str(p.payment_date),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                p.payment_mode.name if p.payment_mode else '',
                p.reference_number or '',
                float(p.amount),
            ])

        # Sheet 3 — Refunds
        ws3 = wb.create_sheet('Refunds')
        hdr3 = ['Date', 'Folio', 'Guest', 'Room', 'Amount (₹)', 'Refund Mode', 'Reason', 'Remarks', 'Processed By']
        ws3.append(hdr3)
        for col_idx, _ in enumerate(hdr3, 1):
            ws3.cell(1, col_idx).fill = red_fill
            ws3.cell(1, col_idx).font = dark_font
        for r in refund_q:
            res = r.reservation
            ws3.append([
                r.created_at.strftime('%d %b %Y'),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                float(r.overpaid_amount),
                r.refund_mode.name if r.refund_mode else '',
                (r.reason or '').title(),
                r.remarks or '',
                r.resolved_by.username if r.resolved_by else '',
            ])

        # Sheet 4 — Tips
        ws4 = wb.create_sheet('Tips')
        hdr4 = ['Date', 'Folio', 'Guest', 'Room', 'Amount (₹)', 'Waiter Name', 'Remarks', 'Processed By']
        ws4.append(hdr4)
        green_fill2 = PatternFill('solid', fgColor='1E8449')
        for col_idx, _ in enumerate(hdr4, 1):
            ws4.cell(1, col_idx).fill = green_fill2
            ws4.cell(1, col_idx).font = dark_font
        for t in tip_q:
            res = t.reservation
            ws4.append([
                t.created_at.strftime('%d %b %Y'),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                float(t.overpaid_amount),
                t.waiter_name or '',
                t.remarks or '',
                t.resolved_by.username if t.resolved_by else '',
            ])

        # Sheet 5 — Other Income
        ws5 = wb.create_sheet('Other Income')
        hdr5 = ['Date', 'Folio', 'Guest', 'Room', 'Amount (₹)', 'Remarks', 'Processed By']
        ws5.append(hdr5)
        blue_fill = PatternFill('solid', fgColor='1A5276')
        for col_idx, _ in enumerate(hdr5, 1):
            ws5.cell(1, col_idx).fill = blue_fill
            ws5.cell(1, col_idx).font = dark_font
        for o in income_q:
            res = o.reservation
            ws5.append([
                o.created_at.strftime('%d %b %Y'),
                res.booking_reference if res else '',
                res.guest.name if res and res.guest else '',
                res.room.room_number if res and res.room else '',
                float(o.overpaid_amount),
                o.remarks or '',
                o.resolved_by.username if o.resolved_by else '',
            ])

        # Auto-width all sheets
        for sheet in wb.worksheets:
            for col in sheet.columns:
                max_len = max((len(str(cell.value or '')) for cell in col), default=10)
                sheet.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 40)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf,
                         download_name=f'daily_reconciliation_{date_str}.xlsx',
                         as_attachment=True,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return render_template('reports/daily_reconciliation.html',
                           report_date=report_date,
                           by_mode=by_mode,
                           payments=payments_q,
                           total_collection=total_collection,
                           refunds=refund_q,
                           total_refunds=total_refunds,
                           tips=tip_q,
                           total_tips=total_tips,
                           other_income=income_q,
                           total_other_income=total_other_income,
                           net_collection=net_collection,
                           mode_filter=mode_filter,
                           staff_filter=staff_filter,
                           mode_list=mode_list,
                           staff_list=staff_list,
                           today=today)


# ---------------------------------------------------------------------------
# Money at Risk Dashboard
# ---------------------------------------------------------------------------

@reports_bp.route('/money-at-risk')
def money_at_risk():
    today = get_business_date()
    fmt   = request.args.get('format', 'html')

    # ── SQL aggregates ──────────────────────────────────────────────────────
    # Total paid per reservation (non-voided payments)
    paid_rows = db.session.query(
        Payment.reservation_id,
        func.sum(Payment.amount).label('total_paid')
    ).filter(Payment.is_voided == False).group_by(Payment.reservation_id).all()
    paid_map = {r.reservation_id: float(r.total_paid) for r in paid_rows}

    # Total extra charges per reservation — exclude night-audit
    # room_rent rows, which are double-counted against rate × nights
    # in _balance below.
    from sqlalchemy import or_ as _or_rep
    extras_rows = db.session.query(
        ExtraCharge.reservation_id,
        func.sum(ExtraCharge.amount).label('total_extras')
    ).filter(
        _or_rep(ExtraCharge.charge_type.is_(None),
                ExtraCharge.charge_type != 'room_rent')
    ).group_by(ExtraCharge.reservation_id).all()
    extras_map = {r.reservation_id: float(r.total_extras) for r in extras_rows}

    def _balance(res):
        nights = max((res.departure_date - res.arrival_date).days, 1)
        billed = (float(res.rate_per_night or 0) * nights
                  + extras_map.get(res.id, 0.0)
                  - float(res.discount_amount or 0))
        return round(billed - paid_map.get(res.id, 0.0), 2)

    # ── 1a. In-house pending dues ───────────────────────────────────────────
    inhouse_all = Reservation.query.filter_by(status='CheckedIn').all()
    inhouse_dues  = []
    inhouse_total = 0.0
    for res in inhouse_all:
        bal = _balance(res)
        if bal > 0.01:
            inhouse_dues.append({'res': res, 'balance': bal})
            inhouse_total += bal

    # ── 1b. Checked-out pending dues (last 60 days) ─────────────────────────
    cutoff = datetime.combine(today - timedelta(days=60), datetime.min.time())
    co_all = Reservation.query.filter(
        Reservation.status == 'CheckedOut',
        Reservation.checked_out_at >= cutoff
    ).all()
    checkedout_dues  = []
    checkedout_total = 0.0
    for res in co_all:
        bal = _balance(res)
        if bal > 0.01:
            checkedout_dues.append({'res': res, 'balance': bal})
            checkedout_total += bal

    # ── 1c. Company credit pending ──────────────────────────────────────────
    company_ci = (CheckInRecord.query
                  .filter_by(billing_responsibility='Company')
                  .join(Reservation, CheckInRecord.reservation_id == Reservation.id)
                  .filter(Reservation.status.in_(['CheckedIn', 'CheckedOut']))
                  .all())
    company_map = {}
    for ci in company_ci:
        if not ci.company_id:
            continue
        res = ci.reservation
        if not res:
            continue
        bal = _balance(res)
        if bal > 0.01:
            if ci.company_id not in company_map:
                company_map[ci.company_id] = {'company': ci.company, 'total': 0.0, 'count': 0}
            company_map[ci.company_id]['total'] += bal
            company_map[ci.company_id]['count'] += 1
    company_dues  = list(company_map.values())
    company_total = sum(d['total'] for d in company_dues)

    pending_dues_total = inhouse_total + checkedout_total + company_total

    # ── 2. Overdue pending check-outs ──────────────────────────────────────
    overdue = []
    for res in inhouse_all:
        if res.departure_date <= today:
            overdue.append({
                'res':        res,
                'balance':    _balance(res),
                'delay_days': (today - res.departure_date).days,
            })
    overdue.sort(key=lambda x: x['delay_days'], reverse=True)

    # ── 3. ExtraCharge breakdown by service category (in-house) ────────────
    # Exclude night-audit room_rent rows so "unposted" service categories
    # don't include auto-posted room revenue.
    inhouse_ids = [r.id for r in inhouse_all]
    in_extras   = (ExtraCharge.query
                   .filter(ExtraCharge.reservation_id.in_(inhouse_ids),
                           _or_rep(ExtraCharge.charge_type.is_(None),
                                   ExtraCharge.charge_type != 'room_rent')).all()
                   if inhouse_ids else [])

    def _classify(desc):
        d = (desc or '').lower()
        if any(k in d for k in ('restaurant', 'food', 'dining', 'meal', 'breakfast',
                                'lunch', 'dinner', 'snack', 'f&b', 'bar', 'beverage')):
            return 'restaurant'
        if any(k in d for k in ('laundry', 'washing', 'dry clean', 'ironing')):
            return 'laundry'
        if any(k in d for k in ('extra bed', 'extra cot', 'mattress', 'cot')):
            return 'extra_bed'
        if any(k in d for k in ('late checkout', 'late check out', 'late check-out')):
            return 'late_checkout'
        return 'other'

    unposted = {'restaurant': 0.0, 'laundry': 0.0,
                'extra_bed': 0.0, 'late_checkout': 0.0, 'other': 0.0}
    for ec in in_extras:
        unposted[_classify(ec.description)] += float(ec.amount)
    unposted_total = sum(unposted.values())

    # ── 4. Revenue Leakage Alerts ───────────────────────────────────────────
    # a. Unauthorized discounts
    unauth_discounts = Reservation.query.filter(
        Reservation.discount_amount > 0,
        Reservation.status.in_(['CheckedIn', 'CheckedOut', 'Reserved', 'Confirmed']),
        Reservation.discount_authorized_by == None,
    ).all()
    unauth_total = sum(float(r.discount_amount) for r in unauth_discounts)

    # b. Tariff override / leakage
    tariff_overrides  = Reservation.query.filter(
        Reservation.tariff_modified_manually == True,
        Reservation.status.in_(['CheckedIn', 'Reserved', 'Confirmed'])
    ).all()
    leakage_overrides = [r for r in tariff_overrides if r.adjustment_type == 'LEAKAGE']
    leakage_override_total = sum(
        float(r.adjustment_amount or 0)
        * max((r.departure_date - r.arrival_date).days, 1)
        for r in leakage_overrides
    )

    # c. Low-rate occupied rooms (rate < 80 % of room-type base rate)
    low_rate = []
    for res in inhouse_all:
        if res.room_type and res.rate_per_night:
            base   = float(res.room_type.base_rate or 0)
            actual = float(res.rate_per_night)
            if base > 0 and actual < base * 0.80:
                low_rate.append({'res': res, 'base_rate': base,
                                 'actual_rate': actual, 'gap': round(base - actual, 2)})

    # d. Voided payments today
    voided_today = Payment.query.filter(
        Payment.is_voided == True,
        func.date(Payment.voided_at) == today
    ).all()

    # e. Unresolved overpayments (in-house, balance < 0, no OverpaymentLog yet)
    resolved_ids = {
        r.reservation_id
        for r in OverpaymentLog.query.with_entities(OverpaymentLog.reservation_id).all()
    }
    unresolved_overpay = []
    for res in inhouse_all:
        bal = _balance(res)
        if bal < -0.01 and res.id not in resolved_ids:
            unresolved_overpay.append({'res': res, 'overpaid': round(abs(bal), 2)})

    leakage_total = (unauth_total + leakage_override_total
                     + sum(d['gap'] for d in low_rate))

    # ── 5. Dirty rooms blocking revenue ────────────────────────────────────
    dirty_rooms   = Room.query.filter_by(status='Dirty').all()
    dirty_count   = len(dirty_rooms)
    blocked_rates = [float(r.room_type.base_rate)
                     for r in dirty_rooms if r.room_type and r.room_type.base_rate]
    avg_lost_rate  = (sum(blocked_rates) / len(blocked_rates)) if blocked_rates else 0.0
    blocked_revenue = sum(blocked_rates)

    # ── Top-card grand total ────────────────────────────────────────────────
    total_at_risk = pending_dues_total + unposted_total + leakage_total + blocked_revenue

    # ── Excel export ────────────────────────────────────────────────────────
    if fmt == 'excel':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()

        def _sheet_header(ws, headers, fill_hex='1F4E79'):
            ws.append(headers)
            fill = PatternFill('solid', fgColor=fill_hex)
            fnt  = Font(color='FFFFFF', bold=True)
            for i in range(1, len(headers) + 1):
                c = ws.cell(ws.max_row, i)
                c.fill = fill; c.font = fnt
                c.alignment = Alignment(horizontal='center')

        # Sheet 1 — Pending Dues
        ws1 = wb.active
        ws1.title = 'Pending Dues'
        _sheet_header(ws1, ['Type', 'Folio', 'Guest', 'Room',
                             'Check-In', 'Check-Out Due', 'Balance (₹)'], 'C0392B')
        for d in inhouse_dues:
            r = d['res']
            ws1.append(['In-House', r.booking_reference or str(r.id),
                        r.guest.name if r.guest else '',
                        r.room.room_number if r.room else '',
                        r.arrival_date.strftime('%d %b %Y'),
                        r.departure_date.strftime('%d %b %Y'), d['balance']])
        for d in checkedout_dues:
            r = d['res']
            ws1.append(['Checked-Out', r.booking_reference or str(r.id),
                        r.guest.name if r.guest else '',
                        r.room.room_number if r.room else '',
                        r.arrival_date.strftime('%d %b %Y'),
                        r.departure_date.strftime('%d %b %Y'), d['balance']])

        # Sheet 2 — Revenue Leakage
        ws2 = wb.create_sheet('Revenue Leakage')
        _sheet_header(ws2, ['Alert Type', 'Folio', 'Guest', 'Room',
                             'Actual Rate (₹)', 'Base Rate (₹)', 'Discount (₹)',
                             'Impact (₹)'], 'E67E22')
        for r in unauth_discounts:
            ws2.append(['Unauthorized Discount', r.booking_reference or str(r.id),
                        r.guest.name if r.guest else '',
                        r.room.room_number if r.room else '',
                        '', '', float(r.discount_amount), float(r.discount_amount)])
        for d in low_rate:
            r = d['res']
            ws2.append(['Low Rate Room', r.booking_reference or str(r.id),
                        r.guest.name if r.guest else '',
                        r.room.room_number if r.room else '',
                        d['actual_rate'], d['base_rate'], '', d['gap']])

        # Sheet 3 — Overdue Checkouts
        ws3 = wb.create_sheet('Overdue Checkouts')
        _sheet_header(ws3, ['Folio', 'Guest', 'Room', 'Due Date',
                             'Days Overdue', 'Balance (₹)'], '2C3E50')
        for d in overdue:
            r = d['res']
            ws3.append([r.booking_reference or str(r.id),
                        r.guest.name if r.guest else '',
                        r.room.room_number if r.room else '',
                        r.departure_date.strftime('%d %b %Y'),
                        d['delay_days'], d['balance']])

        # Auto-width all sheets
        for sheet in wb.worksheets:
            for col in sheet.columns:
                max_len = max((len(str(c.value or '')) for c in col), default=8)
                sheet.column_dimensions[
                    get_column_letter(col[0].column)].width = min(max_len + 4, 40)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf,
                         download_name=f'money_at_risk_{today.isoformat()}.xlsx',
                         as_attachment=True,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    # ── Waived CICO charges (last 30 days) ─────────────────────────────────
    cutoff_30 = datetime.combine(today - timedelta(days=30), datetime.min.time())
    _waived_logs = (CICOChargeLog.query
                    .filter(CICOChargeLog.waived == True)
                    .filter(CICOChargeLog.timestamp >= cutoff_30)
                    .order_by(CICOChargeLog.timestamp.desc())
                    .all())
    waived_cico_total = sum(float(lg.amount_calculated or 0) for lg in _waived_logs)

    return render_template('reports/money_at_risk.html',
                           today=today,
                           total_at_risk=total_at_risk,
                           pending_dues_total=pending_dues_total,
                           unposted_total=unposted_total,
                           leakage_total=leakage_total,
                           blocked_revenue=blocked_revenue,
                           inhouse_dues=inhouse_dues,
                           inhouse_total=inhouse_total,
                           checkedout_dues=checkedout_dues,
                           checkedout_total=checkedout_total,
                           company_dues=company_dues,
                           company_total=company_total,
                           overdue=overdue,
                           unposted=unposted,
                           unauth_discounts=unauth_discounts,
                           unauth_total=unauth_total,
                           tariff_overrides=tariff_overrides,
                           leakage_overrides=leakage_overrides,
                           low_rate=low_rate,
                           voided_today=voided_today,
                           unresolved_overpay=unresolved_overpay,
                           dirty_rooms=dirty_rooms,
                           dirty_count=dirty_count,
                           avg_lost_rate=avg_lost_rate,
                           waived_cico=_waived_logs,
                           waived_cico_total=waived_cico_total)


# ---------------------------------------------------------------------------
# Daily Profit Snapshot Dashboard
# ---------------------------------------------------------------------------

@reports_bp.route('/daily-profit-snapshot')
def daily_profit_snapshot():
    today     = get_business_date()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)

    def _day_data(target):
        # Rooms occupied on target date (arrival <= target < departure)
        occupied = Reservation.query.filter(
            Reservation.status.in_(['CheckedIn', 'CheckedOut']),
            Reservation.arrival_date  <= target,
            Reservation.departure_date > target,
        ).all()

        # Canonical denominators from the occupancy engine (KPI Phase 1,
        # Step 4): occ_count is DISTINCT rooms occupied on `target` (not a
        # reservation-row count, which could exceed the room inventory and
        # produce an impossible >100% occupancy); `sellable` is the
        # canonical sell-able denominator shared by every KPI surface.
        from app.occupancy_engine import (
            occupied_room_nights as _engine_room_nights,
            sellable_rooms as _engine_sellable_rooms,
        )
        occ_count   = _engine_room_nights(target, target)
        sellable    = _engine_sellable_rooms()
        total_rooms = db.session.query(
            func.count(Room.id)
        ).filter(Room.status != 'Maintenance').scalar() or 1
        room_rev = sum(float(r.rate_per_night or 0) for r in occupied)

        # Extra charges posted on target date, split by food vs non-food
        extras_today = ExtraCharge.query.filter(
            ExtraCharge.charge_date == target
        ).all()
        food_rev = 0.0
        for ec in extras_today:
            d = (ec.description or '').lower()
            if any(k in d for k in ('restaurant', 'food', 'dining', 'meal',
                                    'breakfast', 'lunch', 'dinner', 'snack',
                                    'f&b', 'bar', 'beverage')):
                food_rev += float(ec.amount)

        # Other income (overpayment adjusted as income)
        other_income = float(db.session.query(
            func.sum(OverpaymentLog.overpaid_amount)
        ).filter(
            func.date(OverpaymentLog.created_at) == target,
            OverpaymentLog.resolution == 'income'
        ).scalar() or 0)

        gross = room_rev + food_rev + other_income

        # Discounts applied on target date
        discounts = float(db.session.query(
            func.sum(Reservation.discount_amount)
        ).filter(
            func.date(Reservation.discount_at) == target,
            Reservation.discount_amount > 0
        ).scalar() or 0)

        # Refunds processed on target date
        refunds = float(db.session.query(
            func.sum(OverpaymentLog.overpaid_amount)
        ).filter(
            func.date(OverpaymentLog.created_at) == target,
            OverpaymentLog.resolution == 'refund'
        ).scalar() or 0)

        # OTA commission estimate — 15 % of total room-nights for OTA arrivals today
        ota_arrivals = Reservation.query.filter(
            Reservation.arrival_date == target,
            Reservation.source == 'OTA',
            Reservation.status.in_(['CheckedIn', 'CheckedOut'])
        ).all()
        ota_commission = round(sum(
            float(r.rate_per_night or 0)
            * max((r.departure_date - r.arrival_date).days, 1) * 0.15
            for r in ota_arrivals
        ), 2)

        total_reductions = discounts + refunds + ota_commission
        net_rev = gross - total_reductions

        # KPIs — ARR over distinct occupied rooms, RevPAR/occupancy over
        # the canonical sellable denominator (KPI Phase 1, Step 4).
        occ_pct = round(occ_count / sellable * 100, 1) if sellable  else 0.0
        arr    = round(room_rev / occ_count, 2)        if occ_count else 0.0
        revpar = round(room_rev / sellable, 2)         if sellable  else 0.0
        alos   = 0.0
        if occupied:
            stays = [(r.departure_date - r.arrival_date).days for r in occupied]
            alos  = round(sum(stays) / len(stays), 1)

        # v2.2.11: payment-by-mode breakdown now uses the canonical
        # cash-basis helper. Matches the dashboard's "Cash In / UPI In /
        # Cards In" tiles and the flash report's payment-mode breakdown.
        from app.kpi_helpers import get_payment_by_mode as _gpbm
        _by_mode_dict = _gpbm(target)
        # Preserve the namedtuple-style ``row.total`` access used below.
        from collections import namedtuple
        _ModeRow = namedtuple('_ModeRow', ['name', 'total'])
        mode_rows = [_ModeRow(name=n, total=v) for n, v in _by_mode_dict.items()]
        total_collected = sum(float(p.total) for p in mode_rows)

        return dict(
            room_rev=room_rev, food_rev=food_rev,
            other_income=other_income, gross=gross,
            discounts=discounts, refunds=refunds,
            ota_commission=ota_commission,
            total_reductions=total_reductions, net_rev=net_rev,
            occ_count=occ_count, total_rooms=total_rooms, occ_pct=occ_pct,
            arr=arr, revpar=revpar, alos=alos,
            mode_rows=mode_rows, total_collected=total_collected,
        )

    # v2.2.11: MTD collection now routes through canonical helper. Matches
    # the dashboard's MTD Revenue tile and the flash report's MTD.
    from app.kpi_helpers import get_monthly_revenue
    mtd = get_monthly_revenue(month_start, today)

    today_d = _day_data(today)
    yest_d  = _day_data(yesterday)
    today_d['mtd'] = mtd

    fmt = request.args.get('format', 'html')
    if fmt == 'excel':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        wb  = openpyxl.Workbook()
        ws  = wb.active
        ws.title = 'Daily Profit Snapshot'

        blue = PatternFill('solid', fgColor='1F4E79')
        bfnt = Font(color='FFFFFF', bold=True)
        gfnt = Font(bold=True)

        def _row(label, today_val, yest_val):
            ws.append([label,
                       round(float(today_val), 2),
                       round(float(yest_val),  2)])

        ws.append(['Daily Profit Snapshot', today.strftime('%d %b %Y'), yesterday.strftime('%d %b %Y')])
        for i in (1, 2, 3):
            c = ws.cell(1, i); c.fill = blue; c.font = bfnt
        ws.append([])
        ws.append(['Metric', 'Today', 'Yesterday'])
        for i in (1, 2, 3):
            c = ws.cell(ws.max_row, i); c.fill = blue; c.font = bfnt

        _row('Room Revenue',       today_d['room_rev'],   yest_d['room_rev'])
        _row('Food Revenue',       today_d['food_rev'],   yest_d['food_rev'])
        _row('Other Income',       today_d['other_income'], yest_d['other_income'])
        _row('Gross Revenue',      today_d['gross'],       yest_d['gross'])
        ws.append([])
        _row('Less: Discounts',    today_d['discounts'],  yest_d['discounts'])
        _row('Less: Refunds',      today_d['refunds'],    yest_d['refunds'])
        _row('Less: OTA Commission', today_d['ota_commission'], yest_d['ota_commission'])
        _row('Net Revenue',        today_d['net_rev'],    yest_d['net_rev'])
        ws.append([])
        _row('Cash Collected',     today_d['total_collected'], yest_d['total_collected'])
        ws.append([])
        _row('Occupancy %',        today_d['occ_pct'],    yest_d['occ_pct'])
        _row('ARR',                today_d['arr'],         yest_d['arr'])
        _row('RevPAR',             today_d['revpar'],      yest_d['revpar'])
        _row('ALOS',               today_d['alos'],        yest_d['alos'])
        _row('MTD Revenue',        today_d['mtd'],         0)

        for col in ws.columns:
            max_len = max((len(str(c.value or '')) for c in col), default=8)
            ws.column_dimensions[
                get_column_letter(col[0].column)].width = min(max_len + 4, 36)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf,
                         download_name=f'daily_profit_snapshot_{today.isoformat()}.xlsx',
                         as_attachment=True,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return render_template('reports/daily_profit_snapshot.html',
                           today=today,
                           yesterday=yesterday,
                           today_d=today_d,
                           yest_d=yest_d)


# ---------------------------------------------------------------------------
# GSTR-1 JSON Export
# ---------------------------------------------------------------------------

@reports_bp.route('/gstr1-export', methods=['GET', 'POST'])
def gstr1_export():
    """
    GET  — show form with date range and filing period inputs.
    POST — generate GSTR-1 JSON file and return as download.
    """
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access denied.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app import gst_service as _gs

    if request.method == 'GET':
        hotel_gstin = _gs.get_hotel_gstin()
        today = date.today()
        # Default: previous month
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        default_fp = last_month_start.strftime('%m%Y')  # MMYYYY

        return render_template(
            'reports/gstr1_export.html',
            hotel_gstin=hotel_gstin,
            from_date=last_month_start,
            to_date=last_month_end,
            fp=default_fp,
        )

    # POST — generate and download
    from_str = request.form.get('from_date', '')
    to_str   = request.form.get('to_date', '')
    fp       = request.form.get('fp', '').strip()
    gstin    = request.form.get('gstin', '').strip()

    if not gstin or len(gstin) != 15:
        from flask import flash
        flash('Valid 15-character GSTIN is required.', 'danger')
        return redirect(request.referrer or url_for('reports.gstr1_export'))

    if not fp or len(fp) != 6:
        from flask import flash
        flash('Filing period must be in MMYYYY format (e.g. 032026).', 'danger')
        return redirect(request.referrer or url_for('reports.gstr1_export'))

    try:
        from_date = date.fromisoformat(from_str)
        to_date   = date.fromisoformat(to_str)
    except ValueError:
        from flask import flash
        flash('Invalid date format.', 'danger')
        return redirect(request.referrer or url_for('reports.gstr1_export'))

    from app.gstr_export import generate_gstr1_json
    import json

    data = generate_gstr1_json(from_date, to_date, gstin, fp)
    json_str = json.dumps(data, indent=2, ensure_ascii=False)

    filename = f'GSTR1_{gstin}_{fp}.json'
    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


# ---------------------------------------------------------------------------
# Accounts Receivable Aging Report
# ---------------------------------------------------------------------------

@reports_bp.route('/ar-aging')
def ar_aging():
    """Accounts receivable aging report — outstanding balances by 30/60/90+ day buckets."""
    today = get_business_date()

    reservations = (
        Reservation.query
        .filter(Reservation.status == 'CheckedOut')
        .all()
    )

    aging_rows = []
    totals = {'current': 0, 'days_30': 0, 'days_60': 0, 'days_90': 0, 'total': 0}

    for res in reservations:
        billing = calculate_stay_amount(res)
        balance = float(billing['balance'])
        if balance <= 1.0:
            continue

        checkout_date = res.checked_out_at.date() if res.checked_out_at else res.departure_date
        days_old = (today - checkout_date).days if checkout_date else 0

        bucket = 'current'
        if days_old > 90:
            bucket = 'days_90'
        elif days_old > 60:
            bucket = 'days_60'
        elif days_old > 30:
            bucket = 'days_30'

        company_name = None
        if res.checkin_record and res.checkin_record.company_id:
            company_name = res.checkin_record.company.name if res.checkin_record.company else None

        aging_rows.append({
            'reservation_id': res.id,
            'guest_name': res.guest.name if res.guest else 'Unknown',
            'company': company_name,
            'invoice_number': res.invoice_number or '-',
            'checkout_date': checkout_date,
            'days_old': days_old,
            'balance': balance,
            'bucket': bucket,
            'room': res.room.room_number if res.room else '-',
        })

        totals[bucket] += balance
        totals['total'] += balance

    aging_rows.sort(key=lambda r: r['days_old'], reverse=True)

    if request.args.get('format') == 'excel':
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'AR Aging'
        headers = ['Guest', 'Company', 'Invoice #', 'Room', 'Checkout Date', 'Days Old',
                    'Current', '31-60 Days', '61-90 Days', '90+ Days', 'Total']
        ws.append(headers)
        for r in aging_rows:
            ws.append([
                r['guest_name'], r['company'] or '', r['invoice_number'], r['room'],
                r['checkout_date'].strftime('%d-%b-%Y') if r['checkout_date'] else '',
                r['days_old'],
                r['balance'] if r['bucket'] == 'current' else 0,
                r['balance'] if r['bucket'] == 'days_30' else 0,
                r['balance'] if r['bucket'] == 'days_60' else 0,
                r['balance'] if r['bucket'] == 'days_90' else 0,
                r['balance'],
            ])
        ws.append(['', '', '', '', '', 'TOTAL',
                    totals['current'], totals['days_30'], totals['days_60'], totals['days_90'], totals['total']])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, download_name=f'ar_aging_{today}.xlsx', as_attachment=True,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return render_template('reports/ar_aging.html',
                           rows=aging_rows, totals=totals, today=today)


# ---------------------------------------------------------------------------
# Revenue Leakage Report
# ---------------------------------------------------------------------------

@reports_bp.route('/leakage')
def leakage():
    """Revenue leakage report — rate + discount leakage by reservation."""
    from app.leakage_service import (
        compute_leakage_for_date_range, compute_leakage_summary,
    )
    today = get_business_date()

    # Quick filter
    quick = request.args.get('quick', '').strip()
    if quick == 'today':
        start_date = end_date = today
    elif quick == 'week':
        start_date = today - timedelta(days=6)
        end_date = today
    elif quick == 'month':
        start_date = today.replace(day=1)
        end_date = today
    else:
        try:
            start_date = date.fromisoformat(request.args.get('start_date', today.isoformat()))
        except ValueError:
            start_date = today
        try:
            end_date = date.fromisoformat(request.args.get('end_date', today.isoformat()))
        except ValueError:
            end_date = today

    only_leakage = request.args.get('only_leakage') == '1'
    leak_type = request.args.get('leak_type', 'all').strip()
    source_filter = request.args.get('source_filter', 'all').strip()
    fmt = request.args.get('format', 'html')

    records = compute_leakage_for_date_range(
        start_date, end_date, only_leakage=only_leakage)

    # Source counts (before filtering — reflects underlying data distribution)
    source_counts = {
        'nightly_rows': 0,
        'legacy_aggregate': 0,
        'validation_fallback': 0,
    }
    for r in records:
        _s = r.get('source', 'legacy_aggregate')
        source_counts[_s] = source_counts.get(_s, 0) + 1

    # Source filter
    if source_filter == 'nightly':
        records = [r for r in records if r.get('source') == 'nightly_rows']
    elif source_filter == 'legacy':
        records = [r for r in records if r.get('source') == 'legacy_aggregate']
    elif source_filter == 'validation':
        records = [r for r in records if r.get('source') == 'validation_fallback']

    # Leakage type filter (applied after fetch — keeps service simple)
    if leak_type == 'rate':
        records = [r for r in records if r['rate_leakage'] > 0]
    elif leak_type == 'discount':
        records = [r for r in records if r['discount_amount'] > 0]
    elif leak_type == 'both':
        records = [r for r in records
                   if r['rate_leakage'] > 0 and r['discount_amount'] > 0]

    summary = compute_leakage_summary(records)

    # Migration metrics on the filtered dataset
    _mig_counts = {'nightly_rows': 0, 'legacy_aggregate': 0, 'validation_fallback': 0}
    _mig_leakage = {'nightly_rows': 0.0, 'legacy_aggregate': 0.0, 'validation_fallback': 0.0}
    for r in records:
        _s = r.get('source', 'legacy_aggregate')
        _mig_counts[_s] = _mig_counts.get(_s, 0) + 1
        _mig_leakage[_s] = _mig_leakage.get(_s, 0.0) + float(r['total_leakage'])
    _total_mig = sum(_mig_counts.values()) or 1
    migration = {
        'counts': _mig_counts,
        'leakage': _mig_leakage,
        'pct': {
            k: round(v * 100 / _total_mig, 1)
            for k, v in _mig_counts.items()
        },
        'total_records': sum(_mig_counts.values()),
    }

    if fmt == 'excel':
        headers = [
            'Reservation', 'Invoice', 'Guest', 'Room', 'Nights',
            'Pricing Mode', 'Std Revenue', 'Actual Revenue',
            'Rate Leakage', 'Discount', 'Total Leakage', 'Leakage %',
            'Status', 'Source', 'Adj Type', 'Authorized By', 'Reason',
        ]
        _src_labels = {
            'nightly_rows': 'Nightly Rows',
            'legacy_aggregate': 'Legacy Aggregate',
            'validation_fallback': 'Validation Fallback',
        }
        rows = []
        for r in records:
            rows.append([
                r['reservation_id'],
                r['invoice_number'] or '',
                r['guest_name'],
                r['room_number'],
                r['nights'],
                r['pricing_mode'] or '',
                float(r['standard_revenue']),
                float(r['actual_revenue']),
                float(r['rate_leakage']),
                float(r['discount_amount']),
                float(r['total_leakage']),
                float(r['leakage_pct']),
                r['status'],
                _src_labels.get(r.get('source', ''), r.get('source', '')),
                r['adjustment_type'] or '',
                r['discount_authorized_by'] or '',
                r['discount_reason'] or '',
            ])
        _type_label = {'all': 'All', 'rate': 'Rate Only', 'discount': 'Discount Only', 'both': 'Both'}.get(leak_type, 'All')
        return _excel_response(
            f'leakage_{leak_type}_{start_date}_{end_date}.xlsx',
            headers, rows,
            title=f'Revenue Leakage ({_type_label}) — {start_date.strftime("%d %b %Y")} to {end_date.strftime("%d %b %Y")}',
        )

    return render_template('reports/leakage.html',
                           records=records, summary=summary,
                           start_date=start_date, end_date=end_date,
                           only_leakage=only_leakage, leak_type=leak_type,
                           source_filter=source_filter,
                           source_counts=source_counts,
                           migration=migration,
                           quick=quick)


# ---------------------------------------------------------------------------
# Credit Ledger — Individual guest credit checkouts (outstanding only)
# ---------------------------------------------------------------------------

@reports_bp.route('/credit-ledger')
def credit_ledger():
    """Receivables ledger — every reservation checked out on Individual Credit.

    Status (Open / Partial / Settled) is derived from credit_amount vs
    credit_settled_amount. By default, only Open + Partial rows are shown;
    pass ``?include_settled=1`` to include fully cleared credits as well.
    """
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    fmt = request.args.get('format', 'html')
    include_settled = request.args.get('include_settled', '0') == '1'

    # Pull every reservation that's ever had individual credit on it.
    rows = (
        Reservation.query
        .filter(Reservation.credit_amount > 0)
        .order_by(Reservation.credit_approved_at.desc().nullslast())
        .all()
    )

    today = get_business_date()
    from app.services import credit_status, credit_lifecycle_summary
    records = []
    grand_open    = 0.0
    grand_recovered = 0.0
    count_open = count_partial = count_settled = count_overdue = 0

    for r in rows:
        # Apr 2026 final tightening: use credit_lifecycle_summary for the
        # full triage view (status with Overdue, days_outstanding,
        # last_payment_date, aging_bucket).
        life = credit_lifecycle_summary(r)
        original  = life['original']
        settled   = life['recovered']
        remaining = life['remaining']
        status    = life['status']

        if status == 'Settled':
            count_settled += 1
            if not include_settled:
                continue
        elif status == 'Overdue':
            count_overdue += 1
        elif status == 'Partial':
            count_partial += 1
        else:
            count_open += 1

        approved_at = r.credit_approved_at
        approver = ''
        if r.credit_approved_by_user_id:
            try:
                u = db.session.get(User, r.credit_approved_by_user_id)
                approver = u.username if u else ''
            except Exception:
                approver = ''

        grand_open      += remaining if status != 'Settled' else 0
        grand_recovered += settled

        records.append({
            'reservation':    r,
            'guest_name':     r.guest.name if r.guest else '—',
            'room_no':        r.room.room_number if r.room else '—',
            'departure_date': r.departure_date,
            'original':       original,
            'recovered':      settled,
            'remaining':      remaining,
            'status':         status,
            'reason':         r.credit_reason or '',
            'approver':       approver,
            'approved_at':    approved_at,
            'settled_at':     r.credit_settled_at,
            'days_open':      life['days_outstanding'],
            'days_outstanding':    life['days_outstanding'],
            'last_payment_date':   life['last_payment_date'],
            'last_payment_amount': life['last_payment_amount'],
            'aging_bucket':        life['aging_bucket'],
        })

    if fmt == 'excel':
        headers = ['Approved On', 'Reservation', 'Guest', 'Room',
                   'Checkout Date', 'Status',
                   'Original (₹)', 'Recovered (₹)', 'Remaining (₹)',
                   'Days Open', 'Settled On', 'Reason', 'Approved By']
        excel_rows = []
        for rec in records:
            r = rec['reservation']
            excel_rows.append([
                rec['approved_at'].strftime('%Y-%m-%d %H:%M') if rec['approved_at'] else '',
                r.booking_reference or r.id,
                rec['guest_name'],
                rec['room_no'],
                rec['departure_date'].isoformat() if rec['departure_date'] else '',
                rec['status'],
                rec['original'],
                rec['recovered'],
                rec['remaining'],
                rec['days_open'] if rec['days_open'] is not None else '',
                rec['settled_at'].strftime('%Y-%m-%d %H:%M') if rec['settled_at'] else '',
                rec['reason'],
                rec['approver'],
            ])
        return _excel_response(
            f'credit_ledger_{today.isoformat()}.xlsx',
            headers, excel_rows,
            title=f'Credit Ledger as of {today.strftime("%d %b %Y")}'
        )

    return render_template('reports/credit_ledger.html',
                           records=records,
                           grand_open=grand_open,
                           grand_recovered=grand_recovered,
                           count_open=count_open,
                           count_partial=count_partial,
                           count_settled=count_settled,
                           count_overdue=count_overdue,
                           include_settled=include_settled,
                           today=today)


@reports_bp.route('/credit-aging')
def credit_aging():
    """Bucket open individual credit by age: 0-7, 8-15, 16-30, 30+ days."""
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    fmt = request.args.get('format', 'html')

    rows = (
        Reservation.query
        .filter(Reservation.credit_amount > 0)
        .all()
    )

    today = get_business_date()
    buckets = {
        '0-7':   {'label': '0–7 days',   'count': 0, 'amount': 0.0, 'records': []},
        '8-15':  {'label': '8–15 days',  'count': 0, 'amount': 0.0, 'records': []},
        '16-30': {'label': '16–30 days', 'count': 0, 'amount': 0.0, 'records': []},
        '30+':   {'label': '30+ days',   'count': 0, 'amount': 0.0, 'records': []},
    }
    grand_total = 0.0

    for r in rows:
        # Use credit_settled_amount as the source of truth for remaining
        # (drops Settled rows out of the aging buckets entirely).
        original  = float(r.credit_amount or 0)
        settled   = float(r.credit_settled_amount or 0)
        remaining = max(0.0, round(original - settled, 2))
        if remaining <= 0.01:
            continue
        approved_date = r.credit_approved_at.date() if r.credit_approved_at else r.departure_date
        days_open = (today - approved_date).days if approved_date else 0
        amt = remaining
        grand_total += amt

        if days_open <= 7:
            key = '0-7'
        elif days_open <= 15:
            key = '8-15'
        elif days_open <= 30:
            key = '16-30'
        else:
            key = '30+'

        buckets[key]['count']  += 1
        buckets[key]['amount'] += amt
        buckets[key]['records'].append({
            'reservation':  r,
            'guest_name':   r.guest.name if r.guest else '—',
            'room_no':      r.room.room_number if r.room else '—',
            'amount':       amt,
            'days_open':    days_open,
            'reason':       r.credit_reason or '',
            'approved_at':  r.credit_approved_at,
        })

    if fmt == 'excel':
        headers = ['Age Bucket', 'Guest', 'Reservation', 'Room',
                   'Amount (₹)', 'Days Open', 'Approved On', 'Reason']
        excel_rows = []
        for key in ('0-7', '8-15', '16-30', '30+'):
            for rec in buckets[key]['records']:
                r = rec['reservation']
                excel_rows.append([
                    buckets[key]['label'],
                    rec['guest_name'],
                    r.booking_reference or r.id,
                    rec['room_no'],
                    rec['amount'],
                    rec['days_open'],
                    rec['approved_at'].strftime('%Y-%m-%d %H:%M') if rec['approved_at'] else '',
                    rec['reason'],
                ])
        return _excel_response(
            f'credit_aging_{today.isoformat()}.xlsx',
            headers, excel_rows,
            title=f'Credit Aging as of {today.strftime("%d %b %Y")}'
        )

    # 30+ alert payload — exposed for dashboard / alert engine consumption.
    overdue_30 = {
        'count':  buckets['30+']['count'],
        'amount': buckets['30+']['amount'],
    }

    return render_template('reports/credit_aging.html',
                           buckets=buckets,
                           grand_total=grand_total,
                           overdue_30=overdue_30,
                           today=today)


# ---------------------------------------------------------------------------
# Credit Voucher Ledger — active / expired / redeemed (Apr 2026)
# ---------------------------------------------------------------------------

@reports_bp.route('/voucher-ledger')
def voucher_ledger():
    """Lifecycle view of all credit vouchers. Filter by status via ?status=.

    Sums shown at the top: Total Issued, Total Redeemed, Outstanding (live
    liability). Active / Expired / Redeemed tabs share the same table; the
    status column carries the badge so the filter is cosmetic.
    """
    if not _require_accountant():
        from flask import flash, redirect, url_for
        flash('Access restricted.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.models import CreditVoucher
    from app.services import refresh_voucher_status, voucher_remaining
    fmt    = request.args.get('format', 'html')
    status_filter = (request.args.get('status') or '').strip().lower()

    # Refresh status on read so calendar-expired vouchers don't linger as 'active'.
    rows = CreditVoucher.query.order_by(CreditVoucher.issued_date.desc()).all()
    for v in rows:
        refresh_voucher_status(v)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    today = get_business_date()

    # Aggregate
    total_issued    = 0.0
    total_redeemed  = 0.0
    total_outstanding = 0.0
    counts = {'active': 0, 'expired': 0, 'fully_redeemed': 0, 'cancelled': 0}
    records = []
    for v in rows:
        issued    = float(v.issued_amount or 0)
        redeemed  = float(v.redeemed_amount or 0)
        remaining = voucher_remaining(v)
        total_issued   += issued
        total_redeemed += redeemed
        if v.status == 'active':
            total_outstanding += remaining
        counts[v.status] = counts.get(v.status, 0) + 1
        if status_filter and v.status != status_filter:
            continue
        records.append({
            'voucher':      v,
            'guest_name':   v.guest.name if v.guest else '—',
            'issued':       issued,
            'redeemed':     redeemed,
            'remaining':    remaining,
            'status':       v.status,
            'issued_date':  v.issued_date,
            'expiry_date':  v.expiry_date,
            'days_left':    ((v.expiry_date - today).days if v.expiry_date else None),
            'issued_from_reservation': v.issued_from_reservation,
        })

    if fmt == 'excel':
        headers = ['Voucher Code', 'Guest', 'Status', 'Issued (₹)', 'Redeemed (₹)',
                   'Remaining (₹)', 'Issued Date', 'Expiry Date',
                   'Issued From Booking', 'Notes']
        excel_rows = []
        for rec in records:
            v = rec['voucher']
            excel_rows.append([
                v.voucher_code, rec['guest_name'], rec['status'],
                rec['issued'], rec['redeemed'], rec['remaining'],
                v.issued_date.isoformat() if v.issued_date else '',
                v.expiry_date.isoformat() if v.expiry_date else '',
                (v.issued_from_reservation.booking_reference
                  if v.issued_from_reservation and v.issued_from_reservation.booking_reference
                  else (v.issued_from_reservation.id if v.issued_from_reservation else '')),
                v.notes or '',
            ])
        return _excel_response(
            f'voucher_ledger_{today.isoformat()}.xlsx',
            headers, excel_rows,
            title=f'Credit Voucher Ledger as of {today.strftime("%d %b %Y")}'
        )

    return render_template('reports/voucher_ledger.html',
                           records=records,
                           total_issued=total_issued,
                           total_redeemed=total_redeemed,
                           total_outstanding=total_outstanding,
                           counts=counts,
                           status_filter=status_filter,
                           today=today)
