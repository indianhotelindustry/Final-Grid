# "Force Close (Admin)" — investigation

Read-only. 2026-08-08. **The function was not executed. No code, schema or
row was modified.** Production remains byte-identical to the
`v2.2.18-wave0.5-frozen` tag.

## Verdict

> ## NOT SAFE
>
> Not for the stated purpose. It does not advance the business date — it
> advances the business date **and fabricates 72 closure records** for days
> on which no audit was performed, in a form the verification framework
> cannot see.

---

## 1. Route

```
POST /reports/night-audit/advance-date        →  reports.night_audit_advance_date
```

`app/reports.py:3387`. Admin-only (`abort(403)` otherwise), POST-only, CSRF
token supplied by the form. Reached from `night_audit_panel.html:634` via a
confirmation modal that is itself gated on
`current_user.has_role('Admin') and bd and bd < today`, with a mandatory
acknowledgement checkbox before the submit button enables.

## 2. Implementing function

`night_audit_advance_date()` — `app/reports.py:3388–3447`. Sixty lines, no
delegation to any service. It does not call `NightAuditService`,
`run_night_audit`, `ensure_all_tax_lines`, or any posting routine.

## 3. Exact database writes

**Two tables. Nothing else is touched.**

### `night_audit_logs`

One row per date in `[business_date, today)`. For each date:

- If **no row exists** → `INSERT` with `audit_date` only, then the fields
  below.
- If a row exists with status **`Completed`** or **`Warning`** → left
  untouched (but still counted in the "Skipped dates" flash message).
- If a row exists with **any other status** — `Pending`, `Reopened`,
  `InProgress` → **overwritten** with the fields below.

Fields written:

| Column | Value |
|---|---|
| `status` | `'Skipped'` |
| `run_by_user_id` | the acting admin |
| `run_at` | `datetime.utcnow()` |
| `completed_at` | `datetime.utcnow()` |
| `override_used` | `True` |
| `override_reason` | `"Force-advanced by admin (…) to catch up to …"` |
| `snapshot_valid` | **`True`** — the ORM default, on insert |

Never written: `snapshot_json`, `snapshot_hash`, `snapshot_version`,
`total_revenue`, `net_revenue`, `accrual_revenue`, `total_payments`,
`outstanding_amount`, `occupancy_count`, `reconciliation_difference`,
`expected_cash`, `actual_cash`, `cash_variance`.

### `business_date`

| Column | Value |
|---|---|
| `current_date` | `date.today()` — a jump of arbitrary length, not `+1 day` |
| `is_locked` | **`False`** — cleared, never read first |
| `updated_at` | `datetime.utcnow()` |

Then one `db.session.commit()`.

### What is *not* written

**No `audit_logs` row.** The general audit trail is live (71 rows) and is
used by comparable admin actions — including the night-audit *reopen* path
15 lines earlier in the same file, which writes a before/after `AuditLog`
entry and comments that "audit-log write must never block the reopen action
itself". Force Close has no equivalent. The docstring's claim that it
"writes an audit trail entry for every skipped day" refers to the
`NightAuditLog` row, not the audit trail.

## 4. The seven questions

| | Answer |
|---|---|
| Posts `room_rent` rows? | **No.** No `ExtraCharge` is created. The real audit posts one per in-house reservation per night (`services.py:111`) |
| Creates `NightAuditLog` entries? | **Yes — one per skipped date.** This is its principal side effect and the source of the risk |
| Advances the business date? | **Yes**, straight to `today` in one step |
| Recalculates revenue? | **No.** Every revenue column on the log is left NULL |
| Updates folios? | **No** |
| Creates snapshots? | **No** — and it sets `snapshot_valid = True` anyway (§5.1) |
| Bypasses validations? | **Yes.** No open-shift check, no pending-checkout check, no blocker/warning evaluation, no `is_locked` check — it *clears* the lock |

## 5. Three defects in the function itself

### 5.1 `snapshot_valid = True` on a row with no snapshot

`models.py:937` — `snapshot_valid = db.Column(db.Boolean, default=True,
nullable=False)`, documented as *"True: `snapshot_json` is the
authoritative frozen state for this date."*

Force Close inserts rows without ever setting `snapshot_json`. The ORM
default therefore asserts an authoritative frozen state that does not
exist. Every real close path sets the flag **and** the snapshot together
(`services.py:216-218`, `reports.py:2985-2991`); this path sets the flag
alone.

### 5.2 The rows are invisible to the audit invariants — and silence one

Measured against the D4 registry:

| Invariant | Population | A Force-Closed row |
|---|---|---|
| `INV-B01` | logs with status `Completed` or `Warning` | **excluded** — status is `Skipped` |
| `INV-B02` | logs where `has_snapshot` | **excluded** — `continue`s on the first check |
| `INV-B03` | closed dates with a snapshot to recompute against | **excluded** |
| `INV-B05` | every date from the first audit to the business date | **satisfied by the row's mere existence** |

`INV-B05` asks whether an audit row exists for each day. It does not ask
whether an audit happened. **Force Close makes the "no un-audited date"
control pass for 72 days on which nothing was audited**, while the three
invariants that would examine an audit's content all exclude the rows.

This is the decisive finding. The framework does not merely fail to object
— it is made to report the sequence as sound.

### 5.3 A reopened audit is masked rather than resolved

The docstring says the function is "used when the date gets stuck due to a
Reopened audit that was never completed". A `Reopened` log is not in the
`('Completed','Warning')` exemption, so it is **overwritten**: status
becomes `Skipped` and `completed_at` is stamped — while its stale
`snapshot_json` and `snapshot_hash` from the original close remain in place.

The row then reads as a closed-and-skipped day carrying a snapshot from a
close that was subsequently reopened. `INV-B02` and `INV-B03` *will*
examine it, because it has a snapshot, and will compare today's
recomputation against a stale one.

## 6. Step-by-step execution trace

Against the current database, were the button pressed today:

```
 1  POST /reports/night-audit/advance-date
 2  current_user.has_role('Admin')                    → else 403
 3  bd = BusinessDate.query.first()                   → 2026-05-28
 4  today = date.today()                              → 2026-08-08
 5  if bd.current_date >= today: return               → not taken
 6  bd = SELECT ... FOR UPDATE                        → see note below
 7  cursor = 2026-05-28
 8  ── loop, 72 iterations, cursor < 2026-08-08 ──────────────────
 9      log = NightAuditLog WHERE audit_date = cursor → None, all 72
10      db.session.add(NightAuditLog(audit_date=cursor))
11      status='Skipped'; run_by_user_id; run_at; completed_at;
12      override_used=True; override_reason='Force-advanced…'
13      snapshot_valid = True   (ORM default; snapshot_json stays NULL)
14      cursor += 1 day
15  ── end loop ─────────────────────────────────────────────────
16  bd.current_date = 2026-08-08
17  bd.is_locked    = False
18  bd.updated_at   = utcnow()
19  db.session.commit()          ← 72 INSERTs + 1 UPDATE, one transaction
20  flash(...); redirect to the night audit dashboard
```

**Net effect: 72 new `night_audit_logs` rows and one `business_date`
update. 0 charges, 0 payments, 0 folio changes, 0 snapshots, 0
`audit_logs` rows.**

Two notes on the trace:

- **Step 6 does not lock.** The application logs on startup that "Running
  on SQLite — row-level locking (`with_for_update`) is not enforced". The
  concurrency guard is inert on this deployment.
- **Step 9 finds nothing for all 72 dates.** The only existing log is
  2026-05-27, which precedes the loop. So all 72 rows are inserts, and
  none of the overwrite paths in §5.3 are reached *on today's data*.

## 7. Is it safe for advancing the business date during a parallel pilot?

**No.** Five reasons, in order of weight.

1. **It is not a date-advance function.** Advancing the date is 3 of its 60
   lines. The other 57 manufacture closure records. There is no way to use
   "only" that part — the loop is unconditional.

2. **It defeats the control that would tell you the days were not audited.**
   §5.2. After running it, `INV-B05` reports an unbroken audit sequence
   across 72 days that were never audited, and no other invariant examines
   the rows. A parallel pilot's entire value is that the framework can tell
   you when the two systems disagree; this makes it assert agreement.

3. **It writes to production.** 73 rows in one commit. Every Wave 0
   evidence pack — 147 of them — rests on `instance/pms.db` being
   byte-identical to the freeze. Running this invalidates that baseline
   permanently, and the baseline is what a parallel run would be compared
   against.

4. **Its rollback is unproven.** This is a data migration in everything but
   name, and per `WAVE1_BLUEPRINT.md` §1 rollback of a data migration is a
   restore. `backup_logs` carries no checksum, `FLT-D04` and `FLT-D05` are
   UNCOVERED, and **D9 does not exist**. There is a manually verified
   snapshot and `tools/backup_db.py`, but a procedure proven once by hand
   is not a control.

5. **The 72 rows are not cleanly reversible by the application.** No
   supported path deletes a `NightAuditLog`. The reopen path only rolls the
   date back one day (`reports.py:3091`, guarded on
   `bd.current_date == audit_date + 1`), so it cannot undo a 72-day jump.
   Reversal means either direct SQL or a restore.

### The one argument in its favour, and why it does not carry

The modal's own warning — *"Does NOT post any `room_rent` charges … balances
will be incomplete"* — is the harm it advertises, and on **today's data that
harm is nil**: there are **0 in-house reservations**, so a real night audit
would post 0 `room_rent` rows too. The advertised risk is the one that does
not apply.

The unadvertised risk is the one that does: 72 fabricated closure records
that silence `INV-B05` and are invisible to `INV-B01`, `B02` and `B03`.

## 8. What to do instead

**There is no supported way to advance the business date without either
running a real audit or fabricating skipped rows.** The complete set of
writers to `business_date.current_date`:

| Path | Behaviour |
|---|---|
| `services.run_night_audit` | +1 day, after posting charges and storing a hashed snapshot |
| `reports.py:2991` manual complete | +1 day, after storing a hashed snapshot |
| `reports.py:3091` reopen | −1 day, guarded |
| `reports.py:3438` **Force Close** | → today, no snapshot, no charges |

If the pilot needs the date moved, the options are, in order of preference:

1. **Run the real night audit repeatedly** — 72 times. Slow, but each day
   gets a snapshot, a hash and a real close, and `INV-B02`/`B03` can see
   every one of them. With 0 in-house reservations it posts no charges, so
   it is close to a no-op financially. **This is the recommended path.**
2. **Run the pilot on a copy**, not on production — which is what the
   verification framework already does for every measurement, and what
   `verification/_work/` exists for.
3. If Force Close is used regardless: take a fresh verified snapshot
   immediately before (`python tools/backup_db.py --label pre-force-close`),
   record the 72 `audit_date` values, and accept that the Wave 0 baseline
   and every comparison resting on it are void from that point.

Option 3 is a decision for whoever owns the audit record, not an
engineering call — the rows assert that days were closed, and they will
outlive the pilot.
