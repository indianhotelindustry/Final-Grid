# Production Initialization Framework

`tools/production_initialize.py` — prepares a FinalGrid database for pilot
or production use by **preserving every piece of configuration and removing
every piece of business activity**. The result behaves like a freshly
installed system that has already been fully configured.

Not a financial correction, a migration or a verification task. It changes
no schema object, no business logic and no application code.

---

## Usage

```bash
# See what would happen. This is the default — no flag means no change.
python tools/production_initialize.py --dry-run

# Apply.
python tools/production_initialize.py --confirm
```

| Flag | Effect |
|---|---|
| `--confirm` | Actually apply. **Without it the tool is a dry run** |
| `--db PATH` | Target a different database (default `instance/pms.db`) |
| `--business-date YYYY-MM-DD` | First production day (default: today) |
| `--preserve-guests` | Keep the `guests` table for CRM continuity |
| `--backup-dir PATH` | Where the pre-run snapshot goes. **Point this elsewhere when initializing a copy**, so rehearsals do not accumulate in the production backup store |
| `--no-boot-check` | Skip booting the application against a copy of the result |
| `--quiet` | Suppress progress output |

Exit codes: **0** success, dry run, or already initialized; **1**
verification failed; **2** aborted before any change.

## What it produces

```
db-backups/initialization/YYYYMMDD_HHMMSS/
    pms_before_initialize.db     complete verified snapshot
    manifest.json                hashes, row counts, integrity result
    report.md                    the run report
    result.json                  machine-readable record
PRODUCTION_INITIALIZATION_REPORT.md   the same report, at the repo root
```

The report states plainly whether it targeted the default production
database or a copy, so a specimen from a rehearsal cannot be mistaken for a
record of production having been initialized.

---

## Rollback

The snapshot is a complete database, verified at the moment it was taken by
`PRAGMA integrity_check` **and** a per-table row-count match against the
source. Restoring it returns the system to the exact state before the run.

```
1. Stop the application.
2. Copy db-backups\initialization\<STAMP>\pms_before_initialize.db
   over instance\pms.db
3. Restart.
```

Verify the restore before trusting it — a backup that has never been
restored is not a backup:

```bash
python -c "import sqlite3;c=sqlite3.connect('instance/pms.db');print([r[0] for r in c.execute('PRAGMA integrity_check')])"
```

If a run reaches phase 6 and **verification fails**, the tool exits non-zero
and names the snapshot path. The database has been changed at that point.
Restore it before using the system.

---

## The seven phases

| | Phase | What it does | Aborts if |
|---|---|---|---|
| 1 | Safety | `integrity_check`, snapshot via the SQLite backup API, verify the snapshot, hash both, write the manifest | source corrupt; backup missing, corrupt, or row counts differ |
| 2 | Classification | Classify every live table | **any table is unclassified**; a MASTER declares an FK into a cleared table |
| 3 | Preserve | Nothing — MASTER and SYSTEM tables are simply not touched | — |
| 4 | Reset | Delete TRANSACTION and TEMPORARY tables in FK-safe order, reset `sqlite_sequence` | any delete raises (the whole run rolls back) |
| 5 | Reinitialize | Business date = today, hotel unlocked | — |
| 6 | Verification | 8 checks including `foreign_key_check`, `integrity_check` and an application boot | any check fails |
| 7 | Report | Write report, manifest and machine-readable result | — |

### Why abort-on-unknown is not negotiable

`reset_transactional_data.py` ships with the application and classifies
tables for the same purpose. It has **no dynamic catch-all**, so four tables
it does not name survive a reset:

```
reservation_rooms, credit_vouchers, credit_voucher_redemptions, ota_payouts
```

`reservation_rooms` is the one that matters — 28 rows on production, every
one a child of a reservation the reset deletes, leaving orphaned room
allocations pointing at reservations that no longer exist. (Wave 0 finding,
`verification/datasets/schema.py`, `UNCLASSIFIED_BY_ADMIN_RESET`.)

All four are classified here. And **the first dry run of this tool aborted
on `notification_logs`** — a table its own author had missed. That is the
control working on the person who wrote it, and it is why there is no
default and no catch-all.

### Determinism

Deletion order is derived from the live foreign-key graph, not
hand-maintained, so a new child table cannot be deleted out of order because
someone forgot to update a list. The graph contains a genuine cycle
(`reservations` → `payments` → `reservations`); it is broken deterministically
by table name and recorded in the result. Correctness does not rest on the
order, because `PRAGMA foreign_key_check` runs afterwards and the run aborts
if it reports anything.

Two runs on identical inputs produce the same deletion order, the same rows
removed and identical resulting row counts.

### Idempotency

Running twice is safe. The second run removes zero rows, sets the business
date to the same value and reports `ALREADY INITIALIZED`.

### Why the boot check uses a copy

`create_app()` writes — migrations, the SQLite column fixer and
`init_data()` seeding all commit. Booting the delivered database to verify
it would change the thing being verified, so phase 6 boots a copy and
throws it away.

---

## Commissioning

**43 checks, 0 failed.** Evidence:
`verification/evidence/20260808_production_initialize_commission/`.

Production is never opened except read-only, and its SHA-256 is compared
before and after the whole run. Every case runs on a throwaway copy.

| Group | Proved |
|---|---|
| Aborts | unknown table (names it, changes nothing); MASTER depending on TRANSACTION; corrupt source; missing database; no `--confirm` leaves the file byte-identical |
| A real run | every cleared table empty; every master untouched and still populated; `schema_migrations`, `settings`, `users`, `rooms` preserved; no FK violations; integrity ok; business date today; unlocked; no reservations, shifts, audits or payments; **no orphaned `reservation_rooms`** |
| The backup | exists; holds the *original* rows, not the reset ones; row counts match the pre-run source; manifest records both hashes; **restoring reproduces the original counts** |
| Idempotency | second run reports `ALREADY INITIALIZED`, removes 0 rows, counts unchanged |
| `--preserve-guests` | guests retained, reservations still cleared, no FK violation |
| Determinism | two runs: same order, same rows removed, identical resulting counts |

**Two defects were found by commissioning and fixed:**

- `verify_result` checked residue against the *classification* rather than
  the set actually cleared, so it failed its own `--preserve-guests` option
  — demanding that a table it had been told to keep be empty.
- Backups from a commissioning run were landing in the production backup
  store, which is how a rehearsal artefact ends up looking like a
  production event. Hence `--backup-dir`.

---

## Before running this on production

The tool is safe and proved. The **decision** to run it is not an
engineering one, because of what it removes.

1. **The Wave 0 baseline ends.** 147 evidence packs, every D1 comparison and
   the entire regression reference rest on `instance/pms.db` being
   byte-identical to the `v2.2.18-wave0.5-frozen` tag. Initializing it ends
   that permanently. The archived copy and the repo bundles remain, so the
   *evidence* survives — but the live database stops being the thing that
   evidence describes.
2. **`night_audit_logs` is release evidence** under Phase 2.6 §13 and
   immutable under P12. It survives only in the backup.
3. **`audit_logs` is the compliance record** of who did what — 71 rows.
   Same.
4. **`guest_id_documents` and `foreign_national_info`** may carry statutory
   retention independent of this system. Clearing them is the right
   data-protection outcome; confirm the retention position before the
   backup is ever discarded.

The tool reports all four as warnings on every run, so the report cannot be
read as "nothing of consequence was removed".

### Recommended sequence

```bash
# 1. Rehearse on a copy, with its own backup directory.
python tools/production_initialize.py --db <copy.db> \
       --backup-dir <copy-backups> --confirm

# 2. Read the report. Confirm the four warnings are acceptable.
# 3. Archive the current database off this machine.

# 4. Dry run against production, and read it again.
python tools/production_initialize.py --dry-run

# 5. Apply.
python tools/production_initialize.py --confirm
```

---

## Canonical table classification

53 tables: **12 MASTER, 2 SYSTEM, 3 TEMPORARY, 36 TRANSACTION.**

The reference for future initializations. A table added to the schema and
not added here will abort the next run — deliberately.

| Table | Classification | Action | Rows (production, pre-run) | Reason |
|---|---|---|---|---|
| `audit_logs` | TRANSACTION | Cleared | 71 | The general audit trail. Cleared because it records activity that will not exist. **The tool warns on this.** |
| `backup_logs` | TRANSACTION | Cleared | 0 | History of backups taken by the application. |
| `business_date` | SYSTEM | **Reinitialized** | 1 | The PMS operating date. The one table that is neither preserved nor cleared — set to today and unlocked. |
| `checkin_records` | TRANSACTION | Cleared | 28 | Check-in events. |
| `cico_charge_logs` | TRANSACTION | Cleared | 3 | Check-in/check-out charge audit entries. |
| `companies` | MASTER | Preserved | 0 | Corporate accounts and travel agents, with credit limits. A counterparty ledger, not a transaction. |
| `credit_notes` | TRANSACTION | Cleared | 0 | Credit issued against an invoice. |
| `credit_voucher_redemptions` | TRANSACTION | Cleared | 0 | Voucher usage. **Not classified by `reset_transactional_data.py`.** |
| `credit_vouchers` | TRANSACTION | Cleared | 0 | Vouchers issued to guests. **Not classified by `reset_transactional_data.py`.** |
| `equipment` | MASTER | Preserved | 0 | Maintenance asset register, keyed to rooms. The assets themselves, not work done on them. |
| `equipment_health_logs` | TRANSACTION | Cleared | 0 | Readings against equipment. The readings, not the equipment. |
| `extra_charges` | TRANSACTION | Cleared | 5 | Charges posted to a folio. |
| `folios` | TRANSACTION | Cleared | 28 | The bill a stay is invoiced on. |
| `foreign_national_info` | TRANSACTION | Cleared | 0 | Form C / immigration data per guest. **The tool warns on this.** |
| `group_blocks` | TRANSACTION | Cleared | 0 | A group booking. A sale, despite looking configuration-shaped. |
| `guest_feedback` | TRANSACTION | Cleared | 0 | Feedback against a stay. |
| `guest_id_documents` | TRANSACTION | Cleared | 0 | Identity documents captured at check-in. **The tool warns on this.** |
| `guests` | TRANSACTION | Cleared | 28 | Guest records created per stay. Not a master in this schema — there is no separate guest-profile table, so a guest exists because a stay did. See `--preserve-guests`. |
| `loyalty_config` | MASTER | Preserved | 3 | Loyalty programme parameters. |
| `loyalty_milestones` | MASTER | Preserved | 3 | Loyalty tier definitions. |
| `loyalty_redemptions` | TRANSACTION | Cleared | 0 | Points redeemed against a stay. |
| `loyalty_transactions` | TRANSACTION | Cleared | 0 | Points earned and spent. |
| `maintenance_requests` | TRANSACTION | Cleared | 0 | Work raised against a room. The work, not the asset. |
| `night_audit_logs` | TRANSACTION | Cleared | 1 | Closed business days and their frozen snapshots. **The tool warns on this.** |
| `night_audit_reopen_logs` | TRANSACTION | Cleared | 0 | Reopen events against closed days. |
| `no_show_logs` | TRANSACTION | Cleared | 0 | No-show events and their charges. |
| `notification_logs` | TRANSACTION | Cleared | 56 | Record of notifications already sent. History of activity, unlike `notification_queue` which is the pending work itself. |
| `notification_queue` | TEMPORARY | Cleared | 28 | Outbound work queue. Anything undelivered refers to stays that will not exist. |
| `ota_payouts` | TRANSACTION | Cleared | 0 | Remittances received from channels. **Not classified by `reset_transactional_data.py`.** |
| `overpayment_logs` | TRANSACTION | Cleared | 2 | Recorded guest overpayments. |
| `payment_modes` | MASTER | Preserved | 12 | Settlement heads and their categories. Chart of accounts for money in. |
| `payments` | TRANSACTION | Cleared | 35 | Money received against a stay. |
| `pos_items` | MASTER | Preserved | 8 | Sellable item catalogue with prices. A menu master. |
| `precheckin_submissions` | TRANSACTION | Cleared | 0 | Guest-submitted pre-arrival data. |
| `precheckin_tokens` | TEMPORARY | Cleared | 0 | Short-lived guest links. Expire by design. |
| `preventive_schedules` | MASTER | Preserved | 0 | Maintenance schedules against equipment. A plan, not an event. |
| `rate_plans` | MASTER | Preserved | 0 | Tariff plans against room types. Pricing configuration, not a sale. |
| `reservation_night_rates` | TRANSACTION | Cleared | 30 | Priced room nights. The revenue source. |
| `reservation_passengers` | TRANSACTION | Cleared | 0 | Occupants of a stay. |
| `reservation_rooms` | TRANSACTION | Cleared | 28 | Room allocation per stay. **Not classified by `reset_transactional_data.py`** — this is the 28 orphans that tool would leave. |
| `reservations` | TRANSACTION | Cleared | 28 | The booking. Root of the activity graph. |
| `revenue_alerts` | TEMPORARY | Cleared | 0 | Generated advisory output. Regenerated from data about to be removed. |
| `room_types` | MASTER | Preserved | 3 | Room type catalogue and base tariff. |
| `rooms` | MASTER | Preserved | 39 | The physical rooms. A hotel does not lose its rooms when it stops trading. |
| `schema_migrations` | SYSTEM | **Preserved** | 57 | Applied migration versions. Clearing it would make the application re-run every migration against an already-migrated schema. |
| `settings` | MASTER | Preserved | 60 | Hotel profile, tax policy, GST regime, printers and every operational switch. The single most important table to preserve. |
| `shift_adjustments` | TRANSACTION | Cleared | 0 | Float and payout movements within a shift. |
| `shifts` | TRANSACTION | Cleared | 0 | Front-desk cash shifts. |
| `staff_performance_daily` | TRANSACTION | Cleared | 0 | Derived daily staff statistics. |
| `tax_lines` | TRANSACTION | Cleared | 66 | GST raised per charge. Derived from activity. |
| `users` | MASTER | Preserved | 1 | Operator accounts, roles and permissions. Clearing these would lock the hotel out of its own system. |
| `void_requests` | TRANSACTION | Cleared | 0 | Requests to void a payment. |
| `webhook_logs` | TRANSACTION | Cleared | 0 | Inbound and outbound integration traffic. |

### Reading the table

- **MASTER** — the hotel's configuration. Preserved verbatim. A hotel does
  not lose its rooms, tariffs, tax policy, payment heads or operators
  because it stopped trading.
- **SYSTEM** — framework state. The two members differ:
  `schema_migrations` is preserved verbatim; `business_date` is
  reinitialized.
- **TEMPORARY** — ephemeral working data: a pending queue, expiring tokens,
  regenerable advisory output.
- **TRANSACTION** — business activity, and everything derived from it.

`guests` is TRANSACTION rather than MASTER because this schema has no
separate guest-profile table: a guest row exists because a stay did. Use
`--preserve-guests` where CRM continuity is wanted — commissioned, and it
leaves no foreign-key violation.
