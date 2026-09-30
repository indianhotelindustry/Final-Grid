# ADR011-SA — regression at `3ffeba5` (branch)

All suites ran against the branch application in `C:\wt_adr011` on disposable copies of production.

- **How.** `run_with_branch_app.py` imports `app` from the worktree and `verification` from the main repository. The verbatim suite copies (`regression/reg_*.py`) ran from a git-ignored scratch directory at the same depth, so no committed pack could be overwritten.
- **Outputs.** Under `regression/` and `pvf/`.
- **Production.** SHA-256 `51dd83b7…30bc2` before and after every run.

| Suite | Result at `3ffeba5` | Reference (unchanged `main`) |
|---|---|---|
| ADR011-SA harness (`verify_adr011_impl.py`) | **42/42 PASS** | — (new) |
| CF-10 / CF-11 harness | **242/242 PASS**: cf11 48, corr 46, w10 25, voucher 9, w12 16, w13 16, w24 38, na 21, actor 9, w14 14 (see note 1) | 242/242 |
| Phase 1 writers A / B / C / D | **89/89 · 48/48 · 15/15 · 46/46** (note 1) | same |
| Phase 1 execution | **44/44** (note 1) | 44/44 |
| Phase 2a authorization matrix | **29/29 PASS** | 29/29 |
| Q06 fix | **15 PASS / 0 FAIL** | 15 / 0 |
| Retention (FD-P2-02) | **18/18** | 18/18 |
| W-20 runtime | **23/23** | 23/23 |
| `tools/test_restore_db.py` | **19 OK** | 19 OK |
| Replay `production` | FAIL — the two Q06-H2 deltas only; **identical** to `3efdd2b` (`20260930_031721`) | same |
| inv-run `production` | FAIL — the eight D11 objects only; **record-identical** to `3efdd2b` (`20260930_031723`); 0 writes | same |
| Cross-implementation | FAIL — 15 AGREED / 4 DIVERGED / 1 SINGLE_SOURCE / 2 VACUOUS; **record-identical** to `3efdd2b` (`20260930_031724`) | same |
| Golden Master `phase1_aa6d9e91` | FAIL — 9 differences, **identical to the control run of unchanged `main` code from a worktree root** (`pvf/20260930_052018_…`) (note 2) | in place at `3efdd2b`: PASS 158/158 |
| Datasets (`ds-run`) | 5/5 PASS, identical counts to `main` | 5/5 — **does not exercise the branch** (note 3) |

**Note 1 — declared system mechanism.** Some frozen suites stand in for the scheduler by calling `run_night_audit(app)` or `process_reservation_noshow(..., posted_by_user_id=None)` directly, with no operator:
- Phase 1 writers sets A and D;
- Phase 1 execution;
- CF-10 w14 case W14-E1.

Under ADR011-SA such a call is refused, because the actor is unknown. Run undeclared, these suites stop at that refusal (`regression/*_undeclared.log`: set A 2, set D 2, Phase 1 execution 3 refusals). Sets B and C also run undeclared and pass (`writers_set{B,C}_undeclared.json`).

The suites were not edited. They were re-run with `--system-mechanism verification:<suite>`, which declares only those no-operator calls as SYSTEM; operator rows stay HUMAN because the resolver prefers a real user. The results above are those runs. CF-10 findings A-04/A-06 (undeclared automated calls cannot complete) are unchanged by design. Declared scheduler and automated paths are proven by S1/S2-GREEN-FK. W14-E2's finding changes from actor `0` to no user, as the ruling requires.

**Note 2 — Golden Master.** Two surfaces read files relative to the application root, and a worktree has neither:
- `/backup/` lists `backups/`;
- the command-centre persistent-alert fields read `instance/alert_memory.json`.

The same runner over an unchanged worktree at `16c4ca8` produces the identical 9 differences. The GM delta attributable to the branch is **zero**. An in-place Golden Master of the branch is possible only after merge.

**Note 3 — datasets.** `verification/datasets` evaluates pre-built dataset databases with SQL and never imports `app`. Its PASS is recorded but is not evidence about the branch.

## PostgreSQL

**NOT EXECUTED.** PostgreSQL 13 and 18 services are installed and running on this machine, but:
- no database or credentials are provisioned for this work;
- the application venv has no PostgreSQL driver;
- installing one is not authorized.

The PostgreSQL DDL of migration `10.0.0` (`_AUDIT_LOGS_PG_DDL`) has not been run anywhere. "SQLite with FK enforcement" results are not PostgreSQL results.

## Findings recorded during this work

- `python -m verification gm-verify` run from the main working tree **rewrites `instance/alert_memory.json`** in the live instance folder. Its mtime moved to 2026-09-30 08:47:19 during the `3efdd2b` regression run, with size unchanged (175 B). This is a pre-existing side effect of the verification framework on a production-adjacent file, not the database. Recorded for the Founder; not changed here.
- Harness logs capture production guest phone numbers through notification warnings. 36 occurrences were redacted in this pack's logs before commit.
