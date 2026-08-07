"""
Wave 0 — Deliverable D3: Historical Replay Framework.

What D1 and D2 do not cover
---------------------------
D1 measures the *engines* against each other, today. D2 measures the
*surfaces* against a stored master, today. Neither asks the question that
matters most before a financial migration:

    Does the system still tell the same story about days that are
    already closed?

A closed business day is a promise. It was reported to the owner, it
underpins a GST return, and it is the basis on which cash was reconciled.
If a code change quietly moves the number for 27 May, nobody finds out —
D1 compares today's engines to each other and both moved together; D2
compares today's page to today's master and the master was recaptured
after the change.

D3 replays history.

Three independent accounts of every historical business date
------------------------------------------------------------
1. **LEDGER** — a reconstruction from the primary record alone: the
   payment, charge, tax and nightly-rate rows dated to that day, summed
   by this package with plain SQL and no application code. This is the
   only account that cannot move when application code changes, which is
   exactly what makes it the reference.

2. **ENGINE** — the application's own date-parameterised helpers and the
   read-only ``NightAuditService`` report builder, run with the clock
   frozen to noon on the date being replayed.

3. **RECORDED** — what the system itself froze at close time: the
   ``NightAuditLog`` row and its ``snapshot_json``, written by the code
   as it existed on that night.

Comparing 1 against 2 asks *does the application agree with the books*.
Comparing 2 against 3 asks *has the meaning of a closed day changed since
it was closed*. They fail independently and are reported separately.

The retroactivity control
-------------------------
Every past date is additionally replayed a second time with the clock
frozen to the CURRENT business date — that is, asking today about a day
that is already closed. A closed day's figures must not depend on when
the question is asked. Anything that moves between the two passes is an
as-of-now query leaking into a historical report, and it is reported as
``ASAT_DRIFT``.

Hard rules, inherited unchanged from D1 and D2
----------------------------------------------
* Production is opened ``mode=ro``, copied through the SQLite backup API,
  and SHA-256 verified before and after. Nothing here writes.
* No file under ``app/`` is modified, and the application never imports
  this package.
* Determinism is a requirement, not an aspiration: two replays of the
  same dataset produce identical ledgers, and replaying the dates in the
  reverse order must produce the same answer as replaying them forward.
* Nothing is dropped silently. Dates skipped, engine probes that cannot
  be evaluated for a past date, and every masking rule are listed on
  every run with a stated reason.
"""
from __future__ import annotations

__all__ = [
    'ledger', 'engines', 'recorded', 'reconcile', 'replay', 'compare',
    'report', 'timeline',
]
