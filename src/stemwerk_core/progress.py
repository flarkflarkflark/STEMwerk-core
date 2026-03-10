from __future__ import annotations

from typing import Protocol


class ProgressCallback(Protocol):
    """Callback signature for progress updates.

    Args:
        percent: Progress percentage from 0.0 to 100.0.
        message: Human-readable status message.
    """

    def __call__(self, percent: float, message: str) -> None:
        ...
