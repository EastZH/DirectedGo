"""Stone colours."""

from __future__ import annotations

from enum import IntEnum

__all__ = ["Color"]


class Color(IntEnum):
    """State of a single vertex.

    ``EMPTY`` is a member rather than ``None`` so that a board is a flat array of
    one type and ``stones[v] is Color.EMPTY`` is the only emptiness test needed.
    """

    EMPTY = 0
    BLACK = 1
    WHITE = 2

    def opponent(self) -> "Color":
        """The other colour. Undefined for ``EMPTY``."""
        if self is Color.BLACK:
            return Color.WHITE
        if self is Color.WHITE:
            return Color.BLACK
        raise ValueError("Color.EMPTY has no opponent")

    @property
    def glyph(self) -> str:
        """Single character used by the ASCII renderers."""
        return {Color.EMPTY: ".", Color.BLACK: "X", Color.WHITE: "O"}[self]
