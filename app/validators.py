"""
Centralized validation helpers for PMS form inputs.
====================================================
All validators return an error message string on failure, or None on success.
Collect errors with validate_fields() for batch validation.
"""

import re
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Phone
# ---------------------------------------------------------------------------
_PHONE_DIGITS_RE = re.compile(r'^\d{10}$')           # Indian mobile (10 digits)
_PHONE_INTL_RE = re.compile(r'^\+\d{7,15}$')         # International with +


def clean_phone(raw: str | None) -> str:
    """Strip spaces, dashes, parentheses from a phone number."""
    return re.sub(r'[\s\-\(\)]+', '', (raw or '').strip())


def validate_phone(phone: str | None, field_name: str = 'Phone') -> str | None:
    """Validate phone: 10-digit Indian or international with + prefix."""
    p = clean_phone(phone)
    if not p:
        return f'{field_name} is required.'
    if _PHONE_DIGITS_RE.match(p):
        return None
    if _PHONE_INTL_RE.match(p):
        return None
    return f'{field_name} must be a 10-digit mobile number or international format (+XXXX...).'


def validate_phone_optional(phone: str | None, field_name: str = 'Phone') -> str | None:
    """Validate phone format only if provided (not blank)."""
    p = clean_phone(phone)
    if not p:
        return None
    return validate_phone(p, field_name)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)


def validate_email(email: str | None, field_name: str = 'Email') -> str | None:
    """Validate email format. Returns error if non-empty and invalid."""
    e = (email or '').strip()
    if not e:
        return None  # optional by default
    if len(e) > 254:
        return f'{field_name} is too long (max 254 characters).'
    if not _EMAIL_RE.match(e):
        return f'{field_name} format is invalid.'
    return None


def validate_email_required(email: str | None, field_name: str = 'Email') -> str | None:
    """Email is required and must be valid."""
    e = (email or '').strip()
    if not e:
        return f'{field_name} is required.'
    return validate_email(e, field_name)


# ---------------------------------------------------------------------------
# Name
# ---------------------------------------------------------------------------
def validate_name(name: str | None, field_name: str = 'Name',
                  min_len: int = 2, max_len: int = 100) -> str | None:
    """Validate a person/entity name."""
    n = (name or '').strip()
    if not n:
        return f'{field_name} is required.'
    if len(n) < min_len:
        return f'{field_name} must be at least {min_len} characters.'
    if len(n) > max_len:
        return f'{field_name} must be at most {max_len} characters.'
    return None


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def validate_date_range(start: date | None, end: date | None,
                        start_label: str = 'Start date',
                        end_label: str = 'End date') -> str | None:
    """Ensure end date is after start date."""
    if start and end and end <= start:
        return f'{end_label} must be after {start_label}.'
    return None


def validate_not_past(d: date | None, field_name: str = 'Date') -> str | None:
    """Ensure date is not in the past."""
    if d and d < date.today():
        return f'{field_name} cannot be in the past.'
    return None


def parse_date(raw: str | None, field_name: str = 'Date') -> tuple[date | None, str | None]:
    """Parse an ISO date string. Returns (date, error)."""
    s = (raw or '').strip()
    if not s:
        return None, f'{field_name} is required.'
    try:
        return date.fromisoformat(s), None
    except (ValueError, TypeError):
        return None, f'{field_name} is not a valid date (expected YYYY-MM-DD).'


def parse_date_optional(raw: str | None, field_name: str = 'Date') -> tuple[date | None, str | None]:
    """Parse an ISO date string, allowing blank. Returns (date_or_None, error)."""
    s = (raw or '').strip()
    if not s:
        return None, None
    try:
        return date.fromisoformat(s), None
    except (ValueError, TypeError):
        return None, f'{field_name} is not a valid date (expected YYYY-MM-DD).'


# ---------------------------------------------------------------------------
# ID Proof (Indian documents)
# ---------------------------------------------------------------------------
_AADHAAR_RE = re.compile(r'^\d{12}$')
_PAN_RE = re.compile(r'^[A-Z]{5}\d{4}[A-Z]$')
_PASSPORT_RE = re.compile(r'^[A-Z]\d{7}$')            # Indian passport
_DL_RE = re.compile(r'^[A-Z]{2}\d{2}\s?\d{11}$')     # Driving license
_VOTER_RE = re.compile(r'^[A-Z]{3}\d{7}$')            # Voter ID

_ID_FORMATS = {
    'Aadhaar':          (_AADHAAR_RE, '12-digit number'),
    'Aadhar':           (_AADHAAR_RE, '12-digit number'),
    'PAN':              (_PAN_RE,     'format ABCDE1234F'),
    'PAN Card':         (_PAN_RE,     'format ABCDE1234F'),
    'Passport':         (_PASSPORT_RE, 'format A1234567'),
    'Driving License':  (_DL_RE,      'format XX00 12345678901'),
    'Voter ID':         (_VOTER_RE,   'format ABC1234567'),
}


def validate_id_proof(id_type: str | None, id_number: str | None) -> str | None:
    """Validate ID proof number format based on document type. Optional — skips if blank."""
    t = (id_type or '').strip()
    n = (id_number or '').strip().upper().replace(' ', '')
    if not t or not n:
        return None  # both blank = skip
    spec = _ID_FORMATS.get(t)
    if not spec:
        return None  # unknown type — accept anything
    regex, desc = spec
    if not regex.match(n):
        return f'{t} number is invalid (expected {desc}).'
    return None


# ---------------------------------------------------------------------------
# PIN code (Indian)
# ---------------------------------------------------------------------------
_PIN_RE = re.compile(r'^\d{6}$')


def validate_pin_code(pin: str | None, field_name: str = 'PIN code') -> str | None:
    """Validate 6-digit Indian PIN code (optional — skips if blank)."""
    p = (pin or '').strip()
    if not p:
        return None
    if not _PIN_RE.match(p):
        return f'{field_name} must be a 6-digit number.'
    return None


# ---------------------------------------------------------------------------
# GSTIN
# ---------------------------------------------------------------------------
_GSTIN_RE = re.compile(r'^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]$')


def validate_gstin(gstin: str | None, field_name: str = 'GSTIN') -> str | None:
    """Validate 15-char GSTIN format (optional — skips if blank)."""
    g = (gstin or '').strip().upper()
    if not g:
        return None
    if not _GSTIN_RE.match(g):
        return f'{field_name} format is invalid (expected 15-character GSTIN).'
    return None


# ---------------------------------------------------------------------------
# Numeric ranges
# ---------------------------------------------------------------------------
def validate_positive_int(value, field_name: str = 'Value',
                          min_val: int = 1, max_val: int = 999) -> str | None:
    """Validate an integer is within range."""
    try:
        v = int(value)
    except (ValueError, TypeError):
        return f'{field_name} must be a whole number.'
    if v < min_val:
        return f'{field_name} must be at least {min_val}.'
    if v > max_val:
        return f'{field_name} cannot exceed {max_val}.'
    return None


def validate_non_negative_float(value, field_name: str = 'Amount') -> str | None:
    """Validate a number is >= 0."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return f'{field_name} must be a valid number.'
    if v < 0:
        return f'{field_name} cannot be negative.'
    return None


def validate_positive_float(value, field_name: str = 'Amount') -> str | None:
    """Validate a number is > 0."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return f'{field_name} must be a valid number.'
    if v <= 0:
        return f'{field_name} must be greater than zero.'
    return None


# ---------------------------------------------------------------------------
# Text length
# ---------------------------------------------------------------------------
def validate_text_length(text: str | None, field_name: str = 'Field',
                         max_len: int = 500) -> str | None:
    """Validate text does not exceed max length (optional — skips if blank)."""
    t = (text or '').strip()
    if not t:
        return None
    if len(t) > max_len:
        return f'{field_name} is too long (max {max_len} characters).'
    return None


# ---------------------------------------------------------------------------
# Enum / allowed values
# ---------------------------------------------------------------------------
def validate_enum(value: str | None, allowed: set | list,
                  field_name: str = 'Value', required: bool = False) -> str | None:
    """Validate value is in the allowed set."""
    v = (value or '').strip()
    if not v:
        return f'{field_name} is required.' if required else None
    if v not in allowed:
        return f'{field_name} "{v}" is not valid. Allowed: {", ".join(sorted(allowed))}.'
    return None


# ---------------------------------------------------------------------------
# Batch validator — collect multiple errors at once
# ---------------------------------------------------------------------------
def validate_fields(*checks) -> list[str]:
    """Run multiple validation checks. Returns list of error messages (empty = all OK).

    Usage:
        errors = validate_fields(
            validate_phone(phone),
            validate_email(email),
            validate_date_range(arrival, departure, 'Arrival', 'Departure'),
        )
        if errors:
            for e in errors:
                flash(e, 'danger')
            return redirect(...)
    """
    return [msg for msg in checks if msg is not None]
