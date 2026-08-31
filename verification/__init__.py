"""
FinalGrid — Production Verification Framework (PVF)
===================================================

Wave 0 deliverable set. This package contains NO production code and is
NEVER imported by the Flask application. It exists solely to measure the
application from the outside.

Constitutional basis
--------------------
Phase 2.6 §4 (Production Verification Framework), §5 (Financial Parity
Harness), and Principle 9 (a control must be capable of failing).

Hard rules for everything in this package
-----------------------------------------
1. READ-ONLY with respect to production. Every operation runs against a
   disposable copy of the production database. The live file is never
   opened writable. See ``verification.dbcopy``.

2. NEVER imported by ``app``. If any module under ``app/`` ever imports
   ``verification``, that is a defect: the measuring instrument would
   become part of the thing it measures.

3. DETERMINISTIC. Two runs over the same dataset produce byte-identical
   output. Non-determinism is a harness defect, not tolerable noise.

4. FAIL LOUDLY, NEVER SILENTLY. A quantity that cannot be measured
   reports NOT_IMPLEMENTED or ERROR. It never reports agreement by
   omission (Principle 10 — absence of data is not evidence of
   correctness).

Deliverable status (Wave 0)
---------------------------
  D1  Financial Parity Harness      — complete, commissioned 8/8
  D2  Golden Master Framework       — complete, commissioned 16/16
                                      (verification.golden)
  D3  Historical Replay Framework   — complete, commissioned 21/21
                                      (verification.replay)
  D4  Financial Invariant Engine    — complete, commissioned 26/26
                                      (verification.invariants)
  D5  Fault Injection Framework     — complete, commissioned 37/37
                                      (verification.faults)
  D6  Regression Dataset Framework  — not started
  D7  Certification Engine          — not started
  D8  CI/CD Verification Pipeline   — not started
  D9  Backup Restore Verification   — not started
  D10 Release Gate Framework        — not started
"""

__version__ = '0.5.0'
__pvf_deliverable__ = 'D5 — Fault Injection Framework'
