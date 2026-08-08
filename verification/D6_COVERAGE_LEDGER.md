# D6 — the coverage ledger

Every regression dataset records what it adds, loses and changes, and
whether that movement was declared. Introduced 2026-08-08.

`python -m verification ds-coverage --id <dataset> [--tag <tag>]`

Exit **0** when coverage moved exactly as the dataset declared, **1** when
it did not, **3** on a build failure, **4** if production moved during the
measurement.

---

## 1. Why it exists

`DS-ACT-INHOUSE` was declared to resolve three golden-master surfaces that
production leaves UNRESOLVED. It did. Its first version also **un-resolved
four others**, and it passed every declared expectation while doing so.

That loss was found by capturing masters by hand and counting. Doing that
once is diligence; relying on it is not a control. A dataset *replaces* the
transactional layer rather than adding to it (`builder.strip`), so coverage
over a dataset is never automatically a superset of coverage over
production — and nothing in D6 measured the difference.

---

## 2. What is recorded

| | |
|---|---|
| **Coverage Added** | what this dataset can exercise that production cannot |
| **Coverage Lost** | what production exercises that this dataset cannot |
| **Coverage Changed** | what both exercise, but differently — a status that moved, or a population that shrank |
| **Expected vs Unexpected** | movement the dataset declared, against movement it did not |

Two layers are measured: **D2 surfaces** (which resolve) and **D4
invariants** (status *and population*).

Population is the part that matters. An invariant holding over 28
reservations and one holding over 0 are both `HOLDS`, and only one of them
proves anything (P10). A drop to zero is a coverage loss even though
nothing failed, and it is invisible in every other report.

**D1 and D3 are not measured.** Both are per-quantity and per-date rather
than per-entity, and a delta over them needs a definition of "covered" this
module would have to invent. Stated as a gap rather than approximated: an
approximated ledger is worse than none, because it reads as complete.

---

## 3. How a dataset declares

`coverage_expectation` on the `Dataset`, validated at registration —
unknown keys and unknown invariant ids are refused, because a misspelled
key would read as "expected nothing" and turn every real movement into an
unexpected one.

```python
coverage_expectation={
    'surfaces_added':         ('main.checkout__inhouse_reservation', ...),
    'surfaces_lost':          ('reports.night_audit_snapshot__night_audit_log',),
    'invariants_activated':   (),
    'invariants_deactivated': ('INV-B01', ...),
}
```

An **empty** `coverage_expectation` means "no movement declared", so any
movement at all is reported as unexpected. That is the intended default for
a dataset nobody has thought about — not a way to opt out.

A **status change** is read against `expectations.invariants`, not declared
again here. A dataset that already says `INV-A02: HOLDS` has declared the
change from production's `VIOLATED`; duplicating it would be two
declarations of one intent that can drift apart.

**Declared-but-absent is a failure too.** A dataset claiming it resolves a
surface and not resolving it has made a claim the ledger cannot support —
the same class of error as an undeclared loss.

---

## 4. The ledger for `DS-ACT-INHOUSE@1.0`

Measured 2026-08-08. Evidence:
`evidence/20260808_075922_ds_coverage_step2_backfill/`.

**Coverage Added (3)** — all three the stated purpose of the dataset:

```
+ main.checkout__inhouse_reservation
+ main.reservation_folio__inhouse_reservation
+ pos.room_charges_api__inhouse_reservation
```

**Coverage Lost (9)** — one surface and **eight invariants**:

```
- reports.night_audit_snapshot__night_audit_log
- INV-A03   no extra_charges at all, so nothing to group
- INV-B01   no night audit
- INV-B02   no night audit -> no snapshot to hash
- INV-B03   no night audit -> no closed day to recompute
- INV-B05   no night audit -> no audit sequence
- INV-C01   both stays pay cash, so no OTA head is involved
- INV-C05   same population as INV-C01
- INV-D07   no overpayment_logs row
```

**The eight invariants were not known before this measurement.** The hand
count that produced the `+3 / −1` figure in
`D6_STEP2_DS_ACT_INHOUSE.md` §4 covered D2 surfaces only. That figure was
right about surfaces and silent about invariants; the dataset covers
substantially less of the invariant registry than production does.

**Coverage Changed (12)** — every jointly-covered invariant, with two
status moves, both already declared in `expectations.invariants`:

```
! INV-A02   VIOLATED over 40 -> HOLDS over 2   production's NULL folio defect
! INV-C04   VIOLATED over 30 -> HOLDS over 3   production's double-booked room
  INV-C03   HOLDS over 106   -> HOLDS over 8
  ...
```

**Verdict: `AS_DECLARED`.** Every movement was declared and every declared
movement happened.

### This one is backfilled, and it is the only one that will be

`DS-ACT-INHOUSE` was commissioned before the ledger existed, so its
declaration was written against `ds-coverage` output rather than ahead of
it. Every entry traces to the narrative — the eight deactivations are each
a direct consequence of something the story does not contain — but the
order was wrong, and the ledger cannot catch anything in that order.

**`DS-ACT-GROUP` onward declare first and measure after.**

---

## 5. The ledger is itself commissioned

It reported `AS_DECLARED` on the first dataset it was pointed at. That is
the answer it was built to give, which is exactly why it was not evidence
yet — a classifier returning `AS_DECLARED` unconditionally produces the
same output (P9).

21 checks against synthetic snapshots, no database touched. Evidence:
`evidence/20260808_ds_coverage_commission/`.

| Group | Required behaviour |
|---|---|
| Four kinds of movement | identical snapshots clean; undeclared addition reported; undeclared loss reported; declared loss clean; declared-but-absent fails and is reported separately |
| Population decides coverage | `HOLDS` over 0 counts as deactivated even though the status did not move; a population appearing counts as activated |
| Status changes | a declared change is clean; an undeclared one is not; declaring the **wrong** status does not excuse it |
| Population shrink | reported as Changed, not Lost, and does not by itself fail the ledger |

### Two measurement decisions the commissioning forced

**Surfaces are keyed `endpoint__resolver`, not collapsed to the endpoint.**
The first version collapsed them and got the first dataset wrong:
`main.reservation_folio` has both a `checked_out_reservation` and an
`inhouse_reservation` variant, so an endpoint-level set showed it covered
before and after and reported no gain — when a variant that had never
resolved had begun resolving. Collapsing also hides the dangerous
direction, an endpoint keeping one working variant while another silently
stops.

**Dates in surface keys are normalised to `YYYY_MM_DD`.** Report surfaces
are pinned to the business date, so comparing literally produced six
spurious additions and six spurious losses on every dataset — noise that
would bury the real movement and train everyone to skim the ledger. A
surface that does not resolve at all is still reported as lost, because
the normalised key is simply absent.

---

## 6. Obligation

From `DS-ACT-GROUP` onward, a dataset is not finished until:

1. `coverage_expectation` is declared **before** the dataset is built;
2. `ds-coverage --id <dataset> --tag <tag>` exits 0;
3. the evidence pack is retained;
4. the ledger appears in the dataset's completion record.

A dataset whose ledger exits 1 is not commissioned work. Either the
declaration is wrong or the dataset covers something nobody intended, and
the platform does not guess which.
