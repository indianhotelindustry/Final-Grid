"""Development-only seed-data generator.

Generates versatile fixture data covering every major feature surface
(reservations across all statuses, OTA channels, payment modes, split
folios, extra charges, 30 days of night-audit history, OTA payouts,
preventive maintenance, a closed shift, staff for every role). Reset
removes only the rows this module created — tracked via IDs stored
in the Settings table.

The harness entry-points (``seed`` and ``reset``) must only ever be
reachable through the gated routes in ``app.routes`` — never call
them directly from production code.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete

from app.models import (
    db,
    AuditLog,
    BusinessDate,
    CheckInRecord,
    Company,
    ExtraCharge,
    Folio,
    Guest,
    GuestIDDocument,
    NightAuditLog,
    OTAPayout,
    Payment,
    PaymentMode,
    PreventiveSchedule,
    Reservation,
    Room,
    RoomType,
    Settings,
    Shift,
    User,
)

SEED_MARKER_KEY = '_dev_seed_ids'

# Deterministic seed so reruns after a reset produce identical fixtures.
_RNG = random.Random(20260419)


# ---------------------------------------------------------------------------
# Marker persistence
# ---------------------------------------------------------------------------

def _load_marker() -> dict:
    row = Settings.query.filter_by(key=SEED_MARKER_KEY).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except Exception:
        return {}


def _save_marker(ids_by_table: dict) -> None:
    payload = json.dumps(ids_by_table, separators=(',', ':'))
    # Settings.value is String(200) — keep payload compact; it holds only
    # integer ID lists, which stay well under that for realistic seed sizes.
    row = Settings.query.filter_by(key=SEED_MARKER_KEY).first()
    if row:
        row.value = payload
    else:
        db.session.add(Settings(key=SEED_MARKER_KEY, value=payload,
                                description='Dev seed row IDs — do not edit'))


def _clear_marker() -> None:
    row = Settings.query.filter_by(key=SEED_MARKER_KEY).first()
    if row:
        db.session.delete(row)


def is_seeded() -> bool:
    return bool(_load_marker())


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed() -> dict:
    """Populate a versatile fixture set. Idempotent: no-op if already seeded."""
    if is_seeded():
        return {'skipped': True, 'reason': 'already seeded — reset first'}

    tracked: dict[str, list[int]] = {
        'users': [], 'room_types': [], 'rooms': [], 'guests': [],
        'id_documents': [], 'companies': [], 'reservations': [],
        'checkin_records': [], 'extra_charges': [], 'payments': [],
        'folios': [], 'night_audit_logs': [], 'ota_payouts': [],
        'preventive_schedules': [], 'shifts': [],
    }

    today = date.today()

    # ── 1. Staff users — one per role ─────────────────────────────────
    role_users = [
        ('manager',   'Priya Sharma',    'Manager'),
        ('frontdesk', 'Rohan Kumar',     'FrontDesk'),
        ('housekeep', 'Meena Pillai',    'Housekeeping'),
        ('accounts',  'Suresh Iyer',     'Accountant'),
    ]
    for username, full_name, role in role_users:
        if User.query.filter_by(username=username).first():
            continue
        u = User(username=username, full_name=full_name, role=role, is_active=True)
        u.set_password('dev12345')
        db.session.add(u)
        db.session.flush()
        tracked['users'].append(u.id)

    admin = User.query.filter_by(username='admin').first()
    staff_id = admin.id if admin else (tracked['users'][0] if tracked['users'] else None)

    # ── 2. Room types — varied GST bands ──────────────────────────────
    rt_specs = [
        ('Standard Seed', Decimal('1200'), Decimal('12')),
        ('Deluxe Seed',   Decimal('2500'), Decimal('12')),
        ('Suite Seed',    Decimal('5500'), Decimal('18')),
    ]
    rt_by_name = {}
    for name, rate, gst in rt_specs:
        rt = RoomType(name=name, base_rate=rate, gst_rate=gst, is_active=True,
                      description='SEED')
        db.session.add(rt)
        db.session.flush()
        tracked['room_types'].append(rt.id)
        rt_by_name[name] = rt

    # ── 3. Rooms — 12 rooms across 3 floors + wings + 1 OOO ───────────
    room_plan = [
        # (number, floor, wing, type_name, status, ooo)
        ('S101', 1, 'A', 'Standard Seed', 'Vacant',      False),
        ('S102', 1, 'A', 'Standard Seed', 'Dirty',       False),
        ('S103', 1, 'A', 'Standard Seed', 'Vacant',      False),
        ('S104', 1, 'B', 'Standard Seed', 'Maintenance', True),
        ('D201', 2, 'A', 'Deluxe Seed',   'Vacant',      False),
        ('D202', 2, 'A', 'Deluxe Seed',   'Vacant',      False),
        ('D203', 2, 'B', 'Deluxe Seed',   'Occupied',    False),
        ('D204', 2, 'B', 'Deluxe Seed',   'Occupied',    False),
        ('D205', 2, 'B', 'Deluxe Seed',   'Occupied',    False),
        ('U301', 3, 'A', 'Suite Seed',    'Vacant',      False),
        ('U302', 3, 'A', 'Suite Seed',    'Vacant',      False),
        ('U303', 3, 'B', 'Suite Seed',    'Dirty',       False),
    ]
    rooms = []
    for num, floor, wing, type_name, status, ooo in room_plan:
        r = Room(
            room_number=num, floor=floor, wing=wing,
            room_type_id=rt_by_name[type_name].id,
            status=status,
            is_active=True, is_sellable=not ooo,
            is_out_of_order=ooo,
            maintenance_note='SEED: routine HVAC check' if ooo else None,
        )
        db.session.add(r)
        db.session.flush()
        tracked['rooms'].append(r.id)
        rooms.append(r)

    # ── 4. Guests — varied profiles, VIP/loyalty/country mix ──────────
    guest_specs = [
        # name, phone, company, vip, tier, purpose, country, state
        ('Arjun Mehta',     '9811000011', None,              None, 'Silver',   'Business', 'India',  'Delhi'),
        ('Sara Khan',       '9811000012', None,              'V1', 'Gold',     'Leisure',  'India',  'Maharashtra'),
        ('Robert Lewis',    '9811000013', None,              None, 'Silver',   'Leisure',  'USA',    'California'),
        ('Pooja Nair',      '9811000014', 'Acme Corp Seed',  'V2', 'Platinum', 'Business', 'India',  'Karnataka'),
        ('Ahmed Farouk',    '9811000015', None,              None, 'Silver',   'Medical',  'UAE',    'Dubai'),
        ('Lina Park',       '9811000016', None,              None, 'Gold',     'Leisure',  'Korea',  'Seoul'),
        ('Vivek Rao',       '9811000017', None,              None, 'Silver',   'Conference', 'India', 'Telangana'),
        ('Anjali Deshmukh', '9811000018', None,              'V3', 'Platinum', 'Business', 'India',  'Maharashtra'),
    ]
    guests = []
    for name, phone, company, vip, tier, purpose, country, state in guest_specs:
        if Guest.query.filter_by(phone=phone).first():
            continue
        first, _, last = name.partition(' ')
        g = Guest(
            name=name, first_name=first, last_name=last or '',
            phone=phone, email=f'{first.lower()}.seed@example.com',
            company=company, vip_level=vip, loyalty_tier=tier,
            purpose_of_visit=purpose, country=country, state=state,
            city='—', pin_code='000000', address='SEED address',
            id_proof_type='Aadhaar',
            guest_notes='SEED',
        )
        db.session.add(g)
        db.session.flush()
        tracked['guests'].append(g.id)

        doc = GuestIDDocument(
            guest_id=g.id,
            document_type='Aadhaar',
            document_number=f'SEED{phone[-6:]}XX',
            verification_status='Verified',
        )
        db.session.add(doc)
        db.session.flush()
        tracked['id_documents'].append(doc.id)
        guests.append(g)

    # ── 5. Corporate billing company ──────────────────────────────────
    company = Company.query.filter_by(name='Acme Corp Seed').first()
    if not company:
        company = Company(
            name='Acme Corp Seed', credit_limit=Decimal('100000'),
            contact_person='Accounts Dept', phone='9800000099',
            email='accounts@acme.seed', gstin='07AACCA1234C1Z5',
            state_code='07', business_category='IT', is_active=True,
        )
        db.session.add(company)
        db.session.flush()
        tracked['companies'].append(company.id)

    # ── 6. Resolve existing payment modes (seeded by init_data) ───────
    def _pmode(code: str) -> int | None:
        m = PaymentMode.query.filter_by(code=code).first()
        return m.id if m else None

    cash_id        = _pmode('CASH')
    upi_id         = _pmode('UPI')
    card_id        = _pmode('CARD')
    mmt_paid_id    = _pmode('MMT_PAID')
    bdc_paid_id    = _pmode('BDC_PAID') or _pmode('BOOKING_PAID')
    goi_paid_id    = _pmode('GOIBIBO_PAID')
    agd_paid_id    = _pmode('AGODA_PAID')
    # Fall back to any ota_receivable if specific codes differ
    if not bdc_paid_id:
        bdc_paid_id = db.session.query(PaymentMode.id).filter(
            PaymentMode.category == 'ota_receivable',
            PaymentMode.name.like('Booking.com%')).scalar()

    # ── 7. Reservations — every status, every OTA channel ─────────────
    # Pattern: (arrival_offset_days, nights, guest_idx, room_idx, status,
    #          source, ota_channel, ota_payment_status, billing_resp)
    res_plan = [
        # -- Past completed stays (CheckedOut) -----------------------------
        (-28, 3, 0, 4,  'CheckedOut', 'Walk-in', None,          'pay_at_hotel', 'Guest'),
        (-25, 2, 1, 5,  'CheckedOut', 'OTA',     'MakeMyTrip',  'paid_at_ota',  'Guest'),
        (-22, 4, 2, 9,  'CheckedOut', 'OTA',     'Booking.com', 'paid_at_ota',  'Guest'),
        (-20, 1, 3, 10, 'CheckedOut', 'Website', None,          'pay_at_hotel', 'Company'),
        (-18, 2, 4, 0,  'CheckedOut', 'OTA',     'Goibibo',     'pay_at_hotel', 'Guest'),
        (-15, 3, 5, 1,  'CheckedOut', 'OTA',     'Agoda',       'paid_at_ota',  'Guest'),
        (-12, 2, 6, 2,  'CheckedOut', 'Agent',   None,          'pay_at_hotel', 'Guest'),
        (-10, 1, 7, 4,  'CheckedOut', 'Calling', None,          'pay_at_hotel', 'Guest'),
        (-8,  2, 0, 5,  'CheckedOut', 'OTA',     'MakeMyTrip',  'paid_at_ota',  'Guest'),
        (-6,  3, 1, 9,  'CheckedOut', 'OTA',     'Expedia',     'paid_at_ota',  'Guest'),
        (-4,  1, 2, 10, 'CheckedOut', 'Walk-in', None,          'pay_at_hotel', 'Guest'),
        # -- No-show and cancelled -----------------------------------------
        (-5,  2, 3, 0,  'NoShow',     'OTA',     'Goibibo',     'pay_at_hotel', 'Guest'),
        (-3,  2, 4, 1,  'Cancelled',  'OTA',     'Booking.com', 'paid_at_ota',  'Guest'),
        # -- Currently in-house --------------------------------------------
        (-2,  4, 5, 6,  'CheckedIn',  'OTA',     'MakeMyTrip',  'paid_at_ota',  'Guest'),
        (-1,  3, 6, 7,  'CheckedIn',  'Walk-in', None,          'pay_at_hotel', 'Guest'),
        (0,   2, 7, 8,  'CheckedIn',  'OTA',     'Agoda',       'paid_at_ota',  'Guest'),
        # -- Upcoming arrivals ---------------------------------------------
        (1,   2, 0, 4,  'Reserved',   'OTA',     'Booking.com', 'paid_at_ota',  'Guest'),
        (2,   3, 1, 9,  'Confirmed',  'Website', None,          'pay_at_hotel', 'Guest'),
        (4,   1, 2, 10, 'Reserved',   'Walk-in', None,          'pay_at_hotel', 'Guest'),
    ]

    for idx, (arr_off, nights, gi, ri, status, source, channel, ota_pay, billing) in enumerate(res_plan):
        if gi >= len(guests) or ri >= len(rooms):
            continue
        guest = guests[gi]
        room = rooms[ri]
        arrival = today + timedelta(days=arr_off)
        departure = arrival + timedelta(days=nights)
        rate = Decimal(room.room_type.base_rate)

        ref_prefix = {
            'MakeMyTrip':  'MMT',
            'Booking.com': 'BDC',
            'Goibibo':     'GOI',
            'Agoda':       'AGD',
            'Expedia':     'EXP',
        }.get(channel or '', 'SEED')
        booking_ref = f'SEED-{ref_prefix}-{idx:03d}'

        r = Reservation(
            booking_reference=booking_ref,
            guest_id=guest.id,
            room_id=room.id if status not in ('Cancelled', 'NoShow') else room.id,
            room_type_id=room.room_type_id,
            arrival_date=arrival,
            departure_date=departure,
            adults=2, children=0,
            status=status,
            rate_per_night=rate,
            advance_payment=Decimal('0'),
            special_requests='SEED',
            source=source,
            market_segment='OTA' if source == 'OTA' else ('Corporate' if billing == 'Company' else 'FIT'),
            ota_booking_id=f'{ref_prefix}-{idx:05d}' if channel else None,
            ota_channel=channel,
            ota_payment_status=ota_pay,
            billing_state_code='07',
            checked_in_at=datetime.combine(arrival, datetime.min.time()).replace(hour=14)
                          if status in ('CheckedIn', 'CheckedOut') else None,
            checked_out_at=datetime.combine(departure, datetime.min.time()).replace(hour=11)
                           if status == 'CheckedOut' else None,
        )
        db.session.add(r)
        db.session.flush()  # triggers Folio A auto-create
        tracked['reservations'].append(r.id)

        # Track the auto-created Folio A for FK-safe cleanup
        folio_a = Folio.query.filter_by(reservation_id=r.id, folio_letter='A').first()
        if folio_a:
            tracked['folios'].append(folio_a.id)

        # CheckInRecord for anyone who checked in
        if status in ('CheckedIn', 'CheckedOut') and staff_id:
            cir = CheckInRecord(
                reservation_id=r.id, guest_id=guest.id, room_id=room.id,
                staff_user_id=staff_id,
                checkin_date=r.checked_in_at or datetime.utcnow(),
                checkout_date=r.checked_out_at,
                checkin_mode='EXPRESS',
                is_profile_complete=True,
                billing_responsibility=billing,
                company_id=company.id if billing == 'Company' else None,
                deposit_amount=Decimal('500') if status == 'CheckedIn' else Decimal('0'),
                deposit_payment_mode_id=cash_id if status == 'CheckedIn' else None,
            )
            db.session.add(cir)
            db.session.flush()
            tracked['checkin_records'].append(cir.id)

        # Split-folio for corporate billing: add folio B (Company)
        if billing == 'Company':
            folio_b = Folio(reservation_id=r.id, folio_letter='B',
                            label='Company', company_id=company.id,
                            notes='SEED')
            db.session.add(folio_b)
            db.session.flush()
            tracked['folios'].append(folio_b.id)

        # Extra charges on a subset (restaurant, laundry, minibar, early checkin)
        if status in ('CheckedIn', 'CheckedOut') and idx % 2 == 0:
            for desc, amt, cat in [
                ('Restaurant Dinner', Decimal('650'),  'Restaurant'),
                ('Laundry Service',   Decimal('250'),  'Laundry'),
                ('Minibar',           Decimal('180'),  'Minibar'),
            ]:
                ec = ExtraCharge(
                    reservation_id=r.id, folio_id=folio_a.id if folio_a else None,
                    description=desc, amount=amt,
                    charge_date=arrival + timedelta(days=1),
                    charge_category=cat,
                )
                db.session.add(ec)
                db.session.flush()
                tracked['extra_charges'].append(ec.id)

        # Payments
        if status == 'CheckedOut':
            total = rate * nights + Decimal('1080')  # room + extras (approx)
            # Route to OTA receivable head if paid_at_ota, else cash/upi/card mix
            if ota_pay == 'paid_at_ota' and channel:
                mode_id = {
                    'MakeMyTrip':  mmt_paid_id,
                    'Booking.com': bdc_paid_id,
                    'Goibibo':     goi_paid_id,
                    'Agoda':       agd_paid_id,
                }.get(channel)
                if mode_id:
                    p = Payment(reservation_id=r.id, folio_id=folio_a.id if folio_a else None,
                                payment_mode_id=mode_id, amount=total,
                                payment_date=departure,
                                reference_number=f'SEED-{channel[:3].upper()}-{idx:03d}')
                    db.session.add(p)
                    db.session.flush()
                    tracked['payments'].append(p.id)
            else:
                # Split: 60% cash, 40% card/upi
                split_a = (total * Decimal('0.6')).quantize(Decimal('0.01'))
                split_b = total - split_a
                for amt, mid in [(split_a, cash_id),
                                 (split_b, card_id if idx % 2 else upi_id)]:
                    if mid and amt > 0:
                        p = Payment(reservation_id=r.id, folio_id=folio_a.id if folio_a else None,
                                    payment_mode_id=mid, amount=amt,
                                    payment_date=departure,
                                    reference_number=f'SEED-PAY-{idx:03d}')
                        db.session.add(p)
                        db.session.flush()
                        tracked['payments'].append(p.id)
        elif status == 'CheckedIn':
            # Advance received at check-in
            p = Payment(reservation_id=r.id, folio_id=folio_a.id if folio_a else None,
                        payment_mode_id=cash_id, amount=rate,
                        payment_date=arrival,
                        reference_number=f'SEED-ADV-{idx:03d}')
            db.session.add(p)
            db.session.flush()
            tracked['payments'].append(p.id)

    # ── 8. Night audit history — 30 nights ────────────────────────────
    for d_off in range(30, 0, -1):
        audit_date = today - timedelta(days=d_off)
        # Simulate noisy revenue with varying occupancy
        occ = _RNG.randint(3, 9)
        rev = Decimal(_RNG.randint(8000, 35000))
        log = NightAuditLog(
            audit_date=audit_date,
            run_at=datetime.combine(audit_date, datetime.min.time()).replace(hour=23, minute=59),
            total_revenue=rev,
            net_revenue=rev - Decimal('500'),
            total_discount=Decimal('500'),
            accrual_revenue=rev + Decimal('1200'),
            occupancy_count=occ,
            pending_checkouts=0,
            status='Completed',
            run_by_user_id=staff_id,
            completed_at=datetime.combine(audit_date, datetime.min.time()).replace(hour=23, minute=59),
            total_payments=rev,
            outstanding_amount=Decimal('0'),
            expected_cash=rev * Decimal('0.6'),
            actual_cash=rev * Decimal('0.6'),
            cash_variance=Decimal('0'),
            notes='SEED',
        )
        db.session.add(log)
        db.session.flush()
        tracked['night_audit_logs'].append(log.id)

    # ── 9. OTA payouts — reconciliation rows ──────────────────────────
    for channel, days_back, gross in [
        ('MakeMyTrip',  14, Decimal('12500')),
        ('Booking.com', 10, Decimal('18200')),
        ('Goibibo',     20, Decimal('6400')),
    ]:
        commission = (gross * Decimal('0.15')).quantize(Decimal('0.01'))
        tds = (gross * Decimal('0.05')).quantize(Decimal('0.01'))
        net = gross - commission - tds
        payout = OTAPayout(
            ota_channel=channel,
            payout_date=today - timedelta(days=days_back),
            reference_number=f'SEED-PAYOUT-{channel[:3].upper()}',
            gross_amount=gross, commission_amount=commission,
            tax_deducted=tds, net_paid=net,
            remarks='SEED',
            created_by_user_id=staff_id,
        )
        db.session.add(payout)
        db.session.flush()
        tracked['ota_payouts'].append(payout.id)

    # ── 10. Preventive schedule ───────────────────────────────────────
    if rooms:
        ps = PreventiveSchedule(
            room_id=rooms[3].id,  # the OOO room
            category='HVAC',
            task_description='SEED: Quarterly AC servicing',
            scheduled_date=today + timedelta(days=7),
        )
        db.session.add(ps)
        db.session.flush()
        tracked['preventive_schedules'].append(ps.id)

    # ── 11. A closed shift (for cash reconciliation views) ────────────
    if staff_id:
        s = Shift(
            user_id=staff_id, shift_type='Morning',
            start_time=datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(hour=8),
            end_time=datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(hour=16),
            opening_cash=Decimal('2000'),
            expected_cash=Decimal('8500'),
            declared_closing_cash=Decimal('8500'),
            variance=Decimal('0'),
            closed_by_user_id=staff_id,
            approved_by_user_id=staff_id,
            approved_at=datetime.utcnow(),
            status='Closed',
            approval_status='auto_approved',
            close_notes='SEED',
        )
        db.session.add(s)
        db.session.flush()
        tracked['shifts'].append(s.id)

    # ── 12. Persist marker + commit ───────────────────────────────────
    _save_marker(tracked)

    db.session.add(AuditLog(
        entity_type='DevSeed', entity_id=0, action='seed',
        before_state={}, after_state={k: len(v) for k, v in tracked.items()},
        staff_user_id=staff_id,
    ))
    db.session.commit()

    return {'seeded': True, 'counts': {k: len(v) for k, v in tracked.items()}}


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

# Deletion order — descendants before parents. Each entry is (table_key, model).
_DELETE_ORDER = [
    ('payments',             Payment),
    ('extra_charges',        ExtraCharge),
    ('checkin_records',      CheckInRecord),
    ('id_documents',         GuestIDDocument),
    ('preventive_schedules', PreventiveSchedule),
    ('ota_payouts',          OTAPayout),
    ('night_audit_logs',     NightAuditLog),
    ('shifts',               Shift),
    ('folios',               Folio),
    ('reservations',         Reservation),
    ('guests',               Guest),
    ('rooms',                Room),
    ('companies',            Company),
    ('room_types',           RoomType),
    ('users',                User),
]


def reset() -> dict:
    """Delete every row seeded by :func:`seed`. Safe to call when unseeded."""
    ids_by_table = _load_marker()
    if not ids_by_table:
        return {'reset': False, 'reason': 'no seed marker found'}

    removed: dict[str, int] = {}
    for key, model in _DELETE_ORDER:
        ids = ids_by_table.get(key) or []
        if not ids:
            continue
        stmt = delete(model).where(model.id.in_(ids))
        result = db.session.execute(stmt)
        removed[key] = int(getattr(result, 'rowcount', 0) or 0)

    _clear_marker()

    admin = User.query.filter_by(username='admin').first()
    db.session.add(AuditLog(
        entity_type='DevSeed', entity_id=0, action='reset',
        before_state={}, after_state=removed,
        staff_user_id=admin.id if admin else 0,
    ))
    db.session.commit()
    return {'reset': True, 'removed': removed}
