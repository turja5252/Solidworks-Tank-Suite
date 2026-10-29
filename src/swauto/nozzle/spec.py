"""One shell nozzle, in the same terms as the AutoCAD nozzle list.

Inches throughout. The flange, the neck, and the repad are looked up from the
tables; where the nozzle sits on the shell is ``place.place``.
"""

from __future__ import annotations

from dataclasses import dataclass

from swauto.nozzle.flange import normalize_kind, normalize_rating
from swauto.nozzle.pipe import normalize_nps, normalize_schedule
from swauto.nozzle.repad import normalize_repad_mode, normalize_repad_style


INSIDE_NONE = "none"


def normalize_inside_flange(value: object) -> str:
    """``none``, or ``wn`` / ``so`` for a weld neck or slip-on at the inside end. Takes RNC's labels too
    ("CL150 RFSO" ...); the class is the nozzle's, as RNC draws it."""
    text = " ".join(str(value if value is not None else "").strip().lower().split())
    if text in ("", "none", "no", "0", "false", "off", "standard"):
        return INSIDE_NONE
    try:
        return normalize_kind(text)
    except ValueError:
        pass
    if "rfso" in text or "slip" in text:
        return "so"
    if "rfwn" in text or "weld" in text:
        return "wn"
    raise ValueError(f"Inside flange {value!s} must be none, a weld neck or a slip-on.")


@dataclass(frozen=True)
class Nozzle:
    """A radial or parallel shell nozzle. Projections are along the nozzle centerline.

    Outside projection (OSP) is the shell outside to the far end of the flange,
    the raised face. Inside projection (ISP) is the shell inside to the inner end
    of the pipe or neck, or to the raised face of an inside flange. A positive offset
    shifts the nozzle to the clockwise side, looking down on the tank, and keeps
    it parallel to the radial line at ``rotation_deg``. Rotation 0 points the
    nozzle toward +Z; a positive rotation swings it toward −X, the same way the
    stair measures its angle.
    """

    mark: str
    nps: str
    rating: int = 150
    kind: str = "wn"
    schedule: str = "XS"
    elevation_in: float = 0.0
    rotation_deg: float = 0.0
    outside_projection_in: float = 0.0
    inside_projection_in: float = 0.0
    offset_in: float = 0.0
    match_plane: bool = False
    repad_mode: str = "none"
    repad_outer_in: float = 0.0
    repad_inner_in: float = 0.0
    repad_thickness_in: float | None = None
    repad_style: str = "circular"
    telltale_offset_in: float = 1.0
    description: str = ""
    blind: bool = False  # a blind flange bolted to the face
    gasket: bool = False  # a flat ring gasket on the face, under the blind if there is one
    gasket_material: str = ""
    gasket_thickness_in: float | None = None  # None is 1/8 in
    # RNC's break flange: a flange at the inside end, ``none``, ``wn`` or ``so``, in the nozzle's own class.
    # Its raised face is the inside end, so ISP runs to it; its hub points back at the shell.
    inside_flange: str = "none"

    def __post_init__(self) -> None:
        mark = " ".join(str(self.mark).split())
        if not mark:
            raise ValueError("A nozzle needs a mark.")
        if self.elevation_in < 0.0:
            raise ValueError(f"{mark}: elevation cannot be below the tank floor.")
        if self.outside_projection_in < 0.0 or self.inside_projection_in < 0.0:
            raise ValueError(f"{mark}: projections cannot be negative.")
        object.__setattr__(self, "mark", mark)
        object.__setattr__(self, "nps", normalize_nps(self.nps))
        object.__setattr__(self, "rating", normalize_rating(self.rating))
        object.__setattr__(self, "kind", normalize_kind(self.kind))
        object.__setattr__(self, "schedule", normalize_schedule(self.schedule))
        object.__setattr__(self, "repad_mode", normalize_repad_mode(self.repad_mode))
        object.__setattr__(self, "repad_style", normalize_repad_style(self.repad_style))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "gasket_material", " ".join(str(self.gasket_material).split()))
        object.__setattr__(self, "inside_flange", normalize_inside_flange(self.inside_flange))
        if self.gasket and not self.gasket_material:
            raise ValueError(f"{mark}: type the gasket material.")
