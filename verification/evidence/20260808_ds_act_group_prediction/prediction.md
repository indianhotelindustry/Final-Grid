# `DS-ACT-GROUP` — reassessment and coverage prediction

Written **before** the dataset was authored or built.

---

## Part 1 — the reassessment the owner asked for

> If `DS-ACT-GROUP` still activates no additional verification and no new
> blocking evidence has emerged, implement it as the final non-blocked
> business dataset before returning to governance-dependent work.

**Both conditions hold. Re-measured after the verification enhancements,
not assumed from last time.**

**It still activates nothing.** No invariant's `data_sources` names a group
table, no fault's declaration mentions one, and no parity quantity reads
`GroupBlock`. Re-checked against the registries after the D1 extension —
if any quantity had touched groups, extending the ledger to D1 would have
been the moment it showed up. Nothing did.

**No new blocking evidence.** `group_blocks` is transactional, covered by
`content_hash`, and needs five columns. It carries none of the
`DS-ACT-CORPCREDIT` problem: that one is blocked because `companies` is a
PRESERVED master table outside the content hash, and a group block is not.

**One thing changed in its favour.** The D2 expectation element now exists,
so this dataset can *declare* that `groups.detail` resolves and have the
registry check it. Written a day ago the claim would have been
unverifiable — exactly the position `DS-ACT-INHOUSE` was left in.

So it goes ahead as what it is: **a D2-coverage dataset that activates
nothing**, closing the last UNRESOLVED surface with no other owner. Its
record says so rather than letting the `DS-ACT-` prefix imply otherwise.

---

## Part 2 — predicted coverage

### `surfaces_added` — 1

```
groups.detail__any_group
```

The only surface pinned to `any_group`, UNRESOLVED on production because
`group_blocks` is empty. This is the whole point of the dataset.

### `surfaces_lost` — 1

```
reports.night_audit_snapshot__night_audit_log
```

No night audit declared, as in all three previous datasets.

### `invariants_activated` — none

Nothing references group tables. Predicted **empty**, and if the ledger
disagrees the reasoning was wrong about what a group booking touches.

### `invariants_deactivated` — 7

```
INV-B01, INV-B02, INV-B03, INV-B05    no night audit
INV-C01, INV-C05                       cash only
INV-D07                                no overpayment log
```

The same seven as `DS-ACT-CORRECTION` and `DS-ACT-VOIDCN`. `INV-A03`
survives, because the narrative carries an extra charge.

### `quantities_activated` — none. `quantities_deactivated` — 1

```
Q15    no night audit to recompute
```

Same as all three predecessors.

### Predicted parity verdicts

From the three ledgers already measured, a small clean dataset moves
`Q12`, `Q13`, `Q14`, `Q17`, `Q22` from DIVERGED to AGREED: production's
divergences need populations a small narrative does not contain.

`Q09`, `Q02`, `Q07` should **not** move — they diverge only where a
correction or reversal exists, and this narrative has neither. That is the
sharpest test here: it is the one place where copying the previous
dataset's declaration would be wrong.

`Q20` (ADR and RevPAR) moved on `DS-ACT-INHOUSE` and not on the other two.
Two occupied rooms across one night may or may not reproduce that;
**this is the prediction's weakest point and it is stated as such.**

---

## The risk

The declaration is written before measuring, so anything above may be
wrong. The two most likely places, in order: `Q20`, and whether a group
booking pulls any further quantity into or out of coverage. Recorded now so
that whichever way it goes it is not read as hindsight.
