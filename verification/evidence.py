"""
Evidence pack writer.

Constitutional basis: Phase 2.6 §13 (Evidence Model). Working code without
evidence has not been delivered, because nobody can demonstrate it is
safe.

Every PVF run emits two artefacts to the same timestamped directory:

  result.json   machine-readable, diffable, the input to release gates
  report.txt    human-readable, the thing an engineer actually reads

Both are deterministic: given the same measurements they are byte-
identical, so a diff between two runs shows only real change.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any

from verification.config import (
    EVIDENCE_DIR, INCOMPLETE_VERDICTS, NON_PASSING, SEVERITY_RANK,
    Severity, Verdict,
)


def _json_default(obj: Any):
    """Serialise the types our measurements actually produce.

    Deliberately narrow: an unexpected type raises rather than being
    coerced to a string, because silently stringifying a Decimal would
    make the evidence pack lie about precision.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    import datetime as _dt
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f'PVF evidence cannot serialise {type(obj).__name__}: {obj!r}')


@dataclass
class Divergence:
    """One disagreement between two implementations of a quantity."""
    scope: str                  # which reservation / date / folio
    impl_a: str
    impl_b: str
    value_a: Any
    value_b: Any
    delta: Any


@dataclass
class QuantityResult:
    """The outcome of measuring one of the 22 parity quantities."""
    quantity_id: str
    label: str
    policy: str
    severity: str
    verdict: str
    implementations: dict[str, Any] = field(default_factory=dict)
    divergences: list[Divergence] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    note: str = ''
    error: str = ''
    duration_ms: int = 0

    @property
    def passing(self) -> bool:
        return self.verdict not in NON_PASSING


@dataclass
class RunResult:
    """A complete PVF run."""
    mode: str
    started_at: str
    finished_at: str = ''
    duration_seconds: float = 0.0
    app_version: str = ''
    pvf_version: str = ''
    source_db: str = ''
    source_hash_before: str = ''
    source_hash_after: str = ''
    source_size_bytes: int = 0
    copy_method: str = ''
    read_only_verified: bool = False
    quantities: list[QuantityResult] = field(default_factory=list)

    # -- aggregates -------------------------------------------------------

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for q in self.quantities:
            out[q.verdict] = out.get(q.verdict, 0) + 1
        return out

    @property
    def blocking_failures(self) -> list[QuantityResult]:
        return [q for q in self.quantities
                if not q.passing and q.severity == Severity.BLOCK]

    @property
    def overall(self) -> str:
        """PASS only when nothing non-passing carries BLOCK severity AND
        no quantity errored. NOT_IMPLEMENTED never yields PASS — a harness
        that omits a quantity has not verified it (Principle 10)."""
        if any(q.verdict == Verdict.ERROR for q in self.quantities):
            return 'ERROR'
        if self.blocking_failures:
            return 'FAIL'
        if any(q.verdict in INCOMPLETE_VERDICTS for q in self.quantities):
            return 'INCOMPLETE'
        if not self.read_only_verified:
            return 'UNVERIFIED'
        return 'PASS'


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_pack(run: RunResult, tag: str = '') -> str:
    """Write result.json and report.txt. Returns the directory path."""
    stamp = run.started_at.replace(':', '').replace('-', '').replace('T', '_')[:15]
    name = f'{stamp}_{tag}' if tag else stamp
    out_dir = os.path.join(EVIDENCE_DIR, name)
    os.makedirs(out_dir, exist_ok=True)

    payload = asdict(run)
    payload['overall'] = run.overall
    payload['counts'] = run.counts
    with open(os.path.join(out_dir, 'result.json'), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, default=_json_default, sort_keys=True)
        fh.write('\n')

    with open(os.path.join(out_dir, 'report.txt'), 'w', encoding='utf-8') as fh:
        fh.write(render_report(run))

    return out_dir


def render_report(run: RunResult) -> str:
    """Human-readable report. Deterministic."""
    W = 100
    L: list[str] = []
    add = L.append

    add('=' * W)
    add('DSBC FRONTLINE — FINANCIAL PARITY HARNESS')
    add('Production Verification Framework, Wave 0 Deliverable 1')
    add('=' * W)
    add(f'Mode            : {run.mode}')
    add(f'Started         : {run.started_at}')
    add(f'Finished        : {run.finished_at}')
    add(f'Duration        : {run.duration_seconds:.1f}s')
    add(f'Application     : v{run.app_version}')
    add(f'PVF             : v{run.pvf_version}')
    add('')
    add('-' * W)
    add('READ-ONLY GUARANTEE')
    add('-' * W)
    add(f'Source database : {run.source_db}')
    add(f'Size            : {run.source_size_bytes:,} bytes')
    add(f'Copy method     : {run.copy_method}')
    add(f'SHA-256 before  : {run.source_hash_before}')
    add(f'SHA-256 after   : {run.source_hash_after}')
    verdict = ('VERIFIED — production database byte-identical after run'
               if run.read_only_verified else
               '*** NOT VERIFIED — DO NOT TRUST THIS RUN ***')
    add(f'Guarantee       : {verdict}')
    add('')
    add('-' * W)
    add('SUMMARY')
    add('-' * W)
    counts = run.counts
    for v in (Verdict.AGREED, Verdict.SINGLE_SOURCE, Verdict.DIVERGED,
              Verdict.VACUOUS, Verdict.NOT_IMPLEMENTED, Verdict.ERROR):
        add(f'  {v:<18} {counts.get(v, 0):>3}')
    add(f'  {"TOTAL":<18} {len(run.quantities):>3}')
    add('')
    add(f'  OVERALL VERDICT  : {run.overall}')
    add(f'  Blocking failures: {len(run.blocking_failures)}')
    add('')

    add('-' * W)
    add('QUANTITY RESULTS')
    add('-' * W)
    add(f'{"ID":<5} {"QUANTITY":<44} {"POLICY":<14} {"SEV":<6} {"VERDICT":<16} {"ms":>6}')
    add('-' * W)
    for q in run.quantities:
        add(f'{q.quantity_id:<5} {q.label[:43]:<44} {q.policy:<14} '
            f'{q.severity:<6} {q.verdict:<16} {q.duration_ms:>6}')
    add('')

    # Divergences — the findings the harness exists to produce.
    diverged = [q for q in run.quantities if q.verdict == Verdict.DIVERGED]
    if diverged:
        add('=' * W)
        add('DIVERGENCES')
        add('=' * W)
        for q in diverged:
            add('')
            add(f'[{q.quantity_id}] {q.label}   ({q.severity}, policy {q.policy})')
            add('-' * W)
            if q.note:
                add(f'  {q.note}')
            add('  Implementations:')
            for impl, val in sorted(q.implementations.items()):
                add(f'    {impl:<44} {val}')
            if q.divergences:
                add('  Attributed divergences:')
                for d in q.divergences[:25]:
                    add(f'    {d.scope:<24} {d.impl_a} = {d.value_a}  vs  '
                        f'{d.impl_b} = {d.value_b}   (delta {d.delta})')
                if len(q.divergences) > 25:
                    add(f'    ... {len(q.divergences) - 25} more (see result.json)')

    errored = [q for q in run.quantities if q.verdict == Verdict.ERROR]
    if errored:
        add('')
        add('=' * W)
        add('ERRORS')
        add('=' * W)
        for q in errored:
            add(f'[{q.quantity_id}] {q.label}')
            add(f'  {q.error}')

    vacuous = [q for q in run.quantities if q.verdict == Verdict.VACUOUS]
    if vacuous:
        add('')
        add('=' * W)
        add('VACUOUS — measured, but the population is empty')
        add('=' * W)
        add('These implementations agreed only because there was nothing to')
        add('disagree about. Per Principle 10 that is not evidence of')
        add('correctness. Each requires a regression dataset (Wave 0 D6)')
        add('before it can be reported as verified.')
        for q in vacuous:
            add(f'  [{q.quantity_id}] {q.label}')
            if q.note:
                add(f'         {q.note}')

    incomplete = [q for q in run.quantities
                  if q.verdict == Verdict.NOT_IMPLEMENTED]
    if incomplete:
        add('')
        add('=' * W)
        add('NOT IMPLEMENTED — declared but not measured')
        add('=' * W)
        add('Per Principle 10, these are reported explicitly and never counted')
        add('as agreement. The harness is NOT commissioned while any remain.')
        for q in incomplete:
            add(f'  [{q.quantity_id}] {q.label}')
            if q.note:
                add(f'         {q.note}')

    add('')
    add('=' * W)
    add('END OF REPORT')
    add('=' * W)
    return '\n'.join(L) + '\n'
