"""
The ENGINE account — what the application says about a past date.

Only date-parameterised entry points are probed. A helper that takes no
date cannot answer a question about 27 May: it answers about now, and
calling it during a replay would silently record today's number against a
historical day. Those helpers are not skipped quietly — they are listed
in ``NOT_REPLAYABLE`` with the reason, counted on every run, and included
in the evidence pack, because "this figure has no historical form" is one
of the more useful things a replay framework can tell you before a
migration starts.

Each probe returns either a scalar or a dict; both are flattened to
``{dotted path: value}`` by D2's figure walker, so the ENGINE account has
exactly the same shape as the LEDGER account and the two can be compared
path by path.

Read-only contract
------------------
Every probe below was checked for writes. ``kpi_helpers``,
``occupancy_engine`` and ``night_audit_service`` contain no ``commit``,
``session.add`` or ``flush``. The two helpers D1 documented as writers —
``gst_service.get_folio_gst_summary`` and ``services.run_night_audit`` —
are not called here either, for the same reasons recorded there.
"""
from __future__ import annotations

import datetime as _dt
import traceback

from verification.golden import normalize as norm


class ProbeError(RuntimeError):
    """A probe raised. Recorded against that probe alone, never fatal."""


#: Engine entry points that CANNOT be replayed, with the reason. Reported
#: on every run. The distinction is not stylistic: a figure that only has
#: a present-tense form cannot be verified against history at all, so any
#: report showing it for a past date is showing today's number under a
#: historical heading.
NOT_REPLAYABLE: list[tuple[str, str]] = [
    ('kpi_helpers.get_occupancy',
     'takes no date; counts reservations in-house NOW'),
    ('kpi_helpers.get_occupied_count',
     'takes no date; counts reservations in-house NOW'),
    ('kpi_helpers.get_adr',
     'takes no date; averages the tariffs of CURRENTLY checked-in '
     'reservations, so it returns 0.00 for every past date once the '
     'guests have left'),
    ('kpi_helpers.get_revpar',
     'derived from get_adr and get_occupancy, both present-tense'),
    ('kpi_helpers.get_sellable_room_count',
     'reads Room.status, which is present-tense: it says what a room is '
     'like now, not what it was like on the replayed date'),
    ('occupancy_engine.occupancy_snapshot',
     'reads Room.status; same present-tense limitation'),
    ('night_audit_service.NightAuditService.occupancy_position (room half)',
     'the reservation half is date-scoped and IS replayed; the room '
     'counts inside it derive from Room.status and are not'),
]


# ---------------------------------------------------------------------------
# Probe declarations
# ---------------------------------------------------------------------------

def _kpi_probes(day: _dt.date) -> list[tuple[str, object]]:
    """Date-parameterised helpers from ``app.kpi_helpers``."""
    from app import kpi_helpers as K

    month_start = day.replace(day=1)
    return [
        ('kpi.cash_revenue', lambda: K.get_cash_revenue(day)),
        ('kpi.ota_receivable_posted', lambda: K.get_ota_receivable_posted(day)),
        ('kpi.ota_receivable_mtd', lambda: K.get_ota_receivable_mtd(day)),
        ('kpi.monthly_revenue',
         lambda: K.get_monthly_revenue(month_start, day)),
        ('kpi.previous_month_revenue',
         lambda: K.get_previous_month_revenue(day)),
        ('kpi.revenue_on_date', lambda: K.get_revenue_on_date(day)),
        ('kpi.total_revenue', lambda: K.get_total_revenue(day)),
        ('kpi.cash_discount', lambda: K.get_cash_discount(day)),
        ('kpi.net_cash_revenue', lambda: K.get_net_cash_revenue(day)),
        ('kpi.accrual_room_revenue',
         lambda: K.get_accrual_room_revenue(day)),
        ('kpi.accrual_extras', lambda: K.get_accrual_extras(day)),
        ('kpi.payment_by_mode', lambda: K.get_payment_by_mode(day)),
        ('kpi.revenue_by_source', lambda: K.get_revenue_by_source(day)),
        ('kpi.cash_summary', lambda: K.get_cash_summary(day)),
        ('kpi.accrual_summary', lambda: K.get_accrual_summary(day)),
        ('kpi.dashboard_kpis', lambda: K.get_dashboard_kpis(day)),
    ]


#: Read-only sections of the night audit report builder. ``full_report``
#: is not called: it is the union of these plus advisory sections, and
#: calling both would record the same figures twice under two paths,
#: which would double the weight of any divergence in them.
NAS_SECTIONS = (
    'audit_header',
    'occupancy_position',
    'reservation_reconciliation',
    'revenue_summary',
    'payment_summary',
    'folio_control',
    'room_charge_audit',
    'tax_snapshot',
    'final_control',
)


def _nas_probes(day: _dt.date) -> list[tuple[str, object]]:
    """Sections of the read-only night audit report builder."""
    from app.night_audit_service import NightAuditService

    service = NightAuditService(day)
    return [(f'nas.{name}', getattr(service, name))
            for name in NAS_SECTIONS]


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def probe(day: _dt.date) -> tuple[dict, dict, list]:
    """Run every replayable probe for *day*.

    Returns ``(figures, errors, truncations)``. A probe that raises is
    recorded in *errors* under its own name and contributes no figures;
    the remaining probes still run, because a partial account with a
    visible hole is useful and a crashed replay is not.
    """
    figures: dict[str, str] = {}
    errors: dict[str, str] = {}
    truncations: list[str] = []

    for name, call in _kpi_probes(day) + _nas_probes(day):
        try:
            value = call()
        except Exception as exc:                       # noqa: BLE001
            errors[name] = f'{type(exc).__name__}: {exc}'
            continue
        try:
            walked, trunc = norm.figures_from_context({name: value})
        except Exception as exc:                       # noqa: BLE001
            errors[name] = (f'figure extraction failed: '
                            f'{type(exc).__name__}: {exc}')
            continue
        figures.update(walked)
        truncations.extend(trunc)

    return dict(sorted(figures.items())), dict(sorted(errors.items())), \
        sorted(truncations)


def probe_safely(day: _dt.date) -> tuple[dict, dict, list]:
    """``probe`` with a last-resort guard, so one date cannot end a run."""
    try:
        return probe(day)
    except Exception:                                   # noqa: BLE001
        return {}, {'__probe__': traceback.format_exc(limit=6)}, []
