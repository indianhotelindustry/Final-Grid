"""
Declared reconciliations — which engine figure is supposed to equal which
ledger aggregate.

The rule this module exists to enforce
--------------------------------------
Every figure the application publishes for a business date should be
derivable from the primary record for that date. Where it is, the
reconciliation holds and the run records positive evidence of it. Where
it is not, the difference is attributed and reported — never absorbed,
and never explained away by widening a tolerance.

Each reconciliation is *declared*, not discovered. Matching engine
figures to ledger aggregates by searching for pairs that happen to be
equal would be circular: the framework would report agreement precisely
where it had gone looking for it, and a figure that reconciles to nothing
would silently drop out of the report. So the mapping is written down,
reviewable, and complete — and an engine figure that no declaration
covers is listed as UNRECONCILED rather than omitted.

Tolerance
---------
``EXACT`` throughout. These are not two implementations of an estimate
that may legitimately round differently; they are a total and the rows it
is a total of. The one concession is a 0.005 epsilon absorbing the
difference between a float the engine rounded to 2dp and the same figure
summed in Decimal — that is a representation artefact of the application
returning ``float``, and it is documented per reconciliation rather than
applied as a blanket band.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


#: Absorbs float-vs-Decimal representation only. Anything a hotel would
#: call money is orders of magnitude larger than this.
EPSILON = Decimal('0.005')


class Status:
    RECONCILED = 'RECONCILED'
    #: Both sides present and different — the finding.
    UNRECONCILED = 'UNRECONCILED'
    #: One side is missing, so nothing was actually compared. Never
    #: reported as agreement (Principle 10).
    NOT_COMPARABLE = 'NOT_COMPARABLE'
    #: Both sides present, both zero, over an empty population, on a day
    #: that DID trade. The figures agree but the agreement demonstrates
    #: nothing, and the day is not an excuse — this is a real gap.
    VACUOUS = 'VACUOUS'

    #: Both sides zero on a day with no primary records at all. Recorded
    #: rather than reported as agreement, but not counted as a gap in
    #: verification: there was no business to get wrong.
    #:
    #: The distinction matters because every real dataset contains closed
    #: days, and a framework that reported INCOMPLETE for the rest of
    #: time on account of them could never pass. A gate that can never
    #: pass gets switched off just as fast as one that can never fail.
    NO_ACTIVITY = 'NO_ACTIVITY'


@dataclass(frozen=True)
class Rule:
    rule_id: str
    engine_path: str
    ledger_expr: str
    why: str
    #: Ledger path whose row count is the population. When that count is
    #: zero and both sides are zero, the reconciliation is VACUOUS.
    population_path: str = ''


#: ``ledger_expr`` is a ``+``/``-`` expression over ledger paths. Kept
#: deliberately primitive: anything richer would be financial policy, and
#: financial policy belongs in the application, not in its measuring
#: instrument.
RULES: list[Rule] = [
    Rule('RC01', 'kpi.cash_revenue',
         'payments.direct.non_voided',
         'get_cash_revenue sums non-voided payments whose mode category is '
         'direct_payment. That is exactly the ledger slice of the same name.',
         'payments.direct.rows'),

    Rule('RC02', 'kpi.revenue_on_date',
         'payments.direct.non_voided',
         'get_revenue_on_date is documented as a wrapper over '
         'get_cash_revenue. If it ever stops equalling the same ledger '
         'slice, the two have diverged and one of them is wrong.',
         'payments.direct.rows'),

    Rule('RC03', 'kpi.ota_receivable_posted',
         'payments.ota.non_voided',
         'get_ota_receivable_posted sums non-voided payments whose mode '
         'category is ota_receivable.',
         'payments.ota.rows'),

    Rule('RC04', 'kpi.cash_discount',
         'discounts.checkout_total',
         'get_cash_discount sums discount_amount over reservations checked '
         'out on the date.',
         'discounts.checkout_rows'),

    Rule('RC05', 'kpi.net_cash_revenue',
         'payments.direct.non_voided - discounts.checkout_total',
         'Documented as cash collected minus checkout discounts.',
         'payments.direct.rows'),

    Rule('RC06', 'kpi.accrual_room_revenue',
         'occupancy.inhouse_tariff_sum',
         'get_accrual_room_revenue sums rate_per_night over reservations '
         'in-house on the date. The ledger sums the same column over the '
         'same span, read straight from the table.',
         'occupancy.inhouse_reservations'),

    Rule('RC07', 'kpi.accrual_extras',
         'charges.non_room_rent',
         'get_accrual_extras sums extra charges on the date excluding '
         'charge_type room_rent.',
         'charges.rows'),

    Rule('RC08', 'kpi.total_revenue',
         'occupancy.inhouse_tariff_sum + charges.non_room_rent',
         'get_total_revenue is accrual room revenue plus accrual extras.',
         'occupancy.inhouse_reservations'),

    Rule('RC09', 'kpi.accrual_summary.accrual_net',
         'occupancy.inhouse_tariff_sum + charges.non_room_rent '
         '- discounts.checkout_total',
         'accrual_net is gross accrual less the same checkout discount pool '
         'the cash side uses.',
         'occupancy.inhouse_reservations'),

    Rule('RC10', 'kpi.cash_summary.cash_collected',
         'payments.direct.non_voided',
         'cash_summary is a bundle over the same helpers; a divergence '
         'between the bundle and its parts means the bundle is a second '
         'implementation.',
         'payments.direct.rows'),

    Rule('RC11', 'nas.payment_summary.total_collected',
         'payments.direct.non_voided',
         'The night audit\'s collected total is the figure the day is '
         'reconciled on. It must equal the direct payments the ledger '
         'holds for the date.',
         'payments.direct.rows'),

    Rule('RC12', 'nas.payment_summary.total_ota_settled',
         'payments.ota.non_voided',
         'OTA settlement recorded by the night audit against the OTA '
         'receivable postings in the ledger.',
         'payments.ota.rows'),

    Rule('RC13', 'nas.payment_summary.payment_count',
         'payments.direct.rows + payments.ota.rows',
         'The count behind the money. A total that matches while the count '
         'does not means the population changed and two errors cancelled.',
         'payments.rows'),

    Rule('RC14', 'nas.revenue_summary.tax_amount',
         'tax.total',
         'The night audit\'s tax figure against the stored tax lines for '
         'the date. If a mutation to tax_lines does not move this, the '
         'stored lines are dead and tax is being recomputed for display.',
         'tax.rows'),

    Rule('RC15', 'nas.revenue_summary.room_revenue',
         'occupancy.inhouse_tariff_sum',
         'Room revenue earned on the date, against the tariff sum over the '
         'reservations in-house that night.',
         'occupancy.inhouse_reservations'),

    Rule('RC16', 'nas.occupancy_position.occupied',
         'occupancy.inhouse_distinct_rooms',
         'Rooms occupied on the date. The ledger derives this from '
         'reservation date spans; if the engine derives it from present-day '
         'room status the two part company as soon as the date is not '
         'today, which is the defect this rule exists to expose.',
         'occupancy.inhouse_reservations'),

    Rule('RC17', 'nas.reservation_reconciliation.arrivals_today',
         'movement.arrivals_expected',
         'Arrivals booked for the date.',
         'movement.arrivals_expected'),

    Rule('RC18', 'nas.reservation_reconciliation.departures_today',
         'movement.departures_expected',
         'Departures booked for the date.',
         'movement.departures_expected'),

    Rule('RC19', 'kpi.dashboard_kpis.cash_collected',
         'payments.direct.non_voided',
         'The dashboard bundle against the primary record. The dashboard is '
         'the surface management reads first, so its distance from the books '
         'is worth measuring directly rather than through two hops.',
         'payments.direct.rows'),

    Rule('RC20', 'kpi.monthly_revenue',
         '',                     # multi-date: computed by the caller
         'Month-to-date collections must equal the sum of the daily direct '
         'collections from the first of the month to the date. Verified '
         'across dates rather than within one, so it is computed by the '
         'runner from the per-date ledgers.',
         ''),
]

#: RC20 spans dates and is evaluated by the runner, not by ``apply``.
CROSS_DATE_RULES = {'RC20'}


@dataclass
class Reconciliation:
    rule_id: str
    engine_path: str
    ledger_expr: str
    status: str
    engine_value: str = ''
    ledger_value: str = ''
    delta: str = ''
    population: int = -1
    note: str = ''


def _to_decimal(text) -> Decimal | None:
    if text is None or text == '':
        return None
    try:
        return Decimal(str(text))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def evaluate(expr: str, ledger: dict) -> tuple[Decimal | None, list]:
    """Evaluate a ``+``/``-`` expression over ledger paths.

    Returns ``(value, missing_paths)``. A missing path yields ``None``
    rather than being treated as zero: a term that is absent is not a
    term that is nought, and coercing it would manufacture a
    reconciliation out of a gap.
    """
    total = Decimal('0')
    sign = Decimal('1')
    missing: list[str] = []
    token = ''

    def flush() -> None:
        nonlocal total, token
        name = token.strip()
        token = ''
        if not name:
            return
        value = _to_decimal(ledger.get(name))
        if value is None:
            missing.append(name)
            return
        total += sign * value

    for char in expr:
        if char in '+-':
            flush()
            sign = Decimal('1') if char == '+' else Decimal('-1')
        else:
            token += char
    flush()

    if missing:
        return None, missing
    return total, []


def apply(engine: dict, ledger: dict,
          day_traded: bool = True) -> tuple[list, list]:
    """Apply every same-date rule.

    ``day_traded`` is False when the date carries no primary record at
    all; agreement at zero is then recorded as ``NO_ACTIVITY`` rather
    than ``VACUOUS``. See ``Status.NO_ACTIVITY`` for why the distinction
    is drawn.

    Returns ``(reconciliations, unreconciled_engine_paths)``. The second
    list is every engine figure no rule covers — the framework's own
    coverage gap, printed on each run so the declared mapping cannot
    quietly stop keeping up with the application.
    """
    out: list[Reconciliation] = []
    covered: set[str] = set()

    for rule in RULES:
        # Cross-date rules cover their engine path just as much as
        # same-date ones do; they are simply evaluated by the runner.
        # Leaving them out of ``covered`` would list them as an
        # uncovered gap while they are in fact checked.
        covered.add(rule.engine_path)
        if rule.rule_id in CROSS_DATE_RULES:
            continue
        engine_value = _to_decimal(engine.get(rule.engine_path))
        ledger_value, missing = evaluate(rule.ledger_expr, ledger)

        rec = Reconciliation(
            rule_id=rule.rule_id, engine_path=rule.engine_path,
            ledger_expr=rule.ledger_expr, status=Status.NOT_COMPARABLE,
            engine_value='' if engine_value is None else str(engine_value),
            ledger_value='' if ledger_value is None else str(ledger_value))

        population = -1
        if rule.population_path:
            pop = _to_decimal(ledger.get(rule.population_path))
            population = -1 if pop is None else int(pop)
        rec.population = population

        if engine_value is None:
            rec.note = (f'engine did not produce {rule.engine_path} — the '
                        f'probe errored, or the helper no longer publishes '
                        f'this figure')
        elif ledger_value is None:
            rec.note = ('ledger term(s) absent: ' + ', '.join(missing))
        else:
            delta = engine_value - ledger_value
            rec.delta = str(delta)
            if abs(delta) <= EPSILON:
                if population != 0:
                    rec.status = Status.RECONCILED
                elif day_traded:
                    rec.status = Status.VACUOUS
                    rec.note = ('both sides zero over an empty population on '
                                'a day that traded; agreement demonstrates '
                                'nothing')
                else:
                    rec.status = Status.NO_ACTIVITY
                    rec.note = ('no primary record for this date at all; '
                                'recorded, but not evidence of correctness')
            else:
                rec.status = Status.UNRECONCILED
                sign = '+' if delta > 0 else ''
                rec.note = (f'engine is {sign}{delta} against the '
                            f'primary record')
        out.append(rec)

    unreconciled_paths = sorted(
        path for path in engine
        if path not in covered
        and not path.endswith('[len]')
        and not path.endswith('[type]'))
    return out, unreconciled_paths
