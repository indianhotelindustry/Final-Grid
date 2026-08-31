# FinalGrid Phase 2a — Authorization Hardening · Completion Report

**Directive:** FOUNDER-DIR-FINALGRID-TARGET-001, Phase 2a
**Finding:** R7 — folio endpoints presently reachable, unguarded and unaudited
**Branch:** `phase-2a-folio-authz` · 4 commits
**Completed:** 2026-08-31
**Verdict:** all gates satisfied. Implementation authorization for any further
phase: **NO**.

---

## 1. What changed

One application file, `app/folio.py`.

| Change | Detail |
|---|---|
| Blueprint authorization gate | `@folio_bp.before_request` — fail-closed. An endpoint absent from `_FOLIO_ROLES` is denied to everyone, so a folio route added by a later phase is guarded by default. |
| JSON refusals | `401` unauthenticated, `403` authenticated-but-unauthorized. Previously an unauthenticated caller received a `302` to the HTML login page — a refusal a JSON client reads as success. |
| Audit on every mutation | `folio_create`, `folio_charge_transfer`, `folio_payment_transfer` record before/after `folio_id` with actor and IP. The module previously contributed **0 of the 29** `AuditLog` write sites. |
| Audit coupling | A mutation whose audit row fails to reach the session is rolled back rather than committed. |
| Refusal record | A refused mutation writes `folio_access_denied`, best-effort, so failing to log evidence cannot turn a `403` into a `500`. |

**Role map applied** — all four endpoints: `Admin`, `Manager`.

Mutations deliberately match `payment_void_service.can_approve_void()`, so
Phase 2b adds an approval step to an existing boundary rather than moving it.

---

## 2. Decision applied, and one to confirm

The directive's §13 listed four decisions with stated defaults. The
authorization said "proceed exactly within the directive's stated scope and
constraints" without answering them individually, so the **stated defaults**
were applied:

| # | Decision | Applied |
|---|---|---|
| 2 | Read scope | **Admin/Manager** — the conservative default, not the broader read the directive proposed |
| 3 | Audit strictness | Strict: a failed audit write rolls the mutation back |
| 4 | Refusal recording | Recorded to `AuditLog` |

> **For confirmation.** The directive *recommended* broadening `list_folios` to
> `FrontDesk` and `Accountant` — a front-desk clerk inspects folios at
> checkout, an accountant reconciles them — but its own default-if-unanswered
> was the conservative collapse. Erring restrictive is the right direction on a
> security change, so the conservative option was applied. Widening it is a
> one-line edit to `_FOLIO_ROLES` with no other consequence, and no caller
> exists today either way.

---

## 3. Verification

### Gate B — Security · **PASS**

`verification/evidence/20260831_phase2a_folio_authz/verify.py` — **29 of 29 cases passed**.

| Group | Cases | Result |
|---|---|---|
| Unauthorized roles refused (4 endpoints × 3 disallowed roles) | T01–T12 | `403`, no row changed |
| Unauthenticated refused | T13–T16 | `401`, no row changed |
| Authorized paths unchanged | T17–T23 | `200` / `201`, audit row written |
| Refusal recorded as `folio_access_denied` | T24 | pass |
| Fail-closed: unmapped endpoint denied even to Admin | T25 | `403` |
| **Guard commissioning (P9)** — same request succeeds with the guard relaxed | T26 | `200` |
| **Audit coupling** — forced audit failure rolls the mutation back | T27 | `500`, row still `NULL` |
| NULL-source transfer unchanged for an authorized caller | T28 | `200` |
| **D11 freeze** proven by identity, not count | T29 | payments `[1,2,3,4,5,6]` and charges `[1,2]` unattributed before **and after** |

Every case asserts both the status code **and** that no database row changed. A
`403` that still wrote is the failure mode that matters.

### Gate C — Financial · **PASS (stability)**

For Phase 2a the financial gate is that nothing moved, not that anything improved.

```
Registered 26 · HOLDS 17 · VIOLATED 2 · VACUOUS 7 · ERROR 0
INV-A02 VIOLATED [CERTIFICATION_BLOCKING]  population 8 · violations 8
INV-A03 VIOLATED [RELEASE_BLOCKING]        confidence PROVEN
INV-R01 NOT_COMMISSIONED (excluded from verdict)
OVERALL VERDICT FAIL · Release blocking 1
```

Identical to the frozen baseline. A programmatic comparison of the full
`result.json` against `20260830_101251_inv_run_production` found the only
differences to be `memory_peak_kb` metering noise (961→966, 143→146,
4446→4444). Every verdict, count, population, violation figure and blocking
classification is unchanged.

Evidence: `verification/evidence/20260831_155939_inv_run_production/`

### Gate F — Verification framework · **PASS**

`inv-run` self-controls: read-only **VERIFIED** (production byte-identical),
**zero writes** counted across the whole registry, frozen clock proven,
repeatable and order-independent verified. Invariant semantics untouched;
VACUOUS reporting intact; `INV-R01` still `NOT_COMMISSIONED`.

### Gate G — Regression · **PASS, with a stale master declared**

`gm-verify` returns **FAIL** over 158 surfaces. That failure is **not**
attributable to Phase 2a:

- The master was captured **2026-08-03**, before W1-R1, W1-R8, DEF-005 and the
  accepted rebrand. Total differences: 3,342.
- All 8 `STATUS_CHANGED` differences are **500 → 200** — W1-R1's clearing of
  HTTP 500s. This change cannot produce them; it emits only 401/403.
- Exactly **one** `folio_bp` surface exists in the master set, and it carries
  exactly **one** difference:

```
folio.list_folios__checked_out_reservation   [FINANCIAL]
  /api/reservation/1/folios
    [BLOCK] ANON_STATUS_CHANGED
            master : 302
            current: 401
```

That is precisely the intended correction. **Phase 2a's entire golden-master
footprint is one surface, one difference, and it is the one the directive
specified.** Re-baselining the stale master is Phase 6 work, not Phase 2a's.

Evidence: `verification/evidence/20260831_160040_gm_verify_production/`

Known limitation carried forward (**V5**): golden masters capture HTML only, so
Excel and PDF branches remain unverified. Phase 2a touched no report surface, so
this is not material here — but it is not coverage either, and is not claimed as such.

### Functional regression

App boots · **298 routes** (baseline 298) · 151 templates compile, 0 failures ·
all four folio endpoints registered · port 5000 clear.

---

## 4. Database safety

| Control | Result |
|---|---|
| SC-1 — baseline integrity | `51dd83b7…30bc2` verified before and after every step. **Unchanged.** |
| SC-2 — disposable copies | All testing on `verification/_work/phase2a_authz.db` via `dbcopy.make_copy()` (`sqlite-backup-api`). |
| SC-3 — no orphan process | Port 5000 clear at completion. |
| D11 freeze | Payments `1–6` and charges `1–2` unattributed at start and at end, **proven by id set**. |
| Schema | No change. No migration. PD-5 and PD-6 not triggered. |
| Production data | Never written. `audit_logs` in the baseline still 23. |

---

## 5. Answerability (§18)

| Question | Answer |
|---|---|
| What changed | `app/folio.py` — blueprint guard, JSON refusals, audit writes, audit coupling |
| Why | Finding R7: endpoints reachable by any authenticated account, unaudited, and already executing against live data |
| What authorized it | FOUNDER-DIR-FINALGRID-TARGET-001 Phase 2a directive; PD-1 approved |
| Files changed | `app/folio.py`; new `verification/evidence/20260831_phase2a_folio_authz/` |
| Database touched | Disposable copy only. Baseline byte-identical |
| Tests run | 29-case authorization matrix — all passed |
| Verification passed | Gates B, C, F, G, H |
| What remains unresolved | Listed below |

---

## 6. Remaining and newly observed

| Item | Status |
|---|---|
| **R7 — control-model half** | Open. Maker-checker, billing-responsibility governance and the duplicated company linkage are **Phase 2b**. Phase 2a closed the access half only. |
| **R1 / F3** | Unchanged and unaddressed by design. `INV-A02` / `INV-A03` remain VIOLATED. Phase 1. |
| **D11** | Unanswered. Historical NULL attribution untouched. |
| **R6** | Six other guard idioms and 27 unrestricted report routes untouched. Phase 4. |
| **Stale golden master** | Declared, not fixed. Pre-dates Phase 2a. |
| **New observation — CSRF** | `folio_bp` is *not* exempt from the global `CSRFProtect`, so a cross-site attacker could not have driven these endpoints. R7's exposure was always a legitimate-but-unauthorized *user* — a Housekeeping account acting deliberately — not a CSRF attacker. This **refines** the exposure; it does not reduce the finding, and R7's classification as presently reachable stands. Recorded, not acted on. |

---

## 7. Statement

Phase 2a hardened the reachable folio mutation surface without populating,
repairing or altering a single folio relationship. Every unauthorized role is
now refused with a machine-readable status and no data effect; every authorized
mutation is recorded, and refuses to commit if it cannot be recorded. The
financial invariants are exactly as they were, which for this phase is the
required outcome rather than a disappointment.

**No further phase has been started. Awaiting Founder review.**
