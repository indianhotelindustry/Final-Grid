# Production Initialization Report

Generated 2026-08-08T18:47:53 — `pms.db`

**Result: SUCCESS**

**Target: NOT the default production database** — this report describes a run against `C:\Users\SIPLSE~1\AppData\Local\Temp\claude\C--Users-SIPL-Server\67f43bac-9be8-4199-94ba-93357d88e303\scratchpad\demo\pms.db`, which is a copy. It is a specimen of what the tool produces, not a record of production having been initialized.

| | |
|---|---|
| Database | `C:\Users\SIPLSE~1\AppData\Local\Temp\claude\C--Users-SIPL-Server\67f43bac-9be8-4199-94ba-93357d88e303\scratchpad\demo\pms.db` |
| Business date set to | **2026-08-08** |
| Tables classified | 53 |
| Tables preserved | 14 |
| Tables cleared | 39 |
| Rows removed | **437** |
| Rows preserved | **187** |
| Execution time | 1.87s |

## Backup

| | |
|---|---|
| Snapshot | `C:/Users/SIPLSE~1/AppData/Local/Temp/claude/C--Users-SIPL-Server/67f43bac-9be8-4199-94ba-93357d88e303/scratchpad/demo/backups\20260808_184753\pms_before_initialize.db` |
| Source SHA-256 | `d630f730a91133916ee3f76878c2cdd2b7930ec9ad745e571f81be78cdd08413` |
| Backup SHA-256 | `d630f730a91133916ee3f76878c2cdd2b7930ec9ad745e571f81be78cdd08413` |
| Source bytes | 733,184 |
| Backup bytes | 733,184 |
| Integrity | ok |
| Row counts match | True |
| Rows captured | 624 across 53 tables |

The two SHA-256 values are recorded, not compared. The backup API produces a logically identical database that need not be byte-identical — page layout may differ. Equivalence is established by integrity_check plus a per-table row-count match, which is the stronger claim.

## Verification

| Check | Result | Detail |
|---|---|---|
| no transactional rows remain | PASS | 39 table(s) cleared |
| master tables preserved | PASS | 12 master table(s), 129 rows |
| schema_migrations preserved | PASS | 57 rows |
| foreign keys valid | PASS | no orphan references |
| integrity check passes | PASS | ok |
| business date initialized | PASS | business date = 2026-08-08 |
| exactly one business date row | PASS | 1 row(s) |
| application boots successfully | PASS | BOOT-OK 2026-08-08 |

## Warnings

- **audit_logs** (71 rows removed) — The general audit trail is the compliance record of who did what. Clearing it is correct for a fresh environment and irreversible for the old one — the pre-initialization backup is the only remaining copy.
- **foreign_national_info** (0 rows removed) — Immigration records may carry a statutory retention period independent of this system. Confirm before discarding the backup.
- **guest_id_documents** (0 rows removed) — Identity documents. Clearing is the correct data-protection outcome; confirm the backup is held under the same controls as the live database.
- **night_audit_logs** (1 rows removed) — Frozen night-audit snapshots are release evidence under Phase 2.6 §13 and immutable under P12. They survive only in the backup.

## Every table

| Table | Classification | Action | Rows before | Rows after | Reason |
|---|---|---|---|---|---|
| `audit_logs` | TRANSACTION | Cleared | 71 | 0 | The general audit trail. Cleared because it records activity that will not exist. THE TOOL WARNS ON THIS — see CLEARED_WITH_WARNING. |
| `backup_logs` | TRANSACTION | Cleared | 0 | 0 | History of backups taken by the application. |
| `business_date` | SYSTEM | Reinitialized | 1 | 1 | The PMS operating date. The one table that is neither preserved nor cleared but REINITIALIZED — set to today and unlocked. |
| `checkin_records` | TRANSACTION | Cleared | 28 | 0 | Check-in events. |
| `cico_charge_logs` | TRANSACTION | Cleared | 3 | 0 | Check-in/check-out charge audit entries. |
| `companies` | MASTER | Preserved | 0 | 0 | Corporate accounts and travel agents, with credit limits. A counterparty ledger, not a transaction. |
| `credit_notes` | TRANSACTION | Cleared | 0 | 0 | Credit issued against an invoice. |
| `credit_voucher_redemptions` | TRANSACTION | Cleared | 0 | 0 | Voucher usage. NOT classified by reset_transactional_data.py. |
| `credit_vouchers` | TRANSACTION | Cleared | 0 | 0 | Vouchers issued to guests. NOT classified by reset_transactional_data.py. |
| `equipment` | MASTER | Preserved | 0 | 0 | Maintenance asset register, keyed to rooms. The assets themselves, not work done on them. |
| `equipment_health_logs` | TRANSACTION | Cleared | 0 | 0 | Readings against equipment. The readings, not the equipment. |
| `extra_charges` | TRANSACTION | Cleared | 5 | 0 | Charges posted to a folio. |
| `folios` | TRANSACTION | Cleared | 28 | 0 | The bill a stay is invoiced on. |
| `foreign_national_info` | TRANSACTION | Cleared | 0 | 0 | Form C / immigration data per guest. Same reasoning. |
| `group_blocks` | TRANSACTION | Cleared | 0 | 0 | A group booking. A sale, despite looking configuration-shaped. |
| `guest_feedback` | TRANSACTION | Cleared | 0 | 0 | Feedback against a stay. |
| `guest_id_documents` | TRANSACTION | Cleared | 0 | 0 | Identity documents captured at check-in. Also a data-protection reason to clear rather than retain. |
| `guests` | TRANSACTION | Cleared | 28 | 0 | Guest records created per stay. Not a master in this schema — there is no separate guest profile table, so a guest exists because a stay did. See --preserve-guests for the CRM case. |
| `loyalty_config` | MASTER | Preserved | 3 | 3 | Loyalty programme parameters. |
| `loyalty_milestones` | MASTER | Preserved | 3 | 3 | Loyalty tier definitions. |
| `loyalty_redemptions` | TRANSACTION | Cleared | 0 | 0 | Points redeemed against a stay. |
| `loyalty_transactions` | TRANSACTION | Cleared | 0 | 0 | Points earned and spent. |
| `maintenance_requests` | TRANSACTION | Cleared | 0 | 0 | Work raised against a room. The work, not the asset. |
| `night_audit_logs` | TRANSACTION | Cleared | 1 | 0 | Closed business days and their frozen snapshots. A new pilot has no audit history. |
| `night_audit_reopen_logs` | TRANSACTION | Cleared | 0 | 0 | Reopen events against closed days. |
| `no_show_logs` | TRANSACTION | Cleared | 0 | 0 | No-show events and their charges. |
| `notification_logs` | TRANSACTION | Cleared | 56 | 0 | Record of notifications already sent, keyed to a reservation. History of activity, unlike notification_queue which is the pending work itself. |
| `notification_queue` | TEMPORARY | Cleared | 28 | 0 | Outbound work queue. Anything undelivered refers to stays that will not exist after the reset. |
| `ota_payouts` | TRANSACTION | Cleared | 0 | 0 | Remittances received from channels. NOT classified by reset_transactional_data.py. |
| `overpayment_logs` | TRANSACTION | Cleared | 2 | 0 | Recorded guest overpayments. |
| `payment_modes` | MASTER | Preserved | 12 | 12 | Settlement heads and their categories (direct_payment, ota_receivable). Chart of accounts for money in. |
| `payments` | TRANSACTION | Cleared | 35 | 0 | Money received against a stay. |
| `pos_items` | MASTER | Preserved | 8 | 8 | Sellable item catalogue with prices. A menu master. |
| `precheckin_submissions` | TRANSACTION | Cleared | 0 | 0 | Guest-submitted pre-arrival data. |
| `precheckin_tokens` | TEMPORARY | Cleared | 0 | 0 | Short-lived guest links. Expire by design and are meaningless once their reservation is gone. |
| `preventive_schedules` | MASTER | Preserved | 0 | 0 | Maintenance schedules against equipment. A plan, not an event. |
| `rate_plans` | MASTER | Preserved | 0 | 0 | Tariff plans against room types. Pricing configuration, not a sale. |
| `reservation_night_rates` | TRANSACTION | Cleared | 30 | 0 | Priced room nights. The revenue source. |
| `reservation_passengers` | TRANSACTION | Cleared | 0 | 0 | Occupants of a stay. |
| `reservation_rooms` | TRANSACTION | Cleared | 28 | 0 | Room allocation per stay. NOT classified by reset_transactional_data.py, which is why 28 orphans would survive that tool. |
| `reservations` | TRANSACTION | Cleared | 28 | 0 | The booking. Root of the activity graph. |
| `revenue_alerts` | TEMPORARY | Cleared | 0 | 0 | Generated advisory output. Regenerated from data that is about to be removed. |
| `room_types` | MASTER | Preserved | 3 | 3 | Room type catalogue and base tariff. Referenced by rooms, rate plans and reservations; references nothing. |
| `rooms` | MASTER | Preserved | 39 | 39 | The physical rooms. References only room_types. A hotel does not lose its rooms when it stops trading. |
| `schema_migrations` | SYSTEM | Preserved | 57 | 57 | Applied migration versions. Preserved verbatim: clearing it would make the application re-run every migration against an already-migrated schema. |
| `settings` | MASTER | Preserved | 60 | 60 | Hotel profile, tax policy, GST regime, printers and every operational switch. The single most important table to preserve. |
| `shift_adjustments` | TRANSACTION | Cleared | 0 | 0 | Float and payout movements within a shift. |
| `shifts` | TRANSACTION | Cleared | 0 | 0 | Front-desk cash shifts. |
| `staff_performance_daily` | TRANSACTION | Cleared | 0 | 0 | Derived daily staff statistics. |
| `tax_lines` | TRANSACTION | Cleared | 66 | 0 | GST raised per charge. Derived from activity. |
| `users` | MASTER | Preserved | 1 | 1 | Operator accounts, roles and permissions. Clearing these would lock the hotel out of its own system. |
| `void_requests` | TRANSACTION | Cleared | 0 | 0 | Requests to void a payment. |
| `webhook_logs` | TRANSACTION | Cleared | 0 | 0 | Inbound and outbound integration traffic. |

## Rollback

```
# stop the application first
copy "C:/Users/SIPLSE~1/AppData/Local/Temp/claude/C--Users-SIPL-Server/67f43bac-9be8-4199-94ba-93357d88e303/scratchpad/demo/backups\20260808_184753\pms_before_initialize.db" "C:\Users\SIPLSE~1\AppData\Local\Temp\claude\C--Users-SIPL-Server\67f43bac-9be8-4199-94ba-93357d88e303\scratchpad\demo\pms.db"
```

The snapshot is a complete database, verified by `integrity_check` and a per-table row-count match at the moment it was taken. Restoring it returns the system to the exact state before this run.
