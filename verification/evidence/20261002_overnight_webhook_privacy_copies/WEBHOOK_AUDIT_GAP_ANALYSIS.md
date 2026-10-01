# Webhook audit gap analysis

| | |
|---|---|
| Date | 2026-10-02 |
| Kind | Analysis only. No code, schema, data, setting or git change was made. The application was not started and `app` was not imported. Production (`SukoonPMS/`, `instance/pms.db`) was not opened. |
| Code analysed | `origin/main` = `c9eeff0`. `app/` is byte-identical at `0ae01bc` (the `overnight-20261002` head at the time of writing): `git diff --stat c9eeff0 0ae01bc -- app/` is empty. |
| Method | Static reading of `app/webhook.py` and everything it calls, plus the evidence packs that already characterised the webhook at runtime. Line numbers below are at `c9eeff0`. |
| Decisions | `WEBHOOK_DECISION_REQUIRED.md` (WH-D1…WH-D6) |

## 1. Where the "webhook audit gaps" are already documented

| Source | What it records |
|---|---|
| `verification/evidence/20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:41` | `webhook._write_audit` (`modify_booking`) wrote actor **0**, hard-coded. Classed as "no financial row; changes `rate_per_night` / dates". **armed**: `webhook_api_key` is set in production Settings, and 0 calls had been received. |
| same file `:42` | `new_booking` / `cancel_booking`: "**no AuditLog at all**; only `WebhookLog` (pruned after 90 days by `log_pruning_job`)". |
| same file `:55` | Runtime characterisation at `3efdd2b`. F1: "rate change committed with no audit row (HTTP 200)". F2: whole request fails (HTTP 500). FK on with actor 0: OTA modifications cannot complete. |
| same file `:110`, `:115`, `:120-123` | The webhook is called "an unattended non-financial writer". The package asks for a representation or an explicit exemption, and lists the non-strict modify audit, the absence of an AuditLog on new/cancel, and the 90-day WebhookLog pruning as open items. |
| `.../20260930_adr011_system_action_provenance/characterisation_3efdd2b.json:53-81` | `S3-ACTOR` (actor=0), `S3-RED-F1` (state `(1500.0, 0)`, HTTP 200, "swallowing _write_audit"), `S3-FK-completes` (HTTP 500). All three have severity `finding`. |
| `.../20260930_cf10_completion/CF10_COMPLETION.md:73` | `webhook._write_audit` relies on the 0 convention and was "not exercised here" (outside CF-10). |
| `.../20260930_adr011_implementation/ADR011_ANALYSIS.md:16,22` | After ADR011-SA the webhook writes SYSTEM, `webhook`, no user. "webhook `modify_booking` audit remains non-strict (F1 still commits an unaudited rate change); webhook `new_booking` / `cancel_booking` still write no AuditLog". Recorded as out of scope and still open. |
| `.../20260930_adr011_implementation/ADR011_IMPLEMENTATION.md:20,41` | `app/webhook.py` is SYSTEM, `webhook`, no user (was 0). The modify path now completes with FK on. "(non-strict writer unchanged — out of scope)". |
| `.../20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:40-41,129` | The webhook completes under FK enforcement as a SYSTEM row. §6 item 6 lists "classification of the webhook audit gaps" under **Carried over, still open**. |
| `.../20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:78,105` | Identity suite: the webhook writes a SYSTEM row. "The recorded carry-overs: webhook audit gaps, …". |
| `verification/FOUNDER_DECISIONS.md:1287` | ADR011-SA governance effect: the `0` convention in `webhook._write_audit` is non-compliant. This has since been implemented (see §2). |

No entry in `verification/FOUNDER_DECISIONS.md` rules on the webhook gaps themselves. `grep -n -i webhook` finds only lines 1143 (FD-P2-02: WebhookLog pruning unchanged) and 1287.

## 2. How `_write_audit` represents the actor after ADR-011

- `app/webhook.py:348-370`. `_write_audit` builds `AuditLog(... staff_user_id=None, actor_kind='SYSTEM', actor_mechanism='webhook', ip_address=request.remote_addr ...)`, adds it and calls `flush()`. Any exception is logged (`:366-370`) and **swallowed**: "Never raises -- audit failures are non-fatal" (`:349`).
- `app/models.py:1066-1085`. `staff_user_id` is nullable. CHECK `ck_audit_actor_identity` requires HUMAN ⇒ user, and SYSTEM ⇒ no user plus a mechanism. `ck_audit_actor_not_zero` forbids 0.
- `app/models.py:1089-1121`. The `before_insert` listener keeps a row that declares `actor_kind == 'SYSTEM'` as SYSTEM and forces `staff_user_id = None` (`:1100-1103`). It does **not** consult the logged-in user for such a row. `app.audit_actor.resolve` is used only for non-SYSTEM rows.
- The webhook does not use `audit_actor.system_action(...)` (`app/audit_actor.py:37-50`). It hard-codes the SYSTEM identity in the row.
- Runtime evidence, GREEN only. `S3-GREEN-FK` / `S3-GREEN-noFK` show "modify completes; one SYSTEM row, no user, mechanism webhook", `(200, 1500.0, [('SYSTEM', None, 'webhook')])`. Sources: `20260930_adr011_implementation/results_3ffeba5.json:279-297`, `20260930_adr011_preprod_gate/preprod_final.json:431-448`, and `20260930_adr011_production_application/preprod_apply_post_ident.json:199-215`. All **PASS**.
- The RED case `S3-RED-F1` (audit failure) was run only at `3efdd2b`, before ADR-011. It is absent from the three post-ADR-011 result files above. Post-ADR-011 runtime status: **NOT VERIFIED**. Statically, the swallowing code at `webhook.py:366-370` is unchanged, so the F1 path still exists in the code.

## 3. Entry points that reach the webhook writers

| Entry | File:line | Who triggers it | Authentication |
|---|---|---|---|
| `POST /webhook/booking`, dispatching on `event` | `app/webhook.py:125-145` | channel manager / OTA (unattended) | `X-API-Key` plus an optional HMAC (`:55-69`). The blueprint is CSRF-exempt (`app/__init__.py:303-304`). |
| `POST /ota/webhook/retry/<log_id>` re-runs `_handle_new_booking` / `_handle_cancel` / `_handle_modify` on the stored `raw_payload` | `app/ota.py:728-764` (import at `:746`) | **logged-in Admin/Manager** (`@login_required`, role check `:731-732`) | session |

## 4. Write paths

"Financial?" below is a description of what the row is. It is **not** a governance classification. Classification is the open question WH-D1.

| # | Path | File:line | Entity (table) and fields written | Financial? (descriptive) | AuditLog written? | Same transaction as the mutation? | Actor representation | Existing evidence |
|---|---|---|---|---|---|---|---|---|
| WP-01 | Every inbound call: `_log` | `webhook.py:76-91` (flush `:88`, no commit) | `webhook_logs`: source, event_type, `raw_payload` (includes guest name/phone/email), status, IP | no | n/a (this is the integration log) | flushed into the handler's transaction and committed by the handler's commit | none (no actor column) | Production `webhook_logs` = 0 rows at 2026-09-30 13:23 and 13:25 (`20260930_adr011_production_application/backup_pre_manifest.json:60`, `backup_post_manifest.json:60`). Pruned after 90 days (`app/__init__.py:547-566`; FD-P2-02 `FOUNDER_DECISIONS.md:1143` leaves it unchanged). |
| WP-02 | Unknown event | `webhook.py:140-145` | `webhook_logs.status='failed'` | no | no | n/a | none | none |
| WP-03 | `new_booking`, duplicate OTA id | `webhook.py:172-184` | `webhook_logs.status='skipped'`, `reservation_id` | no | no | n/a | none | none |
| WP-04 | `new_booking`, guest find-or-create | `webhook.py:196-208` | `guests` INSERT (name, first/last, phone, email) **or** `Guest.set_name` backfill on an existing guest matched by phone | no (personal data) | **no** | n/a | none | `ADR011_DECISION_REQUIRED.md:42` ("no AuditLog at all") |
| WP-05 | `new_booking`, reservation create | `webhook.py:210-265` (construct `:232-249`, flush `:259`, commit `:265`) | `reservations` INSERT: `rate_per_night` (payload, else `rates.resolve_rate_for_reservation` `:240-241`, a read-only resolver), `advance_payment=0`, `status='Confirmed'`, `source='OTA'`, `ota_payment_status` (`paid_at_ota` / `pay_at_hotel`, `:215-218`), `ota_channel`, `ota_booking_id`, dates, occupancy | Not one of the 24 inventoried financial writers. Those are the Payment/ExtraCharge constructors (`20260908_phase1_implementation_readiness/FINANCIAL_WRITER_INVENTORY.md:3-5`). But `rate_per_night` is the room-rent basis used by night audit (`services.py:400-401`, legacy fallback) and by invoice room accommodation (`services.py:2402`). | **no** | n/a. The only record is `webhook_logs.status='processed'` with `reservation_id` (`:261-263`) in the same commit. | none | `ADR011_DECISION_REQUIRED.md:42`; `ADR011_ANALYSIS.md:22` |
| WP-06 | `new_booking`, default Folio A | `models.py:745-761` (`after_insert` listener on `Reservation`) | `folios` INSERT (letter A, label Guest) | A folio container; recorded as **L-01**, outside the 24 writers, audit "none" (`FINANCIAL_WRITER_INVENTORY.md:42`) | **no** | same flush/transaction as WP-05 (listener uses `connection.execute`) | none | inventory L-01 only; not discussed for the webhook in any pack |
| WP-07 | `new_booking` / `cancel_booking`, post-commit notifications | `webhook.py:267-272`, `:329-334` → `notifications.notify_ota_booking` / `notify_booking_cancelled` (`notifications.py:459-498`) → `_fire` thread (`:203-205`) | `notification_logs` (`_log_notification` `:123-139`) / `notification_queue` (`_enqueue` `:146-168`), each in its own commit in a background thread | no | no | separate transaction, after the business commit | none | The warning at `notifications.py:196` and the info line at `:166` log the destination phone number. That is the origin of the git-history exposure (`GIT_HISTORY_PRIVACY_DECISION.md`). |
| WP-08 | `cancel_booking` | `webhook.py:298-336` (mutation `:323`, commit `:327`) | `reservations.status='Cancelled'` | No financial row is written. Observed: the operator route cancels through `services.post_cancellation_disposition` (`services.py:1692`) and a strict `Reservation`/`cancelled` audit in the same transaction (`routes.py:8853-8879`). The webhook path does neither, and only `CheckedIn`/`CheckedOut` are refused (`:316`). | **no** | n/a | none | `ADR011_DECISION_REQUIRED.md:42` |
| WP-09 | `cancel` / `modify`: not found, status conflict, validation failure | `webhook.py:309-321`, `:384-398`, `:427-433` | `webhook_logs.status='failed'` | no | no | n/a | none | none |
| WP-10 | `modify_booking` | `webhook.py:373-475` (mutation `:446-457`, audit `:468`, commit `:473`) | `reservations`: `arrival_date`, `departure_date`, `adults`, `children`, `rate_per_night`, `special_requests` | Same description as WP-05. `rate_per_night` can change. `reservation_night_rates` rows are not touched (static; whether OTA rows carry any is **NOT VERIFIED**). | **yes**: `AuditLog(entity_type='Reservation', action='webhook_modify', before_state/after_state` of the six fields, `:435-468`) | **Yes when the audit flush succeeds** (flush `:365`, then a single commit `:473`). **Not strict:** an exception in `_write_audit` is swallowed. F1 commits the rate change with no audit row (`characterisation_3efdd2b.json:63-71`, at `3efdd2b`). Post-ADR-011 **NOT VERIFIED**; the path still exists statically. | SYSTEM, `staff_user_id` NULL, `actor_mechanism='webhook'`, `ip_address` of the caller | GREEN **PASS** at `3ffeba5`, the preprod gate and the apply rehearsal (§2). F1 **FAIL** at `3efdd2b`. FK-on completion **PASS** after ADR-011 (`ADR011_IMPLEMENTATION.md:41`). |
| WP-11 | Exception handlers | `webhook.py:281-295`, `:338-345`, `:477-484` | `db.session.rollback()`, then `log.status='failed'`, `log.error_message`, `commit()` | no | no | see finding F-3 | none | none |
| WP-12 | Operator retry of a stored payload | `ota.py:728-764` → WP-03…WP-10 | as WP-03…WP-10 | as above | as above: `modify` writes one AuditLog; `new`/`cancel` write none | as above | **SYSTEM / `webhook` / no user, although a logged-in Admin/Manager initiated it.** `_write_audit` hard-codes SYSTEM (`webhook.py:359-361`), and the listener keeps SYSTEM rows SYSTEM (`models.py:1100-1103`). The operator's id is not recorded; `ip_address` is the operator's. `webhook_logs` has no user column. | none; never exercised in any pack |

Adjacent, outside `app/webhook.py`: the operator OTA cancel `ota.py:671-690` (`cancel_booking`, def at `:673`) also sets `status='Cancelled'` and commits with no AuditLog and no disposition. It is recorded here only because it writes the same entity. It is not a webhook path.

## 5. Findings

| ID | Finding | Basis | Status |
|---|---|---|---|
| F-1 | `new_booking` creates a guest, a reservation with a rate and an OTA payment status, and a Folio A, all with **no AuditLog**. The only record is `webhook_logs`, which is pruned after 90 days. | static `webhook.py:196-265`, `models.py:745-761`; documented `ADR011_DECISION_REQUIRED.md:42` | Gap documented. Classification under Q5-P1: **OPEN** (WH-D1). |
| F-2 | `cancel_booking` changes the reservation status with **no AuditLog** and without the cancellation disposition that the operator path requires. | static `webhook.py:323-327` vs `routes.py:8853-8879` | Gap documented (AuditLog). The disposition bypass is not previously recorded. **OPEN** (WH-D1, WH-D6). |
| F-3 | **Suspected defect (static).** `_log` flushes the `WebhookLog` without committing it (`webhook.py:87-88`). On every exception path the handler first calls `db.session.rollback()` (`:282`, `:289`, `:339`, `:478`), and that also rolls back the `WebhookLog` INSERT. Under SQLAlchemy 2.x (Flask-SQLAlchemy 3.1.1, `requirements.txt:2`), an object whose INSERT is rolled back is expunged from the session. The following `log.status='failed'; db.session.commit()` therefore appears to persist nothing, so a webhook call that ends in an exception (malformed date, missing field, DB error) would leave **no `webhook_logs` row at all**. A retried log loaded from the database (WP-12) is not affected. No business data is left behind, because everything is rolled back. | static reading only | **NOT VERIFIED.** Needs a bounded runtime check on a copy (WH-D5). |
| F-4 | `modify_booking` audit is in the same transaction but is not strict. F1 commits a `rate_per_night` change with no audit row. | `characterisation_3efdd2b.json:63-71`; code unchanged `webhook.py:366-370` | **FAIL** at `3efdd2b` (pre-ADR-011). Post-ADR-011 **NOT VERIFIED**. Classification **OPEN** (WH-D1/WH-D2). |
| F-5 | An operator-initiated retry is recorded as SYSTEM/`webhook` with no user. ADR011-SA requires audit_logs to distinguish "human/operator initiated action" from "system/scheduled action" (`FOUNDER_DECISIONS.md:1275-1276`). Whether a retry is a human or a system action is not ruled. | static `ota.py:728-764`, `webhook.py:359-361`, `models.py:1100-1103` | **OPEN** (WH-D3). Not exercised at runtime: **NOT VERIFIED**. |
| F-6 | The production webhook is armed and had received no calls when last measured. | `ADR011_DECISION_REQUIRED.md:41-42`; `webhook_logs` = 0 in the 2026-09-30 13:23/13:25 manifests | Current production state: **NOT VERIFIED** (production not opened). |

## 6. Does existing governance text already decide whether these gaps violate Q5-P1?

**No.** These are the relevant texts, quoted. None of them classifies the webhook paths.

- Q-5, `FOUNDER_DECISIONS.md:1031-1033`: "APPROVED: Strict audit coupling for Phase 1 financial writers that are touched by implementation. For affected financial operations: financial mutation and its required audit record must succeed or the operation must fail/roll back according to the transaction boundary."
- Q5-P1, `FOUNDER_DECISIONS.md:1078`: "ALL FINANCIAL MUTATIONS SHOULD SATISFY STRICT AUDIT COUPLING. Do NOT weaken Q-5."
- `FOUNDER_DECISIONS.md:1080` names the writer set it was applied to: "strict coupling proven at 12 of 24 writers … The 12 non-strict writers (W-08 … W-24 none) become CF-10". The 24 writers are the Payment/ExtraCharge constructors of `FINANCIAL_WRITER_INVENTORY.md:3-5`. The webhook constructs neither. The folio listener L-01 is listed separately (`:42`).
- Analysis text, not a ruling: `ADR011_DECISION_REQUIRED.md:110` calls the webhook "an unattended non-financial writer", and `:41-42` say "no financial row".
- The preprod gate report keeps "classification of the webhook audit gaps" open (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:129`). The production application report lists "webhook audit gaps" as a carry-over (`ADR011_PRODUCTION_APPLICATION_REPORT.md:105`).

So Q5-P1 covers "ALL FINANCIAL MUTATIONS", and nothing rules whether a webhook change to `rate_per_night`, `ota_payment_status`, reservation status, or the creation of Folio A is a "financial mutation". That classification is a Founder decision (WH-D1). This analysis does not decide it.

## 7. Status summary

| Item | Status |
|---|---|
| Webhook audit row is SYSTEM, has no user, mechanism `webhook` (inbound path) | **PASS** (runtime, three packs) |
| Modify audit written in the same transaction (GREEN) | **PASS** |
| Modify audit strict under audit failure (F1) | **FAIL** at `3efdd2b`; **NOT VERIFIED** after ADR-011 |
| AuditLog for `new_booking` / `cancel_booking` | none (static). Requirement **OPEN**. |
| Q5-P1 classification of the webhook writes | **OPEN**. Founder decision required. |
| Retry provenance (WP-12) | **OPEN** / **NOT VERIFIED** |
| `webhook_logs` survives exception paths (F-3) | **NOT VERIFIED** (suspected defect) |
| Production webhook armed / call count now | **NOT VERIFIED** |
