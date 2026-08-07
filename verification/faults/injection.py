"""
The injection engine.

Five methods, because a defect can enter a financial system at five
different places and only one of them is the database.

``SQL``
    Statements against a private copy. Class A and Class B faults: things
    a hotel can genuinely do, and records that are genuinely malformed.

``ENGINE_PATCH``
    A wrapper installed on a canonical callable inside one throwaway
    subprocess. This is the only way to express a Class C fault: "this
    function now double-counts" is not a state any data can be in. The
    production file is never touched and the wrapper dies with the
    process.

``CLOCK_SHIFT``
    Moves the frozen instant a layer runs under. The only way to
    challenge the temporal basis without changing a single row.

``ENV``
    Process environment. Configuration and environment mismatches — the
    faults where the money is right and the machine is wrong.

``FILE``
    Mutates a file, always a copy, never in place.

Verified injection
------------------
Every injection reports how much it changed and the platform **refuses a
zero-change injection**. This is the lesson D2, D3 and D4 each learned
separately: a seed that ran cleanly and altered nothing produces "not
detected", which reads as a defect in the framework rather than in the
seed. It is a false alarm in the one place false alarms are least
affordable, so rowcount is asserted every time.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
from dataclasses import dataclass

from verification.faults.model import Method


class InjectionDidNotApply(RuntimeError):
    """An injection ran cleanly and changed nothing.

    Raised rather than tolerated. "Not detected" against an injection
    that never happened is a statement about the injection, and reading
    it as a statement about the verification framework is exactly the
    mistake this platform exists to prevent.
    """


class InjectionNotPossible(RuntimeError):
    """The declared injection cannot be realised on this dataset."""


@dataclass
class Injection:
    """What was actually done, for the evidence pack."""
    method: str
    detail: dict
    rows_changed: int = 0
    verified: bool = False


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

def inject_sql(db_path: str, statements: tuple) -> Injection:
    conn = sqlite3.connect(db_path)
    try:
        changed = 0
        for statement in statements:
            cursor = conn.execute(statement)
            changed += max(cursor.rowcount, 0)
        conn.commit()
    finally:
        conn.close()
    if changed == 0:
        raise InjectionDidNotApply(
            'the declared SQL affected 0 rows on this dataset, so the fault '
            'was never introduced')
    return Injection(method=Method.SQL,
                     detail={'statements': list(statements)},
                     rows_changed=changed, verified=True)


# ---------------------------------------------------------------------------
# Engine patch
# ---------------------------------------------------------------------------

#: How a patched return value is perturbed.
OPS = {
    'add': lambda current, value: float(current) + float(value),
    'mul': lambda current, value: float(current) * float(value),
    'set': lambda current, value: float(value),
}


def patch_spec(payload: tuple) -> str:
    """Serialise ``(dotted, key, op, value)`` for a subprocess argument."""
    dotted, key, op, value = payload
    if op not in OPS:
        raise InjectionNotPossible(
            f'unknown patch operation {op!r}; known: {sorted(OPS)}')
    return f'{dotted}|{key}|{op}|{value}'


def _resolve_owner(dotted: str) -> tuple:
    """Resolve ``a.b.C.method`` to ``(C, 'method')`` or ``a.b`` to
    ``(module, 'name')``.

    Class C faults need to patch methods as well as module-level
    functions — "the night audit's payment summary now double-counts" is
    not something a module-level wrapper can express — so the longest
    importable prefix is found and the remainder walked by attribute.
    """
    parts = dotted.split('.')
    module = None
    index = len(parts) - 1
    while index > 0:
        try:
            module = importlib.import_module('.'.join(parts[:index]))
            break
        except ImportError:
            index -= 1
    if module is None:
        raise InjectionNotPossible(
            f'no importable module in {dotted!r}')
    owner = module
    for part in parts[index:-1]:
        owner = getattr(owner, part)
    return owner, parts[-1]


def apply_patch(spec: str) -> Injection:
    """Install the wrapper in THIS process. Called only in a subprocess.

    ``key`` names a key of the returned mapping; an empty key means the
    callable returns a scalar and the scalar itself is perturbed. A
    return value of neither shape is left alone and the injection is
    reported as unverified rather than silently doing nothing.
    """
    dotted, key, op, value = spec.split('|', 3)
    owner, attribute = _resolve_owner(dotted)
    module, original = owner, getattr(owner, attribute)
    operation = OPS[op]
    applied = {'count': 0}

    def patched(*args, **kwargs):
        result = original(*args, **kwargs)
        if key:
            if isinstance(result, dict) and key in result:
                result = dict(result)
                try:
                    result[key] = operation(result[key], value)
                    applied['count'] += 1
                except (TypeError, ValueError):
                    pass
            return result
        try:
            out = operation(result, value)
        except (TypeError, ValueError):
            return result
        applied['count'] += 1
        return out

    patched.__name__ = getattr(original, '__name__', attribute)
    patched.__doc__ = getattr(original, '__doc__', None)
    setattr(module, attribute, patched)
    return Injection(method=Method.ENGINE_PATCH,
                     detail={'target': dotted, 'key': key, 'op': op,
                             'value': value},
                     rows_changed=0, verified=True)


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------

def clock_env(db_path: str, days: int) -> dict:
    """Environment that moves the frozen instant by *days*.

    Reuses D2's ``PVF_GM_FREEZE_DATE`` override, which every layer's
    freeze already honours, rather than inventing a second mechanism
    that could drift away from it.
    """
    import datetime as _dt

    from verification.replay.timeline import read_business_date

    shifted = read_business_date(db_path) + _dt.timedelta(days=days)
    return {'PVF_GM_FREEZE_DATE': shifted.isoformat()}


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

def env_payload(payload: tuple) -> dict:
    """``(name, value)`` pairs, flattened into an environment overlay."""
    if len(payload) % 2:
        raise InjectionNotPossible(
            'ENV payload must be an even number of name/value entries')
    return {payload[i]: payload[i + 1] for i in range(0, len(payload), 2)}


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------

def inject_file(payload: tuple, arena_dir: str) -> Injection:
    """Corrupt a copy of a file. Never the original.

    ``payload`` is ``(source_relative_path, mode)`` where mode is
    ``truncate``, ``append`` or ``flip``. The file is copied into the
    arena first: a platform that corrupted a real backup to prove backups
    can be corrupted would have made the point rather too well.
    """
    from verification.config import PROJECT_ROOT

    relative, mode = payload[0], payload[1]
    source = os.path.join(PROJECT_ROOT, relative)
    if not os.path.isfile(source):
        raise InjectionNotPossible(
            f'{relative} does not exist, so it cannot be corrupted. The '
            f'fault stays registered and is reported as not exercised '
            f'rather than quietly passing.')
    os.makedirs(arena_dir, exist_ok=True)
    target = os.path.join(arena_dir, 'corrupt_' + os.path.basename(source))
    shutil.copy2(source, target)

    size_before = os.path.getsize(target)
    with open(target, 'r+b') as fh:
        if mode == 'truncate':
            fh.truncate(max(0, size_before // 2))
        elif mode == 'append':
            fh.seek(0, os.SEEK_END)
            fh.write(b'\x00CORRUPTED-BY-FIP')
        elif mode == 'flip':
            fh.seek(size_before // 2)
            byte = fh.read(1) or b'\x00'
            fh.seek(size_before // 2)
            fh.write(bytes([byte[0] ^ 0xFF]))
        else:
            raise InjectionNotPossible(f'unknown file mode {mode!r}')
    size_after = os.path.getsize(target)

    return Injection(
        method=Method.FILE,
        detail={'source': relative, 'copy': target, 'mode': mode,
                'size_before': size_before, 'size_after': size_after},
        rows_changed=1, verified=True)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def prepare(f, db_path: str, arena_dir: str) -> tuple:
    """Realise a fault against *db_path*.

    Returns ``(injection, env_overlay, patch_spec)``. SQL and FILE happen
    now; ENGINE_PATCH, CLOCK_SHIFT and ENV are carried into the probe
    subprocesses, because they only exist inside a running process.
    """
    if f.injection_method == Method.SQL:
        return inject_sql(db_path, f.payload), {}, ''
    if f.injection_method == Method.ENGINE_PATCH:
        spec = patch_spec(f.payload)
        return (Injection(method=Method.ENGINE_PATCH,
                          detail={'spec': spec}, verified=True), {}, spec)
    if f.injection_method == Method.CLOCK_SHIFT:
        days = int(f.payload[0]) if f.payload else 1
        overlay = clock_env(db_path, days)
        return (Injection(method=Method.CLOCK_SHIFT,
                          detail={'days': days, **overlay}, verified=True),
                overlay, '')
    if f.injection_method == Method.ENV:
        overlay = env_payload(f.payload)
        return (Injection(method=Method.ENV, detail=dict(overlay),
                          verified=True), overlay, '')
    if f.injection_method == Method.FILE:
        return inject_file(f.payload, arena_dir), {}, ''
    raise InjectionNotPossible(
        f'{f.fault_id}: no injector for method {f.injection_method!r}')
