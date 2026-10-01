# INV-D02 / SR-2 — revision 2 (2026-10-01)

Branch `sr2-inv-d02` (local only; **not pushed, not merged, `main` untouched**). Code commit `6e46e2c`, on top of `3fba926`. Verification framework only: no `app/`, schema, migration, production, K-7 or SR-1 change. Production SHA-256 `21dc0e97…` unchanged across every run; the application was never started against the live folder.

## Founder instructions and what was done

| Instruction | Result |
|---|---|
| A legitimate refund must not depend on the reservation's *current* status | `status == 'Cancelled'` removed from the rule. Status is no longer evaluated. |
| Determine whether existing data can establish the reservation was cancelled when the refund was generated | **Yes, without any app/schema change** — see below. |
| Audit is supporting evidence only | The rule does not read `audit_logs`. The real-writer test records the audit rows it produced as supporting evidence only. |
| Keep amount equality as a corroborating check; separate lineage from later correction/void activity | Amount mismatch is now a separately named failure (`consistency`). Lineage failures and the consistency failure carry different `expected` text. Voiding or correcting the refund afterwards is not examined. |
| Stop if history cannot be established | Not triggered; the remaining gap is stated below. |

## What the existing data establishes

- `reservations.cancellation_disposition / _amount_refunded / _processed_at / _processed_by_user_id / _refund_payment_id` are assigned in exactly one place (`services.py:1828-1836`, `post_cancellation_disposition`), in the **same transaction** as the refund row and, in its only caller (`routes.py cancel_reservation`), the status change.
- That caller refuses any reservation not in Reserved/Confirmed/Overbooked, so the snapshot cannot be re-run or overwritten for a cancelled reservation through the application.
- No application code clears these columns, edits a refund amount or removes the pointer. A void sets `is_voided` only; a correction adds new rows with `corrects_id`.
- The real writer (T2-APP): `corrects_id` NULL, `cancellation_processed_at` stamped, refund `created_at` ≤ `processed_at`, pointer set; supporting audit rows `cancellation_refund` (payment) and `cancellation_disposition` (reservation).

## Revised rule (INV-D02, cancellation refund)

Lineage holds when: exactly one reservation names the payment as `cancellation_refund_payment_id`; it is the refund's own reservation; its disposition is `refund_full`/`refund_partial`; and `cancellation_processed_at` is set (a processed cancellation is identifiable). Separately, `cancellation_amount_refunded` must equal the refund amount (consistency, named separately). Reservation, guest, folio or amount match alone is still not lineage. Ordinary corrections unchanged (resolving `corrects_id`, same reservation).

## Verification (only what the change can affect)

- `verify_sr2.py` at clean `6e46e2c`: **31/31** (previous round 21/21; the new cases are N1/N1b status later not Cancelled → HOLDS, N5 no `cancellation_processed_at` → FAIL, V1 refund voided later → HOLDS, V2 refund later corrected → HOLDS, V3 orphan correction → FAIL, N3/N5/V3 failure naming, T2-APP stamp and status-later). `sr2_final_6e46e2c.json`.
- `inv-commission` (full, new latest pack `20261001_120800_inv_commission`): INV-D02 PASS (8/8); only INV-R01 fails — pre-existing, declared NOT_COMMISSIONED, identical on unchanged `c703150`.
- `inv-run` production: no unbacked COMMISSIONED claim; INV-D02 VACUOUS (production has no correction/refund rows).
- `ds-run` 5/5 PASS; `ds-commission` PASS; VOIDCN still `synthetic-unreachable` with INV-D02 VIOLATED.
- `fault-run`: 40 challenged, 35 detected, 1 missed (FLT-C07), 4 uncovered — identical to the previous round and to `c703150`; FLT-B09 still detected. Verdict FAIL is pre-existing.
- Not re-run (rule change is confined to INV-D02): `gm-verify`, `replay-verify`, `cross-implementation`, application suites.
- Not run: the new test cases against the previous rule text (the previous rule's status check is visible in code and in the `3fba926` diff).

## Remaining gap (exact)

1. **Historical status is inferred, not observed.** The data model has no status history and no timestamped status change. "Cancelled when the refund was generated" is established by the write-once, same-transaction cancellation snapshot, not by a recorded status at that time. Observing status history directly would need an application or schema change; none is proposed.
2. **Write-once is enforced by application code, not by the database.** A direct database write could alter or stamp the snapshot columns; the rule would then accept a forged snapshot. Detecting that is beyond lineage on existing data (the audit trail could corroborate, by Founder instruction it is not the mechanism).
3. **Ordering is not checked.** The rule does not compare refund `created_at` with `cancellation_processed_at` (true for the real writer; hand-written rows may differ).
4. **Refunds predating the snapshot columns** would fail. None exist in production (no correction/reversal rows); other installations were not examined.
5. **Governance record.** `FOUNDER_DECISIONS.md` holds SR2-RULE verbatim; the revision-2 operationalisation above is not recorded as a Founder decision and awaits confirmation.
6. Correction of the earlier report: it said a later correction or void could make a refund fail the amount check. The code shows neither edits the refund row's amount; the revised rule is independent of both anyway.
