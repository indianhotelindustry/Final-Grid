"""
Rendering a surface and reading back what it computed.

This is the piece D1 was missing. Quantities Q16–Q18 — daily report
totals, MIS aggregates, dashboard tiles — are produced inside Flask route
handlers, so the parity harness could not reach them and reported
NOT_IMPLEMENTED. With an authenticated client and the
``template_rendered`` signal it can now compare what a *report shows*
against what the *engines say*, which is the comparison the reported
symptom ("report totals not matching dashboards") actually needs.

The context is read rather than the HTML parsed. A number that reached
the template is the number the route computed; a number scraped out of
rendered HTML has been through Jinja formatting, thousands separators
and rounding filters, and comparing those would confuse a presentation
bug with a financial one.
"""
from __future__ import annotations


class SurfaceRenderFailed(RuntimeError):
    """A surface a parity quantity depends on did not render.

    Raised rather than returning empty figures: a quantity that quietly
    compared nothing would report agreement, which is precisely the
    silence Principle 11 forbids.
    """


def render_context(app, url: str, principal=None) -> tuple[int, dict]:
    """GET *url* as an authenticated user; return ``(status, context)``.

    The merged context of every template rendered during the request is
    returned, child last, so an inherited layout cannot mask a value the
    page itself set.
    """
    from flask import template_rendered
    from verification.golden import client as gmclient

    if principal is None:
        principal = gmclient.resolve_principal()

    captured: list = []

    def _record(sender, template, context, **extra):
        captured.append(dict(context))

    template_rendered.connect(_record, app)
    try:
        c = gmclient.authenticated_client(app, principal)
        resp = c.get(url)
    finally:
        template_rendered.disconnect(_record, app)

    merged: dict = {}
    for ctx in captured:
        merged.update(ctx)
    return resp.status_code, merged


def require_context(app, url: str, principal=None) -> dict:
    """As ``render_context``, but a non-200 is an error, not an empty dict."""
    status, context = render_context(app, url, principal)
    if status != 200:
        raise SurfaceRenderFailed(
            f'{url} returned HTTP {status}. The figures this quantity '
            f'compares are produced by that surface, so there is nothing to '
            f'compare — reported as an error rather than as agreement.')
    return context


def pick(context: dict, path: str, default=None):
    """Read a dotted path out of a template context."""
    node = context
    for part in path.split('.'):
        if isinstance(node, dict):
            if part not in node:
                return default
            node = node[part]
        else:
            node = getattr(node, part, None)
            if node is None:
                return default
    return node
