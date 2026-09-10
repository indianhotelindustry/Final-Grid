# Implementation Consequences of Round 3 — what each ruling permits later

Directive FG-P2-FOUNDER-RESOLUTION-20260910-01. **Nothing below is authorized by the recording itself**; each line names the separate bounded directive that a ruling now permits, its scope boundary, and the evidence its closure needs (FD-004 authority chain: Founder decision → governance → implementation directive → mutation → verification evidence).

| Ruling | Permits (later directive) | Scope boundary | Closure evidence | Does NOT permit |
|---|---|---|---|---|
| FD-P2-01 | Phase 2b scoping under the Admin model; the day-one operating procedure's account rule | roles and routes unchanged; no new role; Phase 2a matrix frozen | Phase 2a matrix re-run 29/29 at the next tag; day-one procedure text | Phase 4 authorization work; any role/route change |
| FD-P2-02 | **Retention-control directive**: remove `AuditLog` from `_prune_old_logs`; `WebhookLog`/`NotificationLog` unchanged | one function in `app/__init__.py`; no scheduler job added/removed; no audit row touched | diff limited to that function; copy test: `audit_logs` rows older than 90 days survive a prune run while webhook/notification rows are pruned; GM/replay/inv unchanged; production anchor unchanged | archival, retention classes, archive-then-delete, any other scheduler change |
| FD-P2-03 | Certification pack format for G12: declared-exception register (8 objects) + set comparison against the `inv-run` violation set | no data, invariant or report change | in the certification pack: register, violation set, equality shown, hash of `rules_a.py` unchanged, D11 rows by id/amount | attribution, reversal, deletion, invoice/GST change, invariant change, disposition (B-3) |
| FD-P2-04 | **Recovery-hardening directive**: operating backup path via the SQLite backup API with SHA-256 + `integrity_check` + per-table manifest; retention exemption for pre-mutation/pre-update artifacts; documented key-custody procedure; one **off-box** restore rehearsal of an application-made `.enc` backup meeting all twelve conditions; optional scheduled verification | `app/backup_manager.py` and/or `tools/`; manifest as file (no schema change) unless PD-004 is issued for a `backup_logs` column | rehearsal manifest with all twelve conditions PASS; `inv-run` and `gm-verify` on a copy of the restored file; custody document (no key material in evidence); production anchor unchanged | any production mutation; a `backup_logs` schema change without PD-004 |
| FD-P2-05 | Daily-close procedure document; Phase 3 directives for units 3.5 (interrupted-close recovery) and 3.6 (staleness escalation) scoped as first-release controls; G11 rehearsal expectation (N-day manual closes) | `night_audit_enabled` stays `false`; no scheduler enablement | procedure text; Phase 3 packs; multi-day manual-close rehearsal pack (INV-B01–B06 HOLD after each close) | enabling `night_audit_job`; automation before the B-1 ADR |
| FD-P2-06 | **Phase 6 invariant-refinement directive**: INV-B06 admits `payment_purpose='advance'` on/before arrival and cancellation refunds on/before cancellation; INV-D02 accepts a reversal row referenced by `reservations.cancellation_refund_payment_id`; `DS-ACT-VOIDCN` declaration updated; negative seeds and `inv-commission` for both | `verification/invariants/` and `verification/datasets/` only | commissioning record showing each refined rule still fails its negative seed; production `inv-run` unchanged except the two rules' populations; datasets 5/5; no diff under `app/` | any change to payment, refund, business-date or cancellation behaviour |
| FD-P2-07 | Adoption of ADR-010 with the operation matrix (B-2): tiers, ₹10,000 threshold, no self-approval, operation-specific mandatory controls, emergency/admin control with mandatory reason and flagged audit; then Phase 2b implementation once CF-10 is delivered | ADR text first; 2b schema-free unless PD-004 | ADR-010 ADOPTED and indexed; 2b packs: per-operation maker≠checker negative matrix, audit rows per transition, existing void/refund control unchanged | implementing maker-checker now; changing the void/refund control (N2) |

## Suggested sequence of directives (not an authorization)

1. Retention-control directive (FD-P2-02) — smallest, time-bound.
2. CF-11 credit-path fix and CF-10 audit-coupling normalization (pre-2b package, already permitted by Q5-P1 / P1-ACC).
3. Invariant-refinement directive (FD-P2-06).
4. Recovery-hardening directive (FD-P2-04).
5. Phase 3 (business date, night audit; FD-P2-05).
6. ADR-010 adoption (FD-P2-07) → Phase 2b.
7. Deployment rehearsal and certification (FD-P2-03 register).

Each directive: one authorizing reference, one commit, one evidence pack (SC-6); production anchor verified at start and end (SC-1).
