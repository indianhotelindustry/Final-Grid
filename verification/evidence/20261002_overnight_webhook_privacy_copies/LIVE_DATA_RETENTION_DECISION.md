# Live-data copies: retention and disposal decisions

Basis: `LIVE_DATA_COPIES_INVENTORY.md` (same directory). **Nothing has been deleted, moved, encrypted or modified, and nothing may be until the Founder rules.** Every item is **OPEN**.

Governing texts:
- FD-P2-04 condition (12): "the artifact exempt from purge or retained in the recovery store" (`FOUNDER_DECISIONS.md:1163`).
- Condition (11): encrypted artifacts and key custody. Required only for Wave 0 D9 / gate G8.
- "Minimum for a production mutation (PD-005 step 3): conditions 1–7, 9, 10" (same line).
- The packs that created the copies kept them under the evidence rule and left disposal to the Founder (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:78`; `ADR011_PRODUCTION_APPLICATION_REPORT.md:86`).
- No retention period and no "recovery store" location is defined. ADR-012 (archival/retention design) is a separate later decision (`FOUNDER_DECISIONS.md:1143`).

All `.db` copies hold real guest personal data (32 guest rows at source), unencrypted, on the same machine as production.

| ID | Question (one line) | Status |
|---|---|---|
| LD-D1 | Which artifacts are the retained recovery points under FD-P2-04 (12), and where is the recovery store? | OPEN |
| LD-D2 | What happens to derived working copies (restore outputs, migration/negative scenario copies, human-check copy) that are not recovery points? | OPEN |
| LD-D3 | What happens to the redundant byte-identical backups of `99505a47…`? | OPEN |
| LD-D4 | What is `SukoonPMS.zip`, and what is done with it? | OPEN |
| LD-D5 | Which protection and retention period applies to retained copies that hold guest personal data? | OPEN |

---

## LD-D1 — Recovery points and recovery store

- **DECISION ID:** LD-D1
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** recovery (PD-006 / FD-P2-04); ADR-011 production application aftermath
- **QUESTION:** Which artifacts are designated retained recovery points under FD-P2-04 condition (12), where is the "recovery store", and is a fresh backup required now that production has changed after the post-migration backup?
- **WHY REQUIRED:**
  - The committed evidence names two recovery points: `db-backups/pms_20260930_132300_adr011-apply-pre.db` (`99505a47…`) and `…_132529_adr011-apply-post.db` (`12ba7b7e…`) (`ADR011_PRODUCTION_APPLICATION_REPORT.md:83-84`).
  - Both sit in `FinalGrid/db-backups/`, next to the production folder, on one disk.
  - The live HUMAN login changed production after the post-migration backup (4 tables differ, `20260930_135930_adr011_live_human_provenance/REPORT.md:44`). No later backup was found in `db-backups/` (inventory §6).
- **OPTIONS:**
  - (a) Designate the two named backups, with their manifests, as retained recovery points in `db-backups/` as they are, and record that location as the recovery store for now.
  - (b) As (a), plus a second copy off-box or on removable media under custody (a step toward conditions 11/12; no encryption mechanism is decided).
  - (c) Also designate `pms_20260908_193942_recovery_rehearsal.db` and `pms_20260930_111550_adr011-preprod.db`. They are byte-identical to apply-pre and cited by the Recovery Foundation and preprod gate packs.
  - Independently: (d) authorize a fresh `tools/backup_db.py` run plus a `restore_db.py` rehearsal to capture current production (read-only on source, `mode=ro`), or (e) not now.
- **EVIDENCE:** inventory §1 and §6; `FOUNDER_DECISIONS.md:1163`.
- **DEPENDENCIES:** none. For (d), a backup run reads production (`mode=ro`) and needs an explicit authorization under the production boundary.
- **WHAT IS BLOCKED:** LD-D3 (which duplicates may go); a recorded recovery-store definition for G11.
- **WHAT CAN CONTINUE:** everything. Nothing is deleted meanwhile.
- **EXACT ACTION AFTER DECISION:** record the designation, including file names, SHA-256 and location, in `FOUNDER_DECISIONS.md` and in a short evidence note. For (b)/(d), issue a bounded recovery directive (copy or backup, then verify the hash against the manifest and run the restore rehearsal).

## LD-D2 — Derived working copies (not recovery points)

- **DECISION ID:** LD-D2
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** data minimisation / evidence retention
- **QUESTION:** Are the 15 derived copies (13 uncited plus the two hash-cited `mig_branch.db`) retained or disposed of?
  - `adr011_preprod/`: `restored.db`, `mig_main_control.db`, six `neg_*.db`;
  - `adr011_apply/`: `restored_pre.db`, `restored_post.db`, `mig_main_control.db`, `human_check_copy.db`;
  - the temp `restore_rehearsal/restored.db`;
  - and the two `mig_branch.db` whose hashes are cited (`61f608f1…`, `c40b3d16…`).
- **WHY REQUIRED:**
  - These files carry guest personal data and are not recovery points.
  - Their evidential content (hashes, gate results) is committed: the restore manifests, `preprod_final.json:39` and `preprod_apply_rehearsal.json:37`.
  - Deleting one removes the ability to re-hash that exact file against a cited value. That matters only for the two `mig_branch.db` files and for the restore outputs, whose bytes equal their backups.
- **OPTIONS:**
  - (a) Retain all until ADR-012 retention design is adopted.
  - (b) Dispose of all derived copies after recording a disposal note (file, size, SHA-256, date, authority). The cited hashes stay in git, and the backups remain to regenerate equivalents.
  - (c) Dispose of everything except the two `mig_branch.db` files.
  - (d) Move them into one access-restricted archive location with the recovery points (LD-D5), then decide later.
- **EVIDENCE:** inventory §2, §3, §5 and §6.
- **DEPENDENCIES:** LD-D5 for the handling standard. If disposal is chosen, the disposal method needs its own authorization.
- **WHAT IS BLOCKED:** nothing technical.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the ruling. For (b)/(c)/(d), a bounded directive does three things: re-hash each file and compare it to the inventory, act only on the listed files, and commit a disposal/move record citing this inventory.

## LD-D3 — Redundant identical backups of `99505a47…`

- **DECISION ID:** LD-D3
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** recovery / data minimisation
- **QUESTION:** `db-backups/` holds three byte-identical backups of the pre-ADR-011 content (`…20260908_193942_recovery_rehearsal.db`, `…20260930_111550_adr011-preprod.db`, `…20260930_132300_adr011-apply-pre.db`). Are all three kept?
- **WHY REQUIRED:** Each is cited by a different committed pack: Recovery Foundation, preprod gate and production application respectively. Only apply-pre is named a recovery point. Keeping all three triples the personal-data exposure. Keeping one preserves the bytes behind every cited hash, because all three share one SHA-256 and each pack can be re-verified against that file.
- **OPTIONS:**
  - (a) Keep all three. Each pack's cited path stays valid.
  - (b) Keep `…132300_adr011-apply-pre.db` only, and record in a note that the other two paths are byte-identical (same SHA-256) to it.
  - (c) Keep two: apply-pre (recovery point) and the 2026-09-08 rehearsal artifact (PD-006 origin).
- **EVIDENCE:** inventory §1 and §6; the identical manifest hashes are recorded in the committed manifests.
- **DEPENDENCIES:** LD-D1.
- **WHAT IS BLOCKED:** nothing.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** as LD-D2 (bounded directive, re-hash, disposal record).

## LD-D4 — `SukoonPMS.zip`

- **DECISION ID:** LD-D4
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** data inventory / privacy
- **QUESTION:** What is `FinalGrid/SukoonPMS.zip` (120,498,117 B, 2026-09-19 16:08, SHA-256 `abaecf8e…a8429`), may its entry list be read to classify it, and is it kept?
- **WHY REQUIRED:** No repository text refers to it. Its contents were not listed, so whether it holds production `instance/pms.db`, `.env` secrets or guest documents is **NOT VERIFIED**. If it is a copy of the install folder from 2026-09-19, it holds personal data and possibly credentials.
- **OPTIONS:**
  - (a) The Founder states its origin and purpose, and it is kept as is.
  - (b) Authorize a read-only listing of entry names (no extraction) to classify it, then decide.
  - (c) Treat it as a live-data copy under LD-D5 (restricted location / retention period).
  - (d) Dispose of it after classification.
- **EVIDENCE:** inventory §4.
- **DEPENDENCIES:** LD-D5.
- **WHAT IS BLOCKED:** a complete live-data inventory.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the ruling. For (b), run `unzip -l` or an equivalent read-only listing, record names only, and record no file contents.

## LD-D5 — Protection and retention period for retained copies

- **DECISION ID:** LD-D5
- **DATE DISCOVERED:** 2026-10-02
- **WORKSTREAM:** privacy; ADR-012 retention design; FD-P2-04 conditions 11/12
- **QUESTION:** For every copy that is kept, what is the handling standard (location, access restriction, encryption) and the retention period or review date?
- **WHY REQUIRED:**
  - All kept copies hold guest personal data, unencrypted, in the user's Downloads tree next to production.
  - FD-P2-04 (12) requires retention in a recovery store but defines neither a store nor a period. Condition (11), encryption and key custody, is not yet implemented ("Implementation status: not implemented", `FOUNDER_DECISIONS.md:1166`).
  - ADR-012 classes and periods are a separate later decision (`FOUNDER_DECISIONS.md:1143`).
- **OPTIONS:**
  - (a) Status quo until ADR-012, with an explicit review date.
  - (b) Move the kept copies into one access-restricted folder (OS permissions) now, and keep the period undecided.
  - (c) Interim rule: keep recovery points until superseded by a newer verified recovery point plus N days, and keep derived copies for at most M days. The Founder sets N and M.
  - (d) Wait for the recovery-hardening directive (encrypted backups with custody, FD-P2-04 implementation) and migrate the kept copies into it.
- **EVIDENCE:** inventory; `FOUNDER_DECISIONS.md:1143,1163,1166`.
- **DEPENDENCIES:** ADR-012 (not decided); the recovery-hardening directive (not issued).
- **WHAT IS BLOCKED:** final disposition under LD-D2/LD-D3/LD-D4.
- **WHAT CAN CONTINUE:** everything.
- **EXACT ACTION AFTER DECISION:** record the interim rule verbatim. Apply it only through a bounded directive that re-verifies each file's SHA-256 against `LIVE_DATA_COPIES_INVENTORY.md` before acting and commits a record of what was moved or disposed of.
