# W1-R8 Steps 1–4 — Night Audit HTML Consolidation

**Completed** 2026-08-12 · app v2.2.18 · branch `main`
**Risk class** SILENT — no financial figure moves
**Blueprint** `WAVE1_BLUEPRINT.md` §4 (W1-R8), steps 1–4 of 6

---

## 1. Scope, and why it changed after Phase 1

The brief described Steps 1–4 as a presentation refactor: inventory →
extract shared partials → single view model → simplify HTML.

Phase 1 measured the estate first, and the measurement contradicted the
premise. **Confirmed with the user before proceeding**, this release
delivers the blueprint's Steps 1–4 instead: restore the lost control →
make the panel the sole HTML authority → instrument before deleting →
record the scheduling gap.

Two findings drove that:

- **59% of Night Audit template code is unreachable.** Refactoring it
  would be work on code already scheduled for deletion in Steps 5–6.
- **Between the live templates there is almost nothing to share.** Every
  cross-file duplicate but one involves the dead template.

---

## 2. Component inventory (Phase 1 deliverable)

### 2.1 Route → template map, verified by execution

| Route | Template | Lines | Status |
|---|---|---|---|
| `/night-audit` · tabs dashboard/analytics/history/settings | `night_audit_panel.html` | 1,696 | **live** |
| `/reports/night-audit?format=print` | `reports/night_audit_print.html` | 664 | **live** |
| `/reports/night-audit/history` | `reports/night_audit_history.html` | 239 | **live** |
| `/reports/night-audit/<id>` | `reports/night_audit_snapshot.html` | 191 | **live** |
| `/reports/night-audit?format=json` | — (JSON) | — | **live** |
| `/reports/night-audit?format=excel` | — (xlsx) | — | **live** |
| `/reports/night-audit` and `?format=html` | — | — | **302 → panel** |
| `/reports/night-audit?format=<unrecognised>` | `reports/night_audit.html` | 3,975 | **unreachable** |
| *(no caller)* | `night_audit.html` | 77 | **zero references** |

**Dead: 4,052 of 6,914 lines (59%).**

`fmt` defaults to `'html'` at `reports.py:2376`; the branches run
json → excel → html → print; the html branch redirects. Only an
unrecognised `format` value reaches the render at the bottom. Every link
in the codebase passes `format='excel'`, `format='print'`, or nothing.
The four bare `url_for('reports.night_audit')` links are inside
`reports/night_audit.html` itself — self-references within dead HTML.

`_partials/audit_override.html` is a **checkout** partial (imported by
`checkout.html`), not a Night Audit surface. Not in scope.

### 2.2 Duplication analysis

Normalised-whitespace hashing of every 6-line window across all six
templates:

```
19 distinct duplicated blocks, 39 occurrences
   cross-file  : 9   <- 9 of 9 involve the dead template
   within-file : 10
```

Live-to-live duplication in full: the Re-run Audit button
(history + panel), the `status_cls` map, one KPI card in snapshot. One
macro exists in the entire estate (`rev_row`, panel:463).

### 2.3 Three status→badge maps that are NOT equivalent

| Template | `Reopened` | `Completed` label |
|---|---|---|
| `reports/night_audit.html` (dead) | `bg-info text-dark` | "Closed" |
| `night_audit_history.html` | `bg-info text-dark` | raw "Completed" |
| `night_audit_panel.html` | **`bg-danger`** | raw "Completed" |

The panel paints a reopened audit red where history paints it blue.
Unifying them would have changed rendered output, which the brief forbids,
so they are **recorded, not merged**. This is a genuine UI inconsistency
and needs a decision about which is correct before it can be fixed.

### 2.4 Business logic living in templates

`night_audit_panel.html:146-186` computes reconciliation deltas,
overpayment sums, unauthorised-discount totals, a risk level, and the
`_hard_blocks` list — duplicating `NightAuditService.final_control()` in
Jinja. This is the strongest argument for the brief's original Phase 3,
and it is recorded as a follow-up rather than attempted here: moving those
calculations is a behavioural risk that a zero-DOM-change release cannot
also carry.

---

## 3. What was implemented

### Step 1 — Restore the surface

`main.night_audit` now computes
`snapshot_integrity = verify_snapshot_integrity(current_log)` — the same
helper `INV-B02` declares as its canonical engine, so the banner and the
invariant cannot disagree about what "tampered" means.

The banner block is ported from `reports/night_audit.html:391-459` into
`night_audit_panel.html`, placed **outside the tab conditionals**: a trust
warning that vanishes when you switch tab is not a warning.

Two defects were fixed during the port rather than carried over:

- The original posted `name="date"`, but `night_audit_run` reads
  `request.form['audit_date']` — **its Re-run button never worked.**
- `btn-outline-light` on a Bootstrap `alert-danger` (pale pink) is
  effectively invisible; now `btn-outline-danger` / `btn-danger`.

### Step 2 — The panel is the sole HTML authority

The four-branch contract is documented at the dispatch point and pinned by
the route matrix in §5.2. Exactly one branch returns an HTML Night Audit
page, and it is the panel.

### Step 3 — Instrument before deleting

The unreachable fallthrough now emits
`Deprecated template rendered: reports/night_audit.html (format=…, date=…, user=…)`.

It is deliberately **left working**. Making it unreachable by construction
would guarantee the observation came back silent, which would prove
nothing and would wrongly license the Step 5 deletion.

### Step 4 — Recorded, not built

The blueprint's own platform note places verification scheduling outside
this release: its scope is the platform, not the Night Audit. Recorded in
§7. Nothing schedules the invariant engine today, so all 25 invariants are
on-demand controls — the gap belongs to all of them, not to `INV-B02`.

---

## 4. A blocker found and fixed: all WARNING logging was disabled app-wide

Step 3's instrumentation did not appear in the logs. The cause was not the
new code:

```
create_app()
  └─ app/admin_reset.py:27   import reset_transactional_data
       └─ reset_transactional_data.py:46   logging.disable(logging.WARNING)
```

A maintenance script disabled **every DEBUG, INFO and WARNING record in
the whole application, for the life of the process, merely by being
imported.** Confirmed by observing `logging.root.manager.disable == 30`
after `create_app()`, and by a direct `logger.warning()` producing no
output on any handler.

This is not a Night Audit defect but it blocks W1-R8 directly. Criterion
A5 measures "`Deprecated template rendered` absent from a full release of
logs" — under the suppression that message could never have been written,
A5 would have passed vacuously, and **Step 5 would have deleted the
template on the strength of a measurement that was impossible.**

It also silently discarded real diagnostics, including the night audit's
own snapshot-parse fallback warning at `routes.py:4737`.

Fixed by scoping the call to the CLI entry point, so importing the module
never reconfigures a host application's logging. `ERROR` and `CRITICAL`
were unaffected throughout, which is why this survived unnoticed.

---

## 5. Verification evidence

### 5.1 Before/after DOM comparison — byte-identical

Every surface rendered before and after, with per-render nonces and CSRF
tokens normalised exactly as D2 normalises them:

```
IDENTICAL  /night-audit?tab=dashboard      4482ff6b3abf2987
IDENTICAL  /night-audit?tab=analytics      baecefa6a75bb6cc
IDENTICAL  /night-audit?tab=history        2830b031efcfddbf
IDENTICAL  /night-audit?tab=settings       750af461603060f3
IDENTICAL  /night-audit                    edffe7421a14bef9
IDENTICAL  /reports/night-audit/history    90305b79c0169a6f
IDENTICAL  /reports/night-audit/1          6ad0e6f357d27910
IDENTICAL  /reports/night-audit?format=print   (wall-clock stamp only)
IDENTICAL  /reports/night-audit?format=json    (wall-clock stamp only)
```

Print and JSON embed a generation timestamp; with that normalised both are
identical. The first implementation left three blank lines where the
inactive `{% if %}` sat — visually irrelevant but not byte-identical, so
the block was whitespace-controlled (`{%- if %}` / `{%- endif -%}`) until
an intact snapshot emits **nothing at all**.

D2 golden capture agrees: of 158 surfaces, one changed —
`/night-audit`, +5 figures, all five being the new `snapshot_integrity`
context variable D2 captures. **No figure changed value; none was
removed.**

### 5.2 A4 — route matrix pinned, 10/10

```
200  /night-audit                        night_audit_panel.html
200  /night-audit?tab=analytics          night_audit_panel.html
200  /night-audit?tab=history            night_audit_panel.html
200  /night-audit?tab=settings           night_audit_panel.html
302  /reports/night-audit                (redirect)
302  /reports/night-audit?format=html    (redirect)
200  /reports/night-audit?format=print   reports/night_audit_print.html
200  /reports/night-audit?format=json    (json)
200  /reports/night-audit/history        reports/night_audit_history.html
200  /reports/night-audit/1              reports/night_audit_snapshot.html
```

Forcing `?format=__unrecognised__` renders the legacy template **and emits
the deprecation warning** — A5 is now a real measurement.

### 5.3 A1/A3 — the control fires, and only when it should

Against a throwaway copy, using `FLT-D02`'s exact mutation (append one
space to `snapshot_json`):

```
CLEAN     matches=True    banner absent on all four tabs   <- no false positive
TAMPERED  matches=False   banner present on all four tabs, with Re-run button
```

### 5.4 A2 / A8 — the safety rails

Against the W1-R1 run of the same day:

```
A2  26 invariants   status/violations/population differences : NONE
                    overall, release-blocking, cert-blocking, financial
                    impact, total_writes : all unchanged
A8  22 quantities   verdict/value/divergence differences     : NONE
D6  5 datasets      PASS — 281 expectations met, 0 unmet
```

---

## 6. Files modified

| File | Change |
|---|---|
| `app/templates/night_audit_panel.html` | +79 — integrity banner, whitespace-controlled |
| `app/routes.py` | +8 — compute and pass `snapshot_integrity` |
| `app/reports.py` | +26 — four-branch contract documented; deprecation warning |
| `reset_transactional_data.py` | logging.disable scoped to CLI |

**No components were extracted and no view model was introduced** — see
§1. Database impact: none. No schema, migration, backfill or write.

---

## 7. Follow-ups

1. **Steps 5–6 remain open.** Deletion is licensed only by A5 coming back
   silent over a full release — now that the log can actually be written.
2. **Verification scheduling** (blueprint step 4) — platform scope. All 25
   invariants are on-demand; `INV-B02` is simply where it became visible.
3. **`Reopened` renders red on the panel, blue in history.** Needs a
   decision on which is correct; unifying was out of scope here.
4. **Financial arithmetic in `night_audit_panel.html:146-186`** duplicates
   `NightAuditService.final_control()`. This is the brief's original
   Phase 3 and remains worth doing as its own release.
5. **Audit the rest of the codebase for import-time side effects** like
   the one in §4. `reset_transactional_data.py` also calls
   `os.environ.setdefault('FLASK_ENV', 'production')` at import.

---

## 8. Rollback

`git revert <commit>`. No data to restore. Each file is independent;
reverting `reset_transactional_data.py` alone restores the logging
suppression and re-breaks A5.

---

## 9. Verdict against the exit criteria

| Criterion | Result |
|---|---|
| Every Night Audit page renders identically | **PASS** — byte-identical, hashes in §5.1 |
| Duplicated HTML substantially reduced | **NOT MET — and deliberately not attempted.** §2.2 shows the duplication is between live and *dead* templates; Steps 5–6 remove it by deletion |
| Single authoritative rendering contract | **PASS** — one HTML branch, pinned 10/10 |
| No business logic moved into templates | **PASS** — none moved. Pre-existing template arithmetic recorded in §2.4 |
| D1 / D4 / D6 pass without behavioural differences | **PASS** — §5.4 |

The release restores an operator-facing financial control that had been
unreachable, makes the panel provably the only HTML Night Audit page, and
makes the deletion in Steps 5–6 answerable to a measurement that — until
the logging fix in §4 — could not have been taken.
