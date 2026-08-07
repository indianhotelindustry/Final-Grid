"""
Wave 0 — Deliverable D6: the Enterprise Regression Dataset Platform.

What this is
------------
D4 made invariants first-class. D5 made faults first-class. This
deliverable does the same for the **data**, because D4's own findings
proved the need: four invariants are VACUOUS on live production data, and
two D1 quantities with them. Each is commissioned. Not one has ever been
exercised, because the hotel has never produced a row of that shape.

A commissioned rule over an empty population proves nothing (P10). The
only way to close that is data declared as rigorously as the rules it
exercises.

Why a dataset is a declaration
------------------------------
Every verification programme eventually grows a ``fixtures/`` directory: a
handful of SQL files nobody can explain, which pass until the day they do
not, and which nobody dares delete because nobody knows what they cover.
A dataset here instead declares, up front, its business narrative, its
timeline, its provenance, what the money should come to, which invariants
should hold or be violated, which should stop being VACUOUS, what a replay
should reconcile to, what parity should say, and which faults injected
into it should still be detected.

The rows are the smallest part of it.

The discrimination gate
-----------------------
Under P9 a control that cannot fail is not a control. A dataset whose
expectations hold no matter what the system does is not a regression
dataset; it is decoration. Commissioning therefore perturbs every dataset
and requires the declared expectations to break. A dataset that survives
its own perturbation is reported NOT COMMISSIONED and excluded from
certification.

Build strategy
--------------
Datasets are built by **stripping a copy of production and rebuilding the
transactional layer**, never by synthesising a schema. The schema is then
real by construction — it *is* the production schema, migrated exactly as
production is — and the master data is the hotel's own configuration.
``schema.py`` records why: D5's ``FLT-A10`` was never injected because the
real ``reservations`` table has five NOT NULL money columns a hand-written
statement did not know about. A synthetic schema would have accepted it
and reported a clean pass over a row that could never exist.

Layout
------
``model``        the Dataset object, Event, Provenance, Expectations, and
                 the vocabularies: Origin, Purpose, Layer, Status,
                 Commissioning, Certification, Mode.
``registry``     registration, validation, selection and the matrices.
``schema``       table classification and the strip order, verified
                 against the live schema rather than assumed.
``builder``      strip, insert, set business date, content hash, build,
                 discard, perturb.
``financials``   the declared probes and the measurement.
``evaluate``     run the declared layers and compare with the declaration.
``commission``   the discrimination gate.
``report``       evidence packs, matrices and gap reports.
``datasets_core``        baseline narratives — an ordinary hotel.
``datasets_activation``  datasets that exist to activate a control.

Extension point
---------------
A new dataset is one ``@dataset(...)`` declaration in a ``datasets_*``
module. Nothing else changes. Registration refuses a declaration with an
empty required field, no timeline, no perturbation, no expectation, or a
perturbation that claims to break something nothing is measuring.

Hard rules, inherited unchanged from D1–D5
------------------------------------------
* No file under ``app/`` is modified, and the application never imports
  this package.
* Production is opened ``mode=ro``, copied through the SQLite backup API,
  and SHA-256 verified before and after every build.
* A dataset is materialised into its own file. Perturbation is applied to
  that file, never to production and never to a backup.
* A run that cannot prove its own isolation reports UNVERIFIED, whatever
  the datasets reported.
"""
from __future__ import annotations

__all__ = ['model', 'registry', 'schema', 'builder', 'financials',
           'evaluate', 'commission', 'report',
           'datasets_core', 'datasets_activation']
