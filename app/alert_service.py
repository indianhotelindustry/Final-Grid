"""
alert_service.py — Real-Time Revenue Alert Engine
Fires alerts instantly for: HIGH_DISCOUNT, REPEATED_DISCOUNT,
HIGH_LEAKAGE, SUSPICIOUS_PATTERN.
Non-fatal: alert creation errors are logged but never raise.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import func

log = logging.getLogger(__name__)

# Alert type constants
HIGH_DISCOUNT       = 'HIGH_DISCOUNT'
REPEATED_DISCOUNT   = 'REPEATED_DISCOUNT'
HIGH_LEAKAGE        = 'HIGH_LEAKAGE'
SUSPICIOUS_PATTERN  = 'SUSPICIOUS_PATTERN'

# Severity constants
LOW    = 'LOW'
MEDIUM = 'MEDIUM'
HIGH   = 'HIGH'


class AlertService:
    """
    Static-method service for revenue alert management.
    All check_* methods are non-fatal — they catch & log exceptions internally.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _setting(key: str, default):
        """Read a setting from the Settings table at call time."""
        try:
            from app.models import Settings
            row = Settings.query.filter_by(key=key).first()
            if row is None:
                return default
            val = row.value
            if isinstance(default, float):
                return float(val)
            if isinstance(default, int):
                return int(val)
            return val
        except Exception:
            return default

    @staticmethod
    def _create_alert(user_id: int, alert_type: str, severity: str,
                      message: str, reservation_id=None):
        """
        Persist a RevenueAlert record.
        Non-fatal: any DB error is logged and suppressed.
        """
        try:
            from app.models import db, RevenueAlert
            alert = RevenueAlert(
                user_id=user_id,
                reservation_id=reservation_id,
                alert_type=alert_type,
                severity=severity,
                message=message,
                created_at=datetime.utcnow(),
                resolved=False,
            )
            db.session.add(alert)
            db.session.flush()   # get id without full commit
            log.info('Revenue alert created: type=%s sev=%s user_id=%s',
                     alert_type, severity, user_id)
        except Exception as exc:
            log.error('Failed to create revenue alert (non-fatal): %s', exc)

    # ------------------------------------------------------------------
    # Public check methods — called from routes/revenue_guard
    # ------------------------------------------------------------------

    @staticmethod
    def check_discount(user_id: int, discount_amount: float,
                       reservation_id=None, room_no=None):
        """
        Fire HIGH_DISCOUNT alert if discount_amount exceeds threshold.
        Also fire REPEATED_DISCOUNT if same user applied ≥ N discounts in window.
        """
        try:
            threshold = AlertService._setting('DISCOUNT_ALERT_THRESHOLD', 1000)
            repeat_count  = AlertService._setting('REPEAT_DISCOUNT_COUNT', 3)
            window_minutes = AlertService._setting('REPEAT_TIME_WINDOW_MINUTES', 120)

            # --- HIGH_DISCOUNT ---
            if float(discount_amount) >= float(threshold):
                severity = HIGH if float(discount_amount) >= float(threshold) * 2 else MEDIUM
                msg = (f"High discount of ₹{discount_amount:.2f} applied"
                       f"{' on room ' + str(room_no) if room_no else ''}.")
                AlertService._create_alert(
                    user_id=user_id,
                    alert_type=HIGH_DISCOUNT,
                    severity=severity,
                    message=msg,
                    reservation_id=reservation_id,
                )

            # --- REPEATED_DISCOUNT ---
            try:
                from app.models import RevenueAlert
                window_start = datetime.utcnow() - timedelta(minutes=int(window_minutes))
                recent = RevenueAlert.query.filter(
                    RevenueAlert.user_id == user_id,
                    RevenueAlert.alert_type == HIGH_DISCOUNT,
                    RevenueAlert.created_at >= window_start,
                ).count()
                # +1 for the one we just created above
                if recent + 1 >= int(repeat_count):
                    msg = (f"User has applied {recent + 1} discounts in the last "
                           f"{window_minutes} minutes. Possible discount abuse.")
                    AlertService._create_alert(
                        user_id=user_id,
                        alert_type=REPEATED_DISCOUNT,
                        severity=HIGH,
                        message=msg,
                        reservation_id=reservation_id,
                    )
            except Exception as exc:
                log.error('REPEATED_DISCOUNT check failed (non-fatal): %s', exc)

        except Exception as exc:
            log.error('check_discount failed (non-fatal): %s', exc)

    @staticmethod
    def check_leakage(user_id: int, leakage_amount: float,
                      reservation_id=None, room_no=None, reason: str = ''):
        """
        Fire HIGH_LEAKAGE alert if leakage_amount exceeds threshold.
        """
        try:
            threshold = AlertService._setting('LEAKAGE_ALERT_THRESHOLD', 3000)
            if float(leakage_amount) <= 0:
                return
            if float(leakage_amount) >= float(threshold):
                severity = HIGH if float(leakage_amount) >= float(threshold) * 1.5 else MEDIUM
                msg = (f"Revenue leakage of ₹{leakage_amount:.2f} detected"
                       f"{' on room ' + str(room_no) if room_no else ''}"
                       f"{'. Reason: ' + reason if reason else ''}.")
                AlertService._create_alert(
                    user_id=user_id,
                    alert_type=HIGH_LEAKAGE,
                    severity=severity,
                    message=msg,
                    reservation_id=reservation_id,
                )
        except Exception as exc:
            log.error('check_leakage failed (non-fatal): %s', exc)

    @staticmethod
    def check_suspicious_pattern(user_id: int, reservation_id=None,
                                  note: str = ''):
        """
        Fire SUSPICIOUS_PATTERN alert for manual use (e.g., from revenue_guard
        when unusual combinations are detected).
        """
        try:
            msg = f"Suspicious revenue pattern detected.{' ' + note if note else ''}"
            AlertService._create_alert(
                user_id=user_id,
                alert_type=SUSPICIOUS_PATTERN,
                severity=HIGH,
                message=msg,
                reservation_id=reservation_id,
            )
        except Exception as exc:
            log.error('check_suspicious_pattern failed (non-fatal): %s', exc)

    # ------------------------------------------------------------------
    # Query methods — called from API endpoints
    # ------------------------------------------------------------------

    @staticmethod
    def get_live_alerts(limit: int = 50, severity_filter=None,
                        unresolved_only: bool = True):
        """
        Return active (unresolved) alerts, newest first.
        Returns list of dicts for JSON serialisation.
        """
        try:
            from app.models import RevenueAlert, User
            q = RevenueAlert.query
            if unresolved_only:
                q = q.filter(RevenueAlert.resolved == False)
            if severity_filter:
                q = q.filter(RevenueAlert.severity == severity_filter)
            alerts = q.order_by(RevenueAlert.created_at.desc()).limit(limit).all()

            result = []
            for a in alerts:
                result.append({
                    'id':              a.id,
                    'alert_type':      a.alert_type,
                    'severity':        a.severity,
                    'message':         a.message,
                    'user_id':         a.user_id,
                    'username':        a.user.username if a.user else None,
                    'reservation_id':  a.reservation_id,
                    'created_at':      a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'resolved':        a.resolved,
                })
            return result
        except Exception as exc:
            log.error('get_live_alerts failed: %s', exc)
            return []

    @staticmethod
    def get_alert_counts():
        """
        Return dict with counts by severity for dashboard badges.
        {'HIGH': n, 'MEDIUM': n, 'LOW': n, 'total': n}
        """
        try:
            from app.models import RevenueAlert, db
            rows = (
                db.session.query(RevenueAlert.severity,
                                 func.count(RevenueAlert.id))
                .filter(RevenueAlert.resolved == False)
                .group_by(RevenueAlert.severity)
                .all()
            )
            counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
            for severity, cnt in rows:
                if severity in counts:
                    counts[severity] = cnt
            counts['total'] = sum(counts.values())
            return counts
        except Exception as exc:
            log.error('get_alert_counts failed: %s', exc)
            return {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'total': 0}

    @staticmethod
    def resolve_alert(alert_id: int, resolved_by_user_id: int):
        """
        Mark a single alert as resolved.
        Returns (success: bool, message: str).
        """
        try:
            from app.models import db, RevenueAlert
            alert = db.session.get(RevenueAlert, alert_id)
            if alert is None:
                return False, 'Alert not found'
            if alert.resolved:
                return True, 'Already resolved'
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            alert.resolved_by_user_id = resolved_by_user_id
            db.session.commit()
            return True, 'Resolved'
        except Exception as exc:
            log.error('resolve_alert failed: %s', exc)
            return False, str(exc)

    @staticmethod
    def resolve_all(resolved_by_user_id: int):
        """Bulk-resolve all outstanding alerts (e.g., night-audit sign-off)."""
        try:
            from app.models import db, RevenueAlert
            now = datetime.utcnow()
            updated = (
                db.session.query(RevenueAlert)
                .filter(RevenueAlert.resolved == False)
                .all()
            )
            for a in updated:
                a.resolved = True
                a.resolved_at = now
                a.resolved_by_user_id = resolved_by_user_id
            db.session.commit()
            return True, f'{len(updated)} alerts resolved'
        except Exception as exc:
            log.error('resolve_all failed: %s', exc)
            return False, str(exc)
