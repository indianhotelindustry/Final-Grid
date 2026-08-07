"""
Authenticated test client for surface capture.

Authentication by session injection rather than by posting credentials:

  * the harness does not need, store or guess a production password;
  * logging in writes an AuditLog row and mutates the user's
    ``last_login``, which would put state change inside a measurement;
  * a failed guess would lock the account after five attempts, and the
    lockout would be written to the copy — harmless, but the harness
    should not be in the business of locking accounts at all.

The injected session is exactly what Flask-Login itself writes, so every
downstream ``current_user`` check behaves normally. Session protection
is left at its default; under ``basic`` a missing identifier only marks
the session non-fresh, which no financial surface tests.

What this does NOT verify
-------------------------
The login flow itself. A golden master over rendered content cannot
assert that authentication works, so the capture additionally records
what an ANONYMOUS client receives for the same URL. That is a real
control: if a route loses its ``@login_required``, the anonymous status
moves from 302 to 200 and the comparison fails.
"""
from __future__ import annotations

from dataclasses import dataclass


class NoAdminUser(RuntimeError):
    """No active Admin exists in the dataset under verification."""


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    role: str


def resolve_principal(preferred_role: str = 'Admin') -> Principal:
    """Pick the capture identity deterministically.

    Lowest id among active users of the preferred role. Deterministic
    because a golden master must not depend on which user happens to be
    listed first.
    """
    from app.models import User

    user = (User.query
            .filter_by(role=preferred_role, is_active=True)
            .order_by(User.id).first())
    if user is None:
        raise NoAdminUser(
            f'No active user with role {preferred_role!r}. Golden master '
            f'capture needs an identity that can reach the financial '
            f'surfaces; without one the masters would record permission '
            f'redirects instead of reports.')
    return Principal(user_id=user.id, username=user.username, role=user.role)


def authenticated_client(app, principal: Principal):
    """A test client carrying *principal*'s session."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(principal.user_id)
        sess['_fresh'] = True
    return client


def anonymous_client(app):
    """A test client with no session at all."""
    return app.test_client()
