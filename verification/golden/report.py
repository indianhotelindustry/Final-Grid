"""
Evidence for golden master runs.

Same contract as the D1 evidence pack: a machine-readable ``result.json``
that a release gate can read, and a ``report.txt`` an engineer actually
reads. Both deterministic given the same inputs.

The capture report leads with what is BROKEN, not with what passed.
A surface that returns 500 is the most important thing on the page and
must not be reachable only by scrolling.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from verification.config import EVIDENCE_DIR, Severity

W = 100


def write_pack(payload: dict, text: str, tag: str, started_at: str) -> str:
    stamp = started_at.replace(':', '').replace('-', '').replace('T', '_')[:15]
    out_dir = os.path.join(EVIDENCE_DIR, f'{stamp}_{tag}')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'result.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, sort_keys=True, default=str)
        fh.write('\n')
    with open(os.path.join(out_dir, 'report.txt'), 'w', encoding='utf-8') as fh:
        fh.write(text)
    return out_dir


def render_capture(run) -> str:
    L: list[str] = []
    add = L.append
    add('=' * W)
    add('DSBC FRONTLINE — GOLDEN MASTER CAPTURE')
    add('Production Verification Framework, Wave 0 Deliverable 2')
    add('=' * W)
    add(f'Started         : {run.started_at}')
    add(f'Duration        : {run.duration_seconds:.1f}s')
    add(f'Application     : v{run.app_version}')
    add(f'PVF             : v{run.pvf_version}')
    add(f'Business date   : {run.business_date}')
    add(f'Clock frozen at : {run.frozen_at}')
    add(f'Identity        : {run.principal.get("username")} '
        f'({run.principal.get("role")})')
    add('')

    add('-' * W)
    add('READ-ONLY GUARANTEE')
    add('-' * W)
    add(f'Source database : {run.source_db}')
    add(f'Copy method     : {run.copy_method}')
    add(f'SHA-256 before  : {run.source_hash_before}')
    add(f'SHA-256 after   : {run.source_hash_after}')
    add('Guarantee       : ' + ('VERIFIED — production byte-identical after run'
                                if run.read_only_verified else
                                '*** NOT VERIFIED — DO NOT TRUST THIS RUN ***'))
    add('')

    add('-' * W)
    add('DETERMINISTIC CLOCK (Principle 11 — positive evidence)')
    add('-' * W)
    proof = run.freeze_proof or {}
    add(f'Frozen to       : {proof.get("frozen_to")}')
    add(f'Names rebound   : {proof.get("rebound_names")}')
    for name, ok in sorted((proof.get('checks') or {}).items()):
        add(f'  {"PASS" if ok else "FAIL"}  {name}')
    add(f'Proven          : {proof.get("proven")}')
    add('')

    counts = run.counts
    add('-' * W)
    add('COVERAGE')
    add('-' * W)
    add(f'  Surfaces captured : {counts["total"]}')
    add(f'  Healthy           : {counts["healthy"]}')
    add(f'  Unhealthy         : {counts["unhealthy"]}')
    for key in ('FINANCIAL', 'OPERATIONAL', 'ADVISORY', 'PUBLIC',
                'UNCLASSIFIED'):
        if key in counts:
            add(f'  {key:<18}: {counts[key]}')
    add(f'  Declared gaps     : {len(run.gaps)}  (listed below — nothing is '
        f'dropped silently)')
    add('')

    unhealthy = run.unhealthy
    if unhealthy:
        add('=' * W)
        add(f'UNHEALTHY SURFACES — {len(unhealthy)}')
        add('=' * W)
        add('These surfaces do not render. They are captured as-is so that any')
        add('change in their behaviour is still detected, but a golden master')
        add('over a 500 is a record of a defect, not evidence of correctness.')
        add('')
        for s in unhealthy:
            add(f'  [{s.severity:<5}] {s.status}  {s.url}')
            add(f'          endpoint {s.endpoint}   category {s.category}')
            if s.error:
                add(f'          error {s.error}')
        add('')

    add('=' * W)
    add('SURFACES')
    add('=' * W)
    add(f'{"STATUS":<7}{"ANON":<6}{"CAT":<13}{"FIGURES":>8}  '
        f'{"ms":>6}  SURFACE')
    add('-' * W)
    for s in run.surfaces:
        add(f'{s.status:<7}{s.anon_status:<6}{s.category[:12]:<13}'
            f'{len(s.figures):>8}  {s.duration_ms:>6}  {s.url}')
    add('')

    add('=' * W)
    add('DECLARED GAPS — discovered but not captured')
    add('=' * W)
    for g in run.gaps:
        add(f'  {g["url"]}')
        add(f'      {g["reason"]}')
    add('')

    add('=' * W)
    add('NORMALISATION RULES APPLIED')
    add('=' * W)
    for rule in run.normalisation_rules:
        add(f'  {rule["name"]}')
        add(f'      pattern: {rule["pattern"]}')
        add(f'      why    : {rule["why"]}')
    add('')
    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def render_comparison(result, run) -> str:
    L: list[str] = []
    add = L.append
    add('=' * W)
    add('DSBC FRONTLINE — GOLDEN MASTER VERIFICATION')
    add('Production Verification Framework, Wave 0 Deliverable 2')
    add('=' * W)
    add(f'Master set      : {result.tag}')
    add(f'Master captured : {result.master_captured_at} '
        f'(app v{result.master_app_version})')
    add(f'Current run     : {run.started_at} (app v{run.app_version})')
    add(f'Master clock    : {result.master_frozen_at}')
    add(f'Current clock   : {run.frozen_at}')
    add(f'Read-only       : {"VERIFIED" if run.read_only_verified else "NOT VERIFIED"}')
    add('')
    add(f'Surfaces compared : {result.surfaces_compared}')
    add(f'Surfaces clean    : {result.surfaces_clean}')
    add(f'Differences       : {len(result.differences)}')
    add(f'Blocking          : {len(result.blocking)}')
    add('')
    add(f'VERDICT           : {result.verdict}')
    add('')

    if result.by_kind:
        add('-' * W)
        add('DIFFERENCES BY KIND')
        add('-' * W)
        for kind, n in sorted(result.by_kind.items()):
            add(f'  {kind:<24} {n:>5}')
        add('')

    if result.differences:
        add('=' * W)
        add('DIFFERENCES')
        add('=' * W)
        current_surface = None
        shown = 0
        for d in result.differences:
            if shown >= 400:
                add(f'  ... {len(result.differences) - shown} more '
                    f'(see result.json — nothing is omitted there)')
                break
            if d.surface_id != current_surface:
                current_surface = d.surface_id
                add('')
                add(f'{d.surface_id}   [{d.category}]')
                add(f'  {d.url}')
            line = f'    [{d.severity:<5}] {d.kind:<22}'
            if d.key:
                line += f' {d.key}'
            add(line)
            if d.master or d.current:
                add(f'            master : {d.master}')
                add(f'            current: {d.current}'
                    + (f'   (delta {d.delta})' if d.delta else ''))
            shown += 1
        add('')
    else:
        add('  No differences. Every captured surface renders exactly what it')
        add('  rendered when the master was taken.')
        add('')

    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'


def capture_payload(run) -> dict:
    payload = asdict(run)
    payload['counts'] = run.counts
    return payload


def comparison_payload(result, run) -> dict:
    return {
        'tag': result.tag,
        'verdict': result.verdict,
        'master_captured_at': result.master_captured_at,
        'master_app_version': result.master_app_version,
        'current_app_version': run.app_version,
        'master_frozen_at': result.master_frozen_at,
        'current_frozen_at': run.frozen_at,
        'read_only_verified': run.read_only_verified,
        'surfaces_compared': result.surfaces_compared,
        'surfaces_clean': result.surfaces_clean,
        'difference_count': len(result.differences),
        'blocking_count': len(result.blocking),
        'by_kind': result.by_kind,
        'differences': [asdict(d) for d in result.differences],
    }
