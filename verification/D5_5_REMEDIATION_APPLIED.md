# D5.5 — Remediation Applied

R-1, R-2, R-3 and R-6 of `D5_5_REMEDIATION.md`, applied 2026-08-08.
Companion to that document, which is left as written: it records what was
proposed, this records what was done and where the two differ.

**Scope: one file, `verification/datasets/financials.py`.** No production
financial logic, schema object or configuration value was modified.
Measured, not asserted — the 68 `.py` files under `app/` hash identically
before and after (`8b15333…`), as does `instance/pms.db` (`f07b090a…`).

Evidence: `evidence/20260808_r123_remediation/`, containing the report,
the measurements and the script that produced them.

---

## 1. What moved

Declared before the change, per `ENGINEERING_GUIDE.md` §5:

| Probe | Before | After | Cause |
|---|---|---|---|
| `outstanding` | −1,697.32 | **+199.92** | R-1 — tax added, exactly `tax_total` |
| `taxable_total` | 75,893.34 | **37,946.67** | R-3 — each taxable base counted once |

**21 of the 23 pre-existing probes hold.** The two that moved are the two
declared to move, to the values declared for them. Eight probes were
added; each is new, so none of them can hold or move.

---

## 2. R-1 — `outstanding` omits tax

Applied as specified. `outstanding` is now

```
room revenue + extra charges (excl. room rent) + tax − payments (non-voided)
```

and reports **+199.92**, reconciling to the audit's authoritative table.

### The verification the spec asked for does not hold, because the spec is wrong

`D5_5_REMEDIATION.md` R-1 says to confirm "the per-reservation trace shows
21 of 28 at exactly 0.00". Measured: **19 of 28 at exactly 0.00, 9 with a
residue.**

The fix is not at fault. The audit's own residue table
(`D5_5_CONSISTENCY_AUDIT.md`, "The real position") **names nine
reservations** — 1, 6, 7, 9, 10, 17, 23, 27, 28 — and then adds a row for
"21 others", which totals 30 against a population of 28. The measured
residues match the audit's enumerated list to the paisa and sum to its own
aggregate:

```
+200.00 − 0.50 + 0.15 + 0.15 + 0.16 − 0.01×4 = +199.92
```

The enumeration is right; the count is arithmetic error. **19 + 9 = 28.**

---

## 3. R-2 — the room-rent double count

Applied as specified, mirroring `replay/ledger.py:176-183`:

```sql
extra_charges WHERE charge_type IS NULL OR charge_type <> 'room_rent'
```

Shipped in the same commit as R-1, as the spec requires.

### It cannot be proved by the aggregate, so it was proved by injection

`0 of 30` night-rate rows are posted and no `extra_charges` row carries
`charge_type = 'room_rent'`. The exclusion removes nothing, so
`outstanding` is +199.92 with or without it. Under §5 step 4 a value that
holds is only acceptable if the change is shown to have taken effect some
other way — otherwise this is indistinguishable from not having applied
R-2 at all.

Commissioned by injection into a disposable copy (production untouched):
all 30 night rates posted into `extra_charges` as `room_rent`, ₹37,217.12.

| | `outstanding` |
|---|---|
| Fixed probe, room rent posted | **199.92 — holds** |
| Pre-R-2 form, same database | **37,417.04 — moves** |

The pre-R-2 form overstates by exactly ₹37,217.12, confirming the latent
error the audit predicted at "~₹37,217". The probe is now capable of
being wrong in that scenario and is not (P9).

Two probes were added so the exclusion is visible rather than absorbed —
the reason `replay/ledger.py` records both slices:
`extra_charges_room_rent` (0.00) and `extra_charges_non_room_rent`
(729.85).

---

## 4. R-3 — `taxable_total` double counts

Reports **37,946.67**, down from 75,893.34. Implemented by aggregating
`DISTINCT (reservation_id, charge_source_type, charge_source_id,
taxable_amount)`.

### Two departures from the spec

**The grouping includes `reservation_id`; the spec's does not.**
`D5_5_REMEDIATION.md` R-3 proposes `DISTINCT (charge_source_type,
charge_source_id)`. `charge_source_id` is a label like
`night_2026-05-27` and is unique only *within* a reservation. Grouping
without `reservation_id` collapses the same stay-night across every
reservation that has one: **33 real taxable bases become 5**, and
`taxable_total` reports **18,613.29** — wrong in the opposite direction
and less obviously so. Written as specified, R-3 would have replaced a
2× overstatement with a 2× understatement.

**`DISTINCT`, not the spec's alternative of dividing by component count.**
If two components ever disagreed about the base, `DISTINCT` moves and a
divisor silently would not.

**The result is 37,946.67, not the 37,946.97 the spec predicts.** The
spec's expected value is `room_revenue + extra_charges`. The ₹0.30
difference is the two `other_income` rows of ₹0.15 on reservations 10 and
17 — the postings that resolved the two logged overpayments. **They carry
no tax lines,** correctly, because they are not taxable. `taxable_total`
should not equal total charges whenever an untaxed charge exists; the
spec's check is only right on a dataset with no untaxed charges.

Two count probes were added to make the table's shape measurable rather
than assumed: `tax_lines_count` (66) and `tax_base_count` (33). Their
ratio is the component count, 2 for domestic CGST/SGST. If it moves,
`taxable_total` needs re-reading before it is trusted.

---

## 5. R-6 — `invoice_round_off_amount`

Four probes added: `invoice_unrounded_grand_total` (39,844.25),
`invoice_round_off_total` (−0.25), `invoice_rounded_grand_total`
(39,844.00), `invoice_round_off_rows` (6).

`unrounded + round_off = rounded` holds **exactly, on all 28
reservations** — verified per row, not only in aggregate.

### BS-4 is wrong that round-off is the sole cause of the residue

`D5_5_CONSISTENCY_AUDIT.md` BS-4 calls `invoice_round_off_amount` "the
sole cause of the ±0.01–0.16 residue on seven reservations". Attributing
each of the nine residues to its mechanism:

| Cause | Reservations | Total |
|---|---|---|
| Invoice round-off | 7, 10, 17, 28 | −0.25 |
| Per-line vs whole-invoice tax rounding | 6, 9, 23, 27, 28 | +0.04 |
| Genuine unpaid balance (F-2) | 1 | +200.00 |
| Genuine overpayment, logged and resolved | 10, 17 | −0.30 |

Reservations **6, 9, 23 and 27 have `invoice_round_off_amount = 0.00`**
and a −0.01 residue each. Their cause is a second, unrecorded mechanism:
the invoice rounds GST over the whole bill while `tax_lines` rounds it per
component, so `invoice_unrounded_grand_total` differs from
`room + extras + tax` by up to a paisa. Reservation 6 bills ₹1,500.00
where the component rows sum to ₹1,499.99.

Reservations 11 and 12 carry a non-zero round-off and **no** residue.
Round-off and residue are not the same population.

**Consequence for the deliverable.** R-6's stated purpose is that a
dataset can declare an exact per-reservation balance without tolerances.
Modelling `invoice_round_off_amount` alone does not achieve that — it
leaves the tax-path paisa unexplained on four reservations. That is why
all three invoice columns are probed rather than the one the spec names:
a dataset declaring against `invoice_rounded_grand_total` gets an exact
figure, because the invoice total is what the guest was actually billed.

---

## 6. Framework neutrality

Nothing outside D6 is affected — `financials.py` has no caller in D1–D5.
Measured rather than assumed:

| Gate | Result |
|---|---|
| `selfcheck` | READ-ONLY VERIFIED, exit 0 |
| `compare --tag v2.2.18_preWave1` (D1) | 41 changes, `IMPL_ADDED` 38 / `VERDICT_CHANGED` 3, `Q16`–`Q18` — identical to the D6 Step 1 result |
| `inv-run` (D4) | registered 24, violations 57, uncommissioned 0, release-blocking `INV-A03` `INV-B03` — identical to the `wave0_freeze` state |
| `ds-registry` (D6) | exit 0 against the empty registry |

D1 and D4 exit 1. Both did so before this change, for the reasons recorded
in `WAVE0_STATUS.md` §1a and §3, and both are unchanged by it.

---

## 7. Not applied

- **R-4** — the Class D invariant for orphan overpayment records. Full D4
  declaration with a commissioning obligation; required before
  `DS-ACT-OVERPAY` is declared, not before `DS-ACT-INHOUSE`.
- **R-5** — the ₹1.00 materiality threshold. Owner decision, unchanged.

## 8. Corrections to the D5.5 documents

Recorded here rather than by editing them, per `ENGINEERING_GUIDE.md` §7 —
the repository is the source of truth and the disagreement gets written
down.

| Document | Claim | Measured |
|---|---|---|
| `REMEDIATION` R-1 | "21 of 28 at exactly 0.00" | **19 of 28**; the audit's own list names 9 residues and 9 + 21 = 30 > 28 |
| `REMEDIATION` R-3 | `DISTINCT (charge_source_type, charge_source_id)` | Under-counts to **18,613.29**; `reservation_id` is required |
| `REMEDIATION` R-3 | `taxable_total` ≈ 37,946.97 | **37,946.67**; the ₹0.30 is two untaxed `other_income` rows |
| `AUDIT` BS-4 | round-off is "the sole cause" of the residue, on "seven reservations" | **Nine** reservations, **two** mechanisms; four have zero round-off |

The audit's final authoritative table is unaffected: charges excluding tax
₹37,946.97, tax ₹1,897.24, charges including tax ₹39,844.21, collections
₹39,644.29, outstanding **₹199.92**. Every figure in it is confirmed.
