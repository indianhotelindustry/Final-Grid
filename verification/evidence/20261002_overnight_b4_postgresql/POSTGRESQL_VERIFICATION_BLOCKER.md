# PostgreSQL verification — blocker record

| | |
|---|---|
| Recorded | 2026-10-02, overnight session, by Claude (Claude Code agent), machine of the live installation |
| Method | Read-only discovery only: `Get-Service`, `sc.exe qc`, `--version` of the installed binaries, the `port =` line of each `postgresql.conf`, `Get-NetTCPConnection` (listening sockets), `where`, `importlib.util.find_spec` and `pip list` on the system Python. **No login was attempted. No password was guessed. Nothing was installed, started, stopped or configured.** |
| Not inspected | The application venv. It lives inside the live production folder (`…/FinalGrid/SukoonPMS/venv`), which this session's boundary forbids opening. |
| Status | PostgreSQL verification **BLOCKED** |

---

## 1. Discovered environment state (FACT, 2026-10-02)

| Item | Value |
|---|---|
| Services | `postgresql-x64-13` — **Running**, start type Automatic, account `NT AUTHORITY\NetworkService`, binary `C:\Program Files\PostgreSQL\13\bin\pg_ctl.exe … -D "C:\Program Files\PostgreSQL\13\data"`<br>`postgresql-x64-18` — **Running**, Automatic, `NT AUTHORITY\NetworkService`, data `C:\Program Files\PostgreSQL\18\data` |
| Versions | `postgres (PostgreSQL) 13.23`; `postgres (PostgreSQL) 18.4` (from `bin\postgres.exe --version`) |
| Ports | 13 → `port = 5433`; 18 → `port = 5432` (each `data\postgresql.conf`) |
| Listening | 5432 and 5433 on `0.0.0.0` **and** `::` (all IPv4 and IPv6 interfaces). PIDs 8616 (5432) and 8564 (5433); image path not visible to the agent's account |
| Install folders | `C:\Program Files\PostgreSQL\13`, `\18`, `\psqlODBC`, all dated 2026-05-15 |
| `pg_dump` on `PATH` | **No** (`where pg_dump` finds nothing). Affects `app/backup_manager.py:262-270` |
| Databases on either server | **Unknown.** Listing them requires a login |
| Server owner / purpose / contents | **Unknown.** Not recorded in the repository |
| Credentials | **Not available to the agent.** `PGPASSWORD` unset, `DATABASE_URL` unset in the agent environment, no `%APPDATA%\postgresql\pgpass.conf`. None provided by the directive |
| System Python | `Python 3.14.7`, pip 26.2.1; only `pip` installed. `psycopg`, `psycopg2`, `pg8000`, `asyncpg`, `flask`, `sqlalchemy`: **all absent** |
| Application venv driver | **NOT VERIFIED this session** (venv not inspected; see header). Prior evidence, 2026-09-30: no PostgreSQL driver (`psycopg`, `psycopg2`, `pg8000`, `asyncpg` absent) — `verification/evidence/20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:89` |
| Worktree venv | `C:/wtov` has no venv |
| Repository contract | `requirements.txt` lists `psycopg[binary]>=3.1.0` as optional (commented). `.env.example:20` shows `postgresql+psycopg://…` (placeholder only) |

This matches the prior record (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:81-98`; memory note). Two details are new: the version-to-port mapping (13 on 5433, 18 on 5432) and `pg_dump` absent from `PATH`.

---

## 2. What is missing

| # | Missing | Why it blocks | Resolved by |
|---|---|---|---|
| M-1 | A ruling that PostgreSQL verification is required for the current release at all | MP-D4 is OPEN. The requirement is conditional ("if PostgreSQL is a target", `ADR011_IMPLEMENTATION.md:67`) | PG-D1 |
| M-2 | A designated server, with its owner's consent | The two running servers have unknown owners and contents; using one could touch someone else's data | PG-D2 |
| M-3 | A throwaway database and a least-privilege role, plus custody of the credentials | No login is possible, and guessing is forbidden | PG-D3 |
| M-4 | A Python environment with a driver | No driver anywhere the agent may use; installing is forbidden without authorization | PG-D4 |
| M-5 | An agreed scope and acceptance criteria (L1–L4), and authority to port the SQLite-bound harness | The existing harness is SQLite-bound (`POSTGRESQL_VERIFICATION_PLAN.md` §2.3) | PG-D5 |

---

## 3. Decision / authorization entries

### PG-D1

- **DECISION ID:** PG-D1
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** PostgreSQL verification × MP-D4 (persistence engine)
- **QUESTION:** Is PostgreSQL a target for the first production release? If not, is PostgreSQL verification **NOT APPLICABLE** to that release and deferred to MP-D4?
- **WHY REQUIRED:** Every record states the requirement conditionally (`ADR011_IMPLEMENTATION.md:67`). MP-D4 ("SQLite as system of record") is OPEN (`MASTER_PLAN.md:70,248`; `BACKLOG.md:26`). Static reading shows the PostgreSQL path has known breakages (P-1…P-6, plan §2.1). Verifying it only matters if it will be used.
- **OPTIONS:** (a) PostgreSQL is not a first-release target; PostgreSQL verification NOT APPLICABLE until MP-D4. (b) It is a target; verification becomes a release gate. (c) Not a target, but run L1/L2 now as a compatibility check of the code's PostgreSQL branches.
- **EVIDENCE:** `POSTGRESQL_VERIFICATION_PLAN.md` §1.1, §2.1.
- **DEPENDENCIES:** MP-D4; B4-D1 (single schema authority; F-10 has 39 columns with no PostgreSQL path).
- **WHAT IS BLOCKED:** closure of the "PostgreSQL verification" open item in `ADR011_PRODUCTION_APPLICATION_REPORT.md:104` and of item 14 in the pre-production gate.
- **WHAT CAN CONTINUE:** all SQLite work; static PostgreSQL inventory (done).
- **EXACT ACTION AFTER DECISION:** record the ruling verbatim (FD-018). If (a): mark the open item NOT APPLICABLE for the release and cite the ruling. If (b) or (c): proceed to PG-D2…PG-D5.

### PG-D2

- **DECISION ID:** PG-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** PostgreSQL verification — environment
- **QUESTION:** Which PostgreSQL server may be used for testing: `postgresql-x64-18` (18.4, port 5432), `postgresql-x64-13` (13.23, port 5433), or a separate instance? Who owns it? May a throwaway database be created on it and dropped afterwards?
- **WHY REQUIRED:** Both services are running and auto-start. Their owner, purpose and databases are unknown to this work (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:94`). Creating anything on a server of unknown purpose risks unrelated data.
- **OPTIONS:** (a) the 18.4 server; (b) the 13.23 server; (c) a new isolated instance (separate authorization; installs and configures a service); (d) neither; verification NOT AUTHORIZED.
- **EVIDENCE:** §1 above.
- **DEPENDENCIES:** PG-D1 (b) or (c).
- **WHAT IS BLOCKED:** plan steps E-1…E-8.
- **WHAT CAN CONTINUE:** static analysis.
- **EXACT ACTION AFTER DECISION:** record the designated server and version in the plan's `ENVIRONMENT.md` template; the server owner proceeds to PG-D3.

### PG-D3

- **DECISION ID:** PG-D3
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** PostgreSQL verification — credentials custody
- **QUESTION:** Who creates the least-privilege role and the throwaway database? How are the credentials handed over to the verification run? The proposal is the process environment only, never a repository file, log or evidence. Are they rotated or dropped afterwards?
- **WHY REQUIRED:** No credentials are available to the agent. Guessing or probing is forbidden. Evidence and commits must never contain secrets (prior packs had to redact guest data; the same discipline applies to credentials).
- **OPTIONS:** (a) the Founder creates role and database and passes `DATABASE_URL` into the session environment for the run only, then drops both. (b) The Founder authorizes the agent to create them using credentials the Founder enters interactively (the agent never stores them). (c) A `pgpass.conf` outside the repository, deleted afterwards.
- **EVIDENCE:** §1 (credentials row).
- **DEPENDENCIES:** PG-D2.
- **WHAT IS BLOCKED:** connectivity test E-3 and everything after it.
- **WHAT CAN CONTINUE:** venv preparation (if PG-D4 is granted).
- **EXACT ACTION AFTER DECISION:** record the custody procedure (no secret values) in the run's `ENVIRONMENT.md`. Evidence records role and database names, with the password as `[REDACTED]`.

### PG-D4

- **DECISION ID:** PG-D4
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** PostgreSQL verification — driver installation
- **QUESTION:** May a **new, separate verification venv** be created outside the repository and outside the live folder? May `psycopg[binary]` (exact version pinned; recorded with `pip freeze`) be installed into it together with `requirements.txt`? Which Python interpreter should it use?
- **WHY REQUIRED:** No driver is available anywhere the agent may use (§1). Installing is forbidden without explicit authorization. The application venv lives in the live folder and must not be modified (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:96` already proposes a separate venv). The only interpreter seen is Python 3.14.7, and whether `psycopg[binary]` ships wheels for it is NOT VERIFIED. The interpreter the application venv uses was not inspected.
- **OPTIONS:** (a) separate venv on system Python 3.14.7, `psycopg[binary]` pinned; (b) separate venv on the same Python version as the application venv (requires reading that version: one read-only look into the live folder, or a Founder statement); (c) `psycopg2-binary` instead (dialect `postgresql+psycopg2`; differs from `.env.example:20`); (d) not authorized.
- **EVIDENCE:** §1; `requirements.txt` optional line.
- **DEPENDENCIES:** PG-D1 (b) or (c).
- **WHAT IS BLOCKED:** E-2 onwards.
- **WHAT CAN CONTINUE:** static work.
- **EXACT ACTION AFTER DECISION:** create the venv at the authorized path; install; record the pip log, `pip freeze` and the interpreter version as evidence; do nothing else in the same step.

### PG-D5

- **DECISION ID:** PG-D5
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** PostgreSQL verification — scope and acceptance
- **QUESTION:** Which levels are in scope? Options: L1 (`10.0.0` PostgreSQL DDL), L2 (fresh-install boot + steady state), L3 (ADR-011 / CF-10 semantics; needs harness porting), L4 (Golden Master, replay, invariants). What acceptance criteria apply? Are confirmed PostgreSQL defects (P-1…P-6) to be recorded only, or fixed under a later directive?
- **WHY REQUIRED:** The plan's tests T-01…T-25 range from a single DDL check to full parity. The SQLite-bound harness means L3/L4 need code changes in `verification/` (plan §2.3, §3.3). The earlier statement that the 77-gate harness runs unchanged on PostgreSQL is incorrect (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:98` vs `verify_preprod.py:110`).
- **OPTIONS:** (a) L1 only; (b) L1 + L2; (c) L1–L3 with a harness-porting directive; (d) L1–L4.
- **EVIDENCE:** `POSTGRESQL_VERIFICATION_PLAN.md` §1.2, §2, §4.
- **DEPENDENCIES:** PG-D1…PG-D4; B4-D1 (if PostgreSQL becomes a target, P-5 needs a delivery mechanism).
- **WHAT IS BLOCKED:** E-4…E-7.
- **WHAT CAN CONTINUE:** nothing further on PostgreSQL.
- **EXACT ACTION AFTER DECISION:** run the authorized levels from a dedicated worktree, following the plan's §3.1 principles; produce the §5 evidence pack; report each test with the permitted status vocabulary.

### PG-D6

- **DECISION ID:** PG-D6
- **DATE DISCOVERED:** 2026-10-02 (first observed 2026-09-30, `ADR011_PRE_PRODUCTION_GATE_REPORT.md:86`, "observation, outside this scope")
- **WORKSTREAM:** Host security (outside PostgreSQL verification)
- **QUESTION:** Should a separate review be commissioned of the two PostgreSQL services? Both listen on **all interfaces** (`0.0.0.0` and `::`, ports 5432/5433), auto-start, and have an unknown owner and purpose, on the machine that hosts the production PMS.
- **WHY REQUIRED:** Network exposure depends on Windows Firewall and `pg_hba.conf`. Neither was inspected (both are configuration reads beyond this session's discovery scope). Unknown servers on the production host are a standing risk whether or not PostgreSQL is ever used for FinalGrid.
- **OPTIONS:** (a) commission a read-only review (firewall rules, `pg_hba.conf`, listen addresses, owner); (b) the Founder identifies the owner and purpose, and no review follows; (c) no action.
- **EVIDENCE:** §1 (Listening row).
- **DEPENDENCIES:** none.
- **WHAT IS BLOCKED:** nothing in FinalGrid.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the ruling. If (a), issue a read-only review directive naming exactly which files and commands may be read.

---

## 4. Status

| Item | Status |
|---|---|
| Environment discovery (read-only) | PASS (completed) |
| Application venv driver presence | NOT VERIFIED (not inspected this session; absent per 2026-09-30 evidence) |
| PostgreSQL login / database listing | NOT AUTHORIZED (not attempted) |
| Driver installation | NOT AUTHORIZED |
| PostgreSQL verification (all levels) | BLOCKED |
| PG-D1 … PG-D6 | OPEN (Founder) |
