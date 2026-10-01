# Webhook audit gaps: decisions required

Analysis basis: `WEBHOOK_AUDIT_GAP_ANALYSIS.md` (same directory), code at `c9eeff0`. Nothing below has been decided, implemented or configured. Every item is **OPEN**.

| ID | Question (one line) | Status |
|---|---|---|
| WH-D1 | Are the webhook's reservation and folio writes "financial mutations" under Q5-P1, and if so, which ones? | OPEN |
| WH-D2 | What audit behaviour is required for each webhook path (strict / same-transaction non-strict / none)? | OPEN |
| WH-D3 | Is an operator-triggered webhook retry a HUMAN or a SYSTEM action in `audit_logs`? | OPEN |
| WH-D4 | Does the production webhook stay armed while WH-D1/WH-D2 are open? | OPEN |
| WH-D5 | Is a bounded runtime verification on a copy authorized (post-ADR-011 F1, WebhookLog on exception paths, retry provenance)? | OPEN |
| WH-D6 | Must an OTA cancellation go through the cancellation-disposition path that operator cancellations use? | OPEN |

---

## WH-D1 — Q5-P1 classification of webhook writes

- **DECISION ID:** WH-D1
- **DATE DISCOVERED:** 2026-10-02. The underlying gap has been carried over since 2026-09-30 (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:129`).
- **WORKSTREAM:** CF-10 / Q5-P1 audit coupling; ADR-011 carry-overs
- **QUESTION:** Q5-P1 reads "ALL FINANCIAL MUTATIONS SHOULD SATISFY STRICT AUDIT COUPLING" (`FOUNDER_DECISIONS.md:1078`). Are any of these webhook writes a financial mutation within it?
  - (i) `new_booking` creating a reservation with `rate_per_night`, `advance_payment=0` and `ota_payment_status` (`webhook.py:232-249`);
  - (ii) the automatic Folio A created with it (`models.py:745-761`, inventory L-01);
  - (iii) `modify_booking` changing `rate_per_night` / dates / occupancy (`webhook.py:446-457`);
  - (iv) `cancel_booking` changing status to `Cancelled` (`webhook.py:323`).
- **WHY REQUIRED:** Q5-P1 was applied to the 24 Payment/ExtraCharge writers (`FOUNDER_DECISIONS.md:1080`; `FINANCIAL_WRITER_INVENTORY.md:3-5`). The webhook writes none of those row types. Analysis packs call it "non-financial" (`ADR011_DECISION_REQUIRED.md:41-42,110`), but no Founder text rules on it. The preprod gate and production application reports carry the classification as open (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:129`, `ADR011_PRODUCTION_APPLICATION_REPORT.md:105`). `rate_per_night` is the room-rent basis used by night audit and invoicing (`services.py:400-401`, `:2402`).
- **OPTIONS:**
  - (a) **All four in scope.** Q5-P1 applies to (i)–(iv). Each needs an audit row that is strictly coupled to its mutation.
  - (b) **Monetary attributes only.** In scope: (i) and (iii) where `rate_per_night` / `ota_payment_status` is set or changed. Out of scope: (ii) and (iv), which get audit requirements under a separate rule or none.
  - (c) **Not financial.** None is a financial mutation under Q5-P1. The webhook's audit requirement, if any, is set by a separate provenance/audit rule (e.g. under ADR-011 or AR-007), or it is explicitly exempted with `webhook_logs` as its record.
  - (d) **Defer.** Classify when channel-manager integration is scheduled for activation, and record the gap as accepted until then (see WH-D4).
- **EVIDENCE:** `WEBHOOK_AUDIT_GAP_ANALYSIS.md` §4 (WP-04…WP-10) and §6; `FOUNDER_DECISIONS.md:1031-1033,1078,1080`; `FINANCIAL_WRITER_INVENTORY.md:3-5,42`; `ADR011_DECISION_REQUIRED.md:41-42,110,120-123`.
- **DEPENDENCIES:** none to decide. WH-D2 depends on this item.
- **WHAT IS BLOCKED:** closure of the "webhook audit gaps" carry-over (G5 provenance envelope, `ADR011_PRODUCTION_APPLICATION_REPORT.md:101,105`); any webhook audit change; WH-D2.
- **WHAT CAN CONTINUE:** all other workstreams. The operator-path financial writers are unaffected (CF-10 delivered). Night audit stays manual (FD-P2-05).
- **EXACT ACTION AFTER DECISION:** record the ruling verbatim in `verification/FOUNDER_DECISIONS.md`, naming which of (i)–(iv) are in scope. If any are in scope, open a bounded directive in the style of CF-10 (red/green on copies) for those paths. If (c) or (d), record the exemption or deferral and the record of reference (`webhook_logs`, with its 90-day pruning stated).

## WH-D2 — Required audit behaviour per webhook path

- **DECISION ID:** WH-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** CF-10 / Q-5 audit coupling (webhook)
- **QUESTION:** For each path that WH-D1 places in scope, or that the Founder wants audited anyway, which audit behaviour applies?
- **WHY REQUIRED:** Today `modify` writes an audit row in the same transaction, but `_write_audit` swallows failures (`webhook.py:349,366-370`). F1 committed a rate change with no audit row at `3efdd2b` (`characterisation_3efdd2b.json:63-71`). `new_booking` and `cancel_booking` write no audit row. Strict coupling would turn an audit failure into HTTP 500 for the channel manager, which then depends on the channel manager's retry behaviour. That retry behaviour is not documented in the repository (**NOT VERIFIED**).
- **OPTIONS:**
  - (a) **Strict.** The audit row must be written or the whole webhook transaction rolls back (HTTP 500), as at the CF-10 writers. Applies to every path WH-D1 places in scope.
  - (b) **Same-transaction, non-strict.** Keep the current `modify` behaviour and add the same kind of audit row to `new_booking` / `cancel_booking`.
  - (c) **Keep as is.** Audit on `modify` only, non-strict, with `webhook_logs` as the record for new/cancel.
  - (d) **Mixed.** Strict for rate/payment-status changes, non-strict or `webhook_logs` for the rest.
- **EVIDENCE:** `WEBHOOK_AUDIT_GAP_ANALYSIS.md` WP-05, WP-08, WP-10, F-1, F-2, F-4; `ADR011_ANALYSIS.md:22`; `ADR011_IMPLEMENTATION.md:41`.
- **DEPENDENCIES:** WH-D1. The `webhook_logs` retention period is governed by FD-P2-02, which leaves it unchanged (`FOUNDER_DECISIONS.md:1143`), and by the ADR-012 retention design, which is not yet decided.
- **WHAT IS BLOCKED:** implementation of any webhook audit change.
- **WHAT CAN CONTINUE:** everything else.
- **EXACT ACTION AFTER DECISION:** record the ruling. Then issue a bounded implementation directive. It changes `app/webhook.py` only, adds red/green cases (audit-failure injection for each path, FK on and off) to a verification pack, and is run on copies only.

## WH-D3 — Provenance of an operator-triggered retry

- **DECISION ID:** WH-D3
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** ADR-011 / ADR011-SA provenance
- **QUESTION:** When a logged-in Admin/Manager re-runs a stored webhook payload (`POST /ota/webhook/retry/<log_id>`, `ota.py:728-764`), should `audit_logs` record it as HUMAN (that operator), as SYSTEM `webhook`, or as HUMAN with a mechanism that marks the replay?
- **WHY REQUIRED:** ADR011-SA requires audit_logs to distinguish "human/operator initiated action" from "system/scheduled action" (`FOUNDER_DECISIONS.md:1275-1276`). `_write_audit` hard-codes SYSTEM (`webhook.py:359-361`), and the insert listener keeps it SYSTEM (`models.py:1100-1103`), so the operator's identity is lost. A replayed `new_booking` / `cancel_booking` leaves no audit row at all.
- **OPTIONS:**
  - (a) **HUMAN.** Record the operator, with a mechanism such as `web:webhook_retry` that marks the replay.
  - (b) **SYSTEM.** Keep `webhook`. The retry is treated as the original system event, and the operator is recorded elsewhere (e.g. on `webhook_logs`, which would need a schema change).
  - (c) **Both.** A SYSTEM row for the replayed event plus a HUMAN row recording that the operator triggered the retry.
- **EVIDENCE:** `WEBHOOK_AUDIT_GAP_ANALYSIS.md` WP-12, F-5. The retry path is not exercised in any pack (**NOT VERIFIED**).
- **DEPENDENCIES:** ADR-011 formal adoption (G5) may absorb this. It is independent of WH-D1.
- **WHAT IS BLOCKED:** a complete ADR011-SA provenance statement for the webhook path.
- **WHAT CAN CONTINUE:** everything else.
- **EXACT ACTION AFTER DECISION:** record the ruling, then include the retry path in the WH-D2 implementation directive or the ADR-011 adoption reconciliation.

## WH-D4 — Production webhook armed while gaps are open

- **DECISION ID:** WH-D4
- **DATE DISCOVERED:** 2026-10-02. The underlying fact was recorded 2026-09-30.
- **WORKSTREAM:** production operating configuration (first release)
- **QUESTION:** While WH-D1/WH-D2 are open, does the production `webhook_api_key` stay set (endpoint accepts authenticated calls), or is the endpoint disarmed until the gaps are resolved?
- **WHY REQUIRED:** On 2026-09-30 the key was set in production Settings and 0 calls had been received (`ADR011_DECISION_REQUIRED.md:41-42`; `webhook_logs` = 0 in `backup_pre_manifest.json:60` / `backup_post_manifest.json:60`). An inbound call would create reservations/folios without an audit row (F-1). Reachability depends on the tunnel URL setting (`app/__init__.py:816,1919`), which is **NOT VERIFIED**. With an empty key the endpoint returns 503 (`webhook.py:61-62`).
- **OPTIONS:**
  - (a) Keep it armed and accept the documented gap.
  - (b) Disarm by clearing the key under a production-configuration authorization (PD-004/PD-005 as applicable).
  - (c) Keep it armed, add an operator procedure to review `webhook_logs`/OTA bookings daily, and accept the gap until WH-D2 is implemented.
- **EVIDENCE:** as above; `WEBHOOK_AUDIT_GAP_ANALYSIS.md` F-6.
- **DEPENDENCIES:** none. Option (b) is a production configuration change and needs its own authorization.
- **WHAT IS BLOCKED:** nothing technical.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the ruling. For (b), issue a production-configuration directive (backup, change, verification) carried out only within its window. For (a)/(c), record the accepted risk in the G11 deployment procedure.

## WH-D5 — Bounded runtime verification of the open webhook facts

- **DECISION ID:** WH-D5
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** verification (CF-10 / ADR-011 carry-overs)
- **QUESTION:** Is a bounded verification run authorized on a disposable copy (never `instance/`, never the live folder, from a worktree) for three things?
  - (1) F1 on `modify_booking` after ADR-011;
  - (2) whether a webhook call that ends in an exception leaves any `webhook_logs` row (suspected defect F-3);
  - (3) the actor recorded by an operator retry (F-5).
- **WHY REQUIRED:** All three are static findings or pre-ADR-011 results. F-3, if confirmed, means failed inbound calls leave no record at all.
- **OPTIONS:**
  - (a) Authorize (1)–(3) as a verification-only directive with no code change.
  - (b) Authorize only (1) and (2).
  - (c) Defer until WH-D1/WH-D2 are ruled, and verify as part of that implementation.
- **EVIDENCE:** `WEBHOOK_AUDIT_GAP_ANALYSIS.md` §2, F-3, F-4, F-5. Harness caution: harnesses boot with the production `.env` and reuse production guests, and the notification warning logs the destination phone (`ADR011_DECISION_REQUIRED.md:163`). Any run must use synthetic guests or stubbed notifications, and its logs must be scanned before commit.
- **DEPENDENCIES:** GH-D3 (harness privacy) in `GIT_HISTORY_PRIVACY_DECISION.md`.
- **WHAT IS BLOCKED:** turning F-3/F-4/F-5 from NOT VERIFIED into PASS/FAIL.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** write the verification script in a new evidence pack, run it on a copy from a worktree, scan its logs for production guest fields, and commit the pack with RESULT.json.

## WH-D6 — OTA cancellation and cancellation disposition

- **DECISION ID:** WH-D6
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** SR-2 / INV-D02 business semantics; CF-10 W-10
- **QUESTION:** Should an OTA cancellation received by webhook go through the same disposition path (`post_cancellation_disposition`, refund/forfeit/voucher, strict `cancelled` audit) as an operator cancellation, or is a status-only cancellation correct for OTA bookings?
- **WHY REQUIRED:** The webhook sets `status='Cancelled'` only (`webhook.py:323`) and refuses only CheckedIn/CheckedOut (`:316`). The operator route records a disposition and a strict audit in one transaction (`routes.py:8853-8879`). Static reading shows no guard against cancelling a Confirmed OTA reservation that carries operator-recorded advance payments. Whether such rows occur for OTA bookings in practice is **NOT VERIFIED**. `FOUNDER_DECISIONS.md:1094-1096` (SR-1/SR-2) says not to modify cancellation behaviour until resolved. SR-2 has since been ruled (FD-P2-06, SR2-RULE, SR2-REV2) for invariant semantics. No ruling mentions webhook cancellations.
- **OPTIONS:**
  - (a) Status-only is correct for OTA bookings (money is settled by the OTA). Record it as intended behaviour.
  - (b) A webhook cancel with recorded payments must be refused (HTTP 409) and left to an operator.
  - (c) A webhook cancel must call the disposition path with a default disposition named by the Founder.
- **EVIDENCE:** `WEBHOOK_AUDIT_GAP_ANALYSIS.md` WP-08, F-2; `services.py:1692`.
- **DEPENDENCIES:** SR-2 / FD-P2-06 semantics; WH-D1.
- **WHAT IS BLOCKED:** nothing currently running. Production had 0 webhook calls as of 2026-09-30.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the ruling. For (b)/(c), add the change to the WH-D2 implementation directive with red/green cases.
