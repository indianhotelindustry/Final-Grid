"""
Wave 0 — Deliverable D5: the Fault Injection Framework.

What this is
------------
D1 to D4 each built a verification layer, and each proved itself with its
own seeded faults. Every one of those proofs is inward-facing: it shows
that the layer detects the defects that layer was written to detect. None
of them can answer the question the platform actually exists for:

    When this defect occurs in production, which parts of the
    verification framework notice, which stay silent, and does the one
    that notices name the right cause?

D5 answers it. A fault is declared once, injected into a private
disposable copy of production, and **every** layer is swept — including
the layers expected to stay silent, because a framework where everything
moves for every fault has detected nothing; it has only proved it is
sensitive to change.

The output that matters
-----------------------
Not the passes. The **MISSED** results — a declared layer that stayed
silent — are the verification gaps this deliverable exists to find, and
they are reported as findings rather than smoothed away.

Three results are kept apart on purpose:

``ATTRIBUTED``   the declared layer reacted at the declared target.
``UNATTRIBUTED`` the layer felt a disturbance but did not identify it.
``MISSED``       the declared layer stayed silent. The finding.

and two more that make attribution possible at all:

``UNEXPECTED``       an undeclared layer moved. Blast radius, never a pass.
``CORRECTLY_SILENT`` an undeclared layer stayed silent. A real result.

Isolation
---------
Inherited unchanged from D1 and verified rather than claimed. Production
is opened ``mode=ro``, copied through the SQLite backup API, and SHA-256
verified **after every single fault** rather than once per run, so a
breach can be attributed to the injection that caused it. Each fault gets
a private copy derived from a pristine baseline — never from the previous
fault's copy — and the baseline is re-hashed after every injection.

A platform that injects faults into a live hotel's financial system on
the strength of an assertion is not a platform; it is an incident waiting
for a bad afternoon.

Layout
------
``model``      the Fault object and the vocabularies: Category, Layer,
               TargetLayer, Method, Severity, Detection, Commissioning,
               Mode; plus LayerOutcome, FaultEvidence and FaultResult.
``registry``   registration, validation, selection and the matrices.
``isolation``  the arena: pristine baseline, per-fault copies, verified
               cleanup, and the evidence for each.
``injection``  the five injection methods and the zero-change refusal.
``detectors``  D1-D4 wrapped as uniform probes returning a signal.
``pipeline``   the execution pipeline and the five-outcome classifier.
``faults_a``   Class A — business faults a hotel can genuinely commit.
``faults_b``   Class B — malformed records.
``faults_c``   Class C — correct data, wrong code.
``faults_d``   Class D — operational and environmental.
``commission`` per-fault commissioning and platform self-verification.
``report``     evidence packs, matrices and gap reports.

Extension point
---------------
A new fault is one ``@fault(...)`` declaration in a ``faults_*`` module.
No pipeline change, no dispatch table, no classifier edit. Registration
refuses a declaration that is incomplete, and in particular refuses one
that expects no layer to detect it without saying why — a fault nothing
detects is either a mistake or a verification gap, and the platform will
not guess which.

Hard rules, inherited unchanged from D1–D4
------------------------------------------
* No file under ``app/`` is modified. Class C faults are wrappers
  installed inside a throwaway probe subprocess and die with it.
* The application never imports this package.
* Faults never touch production, a backup, or any real artefact. FILE
  faults corrupt a copy taken into the arena first.
* A run that cannot prove its own isolation reports UNVERIFIED, whatever
  the faults reported.
"""
from __future__ import annotations

__all__ = ['model', 'registry', 'isolation', 'injection', 'detectors',
           'pipeline', 'commission', 'report',
           'faults_a', 'faults_b', 'faults_c', 'faults_d']
