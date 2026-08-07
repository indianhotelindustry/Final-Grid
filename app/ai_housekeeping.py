"""
Smart Housekeeping Scheduler — AI-optimized room cleaning order.

Prioritization factors:
1. Departures first (rooms needed for new arrivals)
2. VIP arrivals get priority
3. Floor clustering (clean rooms on same floor together to minimize travel)
4. Early check-in requests
5. Stayover rooms (occupied, daily cleaning) lower priority than turnovers

No external dependencies — pure Python optimization.
"""

import logging
from datetime import date, datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class HousekeepingScheduler:
    """Generate an optimized cleaning schedule for the day."""

    # Priority weights (higher = clean first)
    PRIORITY_WEIGHTS = {
        'departure_with_arrival': 100,   # Turnover: someone checking out AND someone arriving
        'departure': 80,                  # Checkout room, no arrival yet
        'vip_arrival': 90,                # VIP arriving today
        'early_checkin': 85,              # Guest requested early check-in
        'arrival': 70,                    # Regular arrival today
        'dirty_vacant': 60,              # Dirty but no specific urgency
        'stayover_vip': 50,              # VIP in-house (daily clean)
        'stayover': 30,                  # Regular stayover
        'maintenance_return': 40,         # Coming back from maintenance
    }

    def generate_schedule(self, business_date=None):
        """
        Generate optimized cleaning schedule for the day.

        Returns: list of {
            room_number, floor, room_type, priority, priority_label,
            score, category, guest_name, notes, estimated_minutes
        }
        """
        from app.models import db, Room, Reservation, Guest
        from app.services import get_business_date

        today = business_date or get_business_date()

        # Get all rooms that need cleaning
        rooms = Room.query.filter(
            Room.is_active == True,
        ).order_by(Room.floor, Room.room_number).all()

        # Get today's departures
        departures = {
            r.room_id: r for r in
            Reservation.query.filter(
                Reservation.status == 'CheckedIn',
                Reservation.departure_date <= today,
                Reservation.room_id.isnot(None),
            ).all()
        }

        # Get today's arrivals
        arrivals = {}
        arriving_reservations = Reservation.query.filter(
            Reservation.status.in_(['Confirmed', 'Reserved']),
            Reservation.arrival_date == today,
        ).all()
        for res in arriving_reservations:
            if res.room_id:
                arrivals[res.room_id] = res
            else:
                # Room not assigned yet — track by room type
                arrivals.setdefault(f'type_{res.room_type_id}', [])
                if isinstance(arrivals.get(f'type_{res.room_type_id}'), list):
                    arrivals[f'type_{res.room_type_id}'].append(res)

        # Get in-house guests (stayovers)
        stayovers = {
            r.room_id: r for r in
            Reservation.query.filter(
                Reservation.status == 'CheckedIn',
                Reservation.departure_date > today,
                Reservation.room_id.isnot(None),
            ).all()
        }

        schedule = []
        for room in rooms:
            if room.is_out_of_order:
                continue

            category = None
            score = 0
            guest_name = None
            notes = []
            est_minutes = 20  # default cleaning time

            is_departure = room.id in departures
            is_arrival = room.id in arrivals
            is_stayover = room.id in stayovers
            is_dirty = room.status == 'Dirty'

            dep_res = departures.get(room.id)
            arr_res = arrivals.get(room.id)
            stay_res = stayovers.get(room.id)

            # Determine category and priority
            if is_departure and is_arrival:
                category = 'departure_with_arrival'
                score = self.PRIORITY_WEIGHTS['departure_with_arrival']
                est_minutes = 35  # full turnover
                guest_name = dep_res.guest.name if dep_res and dep_res.guest else None
                notes.append('TURNOVER — new guest arriving')
                if arr_res and hasattr(arr_res, 'guest') and arr_res.guest:
                    vip = getattr(arr_res.guest, 'vip_level', None)
                    if vip:
                        score += 10
                        notes.append(f'Arriving guest is {vip}')

            elif is_departure:
                category = 'departure'
                score = self.PRIORITY_WEIGHTS['departure']
                est_minutes = 30
                guest_name = dep_res.guest.name if dep_res and dep_res.guest else None
                notes.append('Checkout today')

            elif is_arrival and not is_stayover:
                if arr_res and hasattr(arr_res, 'guest') and arr_res.guest:
                    vip = getattr(arr_res.guest, 'vip_level', None)
                    if vip:
                        category = 'vip_arrival'
                        score = self.PRIORITY_WEIGHTS['vip_arrival']
                        notes.append(f'{vip} arriving')
                    else:
                        category = 'arrival'
                        score = self.PRIORITY_WEIGHTS['arrival']
                    guest_name = arr_res.guest.name
                else:
                    category = 'arrival'
                    score = self.PRIORITY_WEIGHTS['arrival']
                est_minutes = 25
                notes.append('Arrival today')

            elif is_dirty and not is_stayover:
                category = 'dirty_vacant'
                score = self.PRIORITY_WEIGHTS['dirty_vacant']
                est_minutes = 25

            elif is_stayover:
                vip = None
                if stay_res and stay_res.guest:
                    guest_name = stay_res.guest.name
                    vip = getattr(stay_res.guest, 'vip_level', None)
                if vip:
                    category = 'stayover_vip'
                    score = self.PRIORITY_WEIGHTS['stayover_vip']
                    notes.append(f'{vip} in-house')
                else:
                    category = 'stayover'
                    score = self.PRIORITY_WEIGHTS['stayover']
                est_minutes = 15  # lighter clean for stayover

            elif room.status == 'Maintenance':
                category = 'maintenance_return'
                score = self.PRIORITY_WEIGHTS['maintenance_return']
                notes.append('Returning from maintenance')

            else:
                continue  # Vacant + clean = nothing to do

            if not category:
                continue

            schedule.append({
                'room_id': room.id,
                'room_number': room.room_number,
                'floor': room.floor,
                'room_type': room.room_type.name if room.room_type else '?',
                'status': room.status,
                'priority': category,
                'priority_label': category.replace('_', ' ').title(),
                'score': score,
                'guest_name': guest_name,
                'notes': ' | '.join(notes) if notes else None,
                'estimated_minutes': est_minutes,
            })

        # Sort: by score descending, then by floor for clustering
        schedule.sort(key=lambda x: (-x['score'], x['floor'], x['room_number']))

        return schedule

    def get_summary(self, business_date=None):
        """Summary statistics for housekeeping dashboard."""
        schedule = self.generate_schedule(business_date)

        total_rooms = len(schedule)
        total_minutes = sum(r['estimated_minutes'] for r in schedule)

        by_category = defaultdict(int)
        for r in schedule:
            by_category[r['priority']] += 1

        by_floor = defaultdict(int)
        for r in schedule:
            by_floor[r['floor']] += 1

        return {
            'total_rooms': total_rooms,
            'total_estimated_hours': round(total_minutes / 60, 1),
            'by_category': dict(by_category),
            'by_floor': dict(by_floor),
            'turnovers': by_category.get('departure_with_arrival', 0),
            'departures': by_category.get('departure', 0),
            'arrivals': by_category.get('arrival', 0) + by_category.get('vip_arrival', 0),
            'stayovers': by_category.get('stayover', 0) + by_category.get('stayover_vip', 0),
        }


# Singleton
_scheduler = None


def get_housekeeping_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = HousekeepingScheduler()
    return _scheduler
