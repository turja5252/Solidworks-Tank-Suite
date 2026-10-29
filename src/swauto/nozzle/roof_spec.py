"""One roof nozzle, in the same terms as the AutoCAD roof nozzle list (ROOFNOZZLES).

Inches throughout. Where it sits on the cone is ``roof_place.place_on_roof``. The neck is plumb and the
flange face level, as the lisp draws them, so both projections are vertical.
"""

from __future__ import annotations

from dataclasses import dataclass

from swauto.nozzle.flange import normalize_kind, normalize_rating
from swauto.nozzle.pipe import normalize_nps, normalize_schedule
from swauto.nozzle.repad import normalize_repad_mode, normalize_repad_style
from swauto.nozzle.spec import normalize_inside_flange

HEIGHT = "height"  # the value is the flange face's height above the roof bearing line, or the ring top
DIRECT = "osp"  # the value is the OSP: from the roof's outside at the centerline up to the flange face
PROJECTION_LABELS = {HEIGHT: "Height above bearing", DIRECT: "Direct OSP"}


def normalize_projection(value: object) -> str:
    """``height`` or ``osp``. Takes the lisp's codes and labels: 0 or "Height above bearing / CR", 1 or
    "Direct OSP"."""
    text = " ".join(str(value if value is not None else "").strip().lower().split())
    if text in ("", "0", "height", "h", "height above bearing", "height above bearing / cr", "b"):
        return HEIGHT
    if text in ("1", "osp", "direct", "direct osp", "directosp", "o.s.p."):
        return DIRECT
    raise ValueError(f"Projection {value!s} must be the height above the bearing line or a direct OSP.")


def read_isp(value: object) -> float | None:
    """A typed ISP in inches, or None for AUTO. As in the lisp, blank, AUTO and 0 all mean AUTO."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in ("", "auto", "a"):
        return None
    try:
        number = float(text)
    except ValueError:
        raise ValueError("The ISP must be a number of inches, or AUTO.") from None
    if number < 0.0:
        raise ValueError("The ISP cannot be negative.")
    return None if number == 0.0 else number


@dataclass(frozen=True)
class RoofNozzle:
    """A plumb nozzle through the cone roof.

    ``degree`` is measured the way a shell nozzle's rotation is: 0 toward +Z, growing toward -X, clockwise
    looking down on the tank, so a roof nozzle at 90 deg sits over a shell nozzle at 90 deg. ``radial_in``
    is the plan distance from the tank center to the centerline before the offset; a positive offset moves
    it square to that line, to the clockwise side, as the lisp has it.

    ``projection_in`` is the flange face's height above the roof bearing line (the lisp's default), or with
    ``projection`` "osp" the OSP itself. ``isp_in`` None is the lisp's AUTO: the inside end 1/4 in under the
    roof, square to it, at the low side of the pipe. A typed ISP is measured down from the roof's underside
    at the centerline, to the inside end, or to the raised face of an inside flange.
    """

    mark: str
    nps: str
    rating: int = 150
    kind: str = "wn"
    schedule: str = "STD"
    degree: float = 0.0
    radial_in: float = 0.0
    offset_in: float = 0.0
    projection: str = HEIGHT
    projection_in: float = 0.0
    isp_in: float | None = None
    inside_flange: str = "none"
    repad_mode: str = "none"
    repad_outer_in: float = 0.0
    repad_inner_in: float = 0.0
    repad_thickness_in: float | None = None  # None is the roof plate's thickness
    repad_style: str = "circular"
    description: str = ""
    blind: bool = False
    gasket: bool = False
    gasket_material: str = ""
    gasket_thickness_in: float | None = None

    def __post_init__(self) -> None:
        mark = " ".join(str(self.mark).split())
        if not mark:
            raise ValueError("A nozzle needs a mark.")
        if self.radial_in < 0.0:
            raise ValueError(f"{mark}: the radial distance cannot be negative.")
        if self.isp_in is not None and self.isp_in <= 0.0:
            raise ValueError(f"{mark}: a typed ISP must be greater than zero; leave it blank for AUTO.")
        object.__setattr__(self, "mark", mark)
        object.__setattr__(self, "nps", normalize_nps(self.nps))
        object.__setattr__(self, "rating", normalize_rating(self.rating))
        object.__setattr__(self, "kind", normalize_kind(self.kind))
        object.__setattr__(self, "schedule", normalize_schedule(self.schedule))
        object.__setattr__(self, "projection", normalize_projection(self.projection))
        object.__setattr__(self, "inside_flange", normalize_inside_flange(self.inside_flange))
        object.__setattr__(self, "repad_mode", normalize_repad_mode(self.repad_mode))
        object.__setattr__(self, "repad_style", normalize_repad_style(self.repad_style))
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "gasket_material", " ".join(str(self.gasket_material).split()))
        if self.projection == DIRECT and self.projection_in <= 0.0:
            raise ValueError(f"{mark}: a direct OSP must be greater than zero.")
        if self.gasket and not self.gasket_material:
            raise ValueError(f"{mark}: type the gasket material.")
        if self.inside_flange != "none" and self.isp_in is None:
            raise ValueError(
                f"{mark}: with an inside flange, type the ISP, from the roof underside down to its raised face."
            )
