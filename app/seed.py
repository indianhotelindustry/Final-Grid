"""
Demo Data Seeder
================
Two Flask CLI commands:

  flask seed     — Insert ~80 demo records covering every KPI, status, and report section
  flask unseed   — Remove ALL seeded records precisely; zero impact on real data

How it works
------------
* A manifest JSON file is written to  <instance_folder>/seed_manifest.json
* Every seeded primary-key ID is tracked per table so unseed is exact
* init_data() records (Standard room type, 60 rooms, Cash/UPI/Card, settings,
  admin user) are NEVER touched by unseed
* Idempotent: running `flask seed` again will refuse if the manifest already exists
"""

import json
import os
import secrets
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import click
from flask import current_app
from flask.cli import with_appcontext

from app.models import (
    db, User, Shift, RoomType, Room, Guest,
    Reservation, ExtraCharge, Payment, PaymentMode,
    Company, CheckInRecord, MaintenanceRequest, NightAuditLog,
    RatePlan, Settings,
)
from app.services import get_business_date


# ---------------------------------------------------------------------------
# Manifest helpers  (stored as a file, not in the DB, to avoid VARCHAR limits)
# ---------------------------------------------------------------------------

def _manifest_path() -> str:
    return os.path.join(current_app.instance_path, 'seed_manifest.json')


def _load_manifest() -> Optional[dict]:
    p = _manifest_path()
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def _save_manifest(m: dict) -> None:
    os.makedirs(current_app.instance_path, exist_ok=True)
    with open(_manifest_path(), 'w') as f:
        json.dump(m, f, indent=2, default=str)


def _delete_manifest() -> None:
    p = _manifest_path()
    if os.path.exists(p):
        os.remove(p)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _pm(name: str) -> Optional[PaymentMode]:
    pm = PaymentMode.query.filter(PaymentMode.name.ilike(name)).first()
    return pm or PaymentMode.query.filter_by(is_active=True).first()


def _folio(reservation) -> int:
    """The billing folio a seeded financial row belongs to (ADR-002, CD-4).

    Fixtures obey the same contract as production writers, so a seeded
    database is never a standing counterexample to INV-A02.
    """
    from app.services import resolve_billing_folio_id
    return resolve_billing_folio_id(reservation)


def _booking_ref() -> str:
    return 'DEMO' + secrets.token_hex(3).upper()


def _seed_phone() -> str:
    return 'seed_' + secrets.token_hex(5)


# ---------------------------------------------------------------------------
# SEED
# ---------------------------------------------------------------------------

def _do_seed() -> None:
    biz_date: date = get_business_date()

    manifest: Dict = {
        'seeded_at': datetime.utcnow().isoformat(),
        'biz_date': biz_date.isoformat(),
        'users': [],
        'companies': [],
        'guests': [],
        'reservations': [],
        'checkin_records': [],
        'payments': [],
        'extra_charges': [],
        'maintenance_requests': [],
        'night_audit_logs': [],
        'shifts': [],
        'rate_plans': [],
        'room_types_added': [],
    }

    cash = _pm('Cash')
    upi  = _pm('UPI')
    card = _pm('Card')

    # ── 1. Staff Users ──────────────────────────────────────────────────────
    click.echo('  [1/10] Staff users...')
    staff_specs = [
        ('mgr_demo',  'Demo Manager',      'Manager',     'manager123'),
        ('fd_demo',   'Demo FrontDesk',    'FrontDesk',   'frontdesk123'),
        ('acct_demo', 'Demo Accountant',   'Accountant',  'accountant123'),
        ('hk_demo',   'Demo Housekeeping', 'Housekeeping','housekeeping123'),
    ]
    staff_by_role: Dict[str, User] = {}
    for uname, fname, role, pw in staff_specs:
        u = User.query.filter_by(username=uname).first()
        if not u:
            u = User(username=uname, full_name=fname, role=role, is_active=True)
            u.set_password(pw)
            db.session.add(u)
            db.session.flush()
            manifest['users'].append(u.id)
        staff_by_role[role] = u

    manager_user: Optional[User] = (
        staff_by_role.get('Manager')
        or User.query.filter_by(role='Manager').first()
        or User.query.filter_by(role='Admin').first()
    )
    manager_id: int = manager_user.id if manager_user else 1

    # ── 2. Room Types ───────────────────────────────────────────────────────
    click.echo('  [2/10] Room types...')
    rt_specs = [
        ('Deluxe',       2500, 'Deluxe room with city view and premium amenities'),
        ('Suite',        5000, 'Executive suite with separate living area and breakfast'),
        ('Family Room',  3500, 'Spacious family room for 2 adults + 2 children'),
    ]
    room_types: Dict[str, RoomType] = {}
    for rt_name, rate, desc in rt_specs:
        rt = RoomType.query.filter_by(name=rt_name).first()
        if not rt:
            rt = RoomType(name=rt_name, base_rate=rate, description=desc)
            db.session.add(rt)
            db.session.flush()
            manifest['room_types_added'].append(rt.id)
        room_types[rt_name] = rt

    std_rt = RoomType.query.filter_by(name='Standard').first()
    if std_rt:
        room_types['Standard'] = std_rt
    db.session.flush()

    # Re-type some rooms so every room type appears in reports
    if room_types.get('Deluxe'):
        for r in Room.query.filter_by(floor=4, status='Vacant').limit(4).all():
            r.room_type_id = room_types['Deluxe'].id
    if room_types.get('Suite'):
        for r in Room.query.filter_by(floor=5, status='Vacant').limit(2).all():
            r.room_type_id = room_types['Suite'].id
    if room_types.get('Family Room'):
        for r in Room.query.filter_by(floor=3, status='Vacant').limit(4).all():
            r.room_type_id = room_types['Family Room'].id
    db.session.flush()

    # ── 3. Companies ────────────────────────────────────────────────────────
    click.echo('  [3/10] Companies...')
    co_specs = [
        ('Infosys Limited',     500000, 'Rajan Sharma', '9810001001', 'rajan@infosys.example',  '27AAACI1681G1ZK', '27'),
        ('Tata Consultancy',    750000, 'Priya Nair',   '9820002002', 'priya@tcs.example',      '27AAACT2727Q1ZN', '27'),
        ('Reliance Industries', 300000, 'Anil Mehta',   '9830003003', 'anil@ril.example',       '27AAACR5055K1Z5', '27'),
    ]
    companies: List[Company] = []
    for name, limit, contact, phone, email, gstin, sc in co_specs:
        co = Company.query.filter_by(name=name).first()
        if not co:
            co = Company(name=name, credit_limit=limit, credit_used=0,
                         contact_person=contact, phone=phone, email=email,
                         gstin=gstin, state_code=sc, is_active=True)
            db.session.add(co)
            db.session.flush()
            manifest['companies'].append(co.id)
        companies.append(co)
    db.session.flush()

    # ── 4. Guests ────────────────────────────────────────────────────────────
    click.echo('  [4/10] Guests (complete + incomplete KYC)...')
    guest_specs = [
        # (name, phone, email, id_type, id_num, address, company_name)  — 10 complete KYC
        ('Arjun Kapoor',  '9711111101', 'arjun.kapoor@email.com', 'Aadhaar',  '1234 5678 9012', 'B-14 Connaught Place, Delhi',   None),
        ('Sneha Rao',     '9711111102', 'sneha.rao@email.com',    'PAN',      'ABCDE1234F',     'Flat 3A Bandra West, Mumbai',   None),
        ('Vijay Nambiar', '9711111103', 'vijay@email.com',        'Passport', 'P1234567',       '22 MG Road, Bangalore',         'Infosys Limited'),
        ('Meera Patel',   '9711111104', 'meera@email.com',        'Aadhaar',  '2345 6789 0123', '45 Juhu Tara Road, Mumbai',     None),
        ('Rohit Sinha',   '9711111105', 'rohit@email.com',        'Driving',  'DL052018001234', 'Sector 18, Noida',              'Tata Consultancy'),
        ('Kavitha Menon', '9711111106', 'kavitha@email.com',      'Aadhaar',  '3456 7890 1234', 'T Nagar, Chennai',              None),
        ('Suresh Iyer',   '9711111107', 'suresh@email.com',       'PAN',      'BCDEF2345G',     'Koramangala, Bangalore',        None),
        ('Ananya Gupta',  '9711111108', 'ananya@email.com',       'Passport', 'P2345678',       'Dwarka, New Delhi',             'Reliance Industries'),
        ('Devraj Singh',  '9711111109', 'devraj@email.com',       'Aadhaar',  '4567 8901 2345', 'Rajinder Nagar, Patna',         None),
        ('Priya Sharma',  '9711111110', 'priya.s@email.com',      'Driving',  'MH012016005678', 'Powai, Mumbai',                 'Tata Consultancy'),
        # 5 incomplete KYC (no ID proof)
        ('Kiran Bose',    '9711111111', '',                        None,  None, '12 Park Street, Kolkata',  None),
        ('Tanvi Joshi',   '9711111112', 'tanvi@email.com',         None,  None, '',                         None),
        ('Amit Trivedi',  '9711111113', '',                        None,  None, '',                         None),
        ('Ritu Malhotra', '9711111114', 'ritu@email.com',          None,  None, 'Civil Lines, Delhi',       None),
        ('Neeraj Yadav',  '9711111115', '',                        None,  None, '',                         None),
    ]
    # Build or fetch every guest — always produce a full 15-element list
    guests: List[Guest] = []
    for name, phone, email, id_type, id_num, address, co_name in guest_specs:
        g = Guest.query.filter_by(phone=phone).first()
        if not g:
            g = Guest(name=name, phone=phone,
                      email=email or None,
                      id_proof_type=id_type,
                      id_proof_number=id_num,
                      address=address or None,
                      company=co_name)
            db.session.add(g)
            db.session.flush()
            manifest['guests'].append(g.id)
        guests.append(g)
    db.session.flush()

    # ── 5. Reservations ──────────────────────────────────────────────────────
    click.echo('  [5/10] Reservations (all statuses)...')

    def _add_res(g: Guest, rt_name: str, days_offset: int, num_nights: int,
                 status: str, source: str = 'Walk-in',
                 rate: Optional[float] = None,
                 advance: float = 0,
                 adults: int = 1, children: int = 0,
                 special_req: Optional[str] = None) -> Reservation:
        rt = room_types.get(rt_name, room_types.get('Standard'))
        arrival   = biz_date + timedelta(days=days_offset)
        departure = arrival  + timedelta(days=num_nights)
        used_rate = rate if rate is not None else float(rt.base_rate)
        res = Reservation(
            booking_reference=_booking_ref(),
            guest_id=g.id,
            room_type_id=rt.id,
            arrival_date=arrival,
            departure_date=departure,
            adults=adults, children=children,
            rate_per_night=used_rate,
            advance_payment=advance,
            status=status, source=source,
            special_requests=special_req,
            created_at=datetime.utcnow() - timedelta(days=abs(days_offset) + 1),
        )
        db.session.add(res)
        db.session.flush()
        manifest['reservations'].append(res.id)
        return res

    # Grab vacant rooms for assignment
    vacant_pool: List[Room] = Room.query.filter_by(status='Vacant').limit(20).all()
    vpool_idx = [0]  # mutable counter

    def _next_vacant() -> Optional[Room]:
        i = vpool_idx[0]
        if i < len(vacant_pool):
            vpool_idx[0] += 1
            return vacant_pool[i]
        return None

    # 5a — CheckedIn (6 in-house today)
    inhouse_specs = [
        (guests[0],  'Deluxe',      -2, 4, 2200, 'Walk-in',  1, 0, 'High floor please'),
        (guests[1],  'Suite',       -1, 3, 4800, 'OTA',      2, 0, None),
        (guests[2],  'Standard',    -3, 5, 1000, 'Calling',  1, 0, 'Early checkout'),
        (guests[3],  'Family Room', -1, 2, 3200, 'Walk-in',  2, 1, 'Extra cot needed'),
        (guests[4],  'Standard',    -2, 3,  900, 'OTA',      1, 0, None),
        (guests[5],  'Deluxe',      -1, 4, 2400, 'Website',  2, 0, None),
    ]
    inhouse_res: List[Reservation] = []
    for g, rt_name, offset, nn, rate, src, adults, children, req in inhouse_specs:
        res = _add_res(g, rt_name, offset, nn, 'CheckedIn', src,
                       rate=rate, advance=rate,
                       adults=adults, children=children, special_req=req)
        room = _next_vacant()
        if room:
            res.room_id = room.id
            res.checked_in_at = datetime.utcnow() + timedelta(days=offset)
            room.status = 'Occupied'
            # CheckInRecord
            ci = CheckInRecord(
                reservation_id=res.id,
                guest_id=res.guest_id,
                room_id=room.id,
                checkin_date=datetime.utcnow() + timedelta(days=offset),
                checkin_mode='FULL',
                is_profile_complete=bool(g.id_proof_type),
                billing_responsibility='Guest',
                staff_user_id=manager_id,
                deposit_amount=rate,
                deposit_payment_mode_id=cash.id if cash else None,
            )
            db.session.add(ci)
            db.session.flush()
            manifest['checkin_records'].append(ci.id)
            # Advance payment
            if cash:
                p = Payment(reservation_id=res.id, payment_mode_id=cash.id,
                            folio_id=_folio(res),
                            amount=rate, payment_date=biz_date + timedelta(days=offset))
                db.session.add(p)
                db.session.flush()
                manifest['payments'].append(p.id)
        inhouse_res.append(res)
    db.session.flush()

    # 5b — Extra charges for in-house guests
    click.echo('  [6/10] Extra charges...')
    extra_specs = [
        (inhouse_res[0], 'Restaurant - Dinner for 2',   850),
        (inhouse_res[0], 'Laundry - Shirts x3',         210),
        (inhouse_res[1], 'Room Service - Lunch',         650),
        (inhouse_res[1], 'Minibar - Beverages',          480),
        (inhouse_res[2], 'Restaurant - Breakfast',       320),
        (inhouse_res[3], 'Extra Cot',                    500),
        (inhouse_res[4], 'Airport Transfer',             600),
    ]
    for res, desc, amt in extra_specs:
        ec = ExtraCharge(reservation_id=res.id, description=desc,
                         folio_id=_folio(res),
                         amount=amt, charge_date=biz_date)
        db.session.add(ec)
        db.session.flush()
        manifest['extra_charges'].append(ec.id)

    # 5c — Upcoming arrivals
    upcoming_specs = [
        (guests[6],  'Standard',    1, 2, 'Confirmed', 'Website', 1000),
        (guests[7],  'Deluxe',      2, 3, 'Confirmed', 'OTA',     2500),
        (guests[8],  'Suite',       3, 2, 'Reserved',  'Calling', 5000),
        (guests[9],  'Family Room', 4, 4, 'Confirmed', 'Agent',   3500),
        (guests[10], 'Standard',    5, 1, 'Reserved',  'Walk-in', 1000),
        (guests[11], 'Standard',    7, 2, 'Reserved',  'OTA',      950),
    ]
    for g, rt_name, offset, nn, status, src, rate in upcoming_specs:
        _add_res(g, rt_name, offset, nn, status, src, rate=rate, advance=rate)

    # 5d — Past CheckedOut stays
    past_co_specs = [
        (guests[0], 'Standard',  -10, 3, 1000, 'Walk-in'),
        (guests[2], 'Deluxe',     -7, 2, 2500, 'OTA'),
        (guests[5], 'Standard',   -5, 1,  950, 'Calling'),
    ]
    for g, rt_name, offset, nn, rate, src in past_co_specs:
        res = _add_res(g, rt_name, offset, nn, 'CheckedOut', src, rate=rate, advance=rate)
        departure = biz_date + timedelta(days=offset + nn)
        res.checked_in_at  = datetime.combine(biz_date + timedelta(days=offset), datetime.min.time())
        res.checked_out_at = datetime.combine(departure, datetime.min.time())
        if upi:
            p = Payment(reservation_id=res.id, payment_mode_id=upi.id,
                        folio_id=_folio(res),
                        amount=rate * nn, payment_date=departure)
            db.session.add(p)
            db.session.flush()
            manifest['payments'].append(p.id)
    db.session.flush()

    # 5e — Cancelled
    _add_res(guests[12], 'Standard',   2, 2, 'Cancelled', 'OTA',      rate=950)
    _add_res(guests[13], 'Deluxe',     5, 3, 'Cancelled', 'Website',  rate=2400)

    # 5f — NoShow
    _add_res(guests[14], 'Standard',  -1, 1, 'NoShow',    'OTA',      rate=1000)

    # Additional payments (UPI + Card for variety)
    if upi and len(inhouse_res) > 1:
        p = Payment(reservation_id=inhouse_res[1].id, payment_mode_id=upi.id,
                    folio_id=_folio(inhouse_res[1]),
                    amount=4800, payment_date=biz_date)
        db.session.add(p); db.session.flush(); manifest['payments'].append(p.id)
    if card and len(inhouse_res) > 4:
        p = Payment(reservation_id=inhouse_res[4].id, payment_mode_id=card.id,
                    folio_id=_folio(inhouse_res[4]),
                    amount=900, payment_date=biz_date)
        db.session.add(p); db.session.flush(); manifest['payments'].append(p.id)

    # ── 6. Maintenance Requests ──────────────────────────────────────────────
    click.echo('  [7/10] Maintenance requests...')
    maint_rooms: List[Room] = Room.query.filter_by(status='Vacant').order_by(Room.floor).limit(5).all()
    maint_specs = [
        (0, 'Plumbing',   'Bathroom tap dripping continuously',          'High',   'Open',       'Ravi Kumar',   None),
        (1, 'AC/Heating', 'AC not cooling — stuck at 28°C',              'High',   'InProgress', 'Sunil Singh',  'Raj Tech'),
        (2, 'Electrical', 'Bedside lamp not working',                    'Low',    'Resolved',   'Priya FD',     'Anil Elec'),
        (3, 'Furniture',  'Wardrobe hinge broken',                       'Medium', 'Open',       'Meena HK',     None),
        (4, 'Cleaning',   'Deep cleaning required after checkout',       'Low',    'InProgress', 'Meena HK',     'HK Team'),
    ]
    for i, (ri, cat, desc, pri, stat, rep, asgn) in enumerate(maint_specs):
        if ri < len(maint_rooms):
            mr = MaintenanceRequest(
                room_id=maint_rooms[ri].id,
                category=cat, description=desc,
                priority=pri, status=stat,
                reported_by=rep, assigned_to=asgn,
                created_at=datetime.utcnow() - timedelta(hours=6 * (i + 1)),
                resolved_at=(datetime.utcnow() - timedelta(hours=1)) if stat == 'Resolved' else None,
            )
            db.session.add(mr); db.session.flush()
            manifest['maintenance_requests'].append(mr.id)

    # ── 7. Closed Shift ──────────────────────────────────────────────────────
    click.echo('  [8/10] Shift record...')
    fd_user: Optional[User] = (
        staff_by_role.get('FrontDesk')
        or User.query.filter_by(role='FrontDesk').first()
    )
    if fd_user:
        shift = Shift(
            user_id=fd_user.id,
            shift_type='Morning',
            start_time=datetime.utcnow() - timedelta(hours=9),
            end_time=datetime.utcnow() - timedelta(hours=1),
            opening_cash=5000,
            expected_cash=14200,
            declared_closing_cash=14000,
            variance=-200,
            close_notes='Short by ₹200 — possible miscounting at checkout.',
            payment_summary={'Cash': 9200, 'UPI': 3800, 'Card': 1200},
            status='Closed',
            approval_status='approved',
            closed_by_user_id=fd_user.id,
            approved_by_user_id=manager_id,
            approved_at=datetime.utcnow() - timedelta(minutes=30),
        )
        db.session.add(shift); db.session.flush()
        manifest['shifts'].append(shift.id)

    # ── 8. Rate Plans ────────────────────────────────────────────────────────
    click.echo('  [9/10] Rate plans...')
    rp_specs = [
        ('Weekend Premium', 'Weekend',  None,                       3000, 'fixed', None, None, '5,6', 20),
        ('Diwali Special',  'Seasonal', room_types.get('Deluxe'),   3200, 'fixed',
         biz_date + timedelta(days=10), biz_date + timedelta(days=17), None, 30),
        ('Corporate Rate',  'Package',  room_types.get('Standard'),  850, 'fixed', None, None, '0,1,2,3,4', 15),
    ]
    for name, ptype, rt_obj, amt, mode, sd, ed, dow, pri in rp_specs:
        if not RatePlan.query.filter_by(name=name).first():
            rp = RatePlan(
                name=name, plan_type=ptype,
                room_type_id=rt_obj.id if rt_obj else None,
                rate_amount=amt, rate_mode=mode,
                start_date=sd, end_date=ed,
                days_of_week=dow, priority=pri, is_active=True,
            )
            db.session.add(rp); db.session.flush()
            manifest['rate_plans'].append(rp.id)

    # ── 9. Night Audit History (yesterday — completed) ───────────────────────
    click.echo('  [10/10] Night audit history...')
    yesterday = biz_date - timedelta(days=1)
    if not NightAuditLog.query.filter_by(audit_date=yesterday).first():
        snap = {
            'control': {'can_close': True, 'blocker_count': 0, 'warning_count': 1,
                         'total_outstanding': 2200.0},
            'occupancy': {'occupied': 12, 'sellable_rooms': 58, 'occ_pct': 20.7},
            'revenue': {'room_revenue': 18400.0, 'extra_charges_total': 2860.0,
                         'discount_total': 0.0, 'tax_amount': 1923.0,
                         'gross_revenue': 23183.0},
            'payments': {'total_collected': 20983.0,
                          'by_mode': {'Cash': {'amount': 12000.0},
                                       'UPI':  {'amount': 6000.0},
                                       'Card': {'amount': 2983.0}}},
            'exceptions': {
                'blockers': [],
                'warnings': [{'type': 'Pending Checkout',
                               'detail': 'Booking DEMO123: departure overdue, still checked in.'}],
            },
        }
        nal = NightAuditLog(
            audit_date=yesterday,
            run_at=datetime.utcnow() - timedelta(hours=22),
            total_revenue=23183.0,
            total_payments=20983.0,
            outstanding_amount=2200.0,
            occupancy_count=12,
            pending_checkouts=1,
            blocker_count=0, warning_count=1,
            status='Completed',
            completed_at=datetime.utcnow() - timedelta(hours=21, minutes=45),
            snapshot_json=json.dumps(snap),
            run_by_user_id=manager_id,
        )
        db.session.add(nal); db.session.flush()
        manifest['night_audit_logs'].append(nal.id)

    # ── Commit & write manifest file ─────────────────────────────────────────
    db.session.commit()
    _save_manifest(manifest)

    # ── Summary ──────────────────────────────────────────────────────────────
    kyc_complete   = sum(1 for g in guests if g.id_proof_type)
    kyc_incomplete = len(guests) - kyc_complete
    click.echo('')
    click.secho('  ✓ Seeded successfully', fg='green', bold=True)
    click.echo(f"    Staff users    : {len(manifest['users'])}")
    click.echo(f"    Room types     : {len(manifest['room_types_added'])} new (Deluxe, Suite, Family Room)")
    click.echo(f"    Companies      : {len(manifest['companies'])}")
    click.echo(f"    Guests         : {len(manifest['guests'])} "
               f"  (KYC complete: {kyc_complete}, incomplete: {kyc_incomplete})")
    click.echo(f"    Reservations   : {len(manifest['reservations'])} "
               "(CheckedIn, Confirmed, Reserved, CheckedOut, Cancelled, NoShow)")
    click.echo(f"    Payments       : {len(manifest['payments'])}")
    click.echo(f"    Extra charges  : {len(manifest['extra_charges'])}")
    click.echo(f"    Maintenance    : {len(manifest['maintenance_requests'])}")
    click.echo(f"    Shifts         : {len(manifest['shifts'])}")
    click.echo(f"    Rate plans     : {len(manifest['rate_plans'])}")
    click.echo(f"    Audit logs     : {len(manifest['night_audit_logs'])}")
    click.echo('')
    click.secho('  Demo logins:', fg='cyan')
    click.echo('    Manager      mgr_demo   / manager123')
    click.echo('    FrontDesk    fd_demo    / frontdesk123')
    click.echo('    Accountant   acct_demo  / accountant123')
    click.echo('    Housekeeping hk_demo    / housekeeping123')
    click.echo(f'\n  Manifest saved → {_manifest_path()}\n')


# ---------------------------------------------------------------------------
# UNSEED
# ---------------------------------------------------------------------------

def _do_unseed() -> None:
    manifest = _load_manifest()
    if not manifest:
        click.secho('  No seed manifest found — nothing to unseed.', fg='yellow')
        return

    click.echo(f"  Manifest from: {manifest.get('seeded_at', 'unknown')}")

    def _del(model, ids: list, label: str) -> None:
        if not ids:
            return
        n = model.query.filter(model.id.in_(ids)).delete(synchronize_session=False)
        click.echo(f'    Removed {n:>3}  {label}')

    # Delete in reverse dependency order
    _del(Shift,              manifest.get('shifts', []),               'shifts')
    _del(NightAuditLog,      manifest.get('night_audit_logs', []),     'night audit logs')
    _del(MaintenanceRequest, manifest.get('maintenance_requests', []), 'maintenance requests')
    _del(ExtraCharge,        manifest.get('extra_charges', []),        'extra charges')
    _del(Payment,            manifest.get('payments', []),             'payments')
    _del(CheckInRecord,      manifest.get('checkin_records', []),      'checkin records')
    _del(RatePlan,           manifest.get('rate_plans', []),           'rate plans')
    _del(Reservation,        manifest.get('reservations', []),         'reservations')
    _del(Guest,              manifest.get('guests', []),               'guests')

    # Restore rooms that were re-typed back to Standard
    std = RoomType.query.filter_by(name='Standard').first()
    rt_ids = manifest.get('room_types_added', [])
    if std and rt_ids:
        Room.query.filter(Room.room_type_id.in_(rt_ids)).update(
            {'room_type_id': std.id}, synchronize_session=False
        )
        click.echo('      Restored room types → Standard')
        _del(RoomType, rt_ids, 'room types (Deluxe/Suite/Family)')

    _del(Company, manifest.get('companies', []), 'companies')
    _del(User,    manifest.get('users', []),     'staff users')

    # Reset rooms that seed set to Occupied back to Vacant
    Room.query.filter_by(status='Occupied').update(
        {'status': 'Vacant'}, synchronize_session=False
    )
    click.echo('      Reset Occupied rooms → Vacant')

    db.session.commit()
    _delete_manifest()
    click.secho('  ✓ All demo data removed. Database is clean.\n', fg='green', bold=True)


# ---------------------------------------------------------------------------
# Flask CLI registration
# ---------------------------------------------------------------------------

@click.command('seed')
@with_appcontext
def seed_command() -> None:
    """Insert demo data for testing (guests, reservations, payments, maintenance…)."""
    if _load_manifest():
        click.secho(
            '\n  Demo data already exists. Run  flask unseed  first.\n',
            fg='yellow'
        )
        return
    click.echo('\n  Seeding demo data...')
    try:
        _do_seed()
    except Exception as exc:
        db.session.rollback()
        click.secho(f'\n  ERROR: {exc}', fg='red')
        import traceback; traceback.print_exc()


@click.command('unseed')
@with_appcontext
def unseed_command() -> None:
    """Remove all demo data created by  flask seed  — safe for production records."""
    click.echo('\n  Removing demo data...')
    try:
        _do_unseed()
    except Exception as exc:
        db.session.rollback()
        click.secho(f'\n  ERROR: {exc}', fg='red')
        import traceback; traceback.print_exc()
