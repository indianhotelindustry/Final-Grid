"""
AI-Powered Upsell Engine — recommends room upgrades at check-in.

Factors considered:
1. Availability: only recommend room types with available rooms
2. Price delta: calculate optimal upsell price (not full rack rate)
3. Guest profile: VIP level, repeat guest, corporate vs leisure
4. Occupancy: higher occupancy = less discount on upgrades
5. Revenue opportunity: prioritize upgrades with highest incremental revenue

No external dependencies — pure Python heuristics.
"""

import logging
from datetime import date
from decimal import Decimal

logger = logging.getLogger(__name__)


class UpsellEngine:
    """Generate upsell recommendations for a reservation at check-in time."""

    # Upsell discount tiers based on occupancy
    # Higher occupancy = less discount needed (rooms sell themselves)
    OCCUPANCY_DISCOUNT_MAP = [
        (90, 0.0),    # >90% occ: no discount, full upgrade price
        (75, 0.10),   # 75-90%: 10% off upgrade delta
        (60, 0.20),   # 60-75%: 20% off
        (40, 0.35),   # 40-60%: 35% off
        (0,  0.50),   # <40%: 50% off (stimulate upgrades)
    ]

    # Guest-type multipliers (discount on the upsell price)
    GUEST_MULTIPLIERS = {
        'V5': 0.0,    # Top VIP: complimentary upgrade
        'V4': 0.20,   # High VIP: 80% of upsell price
        'V3': 0.15,   # VIP: 85%
        'V2': 0.10,   # VIP: 90%
        'V1': 0.05,   # VIP: 95%
        'repeat': 0.10,  # Repeat guest: 10% off
    }

    def get_recommendations(self, reservation):
        """
        Generate upsell recommendations for a reservation.

        Returns: list of {
            room_type_id, room_type_name, current_rate, rack_rate,
            upsell_price, savings_pct, revenue_delta,
            available_rooms, confidence, reason
        }
        """
        from app.models import db, Room, RoomType, Reservation

        if not reservation or reservation.status not in ('Reserved', 'Confirmed', 'CheckedIn'):
            return []

        current_rate = float(reservation.rate_per_night or 0)
        current_type_id = reservation.room_type_id
        arrival = reservation.arrival_date
        departure = reservation.departure_date
        nights = (departure - arrival).days
        if nights <= 0:
            return []

        # Projected occupancy across the stay window. The denominator is the
        # canonical sellable-room count (occupancy_engine) — not a hand-rolled
        # is_active/is_sellable count that misses OOO/maintenance rooms.
        # booked_rooms remains a forward-looking count of overlapping
        # Confirmed/CheckedIn reservations: the engine models only current
        # occupancy, not future projections, so only its denominator applies.
        from app.occupancy_engine import sellable_rooms as _engine_sellable_rooms
        total_rooms = _engine_sellable_rooms()
        booked_rooms = Reservation.query.filter(
            Reservation.status.in_(['Confirmed', 'CheckedIn']),
            Reservation.arrival_date < departure,
            Reservation.departure_date > arrival,
        ).count()
        occupancy_pct = (booked_rooms / total_rooms * 100) if total_rooms else 0

        # Get guest profile signals
        guest = reservation.guest
        vip_level = getattr(guest, 'vip_level', None) if guest else None
        is_repeat = (getattr(guest, 'total_stays', 0) or 0) > 1

        # Get all higher room types
        current_type = RoomType.query.get(current_type_id)
        if not current_type:
            return []

        higher_types = (
            RoomType.query
            .filter(
                RoomType.id != current_type_id,
                RoomType.base_rate > current_type.base_rate,
                RoomType.is_active == True,
            )
            .order_by(RoomType.base_rate.asc())
            .all()
        )

        recommendations = []
        for rt in higher_types:
            # Check availability
            rt_booked = Reservation.query.filter(
                Reservation.room_type_id == rt.id,
                Reservation.status.in_(['Confirmed', 'CheckedIn']),
                Reservation.arrival_date < departure,
                Reservation.departure_date > arrival,
            ).count()
            rt_total = Room.query.filter_by(room_type_id=rt.id, is_active=True, is_sellable=True).count()
            available = rt_total - rt_booked

            if available <= 0:
                continue

            rack_rate = float(rt.base_rate)
            rate_delta = rack_rate - current_rate

            if rate_delta <= 0:
                continue

            # Calculate upsell price with discounts
            occupancy_discount = self._get_occupancy_discount(occupancy_pct)
            guest_discount = self._get_guest_discount(vip_level, is_repeat)

            # Upsell price = rate delta * (1 - occupancy_discount) * (1 - guest_discount)
            upsell_price = rate_delta * (1 - occupancy_discount) * (1 - guest_discount)
            upsell_price = round(max(upsell_price, 0), 2)

            # Revenue delta per night
            revenue_delta = upsell_price * nights

            # Confidence based on availability and value
            confidence = min(95, 50 + available * 5 + (10 if is_repeat else 0))

            # Reason string
            reasons = []
            if vip_level:
                reasons.append(f'{vip_level} guest')
            if is_repeat:
                reasons.append('repeat guest')
            if occupancy_pct < 50:
                reasons.append('low occupancy')
            if available > 3:
                reasons.append(f'{available} rooms available')

            savings_pct = round((1 - upsell_price / rate_delta) * 100) if rate_delta > 0 else 0

            recommendations.append({
                'room_type_id': rt.id,
                'room_type_name': rt.name,
                'current_rate': current_rate,
                'rack_rate': rack_rate,
                'rate_delta': rate_delta,
                'upsell_price': upsell_price,
                'savings_pct': savings_pct,
                'total_upgrade_cost': round(upsell_price * nights, 2),
                'revenue_delta': round(revenue_delta, 2),
                'available_rooms': available,
                'nights': nights,
                'confidence': confidence,
                'reason': ', '.join(reasons) if reasons else 'standard upgrade',
            })

        # Sort by revenue delta (best value for the hotel)
        recommendations.sort(key=lambda x: x['revenue_delta'], reverse=True)
        return recommendations[:3]  # Top 3 recommendations

    def _get_occupancy_discount(self, occupancy_pct):
        for threshold, discount in self.OCCUPANCY_DISCOUNT_MAP:
            if occupancy_pct >= threshold:
                return discount
        return 0.50

    def _get_guest_discount(self, vip_level, is_repeat):
        if vip_level and vip_level in self.GUEST_MULTIPLIERS:
            return self.GUEST_MULTIPLIERS[vip_level]
        if is_repeat:
            return self.GUEST_MULTIPLIERS['repeat']
        return 0.0


# Singleton
_engine = None


def get_upsell_engine():
    global _engine
    if _engine is None:
        _engine = UpsellEngine()
    return _engine


def get_upsell_recommendations(reservation):
    """Convenience function for use in templates and routes."""
    return get_upsell_engine().get_recommendations(reservation)
