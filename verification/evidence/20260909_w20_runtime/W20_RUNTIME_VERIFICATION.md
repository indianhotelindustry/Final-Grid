# W-20 Overstay — Runtime Verification Closure

| | |
|---|---|
| Directive | FG-P1-W20-RUNTIME-20260909-01 |
| Executed | 2026-09-09 |
| Repository | `C:\Users\SIPL Server\Downloads\DSS\FinalGrid\SukoonPMS` · `main` |
| HEAD | `e69f2ac242f7fdc3e0c042ceb40dc0393280134b` — unchanged; no commit, no push |
| Writer | **W-20** — `main.add_overstay_charge`, `POST /reservation/<id>/overstay-charge` |
| Production database | 733,184 B · `51dd83b7f0fa42a3e85afb0f46c1a5f7cc6978436ff361250caef9ae92830bc2` — unchanged |
| Result | **23 / 23 cases passed — W-20 RUNTIME VERIFICATION PASS** |
| Application code changed | **No** |

---

## 1. The disclosed vacuous condition, and its exact cause

The Phase 1 report recorded that `T-W20` passed vacuously: the case asserted
`got in (folio_id, None)`, and `None` was the value it actually got, because
no charge was ever created. Inspection of the route establishes why.

`add_overstay_charge` returns early, before the charge block, unless **all**
of these hold:

| # | Precondition | Phase 1 fixture | Met? |
|---|---|---|---|
| 1 | caller is Admin / Manager / FrontDesk | Admin | ✅ |
| 2 | `reservation.status == 'CheckedIn'` | set to `CheckedIn` | ✅ |
| 3 | **`reservation.booking_type == 'Hourly'`** | **`'Regular'`** — the model default (`app/models.py:326`) | ❌ |
| 4 | **`reservation.checkout_time` is set** | **`None`** — never assigned | ❌ |
| 5 | `rate_per_night > 0` | 1000 | ✅ |
| 6 | `departure_date + checkout_time` parses | n/a (blocked at 4) | — |
| 7 | billable minutes > 0 after a 10-minute grace | n/a | — |

**Condition 3 is what stopped it**, with condition 4 waiting immediately
behind. The route is deliberately Hourly-only — *"Overstay billing currently
supports Hourly bookings only"* — and all four reservations on the
production database are `booking_type='Regular'` with no hourly stay, so the
Phase 1 fixture, which copied their shape, could never reach the charge.

**This is a fixture gap, not an implementation defect.** No production logic
was changed to make the path executable.

## 2. Fixture correction — the smallest change that reaches the charge

A fresh reservation on the disposable copy, with:

```
booking_type          = 'Hourly'          # was 'Regular' (model default)
checkout_time         = '12:00'           # was None
departure_date        = yesterday         # so the overstay window is real
status                = 'CheckedIn'
rate_per_night        = 2400
overstay_billed_until = None              # first charge, grace applies
```

A second reservation was left as `booking_type='Regular'` with no
`checkout_time` so the **original vacuous condition is reproduced and
asserted** (case W20-01) rather than merely described. The eight D11 rows
were not used as fixtures.

## 3. Runtime path exercised

`POST /reservation/6/overstay-charge` through `app.test_client()` against a
`make_copy()` copy — the real Flask route, the real handler, the real
`ExtraCharge` construction. Nothing mocked; the test constructs no financial
row of its own. HTTP 302 (the route's normal redirect on success).

## 4. The financial row the route produced

| Field | Value |
|---|---|
| `id` | 3 |
| `reservation_id` | 6 |
| **`folio_id`** | **6** |
| `amount` | 2000.00 |
| `description` | `Overstay — 20 hrs @ ₹100.00/hr` |
| `charge_date` | 2026-09-09 |

## 5. Folio attribution

| Assertion | Result |
|---|---|
| `folio_id IS NOT NULL` | ✅ (W20-03) |
| equals the reservation's authoritative billing folio | ✅ folio **6** = folio A of reservation 6 (W20-04) |
| that folio belongs to *this* reservation, letter A | ✅ `(6, 'A')` (W20-05) |
| not an arbitrary or unrelated folio | ✅ charge's `reservation_id` is 6 (W20-06) |
| reservation context unchanged | ✅ status, arrival, departure, rate, booking_type, checkout_time, room all identical (W20-11) |

## 6. Audit

| Assertion | Result |
|---|---|
| audit row exists for this charge | ✅ exactly one: `('posted', 'ExtraCharge', 3)` (W20-07) |
| it corresponds to the actual operation | ✅ `after_state` = `{amount: 2000.0, folio_id: 6, reservation_id: 6, charge_type: 'overstay', flow: 'overstay_charge'}` — same folio (W20-08) and same amount (W20-09) as the row |
| no audit-after-commit | ✅ (W20-10) The `Reservation`-level `overstay_charged` row now **survives the commit**. Before Phase 1 it was written *after* `db.session.commit()` into a session that was never committed again, so it was discarded at teardown. Phase 1 moved both audit rows ahead of the commit. |

**Q-5 fault injection on this specific path** (`app.services.audited_financial_write` replaced with a raiser):

| Assertion | Before | After | Result |
|---|---|---|---|
| overstay charge committed | 3 charges | 3 charges | ✅ none (W20-13) |
| audit row committed | 25 | 25 | ✅ none (W20-14) |
| caller told it failed | — | **HTTP 500** | ✅ no misleading success (W20-15) |
| billing marker advanced | `None` | `None` | ✅ not advanced (W20-16) |

## 7. Repeat execution — existing window semantics

Second `POST` issued 66 ms after the first.

| Observation | Value |
|---|---|
| Billing marker before / after | `08:07:02.833063` → `08:07:02.899686` |
| Same window re-billed? | **No** — the marker moved forward (W20-17) |
| Duplicate folio created? | **No** — still exactly 1 folio (W20-18) |
| Charges after two calls | **2**: `#3` ₹2000.00 *(20 hrs)* and `#4` ₹100.00 *(1 hr)* |
| Second charge attributed? | ✅ folio **6**, same billing folio (W20-19) |

**Recorded plainly rather than presented as clean:** the second call did
create a second charge. That is the route's existing semantics, not a Phase 1
regression. `overstay_billed_until` guarantees the *same* window is never
billed twice, but the handler bills whatever window has elapsed since the
marker, and `billable_hours = ceil(billable_minutes / 60)` rounds any
positive remainder up to a full hour — so a repeat click 66 ms later bills
one further hour at ₹100.

The billing logic is **untouched by Phase 1**: the diff to
`add_overstay_charge` adds only `folio_id=`, the strict audit call, and the
move of `db.session.commit()`. `ceil`, `billable_hours`, the grace period and
the marker assignment are byte-identical to the committed version. Whether an
immediate repeat should bill a further hour is a question about the overstay
product rule, outside this directive and outside Phase 1; it is recorded here
so the behaviour is on the record and not discovered later as a surprise.

## 8. D11 safety

| | Before | After |
|---|---|---|
| `payments` with NULL folio | ids 1–6 | **identical** |
| `extra_charges` with NULL folio | ids 1, 2 | **identical** |
| Amounts / `folio_id` / `reservation_id` per row | captured | **identical** (W20-20, W20-21) |

The D11 rows were not used as fixtures at any point.

## 9. Production database safety

| | Before | After |
|---|---|---|
| SHA-256 | `51dd83b7…30bc2` | **identical** (W20-22) |
| Size | 733,184 B | **identical** (W20-23) |

Production was opened read-only for hashing only; every mutation happened on
`verification/_work/w20_overstay.db`, a `sqlite-backup-api` copy.

## 10. Files changed by this directive

| File | Action |
|---|---|
| `verification/evidence/20260909_w20_runtime/verify.py` | created — focused runtime test |
| `verification/evidence/20260909_w20_runtime/result.json` | created — machine-readable result |
| `verification/evidence/20260909_w20_runtime/test_results.txt` | created — exact output |
| `verification/evidence/20260909_w20_runtime/W20_RUNTIME_VERIFICATION.md` | created — this record |

**No application code was modified.** No schema, migration, FK, `NOT NULL`,
business-date, authorization, scheduler, invoice/GST or Level 3 change. The
Golden Master was **not** recaptured or rewritten. No unrelated working-tree
change was cleaned.

## 11. Limitations

1. The repeat-call behaviour in §7 (a further hour billed for a 66 ms window)
   is recorded, not fixed — pre-existing and out of scope.
2. The test exercises the **charge** path. The **waive** path
   (`waive_charge=1`) is not covered; it creates no financial row and was
   outside this closure's objective. It still contains an audit-after-commit
   pattern, which Phase 1 deliberately did not touch because it is not a
   financial writer.
3. The charge date comes from `now.date()` (wall clock), not the business
   date — a known K-7 item, deferred to Phase 3 under Q-3 and unchanged here.
4. One test defect was found and fixed during this run: ORM objects were
   indexed as dicts in the idempotency assertion. Corrected; the final run is
   clean.

## 12. Effect on Phase 1 status

The disclosed gap is closed: W-20's attribution, audit coupling and repeat
behaviour are now proven at runtime, not only statically. The overall Phase 1
verdict is **not** altered by this record — that remains for Founder review.
