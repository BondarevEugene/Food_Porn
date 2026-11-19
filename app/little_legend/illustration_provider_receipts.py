"""Optional image-provider receipt; never infer a charge from queue estimates."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IllustrationProviderResult:
    data: bytes
    actual_micro_usd: int | None = None
    provider_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.data:
            raise ValueError("Image data is empty")
        if self.actual_micro_usd is None and self.provider_reference is None:
            return
        if (
            not isinstance(self.actual_micro_usd, int)
            or isinstance(self.actual_micro_usd, bool)
            or self.actual_micro_usd < 0
            or not isinstance(self.provider_reference, str)
            or not 1 <= len(self.provider_reference) <= 160
        ):
            raise ValueError("Incomplete image provider receipt")
