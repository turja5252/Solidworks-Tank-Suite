"""The handrail's heights, the user's to set (2026-10-30: "adjustable in the Stair game, make it easy").

Inches. On a flight a rail's height is its top edge over the stringer's top edge, which runs through every tread's
top front corner; on a platform it is over the grating. The defaults are the lisp's and Elite's: the top rail 42 in,
the flights' midrail halfway up to it, the platforms' midrail 24 in, the grab rail's pipe and the inside pipe 34 in.
"""

from __future__ import annotations

from dataclasses import dataclass

RAIL_TOP_IN = 42.0  # top rail's top edge
GRAB_TOP_IN = 34.0  # grab rail pipe's top, on a flight
INNER_PIPE_TOP_IN = 34.0  # the inside handrail's pipe top (Elite STWE)
PLATFORM_MID_TOP_IN = 24.0  # the lisp's default over the grating; the end pieces come down to its bottom
SNAP_IN = 0.25  # the Stair game moves a rail in quarter inches


@dataclass(frozen=True)
class RailHeights:
    """Every rail's height. ``mid`` None puts the flights' midrail halfway up to the top rail, as the lisp's
    automatic midrail does, so it follows the top rail."""

    top: float = RAIL_TOP_IN
    mid: float | None = None
    platform_mid: float = PLATFORM_MID_TOP_IN
    grab: float = GRAB_TOP_IN
    inner: float = INNER_PIPE_TOP_IN

    @property
    def flight_mid(self) -> float:
        """The flights' midrail top."""
        return self.top / 2.0 if self.mid is None else self.mid

    def validate(self) -> None:
        if not 30.0 <= self.top <= 60.0:
            raise ValueError("The top rail must be 30 to 60 in up.")
        if not 6.0 <= self.flight_mid <= self.top - 6.0:
            raise ValueError(f"The flights' midrail must be 6 in up to 6 in under the top rail ({self.top:g} in).")
        if not 20.0 <= self.grab <= self.top - 3.0:
            raise ValueError(f"The grab rail must be 20 in up to 3 in under the top rail ({self.top:g} in).")
        if not 20.0 <= self.inner <= 48.0:
            raise ValueError("The inside pipe must be 20 to 48 in up.")


def snap(value: float) -> float:
    """To the Stair game's quarter inch."""
    return round(value / SNAP_IN) * SNAP_IN
