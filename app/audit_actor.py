"""Audit actor resolution — ADR011-SA (FOUNDER_DECISIONS.md, Round 5).

Every ``audit_logs`` row says who acted, as one of two kinds:

* ``HUMAN`` — an authenticated user. ``staff_user_id`` references
  ``users``; ``actor_role`` and ``actor_shift_id`` snapshot that user's
  role and open shift at the time (filled by the ``AuditLog`` insert
  listener in ``app.models``).
* ``SYSTEM`` — no human. ``staff_user_id`` is empty and ``actor_mechanism``
  names what acted (``scheduler:night_audit_job``, ``webhook``, ...).
  A system action never borrows a human identity and never uses the old
  ``users.id = 0`` convention.

Resolution order: an explicit user id, else the logged-in operator, else
the system mechanism declared by the caller (``system_action``), else an
unauthenticated web request. When none applies, resolution raises rather
than guessing — an audit row whose actor is unknown is not written.
"""
from __future__ import annotations

import contextvars
from collections import namedtuple
from contextlib import contextmanager

HUMAN = 'HUMAN'
SYSTEM = 'SYSTEM'

AuditActor = namedtuple('AuditActor', 'staff_user_id actor_kind actor_mechanism')

_system_mechanism = contextvars.ContextVar('finalgrid_system_mechanism', default=None)


class AuditActorError(RuntimeError):
    """No human actor and no declared system mechanism for an audit row."""


@contextmanager
def system_action(mechanism):
    """Declare that code in this block runs as a system actor named *mechanism*.

    Used only where no human initiated the work (scheduler jobs, inbound
    integrations). A logged-in operator or an explicit user id still wins.
    """
    if not mechanism:
        raise ValueError('a system action needs a mechanism name')
    token = _system_mechanism.set(mechanism)
    try:
        yield
    finally:
        _system_mechanism.reset(token)


def _request_state():
    """(has request context, authenticated user id or None)."""
    try:
        from flask import has_request_context
        if not has_request_context():
            return False, None
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return True, current_user.id
        return True, None
    except Exception:
        return False, None


def resolve(user_id=None, mechanism=None):
    """Return the :class:`AuditActor` for an audit row.

    ``user_id`` 0 is treated as "no user": it is the retired system
    convention, never a real account.
    """
    if user_id:
        in_request, _ = _request_state()
        return AuditActor(int(user_id), HUMAN, mechanism or ('web' if in_request else 'service'))
    in_request, uid = _request_state()
    if uid is not None:
        return AuditActor(int(uid), HUMAN, mechanism or 'web')
    mech = mechanism or _system_mechanism.get()
    if mech:
        return AuditActor(None, SYSTEM, mech)
    if in_request:
        return AuditActor(None, SYSTEM, 'web:unauthenticated')
    raise AuditActorError(
        'audit actor unknown: no user, no logged-in operator and no declared '
        'system mechanism (wrap unattended work in audit_actor.system_action)')
