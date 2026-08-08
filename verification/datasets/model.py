"""
The dataset object, its provenance, and the evidence a dataset produces.

Why a dataset is a declaration
------------------------------
Every verification framework eventually grows a ``fixtures/`` directory:
a handful of SQL files nobody can explain, which pass until the day they
do not, and which nobody dares delete because nobody knows what they
cover. That directory is where verification programmes go to die.

D4 made invariants first-class. D5 made faults first-class. This
deliverable does the same for the data, because D4's own findings proved
the need: four invariants are VACUOUS on live production data —
overpayment recording, corporate credit backing, correction/reversal
traceability and void/credit-note traceability. Each is commissioned. Not
one has ever been exercised, because the hotel has never produced a row
of that shape.

A commissioned rule over an empty population proves nothing (P10). The
only way to close that is data that is *declared* as rigorously as the
rules it exercises.

So a dataset declares, up front:

* the business narrative — what happened at this hotel, in prose a
  manager would recognise;
* the timeline — the events that narrative consists of;
* its provenance — synthetic, derived, or anonymised, and from what;
* what the money should come to;
* which invariants should hold, which should be violated, and — crucially
  — which should stop being VACUOUS;
* what a replay of it should reconcile to;
* what the parity harness should say;
* which faults injected into it should be detected.

The rows are the smallest part of it. As with invariants and faults, the
fields that are hard to write are the ones that expose a dataset nobody
has thought through: a fixture cannot state what it proves, and this
registry refuses one that does not.

The discrimination gate
-----------------------
Under P9 a control that cannot fail is not a control. A dataset whose
expectations hold no matter what the system does is not a regression
dataset; it is decoration. Commissioning therefore perturbs each dataset
and requires the declared expectations to break. A dataset that survives
its own perturbation is reported as NOT COMMISSIONED and excluded from
certification.

Constitutional basis
--------------------
P9 (a control must be capable of failing), P10 (absence of evidence is
not evidence of correctness — the principle that makes this deliverable
necessary), P11 (observable correctness), P13 (verification before
implementation) and P14 (every financial object has provenance — applied
here to the data itself).
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

class Origin:
    """Where a dataset's data came from. Element 8 of the charter."""

    #: Written by hand from a declared narrative. Nothing derives from a
    #: real guest. The default and the only origin that can be published.
    SYNTHETIC = 'SYNTHETIC'

    #: Built by transforming production rows. Carries real business shape
    #: and therefore real disclosure risk; must state its transformation.
    DERIVED_FROM_PRODUCTION = 'DERIVED_FROM_PRODUCTION'

    #: Derived, then anonymised by a declared procedure. Still not
    #: publishable without review: anonymisation is a claim, not a fact,
    #: and this registry does not verify it.
    ANONYMISED_PRODUCTION = 'ANONYMISED_PRODUCTION'


ALL_ORIGINS = (Origin.SYNTHETIC, Origin.DERIVED_FROM_PRODUCTION,
               Origin.ANONYMISED_PRODUCTION)


class Purpose:
    """What a dataset exists to do."""
    #: Give a VACUOUS invariant a population. The reason D6 exists.
    ACTIVATE_INVARIANT = 'ACTIVATE_INVARIANT'
    #: A clean hotel where everything should hold. The positive control.
    BASELINE = 'BASELINE'
    #: A known-bad hotel where a specific rule must be violated.
    NEGATIVE = 'NEGATIVE'
    #: An empty or degenerate population, to prove the framework reports
    #: VACUOUS rather than PASS.
    DEGENERATE = 'DEGENERATE'
    #: A shape the framework has never seen, to find out what it says.
    EXPLORATORY = 'EXPLORATORY'


ALL_PURPOSES = tuple(v for k, v in vars(Purpose).items()
                     if not k.startswith('_') and isinstance(v, str))


class Layer:
    """The verification layers a dataset declares outcomes for."""
    D1_PARITY = 'D1_PARITY'
    D2_GOLDEN = 'D2_GOLDEN'
    D3_REPLAY = 'D3_REPLAY'
    D4_INVARIANTS = 'D4_INVARIANTS'
    D5_FAULTS = 'D5_FAULTS'


ALL_LAYERS = (Layer.D1_PARITY, Layer.D2_GOLDEN, Layer.D3_REPLAY,
              Layer.D4_INVARIANTS, Layer.D5_FAULTS)


class Status:
    """The outcome of comparing one declared expectation to reality."""
    #: Declared and observed agree.
    MET = 'MET'
    #: Declared and observed disagree. Either the system changed or the
    #: declaration was wrong; the platform does not guess which.
    UNMET = 'UNMET'
    #: The expectation names something that does not exist.
    UNKNOWN_TARGET = 'UNKNOWN_TARGET'
    #: The layer could not be run against this dataset.
    NOT_RUN = 'NOT_RUN'
    #: The comparison raised.
    ERROR = 'ERROR'


class Commissioning:
    COMMISSIONED = 'COMMISSIONED'
    NOT_COMMISSIONED = 'NOT_COMMISSIONED'
    #: Registered so the taxonomy is complete, but the dataset cannot be
    #: materialised on this schema. Reported as a gap, never as a pass.
    NOT_MATERIALISABLE = 'NOT_MATERIALISABLE'


class Certification:
    CERTIFIED = 'CERTIFIED'
    UNCERTIFIED = 'UNCERTIFIED'
    #: Certified once, but the content hash has moved since. The
    #: certificate names a dataset that no longer exists.
    STALE = 'STALE'


class Mode:
    """Execution modes a dataset may participate in."""
    REGRESSION = 'REGRESSION'
    COMMISSIONING = 'COMMISSIONING'
    CERTIFICATION = 'CERTIFICATION'
    RELEASE_VERIFICATION = 'RELEASE_VERIFICATION'
    CONTINUOUS_VERIFICATION = 'CONTINUOUS_VERIFICATION'
    INVARIANT_ACTIVATION = 'INVARIANT_ACTIVATION'


ALL_MODES = tuple(v for k, v in vars(Mode).items()
                  if not k.startswith('_') and isinstance(v, str))


# ---------------------------------------------------------------------------
# The narrative
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    """One thing that happened, in business language.

    The timeline is not documentation of the rows — it is the *reason*
    the rows exist. Every declared expectation must trace back to an
    event, and commissioning checks that it does. An expectation with no
    narrative behind it is an assertion somebody tuned until it passed.
    """
    date: str                  # ISO business date
    description: str           # what a manager would say happened
    tables: tuple = ()         # tables this event writes
    amount: str = ''           # the money involved, if any, as a string


# ---------------------------------------------------------------------------
# Provenance — charter element 8
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    """Where this data came from and what may be done with it."""
    origin: str
    author: str
    created: str                     # ISO date, declared not stamped
    derivation: str                  # how it was produced, in prose
    contains_real_guest_data: bool
    disclosure: str                  # what may be shared, and with whom
    base_dataset: str = ''           # for derived datasets
    rationale: str = ''              # why this origin rather than another


# ---------------------------------------------------------------------------
# Expectations — charter elements 3 to 7
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Expectations:
    """What this dataset says every layer should conclude.

    Kept as one object rather than five loose fields so that a dataset
    declaring nothing for a layer is visible as a deliberate empty
    mapping rather than as an omission nobody noticed.
    """

    #: Charter element 3. Name -> declared money value, as a string so
    #: the declaration is exact and never a float.
    financial: dict = field(default_factory=dict)

    #: Charter element 4. Invariant id -> expected Status value from
    #: ``verification.invariants.model.Status``. The point of the whole
    #: deliverable: an invariant declared HOLDS or VIOLATED here is one
    #: that is no longer VACUOUS.
    invariants: dict = field(default_factory=dict)

    #: Charter element 5. Reconciliation id -> expected status, plus the
    #: reserved key ``'ledger_stable'``.
    replay: dict = field(default_factory=dict)

    #: Charter element 6. Quantity id -> expected verdict.
    parity: dict = field(default_factory=dict)

    #: Charter element 7. Fault id -> whether the fault should still be
    #: detected when injected into THIS dataset. A fault that is detected
    #: on production data and missed here has found a population the
    #: framework is blind on.
    faults: dict = field(default_factory=dict)

    def declared_layers(self) -> tuple:
        out = []
        if self.parity:
            out.append(Layer.D1_PARITY)
        if self.replay:
            out.append(Layer.D3_REPLAY)
        if self.invariants:
            out.append(Layer.D4_INVARIANTS)
        if self.faults:
            out.append(Layer.D5_FAULTS)
        return tuple(out)

    def total(self) -> int:
        return (len(self.financial) + len(self.invariants) +
                len(self.replay) + len(self.parity) + len(self.faults))


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class ExpectationOutcome:
    """One declared expectation, compared with what actually happened."""
    element: str               # 'financial' | 'invariants' | ...
    target: str
    expected: str
    observed: str = ''
    status: str = Status.NOT_RUN
    detail: str = ''

    @property
    def met(self) -> bool:
        return self.status == Status.MET


@dataclass
class Materialisation:
    """What building the dataset actually produced."""
    db_path: str = ''
    content_hash: str = ''
    rows_inserted: int = 0
    rows_removed: int = 0
    tables_touched: tuple = ()
    business_date: str = ''
    duration_ms: int = 0
    production_unchanged: bool = False
    error: str = ''

    @property
    def ok(self) -> bool:
        return bool(self.db_path) and not self.error


@dataclass
class DatasetResult:
    """Everything one dataset evaluation leaves behind."""
    dataset_id: str
    version: str
    title: str
    materialisation: Materialisation = field(default_factory=Materialisation)
    outcomes: list = field(default_factory=list)
    layers_run: tuple = ()
    activated_invariants: list = field(default_factory=list)
    still_vacuous: list = field(default_factory=list)
    commissioning_status: str = Commissioning.NOT_COMMISSIONED
    certification_status: str = Certification.UNCERTIFIED
    duration_seconds: float = 0.0
    error: str = ''

    @property
    def unmet(self) -> list:
        return [o for o in self.outcomes if o.status == Status.UNMET]

    @property
    def met(self) -> list:
        return [o for o in self.outcomes if o.met]

    @property
    def not_run(self) -> list:
        return [o for o in self.outcomes if o.status == Status.NOT_RUN]

    @property
    def verdict(self) -> str:
        if self.error or not self.materialisation.ok:
            return 'ERROR'
        if any(o.status in (Status.UNKNOWN_TARGET, Status.ERROR)
               for o in self.outcomes):
            return 'ERROR'
        if self.unmet:
            return 'FAIL'
        if not self.outcomes:
            return 'INCOMPLETE'
        # An expectation that could not be measured is not an expectation
        # that was met. Treating NOT_RUN as a pass would let a dataset
        # report PASS on a layer that never ran — silence as evidence,
        # which is the one thing P10 forbids.
        if self.not_run or self.still_vacuous:
            return 'INCOMPLETE'
        return 'PASS'


# ---------------------------------------------------------------------------
# The dataset
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dataset:
    """A regression dataset, declared rather than fixtured.

    Every field is required by the D6 charter. The ``rows`` are how the
    narrative is realised; they are not the dataset.
    """

    dataset_id: str
    version: str                      # semantic, e.g. '1.0'
    title: str
    purpose: str                      # Purpose value
    business_narrative: str           # charter element 2
    timeline: tuple                   # tuple[Event]
    provenance: Provenance            # charter element 8
    expectations: Expectations        # charter elements 3-7

    #: The rows, as ``(table, (column, ...), ((value, ...), ...))``.
    #: Applied in declaration order on top of a stripped baseline, so a
    #: parent row is simply declared before its children.
    rows: tuple

    #: The business date the dataset represents. Everything date-scoped
    #: is evaluated as at this date.
    business_date: str

    #: Invariants this dataset is built to lift out of VACUOUS. Checked
    #: against reality by commissioning: a dataset that claims to
    #: activate an invariant and leaves it VACUOUS has not done its job.
    activates_invariants: tuple = ()

    #: How commissioning perturbs this dataset to prove its expectations
    #: can fail. SQL, applied to a throwaway copy. Required — a dataset
    #: with no perturbation cannot be shown to discriminate.
    perturbation: tuple = ()
    perturbation_breaks: tuple = ()   # expectation targets it must break

    #: The coverage movement this dataset intends, against production.
    #: Keys are ``coverage.EXPECTATION_KEYS``; values are tuples of
    #: endpoint or invariant ids.
    #:
    #: Separate from ``expectations`` because it is a different kind of
    #: claim. ``expectations`` says what each layer should CONCLUDE about
    #: this data; this says what the dataset can EXERCISE at all. A
    #: dataset can meet every expectation it declares while silently
    #: covering less than production did — which is exactly what
    #: ``DS-ACT-INHOUSE`` did in its first version, resolving three
    #: golden-master surfaces and un-resolving four.
    #:
    #: Empty means "no movement declared", and then any movement at all is
    #: reported as unexpected. That is the intended default for a dataset
    #: nobody has thought about yet, not a way to opt out.
    coverage_expectation: dict = field(default_factory=dict)

    commissioning_status: str = Commissioning.NOT_COMMISSIONED
    certification_status: str = Certification.UNCERTIFIED

    #: Recorded at certification. A dataset whose content hash has moved
    #: since its certificate was issued is STALE, not certified.
    certified_content_hash: str = ''

    applicable_releases: str = 'all'
    principles: tuple = ()
    modes: tuple = ()

    #: Set when the dataset cannot be built on the current schema.
    not_materialisable_reason: str = ''
    covered_by_deliverable: str = ''

    @property
    def key(self) -> str:
        return f'{self.dataset_id}@{self.version}'

    def expects_layer(self, layer: str) -> bool:
        return layer in self.expectations.declared_layers()

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)
