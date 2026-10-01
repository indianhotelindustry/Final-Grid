# Live-data copies outside the repository: inventory

| | |
|---|---|
| Date | 2026-10-02 (taken between 00:40 and 01:10 +0530) |
| Kind | Read-only inventory. Files were listed, `stat`-ed and hashed with `sha256sum`. **No database was opened** (no sqlite), nothing was extracted, moved, modified or deleted. The live folder `SukoonPMS/` was not opened. |
| Root | `C:/Users/SIPL Server/Downloads/DSS/FinalGrid/` (written `FinalGrid/` below) |
| Times | local (+0530). "Created" is the filesystem birth time; "Modified" is the mtime. |
| Decisions | `LIVE_DATA_RETENTION_DECISION.md` (LD-D1…LD-D5) |

**Personal data.** Every `.db` below is a byte copy of production `instance/pms.db`, or a copy derived from it, with the same size (733,184 B). The committed backup manifests record 32 `guests`, 4 `reservations`, 6 `payments` and 1 `users` row at the source (`20260930_adr011_production_application/backup_pre_manifest.json`, `row_counts`). Those copies therefore hold real guest personal data. They are plain SQLite files, not encrypted: `method: sqlite-backup-api`, with no encryption in the manifests. Their content was not inspected for this inventory.

**Recovery points named in committed evidence:**
- Pre-migration: `db-backups/pms_20260930_132300_adr011-apply-pre.db`, `99505a47…`.
- Post-migration, "the new recovery point": `db-backups/pms_20260930_132529_adr011-apply-post.db`, `12ba7b7e…`.

Sources: `20260930_adr011_production_application/ADR011_PRODUCTION_APPLICATION_REPORT.md:23,64,83-84`.

## 1. `FinalGrid/db-backups/` (8 files, made by `tools/backup_db.py`)

| File | Size (B) | Created | Modified | SHA-256 | Purpose / cited by (committed) | Required for recovery evidence? |
|---|---|---|---|---|---|---|
| `pms_20260908_193942_recovery_rehearsal.db` | 733,184 | 2026-09-08 19:39:42 | 2026-09-08 19:39:42 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | Recovery Foundation backup for rehearsal RR-20260908-01. Cited by `20260908_recovery_foundation/RESTORE_REHEARSAL.md:20`, `backup_manifest.json`, `restore_manifest.json`, `result.json`, `IMPLEMENTATION_RECORD.md` | **Cited** as a PD-006 rehearsal artifact, not as a current recovery point. Byte-identical to the two `99505a47` backups below. |
| `pms_20260908_193942_recovery_rehearsal.db.manifest.json` | 2,344 | 2026-09-08 19:39:42 | 2026-09-08 19:39:42 | `20ad0c0143a342f6cdac66cceefdb54fd4ec87db07f3f1b9a4c904d61876e016` | Backup manifest. Byte-identical to committed `20260908_recovery_foundation/backup_manifest.json` | Copy is committed |
| `pms_20260930_111550_adr011-preprod.db` | 733,184 | 2026-09-30 11:15:50 | 2026-09-30 11:15:50 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | ADR-011 pre-production gate backup, gate 6 (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:34`). Source of restore RR-20260930-ADR011. Cited by the gate `RESULT.json`, `restore/backup_manifest.json`, `restore/restore_manifest.json` | **Cited** (gate evidence). Report `:78` says "(retained)". |
| `pms_20260930_111550_adr011-preprod.db.manifest.json` | 2,336 | 2026-09-30 11:15:50 | 2026-09-30 11:15:50 | `609af57273be7815a6d20d60fcb3ec414eaae58a9b53b8d1ea4a5fe071cb1a64` | Byte-identical to committed `20260930_adr011_preprod_gate/restore/backup_manifest.json` | Copy is committed |
| `pms_20260930_132300_adr011-apply-pre.db` | 733,184 | 2026-09-30 13:23:00 | 2026-09-30 13:23:00 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | **Pre-migration recovery point**, restore-rehearsed (`ADR011_PRODUCTION_APPLICATION_REPORT.md:23,83`). Cited by that pack's `RESULT.json`, `backup_pre.log`, `backup_pre_manifest.json`, `restore_pre_manifest.json` | **YES: named recovery point** |
| `pms_20260930_132300_adr011-apply-pre.db.manifest.json` | 2,340 | 2026-09-30 13:23:00 | 2026-09-30 13:23:00 | `b510a792b310378d1d1b57eda0e741c846a58e6115081d743c49e6859ec45463` | Byte-identical to committed `20260930_adr011_production_application/backup_pre_manifest.json` | Copy is committed |
| `pms_20260930_132529_adr011-apply-post.db` | 733,184 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `12ba7b7eb8004b43492829b5c1f153e0010f777e0b2c146f86b423cb39c8fac6` | **Post-migration recovery point**, "the new recovery point", restore-rehearsed (`ADR011_PRODUCTION_APPLICATION_REPORT.md:64,84`). Also the comparison baseline of `20260930_135930_adr011_live_human_provenance/REPORT.md:6` | **YES: named recovery point**, the latest one recorded |
| `pms_20260930_132529_adr011-apply-post.db.manifest.json` | 2,342 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `9c825ce171c9028a4805509ec0e2ced7e0dc2d7956eda8a3b88f2cf481424023` | Byte-identical to committed `20260930_adr011_production_application/backup_post_manifest.json` | Copy is committed |

## 2. `FinalGrid/adr011_preprod/` (10 files: 9 `.db` + 1 manifest, made by the pre-production gate, `verify_preprod.py`)

| File | Size (B) | Created | Modified | SHA-256 | Purpose / cited by | Required for recovery evidence? |
|---|---|---|---|---|---|---|
| `restored.db` | 733,184 | 2026-09-30 11:15:57 | 2026-09-30 11:15:57 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | Restore-rehearsal output RR-20260930-ADR011 (`restored_path` in committed `20260930_adr011_preprod_gate/restore/restore_manifest.json:186`) | No. It is a restore output, byte-identical to the backup. |
| `restored.db.restore_manifest.json` | 7,984 | 2026-09-30 11:15:57 | 2026-09-30 11:15:57 | `b1702a32897a8451d584d3930dcfb8353cbd8ce19cba31d7eeddbdb3a986f0a2` | Byte-identical to committed `20260930_adr011_preprod_gate/restore/restore_manifest.json` | Copy is committed |
| `mig_branch.db` | 733,184 | 2026-09-30 11:17:51 | 2026-09-30 11:22:54 | `61f608f12a3ce9d08b298d9031950f184795176f0dde6f2def204504f409c5f7` | Migration rehearsal: restored copy booted on the branch (`verify_preprod.py:156`). Hash recorded in `preprod_final.json:39` | No. Its hash is gate evidence; the file is a rehearsal product. |
| `mig_main_control.db` | 733,184 | 2026-09-30 11:17:51 | 2026-09-30 11:22:53 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | Control copy booted on `main` (`verify_preprod.py:157`). Unchanged bytes. | No |
| `neg_validation.db` | 733,184 | 2026-09-30 11:18:08 | 2026-09-30 11:22:59 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | Negative-scenario copy (`verify_preprod.py:352`, `neg_%s.db`). Unchanged bytes. | No (hash not cited) |
| `neg_hist_zero.db` | 733,184 | 2026-09-30 11:18:09 | 2026-09-30 11:23:00 | `cf504c3297871b62d5c0382cd4a1c808886bcd13cab103006dc6f7d563ca7935` | Negative-scenario copy (history with actor 0) | No (hash not cited) |
| `neg_hist_dangling.db` | 733,184 | 2026-09-30 11:18:10 | 2026-09-30 11:23:01 | `85987dd9303bb6cd4351172f25cef3e091ff92897f37e239ef980c7f76d2535a` | Negative-scenario copy | No (hash not cited) |
| `neg_hist_mixed.db` | 733,184 | 2026-09-30 11:18:11 | 2026-09-30 11:23:01 | `e7cbc7f0a3184be69836e49bb5fe2af8488f004bb33962811e968ad271b17214` | Negative-scenario copy | No (hash not cited) |
| `neg_interrupt_drop.db` | 733,184 | 2026-09-30 11:18:12 | 2026-09-30 11:23:04 | `0ccde371d6ec5afa252522932c77fdccf9651b48e78b7c0e0427763a4c9a0a6f` | Negative-scenario copy (interrupted migration) | No (hash not cited) |
| `neg_interrupt_alter.db` | 733,184 | 2026-09-30 11:18:14 | 2026-09-30 11:23:06 | `44f71df7c52c499eb5d92826df693f60738d6c691822918510d2f763caa2c42a` | Negative-scenario copy (interrupted migration) | No (hash not cited) |

The gate report says of this folder and `db-backups/`: "They hold copies of live data and were **not deleted** (evidence rule); their disposal is for the Founder" (`ADR011_PRE_PRODUCTION_GATE_REPORT.md:78`).

## 3. `FinalGrid/adr011_apply/` (7 top-level files + `evidence/` with 40 files)

| File | Size (B) | Created | Modified | SHA-256 | Purpose / cited by | Required for recovery evidence? |
|---|---|---|---|---|---|---|
| `restored_pre.db` | 733,184 | 2026-09-30 13:23:01 | 2026-09-30 13:23:01 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | Restore rehearsal of the apply-pre backup (`restored_path` in committed `restore_pre_manifest.json:186`) | No (restore output; identical to the backup) |
| `restored_pre.db.restore_manifest.json` | 7,993 | 2026-09-30 13:23:01 | 2026-09-30 13:23:01 | `7f4f6d96096d2b16026b24bf7cac94ba67c04e1009674a5a989f3a8d28a9d9a8` | Byte-identical to committed `20260930_adr011_production_application/restore_pre_manifest.json` | Copy is committed |
| `restored_post.db` | 733,184 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `12ba7b7eb8004b43492829b5c1f153e0010f777e0b2c146f86b423cb39c8fac6` | Restore rehearsal of the apply-post backup (committed `restore_post/restore_manifest.json:186`). Source of `human_provenance_copy.py` | No (restore output; identical to the backup) |
| `restored_post.db.restore_manifest.json` | 8,009 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `615f0dbf5ef2a46c2a889a396155d5319827d3e1e58054746f4bc26dff0aaea5` | Byte-identical to committed `restore_post/restore_manifest.json` | Copy is committed |
| `mig_branch.db` | 733,184 | 2026-09-30 13:23:57 | 2026-09-30 13:23:59 | `c40b3d16730de412d7cb52bbd0428e0ac789e06dcb0c56e8d1ab77f668e3baf4` | Apply rehearsal on a copy. Hash recorded in committed `preprod_apply_rehearsal.json:37` | No (rehearsal product; hash is evidence) |
| `mig_main_control.db` | 733,184 | 2026-09-30 13:23:57 | 2026-09-30 13:23:57 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | Control copy. Unchanged bytes. | No |
| `human_check_copy.db` | 733,184 | 2026-09-30 13:25:59 | 2026-09-30 13:26:13 | `97ddd877c371fbea65dff224b14aa4dfb2ec045dab11ab76e7cf158189b8ad6b` | HUMAN-provenance check on a copy of the migrated database. Named in the committed `RESULT.json` and `human_provenance_copy.log`; hash not cited | No (hash not cited) |

### 3.1 `adr011_apply/evidence/`: staging copy of the committed pack `20260930_adr011_production_application/`

38 of 40 files are byte-identical to a committed file, listed in the last column. The 2 uncommitted files, `packs_before_pre.txt` and `packs_before_post.txt`, list PVF pack directory names only; both were read and contain no personal data.

| File | Size (B) | Created | Modified | SHA-256 | Byte-identical committed copy (under `20260930_adr011_production_application/`) |
|---|---|---|---|---|---|
| `backup_post.log` | 405 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `11da2dd0e200de3cf4f77736c35b48e85409b9a8ef94db3adc0e55664e46efaf` | backup_post.log |
| `backup_post_manifest.json` | 2342 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `9c825ce171c9028a4805509ec0e2ced7e0dc2d7956eda8a3b88f2cf481424023` | backup_post_manifest.json |
| `backup_pre.log` | 483 | 2026-09-30 13:23:00 | 2026-09-30 13:23:00 | `75467c8b3e43c2f7b31e88859f1bdda1b022303d14fd48f1a4051708d822b3fd` | backup_pre.log |
| `backup_pre_manifest.json` | 2340 | 2026-09-30 13:23:00 | 2026-09-30 13:23:00 | `b510a792b310378d1d1b57eda0e741c846a58e6115081d743c49e6859ec45463` | backup_pre_manifest.json |
| `first_start.log` | 2782 | 2026-09-30 13:24:34 | 2026-09-30 13:24:35 | `474ca43813188ea29dcd93136b939b8431c43609640a63f3b642eee2cb8dfb9e` | first_start.log |
| `first_start.py` | 1386 | 2026-09-30 13:24:32 | 2026-09-30 13:24:32 | `00888fed7aab9e5ce3c668b2182569c2f980f70f055945cfd6062606f18eeb72` | first_start.py |
| `human_provenance_copy.log` | 2086 | 2026-09-30 13:25:59 | 2026-09-30 13:26:13 | `cd1c52f71d7caca4f3475b13328caad792591b57b0ecae4004bdbbb003312bf9` | human_provenance_copy.log |
| `human_provenance_copy.py` | 2256 | 2026-09-30 13:26:11 | 2026-09-30 13:26:11 | `4e2974e822320c5581b5ede9d9d1fe3ae1145bf2b39b013f8118383658b23797` | human_provenance_copy.py |
| `packs_before_post.txt` | 700 | 2026-09-30 13:26:28 | 2026-09-30 13:26:28 | `549fda53f4d763b5646ee407fbe984aa09700dd630a139a281a89965e8385cde` | none (not committed) |
| `packs_before_pre.txt` | 596 | 2026-09-30 13:23:40 | 2026-09-30 13:23:40 | `53c91ab449c439af994bb75717ec2c50a0cdbca252d92edf1412f520164f12d5` | none (not committed) |
| `post_cross.log` | 13827 | 2026-09-30 13:26:43 | 2026-09-30 13:26:44 | `7a70fdcfc94c6bc6e9911555c3d81bf37df441c70bfeced10553b7cc49ff9ad8` | post_cross.log |
| `post_gm.log` | 5449 | 2026-09-30 13:26:30 | 2026-09-30 13:26:40 | `d7c1926c4845e444d7d31b14f5d885850178595577601b3cf6904dfc68cbfb7e` | post_gm.log |
| `post_ident.log` | 11648 | 2026-09-30 13:25:38 | 2026-09-30 13:25:40 | `859b0b36d615b57a32712511a7366884e9143e7eb06d50683169e81614adcc79` | post_ident.log |
| `post_inv.log` | 19142 | 2026-09-30 13:26:28 | 2026-09-30 13:26:30 | `da8b608a9efeacfb4ae3cc605b132a5d56fa8c1b21b6651c7a7c17fe4bb2f912` | post_inv.log |
| `post_replay.log` | 6919 | 2026-09-30 13:26:40 | 2026-09-30 13:26:42 | `540aa6e8b887433ca5ead7538b56ff56bfaa4224f71d32ae11d8482d48df460b` | post_replay.log |
| `pre_gm.log` | 5449 | 2026-09-30 13:23:44 | 2026-09-30 13:23:56 | `76e0c49d9f9bd9916e49dd2851b5004af33d842cb6c8465679ceaa9fd4b11966` | pre_gm.log |
| `pre_inv.log` | 19142 | 2026-09-30 13:23:40 | 2026-09-30 13:23:44 | `376b53e63551448189bdc420ce1601270a78cb2c8cc81b64a7c6985348f3025d` | pre_inv.log |
| `preprod_apply_post_ident.json` | 14841 | 2026-09-30 13:25:40 | 2026-09-30 13:25:40 | `6b2fd81d79ff4930681a8a2ce5ea74581a49814722f7a2cb172f2259c7e1efb1` | preprod_apply_post_ident.json |
| `preprod_apply_rehearsal.json` | 42602 | 2026-09-30 13:24:03 | 2026-09-30 13:24:03 | `3eaea6e5f21d3e2f6b394e3f615b4a48860e536de5c6168738b3a40b5bc7478a` | preprod_apply_rehearsal.json |
| `prod_post_state.json` | 7294 | 2026-09-30 13:24:53 | 2026-09-30 13:24:53 | `ab7752822328e81b4478baf0a379823ab068c154bc82c48fc111fcba8787648f` | prod_post_state.json |
| `prod_pre_state.json` | 6921 | 2026-09-30 13:23:29 | 2026-09-30 13:23:29 | `9d1ffc6e6b0f6dab293ff6bc10c7189631195c2cf292ba9e50dac53564038c29` | prod_pre_state.json |
| `pvf_post/20260930_075629_inv_run_production/report.txt` | 12701 | 2026-09-30 13:26:30 | 2026-09-30 13:26:30 | `ac097795f79914349dab4319ecb391272154ffa8dd1b15d3ef82c44080c4e962` | pvf_post/20260930_075629_inv_run_production/report.txt |
| `pvf_post/20260930_075629_inv_run_production/result.json` | 37144 | 2026-09-30 13:26:30 | 2026-09-30 13:26:30 | `878836559abf40ce6f8b7e8fd5b689b9e1543ec6f40228e8e1381c1d4c1a6be9` | pvf_post/20260930_075629_inv_run_production/result.json |
| `pvf_post/20260930_075631_gm_verify_phase1_aa6d9e91/report.txt` | 1004 | 2026-09-30 13:26:40 | 2026-09-30 13:26:40 | `b926adc95db69da313854ad2d7eb99c725fd69acc134e29e33dd72a44ef582f0` | pvf_post/20260930_075631_gm_verify_phase1_aa6d9e91/report.txt |
| `pvf_post/20260930_075631_gm_verify_phase1_aa6d9e91/result.json` | 444 | 2026-09-30 13:26:40 | 2026-09-30 13:26:40 | `797882725ddc7dbd30747e3e1f54d00b5d359581ab6b036321edf94af1c37e58` | pvf_post/20260930_075631_gm_verify_phase1_aa6d9e91/result.json, pvf_pre/20260930_075346_gm_verify_phase1_aa6d9e91/result.json |
| `pvf_post/20260930_075641_replay_verify_production/report.txt` | 1879 | 2026-09-30 13:26:42 | 2026-09-30 13:26:42 | `73e7c078792f23e52e42319a54409b90fee811c158660c557a0f2fa86ba46aa5` | pvf_post/20260930_075641_replay_verify_production/report.txt |
| `pvf_post/20260930_075641_replay_verify_production/result.json` | 991 | 2026-09-30 13:26:42 | 2026-09-30 13:26:42 | `62211b834a1a4982d4116fac59ade20fc3cba951844c155963dd7348da0efbae` | pvf_post/20260930_075641_replay_verify_production/result.json |
| `pvf_post/20260930_075643_cross_implementation/report.txt` | 8493 | 2026-09-30 13:26:44 | 2026-09-30 13:26:44 | `54fa2639041d196673f8d3ce2f8a9b66a6bf02a312b9390189ca2056dbf7672e` | pvf_post/20260930_075643_cross_implementation/report.txt |
| `pvf_post/20260930_075643_cross_implementation/result.json` | 22757 | 2026-09-30 13:26:44 | 2026-09-30 13:26:44 | `6ad9233ed4bae2982ff38b5b41e599c3fab5e5a81c7f7d31754c61a7da52888b` | pvf_post/20260930_075643_cross_implementation/result.json |
| `pvf_pre/20260930_075341_inv_run_production/report.txt` | 12701 | 2026-09-30 13:23:44 | 2026-09-30 13:23:44 | `4ed50ed10e99a0b4522d7bc4a278158f6238f6b3fcf501670faa16269b118aaa` | pvf_pre/20260930_075341_inv_run_production/report.txt |
| `pvf_pre/20260930_075341_inv_run_production/result.json` | 37147 | 2026-09-30 13:23:44 | 2026-09-30 13:23:44 | `2e9fb203d30d524bc2cba5f4a0342bf76a24119e7a8ad377ddd33b3b67bbde2e` | pvf_pre/20260930_075341_inv_run_production/result.json |
| `pvf_pre/20260930_075346_gm_verify_phase1_aa6d9e91/report.txt` | 1004 | 2026-09-30 13:23:56 | 2026-09-30 13:23:56 | `c648f5c0266d72f51fc13423d6b6e8a1326e9312a38e6323f97cf982f7ba2583` | pvf_pre/20260930_075346_gm_verify_phase1_aa6d9e91/report.txt |
| `pvf_pre/20260930_075346_gm_verify_phase1_aa6d9e91/result.json` | 444 | 2026-09-30 13:23:56 | 2026-09-30 13:23:56 | `797882725ddc7dbd30747e3e1f54d00b5d359581ab6b036321edf94af1c37e58` | pvf_post/20260930_075631_gm_verify_phase1_aa6d9e91/result.json, pvf_pre/20260930_075346_gm_verify_phase1_aa6d9e91/result.json |
| `rehearsal.log` | 2536 | 2026-09-30 13:23:57 | 2026-09-30 13:24:03 | `76661a258b4090aeee47f5753afc3d9f0ede7b6ffe5cd1113e4a68820e5b3e9c` | rehearsal.log |
| `restore_manifest.json` | 7993 | 2026-09-30 13:23:01 | 2026-09-30 13:23:01 | `7f4f6d96096d2b16026b24bf7cac94ba67c04e1009674a5a989f3a8d28a9d9a8` | restore_pre_manifest.json |
| `restore_post.log` | 572 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `615a68ea0ddee042daf3ebc4c47bedbace01188c52ad19c7c5269b7f6fec2a62` | restore_post.log |
| `restore_post/restore_manifest.json` | 8009 | 2026-09-30 13:25:29 | 2026-09-30 13:25:29 | `615f0dbf5ef2a46c2a889a396155d5319827d3e1e58054746f4bc26dff0aaea5` | restore_post/restore_manifest.json |
| `restore_pre.log` | 571 | 2026-09-30 13:23:01 | 2026-09-30 13:23:01 | `d2104220356aef5486aa3f384381655f5afb352a83651b81025fd4922c678726` | restore_pre.log |
| `smoke.log` | 2341 | 2026-09-30 13:25:14 | 2026-09-30 13:25:16 | `4fa947c6fd5fa968409d4c37c2c39e8432e185f4d5636c3cb31284ec0442fd72` | smoke.log |
| `smoke.py` | 1216 | 2026-09-30 13:25:13 | 2026-09-30 13:25:13 | `c0bd41234e65c34a155a8ad955696aba8f8c67fa43883f649a1061fa734859e6` | smoke.py |

## 4. `FinalGrid/SukoonPMS.zip`

| File | Size (B) | Created | Modified | SHA-256 | Purpose / cited by | Required for recovery evidence? |
|---|---|---|---|---|---|---|
| `SukoonPMS.zip` | 120,498,117 | 2026-09-19 16:07:51 | 2026-09-19 16:08:07 | `abaecf8e03769edb59603f8ede6a510827ee945ba85a822d097e606e70ca8429` | Not referenced anywhere in the repository (`git grep` for the name and hash prefix: 0 hits). Content not listed or extracted. Whether it contains `instance/pms.db`, `.env` or other production data: **NOT VERIFIED**. Its name and size (about 120 MB, larger than the database) suggest an archive of the install folder. | Not cited: **NOT APPLICABLE** to recorded recovery evidence. Content unknown. |

## 5. Additional live-data copy found outside the three folders

| File | Size (B) | Created | Modified | SHA-256 | Purpose / cited by | Required for recovery evidence? |
|---|---|---|---|---|---|---|
| `C:/Users/SIPLSE~1/AppData/Local/Temp/claude/c--Users-SIPL-Server-Downloads-DSS-FinalGrid-SukoonPMS/857307e0-10d6-4769-9b4e-d033974225ec/scratchpad/restore_rehearsal/restored.db` | 733,184 | 2026-09-08 19:39:43 | 2026-09-08 19:39:43 | `99505a475fecc508a91d323ef0387142159ac483d6577d7a6801b40ea49eb3cd` | RR-20260908-01 restore output (`restored_path` in committed `20260908_recovery_foundation/restore_manifest.json:186`) | No (restore output). It sits in a temporary directory that the OS or tooling may clean. |
| same folder `/restored.db.restore_manifest.json` | 8,185 | 2026-09-08 19:39:43 | 2026-09-08 19:39:43 | `fbb0da32898088bb23ff3f644c8ea46179de2b9abde69bb71671b5b28697b88a` | Byte-identical to committed `20260908_recovery_foundation/restore_manifest.json` | Copy is committed |

Also seen in `FinalGrid/` but outside this inventory's scope: `g3_decision_package/` (2026-09-30 19:31) and `.claude/`. They were not listed. Other machines, cloud sync, the application's own `instance/` backups and the production folder were not examined (**NOT VERIFIED**).

## 6. Summary

| Measure | Value |
|---|---|
| Database files (`.db`) inventoried | 19: 4 in `db-backups/`, 9 in `adr011_preprod/`, 5 in `adr011_apply/`, 1 in the temp scratchpad, plus `SukoonPMS.zip` (contents unknown) counted separately |
| Byte-identical copies of `99505a47…` (pre-ADR-011 production content) | 9: three backups, `adr011_preprod/{restored,mig_main_control,neg_validation}.db`, `adr011_apply/{restored_pre,mig_main_control}.db`, temp `restored.db` |
| Copies of `12ba7b7e…` (post-migration content) | 2: `db-backups/…apply-post.db`, `adr011_apply/restored_post.db` |
| Files named by committed evidence as **recovery points** | 2: `…132300_adr011-apply-pre.db` (`99505a47`), `…132529_adr011-apply-post.db` (`12ba7b7e`) |
| Backups cited as rehearsal/gate artifacts (not current recovery points) | 2: `…20260908_193942_recovery_rehearsal.db`, `…20260930_111550_adr011-preprod.db` |
| Derived copies whose hash is cited as evidence but which are not recovery points | 2: `adr011_preprod/mig_branch.db` (`61f608f1`), `adr011_apply/mig_branch.db` (`c40b3d16`) |
| Other derived copies: restore outputs, controls, negatives, human check (none is a recovery point) | 13: the 6 `neg_*`, 3 restore outputs (`adr011_preprod/restored.db`, `adr011_apply/restored_{pre,post}.db`), 2 `mig_main_control`, `human_check_copy`, and the temp restore output. The restore outputs' hashes appear in committed restore manifests only as "identical to the backup". |
| Manifests, logs, scripts | All committed byte-identical except `packs_before_{pre,post}.txt` |
| Total on-disk size of the `.db` copies | 19 × 733,184 B = 13,930,496 B (≈ 13.9 MB), plus the 120.5 MB zip |
| Later backup capturing production after the 2026-09-30 live HUMAN login (production changed, `20260930_135930_adr011_live_human_provenance/REPORT.md:44`) | none found in `db-backups/` (**NOT VERIFIED** elsewhere) |
