"""Phone normalization tests — every input format from spec §9.6 + rejects."""

import pytest

from bot.services.phone import normalize_phone


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+380501234567", "+380501234567"),
        ("380501234567", "+380501234567"),
        ("0501234567", "+380501234567"),
        ("050 123 45 67", "+380501234567"),
        ("(050) 123-45-67", "+380501234567"),
        ("80501234567", "+380501234567"),
        ("501234567", "+380501234567"),
    ],
)
def test_normalize_phone_accepts(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abcdefg", "12345"])
def test_normalize_phone_rejects(raw: str) -> None:
    assert normalize_phone(raw) is None
