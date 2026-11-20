"""Plain-Python checks for contact details (no extra dependency such as email-validator)."""
import re

_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24}$")
_PHONE = re.compile(r"^\+?[\d\s().-]{7,25}$")


def normalize_email(value: str) -> str:
    """Lower-cased email, or ValueError. Rejects spaces, line breaks and missing domains."""
    email = value.strip().lower()
    if len(email) > 254 or ".." in email or not _EMAIL.match(email):
        raise ValueError("enter a valid email address")
    return email


def normalize_phone(value: str) -> str:
    """Phone as typed (trimmed) if it looks like one: 7-15 digits plus spaces/()+-. ; else ValueError."""
    phone = value.strip()
    digits = sum(c.isdigit() for c in phone)
    if not _PHONE.match(phone) or not 7 <= digits <= 15:
        raise ValueError("enter a valid phone number")
    return phone
