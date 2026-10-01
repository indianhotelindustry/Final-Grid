# ADR-011 — FORMAL ADOPTION REQUIRED

| | |
|---|---|
| Recorded | 2026-10-02, overnight session FG-OVERNIGHT-01, worktree `C:/wtov`, branch `overnight-20261002` at `c9eeff0` |
| Finding | **Formal adoption of ADR-011 is NOT AUTHORIZED.** No Founder wording adopting ADR-011 exists in `verification/FOUNDER_DECISIONS.md` or in any evidence pack. Search and results: `ADR011_ADOPTION_PACKAGE.md` §9 |
| Current status | ADR-011 **PROPOSED FOR ADOPTION** (`verification/adr/ADR-011-operator-accountability.md:5`; `verification/FOUNDER_DECISIONS.md:954`; `verification/adr/README.md:47`) |
| Scope | Governance recording only. The ADR-011 implementation is complete and applied (migration 10.0.0, `116b221`; live HUMAN provenance PASS, `c703150`); nothing below reopens it. No decision below is taken by this document. |
| Companion | `ADR011_ADOPTION_PACKAGE.md` (actor model, evidence, limitations L-1…L-15, proposed text deltas T-1…T-14, inconsistencies I-1…I-6) |

## 1. Decision index

| ID | One-line question | Blocks adoption? |
|---|---|---|
| A11-D1 | Adopt ADR-011 now, in part, or keep it PROPOSED FOR ADOPTION? | yes (is the adoption) |
| A11-D2 | Does a SYSTEM row with NULL `staff_user_id` (identity = `actor_kind` SYSTEM + mandatory `actor_mechanism`) satisfy ADR-011 item 4 "never NULL and never `admin`"? | yes (reconciliation wording) |
| A11-D3 | Confirm the four implementation readings (unknown actor refused; unauthenticated ⇒ SYSTEM `web:unauthenticated`; history carried as HUMAN; role/shift/mechanism not reconstructed)? | yes, if adoption records them as architecture |
| A11-D4 | Record in `FOUNDER_DECISIONS.md` the in-session authorizations behind the ADR-011 implementation and production application, which today exist only in evidence packs? | no (recommended before or with adoption) |
| A11-D5 | Are the webhook audit gaps inside ADR-011 (and must they be closed before adoption), or outside it? | depends on answer |
| A11-D6 | Are failed-login audit rows that name the targeted (unauthenticated) account as a HUMAN actor acceptable under ADR011-SA, recorded as a documented semantic, or to be changed later? | no |

---

## 2. Decision entries

### A11-D1

| Field | Content |
|---|---|
| DECISION ID | A11-D1 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | ADR-011 operator accountability — formal adoption (G5 governance) |
| QUESTION | Should ADR-011 be moved from PROPOSED FOR ADOPTION to ADOPTED, and if so with what scope and what stated open items? |
| WHY REQUIRED | ADR-011 was held at PROPOSED FOR ADOPTION on 2026-09-08 because "storage location and system-actor mechanics" were open (`ADR-011-operator-accountability.md:5`, `:63`; `FOUNDER_DECISIONS.md:954`). ADR011-SA resolved the system-actor representation and the actor-kind part of storage and states "the reconciliation is applied to it at its adoption review" (`FOUNDER_DECISIONS.md:1287`). Only the Founder can adopt an ADR (`verification/adr/README.md:23`: ADOPTED is "Recorded in `FOUNDER_DECISIONS.md`"). The production report lists "G5: ADR-011 formal adoption" as open (`20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:101`). |
| OPTIONS | **(A) ADOPT with qualifier**, following the ADR-005 / ADR-007 pattern (`FOUNDER_DECISIONS.md:950-951`): adopt the accountability architecture (FD-014, AR-012) and the ADR011-SA actor model as implemented; state the remaining envelope items (workstation identifier, mandatory `shift_id`, structured business date, checker identity) as open in BACKLOG B-8 and not part of what is adopted. **(B) ADOPT IN PART**: adopt only the system-actor representation (item 4) and the role snapshot (item 3) now; keep the envelope storage (item 2) PROPOSED, i.e. a split status — this has no precedent in the register and would need a new status wording. **(C) KEEP PROPOSED FOR ADOPTION**: record the ADR011-SA reconciliation sections (T-4…T-10) but defer adoption until the remaining envelope items are decided. **(D) SUPERSEDE**: adopt a new ADR covering the implemented actor model and leave ADR-011 for the open envelope items — heavier, no precedent. |
| EVIDENCE | `ADR011_ADOPTION_PACKAGE.md` §2-§5 (model at `c9eeff0`; 42/42, 77/77 gates; migration "APPLIED AND VERIFIED"; live HUMAN PASS); §6 limitations; §9 search; adoption procedure observed at `FOUNDER_DECISIONS.md:896-979` and `20260908_architecture_resolution_round1/ADR_ADOPTION_READINESS.md` |
| DEPENDENCIES | A11-D2 (item 4 wording); A11-D3 (whether the readings become architecture); A11-D5 (whether webhook coverage is a precondition). Independent of B-1 (scheduler ADR) because adoption does not enable the scheduler. |
| WHAT IS BLOCKED | ADR-011 status change (T-1, T-11); README register/count update (T-12); BACKLOG B-8 annotation (T-13); the ADR-011 part of G5 "provenance envelope per ADR-011" (`20260910_phase2_entry/CERTIFICATION_GATES.md:35`). G5 also fails on other grounds (coupling, retention) not addressed here. |
| WHAT CAN CONTINUE | Production operation (unaffected — implementation already applied); SR-1, K-7, G3/G6 work; any documentation work; ADR011-SA reconciliation sections can be drafted (not applied) now. Nothing in the application depends on the ADR status. |
| EXACT ACTION AFTER DECISION | Under a named directive: (1) append a `FOUNDER_DECISIONS.md` entry quoting the Founder's adoption wording verbatim (T-14); (2) replace ADR-011 status line `:5` and append the *ADR011-SA reconciliation* and *Adoption* sections (T-1…T-11) — no earlier content rewritten (`adr/README.md:29-31`); (3) update `adr/README.md:47,50-51` and `BACKLOG.md:19`; (4) read-only consistency check (HEAD, `git diff -- app tools` empty, production hash read only if separately authorized); (5) commit only if a commit is authorized. |

### A11-D2

| Field | Content |
|---|---|
| DECISION ID | A11-D2 |
| DATE DISCOVERED | 2026-10-02 (wording conflict first noted as a Founder interpretation in `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:95`) |
| WORKSTREAM | ADR-011 reconciliation text |
| QUESTION | ADR-011 item 4 requires "a designated system actor identity, never NULL and never `admin`" (`ADR-011-operator-accountability.md:38`). Under ADR011-SA the code writes SYSTEM rows with `staff_user_id` NULL, `actor_kind = 'SYSTEM'` and a NOT NULL `actor_mechanism` (`app/models.py:1080-1083`). Is the reconciliation to say that item 4 is satisfied, reading "never NULL" as applying to the system identity (kind + mechanism), not to the user column? |
| WHY REQUIRED | The decision package left it as "a Founder interpretation" (`ADR011_DECISION_REQUIRED.md:95`). The ruling says system rows "shall not require a fabricated human users row merely to satisfy the audit FK" (`FOUNDER_DECISIONS.md:1282`); the statement that `staff_user_id` "may therefore be empty" is the recorder's governance note (`:1287`), not Founder wording. An adopted ADR is append-only, so the wording must be right at adoption. |
| OPTIONS | **(A)** Confirm the reading: item 4 satisfied; "never NULL" means the system identity (`actor_kind` + `actor_mechanism`) is never NULL; `staff_user_id` NULL on SYSTEM rows is required by ADR011-SA. **(B)** Record item 4's "never NULL" as superseded by ADR011-SA for the user column, without reinterpretation. **(C)** Other wording given by the Founder. |
| EVIDENCE | `ADR011_ADOPTION_PACKAGE.md` §2.1, §2.4, I-1; CHECK `ck_audit_actor_identity` present on production (`20260930_adr011_production_application/RESULT.json` → `post_migration.checks`) |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | Text of T-4 in the reconciliation section; hence A11-D1 options A/B. |
| WHAT CAN CONTINUE | Everything else; the code already satisfies both readings (A) and (B). |
| EXACT ACTION AFTER DECISION | Use the chosen wording verbatim in the T-4 paragraph of the ADR-011 reconciliation section and in the adoption entry. |

### A11-D3

| Field | Content |
|---|---|
| DECISION ID | A11-D3 |
| DATE DISCOVERED | 2026-10-02 (question first raised 2026-09-30 at `20260930_adr011_preprod_gate/ADR011_PRE_PRODUCTION_GATE_REPORT.md:123-127`; no answer recorded in the repository) |
| WORKSTREAM | ADR-011 reconciliation text / implementation readings |
| QUESTION | Does the Founder confirm the readings made where ADR011-SA is silent (`20260930_adr011_implementation/ADR011_DECISION.md:19-24`): (1) an unknown actor is refused, never labelled; (2) an unauthenticated web request is SYSTEM `web:unauthenticated`; (3) history is carried as HUMAN, and a database whose history names no real user refuses to migrate; (4) role and open shift are snapshotted at insert for HUMAN rows only, and are not reconstructed for the 23 historical rows? |
| WHY REQUIRED | These readings are in production behaviour (`app/audit_actor.py:67-86`; `app/__init__.py:700-708`; `app/models.py:1109-1121`) but are implementer readings, not Founder wording. Adoption would turn them into architecture; recording them unconfirmed would present them as decided. |
| OPTIONS | **(A)** Confirm all four as architecture. **(B)** Confirm them as implementation behaviour only (recorded in the ADR as "implementation readings, not adopted architecture"). **(C)** Confirm some, and name any to be revisited (a code change would need its own directive). |
| EVIDENCE | `ADR011_ADOPTION_PACKAGE.md` §2.2, L-3, L-7; regression notes on undeclared calls (`20260930_adr011_implementation/ADR011_REGRESSION.md:139-146`) |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | T-10 wording; A11-D1 option A if the readings are to be part of what is adopted. |
| WHAT CAN CONTINUE | Everything; behaviour is unchanged whichever option is chosen unless (C) leads to a later directive. |
| EXACT ACTION AFTER DECISION | Record the answer verbatim in the adoption entry and T-10; if (C), list the revisited reading in BACKLOG with no code change. |

### A11-D4

| Field | Content |
|---|---|
| DECISION ID | A11-D4 |
| DATE DISCOVERED | 2026-10-02 |
| WORKSTREAM | Governance record completeness (ADR-011) |
| QUESTION | Should `FOUNDER_DECISIONS.md` gain an entry recording the in-session authorizations that followed ADR011-SA — branch-only delivery (`20260930_adr011_implementation/ADR011_DECISION.md:5`), the production application of 10.0.0 "subject to PD-004/PD-005 controls" (`20260930_adr011_production_application/RESULT.json` → `authorization`; report `:10`), the acceptance of the inline boot-time registry for 10.0.0 asked at `ADR011_PRE_PRODUCTION_GATE_REPORT.md:113`, the rollback-path authorization asked at `:115-121`, and the read-only live verification directive (`20260930_135930_adr011_live_human_provenance/REPORT.md:5`)? |
| WHY REQUIRED | `FOUNDER_DECISIONS.md:1289-1290` says delivery and production application were "Not addressed by this ruling" and "Implementation status: not implemented"; no later entry exists, so the decision register does not show that production was mutated under Founder authority. The pre-production report asked specifically whether to accept the inline mechanism for 10.0.0 "or decide B-4 first"; the evidence quotes the authorization but does not state an explicit answer on B-4 or on the rollback path. The same class of gap is recorded for SR-2 (overnight note N-01). |
| OPTIONS | **(A)** Founder issues wording for a recording entry (verbatim) covering these authorizations, including an explicit statement on B-4 for 10.0.0 and on the rollback path. **(B)** Record a reference-only entry pointing at the evidence quotes, marked "as recorded in evidence; Founder wording not separately confirmed". **(C)** Leave the record as it is (evidence packs only). |
| EVIDENCE | `ADR011_ADOPTION_PACKAGE.md` §4, I-3; `FOUNDER_DECISIONS.md:1289-1290`; search: no occurrence of `10.0.0`, `adr011-system-actor`, `e7086da` or `3ffeba5` in `FOUNDER_DECISIONS.md`, `MASTER_PLAN.md` or `verification/adr/` |
| DEPENDENCIES | none; benefits A11-D1 (T-9 cites it) |
| WHAT IS BLOCKED | T-9 can cite only evidence packs until this is decided. Nothing operational. |
| WHAT CAN CONTINUE | Everything. |
| EXACT ACTION AFTER DECISION | (A) or (B): append the entry to `FOUNDER_DECISIONS.md` under a governance-recording directive, citing the evidence paths above; no edit to earlier entries. (C): note in the adoption entry that authority for the application is evidenced in `20260930_adr011_production_application/`. |

### A11-D5

| Field | Content |
|---|---|
| DECISION ID | A11-D5 |
| DATE DISCOVERED | 2026-10-02 (carried unanswered from `20260930_adr011_system_action_provenance/ADR011_DECISION_REQUIRED.md:120-125`, 2026-09-30) |
| WORKSTREAM | ADR-011 scope — webhook (unattended, armed integration) |
| QUESTION | Are the webhook audit gaps within ADR-011 — (a) `modify_booking` audit non-strict, so a rate change can commit with no audit row (`app/webhook.py:348-370`); (b) `new_booking` / `cancel_booking` write no `AuditLog` (`app/webhook.py:148`, `:298`); (c) their only record, `WebhookLog`, pruned after 90 days (`app/__init__.py:547-560`) — and must they be resolved before ADR-011 adoption, or are they outside ADR-011 (non-financial, Q5-P1 classification) and tracked elsewhere? |
| WHY REQUIRED | ADR011-SA made webhook rows SYSTEM `webhook` but did not change coverage or strictness (`20260930_adr011_implementation/ADR011_ANALYSIS.md:46`). AR-012 covers "material operational and financial actions" (`RECORD.md:132`); a booking creation/cancellation/rate change is operational. Adopting ADR-011 without a statement would leave the scope ambiguous. |
| OPTIONS | **(A)** Outside ADR-011 adoption: record as an open item (BACKLOG) with its own later directive; adoption proceeds. **(B)** Inside ADR-011 and a precondition: adoption waits for a webhook audit directive. **(C)** Inside ADR-011 but not a precondition: adopt with the gap listed as an open item of the adopted ADR. |
| EVIDENCE | `ADR011_ADOPTION_PACKAGE.md` L-4; `ADR011_DECISION_REQUIRED.md:41-42`; webhook armed (`webhook_api_key` set, 0 calls) per `ADR011_DECISION_REQUIRED.md:41` |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | A11-D1 if (B). Otherwise nothing. |
| WHAT CAN CONTINUE | Everything; no webhook call has been received on production. |
| EXACT ACTION AFTER DECISION | Record the classification in the adoption entry (T-8) and, for (A)/(C), add or annotate a BACKLOG item; any code change needs a separate implementation directive. |

### A11-D6

| Field | Content |
|---|---|
| DECISION ID | A11-D6 |
| DATE DISCOVERED | 2026-10-02 (code reading at `c9eeff0`; not covered by any evidence pack; not runtime-verified here) |
| WORKSTREAM | ADR-011 actor semantics — authentication audit rows |
| QUESTION | A failed login for an existing account writes an audit row with `staff_user_id` = the targeted account (`app/auth.py:110-117`), which the insert listener records as `actor_kind HUMAN`, mechanism `web`, role of that account (`app/audit_actor.py:73-75`; `app/models.py:1104-1114`). The person who attempted the login is not authenticated. Is this acceptable under "Human audit records shall continue referencing the authenticated user" (`FOUNDER_DECISIONS.md:1280`)? |
| WHY REQUIRED | Under ADR011-SA, HUMAN means an authenticated user; this row's user is the subject of the attempt, not a verified actor. The behaviour is pre-existing (same `staff_user_id` before 10.0.0), so it is a semantic classification, not a regression. Related minor note: logout closes the open shift before writing its audit row, so logout rows carry `actor_shift_id` NULL (`app/auth.py:128-141`). |
| OPTIONS | **(A)** Accept and document: for `entity_type='Auth'`, `action='login_failed'`, `staff_user_id` identifies the targeted account; no code change. **(B)** Record as a later change (e.g. such rows as SYSTEM `web:unauthenticated` with the target in `after_state`), under a separate directive; not a precondition for adoption. **(C)** Treat as a precondition for adoption (not recommended given the Founder's position that the implementation is complete). |
| EVIDENCE | `ADR011_ADOPTION_PACKAGE.md` L-11, I-6. The post-migration live rows 24-26 are `login_success`/`logout`; whether any of the 23 historical rows is a `login_failed` row was not checked (production not opened by this work). |
| DEPENDENCIES | none |
| WHAT IS BLOCKED | Nothing unless (C). |
| WHAT CAN CONTINUE | Everything. |
| EXACT ACTION AFTER DECISION | (A): one sentence in the reconciliation section; (B): BACKLOG entry; (C): implementation directive, then adoption. |

---

## 3. Draft adoption wording

> **DRAFT — for Founder approval, not adopted.**
> Nothing in this section has effect. It is offered so the Founder can approve, amend or reject wording. It assumes A11-D1 option (A), A11-D2 option (A), A11-D3 option (A), A11-D5 option (A) and A11-D6 option (A); any other answer changes the text.

### 3.1 Draft `FOUNDER_DECISIONS.md` entry (append-only)

> **DRAFT — for Founder approval, not adopted.**
>
> `# ADR-011 Adoption — <directive identifier to be issued by the Founder>`
>
> | | |
> |---|---|
> | Recorded | <date> |
> | Governed HEAD | <sha> |
> | Record | `verification/evidence/20261002_overnight_adr011_adoption/` |
> | Kind | ADR adoption. **Not an implementation authorization.** |
>
> **Decision (Founder wording to be inserted verbatim):** ADR-011 Operator Accountability is ADOPTED.
>
> What is adopted: the accountability principle (FD-014, AR-012); the system-actor model of ADR011-SA — every `audit_logs` row has an explicit actor kind (`HUMAN` or `SYSTEM`); HUMAN rows reference the authenticated user and snapshot role and open shift at insert; SYSTEM rows reference no user, never use `users.id = 0`, and carry a mandatory execution mechanism; an audit row whose actor cannot be established is refused. ADR-011 item 4 is satisfied by the SYSTEM kind plus mechanism; "never NULL" applies to that identity, not to `staff_user_id`.
>
> Not adopted and remaining open (BACKLOG B-8): workstation identifier beyond IP; whether `shift_id` is mandatory at posting; business date as a structured envelope field; checker identity (ADR-010); MP-D9 beyond the first release. Webhook audit coverage is outside this adoption and tracked separately.
>
> Implementation state (separately authorized, not by this entry): migration 10.0.0 applied to production 2026-09-30 (`20260930_adr011_production_application/`); live HUMAN provenance verified (`20260930_135930_adr011_live_human_provenance/`); SYSTEM provenance verified on copies only; PostgreSQL not verified. Scheduler activation remains NOT AUTHORIZED (FD-P2-05, B-1).
>
> ADR-011 is append-only from this entry.

### 3.2 Draft ADR-011 status line (replacement of `:5`)

> **DRAFT — for Founder approval, not adopted.**
>
> `| Status | **ADOPTED (accountability architecture and system-actor model)** — <date> under <directive> (FD-014, AR-012, ADR011-SA). System-actor representation implemented (migration 10.0.0, production 2026-09-30). **Open:** workstation identifier, mandatory shift_id, business date in the envelope, checker identity (B-8). Scheduler not enabled. |`

### 3.3 Draft appended ADR-011 sections

> **DRAFT — for Founder approval, not adopted.**
>
> `## ADR011-SA reconciliation (<date>)`
>
> Source: `FOUNDER_DECISIONS.md` Round 5, ADR011-SA (2026-09-30). Earlier sections are not rewritten.
>
> - Item 4 (system actor) — **resolved**: `audit_logs.actor_kind = 'SYSTEM'` with mandatory `actor_mechanism` (e.g. `scheduler:night_audit_job`, `webhook`, `web:unauthenticated`, `dev_seed`); `staff_user_id` NULL; `users.id = 0` forbidden by CHECK. "Never NULL" is satisfied by that identity; "never `admin`" is satisfied because no user is referenced.
> - Item 2 (storage) — **resolved for actor kind, mechanism, role and shift**: carried by the coupled `audit_logs` row. Business date, workstation identifier and checker identity remain open.
> - Item 3 (role snapshot) — implemented as `audit_logs.actor_role`, snapshot at insert.
> - Item 5 (immutability) — write-once by the application; no database-level immutability.
> - Implementation readings confirmed by the Founder on <date>: <verbatim>.
> - Implementation: `3ffeba5` (code), 10.0.0 applied to production 2026-09-30 under the authorization recorded in <entry or evidence path>; live HUMAN provenance PASS 2026-09-30.
> - Remaining open: workstation identifier · mandatory `shift_id` · business date in the envelope · checker identity (ADR-010) · MP-D9 beyond first release. System-actor representation: closed by ADR011-SA.
>
> `## Adoption (<date>)`
>
> Adopted under <directive>. What is adopted / not adopted: as in `FOUNDER_DECISIONS.md` <line>. Append-only from this section.

---

## 4. What this document did not do

- It did not edit `verification/adr/ADR-011-operator-accountability.md`, `verification/adr/README.md`, `verification/adr/BACKLOG.md`, `verification/FOUNDER_DECISIONS.md` or any existing evidence.
- It did not start the application, import `app`, open any `pms.db`, or touch the live production folder.
- It made no git commit, branch, merge or push.
