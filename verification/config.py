"""
PVF configuration — paths, variance policies, severities, verdicts.

Constitutional basis: Phase 2.6 §5 defines the variance policy vocabulary
and the blocking severities. This module is the single place those are
declared; nothing else in the package may invent a policy.
"""
from __future__ import annotations

import os
from decimal import Decimal

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

#: Project root — the directory containing app/, instance/, verification/.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The live production database. OPENED READ-ONLY, ALWAYS. Never targeted
#: by an application instance created by this package.
PRODUCTION_DB = os.path.join(PROJECT_ROOT, 'instance', 'pms.db')

#: Working directory for disposable copies and evidence packs.
PVF_WORK_DIR = os.path.join(PROJECT_ROOT, 'verification', '_work')

#: Where evidence packs are written. Per Phase 2.6 §10, evidence proving
#: the application's correctness should ultimately live OUTSIDE the
#: application. This local path is the staging location; the release
#: process is responsible for exporting it. Documented as a known
#: limitation in the D1 completion report.
EVIDENCE_DIR = os.path.join(PROJECT_ROOT, 'verification', 'evidence')

#: Baseline snapshots for before/after comparison mode.
BASELINE_DIR = os.path.join(PROJECT_ROOT, 'verification', 'baselines')


# ---------------------------------------------------------------------------
# Variance policy — Phase 2.6 §5
# ---------------------------------------------------------------------------

class Policy:
    """How much difference is tolerated between implementations."""

    #: Bit-for-bit equality. Any delta fails. Used where a change must be
    #: provably a no-op.
    EXACT = 'EXACT'

    #: Equality to one rupee. Sub-rupee drift tolerated as rounding.
    RUPEE = 'RUPEE'

    #: Must match a pre-declared expected delta exactly. Used for intended
    #: changes. A declared change that does NOT occur is also a failure.
    DECLARED = 'DECLARED'

    #: Sign and order of magnitude must match; exact value need not.
    #: Reserved for genuinely estimative quantities.
    DIRECTIONAL = 'DIRECTIONAL'

    #: Recorded for context, never blocking. Used for census figures that
    #: give a divergence its denominator.
    INFORMATIONAL = 'INFORMATIONAL'


#: Absolute tolerance per policy, in rupees.
POLICY_TOLERANCE = {
    Policy.EXACT: Decimal('0'),
    Policy.RUPEE: Decimal('1.00'),
    Policy.DECLARED: Decimal('0'),
    Policy.DIRECTIONAL: None,      # handled by sign comparison
    Policy.INFORMATIONAL: None,    # never compared for pass/fail
}


# ---------------------------------------------------------------------------
# Severity — what a divergence does to a release
# ---------------------------------------------------------------------------

class Severity:
    BLOCK = 'BLOCK'    # release cannot proceed
    WARN = 'WARN'      # release proceeds, divergence recorded and reviewed
    INFO = 'INFO'      # context only


#: Ordering for report sorting and for "worst verdict wins" aggregation.
SEVERITY_RANK = {Severity.BLOCK: 0, Severity.WARN: 1, Severity.INFO: 2}


# ---------------------------------------------------------------------------
# Verdict — the outcome of measuring one quantity
# ---------------------------------------------------------------------------

class Verdict:
    #: All implementations of this quantity agree within policy.
    AGREED = 'AGREED'

    #: Implementations disagree beyond policy. This is the finding the
    #: harness exists to produce.
    DIVERGED = 'DIVERGED'

    #: The quantity is declared but its measurement is not yet built.
    #: Reported explicitly so it can never be mistaken for agreement
    #: (Principle 10).
    NOT_IMPLEMENTED = 'NOT_IMPLEMENTED'

    #: Measurement raised. A harness defect or an application defect —
    #: either way, not a pass.
    ERROR = 'ERROR'

    #: Only one implementation exists, so there is nothing to compare.
    #: Still recorded, because the VALUE is baseline evidence even when
    #: no cross-check is possible.
    SINGLE_SOURCE = 'SINGLE_SOURCE'

    #: The measurement ran and the implementations agreed, but the
    #: underlying population is EMPTY — so the agreement proves nothing.
    #: Two implementations of shift cash both returning zero when there
    #: are no shifts have not been shown to agree about anything.
    #:
    #: Principle 10 applied to the harness itself: absence of data is not
    #: evidence of correctness, and a harness that reported this as
    #: AGREED would be exactly the kind of control that cannot fail.
    VACUOUS = 'VACUOUS'


#: Verdicts that must never be treated as success.
NON_PASSING = frozenset({
    Verdict.DIVERGED, Verdict.NOT_IMPLEMENTED, Verdict.ERROR, Verdict.VACUOUS,
})

#: Verdicts that leave the harness un-commissioned but do not, on their
#: own, block a release. A vacuous or unbuilt quantity means "we do not
#: know", which is different from "we found a problem".
INCOMPLETE_VERDICTS = frozenset({Verdict.NOT_IMPLEMENTED, Verdict.VACUOUS})


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

class Mode:
    #: Compute every quantity by every implementation the codebase
    #: currently contains, and compare them against each other. This is
    #: the mode that produces the pre-migration baseline.
    CROSS_IMPLEMENTATION = 'cross-implementation'

    #: Write all measurements to a baseline file for later comparison.
    BASELINE = 'baseline'

    #: Re-measure and diff against a stored baseline. This is the mode
    #: used as a Wave 1+ release gate.
    COMPARE = 'compare'


# ---------------------------------------------------------------------------
# Runtime budget — Phase 2.6 §5 requires the harness to complete in under
# 15 minutes on a production-sized dataset. A harness that takes an hour
# gets skipped under deadline pressure, which is when it matters most.
# ---------------------------------------------------------------------------

RUNTIME_BUDGET_SECONDS = 15 * 60
