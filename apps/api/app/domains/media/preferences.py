"""Internal value validation for the proposed M4 preference fields."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def _validate_decimal(value: Decimal, minimum: str, maximum: str, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if not Decimal(minimum) <= value <= Decimal(maximum):
        raise ValueError(f"{field} is out of range")
    try:
        if value != value.quantize(Decimal("0.01")):
            raise ValueError(f"{field} must have at most two decimal places")
    except InvalidOperation:
        raise ValueError(f"{field} is not a valid decimal") from None


@dataclass(frozen=True)
class MediaPreferences:
    """Validated internal settings, not a published wire schema."""

    auto_play: bool = False
    volume: Decimal = Decimal("1.00")
    speech_rate: Decimal = Decimal("1.00")
    subtitles_enabled: bool = True

    def __post_init__(self) -> None:
        if type(self.auto_play) is not bool or type(self.subtitles_enabled) is not bool:
            raise ValueError("preference flags must be booleans")
        _validate_decimal(self.volume, "0", "1", "volume")
        _validate_decimal(self.speech_rate, "0.5", "2", "speech_rate")
