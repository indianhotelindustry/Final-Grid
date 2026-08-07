"""
The fault registry — registration, validation, and the taxonomy.

Extension point
---------------
A new fault is one ``@fault(...)`` declaration in a ``faults_*`` module.
No pipeline change, no dispatch table, no classifier edit. That is the
whole mechanism and deliberately the only one, because the charter's
requirement is precisely that adding a fault requires only registration.

Why registration validates
--------------------------
A fault registry that accepts anything degrades into a drawer of
half-written test cases. Registration therefore refuses:

* a duplicate id;
* an unknown category, method, layer, severity or mode;
* an empty required field — a fault with no stated purpose is one nobody
  has thought through, and it will be the one whose result nobody can
  interpret;
* an empty payload for a method that needs one;
* **an expectation of no layer with no stated ``uncovered_reason``.** A
  fault nothing is expected to detect is either a mistake or a
  verification gap; the platform will not guess which.
* an expected invariant that is not in the D4 registry. A declaration
  naming ``INV-Z99`` would quietly never be satisfied, and the fault
  would report a permanent MISS against an invariant that does not
  exist.

All of these raise at import time, so a malformed fault breaks the run
loudly rather than silently narrowing coverage.
"""
from __future__ import annotations

from verification.faults.model import (
    ALL_CATEGORIES, ALL_LAYERS, ALL_MODES, Commissioning, Fault, Method,
    SEVERITY_RANK, TargetLayer,
)


class RegistrationError(ValueError):
    """A fault declaration is not usable. Raised at import time."""


_REGISTRY: dict[str, Fault] = {}

REQUIRED_TEXT_FIELDS = (
    'title', 'purpose', 'business_rule_challenged',
    'expected_replay_behaviour', 'expected_parity_behaviour',
    'expected_certification_impact', 'expected_evidence',
    'cleanup_strategy', 'repeatability', 'determinism',
    'applicable_releases', 'applicable_business_dates',
)

METHODS_REQUIRING_PAYLOAD = (Method.SQL, Method.ENGINE_PATCH, Method.ENV,
                             Method.FILE)

TARGET_LAYERS = tuple(v for k, v in vars(TargetLayer).items()
                      if not k.startswith('_') and isinstance(v, str))

ALL_METHODS = tuple(v for k, v in vars(Method).items()
                    if not k.startswith('_') and isinstance(v, str))


def _known_invariant_ids() -> set:
    from verification.invariants import registry as invreg
    return {i.invariant_id for i in invreg.all_invariants()}


def _validate(f: Fault) -> None:
    if f.fault_id in _REGISTRY:
        raise RegistrationError(
            f'Duplicate fault id {f.fault_id!r}. Two faults sharing an id '
            f'would make every commissioning record ambiguous.')
    if f.category not in ALL_CATEGORIES:
        raise RegistrationError(f'{f.fault_id}: unknown category '
                                f'{f.category!r}')
    if f.injection_method not in ALL_METHODS:
        raise RegistrationError(f'{f.fault_id}: unknown injection method '
                                f'{f.injection_method!r}')
    if f.target_layer not in TARGET_LAYERS:
        raise RegistrationError(f'{f.fault_id}: unknown target layer '
                                f'{f.target_layer!r}')
    if f.expected_severity not in SEVERITY_RANK:
        raise RegistrationError(f'{f.fault_id}: unknown severity '
                                f'{f.expected_severity!r}')
    if not f.modes:
        raise RegistrationError(
            f'{f.fault_id}: declares no execution modes, so nothing would '
            f'ever run it')
    for mode in f.modes:
        if mode not in ALL_MODES:
            raise RegistrationError(f'{f.fault_id}: unknown mode {mode!r}')
    for layer in f.expected_detection:
        if layer not in ALL_LAYERS:
            raise RegistrationError(f'{f.fault_id}: unknown layer {layer!r}')
    for name in REQUIRED_TEXT_FIELDS:
        if not (getattr(f, name) or '').strip():
            raise RegistrationError(f'{f.fault_id}: {name} is empty')
    if not f.target_objects:
        raise RegistrationError(f'{f.fault_id}: declares no target objects')
    if not f.principles:
        raise RegistrationError(
            f'{f.fault_id}: names no constitutional principle. A fault that '
            f'challenges nothing in the constitution is a curiosity, not a '
            f'control.')
    if not f.root_cause_candidates:
        raise RegistrationError(
            f'{f.fault_id}: declares no root cause candidates. The field '
            f'exists because a detection nobody can act on is half a '
            f'control.')
    if f.injection_method in METHODS_REQUIRING_PAYLOAD and not f.payload:
        raise RegistrationError(
            f'{f.fault_id}: method {f.injection_method} needs a payload')
    if not f.expected_detection and not f.uncovered_reason:
        raise RegistrationError(
            f'{f.fault_id}: expects no layer to detect it and gives no '
            f'reason. A fault nothing detects is either a mistake or a '
            f'verification gap, and the platform will not guess which.')
    if f.uncovered_reason and not f.covered_by_deliverable:
        raise RegistrationError(
            f'{f.fault_id}: is declared uncovered but names no deliverable '
            f'that will cover it, so the gap would never be tracked.')

    known = _known_invariant_ids()
    for invariant_id in f.expected_invariants:
        if invariant_id not in known:
            raise RegistrationError(
                f'{f.fault_id}: expects {invariant_id}, which is not in the '
                f'D4 registry. The fault would report a permanent MISS '
                f'against an invariant that does not exist.')


def fault(**declaration):
    """Declare and register a fault."""
    def deco(fn=None):
        f = Fault(**declaration)
        _validate(f)
        _REGISTRY[f.fault_id] = f
        return fn
    return deco


def register(f: Fault) -> Fault:
    """Register a pre-built Fault. Used by generated families."""
    _validate(f)
    _REGISTRY[f.fault_id] = f
    return f


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------

def load_all() -> None:
    from verification.faults import (faults_a, faults_b, faults_c,  # noqa: F401
                                     faults_d)


def all_faults() -> list:
    load_all()
    return list(_REGISTRY.values())


def get(fault_id: str):
    load_all()
    try:
        return _REGISTRY[fault_id]
    except KeyError:
        raise KeyError(
            f'No fault {fault_id!r}. Registered: '
            f'{", ".join(sorted(_REGISTRY))}') from None


def select(category: str | None = None, mode: str | None = None,
           ids: list | None = None, method: str | None = None,
           include_uncovered: bool = True) -> list:
    out = all_faults()
    if ids:
        wanted = set(ids)
        out = [f for f in out if f.fault_id in wanted]
    if category:
        out = [f for f in out if f.category == category]
    if method:
        out = [f for f in out if f.injection_method == method]
    if mode:
        out = [f for f in out if mode in f.modes]
    if not include_uncovered:
        out = [f for f in out if f.expected_detection]
    return out


# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

def category_matrix() -> dict:
    out: dict = {}
    for f in all_faults():
        out.setdefault(f.category, {}).setdefault(
            f.expected_severity, []).append(f.fault_id)
    return out


def layer_matrix() -> dict:
    """{layer: [fault ids expected to be detected by it]}.

    A layer with few faults pointed at it is a layer this platform has
    barely challenged, which is a statement about the platform rather
    than about the layer.
    """
    out: dict = {layer: [] for layer in ALL_LAYERS}
    for f in all_faults():
        for layer in f.expected_detection:
            out[layer].append(f.fault_id)
    return out


def method_matrix() -> dict:
    out: dict = {}
    for f in all_faults():
        out.setdefault(f.injection_method, []).append(f.fault_id)
    return out


def invariant_coverage() -> dict:
    """{invariant id: [faults that should make it fire]}.

    Read the other way round, this is the list of D4 invariants that no
    fault challenges — invariants whose commissioning rests entirely on
    their own seed, with no independent confirmation.
    """
    from verification.invariants import registry as invreg

    out: dict = {i.invariant_id: [] for i in invreg.all_invariants()}
    for f in all_faults():
        for invariant_id in f.expected_invariants:
            out[invariant_id].append(f.fault_id)
    return out


def uncovered_faults() -> list:
    """Faults no layer of the current framework can detect."""
    return [{'fault_id': f.fault_id, 'title': f.title,
             'reason': f.uncovered_reason,
             'covered_by': f.covered_by_deliverable}
            for f in all_faults() if not f.expected_detection]


def commissioning_gaps() -> list:
    return [{'fault_id': f.fault_id,
             'status': f.commissioning_status,
             'reason': (f.uncovered_reason or
                        'declared but not yet commissioned')}
            for f in all_faults()
            if f.commissioning_status != Commissioning.COMMISSIONED]


def unbacked_commissioning_claims() -> tuple:
    """Faults claiming COMMISSIONED that the evidence does not support.

    The same cross-check D4 applies to its invariants, for the same
    reason: a status declared in code is a gate somebody can walk
    through without doing the work.
    """
    import json
    import os

    from verification.config import EVIDENCE_DIR

    claimants = [f for f in all_faults()
                 if f.commissioning_status == Commissioning.COMMISSIONED]
    if not claimants:
        return [], ''

    packs = (sorted(name for name in os.listdir(EVIDENCE_DIR)
                    if name.endswith('_fip_commission'))
             if os.path.isdir(EVIDENCE_DIR) else [])
    if not packs:
        return ([{'fault_id': f.fault_id,
                  'reason': 'no commissioning evidence exists on this machine'}
                 for f in claimants], '')

    pack = os.path.join(EVIDENCE_DIR, packs[-1])
    try:
        with open(os.path.join(pack, 'result.json'), encoding='utf-8') as fh:
            payload = json.load(fh)
    except Exception as exc:                             # noqa: BLE001
        return ([{'fault_id': '*',
                  'reason': f'commissioning evidence unreadable: {exc}'}],
                pack)

    passed = {o['fault_id'] for o in payload.get('outcomes', [])
              if o.get('checks') and all(o['checks'].values())}
    findings = [{'fault_id': f.fault_id,
                 'reason': (f'declares COMMISSIONED, but the most recent '
                            f'commissioning run ({packs[-1]}) did not pass it')}
                for f in claimants if f.fault_id not in passed]
    return findings, pack
