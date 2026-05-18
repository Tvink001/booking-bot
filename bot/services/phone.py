"""Ukrainian phone normalization. Pure function — see project_specs.md §9.6."""

import re


def normalize_phone(raw: str) -> str | None:
    """Return canonical `+380XXXXXXXXX` or None if unparseable.

    Accepts variations: with/without country code, with/without leading 0,
    with spaces, dashes, parentheses.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("380") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("80") and len(digits) == 11:
        return f"+3{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+38{digits}"
    if len(digits) == 9 and not digits.startswith("0"):
        return f"+380{digits}"
    return None
