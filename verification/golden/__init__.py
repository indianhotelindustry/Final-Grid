"""
DSBC Frontline — Golden Master Framework (Wave 0, Deliverable D2)
=================================================================

D1 measures the *engines*. D2 measures the *surfaces*: what a report,
dashboard or API endpoint actually renders to a user. A financial figure
that is correct in the service layer and wrong on the screen is wrong.

Constitutional basis
--------------------
Phase 2.6 §4 (Golden Master Testing, Report Verification, Dashboard
Verification, API Verification) and Principle 11 (Observable
Correctness — a control that cannot fail is not a control).

What a golden master is here
----------------------------
For each declared surface, a stored record of:

  * HTTP status, content type, redirect target
  * the templates Flask rendered
  * every numeric figure the route handed to the template, by dotted
    context path — the figures *before* HTML formatting, which is the
    financially meaningful layer
  * every numeric figure in a JSON response body
  * a SHA-256 of the normalised response body
  * the status an UNAUTHENTICATED client receives for the same URL

The context figures are the substance. The body hash is a coarse net
that catches presentation-only change. The anonymous status turns the
same capture into an authorisation-regression detector at the cost of
one extra request per surface.

Hard rules
----------
1. Read-only with respect to production, enforced by ``verification.dbcopy``.
2. Deterministic. The clock is frozen to a declared instant (see
   ``freeze``) so a master captured today is still valid next month.
   Volatile per-request tokens are normalised, and every normalisation
   rule had to be empirically justified by a repeat-capture diff.
3. Never imported by ``app``.
4. Exclusions are declared and printed on every run. A surface that is
   not covered is stated, never silently dropped.
"""

__all__ = ['freeze', 'catalogue', 'client', 'normalize', 'capture',
           'compare', 'report']

__deliverable__ = 'D2 — Golden Master Framework'
