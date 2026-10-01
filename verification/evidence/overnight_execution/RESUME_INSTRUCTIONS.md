# RESUME INSTRUCTIONS — FG-OVERNIGHT-01

If the laptop restarted or the session was lost, **do not start from the beginning.**

## 1. Read, in this order

1. `verification/evidence/overnight_execution/OVERNIGHT_STATE.md` (and `.json`) — starting state, the CURRENT_OPERATION block
2. `WORK_QUEUE.md` — first item not marked DONE / BLOCKED
3. `DECISION_QUEUE.md` — never re-ask a queued question; never act on a queued decision until the founder rules
4. `BLOCKED_ITEMS.md`, `COMPLETED_ITEMS.md`, `ERRORS.md`
5. `OVERNIGHT_HANDOFF.md` / `OVERNIGHT_FINAL_REPORT.md` if present

These files live on branch `overnight-20261002` (worktree `C:/wtov`; pushed to `origin/overnight-20261002` at each checkpoint commit). If `C:/wtov` is missing, recreate it:
`git -c core.longpaths=true worktree add C:/wtov overnight-20261002` (from the `SukoonPMS` checkout; never check the branch out in the live folder).

## 2. Inspect actual state (read-only)

```
git -C C:/wtov status -sb ; git -C C:/wtov log --oneline -10
git -C "<FinalGrid>/SukoonPMS" status -sb        # must be main @ c703150, clean
git -C "<FinalGrid>/SukoonPMS" worktree list
git -C "<FinalGrid>/SukoonPMS" fetch origin ; git branch -a -vv
sha256sum "<FinalGrid>/SukoonPMS/instance/pms.db"   # expect 21dc0e97…3953e434
Get-Process | ? ProcessName -match 'python|flask|waitress'   # expect none
Get-NetTCPConnection -LocalPort 5000                          # expect none
```

## 3. Compare against the checkpoint

- If the CURRENT_OPERATION block has no RESULT, determine from git/evidence whether it finished. **Prefer inspection over repetition.**
- If the production hash differs from `21dc0e97…`: **STOP all production-related work**, record the exact state in `ERRORS.md`, and continue only non-production investigation (directive §34).

## 4. Standing rules (abridged; full text in the directive and in `verification/FOUNDER_DECISIONS.md`)

- Never start the application in the live folder; never run migrations, change the business date, enable the scheduler, change `.env`/config, force-push or rewrite history.
- Work only in worktrees (`C:/wtov`, `C:/wtsr1`, `C:/wk7`, …). Production DB is read-only.
- Never overwrite evidence: new runs get new timestamped directories. Corrections are new records.
- When blocked: write the decision package → add to `DECISION_QUEUE.md` → mark BLOCKED → continue with independent work.
- Environment traps: `[[finalgrid-verification-gotchas]]` memory — CRLF (never `sed -i` tracked files), `core.longpaths=true` for worktrees, throwaway `SECRET_KEY`, `PYTHONIOENCODING=utf-8`, scan logs for guest data before committing.

## 5. Permission notes

- 2026-10-02 00:5x: a read-only SELECT of production `payments` rows was **denied** by the session's permission classifier. Do not retry it or route around it; use committed evidence for production facts, or ask the founder.
