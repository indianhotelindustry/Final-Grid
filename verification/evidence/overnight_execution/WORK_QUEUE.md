# WORK QUEUE — FG-OVERNIGHT-01

Status: TODO · IN PROGRESS · DONE · BLOCKED (decision ref) · NOT AUTHORIZED. Output directories are under `verification/evidence/`.

| # | Directive § | Work item | Output | Status |
|---|---|---|---|---|
| W-01 | §8 | Read-only state recovery | `overnight_execution/OVERNIGHT_STATE.md/.json` | DONE |
| W-02 | §9–10 | SR-1 / INV-B06: recover ruled text; implement if ruled | `20261002_overnight_sr1/SR1_DECISION_REQUIRED.md` | BLOCKED (DQ-01…DQ-05): no ruled text; implementation NOT AUTHORIZED |
| W-03 | §11–12 | K-7 analysis (architecture, writer inventory, dependency map, production risk, decisions) | `20261002_overnight_k7_analysis/` | DONE — `fdee5de`; implementation NOT AUTHORIZED |
| W-04 | §13 | 53-day business-date production decision | `20261002_overnight_k7_analysis/BUSINESS_DATE_PRODUCTION_DECISION.md` | DONE — `fdee5de` (decision BD-D1…D5 / DQ-64…68) |
| W-05 | §14–15 | G3 matrix; G6 dependency map; gates A–H recovery; gate status register | `20261002_overnight_gates_g3_g6/` | DONE — `c4d8ae2` |
| W-06 | §16–17 | G11 rehearsal package; G12 templates | `20261002_overnight_g11_g12_prep/` | DONE — `5da6f75` |
| W-07 | §18–19 | B-4 startup migration analysis + decision; PostgreSQL plan / blocker | `20261002_overnight_b4_postgresql/` | DONE — `c1e72b8` (PostgreSQL BLOCKED) |
| W-08 | §20–22 | Webhook audit gap; git-history phone number; live-data copies inventory | `20261002_overnight_webhook_privacy_copies/` | DONE — `0337db5` |
| W-09 | §23 | ADR-011 formal adoption package | `20261002_overnight_adr011_adoption/` | DONE — `0ae01bc` (adoption NOT AUTHORIZED) |
| W-10 | §29 | Consolidate all decisions into `DECISION_QUEUE.md` | `overnight_execution/DECISION_QUEUE.md` | DONE — 68 entries |
| W-11 | — | Review every agent-produced document against the code/governance (spot-check citations) before commit | — | DONE — each package spot-checked before commit |
| W-12 | §26–27 | Focused commits per workstream; push `overnight-20261002` (documentation/evidence only) | git | DONE — 7 commits, pushed, 0 0 |
| W-13 | §30, §35 | `OVERNIGHT_HANDOFF.md`, `OVERNIGHT_FINAL_REPORT.md`, `RESULT.json` | `overnight_execution/` | DONE |

Not in the queue on purpose (NOT AUTHORIZED tonight): K-7 implementation (no Phase 3 directive), any production deployment, business-date advancement, migration-behaviour change, history rewrite, data-copy disposal.
