"""
The fault object, the layer vocabulary, and the evidence a challenge
produces.

Why a fault is a declaration
----------------------------
D1, D2, D3 and D4 each carry their own seeded-fault suite, and each was
written to prove that *that* layer works. None of them can answer the
question this platform exists for:

    When this defect occurs in production, which parts of the
    verification framework notice, which stay silent, and does the one
    that notices name the right cause?

Answering it means a fault has to be a first-class object with a
*declared expectation per layer*, not a test case buried inside one
deliverable. A fault that merely says "something should move" cannot
distinguish a framework that detected the defect from a framework that
is simply noisy.

So every fault declares, up front:

* what business rule it challenges;
* which verification layers are expected to react;
* which specific invariants, quantities or reconciliations should fire;
* what should happen to a replay, to parity, and to certification;
* how it is injected and how it is cleaned up.

The platform then injects it, sweeps every layer, and classifies the
result against the declaration. Three outcomes matter and they are kept
apart on purpose:

``DETECTED``      the declared layer reacted — the control works.
``MISSED``        the declared layer stayed silent — a verification gap,
                  and the most valuable output this platform produces.
``UNEXPECTED``    an undeclared layer reacted. Informative, not a pass:
                  a framework where everything moves for every fault
                  cannot attribute anything.

Constitutional basis
--------------------
P6 (evidence must be capable of falsifying a change), P9 (a control must
be capable of failure), P11 (observable correctness), P13 (verification
before implementation) and P14 (every financial object has provenance).
The platform is commissioned under the same principles it applies: a
fault that has never demonstrated detection does not participate in
certification.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

class Category:
    """The four fault classes."""

    #: Class A — something a hotel can genuinely do wrong at the desk or
    #: in the back office. The fault is legal SQL and plausible data.
    BUSINESS = 'A-BUSINESS'

    #: Class B — the record itself is malformed: a dangling reference, a
    #: missing row, a date outside its period.
    DATA = 'B-DATA'

    #: Class C — the data is correct and the code is wrong. Injected at
    #: the engine boundary, because no data mutation can express "this
    #: function now double-counts".
    ENGINE = 'C-ENGINE'

    #: Class D — nothing about the money is wrong; the environment is.
    #: Clock drift, a corrupted snapshot, a configuration that does not
    #: match the one the figures were produced under.
    OPERATIONAL = 'D-OPERATIONAL'


ALL_CATEGORIES = (Category.BUSINESS, Category.DATA, Category.ENGINE,
                  Category.OPERATIONAL)


class Layer:
    """The verification layers a fault can be challenged against."""
    D1_PARITY = 'D1_PARITY'          # cross-implementation parity harness
    D2_GOLDEN = 'D2_GOLDEN'          # rendered-surface golden masters
    D3_REPLAY = 'D3_REPLAY'          # historical replay and reconciliation
    D4_INVARIANTS = 'D4_INVARIANTS'  # the financial invariant engine


ALL_LAYERS = (Layer.D1_PARITY, Layer.D2_GOLDEN, Layer.D3_REPLAY,
              Layer.D4_INVARIANTS)

#: Wall-clock cost of one probe, measured on the reference dataset. Used
#: to decide what a default sweep runs; stated rather than hidden,
#: because a layer skipped for cost is a layer that reported nothing.
LAYER_COST_MS = {
    Layer.D1_PARITY: 2500,
    Layer.D2_GOLDEN: 6700,
    Layer.D3_REPLAY: 3000,
    Layer.D4_INVARIANTS: 3600,
}


class TargetLayer:
    """Where in the stack the fault is introduced."""
    DATA = 'DATA'                  # rows in the database
    ENGINE = 'ENGINE'              # a canonical function's behaviour
    CLOCK = 'CLOCK'                # the temporal basis of a run
    CONFIGURATION = 'CONFIGURATION'  # settings the engines read
    ENVIRONMENT = 'ENVIRONMENT'    # process environment
    ARTEFACT = 'ARTEFACT'          # files: snapshots, backups


class Method:
    """How a fault is injected."""
    SQL = 'SQL'                    # statements against a disposable copy
    ENGINE_PATCH = 'ENGINE_PATCH'  # wrap a callable inside one subprocess
    CLOCK_SHIFT = 'CLOCK_SHIFT'    # move the frozen instant
    ENV = 'ENV'                    # set process environment
    FILE = 'FILE'                  # mutate a file on disk (never in place)


class Severity:
    CRITICAL = 'CRITICAL'
    HIGH = 'HIGH'
    MEDIUM = 'MEDIUM'
    LOW = 'LOW'


SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.HIGH: 1,
                 Severity.MEDIUM: 2, Severity.LOW: 3}


class Detection:
    """What a layer did when the fault was present."""
    #: The layer's signal moved, and the declared target fired.
    ATTRIBUTED = 'ATTRIBUTED'
    #: The layer's signal moved, but not where the declaration said.
    #: The framework noticed something; it did not identify what.
    UNATTRIBUTED = 'UNATTRIBUTED'
    #: The layer stayed silent where it was expected to react. A gap.
    MISSED = 'MISSED'
    #: The layer reacted where nothing was expected. Recorded as blast
    #: radius, never counted as success.
    UNEXPECTED = 'UNEXPECTED'
    #: Expected silence, got silence. This is a real result: it is what
    #: makes attribution possible.
    CORRECTLY_SILENT = 'CORRECTLY_SILENT'
    #: The probe could not run.
    NOT_RUN = 'NOT_RUN'
    #: The probe raised.
    ERROR = 'ERROR'


class Commissioning:
    COMMISSIONED = 'COMMISSIONED'
    NOT_COMMISSIONED = 'NOT_COMMISSIONED'
    #: Registered so the taxonomy is complete, but no layer of the
    #: current framework can detect it. Reported as a gap against the
    #: deliverable that will cover it, never as a pass.
    UNCOVERED = 'UNCOVERED'


class Mode:
    """Execution modes."""
    SINGLE_FAULT = 'SINGLE_FAULT'
    BATCH = 'BATCH'
    HISTORICAL_REPLAY = 'HISTORICAL_REPLAY'
    REGRESSION_DATASET = 'REGRESSION_DATASET'
    GOLDEN_MASTER = 'GOLDEN_MASTER'
    INVARIANT_VALIDATION = 'INVARIANT_VALIDATION'
    PARITY_HARNESS = 'PARITY_HARNESS'
    CONTINUOUS_VERIFICATION = 'CONTINUOUS_VERIFICATION'
    RELEASE_VERIFICATION = 'RELEASE_VERIFICATION'
    COMMISSIONING = 'COMMISSIONING'


ALL_MODES = tuple(v for k, v in vars(Mode).items()
                  if not k.startswith('_') and isinstance(v, str))


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class LayerOutcome:
    """What one verification layer did about one fault."""
    layer: str
    expected: bool = False
    ran: bool = False
    signal_moved: bool = False
    detection: str = Detection.NOT_RUN
    attributed_targets: list = field(default_factory=list)
    missing_targets: list = field(default_factory=list)
    moved_keys: list = field(default_factory=list)
    duration_ms: int = 0
    error: str = ''

    @property
    def satisfied(self) -> bool:
        """Did this layer do what the fault declared it would?"""
        if self.expected:
            return self.detection == Detection.ATTRIBUTED
        return self.detection in (Detection.CORRECTLY_SILENT,
                                  Detection.UNEXPECTED)


@dataclass
class FaultEvidence:
    """Everything a single challenge leaves behind."""
    injection: dict = field(default_factory=dict)
    expected_detection: list = field(default_factory=list)
    actual_detection: list = field(default_factory=list)
    detection_time_ms: int = 0
    detected_by: list = field(default_factory=list)
    missed_by: list = field(default_factory=list)
    affected_invariants: list = field(default_factory=list)
    affected_reports: list = field(default_factory=list)
    affected_replays: list = field(default_factory=list)
    affected_parity_checks: list = field(default_factory=list)
    certification_impact: str = ''
    root_cause_candidates: list = field(default_factory=list)
    evidence_files: list = field(default_factory=list)
    execution_context: dict = field(default_factory=dict)
    business_date: str = ''
    replay_context: dict = field(default_factory=dict)
    timestamp: str = ''


@dataclass
class Metering:
    duration_ms: int = 0
    memory_peak_kb: int = 0
    db_reads: int = 0
    db_writes: int = 0
    layers_run: int = 0

    @property
    def write_free(self) -> bool:
        return self.db_writes == 0


@dataclass
class FaultResult:
    """The outcome of challenging the framework with one fault."""
    fault_id: str
    title: str
    category: str
    severity: str
    method: str
    rows_changed: int = 0
    layers: list = field(default_factory=list)
    evidence: FaultEvidence = field(default_factory=FaultEvidence)
    metering: Metering = field(default_factory=Metering)
    cleanup_verified: bool = False
    isolation_verified: bool = False
    injection_verified: bool = False
    commissioning_status: str = Commissioning.NOT_COMMISSIONED
    error: str = ''

    @property
    def detected(self) -> bool:
        """Detected means an EXPECTED layer attributed it.

        Deliberately not "some layer moved". A framework in which
        everything moves for every fault has detected nothing; it has
        only proved it is sensitive to change.
        """
        expected = [o for o in self.layers if o.expected]
        return bool(expected) and any(
            o.detection == Detection.ATTRIBUTED for o in expected)

    @property
    def fully_satisfied(self) -> bool:
        return bool(self.layers) and all(o.satisfied for o in self.layers)

    @property
    def gaps(self) -> list:
        return [o.layer for o in self.layers
                if o.expected and o.detection != Detection.ATTRIBUTED]

    @property
    def blast_radius(self) -> list:
        return [o.layer for o in self.layers
                if not o.expected and o.detection == Detection.UNEXPECTED]


# ---------------------------------------------------------------------------
# The fault
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Fault:
    """A realistic defect the verification framework must be able to see.

    Every field below is required by the D5 charter. They are not
    documentation of the injection — they ARE the fault; the SQL or the
    patch is only how it is realised.
    """

    fault_id: str
    title: str
    category: str
    purpose: str
    business_rule_challenged: str
    injection_method: str
    target_objects: tuple
    target_layer: str
    expected_detection: tuple          # Layer values
    expected_invariants: tuple         # D4 invariant ids
    expected_replay_behaviour: str
    expected_parity_behaviour: str
    expected_certification_impact: str
    expected_severity: str
    expected_evidence: str
    cleanup_strategy: str
    repeatability: str
    determinism: str
    commissioning_status: str
    applicable_releases: str
    applicable_business_dates: str

    #: Injection payload. Its shape depends on ``injection_method``:
    #:   SQL           tuple of statements
    #:   ENGINE_PATCH  tuple of (dotted_callable, key, op, value)
    #:   CLOCK_SHIFT   int days
    #:   ENV           tuple of (name, value)
    #:   FILE          tuple of (relative_path, mode)
    payload: tuple = ()

    #: Specific D1 quantities / D3 reconciliations expected to move. Used
    #: for attribution: a layer that moved somewhere else is
    #: UNATTRIBUTED, not detected.
    expected_quantities: tuple = ()
    expected_reconciliations: tuple = ()

    #: Reports a real occurrence of this fault would misstate.
    affected_reports: tuple = ()

    #: Where to start looking when this is seen in production.
    root_cause_candidates: tuple = ()

    #: Constitutional principles engaged.
    principles: tuple = ()

    #: Modes this fault may be exercised in.
    modes: tuple = ()

    #: Set when no layer of the current framework can detect the fault.
    #: Names the deliverable that will, so the gap is tracked rather than
    #: forgotten.
    uncovered_reason: str = ''
    covered_by_deliverable: str = ''

    def expects(self, layer: str) -> bool:
        return layer in self.expected_detection

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)
