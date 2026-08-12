# W1-R1 — Surfaces That Do Not Render

**Completed** 2026-08-12 · app v2.2.18 · branch `main`
**Risk class** SILENT — no financial figure moves
**Blueprint** `WAVE1_BLUEPRINT.md` §4 (W1-R1), covering defects W1-13 and W1-14

---

## 1. Objective and outcome

Make every surface that returns HTTP 500 render, and make the dead revenue
alert detector run. No financial calculation was touched.

```
                     before   after
Surfaces captured      158      158
Healthy                145      153
Unhealthy               13        5
of which HTTP 500        7        0
```

**Every 500 in the application is gone.** The five remaining unhealthy
surfaces are 400/404 responses on parameterised API endpoints that require
arguments the catalogue does not supply. They are a declared-gap artefact,
not a render failure, and they are out of this release's scope.

---

## 2. What the blueprint said, and where reality differed

The blueprint listed eight surfaces from D2 §8.1. Two corrections, both
found by measurement rather than assumption:

**`/reports/ar-aging` was no longer 500.** It renders 200 today. Its
`BuildError` is real but *dormant*: the offending `url_for` sits inside
`{% for r in rows %}`, and there are no outstanding receivables, so the
loop never executes. It would have 500'd on the hotel's first overdue
account. Fixed anyway — a latent 500 in an AR report is exactly the kind
of defect that surfaces at the worst moment.

**`/reports/guest-report` had two independent defects stacked.** The one
D2 recorded (`UndefinedError` on `strftime`) is a production defect and is
fixed. Underneath it sat a *harness* defect that made the surface
uncapturable — see §5.

A third discovery: `/reports/daily-reconciliation` had a **second defect
hidden behind the first**. Clearing its template syntax error exposed
`TypeError: unsupported format string passed to Undefined.__format__` —
the route passed `by_mode` as a flat float while the template had always
read `data.amount` / `data.count`. The syntax error had been masking a
route/template contract mismatch.

---

## 3. Files modified

| File | Change |
|---|---|
| `app/templates/reports/daily_reconciliation.html` | `**request.args` → explicit `date`/`mode`/`staff` params |
| `app/templates/reports/refund_report.html` | `**request.args` → explicit `from`/`to` |
| `app/templates/reports/tip_report.html` | `**request.args` → explicit `from`/`to` |
| `app/templates/reports/other_income_report.html` | `**request.args` → explicit `from`/`to` |
| `app/templates/reports/guest_report.html` | Excel link rebuilt to match the PDF link's idiom |
| `app/templates/reports/ar_aging.html` | `main.guest_folio(reservation_id=…)` → `main.reservation_folio` |
| `app/reports.py` | guest_report date coercion; daily_reconciliation `by_mode` shape + `total_payment_count` |
| `app/auth.py` | `join(User)` → `joinedload(Shift.user)` |
| `app/routes.py` | `load_tab('reservations')` now passes `default_checkout_hm` |
| `app/alert_engine.py` | unwrap the `full_month_target` metric envelope |
| `verification/golden/freeze.py` | sqlite3 adapters for `FrozenDate` / `FrozenDateTime` + two new proof checks |

**Files created:** this report, and eight evidence packs under
`verification/evidence/`.

---

## 4. Root causes

Four of the seven were one defect repeated. `url_for('…', **request.args,
format='excel')` is invalid Jinja — a `**` unpacking must be the final
argument in a call. This is the library-upgrade regression D2 predicted:
the templates were written against a Jinja that tolerated it. Each was
replaced with the explicit named parameters used everywhere else in this
codebase (`arrivals.html`, `leakage.html`, `flash.html` and ~20 others),
rather than with a cleverer unpacking.

| Surface | Root cause | Fix |
|---|---|---|
| daily-reconciliation | invalid Jinja call syntax, **plus** route/template `by_mode` contract mismatch | explicit params; route emits `{amount, count}` per mode |
| other-income / refund / tip | invalid Jinja call syntax | explicit `from`/`to` params |
| guest-report | SQLite returns raw-query DATE columns as `str`; three consumers call `.strftime` | coerce once in the route |
| ar-aging (dormant) | `url_for('main.guest_folio')` given `reservation_id`; route takes `guest_id` | link to `main.reservation_folio`, which the row already keys on |
| auth/shifts | `Shift` has three FKs to `users`; bare `join(User)` cannot pick an onclause | `joinedload(Shift.user)` — disambiguates *and* removes 100 lazy lookups |
| api/tab/reservations | `default_checkout_hm` not passed by the AJAX branch; `Undefined` reached `json.dumps` | pass it from the same `_resolve_default_checkout_hm()` authority the other three render paths use |
| revenue alerts (silent) | `full_month_target` is a `{value, display, sub}` envelope, not a scalar | unwrap `.get('value')` |

**`by_mode` shape change is contained.** Three other routes have their own
`by_mode` local with the flat shape; their templates iterate it flat and
are untouched. The new `{amount, count}` shape matches the convention
`night_audit_service.py:651` already established.

---

## 5. A verification blind spot, found and closed

`/reports/guest-report` kept returning 500 under the harness after its
production defect was fixed. The cause was the harness itself:

```
sqlite3.ProgrammingError: Error binding parameter 1:
type 'FrozenDate' is not supported
```

The D2 clock freeze rebinds `datetime.date` to a `FrozenDate` subclass.
`sqlite3` resolves parameter adapters by **exact type**, so the stdlib's
`datetime.date` adapter never matched, and any surface binding a
frozen-derived date into a raw SQL query died.

**This was not introduced by this release.** Verified by stashing every
change and reproducing the identical error at `HEAD`.

The consequence is larger than one report: **every raw-SQL surface taking
a date parameter was uncapturable, and D2 recorded each as an application
500.** The framework was attributing its own failure to the application.

Fixed in `verification/golden/freeze.py` by registering adapters that
mirror the stdlib conversions exactly, so a frozen run binds what a live
run binds. Per P11 the fix is itself falsifiable — `prove()` gained two
checks that bind a frozen date and datetime through real sqlite3 and
compare the round-tripped text:

```
PASS  sqlite_binds_frozen_date
PASS  sqlite_binds_frozen_datetime
Proven : True
```

If the adapters regress, capture aborts rather than manufacturing 500s.

---

## 6. Database impact

**None.** No schema change, no migration, no backfill, no data written.
Both verification runs confirm `read_only_verified: True` and
`source_hash_before == source_hash_after`.

---

## 7. Verification evidence

### 7.1 Surfaces — the eight targets, all rendering with real content

```
200  OPERATIONAL   6 figures  /auth/shifts
200  OPERATIONAL  64 figures  /api/tab/reservations
200  FINANCIAL    13 figures  /reports/ar-aging
200  FINANCIAL    33 figures  /reports/daily-reconciliation
200  FINANCIAL    33 figures  /reports/daily-reconciliation?date=2026-08-10
200  FINANCIAL    24 figures  /reports/guest-report
200  FINANCIAL     9 figures  /reports/other-income-report
200  FINANCIAL     9 figures  /reports/refund-report
200  FINANCIAL     9 figures  /reports/tip-report
```

Evidence: `20260812_083325_gm_capture_w1r1_prefix` (before) →
`20260812_084646_gm_capture_w1r1_final` (after).

### 7.2 Financial neutrality — measured against a same-day control

Because five commits landed since the last full baseline, neutrality was
established against a **control run on stashed `HEAD`**, same data, same
day — not against the 2026-08-08 baseline.

**D1 parity** (`w1r1_headctl` vs `w1r1_post`): 22 quantities.

```
verdict differences        : NONE
implementation-value diffs : NONE
divergence-set differences : NONE
1 SINGLE_SOURCE · 15 AGREED · 4 DIVERGED · 2 VACUOUS   (both runs)
```

**D4 invariants** (vs the DEF-005 production run): 26 invariants, status,
violation count and population **identical for all 26**. Release-blocking
`[INV-A03]` and certification-blocking `[INV-A02, INV-A03]` unchanged;
financial impact unchanged at ₹4,776.19 / ₹476.19.

> One field differs and it is not a regression: `overall` reads
> `UNVERIFIED` in the DEF-005 baseline and `FAIL` here. The baseline was a
> `--fast` run, which skips the repeatability and reverse-order passes and
> is reported UNVERIFIED **by construction**. This release's run performed
> both passes and both passed, letting the engine reach its real verdict —
> FAIL, driven by the two pre-existing VIOLATED invariants scheduled for
> W1-R3. Re-running this code with `--fast` reproduces `UNVERIFIED`
> exactly (`20260812_084855_inv_run_w1r1_fastctl`), confirming the
> difference is a run-flag artefact.

**D6 datasets**: all five PASS — 281 expectations met, 0 unmet, 0 not_run.

```
DS-ACT-INHOUSE@1.0     PASS  met=59
DS-ACT-CORRECTION@1.0  PASS  met=55
DS-ACT-VOIDCN@1.0      PASS  met=54
DS-ACT-GROUP@1.0       PASS  met=56
DS-ACT-SHIFT@1.0       PASS  met=57
```

**D3 replay**: not re-run. No derivation engine was touched; every change
is presentation-layer or harness. D1 showing zero value movement across
22 quantities is the stronger statement.

### 7.3 The alert detector, commissioned

A detector that merely stops raising is not evidence it works. Seeding a
monthly target above actual MTD sales:

```
SEEDED   -> 4 alerts   MTD_REVENUE_BELOW_PACE, TODAY_SALES_BELOW_TARGET,
                       FORECAST_BELOW_TARGET, RUN_RATE_UNREALISTIC
NULL     -> 0 alerts   (real production data, no target configured)
```

The control fires when it should and stays silent when it should not.

**It emits 0 alerts on production today, and that is the correct answer** —
no monthly revenue target is configured, so every guard is `> 0`-gated
and legitimately false. Dashboard output is therefore byte-identical to
before the fix, which is what makes this release silent. The difference
is that the silence is now honest rather than the result of a swallowed
`TypeError`.

**A P11 finding, recorded not fixed.** `build_alerts` wraps every detector
in `except Exception: logger.exception(...)`. That is why this failure
survived undetected across every dashboard render. The remaining seven
detectors were each run individually and all pass, so nothing else is
currently dead — but the swallow means the *next* one to break will also
be invisible. Making detector failure observable is a control-design
change, not a render fix, and belongs in its own release.

---

## 8. Risk assessment

| Risk | Severity | Mitigation | Residual |
|---|---|---|---|
| A template fix changes a displayed figure | High | 158-surface golden capture; D1 value-level diff vs HEAD control | None — zero value movement |
| `by_mode` shape change breaks another report | Medium | All `by_mode` sites enumerated; the other three are separate locals with flat-reading templates | None — all render 200 |
| `SimpleNamespace` rows break attribute access | Medium | Every consumer uses attribute access; verified across HTML, print and Excel paths | Low |
| `joinedload` changes which shifts are listed | Low | `user_id` is `nullable=False`, so the previous inner join dropped nothing | None |
| Freeze adapters mask a real date defect | Medium | Adapters mirror stdlib conversions exactly; two proof checks compare round-tripped text | Low |
| Excel export paths not covered by D2 | Medium | D2 captures HTML only. `guest_report`'s Excel branch shared the fixed date bug | **Open — see §10** |

---

## 9. Rollback

No data to restore; `git revert` is sufficient and complete.

```bash
git revert <this-commit>
```

Partial rollback is safe — every file is independent. To keep the
application fixes but drop the harness change:

```bash
git checkout HEAD~1 -- verification/golden/freeze.py
```

Reverting `freeze.py` alone restores the blind spot: `guest-report` will
again be recorded as a 500 that the application does not have.

---

## 10. Follow-ups, deliberately not in this release

1. **Detector failure is unobservable.** `build_alerts` swallows every
   detector exception (§7.3). A control whose failure is invisible
   violates P11. Needs its own release.
2. **D2 does not capture Excel/PDF branches.** `?format=excel` was never
   captured, so `guest_report`'s Excel export carried the same date defect
   undetected. A whole output format is unverified.
3. **Five unhealthy non-500 surfaces remain** — 400/404 on parameterised
   endpoints. Either declare them as gaps with reasons or supply
   parameters; today they sit in an ambiguous middle.
4. **`/api/voucher/lookup` returns 400 at BLOCK severity** and is
   classified FINANCIAL. It should not stay unexplained.

---

## 11. Verdict

W1-R1 is complete. Every HTTP 500 is cleared, the dead detector is live
and commissioned, and the release is provably silent: 22 D1 quantities,
26 invariants and 281 dataset expectations all identical to the control.

The release also closed a blind spot in the verification framework itself
that had been attributing a harness failure to the application — which is
precisely what a golden master exists to expose, and the reason this work
was sequenced first.
