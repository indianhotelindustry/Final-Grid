"""
Comparison of a capture against a stored golden master set.

Every difference is classified, attributed to a surface, and carries the
severity of that surface's category. The comparison is symmetric: a
figure that disappeared is as much a finding as one that changed, and a
surface that vanished is as much a finding as one that appeared.

There is no tolerance band. A golden master is a statement that "this
release renders exactly what the last one rendered"; if a figure moved
by a paisa, either the change was intended — in which case it is
declared and accepted — or it is a regression. Tolerances belong in the
parity harness (D1), where two implementations of the same quantity are
legitimately allowed to round differently. Applying them here would let
a systematic one-paisa drift through unnoticed on every surface at once.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from verification.config import SEVERITY_RANK, Severity


class Kind:
    SURFACE_ADDED = 'SURFACE_ADDED'
    SURFACE_REMOVED = 'SURFACE_REMOVED'
    STATUS_CHANGED = 'STATUS_CHANGED'
    LOCATION_CHANGED = 'LOCATION_CHANGED'
    ANON_STATUS_CHANGED = 'ANON_STATUS_CHANGED'
    CONTENT_TYPE_CHANGED = 'CONTENT_TYPE_CHANGED'
    TEMPLATES_CHANGED = 'TEMPLATES_CHANGED'
    FIGURE_CHANGED = 'FIGURE_CHANGED'
    FIGURE_ADDED = 'FIGURE_ADDED'
    FIGURE_REMOVED = 'FIGURE_REMOVED'
    BODY_CHANGED = 'BODY_CHANGED'
    NORMALISATION_CHANGED = 'NORMALISATION_CHANGED'
    ERROR_CHANGED = 'ERROR_CHANGED'
    TRUNCATION_CHANGED = 'TRUNCATION_CHANGED'


#: An authorisation change is BLOCK regardless of the surface's own
#: category: a page that stops redirecting anonymous callers has become
#: public, and that is never an operational detail.
ALWAYS_BLOCK = {Kind.ANON_STATUS_CHANGED}

#: A body-hash move with no figure move is presentation-only. Recorded
#: at WARN on every surface: it is real (someone changed a template) but
#: it is not, on its own, a misstatement of money.
ALWAYS_WARN = {Kind.BODY_CHANGED, Kind.TRUNCATION_CHANGED,
               Kind.NORMALISATION_CHANGED}


@dataclass
class Difference:
    surface_id: str
    url: str
    category: str
    kind: str
    severity: str
    key: str = ''
    master: str = ''
    current: str = ''
    delta: str = ''

    def line(self) -> str:
        head = f'[{self.severity:<5}] {self.kind:<22} {self.surface_id}'
        if self.key:
            head += f'  {self.key}'
        return head


@dataclass
class ComparisonResult:
    tag: str
    master_captured_at: str = ''
    master_app_version: str = ''
    current_app_version: str = ''
    master_frozen_at: str = ''
    current_frozen_at: str = ''
    differences: list = field(default_factory=list)
    surfaces_compared: int = 0
    surfaces_clean: int = 0

    @property
    def blocking(self) -> list:
        return [d for d in self.differences if d.severity == Severity.BLOCK]

    @property
    def by_kind(self) -> dict:
        out: dict = {}
        for d in self.differences:
            out[d.kind] = out.get(d.kind, 0) + 1
        return out

    @property
    def verdict(self) -> str:
        if self.blocking:
            return 'FAIL'
        if self.differences:
            return 'WARN'
        return 'PASS'


def _severity_for(kind: str, surface_severity: str) -> str:
    if kind in ALWAYS_BLOCK:
        return Severity.BLOCK
    if kind in ALWAYS_WARN:
        return Severity.WARN
    return surface_severity


def _delta(master: str, current: str) -> str:
    """Numeric delta when both sides are numbers, else empty."""
    try:
        return f'{float(current) - float(master):+.6f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return ''


def compare(current_surfaces: list, masters: dict, index: dict,
            tag: str) -> ComparisonResult:
    """Diff a capture against a stored master set."""
    result = ComparisonResult(
        tag=tag,
        master_captured_at=index.get('started_at', ''),
        master_app_version=index.get('app_version', ''),
        master_frozen_at=index.get('frozen_at', ''),
    )

    current = {s.surface_id: s for s in current_surfaces}
    result.surfaces_compared = len(current)

    for sid in sorted(set(current) | set(masters)):
        cur = current.get(sid)
        mas = masters.get(sid)

        if mas is None:
            result.differences.append(Difference(
                surface_id=sid, url=cur.url, category=cur.category,
                kind=Kind.SURFACE_ADDED,
                severity=_severity_for(Kind.SURFACE_ADDED, Severity.WARN),
                current=f'{cur.status}'))
            continue
        if cur is None:
            result.differences.append(Difference(
                surface_id=sid, url=mas.get('url', ''),
                category=mas.get('category', ''),
                kind=Kind.SURFACE_REMOVED,
                severity=_severity_for(Kind.SURFACE_REMOVED, Severity.WARN),
                master=str(mas.get('status', ''))))
            continue

        sev = cur.severity
        diffs_before = len(result.differences)

        def add(kind, key='', m='', c=''):
            result.differences.append(Difference(
                surface_id=sid, url=cur.url, category=cur.category,
                kind=kind, severity=_severity_for(kind, sev),
                key=key, master=str(m), current=str(c),
                delta=_delta(m, c) if kind == Kind.FIGURE_CHANGED else ''))

        if cur.status != mas.get('status'):
            add(Kind.STATUS_CHANGED, '', mas.get('status'), cur.status)
        if (cur.location or '') != (mas.get('location') or ''):
            add(Kind.LOCATION_CHANGED, '', mas.get('location'), cur.location)
        if cur.anon_status != mas.get('anon_status'):
            add(Kind.ANON_STATUS_CHANGED, '',
                mas.get('anon_status'), cur.anon_status)
        if cur.content_type != mas.get('content_type'):
            add(Kind.CONTENT_TYPE_CHANGED, '',
                mas.get('content_type'), cur.content_type)
        if list(cur.templates) != list(mas.get('templates') or []):
            add(Kind.TEMPLATES_CHANGED, '',
                ','.join(mas.get('templates') or []), ','.join(cur.templates))
        if (cur.error or '') != (mas.get('error') or ''):
            add(Kind.ERROR_CHANGED, '', mas.get('error'), cur.error)

        mfig = mas.get('figures') or {}
        for key in sorted(set(mfig) | set(cur.figures)):
            mv, cv = mfig.get(key), cur.figures.get(key)
            if mv is None:
                add(Kind.FIGURE_ADDED, key, '', cv)
            elif cv is None:
                add(Kind.FIGURE_REMOVED, key, mv, '')
            elif mv != cv:
                add(Kind.FIGURE_CHANGED, key, mv, cv)

        if cur.body_sha256 != mas.get('body_sha256'):
            add(Kind.BODY_CHANGED, '', mas.get('body_sha256', '')[:16],
                cur.body_sha256[:16])
        if cur.normalisation_hits != (mas.get('normalisation_hits') or {}):
            add(Kind.NORMALISATION_CHANGED, '',
                mas.get('normalisation_hits'), cur.normalisation_hits)
        if sorted(cur.truncations) != sorted(mas.get('truncations') or []):
            add(Kind.TRUNCATION_CHANGED, '',
                len(mas.get('truncations') or []), len(cur.truncations))

        if len(result.differences) == diffs_before:
            result.surfaces_clean += 1

    result.differences.sort(
        key=lambda d: (SEVERITY_RANK.get(d.severity, 9), d.surface_id,
                       d.kind, d.key))
    return result
