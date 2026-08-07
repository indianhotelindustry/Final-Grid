"""
performance_service.py — Staff Performance Scorecard
Aggregates per-user daily revenue metrics and flags HIGH_RISK / TOP_PERFORMER.
"""
import logging
from datetime import date as date_type, datetime
from decimal import Decimal

log = logging.getLogger(__name__)


class PerformanceService:

    @staticmethod
    def compute_daily_performance(target_date=None):
        """
        Compute (or recompute) StaffPerformanceDaily rows for target_date.
        Upserts — safe to call multiple times.
        Returns list of StaffPerformanceDaily objects.
        """
        if target_date is None:
            target_date = date_type.today()
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        try:
            from app.models import db, User, Reservation, StaffPerformanceDaily

            # Pull all checked-in reservations attributed to this date.
            # We use checkin_date == target_date as the anchor.
            reservations = Reservation.query.filter(
                Reservation.checkin_date == target_date,
                Reservation.status.in_(['checked_in', 'checked_out']),
            ).all()

            # Aggregate per user (keyed by username for checkin_by)
            from collections import defaultdict
            agg = defaultdict(lambda: {
                'rooms': 0,
                'revenue': Decimal('0'),
                'leakage': Decimal('0'),
                'discount': Decimal('0'),
                'upsell': Decimal('0'),
            })

            for r in reservations:
                uname = r.checkin_by or '__unknown__'
                a = agg[uname]
                a['rooms'] += 1

                rate = Decimal(str(r.rate_per_night or 0))
                nights = r.num_nights or 1
                a['revenue'] += rate * nights

                # Leakage: expected_tariff - rate (if positive)
                if r.expected_tariff is not None:
                    diff = Decimal(str(r.expected_tariff)) - rate
                    if diff > 0:
                        a['leakage'] += diff * nights

                # Discount given
                if r.discount_amount:
                    a['discount'] += Decimal(str(r.discount_amount))

                # Upsell: rate above standard base_rate
                if r.standard_tariff is not None:
                    diff = rate - Decimal(str(r.standard_tariff))
                    if diff > 0:
                        a['upsell'] += diff * nights

            # Map usernames → user_ids
            results = []
            all_users = {u.username: u.id for u in User.query.all()}

            for uname, data in agg.items():
                if uname == '__unknown__':
                    continue
                user_id = all_users.get(uname)
                if not user_id:
                    continue

                net_score = data['upsell'] - data['leakage'] - data['discount']
                flag = None
                if data['leakage'] > Decimal('5000') or data['discount'] > Decimal('3000'):
                    flag = 'HIGH_RISK'
                elif net_score > Decimal('2000'):
                    flag = 'TOP_PERFORMER'

                # Upsert into StaffPerformanceDaily
                existing = StaffPerformanceDaily.query.filter_by(
                    user_id=user_id, date=target_date
                ).first()

                if existing:
                    row = existing
                else:
                    row = StaffPerformanceDaily(user_id=user_id, date=target_date)
                    db.session.add(row)

                row.rooms_handled  = data['rooms']
                row.total_revenue  = data['revenue']
                row.total_leakage  = data['leakage']
                row.total_discount = data['discount']
                row.total_upsell   = data['upsell']
                row.net_score      = net_score
                row.flag           = flag
                row.updated_at     = datetime.utcnow()
                results.append(row)

            # Rank by net_score descending
            results.sort(key=lambda x: float(x.net_score or 0), reverse=True)
            for i, row in enumerate(results, start=1):
                row.rank = i

            db.session.commit()
            return results

        except Exception as exc:
            log.error('compute_daily_performance failed: %s', exc)
            try:
                from app.models import db
                db.session.rollback()
            except Exception:
                pass
            return []

    @staticmethod
    def get_today_performance():
        """
        Return today's StaffPerformanceDaily rows (stored or on-the-fly).
        Returns list of dicts suitable for JSON serialisation.
        """
        today = date_type.today()
        try:
            from app.models import StaffPerformanceDaily
            rows = StaffPerformanceDaily.query.filter_by(date=today).all()
            if not rows:
                rows = PerformanceService.compute_daily_performance(today)

            result = []
            for r in rows:
                result.append({
                    'user_id':        r.user_id,
                    'username':       r.user.username if r.user else None,
                    'full_name':      r.user.full_name if r.user else None,
                    'date':           r.date.isoformat(),
                    'rooms_handled':  r.rooms_handled,
                    'total_revenue':  float(r.total_revenue  or 0),
                    'total_leakage':  float(r.total_leakage  or 0),
                    'total_discount': float(r.total_discount or 0),
                    'total_upsell':   float(r.total_upsell   or 0),
                    'net_score':      float(r.net_score      or 0),
                    'rank':           r.rank,
                    'flag':           r.flag,
                })
            return result
        except Exception as exc:
            log.error('get_today_performance failed: %s', exc)
            return []
