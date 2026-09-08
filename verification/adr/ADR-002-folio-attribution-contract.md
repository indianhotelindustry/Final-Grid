# ADR-002 — Folio Attribution Contract

| | |
|---|---|
| Status | **DRAFT** — not adopted |
| Founder decision | FD-011 (Level 2 floor), FD-003 (folio = billing unit), FD-010 (the eight rows) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Provenance | Phase 0 unit 0.2, *Folio Ownership & Creation Contract*, artifact `ea374fdc-c1ec-4c7d-9385-af33e486df74` (2026-09-05) — the drafted specification; not repository authority |
| Implements | Nothing. |

## Context

- `folio_id` is nullable on `payments` (`app/models.py:806`) and `extra_charges` (`:772`).
- Folio A ("Guest") is created for every reservation by an `after_insert` listener (`app/models.py:745-761`); unique per letter (`uq_folio_letter`, `:735`).
- Of 24 production creation sites (12 `Payment(`, 12 `ExtraCharge(`), only the four correction paths set `folio_id`, by copying it from the row being corrected (`app/services.py:922, 953, 1007, 1041`). Every originating writer leaves it NULL.
- The refund path (`app/services.py:1489`) does not inherit and does not set it.
- Production state: 4 reservations, 4 folios (all A), 6 payments and 2 charges all NULL — the eight rows governed by FD-010.
- `INV-A02` (every financial row belongs to a folio) and `INV-A03` (charges summed over folios equal charges summed over reservations) are VIOLATED on production.
- All five D6 regression datasets already route every row to a folio and declare `INV-A02: HOLDS`.

## Decision (architecture derived from FD-011)

**A. Ownership**
- O-1 Every reservation owns exactly one default folio (Folio A), created with the reservation. The existing listener is the mechanism.
- O-2 A folio belongs to one reservation for its whole life.
- O-3 Additional folios exist only through `folio_bp.create_folio` under the Phase 2a guard. No creation site creates one implicitly.
- O-4 The live company relationship stays on the check-in record; `Folio.company_id` stays inert (FD-003).

**B. Routing**
- R-1 Every new `payments` row and every new `extra_charges` row is attributed, at insert, in the same transaction, to the default folio of its own reservation, through one service-layer resolver. No site computes a folio any other way.
- R-2 Room-revenue rows participate in attribution (FD-012); the representation is ADR-003.
- R-3 A correction or reversal row inherits the `folio_id` of the row it corrects (already implemented; ratified).
- R-4 A refund row is attributed to the default folio of its reservation.
- R-5 Attribution is never changed by a posting, correction, night-audit re-run or report; a change of attribution is a transfer through `folio_bp` only.
- R-6 Attribution and the row commit together or not at all.

**C. Unattributed transactions**
- U-1 The set of transactions permitted to carry `folio_id NULL` after deployment is empty.
- U-2 A NULL found after deployment is a defect in a creation site, reported by INV-A02, fixed at the site — never by editing the row.

**D. The pre-contract population**
- The eight rows are governed by FD-010: preserved, untouched, unattributed. This contract governs rows created after deployment only.

## Unresolved — explicitly not decided here

| Ref | Question | Options on record | Founder default proposed in the contract |
|---|---|---|---|
| CD-1 | Posting path finds a reservation with no default folio | create Folio A + audit row and continue / refuse the posting | create and audit |
| CD-2 | Room-revenue rows attributed to Folio A | yes / amend INV-A02+A03 | yes — **now depends on ADR-003** |
| CD-3 | Refund rows attributed to the reservation's default folio | yes / inherit from refunded payment where identifiable | yes |
| CD-4 | Seed fixtures brought under the contract in Phase 1 | yes / defer to Phase 6 | yes |
| — | Schema enforcement (`NOT NULL`) | deferred; service-layer + INV-A02 enforcement | defer — blocked by FD-010 (NULL rows must remain) |
| — | Whether INV-A02's production population should be declared/exempted following FD-010 | constitutional amendment / leave VIOLATED | **not decided**; separate Founder decision |

## Consequences

- With one folio per stay, folio-level and reservation-level totals are arithmetically identical; INV-A03 holds by construction for new rows.
- Q14 (folio partition parity) moves DIVERGED → AGREED for populations where every row is attributed.
- Production `inv-run` stays FAIL while the eight rows are preserved (FD-010 consequence).

## Implementation boundary

None authorized. The Phase 1 directive (artifact `42e90c62…`) is the proposed implementation and requires its own authorization.
