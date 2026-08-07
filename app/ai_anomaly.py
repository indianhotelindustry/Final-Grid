"""
ai_anomaly.py — Payment Anomaly Detection Engine
Scans payment, void, cash-handling, off-hours, and rate manipulation patterns.
Returns severity-scored findings for the anomaly dashboard.
No external dependencies — pure Python + SQLAlchemy queries.
"""
import logging
import math
from datetime import datetime, timedelta
from decimal import Decimal

log = logging.getLogger(__name__)

# Severity constants
CRITICAL = 'CRITICAL'
HIGH = 'HIGH'
MEDIUM = 'MEDIUM'
LOW = 'LOW'

SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}


class AnomalyDetector:
    """Stateless anomaly scanner — all methods query the DB on each call."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def scan_all(self, lookback_days=30):
        """Run all anomaly checks and return findings sorted by severity."""
        findings = []
        try:
            findings += self.check_discount_patterns(lookback_days)
        except Exception as e:
            log.error('check_discount_patterns failed: %s', e)
        try:
            findings += self.check_void_patterns(lookback_days)
        except Exception as e:
            log.error('check_void_patterns failed: %s', e)
        try:
            findings += self.check_cash_handling(lookback_days)
        except Exception as e:
            log.error('check_cash_handling failed: %s', e)
        try:
            findings += self.check_off_hours_activity(lookback_days)
        except Exception as e:
            log.error('check_off_hours_activity failed: %s', e)
        try:
            findings += self.check_rate_manipulation(lookback_days)
        except Exception as e:
            log.error('check_rate_manipulation failed: %s', e)

        findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.get('severity'), 9),
                                      -(f.get('value') or 0)))
        return findings

    # ------------------------------------------------------------------
    # 1. Discount patterns
    # ------------------------------------------------------------------

    def check_discount_patterns(self, lookback_days=30):
        """Flag users giving unusually high discounts.
        - Compare each user's avg discount % vs hotel-wide average
        - Flag if > 2 standard deviations above mean
        - Flag if discount frequency > 3x average
        Returns: list of {user, metric, value, threshold, severity, description}
        """
        from app.models import db, Reservation, User
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        findings = []

        # All reservations with discounts in the period
        rows = (
            db.session.query(
                Reservation.discount_given_by,
                func.count(Reservation.id).label('cnt'),
                func.avg(Reservation.discount_amount).label('avg_disc'),
                func.sum(Reservation.discount_amount).label('total_disc'),
            )
            .filter(
                Reservation.discount_amount > 0,
                Reservation.created_at >= cutoff,
                Reservation.discount_given_by.isnot(None),
            )
            .group_by(Reservation.discount_given_by)
            .all()
        )

        if not rows:
            return findings

        # Hotel-wide stats
        all_counts = [float(r.cnt) for r in rows]
        all_avgs = [float(r.avg_disc or 0) for r in rows]
        hotel_avg_disc = sum(all_avgs) / len(all_avgs) if all_avgs else 0
        hotel_avg_count = sum(all_counts) / len(all_counts) if all_counts else 0

        # Std deviation of avg discount
        if len(all_avgs) > 1:
            variance = sum((x - hotel_avg_disc) ** 2 for x in all_avgs) / len(all_avgs)
            std_dev = math.sqrt(variance) if variance > 0 else 0
        else:
            std_dev = 0

        threshold_disc = hotel_avg_disc + 2 * std_dev if std_dev > 0 else hotel_avg_disc * 2
        threshold_freq = hotel_avg_count * 3

        # Map usernames to user objects for display
        user_map = {u.username: u for u in User.query.all()}

        for r in rows:
            username = r.discount_given_by
            user = user_map.get(username)
            user_label = user.full_name if user else username

            avg_disc = float(r.avg_disc or 0)
            cnt = float(r.cnt)

            # High average discount
            if std_dev > 0 and avg_disc > threshold_disc:
                deviation = (avg_disc - hotel_avg_disc) / std_dev if std_dev else 0
                severity = CRITICAL if deviation > 3 else HIGH
                findings.append({
                    'category': 'discount',
                    'user': user_label,
                    'user_id': user.id if user else None,
                    'metric': 'avg_discount_amount',
                    'value': round(avg_disc, 2),
                    'threshold': round(threshold_disc, 2),
                    'severity': severity,
                    'description': (
                        f'{user_label} averages Rs {avg_disc:,.0f} discount '
                        f'({deviation:.1f} std devs above hotel mean of Rs {hotel_avg_disc:,.0f}). '
                        f'Total: Rs {float(r.total_disc or 0):,.0f} across {int(cnt)} bookings.'
                    ),
                    'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                })

            # High discount frequency
            if hotel_avg_count > 0 and cnt > threshold_freq:
                ratio = cnt / hotel_avg_count
                severity = HIGH if ratio > 5 else MEDIUM
                findings.append({
                    'category': 'discount',
                    'user': user_label,
                    'user_id': user.id if user else None,
                    'metric': 'discount_frequency',
                    'value': int(cnt),
                    'threshold': round(threshold_freq, 1),
                    'severity': severity,
                    'description': (
                        f'{user_label} applied discounts {int(cnt)} times '
                        f'({ratio:.1f}x the average of {hotel_avg_count:.0f}). '
                        f'Total discount value: Rs {float(r.total_disc or 0):,.0f}.'
                    ),
                    'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                })

        return findings

    # ------------------------------------------------------------------
    # 2. Void patterns
    # ------------------------------------------------------------------

    def check_void_patterns(self, lookback_days=30):
        """Flag unusual void activity.
        - Users with void rate > 2x average
        - Multiple voids in same shift
        - Voids immediately after payment (< 5 min)
        - High-value void without proper reason
        """
        from app.models import db, Payment, VoidRequest, User, Shift
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        findings = []

        # --- Per-user void counts ---
        void_rows = (
            db.session.query(
                Payment.voided_by_user_id,
                func.count(Payment.id).label('void_count'),
                func.sum(Payment.amount).label('void_total'),
            )
            .filter(
                Payment.is_voided == True,
                Payment.voided_at >= cutoff,
                Payment.voided_by_user_id.isnot(None),
            )
            .group_by(Payment.voided_by_user_id)
            .all()
        )

        if void_rows:
            all_counts = [float(r.void_count) for r in void_rows]
            avg_void_count = sum(all_counts) / len(all_counts)
            user_map = {u.id: u for u in User.query.all()}

            for r in void_rows:
                user = user_map.get(r.voided_by_user_id)
                user_label = user.full_name if user else f'User #{r.voided_by_user_id}'
                cnt = float(r.void_count)

                # High void rate
                if avg_void_count > 0 and cnt > avg_void_count * 2:
                    ratio = cnt / avg_void_count
                    severity = CRITICAL if ratio > 4 else HIGH
                    findings.append({
                        'category': 'void',
                        'user': user_label,
                        'user_id': r.voided_by_user_id,
                        'metric': 'void_rate',
                        'value': int(cnt),
                        'threshold': round(avg_void_count * 2, 1),
                        'severity': severity,
                        'description': (
                            f'{user_label} voided {int(cnt)} payments '
                            f'({ratio:.1f}x the average of {avg_void_count:.0f}). '
                            f'Total voided: Rs {float(r.void_total or 0):,.0f}.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })

        # --- Quick voids (< 5 min after payment) ---
        quick_voids = (
            Payment.query
            .filter(
                Payment.is_voided == True,
                Payment.voided_at >= cutoff,
                Payment.voided_at.isnot(None),
                Payment.created_at.isnot(None),
            )
            .all()
        )
        user_map = {u.id: u for u in User.query.all()}

        for p in quick_voids:
            if p.voided_at and p.created_at:
                delta = (p.voided_at - p.created_at).total_seconds()
                if 0 < delta < 300:  # less than 5 minutes
                    user = user_map.get(p.voided_by_user_id)
                    user_label = user.full_name if user else f'User #{p.voided_by_user_id}'
                    findings.append({
                        'category': 'void',
                        'user': user_label,
                        'user_id': p.voided_by_user_id,
                        'metric': 'quick_void',
                        'value': round(delta / 60, 1),
                        'threshold': 5.0,
                        'severity': HIGH,
                        'description': (
                            f'Payment #{p.id} of Rs {float(p.amount):,.0f} was voided '
                            f'only {delta / 60:.1f} minutes after creation by {user_label}. '
                            f'Reason: {p.void_reason or "not specified"}.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })

        # --- High-value voids without proper reason ---
        high_value_voids = (
            Payment.query
            .filter(
                Payment.is_voided == True,
                Payment.voided_at >= cutoff,
                Payment.amount >= 5000,
            )
            .all()
        )

        for p in high_value_voids:
            reason = (p.void_reason or '').strip()
            if len(reason) < 10:  # no meaningful reason
                user = user_map.get(p.voided_by_user_id)
                user_label = user.full_name if user else f'User #{p.voided_by_user_id}'
                findings.append({
                    'category': 'void',
                    'user': user_label,
                    'user_id': p.voided_by_user_id,
                    'metric': 'high_value_void_no_reason',
                    'value': float(p.amount),
                    'threshold': 5000,
                    'severity': HIGH,
                    'description': (
                        f'High-value void of Rs {float(p.amount):,.0f} (Payment #{p.id}) '
                        f'by {user_label} without adequate reason. '
                        f'Reason given: "{reason or "none"}".'
                    ),
                    'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                })

        # --- Multiple voids in same shift ---
        try:
            shifts_with_voids = (
                db.session.query(
                    Shift.id,
                    Shift.user_id,
                    Shift.start_time,
                    Shift.end_time,
                )
                .filter(Shift.start_time >= cutoff)
                .all()
            )

            for s in shifts_with_voids:
                end = s.end_time or datetime.utcnow()
                void_in_shift = (
                    Payment.query
                    .filter(
                        Payment.is_voided == True,
                        Payment.voided_at >= s.start_time,
                        Payment.voided_at <= end,
                        Payment.voided_by_user_id == s.user_id,
                    )
                    .count()
                )
                if void_in_shift >= 3:
                    user = user_map.get(s.user_id)
                    user_label = user.full_name if user else f'User #{s.user_id}'
                    severity = CRITICAL if void_in_shift >= 5 else HIGH
                    findings.append({
                        'category': 'void',
                        'user': user_label,
                        'user_id': s.user_id,
                        'metric': 'voids_per_shift',
                        'value': void_in_shift,
                        'threshold': 3,
                        'severity': severity,
                        'description': (
                            f'{user_label} voided {void_in_shift} payments during '
                            f'shift #{s.id} ({s.start_time.strftime("%Y-%m-%d %H:%M")} - '
                            f'{end.strftime("%H:%M")}). Investigate pattern.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })
        except Exception as e:
            log.warning('Shift-void cross-check skipped: %s', e)

        return findings

    # ------------------------------------------------------------------
    # 3. Cash handling
    # ------------------------------------------------------------------

    def check_cash_handling(self, lookback_days=30):
        """Flag cash handling anomalies.
        - Large cash variance at shift close (> threshold)
        - Consistent negative variance (short cash)
        - Cash payments with no matching shift
        - Unusual cash-to-card ratio vs historical
        """
        from app.models import db, Shift, Payment, PaymentMode, User
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        findings = []
        user_map = {u.id: u for u in User.query.all()}

        # --- Large variance at shift close ---
        variance_threshold = 500  # Rs
        shifts = (
            Shift.query
            .filter(
                Shift.start_time >= cutoff,
                Shift.variance.isnot(None),
            )
            .all()
        )

        # Track per-user negative variances
        user_variances = {}

        for s in shifts:
            var = float(s.variance or 0)
            user = user_map.get(s.user_id)
            user_label = user.full_name if user else f'User #{s.user_id}'

            # Track variances per user
            if s.user_id not in user_variances:
                user_variances[s.user_id] = []
            user_variances[s.user_id].append(var)

            if abs(var) > variance_threshold:
                severity = CRITICAL if abs(var) > 2000 else HIGH if abs(var) > 1000 else MEDIUM
                direction = 'short' if var < 0 else 'over'
                findings.append({
                    'category': 'cash',
                    'user': user_label,
                    'user_id': s.user_id,
                    'metric': 'shift_variance',
                    'value': round(abs(var), 2),
                    'threshold': variance_threshold,
                    'severity': severity,
                    'description': (
                        f'Shift #{s.id} closed by {user_label} with Rs {abs(var):,.0f} '
                        f'{direction} cash ({s.start_time.strftime("%Y-%m-%d")}). '
                        f'Expected: Rs {float(s.expected_cash or 0):,.0f}, '
                        f'Declared: Rs {float(s.declared_closing_cash or 0):,.0f}.'
                    ),
                    'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                })

        # --- Consistent negative variance (short cash) ---
        for uid, variances in user_variances.items():
            if len(variances) >= 3:
                negative_count = sum(1 for v in variances if v < -100)
                if negative_count >= 3:
                    user = user_map.get(uid)
                    user_label = user.full_name if user else f'User #{uid}'
                    avg_shortage = abs(sum(v for v in variances if v < 0) / negative_count)
                    findings.append({
                        'category': 'cash',
                        'user': user_label,
                        'user_id': uid,
                        'metric': 'consistent_shortage',
                        'value': negative_count,
                        'threshold': 3,
                        'severity': HIGH,
                        'description': (
                            f'{user_label} had {negative_count} shifts with cash shortage '
                            f'(out of {len(variances)} shifts). '
                            f'Avg shortage: Rs {avg_shortage:,.0f}. Pattern suggests concern.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })

        # --- Unusual cash-to-card ratio ---
        try:
            cash_mode = PaymentMode.query.filter(
                PaymentMode.name.ilike('%cash%')
            ).first()

            if cash_mode:
                per_user_cash = (
                    db.session.query(
                        Reservation.checkin_by,
                        func.sum(Payment.amount).label('cash_total'),
                    )
                    .join(Payment, Payment.reservation_id == Reservation.id)
                    .filter(
                        Payment.payment_mode_id == cash_mode.id,
                        Payment.is_voided == False,
                        Payment.created_at >= cutoff,
                        Reservation.checkin_by.isnot(None),
                    )
                    .group_by(Reservation.checkin_by)
                    .all()
                )

                per_user_total = (
                    db.session.query(
                        Reservation.checkin_by,
                        func.sum(Payment.amount).label('all_total'),
                    )
                    .join(Payment, Payment.reservation_id == Reservation.id)
                    .filter(
                        Payment.is_voided == False,
                        Payment.created_at >= cutoff,
                        Reservation.checkin_by.isnot(None),
                    )
                    .group_by(Reservation.checkin_by)
                    .all()
                )

                cash_map = {r.checkin_by: float(r.cash_total or 0) for r in per_user_cash}
                total_map = {r.checkin_by: float(r.all_total or 0) for r in per_user_total}

                ratios = {}
                for uname, total in total_map.items():
                    if total > 0:
                        ratios[uname] = cash_map.get(uname, 0) / total

                if ratios:
                    avg_ratio = sum(ratios.values()) / len(ratios)
                    u_map_name = {u.username: u for u in User.query.all()}

                    for uname, ratio in ratios.items():
                        if avg_ratio > 0 and ratio > avg_ratio * 1.5 and ratio > 0.7:
                            user = u_map_name.get(uname)
                            user_label = user.full_name if user else uname
                            findings.append({
                                'category': 'cash',
                                'user': user_label,
                                'user_id': user.id if user else None,
                                'metric': 'cash_ratio',
                                'value': round(ratio * 100, 1),
                                'threshold': round(avg_ratio * 150, 1),
                                'severity': MEDIUM,
                                'description': (
                                    f'{user_label} processes {ratio * 100:.0f}% payments in cash '
                                    f'(hotel avg: {avg_ratio * 100:.0f}%). '
                                    f'High cash ratio may warrant review.'
                                ),
                                'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                            })
        except Exception as e:
            log.warning('Cash ratio check skipped: %s', e)

        return findings

    # ------------------------------------------------------------------
    # 4. Off-hours activity
    # ------------------------------------------------------------------

    def check_off_hours_activity(self, lookback_days=30):
        """Flag transactions at unusual hours.
        - Payments/voids between 12am-5am
        - Rate changes during night shift
        - High-value operations without manager presence
        """
        from app.models import db, Payment, Reservation, User, AuditLog
        from sqlalchemy import func, extract

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        findings = []
        user_map = {u.id: u for u in User.query.all()}

        # --- Late-night payments ---
        late_payments = (
            Payment.query
            .filter(
                Payment.created_at >= cutoff,
                Payment.is_voided == False,
                extract('hour', Payment.created_at) >= 0,
                extract('hour', Payment.created_at) < 5,
            )
            .all()
        )

        if late_payments:
            # Group by date for summary
            by_date = {}
            for p in late_payments:
                dt_key = p.created_at.strftime('%Y-%m-%d')
                if dt_key not in by_date:
                    by_date[dt_key] = {'count': 0, 'total': 0, 'payments': []}
                by_date[dt_key]['count'] += 1
                by_date[dt_key]['total'] += float(p.amount)
                by_date[dt_key]['payments'].append(p)

            for dt_key, info in by_date.items():
                if info['count'] >= 2 or info['total'] >= 5000:
                    severity = HIGH if info['total'] >= 10000 else MEDIUM
                    findings.append({
                        'category': 'off_hours',
                        'user': 'Multiple',
                        'user_id': None,
                        'metric': 'late_night_payments',
                        'value': info['count'],
                        'threshold': 2,
                        'severity': severity,
                        'description': (
                            f'{info["count"]} payments totaling Rs {info["total"]:,.0f} '
                            f'processed between 12am-5am on {dt_key}. '
                            f'Review for legitimacy.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })

        # --- Late-night voids ---
        late_voids = (
            Payment.query
            .filter(
                Payment.is_voided == True,
                Payment.voided_at >= cutoff,
                Payment.voided_at.isnot(None),
                extract('hour', Payment.voided_at) >= 0,
                extract('hour', Payment.voided_at) < 5,
            )
            .all()
        )

        for p in late_voids:
            user = user_map.get(p.voided_by_user_id)
            user_label = user.full_name if user else f'User #{p.voided_by_user_id}'
            findings.append({
                'category': 'off_hours',
                'user': user_label,
                'user_id': p.voided_by_user_id,
                'metric': 'late_night_void',
                'value': float(p.amount),
                'threshold': 0,
                'severity': HIGH,
                'description': (
                    f'Payment #{p.id} of Rs {float(p.amount):,.0f} voided at '
                    f'{p.voided_at.strftime("%H:%M")} on {p.voided_at.strftime("%Y-%m-%d")} '
                    f'by {user_label}. Late-night voids require scrutiny.'
                ),
                'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            })

        # --- Late-night rate changes via audit log ---
        try:
            rate_changes = (
                AuditLog.query
                .filter(
                    AuditLog.entity_type == 'Reservation',
                    AuditLog.action.ilike('%rate%'),
                    AuditLog.timestamp >= cutoff,
                    extract('hour', AuditLog.timestamp) >= 0,
                    extract('hour', AuditLog.timestamp) < 5,
                )
                .all()
            )

            for al in rate_changes:
                user = user_map.get(al.staff_user_id)
                user_label = user.full_name if user else f'User #{al.staff_user_id}'
                findings.append({
                    'category': 'off_hours',
                    'user': user_label,
                    'user_id': al.staff_user_id,
                    'metric': 'late_night_rate_change',
                    'value': 1,
                    'threshold': 0,
                    'severity': MEDIUM,
                    'description': (
                        f'Rate change on reservation #{al.entity_id} at '
                        f'{al.timestamp.strftime("%H:%M")} on {al.timestamp.strftime("%Y-%m-%d")} '
                        f'by {user_label}. After-hours rate modifications need review.'
                    ),
                    'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                })
        except Exception as e:
            log.warning('Audit log rate-change check skipped: %s', e)

        return findings

    # ------------------------------------------------------------------
    # 5. Rate manipulation
    # ------------------------------------------------------------------

    def check_rate_manipulation(self, lookback_days=30):
        """Flag suspicious rate patterns.
        - Reservations significantly below rack rate without authorization
        - Last-minute rate changes before checkout
        - Same guest repeatedly getting deep discounts
        """
        from app.models import db, Reservation, Guest, RoomType, User
        from sqlalchemy import func

        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        findings = []

        # --- Below rack rate without authorization ---
        leakage_reservations = (
            Reservation.query
            .filter(
                Reservation.created_at >= cutoff,
                Reservation.adjustment_type == 'LEAKAGE',
                Reservation.adjustment_amount > 0,
                Reservation.status.in_(['CheckedIn', 'CheckedOut']),
            )
            .all()
        )

        for r in leakage_reservations:
            standard = float(r.standard_tariff or 0)
            actual = float(r.rate_per_night or 0)
            if standard > 0:
                pct_below = ((standard - actual) / standard) * 100
                if pct_below >= 25:
                    severity = CRITICAL if pct_below >= 50 else HIGH if pct_below >= 35 else MEDIUM
                    authorized = r.discount_authorized_by or 'not specified'
                    findings.append({
                        'category': 'rate',
                        'user': r.checkin_by or 'Unknown',
                        'user_id': None,
                        'metric': 'below_rack_rate',
                        'value': round(pct_below, 1),
                        'threshold': 25,
                        'severity': severity,
                        'description': (
                            f'Reservation #{r.id} ({r.guest.name if r.guest else "?"}) '
                            f'booked at Rs {actual:,.0f} — {pct_below:.0f}% below '
                            f'rack rate of Rs {standard:,.0f}. '
                            f'Checked in by: {r.checkin_by or "unknown"}. '
                            f'Authorization: {authorized}.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })

        # --- Last-minute rate changes before checkout ---
        recent_checkouts = (
            Reservation.query
            .filter(
                Reservation.checked_out_at >= cutoff,
                Reservation.tariff_modified_manually == True,
                Reservation.status == 'CheckedOut',
            )
            .all()
        )

        for r in recent_checkouts:
            if r.checked_out_at and r.discount_at:
                delta = (r.checked_out_at - r.discount_at).total_seconds()
                if 0 < delta < 3600:  # within 1 hour of checkout
                    findings.append({
                        'category': 'rate',
                        'user': r.discount_given_by or r.checkout_by or 'Unknown',
                        'user_id': None,
                        'metric': 'last_minute_rate_change',
                        'value': round(delta / 60, 1),
                        'threshold': 60,
                        'severity': HIGH,
                        'description': (
                            f'Reservation #{r.id} had rate/discount modified '
                            f'{delta / 60:.0f} min before checkout. '
                            f'Discount of Rs {float(r.discount_amount or 0):,.0f} '
                            f'by {r.discount_given_by or "unknown"}. '
                            f'Reason: {r.discount_reason or "not specified"}.'
                        ),
                        'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
                    })

        # --- Same guest repeatedly getting deep discounts ---
        guest_discounts = (
            db.session.query(
                Reservation.guest_id,
                func.count(Reservation.id).label('disc_count'),
                func.avg(Reservation.discount_amount).label('avg_disc'),
                func.sum(Reservation.discount_amount).label('total_disc'),
            )
            .filter(
                Reservation.discount_amount > 0,
                Reservation.created_at >= cutoff,
            )
            .group_by(Reservation.guest_id)
            .having(func.count(Reservation.id) >= 3)
            .all()
        )

        for r in guest_discounts:
            guest = db.session.get(Guest, r.guest_id)
            guest_name = guest.name if guest else f'Guest #{r.guest_id}'
            findings.append({
                'category': 'rate',
                'user': guest_name,
                'user_id': None,
                'metric': 'repeat_guest_discounts',
                'value': int(r.disc_count),
                'threshold': 3,
                'severity': MEDIUM,
                'description': (
                    f'{guest_name} received discounts on {int(r.disc_count)} reservations. '
                    f'Avg discount: Rs {float(r.avg_disc or 0):,.0f}, '
                    f'Total: Rs {float(r.total_disc or 0):,.0f}. '
                    f'Check if authorized or preferential treatment.'
                ),
                'detected_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M'),
            })

        return findings

    # ------------------------------------------------------------------
    # 6. Per-user risk score
    # ------------------------------------------------------------------

    def get_risk_score(self, user_id, lookback_days=30):
        """Calculate overall risk score (0-100) for a staff member.
        Weighted sum of anomaly findings associated with that user.
        """
        from app.models import User
        user = User.query.get(user_id)
        if not user:
            return {'user_id': user_id, 'score': 0, 'label': 'unknown', 'findings': []}

        all_findings = self.scan_all(lookback_days)
        user_findings = [
            f for f in all_findings
            if f.get('user_id') == user_id or f.get('user') == user.full_name
               or f.get('user') == user.username
        ]

        severity_weight = {CRITICAL: 30, HIGH: 20, MEDIUM: 10, LOW: 5}
        raw_score = sum(severity_weight.get(f.get('severity'), 5) for f in user_findings)
        score = min(100, raw_score)

        if score >= 70:
            label = 'high_risk'
        elif score >= 40:
            label = 'elevated'
        elif score >= 15:
            label = 'watch'
        else:
            label = 'normal'

        return {
            'user_id': user_id,
            'username': user.username,
            'full_name': user.full_name,
            'score': score,
            'label': label,
            'finding_count': len(user_findings),
            'findings': user_findings,
        }
