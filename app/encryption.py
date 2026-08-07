"""
Field-level Fernet encryption for PII columns.

Usage in models.py:
    from app.encryption import EncryptedString
    id_proof_number = db.Column(EncryptedString(), nullable=True)

The encryption key is read from the PII_ENCRYPTION_KEY environment variable.
If that variable is not set, a key is deterministically derived from the
application's SECRET_KEY using HKDF so that the system works out of the box.

IMPORTANT: In production, always set PII_ENCRYPTION_KEY to a dedicated
Fernet-compatible key (base64-encoded 32 bytes).  Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import sqlalchemy as sa

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

_fernet_instance = None


def _derive_key_from_secret(secret_key: str) -> bytes:
    """Derive a Fernet-compatible key from an arbitrary secret string via HKDF."""
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=b"pms-pii-encryption-salt",
        info=b"pms-pii-field-encryption",
    )
    raw = hkdf.derive(secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _get_fernet() -> Fernet:
    """Return a cached Fernet instance, creating it on first call."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    explicit_key = os.environ.get("PII_ENCRYPTION_KEY")
    if explicit_key:
        key = explicit_key.encode("utf-8") if isinstance(explicit_key, str) else explicit_key
    else:
        secret = os.environ.get("SECRET_KEY", "dev-secret-key-insecure")
        key = _derive_key_from_secret(secret)
        logger.warning(
            "PII_ENCRYPTION_KEY not set -- deriving encryption key from SECRET_KEY. "
            "Set PII_ENCRYPTION_KEY in production for best security."
        )

    _fernet_instance = Fernet(key)
    return _fernet_instance


def reset_fernet():
    """Force re-initialisation (useful after tests change env vars)."""
    global _fernet_instance
    _fernet_instance = None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return the Fernet token as a UTF-8 string."""
    if plaintext is None:
        return None
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet token back to plaintext.

    If decryption fails (e.g. the value is legacy plaintext that was never
    encrypted), the original value is returned unchanged.  This allows a
    gradual migration: old rows are readable immediately and will be
    encrypted the next time they are written back.
    """
    if ciphertext is None:
        return None
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Value is probably legacy plaintext -- return as-is.
        return ciphertext


# ---------------------------------------------------------------------------
# Custom SQLAlchemy column type
# ---------------------------------------------------------------------------

class EncryptedString(sa.types.TypeDecorator):
    """A column type that transparently encrypts on write and decrypts on read.

    Stored as TEXT in the database (Fernet tokens are longer than the
    original plaintext).
    """
    impl = sa.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Called when writing to the DB -- encrypt the plaintext."""
        if value is None:
            return None
        return encrypt_value(str(value))

    def process_result_value(self, value, dialect):
        """Called when reading from the DB -- decrypt (or pass-through)."""
        if value is None:
            return None
        return decrypt_value(value)


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------

def encrypt_existing_rows(db_session, model_class, column_name: str, batch_size: int = 500):
    """Encrypt all plaintext values in *column_name* of *model_class*.

    This is a one-shot migration helper.  It reads every row, attempts to
    decrypt the current value; if decryption fails (meaning the value is
    still plaintext) it encrypts and writes it back.

    Usage (inside a Flask shell or migration script)::

        from app.encryption import encrypt_existing_rows
        from app.models import db, Guest
        encrypt_existing_rows(db.session, Guest, 'id_proof_number')
        db.session.commit()
    """
    column = getattr(model_class, column_name)
    # Bypass the TypeDecorator by using the underlying table column directly
    table = model_class.__table__
    raw_col = table.c[column_name]

    rows = db_session.query(model_class).filter(raw_col.isnot(None)).yield_per(batch_size)
    count = 0
    for row in rows:
        raw_value = db_session.execute(
            sa.select(raw_col).where(table.c.id == row.id)
        ).scalar()
        if raw_value is None:
            continue
        # Try to decrypt -- if it fails, the value is still plaintext
        f = _get_fernet()
        try:
            f.decrypt(raw_value.encode("utf-8"))
            # Already encrypted, skip
            continue
        except (InvalidToken, Exception):
            pass
        # Encrypt and write back (raw UPDATE to avoid TypeDecorator double-encrypting)
        encrypted = encrypt_value(raw_value)
        db_session.execute(
            table.update().where(table.c.id == row.id).values(**{column_name: encrypted})
        )
        count += 1
    logger.info("encrypt_existing_rows: encrypted %d rows in %s.%s", count, model_class.__tablename__, column_name)
    return count
