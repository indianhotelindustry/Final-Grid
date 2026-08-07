"""
Shared measurement helpers for invariant rules.

Small on purpose. Anything that encodes a financial decision belongs in
the invariant that makes it, where the reviewer reading the business rule
can see it; a helper that quietly decided what counted as a discrepancy
would put the decision somewhere nobody looks.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from verification.invariants.model import Status, Violation

#: Money is compared to the paisa. The half-paisa allowance absorbs the
#: difference between a float the application rounded to 2 dp and the
#: same figure summed in Decimal — a representation artefact, not a
#: tolerance band. Anything a hotel would call money is far larger.
EPSILON = Decimal('0.005')


def dec(value) -> Decimal:
    """Decimal from a database value. NULL is zero; junk raises."""
    if value is None:
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def try_dec(value) -> Decimal | None:
    try:
        return dec(value)
    except (InvalidOperation, ValueError, ArithmeticError, TypeError):
        return None


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal('0.01')))


def differs(a: Decimal, b: Decimal, epsilon: Decimal = EPSILON) -> bool:
    return abs(a - b) > epsilon


def verdict(population: int, violations: list) -> str:
    """The three-way outcome every invariant shares.

    An empty population is VACUOUS, never HOLDS. Two sides agreeing over
    nothing have not been shown to agree about anything (P10), and an
    engine that reported "holds" for a rule it never actually exercised
    would be the purest example of the control that cannot fail.
    """
    if violations:
        return Status.VIOLATED
    if population == 0:
        return Status.VACUOUS
    return Status.HOLDS


def row_violation(object_type: str, object_id, expected: str, observed: str,
                  amount: Decimal | str = '0', variance: str = '',
                  **detail) -> Violation:
    return Violation(
        object_type=object_type, object_id=str(object_id),
        expected=expected, observed=observed,
        amount=str(amount), variance=variance, detail=detail)


def scope_clause(ctx, date_column: str = '',
                 reservation_column: str = '') -> tuple:
    """SQL fragment and parameters narrowing a query to the run's scope.

    Returns ``('', ())`` for whole-database scope. An invariant that
    supports a date-scoped mode MUST use this rather than filtering by
    hand: a rule that ignored the scope would report whole-database
    findings under a single date's heading, and the date-by-date replay
    would then show the same violation on every day of the year.
    """
    clauses: list[str] = []
    params: list = []
    if date_column and ctx.date:
        clauses.append(f'{date_column} = ?')
        params.append(ctx.date)
    if reservation_column and ctx.reservation_id:
        clauses.append(f'{reservation_column} = ?')
        params.append(ctx.reservation_id)
    if not clauses:
        return '', ()
    return ' AND ' + ' AND '.join(clauses), tuple(params)


def summarise(label: str, population: int, violations: list) -> str:
    if not population:
        return f'{label}: no rows in scope'
    if not violations:
        return f'{label}: {population} row(s) examined, all satisfied'
    return (f'{label}: {len(violations)} of {population} row(s) '
            f'violate the rule')
