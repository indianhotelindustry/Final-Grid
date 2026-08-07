from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash
from app.encryption import EncryptedString

db = SQLAlchemy()


# ---------------------------------------------------------------------------
# User & Shift models
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        db.CheckConstraint("role IN ('Admin','Manager','FrontDesk','Housekeeping','Accountant')", name='ck_user_role'),
    )
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False, unique=True)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # Roles: Admin, Manager, FrontDesk, Housekeeping, Accountant
    role = db.Column(db.String(20), nullable=False, default='FrontDesk')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    failed_login_count = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)
    is_app_owner = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *roles):
        return self.role in roles

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Shift(db.Model):
    __tablename__ = 'shifts'
    __table_args__ = (
        db.CheckConstraint("status IN ('Open','PendingApproval','Closed')", name='ck_shift_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shift_type = db.Column(db.String(20), nullable=False)   # Morning, Evening, Night
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    opening_cash = db.Column(db.Numeric(10, 2), default=0)
    closing_cash = db.Column(db.Numeric(10, 2))             # legacy — kept for compatibility
    # Reconciliation fields
    expected_cash = db.Column(db.Numeric(10, 2))            # system-calculated at close time
    declared_closing_cash = db.Column(db.Numeric(10, 2))    # staff-entered
    variance = db.Column(db.Numeric(10, 2))                 # declared - expected
    close_notes = db.Column(db.Text)
    payment_summary = db.Column(db.JSON)                    # {mode_name: total} snapshot
    closed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    # Open | PendingApproval | Closed
    status = db.Column(db.String(20), default='Open')
    # auto_approved | pending_approval | approved | override_approved
    approval_status = db.Column(db.String(20))
    notes = db.Column(db.Text)
    user = db.relationship('User', foreign_keys=[user_id], backref='shifts')
    closed_by = db.relationship('User', foreign_keys=[closed_by_user_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_user_id])
    adjustments = db.relationship('ShiftAdjustment', backref='shift', lazy='dynamic')


class ShiftAdjustment(db.Model):
    """Cash adjustments recorded against a shift before closing (payouts, float changes)."""
    __tablename__ = 'shift_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=False)
    # payout | float_add | float_remove | petty_cash
    adjustment_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User')

class IDVerificationStatus(Enum):
    PENDING = 'Pending'
    VERIFIED = 'Verified'
    REJECTED = 'Rejected'

class BillingResponsibility(Enum):
    GUEST = 'Guest'
    COMPANY = 'Company'

class BusinessDate(db.Model):
    """Singleton row — only one business date record should ever exist.
    Enforced at application level: init_data() only inserts if not BusinessDate.query.first().
    """
    __tablename__ = 'business_date'
    id = db.Column(db.Integer, primary_key=True)
    current_date = db.Column(db.Date, nullable=False, default=date.today)
    is_locked = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class RoomType(db.Model):
    __tablename__ = 'room_types'
    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(50), nullable=False, unique=True)
    base_rate        = db.Column(db.Numeric(10, 2), nullable=False)  # always pre-tax (excl. GST)
    description      = db.Column(db.String(200))
    floor_number     = db.Column(db.String(30))
    gst_rate         = db.Column(db.Numeric(5, 2), default=0)
    gst_exempted     = db.Column(db.Boolean, default=False)
    is_gst_inclusive = db.Column(db.Boolean, default=False)  # True = admin entered inclusive price
    is_active        = db.Column(db.Boolean, default=True)

class Room(db.Model):
    __tablename__ = 'rooms'
    __table_args__ = (
        db.CheckConstraint("status IN ('Vacant','Occupied','Dirty','Maintenance')", name='ck_room_status'),
    )
    id                  = db.Column(db.Integer, primary_key=True)
    room_number         = db.Column(db.String(10), nullable=False, unique=True)
    room_name           = db.Column(db.String(100))                          # optional friendly name
    floor               = db.Column(db.Integer, nullable=False)
    wing                = db.Column(db.String(50))                           # A / B / North / South
    room_type_id        = db.Column(db.Integer, db.ForeignKey('room_types.id'), nullable=False)
    status              = db.Column(db.String(20), default='Vacant')         # Vacant, Occupied, Dirty, Maintenance
    max_adults          = db.Column(db.Integer, default=2)
    max_children        = db.Column(db.Integer, default=2)
    extra_bed_allowed   = db.Column(db.Boolean, default=False)
    is_active           = db.Column(db.Boolean, default=True)                # visible in system
    is_sellable         = db.Column(db.Boolean, default=True)                # can be assigned to guests
    is_out_of_order     = db.Column(db.Boolean, default=False)               # OOO flag
    maintenance_note    = db.Column(db.Text)
    sort_order          = db.Column(db.Integer, default=0)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    room_type           = db.relationship('RoomType', backref='rooms')

class PaymentMode(db.Model):
    """
    Settlement Head — captures both direct-payment modes and OTA receivable heads.

    category:
      - 'direct_payment'  : cash, UPI, card, bank transfer — money received from guest
      - 'ota_receivable'  : MMT Paid, Goibibo Paid, etc. — revenue settled via OTA,
                            becomes a receivable until OTA pays us.
    code: short machine identifier (e.g. 'CASH', 'MMT_PAID', 'GOIBIBO_PAID')
          used for OTA source mapping and reporting.
    """
    __tablename__ = 'payment_modes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    code = db.Column(db.String(30), nullable=True, unique=True)
    category = db.Column(db.String(20), nullable=False, default='direct_payment')
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.CheckConstraint(
            "category IN ('direct_payment','ota_receivable')",
            name='ck_payment_mode_category'),
    )

class Guest(db.Model):
    __tablename__ = 'guests'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)       # legacy full name (kept for backward compat)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100))
    company = db.Column(db.String(100))
    id_proof_type = db.Column(db.String(50))
    id_proof_number = db.Column(EncryptedString())
    address = db.Column(db.Text)
    country = db.Column(db.String(60), default='India')
    state = db.Column(db.String(60))
    city = db.Column(db.String(60))
    pin_code = db.Column(db.String(10))
    vip_level = db.Column(db.String(5), nullable=True)       # V1, V2, V3, V4, V5 (None = not VIP)
    loyalty_number = db.Column(db.String(30), nullable=True)  # loyalty program membership
    guest_notes = db.Column(db.Text, nullable=True)           # internal notes about guest preferences
    total_stays = db.Column(db.Integer, default=0)            # auto-incremented on checkout
    loyalty_tier = db.Column(db.String(20), default='Silver')  # Current tier: Silver, Gold, Platinum
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10), nullable=True)             # Male | Female | Other
    purpose_of_visit = db.Column(db.String(50), nullable=True)   # Business | Leisure | Medical | Education | Conference | Other
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Aliases and computed properties
    @property
    def display_name(self):
        """Return 'first_name last_name' if split, else legacy 'name'."""
        if self.first_name:
            return f'{self.first_name} {self.last_name or ""}'.strip()
        return self.name

    def ensure_structured_name(self):
        """Populate first_name/last_name from legacy name if not already set.

        Split rule: first word → first_name, rest → last_name.
        Persists the values so it only needs to happen once per guest.
        """
        if self.first_name:
            return  # already structured
        raw = (self.name or '').strip()
        if not raw:
            return
        parts = raw.split(None, 1)
        self.first_name = parts[0]
        self.last_name = parts[1] if len(parts) > 1 else ''
        # Keep legacy name field in sync
        self.name = self.display_name

    @staticmethod
    def set_name(guest, first_name, last_name=None):
        """Set both structured and legacy name fields consistently."""
        guest.first_name = (first_name or '').strip()
        guest.last_name = (last_name or '').strip()
        guest.name = f'{guest.first_name} {guest.last_name}'.strip()

    @property
    def id_type(self):
        return self.id_proof_type

    @property
    def id_number(self):
        return self.id_proof_number

    def is_kyc_complete(self):
        """
        Check if guest profile meets KYC requirements:
        1. first_name + last_name filled
        2. Valid 10-digit mobile (no leading 0, not all zeros)
        3. state, city, pin_code, address filled
        4. id_proof_type + id_proof_number filled
        5. Guest photo exists (checked via most recent CheckInRecord)
        6. ID front + back attached (GuestIDDocument)
        """
        import re as _re
        # 1. Name
        if not (self.first_name or '').strip() or not (self.last_name or '').strip():
            return False
        # 2. Phone: 10 digits, no leading 0, not all zeros
        phone = (self.phone or '').strip().lstrip('+').lstrip('91')
        if not _re.match(r'^[1-9]\d{9}$', phone):
            return False
        if phone == '0' * 10:
            return False
        # 3. Address fields
        if not (self.state or '').strip():
            return False
        if not (self.city or '').strip():
            return False
        if not (self.pin_code or '').strip():
            return False
        if not (self.address or '').strip():
            return False
        # 4. ID proof
        if not (self.id_proof_type or '').strip():
            return False
        if not (self.id_proof_number or '').strip():
            return False
        # 5. Guest photo (from most recent checkin record)
        latest_checkin = None
        for cr in getattr(self, 'checkin_records', []):
            if not latest_checkin or (cr.created_at and cr.created_at > latest_checkin.created_at):
                latest_checkin = cr
        if not latest_checkin or not (latest_checkin.guest_photo_path or '').strip():
            return False
        # 6. ID document front + back
        id_docs = getattr(self, 'id_documents', [])
        has_front = any((d.front_image_path or '').strip() for d in id_docs)
        has_back = any((d.back_image_path or '').strip() for d in id_docs)
        if not has_front or not has_back:
            return False
        return True

class Reservation(db.Model):
    __tablename__ = 'reservations'
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('Reserved','Confirmed','CheckedIn','CheckedOut','Cancelled','NoShow','Overbooked','Blocked')",
            name='ck_reservation_status'),
        db.CheckConstraint(
            "source IN ('Walk-in','OTA','Calling','Website','Agent')",
            name='ck_reservation_source'),
        db.CheckConstraint("rate_per_night >= 0", name='ck_reservation_rate_positive'),
        db.Index('idx_reservation_guest_id', 'guest_id'),
        db.Index('idx_reservation_room_id', 'room_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    booking_reference = db.Column(db.String(20), unique=True, nullable=True, index=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=True)  # nullable for group blocks (guest assigned at check-in)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))
    room_type_id = db.Column(db.Integer, db.ForeignKey('room_types.id'), nullable=False)
    arrival_date = db.Column(db.Date, nullable=False)
    departure_date = db.Column(db.Date, nullable=False)
    adults = db.Column(db.Integer, default=1)
    children = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Reserved')  # Reserved, Confirmed, CheckedIn, CheckedOut, Cancelled, NoShow, Overbooked, Blocked
    noshow_exempt = db.Column(db.Boolean, default=False, nullable=False)  # Manager sets True to skip tonight's no-show audit
    rate_per_night = db.Column(db.Numeric(10, 2), nullable=False)
    advance_payment = db.Column(db.Numeric(10, 2), default=0)
    special_requests = db.Column(db.Text)
    source = db.Column(db.String(20), default='Walk-in')  # Walk-in, OTA, Calling, Website, Agent
    market_segment = db.Column(db.String(30), nullable=True)    # Corporate, Leisure, Government, Crew, Group, OTA, FIT
    ota_booking_id = db.Column(db.String(100), nullable=True)   # channel manager / OTA reference
    # Authoritative OTA channel name captured at booking creation time
    # ('Booking.com', 'MakeMyTrip', etc.). Set by webhook ingestion and
    # the manual OTA booking form. NULL on legacy rows; the
    # _infer_ota_source helper falls back to booking_reference / ota_booking_id
    # prefix inference when this is missing. Authoritative > inferred —
    # always read via _infer_ota_source(reservation) so dashboard, reports
    # and CEO KPIs cannot drift.
    ota_channel = db.Column(db.String(40), nullable=True)
    # GST: state code of billing party — determines CGST+SGST vs IGST
    billing_state_code = db.Column(db.String(2), nullable=True)   # e.g. '07' Delhi, '27' Maharashtra
    # Booking type: Regular (nightly) or Hourly
    booking_type = db.Column(db.String(10), default='Regular')    # Regular | Hourly
    # Actual check-in / check-out times (HH:MM strings, e.g. '14:30')
    checkin_time = db.Column(db.String(5))
    checkout_time = db.Column(db.String(5))
    # Flag: True when staff manually overrode the system tariff
    tariff_modified_manually = db.Column(db.Boolean, default=False)
    # Pricing mode used at check-in: 'standard' | 'per_night' | 'total_stay' | 'discount_on_total'
    pricing_mode = db.Column(db.String(20), default='standard')
    # OTA payment status: 'pay_at_hotel' | 'paid_at_ota'
    # For paid_at_ota: room revenue settles to an ota_receivable head, not direct cash.
    ota_payment_status = db.Column(db.String(20), default='pay_at_hotel')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    checked_in_at = db.Column(db.DateTime)
    checked_out_at = db.Column(db.DateTime)
    # Set True when front-desk opens the checkout form — used to escalate badge to CRITICAL
    checkout_initiated = db.Column(db.Boolean, default=False, nullable=False)
    # Overstay billing — stores the wall-clock time through which overstay was last billed.
    # Prevents duplicate charges on repeated refreshes (idempotency guard).
    overstay_billed_until = db.Column(db.DateTime, nullable=True)
    # Sequential invoice number assigned on first invoice view (e.g. INV-JBP-2026-000042)
    invoice_number = db.Column(db.String(50), nullable=True, unique=True, index=True)
    # Tariff Adjustment — records deviation from standard tariff at booking/check-in time.
    # standard_tariff = room_type.base_rate captured at that moment.
    # adjustment_type: 'LEAKAGE' (sold below tariff), 'UPSELL' (sold above tariff), or NULL.
    standard_tariff   = db.Column(db.Numeric(10, 2), nullable=True)
    adjustment_type   = db.Column(db.String(10),     nullable=True)
    adjustment_amount = db.Column(db.Numeric(10, 2), default=0)
    # Discount — post-billing reduction authorised by management.
    # Distinct from tariff adjustment: this reduces the bill AFTER the rate is set.
    discount_amount       = db.Column(db.Numeric(10, 2), default=0)
    discount_reason       = db.Column(db.String(50),     nullable=True)
    discount_authorized_by = db.Column(db.String(100),   nullable=True)
    discount_given_by     = db.Column(db.String(100),    nullable=True)
    discount_at           = db.Column(db.DateTime,       nullable=True)
    # Staff attribution — denormalised usernames for user-wise revenue reporting.
    checkin_by  = db.Column(db.String(100), nullable=True)   # username who performed check-in
    checkout_by = db.Column(db.String(100), nullable=True)   # username who performed checkout
    # AI Revenue Intelligence — computed at check-in by revenue_guard.py
    # expected_tariff = MAX(base_rate, 7-day avg same room_type, active rate_plan)
    expected_tariff = db.Column(db.Numeric(10, 2), nullable=True)
    leakage_reason  = db.Column(db.String(200),    nullable=True)
    # ── Source-captured leakage classification (Apr 2026) ─────────
    # Set at the moment the leakage is created (check-in below standard,
    # post-checkout discount, waiver, manual adjustment) so reports show
    # the AUTHORITATIVE type — not a heuristic guess. Heuristic remains
    # only as a fallback for legacy records (labelled "Legacy inferred").
    # Values: DISCOUNT / RATE_OVERRIDE / WAIVER / MANUAL_ADJUSTMENT /
    #         MISSING_CHARGE / PRICING_GAP
    leakage_type                  = db.Column(db.String(20), nullable=True)
    leakage_authorized_by_user_id = db.Column(db.Integer,
                                              db.ForeignKey('users.id'),
                                              nullable=True)
    leakage_created_at            = db.Column(db.DateTime, nullable=True)
    # ── Leakage intent (Apr 2026 final tightening) ───────────────
    # INTENTIONAL  — operator chose to give up revenue (DISCOUNT,
    #                MANUAL_ADJUSTMENT, WAIVER, deliberate RATE_OVERRIDE)
    # UNINTENTIONAL — system / process gap (MISSING_CHARGE, PRICING_GAP)
    # Used by management reports to separate strategic from accidental
    # revenue loss.
    leakage_intent                = db.Column(db.String(15), nullable=True)
    # ── Invoice rounding-reconciliation snapshot (Apr 2026) ───────
    # Frozen at the moment the bill is finalised (checkout success).
    # Reports use these instead of recomputing from live `payments` /
    # `extra_charges` tables — guaranteeing the displayed total never
    # drifts due to later voids, edits, or rounding noise.
    invoice_taxable_total         = db.Column(db.Numeric(12, 2), nullable=True)
    invoice_gst_total             = db.Column(db.Numeric(12, 2), nullable=True)
    invoice_unrounded_grand_total = db.Column(db.Numeric(12, 2), nullable=True)
    invoice_rounded_grand_total   = db.Column(db.Numeric(12, 2), nullable=True)
    invoice_round_off_amount      = db.Column(db.Numeric(10, 2), nullable=True)
    invoice_finalised_at          = db.Column(db.DateTime, nullable=True)
    # ── Individual credit checkout (Apr 2026) ───────────────────────
    # Set when a Manager / Admin checks the guest out with an outstanding
    # balance approved as credit. credit_amount is the SNAPSHOT of the
    # outstanding balance at the moment of credit checkout — frozen for
    # ledger / aging reports. The LIVE balance (calculate_stay_amount)
    # continues to reflect grand_total - paid - company_credit, so any
    # later payment against this reservation reduces the live balance
    # while credit_amount remains as the original credit-extended amount.
    # Aging is calculated from credit_approved_at.
    credit_amount             = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    credit_reason             = db.Column(db.String(200), nullable=True)
    credit_approved_by_user_id = db.Column(db.Integer,
                                           db.ForeignKey('users.id'),
                                           nullable=True)
    credit_approved_at        = db.Column(db.DateTime, nullable=True)
    # Credit recovery tracking — incremented as later payments come in.
    # status (Open / Partial / Settled) is derived in the ledger UI from
    # credit_amount vs credit_settled_amount; credit_settled_at is set
    # only when fully cleared.
    credit_settled_amount     = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    credit_settled_at         = db.Column(db.DateTime, nullable=True)
    # ── Cancellation disposition (Apr 2026 hardening pass) ──────────
    # Set when a reservation is cancelled and it had a non-zero advance
    # collected. Tracks how the advance liability was discharged so the
    # advance lifecycle stays auditable end-to-end.
    #   refund_full     — entire advance refunded to guest
    #   refund_partial  — partial refund + remainder forfeit
    #   forfeit         — entire advance kept by hotel (recognised as
    #                     "Forfeit Income" — separate from room revenue)
    #   credit_voucher  — advance held as a future-stay credit voucher
    #   no_advance      — booking had no advance; recorded for symmetry
    cancellation_disposition         = db.Column(db.String(20), nullable=True)
    cancellation_amount_refunded     = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    cancellation_amount_forfeited    = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    cancellation_amount_credit_voucher = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    cancellation_reason              = db.Column(db.String(300), nullable=True)
    cancellation_processed_by_user_id = db.Column(db.Integer,
                                                  db.ForeignKey('users.id'),
                                                  nullable=True)
    cancellation_processed_at        = db.Column(db.DateTime, nullable=True)
    cancellation_refund_payment_id   = db.Column(db.Integer,
                                                  db.ForeignKey('payments.id'),
                                                  nullable=True)
    # ── Advance Receipt sequence (Apr 2026 polish) ─────────────────
    # Sequential, year-scoped, audit-ready receipt number — assigned
    # the first time the Advance Receipt is viewed and frozen
    # thereafter. Format: AR-YYYY-NNNN.
    advance_receipt_number = db.Column(db.String(20), nullable=True, unique=True)
    advance_receipt_date   = db.Column(db.DateTime, nullable=True)
    # Group reservation link
    group_block_id = db.Column(db.Integer, db.ForeignKey('group_blocks.id'), nullable=True)
    guest = db.relationship('Guest', backref='reservations', lazy='joined')
    room = db.relationship('Room', backref='reservations', lazy='joined')
    room_type = db.relationship('RoomType', lazy='joined')
    group_block = db.relationship('GroupBlock', backref='reservations')

    # ── Explicit FK-disambiguated Payment relationships (Apr 2026) ──
    # Replaces the old ``backref='payments'`` on Payment.reservation.
    # Two paths exist between these tables now:
    #   payments → folio's normal payment rows (payments.reservation_id)
    #   cancellation_refund_payment → the single Payment row written
    #       when this booking was cancelled with a refund disposition
    #       (reservations.cancellation_refund_payment_id)
    # Each side names the FK so SQLAlchemy never has to guess.
    payments = db.relationship(
        'Payment',
        foreign_keys='Payment.reservation_id',
        back_populates='reservation',
    )
    cancellation_refund_payment = db.relationship(
        'Payment',
        foreign_keys='Reservation.cancellation_refund_payment_id',
        uselist=False,
        post_update=True,
    )
    passengers = db.relationship('ReservationPassenger', backref='reservation',
                                  cascade='all, delete-orphan', lazy='dynamic')

    # ── Group Stay (Phase 1, multi-room shared reservation) ──────────────
    # Helpers that make every callsite multi-room-aware via a single API.
    # Backwards-safe: legacy rows lacking a bridge entry fall back to
    # [room_id], so the result is always the *correct* room list.
    # See docs/RELEASE.md for the full Phase 1 design.
    def all_room_ids(self):
        """Return every room linked to this reservation as a list[int].

        For multi-room reservations (Phase 1+): reads from the
        reservation_rooms bridge.
        For single-room reservations (the default): returns the bridge
        list if any rows exist, else falls back to [self.room_id].
        For unassigned reservations (legacy group blocks with no room
        yet): returns []."""
        rows = ReservationRoom.query.filter_by(reservation_id=self.id).all()
        if rows:
            return [r.room_id for r in rows]
        return [self.room_id] if self.room_id else []

    @property
    def is_multi_room(self):
        """True iff this reservation spans more than one room."""
        return ReservationRoom.query.filter_by(reservation_id=self.id).count() > 1

    @property
    def room_count(self):
        """Number of rooms occupied by this reservation. 1 for single-room.
        Used by group badges ('GROUP · 3 ROOMS') and billing multipliers."""
        return len(self.all_room_ids())


class GroupBlock(db.Model):
    """A block of rooms reserved for a group (wedding, corporate event, etc.)."""
    __tablename__ = 'group_blocks'
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(200), nullable=False)
    group_code = db.Column(db.String(20), unique=True, nullable=False)
    contact_name = db.Column(db.String(100))
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(100))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    arrival_date = db.Column(db.Date, nullable=False)
    departure_date = db.Column(db.Date, nullable=False)
    total_rooms = db.Column(db.Integer, nullable=False, default=1)
    group_rate = db.Column(db.Numeric(10, 2), nullable=True)  # negotiated group rate
    status = db.Column(db.String(20), default='Tentative')  # Tentative, Confirmed, Cancelled, Completed
    billing_instructions = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    company = db.relationship('Company')
    created_by = db.relationship('User')
    __table_args__ = (
        db.CheckConstraint("status IN ('Tentative','Confirmed','Cancelled','Completed')", name='ck_group_status'),
    )


class ReservationPassenger(db.Model):
    """Additional guests (beyond the primary guest) travelling on a reservation."""
    __tablename__ = 'reservation_passengers'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))                 # Male | Female | Other
    mobile = db.Column(db.String(20))
    id_type = db.Column(db.String(50))
    id_number = db.Column(EncryptedString())
    relationship = db.Column(db.String(50))           # e.g. Spouse, Child, Parent, Colleague
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.Index('idx_rp_reservation_id', 'reservation_id'),)


class ReservationRoom(db.Model):
    """Bridge table: a Reservation may span 1..N rooms (Group Stay Phase 1).

    For single-room reservations, the post-backfill state is exactly one
    row with ``is_primary=True``. For multi-room reservations (Phase 1+),
    one ``is_primary=True`` row plus one row per secondary room.

    Schema invariants enforced at DB level:
      - UNIQUE(reservation_id, room_id): a room can be linked to a given
        reservation only once.
      - Partial UNIQUE on (reservation_id) WHERE is_primary=1: at most
        one primary room per reservation.

    See docs/RELEASE.md for the full Phase 1 design.
    """
    __tablename__ = 'reservation_rooms'

    id              = db.Column(db.Integer, primary_key=True)
    reservation_id  = db.Column(db.Integer,
                                db.ForeignKey('reservations.id'), nullable=False)
    room_id         = db.Column(db.Integer,
                                db.ForeignKey('rooms.id'), nullable=False)
    is_primary      = db.Column(db.Boolean, nullable=False, default=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    reservation     = db.relationship(
        'Reservation',
        backref=db.backref('room_links', lazy='select',
                           cascade='all, delete-orphan'),
    )
    room            = db.relationship('Room')

    __table_args__ = (
        db.UniqueConstraint('reservation_id', 'room_id',
                            name='uq_resroom_reservation_room'),
        db.Index('idx_resroom_res',  'reservation_id'),
        db.Index('idx_resroom_room', 'room_id'),
    )


def log_group_room_link(
    reservation_id,
    room_id,
    action,
    actor_user_id,
    is_primary=False,
    ip_address=None,
):
    """Audit a reservation_rooms bridge event (Group Stay Phase 1).

    Adds an ``AuditLog`` row to the current session. Caller is
    responsible for committing the surrounding transaction; audit
    integrity is mandatory, so any failure here propagates to the caller.

    Parameters
    ----------
    reservation_id : int
        The reservation owning the bridge row. Stored as
        ``AuditLog.entity_id`` so all bridge events for one reservation
        are queryable as a single timeline.
    room_id : int
        The room being linked or unlinked.
    action : str
        ``'GROUP_ROOM_LINK_CREATED'`` or ``'GROUP_ROOM_LINK_REMOVED'``.
    actor_user_id : int
        ``users.id`` of the staff user performing the action.
    is_primary : bool, optional
        Whether this link was/is the primary room.
    ip_address : str, optional
        Captured from ``request.remote_addr`` if available.

    Backend-only — no UI in Release 1. Release 2/3 application code
    calls this from inside the same transaction that inserts/deletes the
    ReservationRoom row.
    """
    entry = AuditLog(
        entity_type='ReservationRoom',
        entity_id=reservation_id,
        action=action,
        after_state={'room_id': room_id, 'is_primary': bool(is_primary)},
        staff_user_id=actor_user_id,
        ip_address=ip_address,
    )
    db.session.add(entry)


class ReservationNightRate(db.Model):
    """
    Per-night pricing truth for a reservation.

    One row per stay night.  Created at reservation time, updated on
    tariff modification / room change / stay extension.

    **Field semantics (locked — do not change without updating all consumers):**

    ``standard_rate``
        Room-type base_rate snapshot at booking time for this night.
        This is the benchmark for leakage calculations.

    ``resolved_rate``
        Rate after applying active rate plans for this specific night.
        May differ from standard_rate if a seasonal/weekend plan matched.

    ``final_rate``
        Actual chargeable room rate for this night after manual override,
        pricing-mode adjustments, and discount distribution.
        This is what the guest pays.

    ``discount_amount``
        Portion of the reservation-level discount allocated to this night,
        distributed proportionally to pre-discount nightly values.

    **Leakage basis:**
        ``standard_rate`` vs ``final_rate``  (NOT resolved_rate vs final_rate)

    **Immutability rule:**
        Rows with ``is_posted=True`` or ``is_locked=True`` must not be
        overwritten.  Past/audited nights are frozen for audit integrity.
    """
    __tablename__ = 'reservation_night_rates'
    __table_args__ = (
        db.UniqueConstraint('reservation_id', 'stay_date', name='uq_night_rate_res_date'),
        db.Index('idx_night_rate_res', 'reservation_id'),
        db.Index('idx_night_rate_date', 'stay_date'),
        db.Index('idx_night_rate_posted', 'is_posted'),
    )

    id               = db.Column(db.Integer, primary_key=True)
    reservation_id   = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    stay_date        = db.Column(db.Date, nullable=False)
    room_type_id     = db.Column(db.Integer, db.ForeignKey('room_types.id'), nullable=True)
    room_id          = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True)

    # Rate tiers (all Numeric, excl. GST)
    standard_rate    = db.Column(db.Numeric(12, 2), nullable=False)
    resolved_rate    = db.Column(db.Numeric(12, 2), nullable=False)
    final_rate       = db.Column(db.Numeric(12, 2), nullable=False)
    discount_amount  = db.Column(db.Numeric(12, 2), default=0, nullable=False)

    # Source tracking
    rate_source      = db.Column(db.String(30), nullable=False)  # base_rate | rate_plan | manual_override | group_rate
    rate_plan_id     = db.Column(db.Integer, db.ForeignKey('rate_plans.id'), nullable=True)
    rate_plan_name   = db.Column(db.String(100), nullable=True)  # denormalized — plan may be deleted later
    pricing_mode     = db.Column(db.String(20), nullable=True)   # standard | per_night | total_stay | discount_on_total
    manual_override  = db.Column(db.Boolean, default=False, nullable=False)

    # Tax snapshot
    tax_rate         = db.Column(db.Numeric(5, 2), nullable=True)

    # Audit / lifecycle
    is_posted        = db.Column(db.Boolean, default=False, nullable=False)
    posted_charge_id = db.Column(db.Integer, db.ForeignKey('extra_charges.id'), nullable=True)
    is_locked        = db.Column(db.Boolean, default=False, nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reservation      = db.relationship('Reservation', backref=db.backref('night_rates', lazy='dynamic'))
    room_type_rel    = db.relationship('RoomType')
    room_rel         = db.relationship('Room')


class Folio(db.Model):
    """
    Split-billing folio: each reservation can have multiple folios
    (A=Guest, B=Company, C=Third-party, etc.).  Charges and payments
    are optionally routed to a specific folio via folio_id FK on
    ExtraCharge / Payment.
    """
    __tablename__ = 'folios'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    folio_letter = db.Column(db.String(1), nullable=False, default='A')  # A, B, C, D...
    label = db.Column(db.String(50), default='Guest')  # Guest, Company, Travel Agent, etc.
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    is_closed = db.Column(db.Boolean, default=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reservation = db.relationship('Reservation', backref='folios')
    company = db.relationship('Company')
    charges = db.relationship('ExtraCharge', backref='folio', lazy='dynamic')
    payments = db.relationship('Payment', backref='folio', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('reservation_id', 'folio_letter', name='uq_folio_letter'),
        db.Index('idx_folio_reservation_id', 'reservation_id'),
    )


# ---------------------------------------------------------------------------
# Auto-create default Folio A when a Reservation is first persisted
# ---------------------------------------------------------------------------
from sqlalchemy import event as _sa_event

@_sa_event.listens_for(Reservation, 'after_insert')
def _auto_create_default_folio(mapper, connection, target):
    """Create Folio A (Guest) automatically for every new reservation.

    Uses connection.execute() so it works inside the same flush/transaction
    without triggering a recursive flush.
    """
    from sqlalchemy import insert
    connection.execute(
        insert(Folio.__table__).values(
            reservation_id=target.id,
            folio_letter='A',
            label='Guest',
            is_closed=False,
            created_at=datetime.utcnow(),
        )
    )


class ExtraCharge(db.Model):
    __tablename__ = 'extra_charges'
    __table_args__ = (
        db.CheckConstraint("amount >= 0", name='ck_extra_charge_positive'),
        db.Index('idx_extra_charge_reservation_id', 'reservation_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    folio_id = db.Column(db.Integer, db.ForeignKey('folios.id'), nullable=True)
    description = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    charge_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # charge_type: NULL = general extra charge, 'early_checkin', 'late_checkout'
    charge_type = db.Column(db.String(30), nullable=True)
    # GST category for tax calculation.  When set, gst_service uses this
    # directly instead of inferring from description strings.
    # Values: Restaurant, Bar, Laundry, RoomService, Minibar, Telephone, Other
    charge_category = db.Column(db.String(30), nullable=True)
    # ── Post-audit corrections (Apr 2026 hardening pass) ─────────────
    # When a charge in a closed Night Audit must be adjusted, we never
    # mutate the original row. Instead we POST a reversal row
    # (is_correction=True, is_reversal=True, amount=<original>) and an
    # optional replacement row (is_correction=True, is_reversal=False,
    # amount=<corrected>). Both are linked to the original via
    # corrects_id. The CHECK CONSTRAINT amount>=0 stays intact —
    # callers that sum charges flip the sign on is_reversal=True rows.
    is_correction     = db.Column(db.Boolean, default=False, nullable=False)
    is_reversal       = db.Column(db.Boolean, default=False, nullable=False)
    corrects_id       = db.Column(db.Integer, db.ForeignKey('extra_charges.id'),
                                  nullable=True)
    correction_reason = db.Column(db.String(300), nullable=True)
    reservation = db.relationship('Reservation', backref='extra_charges')

class Payment(db.Model):
    __tablename__ = 'payments'
    __table_args__ = (
        db.CheckConstraint("amount > 0", name='ck_payment_amount_positive'),
        db.Index('idx_payment_reservation_id', 'reservation_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    folio_id = db.Column(db.Integer, db.ForeignKey('folios.id'), nullable=True)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.Date, default=date.today)
    reference_number = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Void / refund support
    is_voided = db.Column(db.Boolean, default=False, nullable=False)
    voided_at = db.Column(db.DateTime)
    voided_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    void_reason = db.Column(db.String(200))
    # ── Post-audit corrections (Apr 2026 hardening pass) ─────────────
    # See ExtraCharge for the full pattern. is_reversal=True rows
    # carry a positive amount (CHECK amount > 0 stays intact) but
    # SUBTRACT in callers that compute paid totals.
    is_correction     = db.Column(db.Boolean, default=False, nullable=False)
    is_reversal       = db.Column(db.Boolean, default=False, nullable=False)
    corrects_id       = db.Column(db.Integer, db.ForeignKey('payments.id'),
                                  nullable=True)
    correction_reason = db.Column(db.String(300), nullable=True)
    # ── Payment purpose / accounting bucket (Apr 2026 hardening pass) ──
    # Tags every payment with the accounting bucket it belongs to, so the
    # Night Audit and reports can separate Advance Received (liability)
    # from Settlement (cash for stay-period revenue) from Credit Recovery
    # (cash against post-checkout receivable). Values:
    #   advance         — collected before the stay; a guest deposit /
    #                     liability until revenue is recognised on the
    #                     stay date.
    #   settlement      — cash collected against earned charges (default
    #                     for in-house and checkout payments).
    #   credit_recovery — cash collected against an Individual Credit
    #                     receivable AFTER the guest has checked out.
    #   refund          — outbound payment (when refund flow posts a row
    #                     of its own; today refunds use ExtraCharge but
    #                     the bucket is reserved for future use).
    # Legacy NULL rows (created before this column existed) are treated
    # as 'settlement' by callers so historical data is NEVER mutated.
    payment_purpose   = db.Column(db.String(20), nullable=True)
    # ── Explicit FK disambiguation (Apr 2026) ──────────────────────
    # Reservation now has TWO foreign keys pointing into payments:
    #   payments.reservation_id              (this row's parent folio)
    #   reservations.cancellation_refund_payment_id  (refund link)
    # SQLAlchemy can't auto-pick the join, so we name the FK explicitly
    # on both sides via foreign_keys + back_populates. The matching
    # Reservation.payments / Reservation.cancellation_refund_payment
    # relationships live below the column declaration in Reservation.
    reservation = db.relationship(
        'Reservation',
        foreign_keys=[reservation_id],
        back_populates='payments',
    )
    payment_mode = db.relationship('PaymentMode', lazy='joined')
    voided_by = db.relationship('User', foreign_keys=[voided_by_user_id])


class OTAPayout(db.Model):
    """OTA payout — actual money received from a channel manager.

    Phase 2 of OTA reconciliation. **Sits ON TOP of the existing OTA
    receivable system** (PaymentMode.category='ota_receivable' rows in
    the Payment table) — does not modify it. Each row here records
    one bank transfer / settlement file line FROM the OTA TO the hotel.

    Reconciliation: ``ota_pending = SUM(receivable postings) - SUM(payouts)``
    grouped by ``ota_channel`` (the canonical channel name introduced
    by migration 7.3.0). See ``app.ota_reconciliation`` for the
    helpers that consume this model.

    Validation (DB-level + service-level):
        - all four amount columns are non-negative
        - net_paid <= gross_amount   (commission + tax cannot exceed gross)
    """
    __tablename__ = 'ota_payouts'
    id = db.Column(db.Integer, primary_key=True)
    ota_channel = db.Column(db.String(40), nullable=False, index=True)
    payout_date = db.Column(db.Date, nullable=False, index=True)
    reference_number = db.Column(db.String(100), nullable=True)
    gross_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    commission_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_deducted = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    net_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    remarks = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                                   nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.CheckConstraint('gross_amount >= 0',
                           name='ck_payout_gross_nonneg'),
        db.CheckConstraint('commission_amount >= 0',
                           name='ck_payout_commission_nonneg'),
        db.CheckConstraint('tax_deducted >= 0',
                           name='ck_payout_tax_nonneg'),
        db.CheckConstraint('net_paid >= 0',
                           name='ck_payout_net_nonneg'),
        db.CheckConstraint('net_paid <= gross_amount',
                           name='ck_payout_net_le_gross'),
        db.Index('idx_payout_channel_date', 'ota_channel', 'payout_date'),
    )


class NightAuditLog(db.Model):
    __tablename__ = 'night_audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    audit_date = db.Column(db.Date, nullable=False, index=True)
    run_at = db.Column(db.DateTime, default=datetime.utcnow)
    # ── Cash-basis revenue (collected payments) ──
    total_revenue = db.Column(db.Numeric(12, 2), default=0)       # cash_collected: SUM(payments) for the day
    net_revenue = db.Column(db.Numeric(12, 2), default=0)         # cash_net: cash_collected - discounts
    total_discount = db.Column(db.Numeric(12, 2), default=0)      # cash_discount: checkout discounts applied
    # ── Accrual-basis revenue (earned) ──
    accrual_revenue = db.Column(db.Numeric(12, 2), default=0)     # accrual_net: rate × nights + extras - discounts
    occupancy_count = db.Column(db.Integer, default=0)
    pending_checkouts = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    # Extended audit fields
    status = db.Column(db.String(20), default='Pending')          # Pending / Completed / Reopened
    run_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    total_payments = db.Column(db.Numeric(12, 2), default=0)
    outstanding_amount = db.Column(db.Numeric(12, 2), default=0)
    reconciliation_difference = db.Column(db.Numeric(12, 2), default=0)
    blocker_count = db.Column(db.Integer, default=0)
    warning_count = db.Column(db.Integer, default=0)
    reopen_reason = db.Column(db.Text, nullable=True)
    snapshot_json = db.Column(db.Text, nullable=True)             # JSON snapshot of full report
    # ── Snapshot validity (Apr 2026 critical correction) ─────────
    # True: snapshot_json is the authoritative frozen state for this date.
    # False (or NULL after reopen): snapshot_json is stale; UI must show
    # "Snapshot unavailable — re-run audit" and refuse live fallback.
    snapshot_valid = db.Column(db.Boolean, default=True, nullable=False)
    # ── Snapshot tamper-detection (Apr 2026 final tightening) ────
    # SHA-256 of snapshot_json computed at close time. Re-checked on
    # every render — mismatch surfaces a "Snapshot integrity warning"
    # so a manual DB edit or a patch-driven structural drift can never
    # silently corrupt audit history.
    snapshot_hash    = db.Column(db.String(64), nullable=True)
    snapshot_version = db.Column(db.String(20), nullable=True)
    # Stage tracking
    started_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    # Override fields (admin completes with blockers)
    override_used = db.Column(db.Boolean, default=False)
    override_reason = db.Column(db.Text, nullable=True)
    # Cash tracking from shifts
    expected_cash = db.Column(db.Numeric(12, 2), default=0)
    actual_cash = db.Column(db.Numeric(12, 2), default=0)
    cash_variance = db.Column(db.Numeric(12, 2), default=0)
    # Relationships
    run_by = db.relationship('User', foreign_keys=[run_by_user_id])
    started_by = db.relationship('User', foreign_keys=[started_by_user_id])
    reopen_logs = db.relationship('NightAuditReopenLog', back_populates='audit_log',
                                  order_by='NightAuditReopenLog.reopened_at.desc()')


class NightAuditReopenLog(db.Model):
    """Immutable audit trail for every reopen action on a night audit."""
    __tablename__ = 'night_audit_reopen_logs'
    id = db.Column(db.Integer, primary_key=True)
    audit_log_id = db.Column(db.Integer, db.ForeignKey('night_audit_logs.id'), nullable=False)
    audit_date = db.Column(db.Date, nullable=False, index=True)
    reopened_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reopened_at = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.Text, nullable=False)
    previous_status = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationships
    audit_log = db.relationship('NightAuditLog', back_populates='reopen_logs')
    reopened_by = db.relationship('User', foreign_keys=[reopened_by_user_id])


class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), nullable=False, unique=True)
    value = db.Column(db.String(200))
    description = db.Column(db.String(200))

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    credit_limit = db.Column(db.Numeric(12, 2), default=0)
    credit_used = db.Column(db.Numeric(12, 2), default=0)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    email = db.Column(db.String(100))
    gstin = db.Column(db.String(15), nullable=True)
    state_code = db.Column(db.String(2), nullable=True)
    head_office = db.Column(db.String(200), nullable=True)
    business_category = db.Column(db.String(100), nullable=True)
    vendor_code_generated = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GuestIDDocument(db.Model):
    __tablename__ = 'guest_id_documents'
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)
    document_number = db.Column(EncryptedString(), nullable=False)
    front_image_path = db.Column(db.String(255))
    back_image_path = db.Column(db.String(255))
    verification_status = db.Column(db.String(20), default='Pending')
    verified_by_user_id = db.Column(db.Integer)
    verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    guest = db.relationship('Guest', backref='id_documents')
    __table_args__ = (db.Index('idx_guest_id_documents_guest_id', 'guest_id'),)

class CheckInRecord(db.Model):
    __tablename__ = 'checkin_records'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    guest_id = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    checkin_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    checkout_date = db.Column(db.DateTime)
    checkin_mode = db.Column(db.String(20), default='EXPRESS')
    is_profile_complete = db.Column(db.Boolean, default=False)
    guest_photo_path = db.Column(db.String(255))
    signature_path = db.Column(db.String(255))
    billing_responsibility = db.Column(db.String(20), default='Guest')
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'))
    company_billing_ref = db.Column(db.String(100))
    deposit_amount = db.Column(db.Numeric(10, 2), default=0)
    deposit_payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'))
    company_credit_posted = db.Column(db.Numeric(12, 2), default=0)  # credit charged to company at checkout
    staff_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45))
    device_info = db.Column(db.String(255))
    # GRC (Guest Registration Card) tracking
    grc_generated_at = db.Column(db.DateTime, nullable=True)
    grc_declaration_accepted = db.Column(db.Boolean, default=False)
    grc_signature_ip = db.Column(db.String(45))
    grc_signature_timestamp = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reservation = db.relationship('Reservation', backref=db.backref('checkin_record', uselist=False))
    guest = db.relationship('Guest', backref='checkin_records')
    room = db.relationship('Room')
    company = db.relationship('Company')
    deposit_payment_mode = db.relationship('PaymentMode')
    staff_user = db.relationship('User', foreign_keys=[staff_user_id])
    __table_args__ = (
        db.Index('idx_checkin_reservation_id', 'reservation_id'),
        db.Index('idx_checkin_guest_id', 'guest_id'),
        db.Index('idx_checkin_date', 'checkin_date'),
        db.UniqueConstraint('reservation_id', name='uq_checkin_reservation_id'),
    )

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(50), nullable=False)
    before_state = db.Column(db.JSON)
    after_state = db.Column(db.JSON)
    staff_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    staff_user = db.relationship('User', foreign_keys=[staff_user_id])
    __table_args__ = (db.Index('idx_audit_entity', 'entity_type', 'entity_id'),)


class WebhookLog(db.Model):
    """Logs all inbound webhook calls from channel managers / OTAs."""
    __tablename__ = 'webhook_logs'
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(50), nullable=False)          # e.g. 'staah', 'wubook', 'generic'
    event_type = db.Column(db.String(50), nullable=False)      # e.g. 'new_booking', 'cancel', 'modify'
    raw_payload = db.Column(db.JSON)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=True)
    status = db.Column(db.String(20), default='received')      # received, processed, failed
    error_message = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    reservation = db.relationship('Reservation', backref='webhook_logs')


class RatePlan(db.Model):
    """
    Seasonal / promotional / weekend rate plans.
    The highest-priority active plan matching the dates wins.
    Falls back to RoomType.base_rate when no plan matches.
    """
    __tablename__ = 'rate_plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    plan_type = db.Column(db.String(20), default='Seasonal')   # Seasonal, Weekend, Package, Promo
    room_type_id = db.Column(db.Integer, db.ForeignKey('room_types.id'), nullable=True)  # None = all types
    rate_amount = db.Column(db.Numeric(10, 2), nullable=False)
    # fixed = set amount | percent_up / percent_down = % on top of base_rate
    rate_mode = db.Column(db.String(15), default='fixed')
    start_date = db.Column(db.Date, nullable=True)             # None = always active
    end_date = db.Column(db.Date, nullable=True)
    # Comma-separated weekday numbers: 0=Mon … 6=Sun. Null = every day.
    days_of_week = db.Column(db.String(20), nullable=True)
    priority = db.Column(db.Integer, default=10)               # higher wins
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    room_type = db.relationship('RoomType', backref='rate_plans')


class NotificationLog(db.Model):
    """Records every WhatsApp / email notification attempt."""
    __tablename__ = 'notification_logs'
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(20), nullable=False)         # whatsapp, email
    recipient = db.Column(db.String(200), nullable=False)      # phone or email address
    message_type = db.Column(db.String(50), nullable=False)    # booking_confirmed, cancelled, checkin_welcome, etc.
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=True)
    status = db.Column(db.String(20), default='sent')          # sent, failed, skipped
    error_message = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    reservation = db.relationship('Reservation', backref='notification_logs')


class NotificationQueue(db.Model):
    """Offline-safe queue: failed or deferred notifications are stored here
    and retried automatically when connectivity returns."""
    __tablename__ = 'notification_queue'
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(20), nullable=False)         # whatsapp, email
    recipient = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(200))                        # email only
    body = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), nullable=False)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=True)
    status = db.Column(db.String(20), default='pending')       # pending, sent, failed
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=10)
    next_retry_at = db.Column(db.DateTime, default=datetime.utcnow)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reservation = db.relationship('Reservation', backref='queued_notifications')


class POSItem(db.Model):
    """Catalog of POS items that can be posted to a room folio."""
    __tablename__ = 'pos_items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # Category: Restaurant, Bar, Laundry, Room Service, Minibar, Telephone, Other
    category = db.Column(db.String(50), default='Restaurant')
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MaintenanceRequest(db.Model):
    """Room maintenance / repair tracking."""
    __tablename__ = 'maintenance_requests'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    # Category: Plumbing, Electrical, AC/Heating, Furniture, Cleaning, Other
    category = db.Column(db.String(50), default='Other')
    description = db.Column(db.Text, nullable=False)
    # Priority: Low, Medium, High, Urgent
    priority = db.Column(db.String(10), default='Medium')
    # Status: Open, InProgress, Resolved
    status = db.Column(db.String(15), default='Open')
    reported_by = db.Column(db.String(100))         # staff name / username
    assigned_to = db.Column(db.String(100))         # staff name
    notes = db.Column(db.Text)                       # resolution notes
    resolved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cost_estimate = db.Column(db.Numeric(10, 2), nullable=True)
    room = db.relationship('Room', backref='maintenance_requests')


# ---------------------------------------------------------------------------
# Predictive Maintenance models
# ---------------------------------------------------------------------------

class Equipment(db.Model):
    """Physical asset/equipment in a room (AC unit, geyser, electrical panel, etc.)."""
    __tablename__ = 'equipment'
    __table_args__ = (
        db.Index('idx_equipment_room_cat', 'room_id', 'category'),
    )
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    manufacturer = db.Column(db.String(100))
    model_number = db.Column(db.String(100))
    install_date = db.Column(db.Date)
    expected_life_years = db.Column(db.Float, default=10.0)
    last_service_date = db.Column(db.Date)
    service_interval_days = db.Column(db.Integer, default=180)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    room = db.relationship('Room', backref='equipment')


class PreventiveSchedule(db.Model):
    """Auto-generated or manual preventive maintenance task."""
    __tablename__ = 'preventive_schedules'
    __table_args__ = (
        db.Index('idx_prev_sched_date_status', 'scheduled_date', 'status'),
        db.Index('idx_prev_sched_room', 'room_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    category = db.Column(db.String(50), nullable=False)
    task_description = db.Column(db.Text, nullable=False)
    scheduled_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(15), default='Pending')
    priority = db.Column(db.String(10), default='Medium')
    risk_level = db.Column(db.String(10))
    predicted_failure_probability = db.Column(db.Float)
    assigned_to = db.Column(db.String(100))
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    source = db.Column(db.String(20), default='auto')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    room = db.relationship('Room', backref='preventive_schedules')
    equipment = db.relationship('Equipment', backref='preventive_schedules')


class EquipmentHealthLog(db.Model):
    """Daily health score snapshot per room."""
    __tablename__ = 'equipment_health_logs'
    __table_args__ = (
        db.Index('idx_health_room_date', 'room_id', 'snapshot_date'),
    )
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey('equipment.id'), nullable=True)
    health_score = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50))
    risk_factors = db.Column(db.Text)
    snapshot_date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    room = db.relationship('Room', backref='health_logs')
    equipment = db.relationship('Equipment', backref='health_logs')


class PreCheckinToken(db.Model):
    """
    One-time token sent to the guest (via WhatsApp/email) to access
    the self-service pre-check-in portal before arrival.
    """
    __tablename__ = 'precheckin_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reservation = db.relationship('Reservation', backref='precheckin_tokens')


class PreCheckinSubmission(db.Model):
    """Guest-submitted pre-check-in data (collected via the public portal)."""
    __tablename__ = 'precheckin_submissions'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False, unique=True)
    token_id = db.Column(db.Integer, db.ForeignKey('precheckin_tokens.id'))
    # Personal info
    full_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date)
    nationality = db.Column(db.String(60))
    address = db.Column(db.Text)
    city = db.Column(db.String(60))
    # ID document
    id_type = db.Column(db.String(30))   # Aadhaar, Passport, DL, Voter ID
    id_number = db.Column(EncryptedString())
    id_photo_path = db.Column(db.String(200))
    # Arrival preferences
    estimated_arrival_time = db.Column(db.String(10))   # e.g. "14:30"
    special_requests = db.Column(db.Text)
    # Consent & signature
    signature_path = db.Column(db.String(200))
    terms_accepted = db.Column(db.Boolean, default=False)
    # Meta
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    reservation = db.relationship('Reservation', backref='precheckin_submission')


class ForeignNationalInfo(db.Model):
    """Visa and passport details for foreign national guests (Form C / FRRO compliance)."""
    __tablename__ = 'foreign_national_info'
    id                   = db.Column(db.Integer, primary_key=True)
    guest_id             = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False, unique=True)
    nationality          = db.Column(db.String(60), nullable=False)
    passport_number      = db.Column(EncryptedString())
    passport_issue_place = db.Column(db.String(100))
    passport_issue_date  = db.Column(db.Date)
    passport_expiry_date = db.Column(db.Date)
    visa_number          = db.Column(db.String(50))
    visa_type            = db.Column(db.String(30))
    visa_issue_date      = db.Column(db.Date)
    visa_expiry_date     = db.Column(db.Date)
    visa_issue_place     = db.Column(db.String(100))
    arrival_from         = db.Column(db.String(100))
    next_destination     = db.Column(db.String(100))
    purpose_of_visit     = db.Column(db.String(100))
    employed_in_india    = db.Column(db.Boolean, default=False)
    employer_name        = db.Column(db.String(200))
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    guest                = db.relationship('Guest', backref=db.backref('foreign_info', uselist=False))


class NoShowLog(db.Model):
    """
    Immutable record created each time a reservation is marked as NoShow.
    Created by night audit (posted_by_user_id=None) or manually by Manager/Admin.
    """
    __tablename__ = 'no_show_logs'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    audit_date = db.Column(db.Date, nullable=False)              # business date the no-show was posted
    fee_applied = db.Column(db.Boolean, default=False)
    fee_amount = db.Column(db.Numeric(10, 2), default=0)
    is_ota = db.Column(db.Boolean, default=False)
    ota_booking_id = db.Column(db.String(100), nullable=True)
    # override_by = Manager/Admin who manually triggered this (null = night audit)
    override_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    override_note = db.Column(db.Text)
    # posted_by = null means automated night audit
    posted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)

    reservation = db.relationship('Reservation', backref='noshow_logs')
    posted_by = db.relationship('User', foreign_keys=[posted_by_user_id])
    override_by = db.relationship('User', foreign_keys=[override_by_user_id])

    __table_args__ = (
        db.Index('idx_noshow_reservation_id', 'reservation_id'),
        db.Index('idx_noshow_audit_date', 'audit_date'),
    )


# ---------------------------------------------------------------------------
# GST Tax Lines
# ---------------------------------------------------------------------------

class TaxLine(db.Model):
    """
    Immutable tax record per charge line per tax component.
    Stored at posting time — never recomputed, so historical invoices
    remain accurate even after rate changes.

    charge_source_type: 'room_night' | 'extra_charge' | 'pos_charge'
    charge_source_id:   for room_night = 'night_YYYY-MM-DD'
                        for extra_charge = str(extra_charge.id)
    tax_type:           'CGST' | 'SGST' | 'IGST' | 'EXEMPT'
    """
    __tablename__ = 'tax_lines'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id      = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    charge_source_type  = db.Column(db.String(20), nullable=False)
    charge_source_id    = db.Column(db.String(50), nullable=False)
    charge_date         = db.Column(db.Date, nullable=False)
    taxable_amount      = db.Column(db.Numeric(12, 2), nullable=False)
    tax_type            = db.Column(db.String(10), nullable=False)   # CGST/SGST/IGST/EXEMPT
    tax_rate            = db.Column(db.Numeric(6, 3), nullable=False)  # e.g. 6.000
    tax_amount          = db.Column(db.Numeric(12, 2), nullable=False)
    is_interstate       = db.Column(db.Boolean, default=False)
    is_exempted         = db.Column(db.Boolean, default=False)
    sac_code            = db.Column(db.String(10), nullable=True)    # SAC code for line
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)

    reservation = db.relationship('Reservation', backref='tax_lines')

    __table_args__ = (
        db.Index('idx_taxline_reservation_id', 'reservation_id'),
        db.Index('idx_taxline_source', 'charge_source_type', 'charge_source_id'),
    )


# ---------------------------------------------------------------------------
# Payment Void Requests
# ---------------------------------------------------------------------------

class VoidRequest(db.Model):
    """
    Two-step void approval workflow.
    FrontDesk creates a request; Manager/Admin approves or rejects.
    Manager/Admin can also bypass this by directly voiding (single-step).
    """
    __tablename__ = 'void_requests'
    id = db.Column(db.Integer, primary_key=True)
    payment_id          = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=False)
    requested_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_at        = db.Column(db.DateTime, default=datetime.utcnow)
    reason              = db.Column(db.String(300), nullable=False)
    status              = db.Column(db.String(20), default='Pending')  # Pending/Approved/Rejected
    decided_by_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    decided_at          = db.Column(db.DateTime, nullable=True)
    rejection_reason    = db.Column(db.String(300), nullable=True)

    payment             = db.relationship('Payment', backref='void_requests')
    requested_by        = db.relationship('User', foreign_keys=[requested_by_user_id])
    decided_by          = db.relationship('User', foreign_keys=[decided_by_user_id])

    __table_args__ = (
        db.Index('idx_voidreq_payment_id', 'payment_id'),
        db.Index('idx_voidreq_status', 'status'),
    )


# ---------------------------------------------------------------------------
# Guest Feedback
# ---------------------------------------------------------------------------

class GuestFeedback(db.Model):
    """
    Post-checkout feedback collected via WhatsApp link or staff entry.
    One record per reservation.
    """
    __tablename__ = 'guest_feedback'
    id = db.Column(db.Integer, primary_key=True)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False, unique=True)
    # Overall rating 1-5
    rating = db.Column(db.Integer, nullable=False)
    # Category ratings (optional)
    cleanliness = db.Column(db.Integer)   # 1-5
    service = db.Column(db.Integer)       # 1-5
    food = db.Column(db.Integer)          # 1-5
    value = db.Column(db.Integer)         # 1-5
    comment = db.Column(db.Text)
    # Would they recommend?
    would_recommend = db.Column(db.Boolean)
    # google_review_pushed: True once we sent them the Google review link
    google_review_pushed = db.Column(db.Boolean, default=False)
    # negative_flag: auto-set when rating <= 2
    negative_flag = db.Column(db.Boolean, default=False)
    # Source: 'whatsapp_link' | 'staff_entry' | 'portal'
    source = db.Column(db.String(20), default='whatsapp_link')
    token = db.Column(db.String(64), unique=True, nullable=True, index=True)  # one-time link token
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))

    reservation = db.relationship('Reservation', backref='feedback')

    __table_args__ = (
        db.Index('idx_feedback_reservation_id', 'reservation_id'),
        db.Index('idx_feedback_rating', 'rating'),
    )


# ---------------------------------------------------------------------------
# Database Backup Log
# ---------------------------------------------------------------------------

class BackupLog(db.Model):
    """Records every database backup attempt."""
    __tablename__ = 'backup_logs'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    size_bytes = db.Column(db.Integer, default=0)
    # manual | scheduled
    backup_type = db.Column(db.String(20), default='manual')
    # success | failed
    status = db.Column(db.String(20), default='success')
    error_message = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])


# ---------------------------------------------------------------------------
# Revenue Intelligence Engine
# ---------------------------------------------------------------------------

class RevenueAlert(db.Model):
    """
    Real-time revenue control alert.
    Created by alert_service.py; surfaced on dashboard and in night audit.

    alert_type:  HIGH_DISCOUNT | REPEATED_DISCOUNT | HIGH_LEAKAGE | SUSPICIOUS_PATTERN
    severity:    LOW | MEDIUM | HIGH
    """
    __tablename__ = 'revenue_alerts'
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reservation_id       = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=True)
    alert_type           = db.Column(db.String(30), nullable=False)
    severity             = db.Column(db.String(10), nullable=False, default='MEDIUM')
    message              = db.Column(db.Text, nullable=False)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)
    resolved             = db.Column(db.Boolean, default=False, nullable=False)
    resolved_at          = db.Column(db.DateTime, nullable=True)
    resolved_by_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    user        = db.relationship('User', foreign_keys=[user_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_user_id])
    reservation = db.relationship('Reservation', backref='revenue_alerts')

    __table_args__ = (
        db.Index('idx_rev_alert_user',     'user_id'),
        db.Index('idx_rev_alert_type',     'alert_type'),
        db.Index('idx_rev_alert_resolved', 'resolved'),
        db.Index('idx_rev_alert_created',  'created_at'),
    )


class StaffPerformanceDaily(db.Model):
    """
    Daily per-staff revenue control snapshot.
    Upserted by performance_service.compute_daily_performance().
    One row per (user_id, date) — enforced by unique constraint.

    flag: HIGH_RISK | TOP_PERFORMER | None
    """
    __tablename__ = 'staff_performance_daily'
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date           = db.Column(db.Date,    nullable=False)
    rooms_handled  = db.Column(db.Integer,        default=0)
    total_revenue  = db.Column(db.Numeric(12, 2), default=0)
    total_leakage  = db.Column(db.Numeric(12, 2), default=0)
    total_discount = db.Column(db.Numeric(12, 2), default=0)
    total_upsell   = db.Column(db.Numeric(12, 2), default=0)
    net_score      = db.Column(db.Numeric(12, 2), default=0)
    rank           = db.Column(db.Integer, nullable=True)
    flag           = db.Column(db.String(20), nullable=True)   # HIGH_RISK | TOP_PERFORMER
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref='performance_records')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'date', name='uq_staff_perf_user_date'),
        db.Index('idx_staff_perf_date', 'date'),
        db.Index('idx_staff_perf_user', 'user_id'),
    )


class OverpaymentLog(db.Model):
    """
    Audit record for every overpayment resolved at checkout.

    reason     : why the guest paid more  (mistake | intentional | other)
    resolution : how it was disposed of   (refund | tip | income)
    """
    __tablename__ = 'overpayment_logs'

    id                  = db.Column(db.Integer, primary_key=True)
    reservation_id      = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    guest_id            = db.Column(db.Integer, db.ForeignKey('guests.id'),        nullable=True)
    overpaid_amount     = db.Column(db.Numeric(10, 2), nullable=False)
    reason              = db.Column(db.String(20),     nullable=False)  # mistake | intentional | other
    resolution          = db.Column(db.String(20),     nullable=False)  # refund  | tip         | income
    refund_mode_id      = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=True)
    waiter_name         = db.Column(db.String(100),    nullable=True)
    remarks             = db.Column(db.Text,           nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)

    reservation  = db.relationship('Reservation', backref='overpayment_logs')
    refund_mode  = db.relationship('PaymentMode', foreign_keys=[refund_mode_id])
    resolved_by  = db.relationship('User',        foreign_keys=[resolved_by_user_id])

    __table_args__ = (
        db.Index('idx_overpay_reservation', 'reservation_id'),
    )


# ---------------------------------------------------------------------------
# CICO Charge Audit Log
# ---------------------------------------------------------------------------

class CICOChargeLog(db.Model):
    """
    Immutable audit record for every CICO (early check-in / late check-out)
    charge event — whether posted, waived, or skipped.

    Written by cico_service.post_charge() and the waiver path in routes.py.
    Never deleted or updated — append-only for auditability.
    """
    __tablename__ = 'cico_charge_logs'

    id                 = db.Column(db.Integer, primary_key=True)
    reservation_id     = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    # 'early_checkin' | 'late_checkout'
    charge_type        = db.Column(db.String(20), nullable=False)
    slab_label         = db.Column(db.String(100))
    pct_applied        = db.Column(db.Integer, default=0)
    amount_calculated  = db.Column(db.Numeric(10, 2), default=0)
    actual_time_str    = db.Column(db.String(5))           # 'HH:MM' in hotel local time
    # posted | waived | grace | skipped
    outcome            = db.Column(db.String(20), nullable=False, default='posted')
    waived             = db.Column(db.Boolean, default=False)
    waived_by_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    waive_reason       = db.Column(db.String(200), nullable=True)
    extra_charge_id    = db.Column(db.Integer, db.ForeignKey('extra_charges.id'), nullable=True)
    staff_user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    timestamp          = db.Column(db.DateTime, default=datetime.utcnow)

    reservation   = db.relationship('Reservation', backref='cico_charge_logs')
    waived_by     = db.relationship('User', foreign_keys=[waived_by_user_id])
    staff_user    = db.relationship('User', foreign_keys=[staff_user_id])
    extra_charge  = db.relationship('ExtraCharge', foreign_keys=[extra_charge_id])

    __table_args__ = (
        db.Index('idx_cico_log_reservation', 'reservation_id'),
        db.Index('idx_cico_log_type', 'charge_type'),
    )


# ---------------------------------------------------------------------------
# Credit Notes (GST-compliant invoice reversals)
# ---------------------------------------------------------------------------

class CreditNote(db.Model):
    """
    GST-compliant credit note issued against an existing invoice.
    Used for partial/full invoice reversals — mapped to CDNR section in GSTR-1.
    Sequential numbering: CN-YYYY-000001.
    """
    __tablename__ = 'credit_notes'

    id                      = db.Column(db.Integer, primary_key=True)
    credit_note_number      = db.Column(db.String(30), unique=True, nullable=False)
    reservation_id          = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    original_invoice_number = db.Column(db.String(50), nullable=False)
    reason                  = db.Column(db.String(200), nullable=False)
    # Amounts
    taxable_amount          = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cgst_amount             = db.Column(db.Numeric(10, 2), default=0)
    sgst_amount             = db.Column(db.Numeric(10, 2), default=0)
    igst_amount             = db.Column(db.Numeric(10, 2), default=0)
    total_amount            = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    # Metadata
    issued_by_user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    issued_at               = db.Column(db.DateTime, default=datetime.utcnow)
    notes                   = db.Column(db.Text)

    reservation = db.relationship('Reservation', backref='credit_notes')
    issued_by   = db.relationship('User')

    __table_args__ = (
        db.Index('idx_creditnote_reservation', 'reservation_id'),
        db.Index('idx_creditnote_issued_at', 'issued_at'),
    )


# ═══════════════════════════════════════════════════════════════════════════
# LOYALTY PROGRAM
# ═══════════════════════════════════════════════════════════════════════════

class LoyaltyConfig(db.Model):
    """Tier definitions and earn/redeem rates (admin-editable)."""
    __tablename__ = 'loyalty_config'
    id                       = db.Column(db.Integer, primary_key=True)
    tier_name                = db.Column(db.String(20), nullable=False, unique=True)
    tier_order               = db.Column(db.Integer, nullable=False, default=0)
    min_points               = db.Column(db.Integer, nullable=False, default=0)
    earn_per_night           = db.Column(db.Integer, nullable=False, default=10)
    earn_per_100_rupees      = db.Column(db.Integer, nullable=False, default=1)
    direct_booking_bonus_pct = db.Column(db.Integer, default=20)
    redemption_value         = db.Column(db.Numeric(10, 2), default=0.50)
    late_checkout_points     = db.Column(db.Integer, default=500)
    early_checkin_points     = db.Column(db.Integer, default=300)
    color_hex                = db.Column(db.String(7), default='#6c757d')
    is_active                = db.Column(db.Boolean, default=True)
    updated_at               = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.CheckConstraint('tier_order > 0', name='ck_loyalty_tier_order_pos'),
        db.CheckConstraint('min_points >= 0', name='ck_loyalty_min_points_pos'),
    )


class LoyaltyMilestone(db.Model):
    """Admin-configured bonus triggers (e.g. 5th stay, ₹1L spend)."""
    __tablename__ = 'loyalty_milestones'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    trigger_type  = db.Column(db.String(20), nullable=False)     # 'stays' or 'spend'
    trigger_value = db.Column(db.Integer, nullable=False)
    bonus_points  = db.Column(db.Integer, nullable=False, default=100)
    is_active     = db.Column(db.Boolean, default=True)
    is_recurring  = db.Column(db.Boolean, default=False)


class LoyaltyTransaction(db.Model):
    """Points ledger. Positive = earn, negative = redeem/expire/adjust."""
    __tablename__ = 'loyalty_transactions'
    id                 = db.Column(db.Integer, primary_key=True)
    guest_id           = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    reservation_id     = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=True)
    txn_type           = db.Column(db.String(20), nullable=False)
    points             = db.Column(db.Integer, nullable=False)
    description        = db.Column(db.String(200), nullable=False)
    reference_amount   = db.Column(db.Numeric(10, 2), nullable=True)
    tier_at_time       = db.Column(db.String(20), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    guest              = db.relationship('Guest', backref='loyalty_transactions')
    reservation        = db.relationship('Reservation', backref='loyalty_transactions')
    created_by         = db.relationship('User')
    __table_args__ = (
        db.Index('idx_loyalty_txn_guest', 'guest_id'),
        db.Index('idx_loyalty_txn_reservation', 'reservation_id'),
        db.Index('idx_loyalty_txn_type', 'txn_type'),
        db.Index('idx_loyalty_txn_created', 'created_at'),
    )


class LoyaltyRedemption(db.Model):
    """Tracks each redemption event."""
    __tablename__ = 'loyalty_redemptions'
    id                 = db.Column(db.Integer, primary_key=True)
    guest_id           = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    reservation_id     = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    redemption_type    = db.Column(db.String(20), nullable=False)
    points_used        = db.Column(db.Integer, nullable=False)
    rupee_value        = db.Column(db.Numeric(10, 2), default=0)
    status             = db.Column(db.String(15), default='Applied')
    transaction_id     = db.Column(db.Integer, db.ForeignKey('loyalty_transactions.id'), nullable=True)
    applied_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    guest              = db.relationship('Guest')
    reservation        = db.relationship('Reservation', backref='loyalty_redemptions')
    transaction        = db.relationship('LoyaltyTransaction')
    applied_by         = db.relationship('User')


# ===========================================================================
# Credit Voucher (Apr 2026 hardening pass)
# ===========================================================================
# Issued when an Advance Booking is cancelled with disposition='credit_voucher'.
# Behaves as a financial liability — the hotel owes the guest this amount,
# redeemable against any future booking.
#
# Lifecycle / status (derived in compute_voucher_status):
#   active          — issued_amount > redeemed_amount, expiry not reached
#   fully_redeemed  — redeemed_amount >= issued_amount
#   expired         — expiry_date passed with balance > 0
#   cancelled       — admin manually voided (rare; audit-logged)
#
# Every redemption inserts a CreditVoucherRedemption row + (typically) a
# Payment row tagged payment_purpose='settlement' so the booking ledger
# sees it as cash without inflating the cash collection report.
class CreditVoucher(db.Model):
    __tablename__ = 'credit_vouchers'
    __table_args__ = (
        db.CheckConstraint('issued_amount > 0', name='ck_voucher_issued_positive'),
        db.CheckConstraint('redeemed_amount >= 0', name='ck_voucher_redeemed_nonneg'),
        db.Index('idx_voucher_guest', 'guest_id'),
        db.Index('idx_voucher_status', 'status'),
    )
    id                       = db.Column(db.Integer, primary_key=True)
    voucher_code             = db.Column(db.String(30), unique=True, nullable=False, index=True)
    guest_id                 = db.Column(db.Integer, db.ForeignKey('guests.id'), nullable=False)
    issued_amount            = db.Column(db.Numeric(10, 2), nullable=False)
    redeemed_amount          = db.Column(db.Numeric(10, 2), default=0, nullable=False)
    issued_date              = db.Column(db.Date,    nullable=False, default=date.today)
    expiry_date              = db.Column(db.Date,    nullable=True)
    status                   = db.Column(db.String(20), default='active', nullable=False)
    issued_from_reservation_id = db.Column(db.Integer,
                                            db.ForeignKey('reservations.id'),
                                            nullable=True)
    issued_by_user_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    fully_redeemed_at        = db.Column(db.DateTime, nullable=True)
    expired_at               = db.Column(db.DateTime, nullable=True)
    cancelled_at             = db.Column(db.DateTime, nullable=True)
    notes                    = db.Column(db.String(300), nullable=True)
    created_at               = db.Column(db.DateTime, default=datetime.utcnow)

    guest                = db.relationship('Guest')
    issued_from_reservation = db.relationship('Reservation', foreign_keys=[issued_from_reservation_id])
    issued_by            = db.relationship('User', foreign_keys=[issued_by_user_id])


class CreditVoucherRedemption(db.Model):
    __tablename__ = 'credit_voucher_redemptions'
    __table_args__ = (
        db.CheckConstraint('amount > 0', name='ck_voucher_redeem_positive'),
        db.Index('idx_voucher_redeem_voucher', 'voucher_id'),
        db.Index('idx_voucher_redeem_reservation', 'reservation_id'),
    )
    id                = db.Column(db.Integer, primary_key=True)
    voucher_id        = db.Column(db.Integer, db.ForeignKey('credit_vouchers.id'), nullable=False)
    reservation_id    = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=False)
    amount            = db.Column(db.Numeric(10, 2), nullable=False)
    redeemed_at       = db.Column(db.DateTime, default=datetime.utcnow)
    redeemed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    payment_id        = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=True)
    notes             = db.Column(db.String(300), nullable=True)

    voucher           = db.relationship('CreditVoucher', backref='redemptions')
    reservation       = db.relationship('Reservation')
    redeemed_by       = db.relationship('User', foreign_keys=[redeemed_by_user_id])
    payment           = db.relationship('Payment')
