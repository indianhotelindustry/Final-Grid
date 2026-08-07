"""
Activation datasets — data that exists to give a silent control a voice.

**This module is deliberately empty. D6 Step 1 is infrastructure only.**
See ``datasets_core`` for why an empty module is preferable to no module.

What belongs here
-----------------
One dataset per empty population. These are the reason D6 exists: each
declares ``activates_invariants``, and commissioning checks the claim
against reality — a dataset that says it activates an invariant and leaves
it VACUOUS has not done its job.

The populations to close, measured against production on 2026-08-07:

===========================  =====  ====================================
Target                       Layer  Evidence it is empty
===========================  =====  ====================================
``INV-A06`` overpayment      D4     0 reservations overpaid by > Rs.1
``INV-C06`` corporate credit D4     ``corporate_bookings`` = 0
``INV-D02`` corrections      D4     no correction or reversal rows
``INV-D05`` voids / notes    D4     ``credit_notes`` = 0, ``void_requests`` = 0
``Q11`` refunds vs voids     D1     VACUOUS
``Q21`` shift cash           D1     no shifts
4 golden master surfaces     D2     UNRESOLVED — no checked-in reservation
===========================  =====  ====================================

Planned, cheapest first::

    DS-ACT-INHOUSE      a checked-in reservation. Resolves D2's four
                        UNRESOLVED surfaces and costs almost nothing.
    DS-ACT-OVERPAY      a reservation overpaid by more than Rs.1.
    DS-ACT-CORPCREDIT   a corporate booking with company credit behind it.
    DS-ACT-CORRECTION   a correction and a reversal, each naming what it
                        corrects.
    DS-ACT-VOIDCN       a void request and a credit note. Also lifts Q11.
    DS-ACT-SHIFT        a shift with cash counted. Lifts Q21.

Two things to get right
-----------------------
**The threshold, not the table.** ``INV-A06``'s population is reservations
whose canonical ``settlement_balance`` is below ``-1.00``. It is *not* the
``overpayment_logs`` table. Inserting a log row would leave the invariant
VACUOUS and the activation claim would fail commissioning — correctly.
``DS-ACT-OVERPAY`` must produce a reservation that is genuinely overpaid
by more than one rupee. See ``D5_5_CONSISTENCY_AUDIT.md`` Q1.

**Something to be violated by.** The registry requires a perturbation that
breaks a declared expectation. For an activation dataset the natural
perturbation is the one that makes the activated invariant fail, which is
also the proof the invariant works on a real population rather than merely
having a population.
"""
from __future__ import annotations

# No datasets are declared yet. See the module docstring.
