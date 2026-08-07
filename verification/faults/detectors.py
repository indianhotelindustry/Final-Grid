"""
The verification layers, presented as uniform probes.

Each of D1 to D4 already has an internal JSON entry point that its own
commissioning suite uses. This module wraps all four in one shape so the
platform can ask the same question of each — *what did you see?* — and
compare the answers against a clean baseline.

Signal, not verdict
-------------------
A probe returns a **signal**: a flat mapping of key to digest. Detection
is then "this key moved", which is deliberately weaker than "the layer
reported FAIL". Several verification layers legitimately report FAIL on
this production dataset before any fault is injected; asking whether the
verdict changed would make every one of those layers permanently blind to
new faults. Asking whether the *signal* moved does not.

Attribution is the second question and the harder one. A layer that moved
somewhere unrelated has noticed a disturbance, not identified a defect,
and the classifier keeps the two apart.

Parallelism
-----------
The four probes are independent processes and run concurrently. Each gets
its own ``PVF_WORK_SUFFIX`` so the fixed working-copy names D1-D4 use
cannot collide — without it, two probes recreate each other's working
file mid-read and both produce results nobody can trust.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

from verification.config import PROJECT_ROOT
from verification.faults.model import Layer

#: layer -> (subcommand, stdout marker)
PROBES = {
    Layer.D1_PARITY: ('_measure', '---PVF-JSON---'),
    Layer.D2_GOLDEN: ('_gm_capture_json', '---GM-JSON---'),
    Layer.D3_REPLAY: ('_replay_json', '---REPLAY-JSON---'),
    Layer.D4_INVARIANTS: ('_inv_json', '---INV-JSON---'),
}

#: Environment variable the internal probe entry points honour to install
#: an engine patch. One hook, shared by all four, so a Class C fault does
#: not need four different plumbings.
PATCH_ENV = 'PVF_FIP_PATCH'


@dataclass
class Probe:
    layer: str
    ran: bool = False
    signal: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    duration_ms: int = 0
    error: str = ''


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def _signal_d1(raw: dict) -> dict:
    """Quantity id -> verdict, divergence count and every implementation
    value. The values matter: a fault that moves two implementations
    equally leaves the verdict alone, and only the values reveal it."""
    return {qid: json.dumps(
        {'verdict': q.get('verdict'), 'divergences': q.get('divergences'),
         'implementations': q.get('implementations')}, sort_keys=True)
        for qid, q in raw.items()}


def _signal_d2(raw: dict) -> dict:
    """Surface id -> status, anonymous status, body hash, figures."""
    return {sid: json.dumps(
        {'status': s.get('status'), 'anon_status': s.get('anon_status'),
         'body': s.get('body_sha256'), 'figures': s.get('figures'),
         'templates': s.get('templates')}, sort_keys=True)
        for sid, s in raw.items()}


def _signal_d3(raw: dict) -> dict:
    """Two families of key, because they answer different questions.

    ``date:<d>``  the whole account of that day moved.
    ``rc:<RULE>`` a named reconciliation changed status — which is what
                  makes a D3 detection attributable rather than merely
                  noisy.
    """
    out: dict = {}
    per_rule: dict = {}
    for date, entry in sorted((raw.get('dates') or {}).items()):
        out[f'date:{date}'] = json.dumps(
            {'ledger': entry.get('ledger'), 'engine': entry.get('engine'),
             'recorded': entry.get('recorded'),
             'is_closed': entry.get('is_closed'),
             'snapshot_matches': entry.get('snapshot_matches'),
             'history_drift': entry.get('history_drift'),
             'asat_drift': entry.get('asat_drift')}, sort_keys=True)
        for rule_id, status in (entry.get('reconciliations') or {}).items():
            per_rule.setdefault(rule_id, []).append(f'{date}={status}')
    for rule_id, statuses in per_rule.items():
        out[f'rc:{rule_id}'] = json.dumps(sorted(statuses))
    out['ledger_stable'] = json.dumps(raw.get('ledger_stable'))
    return out


def _signal_d4(raw: dict) -> dict:
    """Invariant id -> status, population, violation count, objects."""
    return {iid: json.dumps(
        {'status': i.get('status'), 'population': i.get('population'),
         'violations': i.get('violations'),
         'objects': i.get('affected_objects')}, sort_keys=True)
        for iid, i in (raw.get('invariants') or {}).items()}


SIGNALS = {
    Layer.D1_PARITY: _signal_d1,
    Layer.D2_GOLDEN: _signal_d2,
    Layer.D3_REPLAY: _signal_d3,
    Layer.D4_INVARIANTS: _signal_d4,
}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def run_probe(layer: str, db_path: str, env_overlay: dict | None = None,
              patch: str = '', slot: str = '') -> Probe:
    """Run one layer against *db_path* in its own process."""
    subcommand, marker = PROBES[layer]
    probe = Probe(layer=layer)

    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    # A unique working-copy suffix per probe. Without it, two concurrent
    # probes would recreate each other's fixed-name working file.
    env['PVF_WORK_SUFFIX'] = f'_{layer.lower()}{slot}'
    if patch:
        env[PATCH_ENV] = patch
    env.update(env_overlay or {})

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'verification', subcommand,
             '--db', os.path.abspath(db_path)],
            cwd=PROJECT_ROOT, capture_output=True, text=True, env=env,
            timeout=600)
    except subprocess.TimeoutExpired:
        probe.duration_ms = int((time.perf_counter() - t0) * 1000)
        probe.error = 'probe timed out after 600s'
        return probe
    probe.duration_ms = int((time.perf_counter() - t0) * 1000)

    if marker not in proc.stdout:
        probe.error = (f'probe produced no result.\n'
                       f'stdout tail: {proc.stdout[-800:]}\n'
                       f'stderr tail: {proc.stderr[-800:]}')
        return probe
    try:
        probe.raw = json.loads(proc.stdout.split(marker, 1)[1].strip())
    except Exception as exc:                             # noqa: BLE001
        probe.error = f'probe result unparseable: {type(exc).__name__}: {exc}'
        return probe

    probe.signal = SIGNALS[layer](probe.raw)
    probe.ran = True
    return probe


def sweep(db_path: str, layers: tuple, env_overlay: dict | None = None,
          patch: str = '', slot: str = '',
          parallel: bool = True) -> dict:
    """Run several layers against the same database.

    Parallel by default. Each probe is a separate process with a private
    working-copy suffix, so concurrency is safe by construction rather
    than by hoping the runs do not overlap.
    """
    if not layers:
        return {}
    if not parallel or len(layers) == 1:
        return {layer: run_probe(layer, db_path, env_overlay, patch, slot)
                for layer in layers}

    out: dict = {}
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(layers)) as pool:
        futures = {pool.submit(run_probe, layer, db_path, env_overlay,
                               patch, slot): layer for layer in layers}
        for future in concurrent.futures.as_completed(futures):
            layer = futures[future]
            try:
                out[layer] = future.result()
            except Exception as exc:                     # noqa: BLE001
                probe = Probe(layer=layer)
                probe.error = f'{type(exc).__name__}: {exc}'
                out[layer] = probe
    return {layer: out[layer] for layer in layers if layer in out}


def moved_keys(baseline: dict, current: dict) -> list:
    """Signal keys that differ, in a stable order."""
    return sorted(key for key in set(baseline) | set(current)
                  if baseline.get(key) != current.get(key))
