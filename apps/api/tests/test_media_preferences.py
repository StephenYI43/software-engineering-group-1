"""Boundary checks for the internal preference value object."""

from decimal import Decimal

import pytest

from app.domains.media.preferences import MediaPreferences


def test_defaults_and_inclusive_boundaries() -> None:
    defaults = MediaPreferences()
    assert defaults.auto_play is False
    assert defaults.subtitles_enabled is True
    assert defaults.volume == Decimal("1.00")
    assert defaults.speech_rate == Decimal("1.00")
    assert MediaPreferences(volume=Decimal("0"), speech_rate=Decimal("0.5"))
    assert MediaPreferences(volume=Decimal("1"), speech_rate=Decimal("2"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("volume", Decimal("-0.01")),
        ("volume", Decimal("1.01")),
        ("volume", Decimal("0.001")),
        ("speech_rate", Decimal("0.49")),
        ("speech_rate", Decimal("2.01")),
        ("speech_rate", Decimal("1.001")),
        ("volume", Decimal("NaN")),
        ("speech_rate", Decimal("Infinity")),
        ("auto_play", 1),
        ("subtitles_enabled", "true"),
        ("volume", 0.5),
    ],
)
def test_invalid_values_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        MediaPreferences(**{field: value})  # type: ignore[arg-type]
