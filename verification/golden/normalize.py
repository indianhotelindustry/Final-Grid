"""
Normalisation and figure extraction.

Two jobs.

**Normalisation** removes the parts of a response that legitimately
differ between two identical runs — per-request security tokens. Every
rule here is narrow, named, and had to be justified by an observed
difference in a repeat capture; a broad rule (say, blanking anything
that looks like a number) would hide exactly the change the framework
exists to catch. ``RULES`` is reported in the evidence pack so a reader
can see precisely what was masked.

**Figure extraction** pulls the numeric content out of a response. For
an HTML page the figures are taken from the *template context* — the
values the route computed, before Jinja formatted them — because that is
the financially meaningful layer and it is immune to cosmetic template
edits. For a JSON response the figures are the numeric leaves of the
payload itself, which is what a consumer would read.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Normalisation rules
# ---------------------------------------------------------------------------

#: (name, compiled pattern, replacement, why it is safe to mask)
RULES: list[tuple[str, re.Pattern, str, str]] = [
    ('csp_nonce_attr',
     re.compile(r'nonce="[A-Za-z0-9+/=_-]{8,}"'),
     'nonce="<CSP_NONCE>"',
     'Content-Security-Policy nonce, regenerated per request by '
     'app.__init__._generate_csp_nonce. Carries no application state.'),

    ('csrf_meta',
     re.compile(r'(<meta[^>]*name="csrf-token"[^>]*content=")[^"]+(")'),
     r'\1<CSRF_TOKEN>\2',
     'Flask-WTF CSRF token in the page meta tag. Signed and timestamped, '
     'so it differs every render.'),

    ('csrf_input',
     re.compile(r'(name="csrf_token"[^>]*value=")[^"]+(")'),
     r'\1<CSRF_TOKEN>\2',
     'Flask-WTF CSRF token in a hidden form input.'),

]

# Two further rules were drafted — a reversed-attribute CSRF input and a
# CSRF token embedded in inline JavaScript — and then deleted. Neither
# matched anything in 149 surfaces, and a repeat capture was already
# byte-identical without them. An unproven masking rule is a liability:
# it can only ever hide a real difference, never reveal one. If a future
# template introduces either pattern the repeat-capture check will fail
# loudly, which is the correct moment to add the rule.


def normalise(body: bytes) -> tuple[bytes, dict[str, int]]:
    """Apply every rule. Returns ``(normalised, {rule_name: hits})``.

    Hit counts are stored in the master. If a rule stops matching — a
    template dropped its CSRF field, say — the count changes and the
    comparison reports it. A normalisation rule that silently stops
    applying would otherwise be an invisible loss of protection.
    """
    text = body.decode('utf-8', errors='replace')
    hits: dict[str, int] = {}
    for name, pattern, replacement, _why in RULES:
        text, n = pattern.subn(replacement, text)
        if n:
            hits[name] = n
    # Line endings only; whitespace is NOT collapsed, because a layout
    # change is a real change and the body hash should notice it.
    text = text.replace('\r\n', '\n')
    return text.encode('utf-8'), hits


def body_digest(body: bytes) -> tuple[str, dict[str, int], int]:
    norm, hits = normalise(body)
    return hashlib.sha256(norm).hexdigest(), hits, len(norm)


# ---------------------------------------------------------------------------
# Figure extraction
# ---------------------------------------------------------------------------

#: Context keys that are framework plumbing, not application output.
#: Each is excluded for a stated reason; the list is short on purpose.
CONTEXT_SKIP = {
    'csrf_token': 'per-request security token',
    'csrf_meta_tag': 'per-request security token',
    'csp_nonce': 'per-request security token',
    'current_user': 'Flask-Login proxy; identity is recorded separately',
    'request': 'Werkzeug request object',
    'session': 'Flask session',
    'g': 'Flask application globals',
    'config': 'Flask config',
    'url_for': 'Jinja global',
    'get_flashed_messages': 'Jinja global',
    'timedelta': 'imported helper passed into the template',
    'datetime': 'imported helper passed into the template',
    'date': 'imported helper passed into the template',
}

#: Hard ceilings so one enormous page (a 350 KB room grid) cannot blow
#: up an evidence pack. Every truncation is RECORDED in the master, per
#: the standing rule that a cap must never look like completeness.
MAX_DEPTH = 5
MAX_LIST_ITEMS = 60
MAX_FIGURES = 4000


class _Budget:
    def __init__(self):
        self.figures = 0
        self.truncations: list[str] = []

    def spend(self) -> bool:
        self.figures += 1
        return self.figures <= MAX_FIGURES


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def _fmt_number(v: Any) -> str:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, float):
        # Round to 6 dp before storing. Float noise below that is
        # representation, not a financial difference, and would make
        # every comparison unstable. Money is compared to 2 dp anyway.
        return f'{v:.6f}'.rstrip('0').rstrip('.') or '0'
    return str(v)


def _walk(value: Any, path: str, out: dict, budget: _Budget, depth: int) -> None:
    if depth > MAX_DEPTH:
        budget.truncations.append(f'{path}: depth limit {MAX_DEPTH}')
        return

    if _is_number(value):
        if budget.spend():
            out[path] = _fmt_number(value)
        else:
            budget.truncations.append(f'{path}: figure budget exhausted')
        return

    if isinstance(value, bool):
        if budget.spend():
            out[path] = str(value)
        return

    if isinstance(value, (datetime, date)):
        if budget.spend():
            out[path] = value.isoformat()
        return

    if isinstance(value, str):
        return                                  # narrative text, not a figure

    if isinstance(value, dict):
        out[f'{path}[len]'] = str(len(value))
        for key in sorted(value.keys(), key=lambda k: str(k)):
            _walk(value[key], f'{path}.{key}', out, budget, depth + 1)
        return

    if isinstance(value, (list, tuple, set)):
        items = list(value)
        out[f'{path}[len]'] = str(len(items))
        numeric = [v for v in items if _is_number(v)]
        if numeric and len(numeric) == len(items):
            out[f'{path}[sum]'] = _fmt_number(sum(numeric))
        for i, item in enumerate(items[:MAX_LIST_ITEMS]):
            _walk(item, f'{path}[{i}]', out, budget, depth + 1)
        if len(items) > MAX_LIST_ITEMS:
            budget.truncations.append(
                f'{path}: {len(items)} items, first {MAX_LIST_ITEMS} captured')
        return

    # SQLAlchemy models and other objects: record the shape only.
    # Their figures reach the surface through the template as attribute
    # access, which no generic walker can enumerate honestly. Recording
    # the class name at least makes a type change visible.
    cls = type(value).__name__
    if cls not in ('function', 'method', 'module', 'type', 'NoneType'):
        out[f'{path}[type]'] = cls


def figures_from_context(context: dict) -> tuple[dict[str, str], list[str]]:
    """Numeric figures a route handed to its template, by dotted path."""
    out: dict[str, str] = {}
    budget = _Budget()
    for key in sorted(context.keys()):
        if key in CONTEXT_SKIP or key.startswith('_'):
            continue
        _walk(context[key], key, out, budget, 0)
    return out, budget.truncations


def figures_from_json(body: bytes) -> tuple[dict[str, str], list[str]]:
    """Numeric leaves of a JSON response body."""
    try:
        payload = json.loads(body.decode('utf-8', errors='replace'))
    except Exception as exc:
        return {'__json_parse_error__': type(exc).__name__}, []
    out: dict[str, str] = {}
    budget = _Budget()
    _walk(payload, '$', out, budget, 0)
    return out, budget.truncations
