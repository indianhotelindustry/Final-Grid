"""
Smart Guest Profile — learns preferences from stay history.

Analyzes past reservations to build a preference profile:
- Preferred room type and floor
- Average spend per night
- Booking patterns (advance days, length of stay)
- Payment preferences
- Special request patterns
- Visit frequency and loyalty tier suggestion

Displayed at check-in for personalized service.
"""

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class GuestProfileEngine:
    """Build smart profiles from guest stay history."""

    LOYALTY_TIERS = [
        (20, 'Platinum', 'V5'),
        (10, 'Gold', 'V4'),
        (5,  'Silver', 'V3'),
        (3,  'Bronze', 'V2'),
        (1,  'Member', 'V1'),
    ]

    def get_profile(self, guest_id):
        """
        Build a comprehensive guest profile from stay history.

        Returns: {
            guest: {name, phone, email, vip_level, total_stays},
            preferences: {room_type, floor, avg_rate, avg_los, booking_lead_days},
            spending: {total_spent, avg_per_night, avg_per_stay},
            patterns: {preferred_dow, preferred_source, avg_advance_days},
            loyalty: {tier_name, suggested_vip, stays_to_next_tier, total_revenue},
            special_requests: [list of past requests],
            last_visit: {date, room, duration, feedback_score},
            personalization_tips: [actionable tips for front desk]
        }
        """
        from app.models import db, Guest, Reservation, Payment, GuestFeedback, ExtraCharge

        guest = db.session.get(Guest, guest_id)
        if not guest:
            return None

        # Get all reservations for this guest
        reservations = (
            Reservation.query
            .filter_by(guest_id=guest_id)
            .filter(Reservation.status.in_(['CheckedOut', 'CheckedIn']))
            .order_by(Reservation.arrival_date.desc())
            .all()
        )

        if not reservations:
            return {
                'guest': self._guest_dict(guest),
                'preferences': {},
                'spending': {},
                'patterns': {},
                'loyalty': self._calc_loyalty(0, 0),
                'special_requests': [],
                'last_visit': None,
                'personalization_tips': ['New guest — no history available.'],
            }

        # Analyze preferences
        room_types = Counter()
        floors = Counter()
        rates = []
        los_list = []
        lead_days = []
        sources = Counter()
        dow_arrivals = Counter()
        special_reqs = []
        total_spent = 0

        for res in reservations:
            # Room type preference
            if res.room_type:
                room_types[res.room_type.name] += 1
            # Floor preference
            if res.room and res.room.floor:
                floors[res.room.floor] += 1
            # Rate
            if res.rate_per_night:
                rates.append(float(res.rate_per_night))
            # Length of stay
            nights = (res.departure_date - res.arrival_date).days
            if nights > 0:
                los_list.append(nights)
            # Booking lead time
            if res.created_at and res.arrival_date:
                lead = (res.arrival_date - res.created_at.date()).days
                if lead >= 0:
                    lead_days.append(lead)
            # Source
            if res.source:
                sources[res.source] += 1
            # Day of week
            dow_arrivals[res.arrival_date.strftime('%A')] += 1
            # Special requests
            if res.special_requests:
                special_reqs.append(res.special_requests)
            # Spending
            for p in res.payments:
                if not p.is_voided:
                    total_spent += float(p.amount or 0)

        # Build preferences
        preferences = {}
        if room_types:
            preferences['room_type'] = room_types.most_common(1)[0][0]
        if floors:
            preferences['floor'] = floors.most_common(1)[0][0]
        if rates:
            preferences['avg_rate'] = round(sum(rates) / len(rates), 2)
        if los_list:
            preferences['avg_los'] = round(sum(los_list) / len(los_list), 1)
        if lead_days:
            preferences['avg_lead_days'] = round(sum(lead_days) / len(lead_days), 0)

        # Spending
        avg_per_stay = total_spent / len(reservations) if reservations else 0
        total_nights = sum(los_list) if los_list else 1
        avg_per_night = total_spent / total_nights if total_nights else 0

        spending = {
            'total_spent': round(total_spent, 2),
            'avg_per_night': round(avg_per_night, 2),
            'avg_per_stay': round(avg_per_stay, 2),
            'total_nights': total_nights,
        }

        # Patterns
        patterns = {
            'preferred_dow': dow_arrivals.most_common(1)[0][0] if dow_arrivals else None,
            'preferred_source': sources.most_common(1)[0][0] if sources else None,
            'total_stays': len(reservations),
        }

        # Last visit
        last_res = reservations[0]
        last_feedback = GuestFeedback.query.filter_by(reservation_id=last_res.id).first()
        last_visit = {
            'date': last_res.departure_date.isoformat() if last_res.departure_date else None,
            'room': last_res.room.room_number if last_res.room else None,
            'room_type': last_res.room_type.name if last_res.room_type else None,
            'duration': (last_res.departure_date - last_res.arrival_date).days,
            'feedback_score': last_feedback.rating if last_feedback else None,
        }

        # Loyalty
        loyalty = self._calc_loyalty(len(reservations), total_spent)

        # Personalization tips
        tips = self._generate_tips(guest, preferences, spending, patterns, last_visit, special_reqs)

        return {
            'guest': self._guest_dict(guest),
            'preferences': preferences,
            'spending': spending,
            'patterns': patterns,
            'loyalty': loyalty,
            'special_requests': special_reqs[-5:],  # last 5
            'last_visit': last_visit,
            'personalization_tips': tips,
        }

    def _guest_dict(self, guest):
        return {
            'id': guest.id,
            'name': guest.name,
            'phone': guest.phone,
            'email': guest.email,
            'vip_level': getattr(guest, 'vip_level', None),
            'total_stays': getattr(guest, 'total_stays', 0) or 0,
        }

    def _calc_loyalty(self, stay_count, total_revenue):
        tier_name = 'New Guest'
        suggested_vip = None
        stays_to_next = 1

        for threshold, name, vip in self.LOYALTY_TIERS:
            if stay_count >= threshold:
                tier_name = name
                suggested_vip = vip
                break

        # Find next tier
        for threshold, name, vip in reversed(self.LOYALTY_TIERS):
            if stay_count < threshold:
                stays_to_next = threshold - stay_count
                break

        return {
            'tier_name': tier_name,
            'suggested_vip': suggested_vip,
            'stays_to_next_tier': max(stays_to_next, 0),
            'total_revenue': round(total_revenue, 2),
        }

    def _generate_tips(self, guest, prefs, spending, patterns, last_visit, requests):
        tips = []

        # Room preference
        if prefs.get('room_type'):
            tips.append(f"Prefers {prefs['room_type']} rooms — try to assign this type.")
        if prefs.get('floor'):
            tips.append(f"Usually stays on floor {prefs['floor']}.")

        # High spender
        if spending.get('avg_per_night', 0) > 3000:
            tips.append("High-value guest — consider complimentary amenity.")

        # Repeat guest
        if patterns.get('total_stays', 0) >= 5:
            tips.append(f"Loyal guest ({patterns['total_stays']} stays) — acknowledge their loyalty.")
        elif patterns.get('total_stays', 0) >= 2:
            tips.append("Returning guest — welcome them back by name.")

        # Last feedback
        if last_visit and last_visit.get('feedback_score'):
            score = last_visit['feedback_score']
            if score <= 2:
                tips.append("ALERT: Last stay had a poor rating. Ask if previous issues were addressed.")
            elif score >= 5:
                tips.append("Last visit rated excellent — maintain the standard.")

        # Special requests
        if requests:
            last_req = requests[-1]
            if len(last_req) < 100:
                tips.append(f"Previous request: \"{last_req}\"")

        if not tips:
            tips.append("No specific preferences on file yet.")

        return tips


# Singleton
_engine = None


def get_guest_profile_engine():
    global _engine
    if _engine is None:
        _engine = GuestProfileEngine()
    return _engine


def get_smart_profile(guest_id):
    """Convenience function."""
    return get_guest_profile_engine().get_profile(guest_id)
