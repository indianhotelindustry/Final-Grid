"""
Wave 0 — Deliverable D4: the Financial Invariant Engine.

What this is
------------
The permanent constitutional verification engine for FinalGrid. It
does not fix anything. It answers one question, repeatedly and with
evidence:

    Does the system currently satisfy its constitutional obligations?

An obligation is expressed as an **invariant**: a structured declaration
carrying its business purpose, its rule, its severity, what a failure
costs, where to look when it fails, and — crucially — how it could be
made to fail. The measurement function is the smallest part of it.

Why the declaration comes first
-------------------------------
The fields that are hard to write are the ones that expose an invariant
nobody has thought through. "Likely root causes" and "suggested
investigation" cannot be filled in convincingly for a rule whose purpose
is vague, and registration refuses an invariant that leaves them empty.
The result is that the registry is a statement of what the system owes,
not a bag of assertions.

The commissioning gate
----------------------
Under P9 a control that cannot fail is not a control. Every invariant
must therefore declare either a ``negative_seed`` — SQL that makes it
fail — or a ``negative_patch``, which perturbs a canonical engine's
output inside the commissioning process only. Registration rejects an
invariant with neither. Until commissioning has actually demonstrated the
failure, the invariant's result is reported but excluded from any
verdict: an invariant that has never been shown to fail cannot be relied
upon to have passed.

Layout
------
``model``      the Invariant, Evidence, Violation and Metering objects,
               and the vocabularies: Category, Severity, Blocking, Mode,
               Status, Confidence, Commissioning.
``registry``   registration, validation, selection, and the matrices.
``context``    the evaluation context: a read-only connection, the
               application, the scope, and the metering.
``engine``     the execution pipeline, determinism and order-independence
               proofs, zero-write enforcement.
``rules_a``    Class A — accounting.
``rules_b``    Class B — temporal.
``rules_c``    Class C — domain.
``rules_d``    Class D — referential.
``history``    historical replay: was it true then, is it true now, and
               where did it first stop being true.
``commission`` per-invariant commissioning with fault injection.
``report``     evidence packs, matrices and failure reports.

Extension point
---------------
A new invariant is one ``@invariant(...)`` declaration in a rules module.
Nothing else changes. That is the entire mechanism, and it is deliberately
the only one — per the standing rule that any future financial feature,
report, night-audit change or accounting change must register its
invariants before implementation is permitted.

Hard rules, inherited unchanged from D1–D3
------------------------------------------
* Production is opened ``mode=ro``, copied through the SQLite backup API,
  and SHA-256 verified before and after.
* No file under ``app/`` is modified, and the application never imports
  this package.
* Database writes during an invariant run are **counted**, not assumed:
  a single write fails the run outright, whatever the invariants reported.
"""
from __future__ import annotations

__all__ = ['model', 'registry', 'context', 'engine', 'history',
           'commission', 'report', 'helpers',
           'rules_a', 'rules_b', 'rules_c', 'rules_d']
