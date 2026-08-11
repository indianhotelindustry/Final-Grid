"""
The registry — registration, extension points, and the rules that stop it
degrading.

Extension point
---------------
A new invariant is added by writing an ``@invariant(...)`` declaration in
one of the ``rules_*`` modules, or in any module that is imported before
the engine runs. Nothing else changes: no list to update, no dispatch
table, no engine edit. That is the whole extension mechanism, and it is
deliberately the only one.

Why registration validates
--------------------------
A registry that accepts anything becomes a place where half-declared
invariants accumulate. So registration refuses:

* a duplicate id — two invariants answering to ``INV-A01`` would make
  every report ambiguous and every historical comparison wrong;
* an unknown category, severity, blocking level or mode;
* an empty required field — an invariant with no stated business purpose
  is one nobody has thought through, and it will be the one that produces
  an unexplainable failure at the worst moment;
* an invariant with neither a ``negative_seed`` nor a stated
  ``not_seedable_reason``. Under P9 a control that cannot be shown to
  fail is not a control, so "how would this break?" must be answered when
  the invariant is written, not when someone gets round to commissioning
  it.

These are raised at import time, which means a malformed invariant breaks
the run loudly instead of quietly narrowing coverage.
"""
from __future__ import annotations

from verification.invariants.model import (
    ALL_CATEGORIES, ALL_MODES, BLOCKING_RANK, Blocking, Commissioning,
    Invariant, SEVERITY_RANK,
)


class RegistrationError(ValueError):
    """An invariant declaration is not usable. Raised at import time."""


#: id -> Invariant, in declaration order.
_REGISTRY: dict[str, Invariant] = {}

REQUIRED_TEXT_FIELDS = (
    'title', 'business_purpose', 'business_rule', 'canonical_engine',
    'validation_method', 'evidence_produced', 'failure_message',
    'applicable_releases', 'applicable_business_dates',
)


def _validate(inv: Invariant) -> None:
    if inv.invariant_id in _REGISTRY:
        raise RegistrationError(
            f'Duplicate invariant id {inv.invariant_id!r}. Two invariants '
            f'sharing an id would make every report ambiguous and every '
            f'historical comparison meaningless.')
    if inv.category not in ALL_CATEGORIES:
        raise RegistrationError(
            f'{inv.invariant_id}: unknown category {inv.category!r}')
    if inv.severity not in SEVERITY_RANK:
        raise RegistrationError(
            f'{inv.invariant_id}: unknown severity {inv.severity!r}')
    if inv.blocking not in BLOCKING_RANK:
        raise RegistrationError(
            f'{inv.invariant_id}: unknown blocking level {inv.blocking!r}')
    if not inv.modes:
        raise RegistrationError(
            f'{inv.invariant_id}: declares no validation modes, so nothing '
            f'would ever run it')
    for mode in inv.modes:
        if mode not in ALL_MODES:
            raise RegistrationError(
                f'{inv.invariant_id}: unknown mode {mode!r}')
    if not inv.principles:
        raise RegistrationError(
            f'{inv.invariant_id}: names no constitutional principle. An '
            f'invariant that enforces nothing in the constitution is a '
            f'preference, not an obligation.')
    for name in REQUIRED_TEXT_FIELDS:
        if not (getattr(inv, name) or '').strip():
            raise RegistrationError(
                f'{inv.invariant_id}: {name} is empty')
    if not inv.data_sources:
        raise RegistrationError(
            f'{inv.invariant_id}: declares no data sources')
    if not inv.likely_root_causes:
        raise RegistrationError(
            f'{inv.invariant_id}: declares no likely root causes. The field '
            f'exists because a failure at 2am is useless without one.')
    if not inv.suggested_investigation:
        raise RegistrationError(
            f'{inv.invariant_id}: declares no suggested investigation')
    if not (inv.negative_seed or inv.negative_patch or
            inv.not_seedable_reason):
        raise RegistrationError(
            f'{inv.invariant_id}: has no negative seed, no negative patch and '
            f'no stated reason why it cannot be broken. Under P9 a control '
            f'that cannot be shown to fail is not a control, and "how would '
            f'this break?" is a question for the moment the invariant is '
            f'written, not for whenever somebody gets round to commissioning '
            f'it.')
    if inv.negative_seed and not inv.negative_seed_reason:
        raise RegistrationError(
            f'{inv.invariant_id}: has a negative seed with no stated reason')
    if inv.negative_patch:
        if not inv.negative_patch_reason:
            raise RegistrationError(
                f'{inv.invariant_id}: has a negative patch with no stated '
                f'reason')
        if len(inv.negative_patch) != 3:
            raise RegistrationError(
                f'{inv.invariant_id}: negative_patch must be '
                f'(dotted_callable, result_key, delta)')
    if inv.fn is None:
        raise RegistrationError(
            f'{inv.invariant_id}: has no measurement function')


def invariant(**declaration):
    """Declare and register an invariant.

    Usage::

        @invariant(invariant_id='INV-A01', title='...', category=..., ...)
        def _a01(ctx):
            ...
            return status, population, violations, extras
    """
    def deco(fn):
        inv = Invariant(fn=fn, **declaration)
        _validate(inv)
        _REGISTRY[inv.invariant_id] = inv
        return fn
    return deco


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def load_all() -> None:
    """Import every rules module so the registry is fully populated.

    Called by the engine before any run. Importing on demand rather than
    at package import keeps ``verification.invariants.model`` usable by
    tooling that only wants the vocabularies.
    """
    from verification.invariants import (  # noqa: F401
        rules_a, rules_b, rules_c, rules_d, rules_r,
    )


def all_invariants() -> list:
    load_all()
    return list(_REGISTRY.values())


def get(invariant_id: str) -> Invariant:
    load_all()
    try:
        return _REGISTRY[invariant_id]
    except KeyError:
        raise KeyError(
            f'No invariant {invariant_id!r}. Registered: '
            f'{", ".join(sorted(_REGISTRY))}') from None


def select(mode: str | None = None,
           category: str | None = None,
           ids: list | None = None) -> list:
    """The invariants that apply to a run.

    Selection is by declaration. An invariant excluded because it does
    not support the mode is reported by the engine as NOT_APPLICABLE
    rather than dropped, so a run's coverage is always the full registry.
    """
    out = all_invariants()
    if ids:
        wanted = set(ids)
        out = [i for i in out if i.invariant_id in wanted]
    if category:
        out = [i for i in out if i.category == category]
    if mode:
        out = [i for i in out if i.supports(mode)]
    return out


def category_matrix() -> dict:
    """{category: {severity: [ids]}} — the shape of the coverage."""
    out: dict = {}
    for inv in all_invariants():
        out.setdefault(inv.category, {}).setdefault(inv.severity, []).append(
            inv.invariant_id)
    return out


def severity_matrix() -> dict:
    """{severity: {blocking: [ids]}} — how the process reacts."""
    out: dict = {}
    for inv in all_invariants():
        out.setdefault(inv.severity, {}).setdefault(inv.blocking, []).append(
            inv.invariant_id)
    return out


def principle_matrix() -> dict:
    """{principle: [ids]} — constitutional coverage.

    A principle with no invariant is a hole in the constitution's
    enforcement, and this is where it becomes visible.
    """
    out: dict = {}
    for inv in all_invariants():
        for principle in inv.principles:
            out.setdefault(principle, []).append(inv.invariant_id)
    return out


def mode_matrix() -> dict:
    """{mode: [ids]} — which invariants a given run actually exercises."""
    out: dict = {}
    for inv in all_invariants():
        for mode in inv.modes:
            out.setdefault(mode, []).append(inv.invariant_id)
    return out


def commissioning_gaps() -> list:
    """Invariants that may not be relied on yet, with the reason."""
    out = []
    for inv in all_invariants():
        if inv.commissioning_status == Commissioning.COMMISSIONED:
            continue
        out.append({
            'invariant_id': inv.invariant_id,
            'status': inv.commissioning_status,
            'reason': (inv.not_seedable_reason or
                       'declared but not yet commissioned'),
        })
    return out


def release_blocking_ids() -> list:
    return [i.invariant_id for i in all_invariants()
            if i.blocking == Blocking.RELEASE]


def unbacked_commissioning_claims() -> tuple:
    """Invariants declaring COMMISSIONED that the evidence does not support.

    ``commissioning_status`` is declared in code, which makes flipping it
    to COMMISSIONED a deliberate act somebody has to perform and a
    reviewer can see. That is the right gate — and it is also a gate that
    can be walked through without doing the work.

    So the claim is checked against the most recent commissioning
    evidence pack. An invariant that declares itself commissioned while
    the last run failed it, or never covered it, is reported at BLOCK.
    Returns ``(findings, evidence_pack_path)``; an empty path means no
    commissioning evidence exists at all, which is itself the finding.
    """
    import json
    import os

    from verification.config import EVIDENCE_DIR

    if not os.path.isdir(EVIDENCE_DIR):
        return ([{'invariant_id': i.invariant_id,
                  'reason': 'no commissioning evidence exists on this machine'}
                 for i in all_invariants()
                 if i.commissioning_status == Commissioning.COMMISSIONED], '')

    packs = sorted(name for name in os.listdir(EVIDENCE_DIR)
                   if name.endswith('_inv_commission'))
    if not packs:
        return ([{'invariant_id': i.invariant_id,
                  'reason': 'no commissioning evidence exists on this machine'}
                 for i in all_invariants()
                 if i.commissioning_status == Commissioning.COMMISSIONED], '')

    pack = os.path.join(EVIDENCE_DIR, packs[-1])
    try:
        with open(os.path.join(pack, 'result.json'), encoding='utf-8') as fh:
            payload = json.load(fh)
    except Exception as exc:                             # noqa: BLE001
        return ([{'invariant_id': '*',
                  'reason': f'commissioning evidence unreadable: {exc}'}], pack)

    passed = {o['invariant_id'] for o in payload.get('outcomes', [])
              if all((o.get('checks') or {}).values()) and o.get('checks')}
    findings = []
    for inv in all_invariants():
        if inv.commissioning_status != Commissioning.COMMISSIONED:
            continue
        if inv.invariant_id not in passed:
            findings.append({
                'invariant_id': inv.invariant_id,
                'reason': (f'declares COMMISSIONED, but the most recent '
                           f'commissioning run ({packs[-1]}) did not pass '
                           f'it')})
    return findings, pack
