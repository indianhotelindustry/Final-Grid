"""
The invariant object, the evidence object, and the vocabularies they use.

Why an object rather than an assertion
--------------------------------------
An assertion tells you that something is wrong. An invariant has to tell
you *what obligation was broken, whose obligation it was, what it costs,
where to look, and whether the control that found it has ever been shown
to work*. A bare ``assert charges - payments == outstanding`` carries none
of that, and six months later nobody can say whether it was ever true, on
which dates, or what a failure would mean for the accounts.

So every invariant in this engine is a structured declaration. The
declaration is written first and the check second, because the fields
that are hard to fill in — Business Purpose, Likely Root Causes,
Suggested Investigation — are exactly the ones that reveal an invariant
nobody has actually thought through.

Constitutional basis
--------------------
Phase 2.6 and the Financial Constitution, P1–P14. Each invariant names
the principles it enforces in ``principles``; the engine reports coverage
per principle, so a principle with no invariant is visible as a gap
rather than assumed to be satisfied.

Commissioning gate
------------------
``commissioning_status`` is part of the declaration, not a side note. An
invariant that has never been shown to fail is not a control (P9), and
the engine refuses to count one as evidence: its result is reported, but
it is excluded from the release verdict and listed separately. That is
the mechanism behind the standing rule that no invariant may enter
production until commissioning passes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

#: The Financial Constitution, P1-P14, in the order the governing document
#: declares them. Held here so that ``principles=('P7',)`` on an invariant
#: is a reference to something written down rather than a private code.
#:
#: Some principles are obligations of the SYSTEM and are enforced by
#: invariants. Others are obligations of the VERIFICATION FRAMEWORK itself
#: and are enforced structurally — by the commissioning gate, by the
#: evidence model, by the refusal to report an empty population as
#: agreement. Those are marked, because listing them as "not enforced"
#: would be as misleading as listing them as covered.
PRINCIPLES: dict = {
    'P1': ('One canonical derivation', 'invariant'),
    'P2': ('Frozen historical values remain immutable', 'invariant'),
    'P3': ('Reports consume canonical engines', 'invariant'),
    'P4': ('Night Audit orchestrates rather than derives', 'invariant'),
    'P5': ('Validation occurs at the service layer', 'invariant'),
    'P6': ('Evidence must be capable of falsifying a change', 'structural'),
    'P7': ('Closed periods are append-only', 'invariant'),
    'P8': ('One temporal basis', 'invariant'),
    'P9': ('Controls must be capable of failure', 'structural'),
    'P10': ('Absence of evidence is not evidence of correctness',
            'structural'),
    'P11': ('Observable correctness', 'invariant'),
    'P12': ('Historical immutability', 'invariant'),
    'P13': ('Verification before implementation', 'structural'),
    'P14': ('Every financial object has provenance', 'invariant'),
}

#: How each structurally-enforced principle is enforced, stated so the
#: claim can be checked rather than taken on trust.
STRUCTURAL_ENFORCEMENT: dict = {
    'P6': ('Every invariant must declare a negative_seed or a '
           'negative_patch: a concrete way it could be made to fail. '
           'Registration refuses one that declares neither, so an '
           'invariant incapable of falsifying a change cannot enter the '
           'registry.'),
    'P9': ('Commissioning demonstrates the failure of every invariant '
           'across eight elements. Until it has, the invariant\'s result '
           'is reported but excluded from every verdict.'),
    'P10': ('An invariant evaluated over an empty population reports '
            'VACUOUS, never HOLDS, and VACUOUS keeps the run at '
            'INCOMPLETE rather than PASS.'),
    'P13': ('Wave 0 builds the verification framework before any '
            'financial logic is changed, and D5 challenges every layer '
            'of it with realistic faults before that framework is relied '
            'upon. Structurally, the registry refuses an invariant that '
            'cannot state how it would fail, so no obligation enters the '
            'system without its verification.'),
}


class Category:
    """The four constitutional classes."""

    #: Class A — the books must add up. Charges, payments, balances,
    #: revenue, tax. A failure here means a number is wrong.
    ACCOUNTING = 'A-ACCOUNTING'

    #: Class B — time must behave. Closed periods, snapshots, business
    #: date, replay determinism. A failure here means a number that was
    #: right has become wrong, or will.
    TEMPORAL = 'B-TEMPORAL'

    #: Class C — the hotel's own rules. Walk-ins, OTA settlement,
    #: checkout prerequisites, orphan events. A failure here means the
    #: system permitted something the business does not.
    DOMAIN = 'C-DOMAIN'

    #: Class D — every financial fact must have an origin. A failure
    #: here means a row exists that nothing explains, which is where
    #: reconciliations go to die.
    REFERENTIAL = 'D-REFERENTIAL'


ALL_CATEGORIES = (Category.ACCOUNTING, Category.TEMPORAL,
                  Category.DOMAIN, Category.REFERENTIAL)


class Severity:
    """How wrong the world is when this invariant fails."""
    CRITICAL = 'CRITICAL'   # money is misstated, or history has changed
    HIGH = 'HIGH'           # a control is absent or a rule is unenforced
    MEDIUM = 'MEDIUM'       # a figure is unattributable or a rule is bent
    LOW = 'LOW'             # hygiene; no financial consequence established


SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.HIGH: 1,
                 Severity.MEDIUM: 2, Severity.LOW: 3}


class Blocking:
    """What a failure stops. Severity is about the world; blocking is
    about the process, and the two are deliberately separate — a LOW
    finding can be certification-blocking (it must be explained before
    the books are signed) without stopping a release."""
    RELEASE = 'RELEASE_BLOCKING'
    CERTIFICATION = 'CERTIFICATION_BLOCKING'
    OPERATIONAL = 'OPERATIONAL_WARNING'
    INFORMATIONAL = 'INFORMATIONAL'


BLOCKING_RANK = {Blocking.RELEASE: 0, Blocking.CERTIFICATION: 1,
                 Blocking.OPERATIONAL: 2, Blocking.INFORMATIONAL: 3}


class Mode:
    """Validation modes — the scopes an invariant can be evaluated over.

    An invariant declares which modes it supports. Declaring the modes is
    not bureaucracy: an invariant that is meaningful over the whole
    database and meaningless for a single reservation will produce
    nonsense if something runs it per reservation, and the declaration is
    what stops that happening.
    """
    SINGLE_RESERVATION = 'SINGLE_RESERVATION'
    BUSINESS_DATE = 'BUSINESS_DATE'
    NIGHT_AUDIT = 'NIGHT_AUDIT'
    ENTIRE_DATABASE = 'ENTIRE_DATABASE'
    HISTORICAL_REPLAY = 'HISTORICAL_REPLAY'
    REGRESSION_DATASET = 'REGRESSION_DATASET'
    GOLDEN_MASTER = 'GOLDEN_MASTER'
    RELEASE_VERIFICATION = 'RELEASE_VERIFICATION'
    CONTINUOUS_MONITORING = 'CONTINUOUS_MONITORING'


ALL_MODES = tuple(v for k, v in vars(Mode).items() if not k.startswith('_')
                  and isinstance(v, str))


class Status:
    """The outcome of evaluating one invariant over one scope."""

    #: The obligation is satisfied over a non-empty population.
    HOLDS = 'HOLDS'

    #: The obligation is broken. This is the finding the engine exists
    #: to produce.
    VIOLATED = 'VIOLATED'

    #: The population is empty, so the invariant was not actually
    #: tested. Never reported as HOLDS: absence of data is not evidence
    #: of correctness (P10).
    VACUOUS = 'VACUOUS'

    #: The invariant does not apply to this scope — declared, not
    #: inferred, so a silently skipped invariant is impossible.
    NOT_APPLICABLE = 'NOT_APPLICABLE'

    #: The evaluation raised. A harness defect or an application defect;
    #: either way, not a pass.
    ERROR = 'ERROR'


NON_PASSING = frozenset({Status.VIOLATED, Status.ERROR})
UNPROVEN = frozenset({Status.VACUOUS, Status.NOT_APPLICABLE})


class Commissioning:
    """Whether this invariant has been shown to be capable of failing."""
    COMMISSIONED = 'COMMISSIONED'
    NOT_COMMISSIONED = 'NOT_COMMISSIONED'
    #: Declared as uncommissionable by data mutation, with a stated
    #: reason. Counted as a gap, never as a pass.
    NOT_SEEDABLE = 'NOT_SEEDABLE'


class Confidence:
    """How much the evidence is worth."""
    #: Every row in the population was examined.
    PROVEN = 'PROVEN'
    #: The population was examined but the violation list was capped;
    #: the count is exact, the listing is not.
    TRUNCATED = 'TRUNCATED'
    #: Only part of the population could be reached.
    PARTIAL = 'PARTIAL'
    #: The population was empty.
    NONE = 'NONE'


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """One broken instance, attributed to a real object."""
    object_type: str            # reservation / payment / folio / date ...
    object_id: str
    expected: str
    observed: str
    variance: str = ''
    #: Rupees at stake in THIS instance, for the financial-impact roll-up.
    amount: str = '0'
    detail: dict = field(default_factory=dict)


@dataclass
class Evidence:
    """What the evaluation looked at and what it found.

    Recorded whether the invariant holds or fails. Evidence only for
    failures would leave "verified" indistinguishable from "never ran"
    (P11): a control that speaks up only when unhappy cannot be audited.
    """
    inputs: dict = field(default_factory=dict)
    expected_result: str = ''
    observed_result: str = ''
    variance: str = ''
    confidence: str = Confidence.NONE
    evidence_files: list = field(default_factory=list)
    affected_objects: list = field(default_factory=list)
    root_cause_candidates: list = field(default_factory=list)
    timestamp: str = ''
    business_date: str = ''
    replay_context: dict = field(default_factory=dict)


@dataclass
class Metering:
    """Cost and safety of one evaluation.

    ``db_writes`` is the important one. It is counted, not assumed: a
    verification engine that wrote to the database it is verifying would
    be both useless and dangerous, and asserting read-only behaviour
    without measuring it is the kind of claim this framework exists to
    reject.
    """
    duration_ms: int = 0
    db_reads: int = 0
    db_writes: int = 0
    memory_peak_kb: int = 0
    rows_examined: int = 0

    @property
    def write_free(self) -> bool:
        return self.db_writes == 0


@dataclass
class InvariantResult:
    """The outcome of evaluating one invariant."""
    invariant_id: str
    title: str
    category: str
    severity: str
    blocking: str
    mode: str
    scope: str
    status: str
    population: int = 0
    violation_count: int = 0
    violations: list = field(default_factory=list)
    evidence: Evidence = field(default_factory=Evidence)
    metering: Metering = field(default_factory=Metering)
    commissioning_status: str = Commissioning.NOT_COMMISSIONED
    error: str = ''

    @property
    def passing(self) -> bool:
        return self.status not in NON_PASSING

    @property
    def financial_impact(self) -> str:
        from decimal import Decimal
        total = Decimal('0')
        for v in self.violations:
            try:
                total += abs(Decimal(str(v.amount)))
            except Exception:                            # noqa: BLE001
                continue
        return str(total)

    @property
    def counts_as_evidence(self) -> bool:
        """A result from an uncommissioned invariant is reported but does
        not contribute to a verdict. An invariant that has never been
        shown to fail cannot be relied on to have passed."""
        return self.commissioning_status == Commissioning.COMMISSIONED


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Invariant:
    """A permanent constitutional obligation of the PMS.

    Every field below is required by the D4 charter. They are not
    documentation of the check — they ARE the invariant; the callable is
    only how it is measured.
    """

    invariant_id: str
    title: str
    category: str
    business_purpose: str
    business_rule: str
    severity: str
    blocking: str
    data_sources: tuple
    canonical_engine: str
    validation_method: str
    evidence_produced: str
    failure_message: str
    likely_root_causes: tuple
    suggested_investigation: tuple
    applicable_releases: str
    applicable_business_dates: str
    commissioning_status: str

    #: The measurement. ``fn(ctx) -> (status, population, violations, evidence_extras)``
    fn: Callable = None

    #: Modes this invariant may be evaluated in.
    modes: tuple = ()

    #: Constitutional principles enforced, e.g. ('P1', 'P7').
    principles: tuple = ()

    #: Surfaces a failure would misstate. Used in the failure report so
    #: the blast radius is stated rather than left to be guessed.
    affected_reports: tuple = ()

    #: SQL that must make this invariant fail, and a one-line reason.
    #: Declared alongside the invariant rather than in the commissioning
    #: module, so that adding an invariant without a way to break it is
    #: an obvious omission at the point of writing.
    negative_seed: tuple = ()
    negative_seed_reason: str = ''

    #: Fault injection at the ENGINE boundary rather than the data
    #: boundary, as ``(dotted_callable, result_key, delta)``.
    #:
    #: Some invariants are internal-consistency checks: they assert that
    #: a canonical engine's own outputs agree with each other. No mutation
    #: of the DATA can break one, because every input moves both sides
    #: together — the only thing that can break it is the code, and Wave 0
    #: forbids changing that. Commissioning such an invariant therefore
    #: means perturbing what the engine RETURNS, inside the commissioning
    #: process only, and requiring detection. Production code is never
    #: touched; the wrapper lives and dies inside one subprocess.
    negative_patch: tuple = ()
    negative_patch_reason: str = ''

    #: Set when the invariant genuinely cannot be broken by either route.
    #: Recorded as a gap, never treated as a pass.
    not_seedable_reason: str = ''

    def supports(self, mode: str) -> bool:
        return mode in self.modes

    def as_dict(self) -> dict:
        from dataclasses import asdict
        out = asdict(self)
        out.pop('fn', None)
        return out
