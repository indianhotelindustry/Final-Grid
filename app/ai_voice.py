"""
Voice-Activated Front Desk — AI command parser for hotel operations.

Parses natural language voice commands into structured actions.
No external API needed — rule-based NLP with fuzzy matching.

Supported commands:
  - Check in / Check out (by room number or guest name)
  - Room status queries
  - Occupancy / revenue / arrivals / departures queries
  - Mark room clean / dirty
  - Show dashboard / reports / specific pages
  - Guest lookup
  - Balance inquiry
  - Today's summary
"""

import re
import logging
from datetime import date, timedelta
from difflib import get_close_matches

logger = logging.getLogger(__name__)


class VoiceCommandParser:
    """Parse natural language into structured hotel commands."""

    # Command patterns: (regex, action_type, param_extractor)
    PATTERNS = [
        # ── Check-in ──
        (r'check\s*in\s+room\s+(\d+)', 'checkin_room', lambda m: {'room': m.group(1)}),
        (r'check\s*in\s+(\d+)', 'checkin_room', lambda m: {'room': m.group(1)}),
        (r'check\s*in\s+(?:guest\s+)?(.+)', 'checkin_guest', lambda m: {'guest_name': m.group(1).strip()}),

        # ── Check-out ──
        (r'check\s*out\s+room\s+(\d+)', 'checkout_room', lambda m: {'room': m.group(1)}),
        (r'check\s*out\s+(\d+)', 'checkout_room', lambda m: {'room': m.group(1)}),
        (r'check\s*out\s+(?:guest\s+)?(.+)', 'checkout_guest', lambda m: {'guest_name': m.group(1).strip()}),

        # ── Room status ──
        (r'(?:what(?:\'s| is)|show|get)\s+(?:the\s+)?(?:status|state)\s+(?:of\s+)?room\s+(\d+)', 'room_status', lambda m: {'room': m.group(1)}),
        (r'(?:is\s+)?room\s+(\d+)\s+(?:available|vacant|free|occupied|dirty|clean)', 'room_status', lambda m: {'room': m.group(1)}),
        (r'mark\s+room\s+(\d+)\s+(?:as\s+)?clean', 'mark_clean', lambda m: {'room': m.group(1)}),
        (r'mark\s+(\d+)\s+clean', 'mark_clean', lambda m: {'room': m.group(1)}),
        (r'mark\s+room\s+(\d+)\s+(?:as\s+)?dirty', 'mark_dirty', lambda m: {'room': m.group(1)}),

        # ── Occupancy ──
        (r'(?:what(?:\'s| is)|show|get)\s+(?:the\s+)?(?:current\s+)?occupancy', 'occupancy', lambda m: {}),
        (r'how\s+(?:many\s+)?rooms?\s+(?:are\s+)?occupied', 'occupancy', lambda m: {}),
        (r'occupancy\s+(?:for\s+)?(?:today|tonight|now)', 'occupancy', lambda m: {}),
        (r'occupancy\s+(?:for\s+)?tomorrow', 'occupancy_tomorrow', lambda m: {}),

        # ── Revenue ──
        (r'(?:what(?:\'s| is)|show|get)\s+(?:the\s+)?(?:today(?:\'s)?|current)\s+revenue', 'revenue_today', lambda m: {}),
        (r'(?:how\s+much|total)\s+revenue\s+(?:today|collected)', 'revenue_today', lambda m: {}),
        (r'(?:today(?:\'s)?)\s+revenue', 'revenue_today', lambda m: {}),

        # ── Arrivals / Departures ──
        (r'(?:how\s+many|show|list|get)\s+(?:the\s+)?arrivals?\s*(?:today)?', 'arrivals', lambda m: {}),
        (r'(?:who(?:\'s| is)|show)\s+(?:arriving|checking in)\s*(?:today)?', 'arrivals', lambda m: {}),
        (r'(?:how\s+many|show|list|get)\s+(?:the\s+)?departures?\s*(?:today)?', 'departures', lambda m: {}),
        (r'(?:who(?:\'s| is)|show)\s+(?:departing|leaving|checking out)\s*(?:today)?', 'departures', lambda m: {}),
        (r'vip\s+arrivals?', 'vip_arrivals', lambda m: {}),
        (r'(?:show|any)\s+vip\s*(?:arrivals?|guests?)?', 'vip_arrivals', lambda m: {}),

        # ── Balance ──
        (r'(?:what(?:\'s| is)|show|get)\s+(?:the\s+)?balance\s+(?:for\s+|of\s+)?room\s+(\d+)', 'balance', lambda m: {'room': m.group(1)}),
        (r'balance\s+(?:for\s+|of\s+)?room\s+(\d+)', 'balance', lambda m: {'room': m.group(1)}),
        (r'balance\s+(\d+)', 'balance', lambda m: {'room': m.group(1)}),

        # ── Guest lookup ──
        (r'(?:find|search|look\s*up|show)\s+guest\s+(.+)', 'guest_search', lambda m: {'query': m.group(1).strip()}),
        (r'(?:who\s+is\s+in|guest\s+in)\s+room\s+(\d+)', 'guest_in_room', lambda m: {'room': m.group(1)}),
        (r'who\s+is\s+in\s+(\d+)', 'guest_in_room', lambda m: {'room': m.group(1)}),

        # ── Navigation ──
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?dashboard', 'navigate', lambda m: {'page': 'dashboard'}),
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?housekeeping', 'navigate', lambda m: {'page': 'housekeeping'}),
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?reservations?', 'navigate', lambda m: {'page': 'reservations'}),
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?reports?', 'navigate', lambda m: {'page': 'reports'}),
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?night\s*audit', 'navigate', lambda m: {'page': 'night_audit'}),
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?groups?', 'navigate', lambda m: {'page': 'groups'}),
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?ai\s*(?:insights?|pricing|forecast)', 'navigate', lambda m: {'page': 'ai'}),

        # ── Predictive Maintenance ──
        (r'(?:show|open|go\s+to)\s+(?:the\s+)?predictive\s+maintenance', 'navigate', lambda m: {'page': 'predictive_maintenance'}),
        (r'(?:show|get|what(?:\'s| are))\s+(?:the\s+)?maintenance\s+predictions?', 'maintenance_predictions', lambda m: {}),
        (r'predict(?:ive)?\s+maintenance', 'maintenance_predictions', lambda m: {}),
        (r'maintenance\s+predictions?', 'maintenance_predictions', lambda m: {}),
        (r'room\s+health\s+(?:for\s+)?(?:room\s+)?(\d+)', 'room_health_detail', lambda m: {'room': m.group(1)}),
        (r'(?:show|get|what(?:\'s| is))?\s*(?:the\s+)?room\s+health', 'room_health', lambda m: {}),
        (r'(?:show|get|what(?:\'s| are))?\s*(?:the\s+)?(?:upcoming\s+)?maintenance\s+schedule', 'maintenance_schedule', lambda m: {}),
        (r'(?:rooms?\s+at\s+risk|at.risk\s+rooms?)', 'rooms_at_risk', lambda m: {}),

        # ── Summary ──
        (r'(?:give\s+me|show|what(?:\'s| is))\s+(?:the\s+)?(?:today(?:\'s)?|daily)\s+summary', 'daily_summary', lambda m: {}),
        (r'flash\s+report', 'daily_summary', lambda m: {}),
        (r'how\s+(?:are\s+)?(?:we\s+)?doing\s+today', 'daily_summary', lambda m: {}),

        # ── Help ──
        (r'(?:what\s+can\s+you\s+do|help|commands?)', 'help', lambda m: {}),
    ]

    def parse(self, text):
        """
        Parse voice command text into a structured action.

        Returns: {
            'action': str,       # action type
            'params': dict,      # extracted parameters
            'confidence': float, # 0.0 - 1.0
            'raw_text': str,     # original input
        }
        """
        if not text:
            return {'action': 'unknown', 'params': {}, 'confidence': 0, 'raw_text': ''}

        cleaned = text.lower().strip()
        # Remove filler words. 'hey sukoon' / 'sukoon' are retained wake-word
        # aliases: staff already speak them, and dropping them would change
        # command parsing. They are not the product name (see README.md).
        cleaned = re.sub(r'\b(please|can you|could you|um|uh|hey sukoon|sukoon|okay)\b', '', cleaned).strip()

        for pattern, action, extractor in self.PATTERNS:
            match = re.search(pattern, cleaned, re.IGNORECASE)
            if match:
                params = extractor(match)
                return {
                    'action': action,
                    'params': params,
                    'confidence': 0.9,
                    'raw_text': text,
                }

        # Fuzzy fallback: try to match key verbs
        if any(w in cleaned for w in ['check in', 'checkin']):
            return {'action': 'checkin_prompt', 'params': {}, 'confidence': 0.5, 'raw_text': text}
        if any(w in cleaned for w in ['check out', 'checkout']):
            return {'action': 'checkout_prompt', 'params': {}, 'confidence': 0.5, 'raw_text': text}

        return {'action': 'unknown', 'params': {}, 'confidence': 0, 'raw_text': text}


class VoiceCommandExecutor:
    """Execute parsed voice commands and return results."""

    NAV_URLS = {
        'dashboard': '/',
        'housekeeping': '/housekeeping',
        'reservations': '/reservations',
        'reports': '/reports/',
        'night_audit': '/night-audit',
        'groups': '/groups/',
        'ai': '/ai/pricing/dashboard',
        'predictive_maintenance': '/ai/predictive-maintenance',
    }

    def execute(self, parsed_command):
        """
        Execute a parsed command and return a response.

        Returns: {
            'speech': str,          # text to speak aloud
            'action_type': str,     # 'navigate' | 'data' | 'execute' | 'error'
            'url': str | None,      # URL to navigate to (if navigate)
            'data': dict | None,    # data payload (if data query)
            'html': str | None,     # optional HTML to show in overlay
        }
        """
        action = parsed_command['action']
        params = parsed_command['params']

        try:
            handler = getattr(self, f'_handle_{action}', None)
            if handler:
                return handler(params)
            return self._handle_unknown(params)
        except Exception as e:
            logger.error('Voice command execution error: %s', e)
            return {
                'speech': 'Sorry, something went wrong processing that command.',
                'action_type': 'error',
                'url': None, 'data': None, 'html': None,
            }

    def _handle_occupancy(self, params):
        from app.models import Room, Reservation
        from app.services import get_business_date
        today = get_business_date()
        total = Room.query.filter_by(is_active=True, is_sellable=True).count()
        occupied = Reservation.query.filter(
            Reservation.status == 'CheckedIn',
            Reservation.room_id.isnot(None),
        ).count()
        pct = round(occupied / total * 100) if total else 0
        return {
            'speech': f'Current occupancy is {pct}%. {occupied} out of {total} rooms occupied.',
            'action_type': 'data',
            'url': None,
            'data': {'occupied': occupied, 'total': total, 'pct': pct},
            'html': None,
        }

    def _handle_occupancy_tomorrow(self, params):
        from app.models import Room, Reservation
        from app.services import get_business_date
        tomorrow = get_business_date() + timedelta(days=1)
        total = Room.query.filter_by(is_active=True, is_sellable=True).count()
        booked = Reservation.query.filter(
            Reservation.status.in_(['Confirmed', 'CheckedIn']),
            Reservation.arrival_date <= tomorrow,
            Reservation.departure_date > tomorrow,
        ).count()
        pct = round(booked / total * 100) if total else 0
        return {
            'speech': f'Tomorrow\'s projected occupancy is {pct}%. {booked} rooms booked out of {total}.',
            'action_type': 'data',
            'url': None,
            'data': {'booked': booked, 'total': total, 'pct': pct},
            'html': None,
        }

    def _handle_revenue_today(self, params):
        from app.models import Payment
        from app.services import get_business_date
        today = get_business_date()
        total = sum(
            float(p.amount or 0)
            for p in Payment.query.filter_by(payment_date=today, is_voided=False).all()
        )
        return {
            'speech': f'Today\'s revenue collected is {total:,.0f} rupees.',
            'action_type': 'data',
            'url': None,
            'data': {'revenue': total, 'date': today.isoformat()},
            'html': None,
        }

    def _handle_arrivals(self, params):
        from app.models import Reservation
        from app.services import get_business_date
        today = get_business_date()
        arrivals = Reservation.query.filter(
            Reservation.arrival_date == today,
            Reservation.status.in_(['Confirmed', 'Reserved']),
        ).all()
        count = len(arrivals)
        names = ', '.join(r.guest.name for r in arrivals[:5] if r.guest) or 'none'
        speech = f'{count} arrival{"s" if count != 1 else ""} today.'
        if count > 0 and count <= 5:
            speech += f' Guests: {names}.'
        elif count > 5:
            speech += f' First five: {names}, and {count - 5} more.'
        return {
            'speech': speech,
            'action_type': 'data',
            'url': '/reports/arrivals',
            'data': {'count': count},
            'html': None,
        }

    def _handle_departures(self, params):
        from app.models import Reservation
        from app.services import get_business_date
        today = get_business_date()
        deps = Reservation.query.filter(
            Reservation.departure_date == today,
            Reservation.status == 'CheckedIn',
        ).all()
        count = len(deps)
        return {
            'speech': f'{count} departure{"s" if count != 1 else ""} today.',
            'action_type': 'data',
            'url': '/reports/departures',
            'data': {'count': count},
            'html': None,
        }

    def _handle_vip_arrivals(self, params):
        from app.models import Reservation, Guest
        from app.services import get_business_date
        today = get_business_date()
        vips = (
            Reservation.query
            .join(Guest)
            .filter(
                Reservation.arrival_date == today,
                Reservation.status.in_(['Confirmed', 'Reserved']),
                Guest.vip_level.isnot(None),
            ).all()
        )
        count = len(vips)
        if count == 0:
            return {'speech': 'No VIP arrivals today.', 'action_type': 'data',
                    'url': None, 'data': {'count': 0}, 'html': None}
        names = ', '.join(f'{r.guest.name} ({r.guest.vip_level})' for r in vips[:5] if r.guest)
        return {
            'speech': f'{count} VIP arrival{"s" if count != 1 else ""} today. {names}.',
            'action_type': 'data',
            'url': '/reports/arrivals',
            'data': {'count': count},
            'html': None,
        }

    def _handle_room_status(self, params):
        from app.models import Room, Reservation
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        guest_name = None
        if room.status == 'Occupied':
            res = Reservation.query.filter_by(room_id=room.id, status='CheckedIn').first()
            if res and res.guest:
                guest_name = res.guest.name
        speech = f'Room {room.room_number} is {room.status}.'
        if guest_name:
            speech += f' Guest: {guest_name}.'
        return {
            'speech': speech, 'action_type': 'data', 'url': None,
            'data': {'room': room.room_number, 'status': room.status, 'guest': guest_name},
            'html': None,
        }

    def _handle_balance(self, params):
        from app.models import Room, Reservation
        from app.services import calculate_stay_amount
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        res = Reservation.query.filter_by(room_id=room.id, status='CheckedIn').first()
        if not res:
            return {'speech': f'No active guest in room {params["room"]}.', 'action_type': 'data',
                    'url': None, 'data': None, 'html': None}
        billing = calculate_stay_amount(res)
        return {
            'speech': f'Room {params["room"]}, guest {res.guest.name}. Total: {billing["total"]:,.0f} rupees. Paid: {billing["paid"]:,.0f}. Balance: {billing["balance"]:,.0f} rupees.',
            'action_type': 'data', 'url': None,
            'data': {'total': billing['total'], 'paid': billing['paid'], 'balance': billing['balance']},
            'html': None,
        }

    def _handle_guest_in_room(self, params):
        from app.models import Room, Reservation
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        res = Reservation.query.filter_by(room_id=room.id, status='CheckedIn').first()
        if not res or not res.guest:
            return {'speech': f'Room {params["room"]} has no active guest.', 'action_type': 'data',
                    'url': None, 'data': None, 'html': None}
        g = res.guest
        return {
            'speech': f'Room {params["room"]} has {g.name}. Phone: {g.phone}. Departing {res.departure_date.strftime("%d %B")}.',
            'action_type': 'data', 'url': None,
            'data': {'guest': g.name, 'phone': g.phone, 'departure': res.departure_date.isoformat()},
            'html': None,
        }

    def _handle_guest_search(self, params):
        from app.models import Guest
        q = params.get('query', '')
        guests = Guest.query.filter(Guest.name.ilike(f'%{q}%')).limit(5).all()
        if not guests:
            guests = Guest.query.filter(Guest.phone.like(f'%{q}%')).limit(5).all()
        if not guests:
            return {'speech': f'No guest found matching {q}.', 'action_type': 'data',
                    'url': None, 'data': {'results': []}, 'html': None}
        names = ', '.join(g.name for g in guests)
        return {
            'speech': f'Found {len(guests)} guest{"s" if len(guests) != 1 else ""}. {names}.',
            'action_type': 'data', 'url': '/guest-database',
            'data': {'results': [{'name': g.name, 'phone': g.phone} for g in guests]},
            'html': None,
        }

    def _handle_mark_clean(self, params):
        from app.models import db, Room
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        if room.status not in ('Dirty', 'Maintenance'):
            return {'speech': f'Room {params["room"]} is {room.status}, not dirty.',
                    'action_type': 'data', 'url': None, 'data': None, 'html': None}
        old = room.status
        room.status = 'Vacant'
        db.session.commit()
        return {
            'speech': f'Room {params["room"]} marked as clean.',
            'action_type': 'execute', 'url': None,
            'data': {'room': params['room'], 'old_status': old, 'new_status': 'Vacant'},
            'html': None,
        }

    def _handle_mark_dirty(self, params):
        from app.models import db, Room
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        if room.status == 'Occupied':
            return {'speech': f'Room {params["room"]} is currently occupied. Cannot mark as dirty.',
                    'action_type': 'error', 'url': None, 'data': None, 'html': None}
        old = room.status
        room.status = 'Dirty'
        db.session.commit()
        return {
            'speech': f'Room {params["room"]} marked as dirty.',
            'action_type': 'execute', 'url': None,
            'data': {'room': params['room'], 'old_status': old, 'new_status': 'Dirty'},
            'html': None,
        }

    def _handle_checkin_room(self, params):
        from app.models import Room, Reservation
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        res = Reservation.query.filter(
            Reservation.room_id == room.id,
            Reservation.status.in_(['Confirmed', 'Reserved']),
        ).first()
        if res:
            return {
                'speech': f'Opening check-in for room {params["room"]}, guest {res.guest.name if res.guest else "unknown"}.',
                'action_type': 'navigate',
                'url': f'/checkin/{res.id}',
                'data': None, 'html': None,
            }
        return {'speech': f'No reservation found for room {params["room"]}.',
                'action_type': 'error', 'url': None, 'data': None, 'html': None}

    def _handle_checkout_room(self, params):
        from app.models import Room, Reservation
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        res = Reservation.query.filter_by(room_id=room.id, status='CheckedIn').first()
        if res:
            return {
                'speech': f'Opening checkout for room {params["room"]}, guest {res.guest.name if res.guest else "unknown"}.',
                'action_type': 'navigate',
                'url': f'/checkout/{res.id}',
                'data': None, 'html': None,
            }
        return {'speech': f'No checked-in guest in room {params["room"]}.',
                'action_type': 'error', 'url': None, 'data': None, 'html': None}

    def _handle_checkin_guest(self, params):
        from app.models import Reservation, Guest
        from app.services import get_business_date
        name = params.get('guest_name', '')
        res = (Reservation.query.join(Guest)
               .filter(Guest.name.ilike(f'%{name}%'),
                       Reservation.status.in_(['Confirmed', 'Reserved']),
                       Reservation.arrival_date <= get_business_date())
               .first())
        if res:
            return {
                'speech': f'Opening check-in for {res.guest.name}.',
                'action_type': 'navigate',
                'url': f'/checkin/{res.id}',
                'data': None, 'html': None,
            }
        return {'speech': f'No reservation found for guest {name}.',
                'action_type': 'error', 'url': None, 'data': None, 'html': None}

    def _handle_checkout_guest(self, params):
        from app.models import Reservation, Guest
        name = params.get('guest_name', '')
        res = (Reservation.query.join(Guest)
               .filter(Guest.name.ilike(f'%{name}%'),
                       Reservation.status == 'CheckedIn')
               .first())
        if res:
            return {
                'speech': f'Opening checkout for {res.guest.name}.',
                'action_type': 'navigate',
                'url': f'/checkout/{res.id}',
                'data': None, 'html': None,
            }
        return {'speech': f'No checked-in guest found matching {name}.',
                'action_type': 'error', 'url': None, 'data': None, 'html': None}

    def _handle_navigate(self, params):
        page = params.get('page', 'dashboard')
        url = self.NAV_URLS.get(page, '/')
        return {
            'speech': f'Opening {page}.',
            'action_type': 'navigate',
            'url': url,
            'data': None, 'html': None,
        }

    def _handle_daily_summary(self, params):
        from app.models import Reservation, Payment
        from app.services import get_business_date
        today = get_business_date()

        # Canonical occupancy from the engine (KPI Phase 1 convergence):
        # distinct occupied rooms over the sellable denominator — never a
        # raw CheckedIn-row count over raw inventory.
        from app.occupancy_engine import occupancy_snapshot
        _occ = occupancy_snapshot()
        total_rooms = _occ['sellable']
        occupied = _occ['occupied']
        occ_pct = round(_occ['pct'])

        arrivals = Reservation.query.filter(
            Reservation.arrival_date == today,
            Reservation.status.in_(['Confirmed', 'Reserved']),
        ).count()
        departures = Reservation.query.filter(
            Reservation.departure_date == today,
            Reservation.status == 'CheckedIn',
        ).count()

        revenue = sum(
            float(p.amount or 0)
            for p in Payment.query.filter_by(payment_date=today, is_voided=False).all()
        )

        speech = (
            f"Today's summary. "
            f"Occupancy: {occ_pct}%, {occupied} of {total_rooms} rooms. "
            f"{arrivals} arrivals, {departures} departures. "
            f"Revenue collected: {revenue:,.0f} rupees."
        )
        return {
            'speech': speech,
            'action_type': 'data',
            'url': None,
            'data': {
                'occupancy_pct': occ_pct, 'occupied': occupied, 'total_rooms': total_rooms,
                'arrivals': arrivals, 'departures': departures, 'revenue': revenue,
            },
            'html': None,
        }

    def _handle_checkin_prompt(self, params):
        return {
            'speech': 'Which room or guest would you like to check in? Say "check in room" followed by the room number.',
            'action_type': 'data', 'url': None, 'data': None, 'html': None,
        }

    def _handle_checkout_prompt(self, params):
        return {
            'speech': 'Which room or guest would you like to check out? Say "check out room" followed by the room number.',
            'action_type': 'data', 'url': None, 'data': None, 'html': None,
        }

    # ── Predictive Maintenance handlers ──

    def _handle_maintenance_predictions(self, params):
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        predictions = engine.get_failure_predictions(days_ahead=14)
        critical = [p for p in predictions if p['risk_level'] in ('Critical', 'High')]
        count = len(predictions)
        crit_count = len(critical)
        if count == 0:
            speech = 'No maintenance issues predicted in the next 14 days.'
        else:
            speech = f'{count} maintenance prediction{"s" if count != 1 else ""}. {crit_count} critical or high risk.'
            if critical:
                top = critical[0]
                speech += f' Top risk: Room {top["room_number"]}, {top["category"]}, {top["probability"]:.0%} probability.'
        return {'speech': speech, 'action_type': 'data', 'url': '/ai/predictive-maintenance',
                'data': {'total': count, 'critical': crit_count}, 'html': None}

    def _handle_room_health(self, params):
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        scores = engine.get_room_health_scores()
        at_risk = [s for s in scores if s['health_score'] < 60]
        avg = sum(s['health_score'] for s in scores) / len(scores) if scores else 100
        speech = f'Average room health score is {avg:.0f} out of 100. {len(at_risk)} room{"s" if len(at_risk) != 1 else ""} at risk.'
        return {'speech': speech, 'action_type': 'data', 'url': '/ai/predictive-maintenance',
                'data': {'avg_health': round(avg, 1), 'at_risk': len(at_risk)}, 'html': None}

    def _handle_room_health_detail(self, params):
        from app.models import Room
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        room = Room.query.filter_by(room_number=params['room']).first()
        if not room:
            return {'speech': f'Room {params["room"]} not found.', 'action_type': 'error',
                    'url': None, 'data': None, 'html': None}
        engine = PredictiveMaintenanceEngine()
        scores = engine.get_room_health_scores()
        room_score = next((s for s in scores if s['room_id'] == room.id), None)
        if room_score:
            speech = f'Room {room.room_number} health score is {room_score["health_score"]:.0f}. Risk level: {room_score["risk_level"]}.'
            if room_score['risk_factors']:
                speech += f' Issues: {", ".join(room_score["risk_factors"][:3])}.'
        else:
            speech = f'Room {room.room_number} has no health data yet.'
        return {'speech': speech, 'action_type': 'data', 'url': '/ai/predictive-maintenance',
                'data': room_score, 'html': None}

    def _handle_rooms_at_risk(self, params):
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        scores = engine.get_room_health_scores()
        at_risk = sorted([s for s in scores if s['health_score'] < 60], key=lambda s: s['health_score'])
        if not at_risk:
            speech = 'No rooms currently at risk. All health scores are above 60.'
        else:
            top3 = at_risk[:3]
            rooms_text = ', '.join(f'Room {s["room_number"]} ({s["health_score"]:.0f})' for s in top3)
            speech = f'{len(at_risk)} rooms at risk. Lowest: {rooms_text}.'
        return {'speech': speech, 'action_type': 'data', 'url': '/ai/predictive-maintenance',
                'data': {'count': len(at_risk)}, 'html': None}

    def _handle_maintenance_schedule(self, params):
        from app.ai_predictive_maintenance import PredictiveMaintenanceEngine
        engine = PredictiveMaintenanceEngine()
        schedules = engine.get_upcoming_schedules(days_ahead=7)
        overdue = [s for s in schedules if s['is_overdue']]
        speech = f'{len(schedules)} maintenance tasks scheduled in the next 7 days.'
        if overdue:
            speech += f' {len(overdue)} overdue.'
        return {'speech': speech, 'action_type': 'data', 'url': '/ai/predictive-maintenance',
                'data': {'upcoming': len(schedules), 'overdue': len(overdue)}, 'html': None}

    def _handle_help(self, params):
        return {
            'speech': (
                "I can help with: "
                "Check in or check out by room number or guest name. "
                "Room status and balance inquiries. "
                "Today's occupancy, revenue, arrivals, and departures. "
                "Mark rooms clean or dirty. "
                "Navigate to dashboard, housekeeping, reports, or AI insights. "
                "Maintenance predictions, room health, rooms at risk, and maintenance schedule. "
                "Ask for today's summary or flash report."
            ),
            'action_type': 'data', 'url': None, 'data': None, 'html': None,
        }

    def _handle_unknown(self, params):
        return {
            'speech': "I didn't understand that command. Say 'help' to hear what I can do.",
            'action_type': 'error', 'url': None, 'data': None, 'html': None,
        }


# Singletons
_parser = VoiceCommandParser()
_executor = VoiceCommandExecutor()


def process_voice_command(text):
    """Parse and execute a voice command. Returns response dict."""
    parsed = _parser.parse(text)
    result = _executor.execute(parsed)
    result['parsed_action'] = parsed['action']
    result['confidence'] = parsed['confidence']
    return result
