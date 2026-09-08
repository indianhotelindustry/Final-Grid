# ADR-003 — Room-Rent Ownership

| | |
|---|---|
| Status | **DRAFT** — not adopted; **implementation model UNRESOLVED** |
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
