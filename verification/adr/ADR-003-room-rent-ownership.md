# ADR-003 — Room-Rent Ownership

| | |
|---|---|
| Status | **ADOPTED** — 2026-09-08 under FG-P0-ADR-ADOPTION-20260908-01 (FD-012, AR-002). Final architecture: **Reservation operational ownership + folio financial ownership**. Historical option labels M1/M2/M3 RETIRED. Architecture adopted; implementation remains separately authorized work. |
| Founder decision | FD-012 (2026-09-08) |
| Drafted | 2026-09-08 at HEAD `237db2ad` |
| Implements | Nothing. |

## Context — room revenue has two representations and one exclusion

| Representation | Where | Behaviour |
|---|---|---|
| Per-night pricing truth | `reservation_night_rates` (`standard_rate`, `resolved_rate`, `final_rate`, `is_posted`, `is_locked`, `posted_charge_id`) — `app/models.py:635-700` | Created at reservation time; locked once posted |
| Posted charge row | `extra_charges` with `charge_type='room_rent'`, `charge_date = business date`, `folio_id NULL` — `app/services.py:148-165` | Posted by the night audit per in-house reservation per business date; also by the skipped-audit re-run (`app/reports.py:3341`) |
| Folio balance | `calculate_folio_total` **excludes** room rent "because they belong to the reservation level" — `app/services.py:2358-2370` | Folio balance is structurally partial by design |
| Stay total | `calculate_stay_amount` prefers posted `room_rent` rows (CASE A), falls back to nightly rates — `app/services.py:2010-2050` | Room rent is simultaneously "a charge row" and "not an extra" |
| Invoice | `get_room_charge_lines(reservation)` derives room lines independently — `app/routes.py:3994-4060` | Reservation-level |
| Invariants | `INV-A02` admits no exception by charge type; `INV-A03` sums every `extra_charges` row through its folio | Under the invariants as written, room-rent rows must carry a folio |

## Principle (as ruled by FD-012)

Room-rent financial activity must ultimately participate consistently in
the financial attribution model rather than remain a special
un-attributed financial path.

## Candidate implementation models — UNRESOLVED

> **Retired 2026-09-08 (FG-P0-ADR-ADOPTION-20260908-01).** The labels M1, M2, M3 in the table below are historical option labels from the period when this question was open. They are **retired** and must not be cited as the name of any architecture. The adopted architecture is defined semantically in *Final architecture — ADOPTED* below. The letter "M3" in Founder resolution AR-002 is **not** the M3 of this table.


| Model | Description | Consequence |
|---|---|---|
| **M1 — Attributed charge row** | Keep posting `room_rent` `ExtraCharge` rows; attribute them to Folio A under ADR-002 R-1; `calculate_folio_total` keeps excluding them from the *balance* | Invariants hold as written; folio-balance semantics unchanged; the two-representation duality remains; Level 3 room-to-company split becomes possible later |
| **M2 — Reservation-level exemption** | Room rent stays unattributed by declared rule | Requires amending `INV-A02` and `INV-A03` (CONSTITUTION §4); a permanent exempt class; conflicts with FD-012's principle unless the Founder narrows it |
| **M3 — Derive-only** | Stop posting `room_rent` rows; room revenue exists only as `reservation_night_rates` | Removes the duality; changes night-audit posting, closed-day recomputation (`INV-B03`), stay calculation CASE A and every report reading `room_rent` rows; a historical-accounting-behaviour change of the kind `WAVE1_BLUEPRINT.md` §6 reserves for explicit approval |

**This ADR does not choose.** The choice determines Phase 1 unit 1.4, the
folio balance definition, and whether a constitutional amendment is
required. It requires a Founder ruling on the accounting meaning
(is room rent a folio-owned transaction?) before the ADR can move to
ADOPTED.

## Facts any model must respect

- The eight FD-010 rows include no `room_rent` rows (production `extra_charges` are two `late_checkout` rows); this ADR does not touch them either way.
- `ReservationNightRate.is_locked` after posting is an immutability control and is preserved under every model.
- Night-audit `snapshot_json` for 2026-08-09 does not read `folio_id`; M1 does not alter closed-day figures. M3 would.

## Implementation boundary

None authorized.

## Architecture Resolution Round 1 reconciliation (2026-09-08)

Source: `verification/evidence/20260908_architecture_resolution_round1/RECORD.md`.

- **AR-002** resolves the question this ADR left open. Recorded architecture, in the Founder's words: *the reservation remains the operational source for determining the stay and room-rate entitlement; the resulting room-rent financial transaction belongs to the reservation's billing folio.* Room-rent revenue posting is therefore a folio financial transaction; reservation is the upstream operational source; Level 2 remains; no multi-folio or split billing.
- **Label discrepancy — REQUIRES FOUNDER CONFIRMATION.** AR-002 says "Adopt M3". In this ADR's table, **M3 = derive-only (stop posting room-rent rows)**, which has no posted financial transaction and is incompatible with the Founder's definition; the definition matches **M1 = attributed charge row** (keep posting `room_rent` rows, attribute to the reservation's Folio A, folio balance semantics unchanged). This ADR records the Founder's definition as the architecture and does not resolve the letter. Until confirmed, status is PROPOSED rather than PROPOSED FOR ADOPTION.
- Consequences under the Founder's definition: `INV-A02`/`INV-A03` hold as written (no amendment); `ReservationNightRate` remains the pricing truth and `is_locked` after posting is preserved; the two-representation duality remains and is an implementation concern; closed-day figures are unaffected.
- Nothing implemented. Night-audit posting unchanged.

## Final architecture — ADOPTED (2026-09-08)

**Name:** *Reservation operational ownership + folio financial ownership.*

**Definition (Founder, AR-002, authoritative by its wording):**

> The reservation remains the operational source for determining the stay and room-rate entitlement; the resulting room-rent financial transaction belongs to the reservation's billing folio.

**Semantics:**

1. The reservation owns the operational stay and rate context: which nights, which room, which rate (`reservation_night_rates` remains the per-night pricing truth; `is_locked` after posting is preserved).
2. The folio owns the financial billing transaction: a posted room-rent charge is a folio financial transaction and carries the reservation's billing folio (under Level 2, Folio A) as its `folio_id`, under ADR-002 rule R-1.
3. Room-rent revenue posting is therefore attributed like every other financial row; `INV-A02` and `INV-A03` hold as written with no charge-type exception.
4. The reservation remains the upstream operational source; attribution does not move ownership of the stay.
5. Level 2 remains the billing architecture. No multi-folio routing and no Level 3 split billing is implied or authorized.
6. What a folio *balance* means is unchanged by this ADR; whether `calculate_folio_total` continues to exclude room rent from the balance figure is an implementation-design question, not an attribution question.

**Status of the two representations:** the coexistence of `reservation_night_rates` (pricing truth) and posted `room_rent` `ExtraCharge` rows (financial transaction) is retained as current structure; simplifying it is not part of this architecture and would require its own decision.

## Retirement of the historical option labels

The candidate table above used the labels **M1**, **M2**, **M3** while the architecture was unresolved. Those labels are **RETIRED** as of 2026-09-08 and must not be cited as the name of any architecture:

- The Founder's resolution AR-002 carries the letter "M3". **That letter is not equivalent to this ADR's retired M3** ("derive-only"), which described no posted transaction and is incompatible with the Founder's definition. The Founder-approved architecture is authoritative by its definition; the historical option label is subordinate and is not used to interpret it.
- It is likewise **not** claimed that the Founder approved this ADR's retired "M1". The correct governance statement is: *the Founder-approved architecture is authoritative by its definition; existing M1/M3 labels are subordinate historical option labels and have been reconciled to prevent semantic ambiguity.*
- Any future reference must use the semantic name above.

## Adoption record (2026-09-08)

Adopted under `FG-P0-ADR-ADOPTION-20260908-01`, recorded in `verification/FOUNDER_DECISIONS.md`, after the label ambiguity flagged in the Architecture Resolution Round 1 record was resolved as above. No other material conflict remains.

**Architecture adopted; implementation remains separately authorized work.** At this recording the night audit still posts `room_rent` rows with `folio_id NULL` (`app/services.py:148-165`). From this point the ADR is append-only.

