"""
AI Revenue Forecasting & Demand Calendar
=========================================
Statistical forecasting engine for hotel revenue and demand analysis.
Uses on-the-books data, historical patterns, and booking curves --
no ML libraries required.

Classes:
    RevenueForecastEngine  -- daily/monthly revenue projections
    DemandCalendar         -- demand heat-map and spike detection
"""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy import func

from app.models import db, Reservation, NightAuditLog
from app.kpi_helpers import get_sellable_room_count
from app.services import get_business_date


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

_ACTIVE_STATUSES = ('Reserved', 'Confirmed', 'CheckedIn')
_HISTORICAL_STATUSES = ('CheckedIn', 'CheckedOut')


def _date_range(start: date, end: date):
    """Yield dates from start up to but not including end."""
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


# =========================================================================
# Revenue Forecast Engine
# =========================================================================

class RevenueForecastEngine:
    """Forecast daily room revenue using OTB + historical fill."""

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def forecast_revenue(self, days_ahead: int = 90) -> List[Dict[str, Any]]:
        """Forecast daily revenue for the next *days_ahead* days.

        Methodology
        -----------
        1. **OTB (On-the-Books):** count rooms and sum ``rate_per_night`` for
           every future reservation with status Reserved/Confirmed/CheckedIn.
        2. **Historical fill:** for dates where OTB is below expected final
           occupancy, project additional rooms using the booking curve and
           historical day-of-week / seasonal averages.
        3. **Combine** OTB revenue + projected additional revenue.

        Returns a list of dicts (one per day) sorted by date.
        """
        today = get_business_date()
        sellable = get_sellable_room_count() or 1
        end_date = today + timedelta(days=days_ahead)

        # -- Step 1: OTB rooms & revenue per date --------------------------
        otb = self._get_otb_by_date(today, end_date)

        # -- Step 2: historical baselines -----------------------------------
        hist_occ = self._build_historical_occ_map(today)
        avg_rate = self._get_average_rate() or 0.0

        # -- Step 3: build daily forecast -----------------------------------
        results: List[Dict[str, Any]] = []
        for d in _date_range(today, end_date):
            lead = (d - today).days
            otb_rooms = otb.get(d, {}).get('rooms', 0)
            otb_revenue = otb.get(d, {}).get('revenue', 0.0)

            # Expected occupancy from history
            hist_pct = self.get_historical_occupancy(d, hist_map=hist_occ)
            expected_rooms = max(otb_rooms, round(sellable * hist_pct / 100))

            # Booking-curve adjustment
            curve_pct = self.get_booking_curve(lead)
            if curve_pct > 0:
                projected_final_rooms = min(
                    sellable,
                    max(expected_rooms, round(otb_rooms / (curve_pct / 100)))
                )
            else:
                projected_final_rooms = expected_rooms

            additional_rooms = max(0, projected_final_rooms - otb_rooms)
            projected_revenue = round(additional_rooms * avg_rate, 2)
            total_revenue = round(otb_revenue + projected_revenue, 2)
            occ_pct = round(projected_final_rooms / sellable * 100, 1)

            # Confidence degrades with lead time
            confidence = self._confidence(lead, otb_rooms, sellable)

            results.append({
                'date': d.isoformat(),
                'otb_rooms': otb_rooms,
                'otb_revenue': round(otb_revenue, 2),
                'projected_rooms': projected_final_rooms,
                'projected_revenue': round(projected_revenue, 2),
                'total_projected_revenue': total_revenue,
                'occupancy_pct': occ_pct,
                'confidence': confidence,
            })
        return results

    def get_booking_curve(self, days_out: int) -> float:
        """Return the % of final occupancy typically booked at *days_out*.

        Analyses completed stays: for each past arrival date, what fraction
        of the final room-count was already booked N days before arrival.
        Falls back to a logistic model when data is thin.
        """
        if days_out <= 0:
            return 100.0

        today = get_business_date()
        lookback_start = today - timedelta(days=180)

        # Historical booking-lead distribution
        rows = (
            db.session.query(
                Reservation.arrival_date,
                Reservation.created_at,
            )
            .filter(
                Reservation.status.in_(_HISTORICAL_STATUSES),
                Reservation.arrival_date >= lookback_start,
                Reservation.arrival_date < today,
                Reservation.created_at.isnot(None),
            )
            .all()
        )

        if len(rows) < 30:
            # Fallback logistic curve: 50% at 21 days, 90% at 3 days
            return round(100 / (1 + math.exp(0.15 * (days_out - 14))), 1)

        # Group by arrival date: count total & count booked >= N days before
        by_arrival: Dict[date, Dict[str, int]] = defaultdict(lambda: {'total': 0, 'early': 0})
        for arr, created in rows:
            if created is None:
                continue
            created_date = created.date() if hasattr(created, 'date') else created
            lead = (arr - created_date).days
            by_arrival[arr]['total'] += 1
            if lead >= days_out:
                by_arrival[arr]['early'] += 1

        totals = sum(v['total'] for v in by_arrival.values())
        early = sum(v['early'] for v in by_arrival.values())
        if totals == 0:
            return 100.0
        return round(early / totals * 100, 1)

    def get_historical_occupancy(
        self,
        target_date: date,
        lookback_days: int = 365,
        hist_map: Optional[Dict] = None,
    ) -> float:
        """Average occupancy % for same weekday in same month from history.

        If *hist_map* is provided (pre-built), use it directly for speed.
        """
        key = (target_date.month, target_date.weekday())
        if hist_map is not None:
            return hist_map.get(key, 50.0)

        today = get_business_date()
        start = today - timedelta(days=lookback_days)
        sellable = get_sellable_room_count() or 1

        rows = (
            db.session.query(
                NightAuditLog.audit_date,
                NightAuditLog.occupancy_count,
            )
            .filter(
                NightAuditLog.audit_date >= start,
                NightAuditLog.audit_date < today,
                NightAuditLog.status.in_(['Completed', 'Warning', 'Pending']),
            )
            .all()
        )

        vals = [
            r.occupancy_count / sellable * 100
            for r in rows
            if r.audit_date.month == target_date.month
            and r.audit_date.weekday() == target_date.weekday()
            and r.occupancy_count is not None
        ]
        if not vals:
            return 50.0  # neutral default
        return round(sum(vals) / len(vals), 1)

    def get_monthly_summary(self, months_ahead: int = 3) -> List[Dict[str, Any]]:
        """Aggregate forecast into monthly buckets."""
        today = get_business_date()
        daily = self.forecast_revenue(days_ahead=months_ahead * 31 + 31)

        buckets: Dict[str, Dict[str, Any]] = {}
        for row in daily:
            d = date.fromisoformat(row['date'])
            key = d.strftime('%Y-%m')
            if key not in buckets:
                days_in_month = calendar.monthrange(d.year, d.month)[1]
                buckets[key] = {
                    'month': key,
                    'month_name': d.strftime('%B %Y'),
                    'days_in_month': days_in_month,
                    'otb_revenue': 0.0,
                    'projected_revenue': 0.0,
                    'total_revenue': 0.0,
                    'avg_occupancy': 0.0,
                    'avg_confidence': 0.0,
                    '_count': 0,
                }
            b = buckets[key]
            b['otb_revenue'] = round(b['otb_revenue'] + row['otb_revenue'], 2)
            b['projected_revenue'] = round(b['projected_revenue'] + row['projected_revenue'], 2)
            b['total_revenue'] = round(b['total_revenue'] + row['total_projected_revenue'], 2)
            b['avg_occupancy'] += row['occupancy_pct']
            b['avg_confidence'] += row['confidence']
            b['_count'] += 1

        result = []
        for key in sorted(buckets):
            b = buckets[key]
            n = b.pop('_count') or 1
            b['avg_occupancy'] = round(b['avg_occupancy'] / n, 1)
            b['avg_confidence'] = round(b['avg_confidence'] / n, 1)
            result.append(b)
        return result

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _get_otb_by_date(self, start: date, end: date) -> Dict[date, Dict]:
        """OTB rooms + revenue keyed by date for the given window."""
        reservations = (
            Reservation.query
            .filter(
                Reservation.status.in_(_ACTIVE_STATUSES),
                Reservation.arrival_date < end,
                Reservation.departure_date > start,
            )
            .all()
        )
        otb: Dict[date, Dict] = {}
        for res in reservations:
            rate = float(res.rate_per_night or 0)
            arr = max(res.arrival_date, start)
            dep = min(res.departure_date, end)
            for d in _date_range(arr, dep):
                if d not in otb:
                    otb[d] = {'rooms': 0, 'revenue': 0.0}
                otb[d]['rooms'] += 1
                otb[d]['revenue'] += rate
        return otb

    def _build_historical_occ_map(self, today: date) -> Dict:
        """Pre-build (month, weekday) -> avg occ% from NightAuditLog."""
        sellable = get_sellable_room_count() or 1
        start = today - timedelta(days=365)

        rows = (
            db.session.query(
                NightAuditLog.audit_date,
                NightAuditLog.occupancy_count,
            )
            .filter(
                NightAuditLog.audit_date >= start,
                NightAuditLog.audit_date < today,
                NightAuditLog.status.in_(['Completed', 'Warning', 'Pending']),
            )
            .all()
        )

        groups: Dict[tuple, list] = defaultdict(list)
        for r in rows:
            if r.occupancy_count is not None:
                key = (r.audit_date.month, r.audit_date.weekday())
                groups[key].append(r.occupancy_count / sellable * 100)

        return {k: round(sum(v) / len(v), 1) for k, v in groups.items()}

    def _get_average_rate(self) -> float:
        """Average rate_per_night across recent reservations (90 days)."""
        today = get_business_date()
        start = today - timedelta(days=90)
        avg = (
            db.session.query(func.avg(Reservation.rate_per_night))
            .filter(
                Reservation.status.in_(_HISTORICAL_STATUSES + _ACTIVE_STATUSES),
                Reservation.arrival_date >= start,
            )
            .scalar()
        )
        return round(float(avg), 2) if avg else 0.0

    @staticmethod
    def _confidence(lead: int, otb_rooms: int, sellable: int) -> float:
        """Confidence score 0-100. High when lead is short or OTB is high."""
        # OTB component: more rooms booked -> higher confidence
        otb_factor = min(otb_rooms / sellable, 1.0) if sellable else 0
        # Lead component: closer dates -> higher confidence
        lead_factor = max(0, 1 - lead / 120)
        raw = (otb_factor * 60 + lead_factor * 40)
        return round(min(100, max(5, raw)), 1)


# =========================================================================
# Demand Calendar
# =========================================================================

class DemandCalendar:
    """Demand heat-map and anomaly detection for date ranges."""

    DEMAND_LEVELS = {
        'low':      {'min': 0,  'max': 40, 'color': '#22c55e', 'bg': '#dcfce7'},
        'moderate': {'min': 40, 'max': 65, 'color': '#eab308', 'bg': '#fef9c3'},
        'high':     {'min': 65, 'max': 85, 'color': '#f97316', 'bg': '#ffedd5'},
        'peak':     {'min': 85, 'max': 101, 'color': '#ef4444', 'bg': '#fee2e2'},
    }

    def get_calendar_data(
        self, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """Return demand heat-map data for each date in the range.

        Each entry contains:
          date, weekday, otb_rooms, projected_occ, demand_level, color, bg_color, events
        """
        engine = RevenueForecastEngine()
        today = get_business_date()
        sellable = get_sellable_room_count() or 1

        days_ahead = max((end_date - today).days + 1, 1)
        forecast = engine.forecast_revenue(days_ahead=days_ahead)
        forecast_map = {row['date']: row for row in forecast}

        results: List[Dict[str, Any]] = []
        for d in _date_range(start_date, end_date + timedelta(days=1)):
            iso = d.isoformat()
            row = forecast_map.get(iso)
            if row:
                occ_pct = row['occupancy_pct']
                otb_rooms = row['otb_rooms']
            else:
                # Date is in the past -- use NightAuditLog
                audit = NightAuditLog.query.filter_by(audit_date=d).first()
                if audit and audit.occupancy_count is not None:
                    occ_pct = round(audit.occupancy_count / sellable * 100, 1)
                    otb_rooms = audit.occupancy_count
                else:
                    occ_pct = 0.0
                    otb_rooms = 0

            level, color, bg_color = self._classify(occ_pct)

            results.append({
                'date': iso,
                'weekday': d.strftime('%A'),
                'weekday_short': d.strftime('%a'),
                'day': d.day,
                'otb_rooms': otb_rooms,
                'projected_occ': occ_pct,
                'demand_level': level,
                'color': color,
                'bg_color': bg_color,
                'events': [],  # placeholder for event integration
            })
        return results

    def detect_demand_spikes(
        self, days_ahead: int = 90
    ) -> List[Dict[str, Any]]:
        """Find dates with projected demand significantly above or below
        the historical average.  Consecutive high-demand days are grouped
        as potential event windows.
        """
        engine = RevenueForecastEngine()
        today = get_business_date()
        forecast = engine.forecast_revenue(days_ahead=days_ahead)

        hist_map = engine._build_historical_occ_map(today)

        spikes: List[Dict[str, Any]] = []
        for row in forecast:
            d = date.fromisoformat(row['date'])
            hist_avg = engine.get_historical_occupancy(d, hist_map=hist_map)
            projected = row['occupancy_pct']
            deviation = projected - hist_avg

            if abs(deviation) >= 15:
                spike_type = 'high' if deviation > 0 else 'low'
                spikes.append({
                    'date': row['date'],
                    'weekday': d.strftime('%A'),
                    'projected_occ': projected,
                    'historical_avg': hist_avg,
                    'deviation': round(deviation, 1),
                    'spike_type': spike_type,
                })

        # Group consecutive high spikes as potential events
        events = self._group_consecutive_spikes(spikes)
        return {
            'spikes': spikes,
            'potential_events': events,
        }

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _classify(self, occ_pct: float):
        """Return (level_name, color, bg_color) for an occupancy %."""
        for level, info in self.DEMAND_LEVELS.items():
            if info['min'] <= occ_pct < info['max']:
                return level, info['color'], info['bg']
        return 'peak', '#ef4444', '#fee2e2'

    @staticmethod
    def _group_consecutive_spikes(spikes: list) -> list:
        """Group consecutive high-demand spike dates into event windows."""
        high_dates = sorted(
            [s['date'] for s in spikes if s['spike_type'] == 'high']
        )
        if not high_dates:
            return []

        events = []
        group_start = high_dates[0]
        prev = date.fromisoformat(high_dates[0])

        for iso in high_dates[1:]:
            d = date.fromisoformat(iso)
            if (d - prev).days <= 2:  # allow 1 gap day
                prev = d
            else:
                if prev >= date.fromisoformat(group_start):
                    events.append({
                        'start': group_start,
                        'end': prev.isoformat(),
                        'days': (prev - date.fromisoformat(group_start)).days + 1,
                        'label': 'Potential high-demand event',
                    })
                group_start = iso
                prev = d

        # Close last group
        events.append({
            'start': group_start,
            'end': prev.isoformat(),
            'days': (prev - date.fromisoformat(group_start)).days + 1,
            'label': 'Potential high-demand event',
        })
        return events
