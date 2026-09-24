"""Vertex labelling schemes.

A scheme is a pure function pair: it turns a grid coordinate ``(x, y)`` into a
label and back, for a given board extent. ``Graph`` never learns about schemes --
the topology builders use one to mint a ``labels`` tuple, and ``Graph`` just
indexes it. That keeps arbitrary graphs (rings, custom topologies) free to label
their vertices however they like, including not at all.

Convention, matching Go: ``x`` runs left to right, ``y`` runs **bottom to top**,
so ``y = 0`` is row 1. Vertex ids follow ``id = y * width + x``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = [
    "GO_COLUMNS",
    "LabelScheme",
    "GoStandard",
    "Alphabet",
    "Numeric",
    "GO_STANDARD",
    "ALPHABET",
    "NUMERIC",
]

#: Board columns as humans write them: ``I`` is omitted, exactly as in Go.
GO_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


@runtime_checkable
class LabelScheme(Protocol):
    """Turns grid coordinates into labels and back."""

    def label_of_xy(self, x: int, y: int, width: int, height: int) -> str:
        """Label for the vertex at ``(x, y)``."""
        ...

    def xy_of_label(self, label: str, width: int, height: int) -> tuple[int, int]:
        """``(x, y)`` for ``label``. Raises ``OutOfBoundsError`` if unknown."""
        ...


class _Base:
    """Shared validation helper for the concrete schemes."""

    def _build(self, width: int, height: int) -> tuple[str, ...]:
        return tuple(
            self.label_of_xy(x, y, width, height)
            for y in range(height)
            for x in range(width)
        )


class GoStandard(_Base):
    """``A..T`` skipping ``I``, rows counted from 1 at the bottom.

    This is what ``square_grid(19, 19)`` uses, so ``A19`` sits at ``(0, 18)`` and
    its neighbours are exactly ``B19`` and ``A18``.
    """

    columns = GO_COLUMNS

    def label_of_xy(self, x: int, y: int, width: int, height: int) -> str:
        if not (0 <= x < width and 0 <= y < height):
            from .errors import OutOfBoundsError

            raise OutOfBoundsError(f"({x}, {y}) outside {width}x{height} board")
        if width > len(self.columns):
            raise ValueError(f"board of width {width} exceeds {len(self.columns)} columns")
        return f"{self.columns[x]}{y + 1}"

    def xy_of_label(self, label: str, width: int, height: int) -> tuple[int, int]:
        from .errors import OutOfBoundsError

        text = label.strip().upper()
        split = 0
        while split < len(text) and text[split].isalpha():
            split += 1
        letters, digits = text[:split], text[split:]
        if not letters or not digits.isdigit():
            raise OutOfBoundsError(f"cannot parse label {label!r}")
        if letters not in self.columns:
            # Keep the "I is not a column" rule honest rather than silently
            # mapping I -> J.
            raise OutOfBoundsError(f"unknown column {letters!r} in label {label!r}")
        x, y = self.columns.index(letters), int(digits) - 1
        if not (0 <= x < width and 0 <= y < height):
            raise OutOfBoundsError(f"{label!r} outside {width}x{height} board")
        return x, y


class Alphabet(_Base):
    """``A..Z`` then ``a..z``, **including** ``I``.

    Useful for tiny boards and non-grid shapes (rings) where the Go convention of
    dropping ``I`` buys nothing.
    """

    columns = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

    def label_of_xy(self, x: int, y: int, width: int, height: int) -> str:
        if not (0 <= x < width and 0 <= y < height):
            from .errors import OutOfBoundsError

            raise OutOfBoundsError(f"({x}, {y}) outside {width}x{height} board")
        return f"{self.columns[x]}{y + 1}"

    def xy_of_label(self, label: str, width: int, height: int) -> tuple[int, int]:
        from .errors import OutOfBoundsError

        text = label.strip()
        split = 0
        while split < len(text) and text[split].isalpha():
            split += 1
        letters, digits = text[:split], text[split:]
        if not letters or not digits.isdigit() or letters not in self.columns:
            raise OutOfBoundsError(f"cannot parse label {label!r}")
        x, y = self.columns.index(letters), int(digits) - 1
        if not (0 <= x < width and 0 <= y < height):
            raise OutOfBoundsError(f"{label!r} outside {width}x{height} board")
        return x, y


class Numeric(_Base):
    """``"3-15"``: 1-based ``x`` and ``y``, unambiguous for any graph."""

    def label_of_xy(self, x: int, y: int, width: int, height: int) -> str:
        if not (0 <= x < width and 0 <= y < height):
            from .errors import OutOfBoundsError

            raise OutOfBoundsError(f"({x}, {y}) outside {width}x{height} board")
        return f"{x + 1}-{y + 1}"

    def xy_of_label(self, label: str, width: int, height: int) -> tuple[int, int]:
        from .errors import OutOfBoundsError

        parts = label.strip().split("-")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise OutOfBoundsError(f"cannot parse label {label!r}")
        x, y = int(parts[0]) - 1, int(parts[1]) - 1
        if not (0 <= x < width and 0 <= y < height):
            raise OutOfBoundsError(f"{label!r} outside {width}x{height} board")
        return x, y


GO_STANDARD: LabelScheme = GoStandard()
ALPHABET: LabelScheme = Alphabet()
NUMERIC: LabelScheme = Numeric()
