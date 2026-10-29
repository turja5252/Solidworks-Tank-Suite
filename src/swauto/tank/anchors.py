"""Anchor chairs round the bottom of the shell, as Elite's lisp lays them out (Anchor Chairs.lsp).

N identical chairs, equally spaced from the global rotation, each nudged by its own offset ("3:15,4:-10").
A chair is a top plate against the shell with the bolt hole, a washer plate on it, and two legs (tapered
gussets) standing on the bottom plate's projection, each with a corner clip over the shell-to-bottom weld.

Lengths are inches: r out from the course 1 outside, t along the shell (the chair's centerline at 0), y up
from the floor's top. Angles are the app's: 0 toward +Z, growing clockwise seen from above (the lisp's
plan: 0 at 12 o'clock, clockwise).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WASHER_HOLE_EXTRA_IN = 0.125  # the washer's hole is the top plate's plus 1/8 in


def read_offsets(text: str) -> dict[int, float]:
    """The lisp's per-chair offsets: "k:deg" pairs split on commas. Tokens without a colon are skipped and a
    chair named twice keeps its last offset."""
    found: dict[int, float] = {}
    for token in str(text or "").split(","):
        if ":" not in token:
            continue
        number, _, degrees = token.partition(":")
        try:
            found[int(number.strip())] = float(degrees.strip())
        except ValueError:
            raise ValueError(f"Chair offset {token.strip()!r} must be a chair number and degrees, like 3:15.") from None
    return found


@dataclass(frozen=True)
class AnchorChairs:
    """The lisp's inputs, with its defaults. Those defaults put the bolt hole off the top plate, so they will not
    build as they are: type the chair's real sizes."""

    count: int = 24
    rotation_deg: float = 0.0
    offsets: str = ""
    top_plate_width_in: float = 12.5  # along the shell
    top_plate_depth_in: float = 4.0  # out from the shell
    top_plate_thk_in: float = 0.25
    height_in: float = 20.0  # floor top to the top of the top plate
    leg_thk_in: float = 0.75  # each leg, along the shell
    leg_gap_in: float = 10.0  # clear, between the legs
    washer_width_in: float = 12.5  # along the shell
    washer_thk_in: float = 1.75
    washer_depth_in: float = 4.0  # out from the shell, centered on the hole
    hole_dia_in: float = 1.0
    hole_from_shell_in: float = 8.0
    weld_leg_in: float = 0.25  # the shell-to-bottom fillet each leg is clipped over
    chime_in: float = 2.5  # the bottom plate's projection past the shell: the legs' foot

    @property
    def leg_height_in(self) -> float:
        return self.height_in - self.top_plate_thk_in

    def validate(self) -> None:
        sizes = {k: v for k, v in vars(self).items() if k.endswith("_in")}
        for name, value in sizes.items():
            if value <= 0.0:
                what = name.removesuffix("_in").replace("_", " ")
                raise ValueError(f"The anchor chair's {what} must be more than 0.")
        if not 1 <= self.count <= 360:
            raise ValueError("Use 1 to 360 anchor chairs.")
        read_offsets(self.offsets)
        depth, e, half_hole = self.top_plate_depth_in, self.hole_from_shell_in, self.hole_dia_in / 2.0
        if e + half_hole >= depth:
            raise ValueError(
                f"The bolt hole, {e:g} in out from the shell, is off the {depth:g} in deep top plate. Make the top "
                "plate deeper or bring the hole in."
            )
        half_washer = self.washer_depth_in / 2.0
        if e - half_washer < 0.0 or e + half_washer > depth:
            raise ValueError(
                f"The washer, {self.washer_depth_in:g} in deep on the hole, runs off the {depth:g} in top plate."
            )
        if self.washer_width_in > self.top_plate_width_in:
            raise ValueError("The washer is wider than the top plate.")
        if self.leg_gap_in / 2.0 + self.leg_thk_in > self.top_plate_width_in / 2.0:
            raise ValueError("The legs stand out past the ends of the top plate.")
        if half_hole + WASHER_HOLE_EXTRA_IN / 2.0 >= self.leg_gap_in / 2.0:
            raise ValueError("The bolt hole does not clear the legs.")
        if self.chime_in <= self.weld_leg_in or self.leg_height_in <= self.weld_leg_in:
            raise ValueError("The legs' weld clip is bigger than the leg.")
        if self.chime_in > depth:
            raise ValueError("The legs' foot is deeper than the top plate.")


@dataclass(frozen=True)
class Chair:
    number: int
    angle_deg: float


def chairs(spec: AnchorChairs) -> list[Chair]:
    """Chair k at rotation + 360 (k - 1) / N + its offset."""
    spec.validate()
    offsets = read_offsets(spec.offsets)
    step = 360.0 / spec.count
    return [Chair(k, (spec.rotation_deg + step * (k - 1) + offsets.get(k, 0.0)) % 360.0)
            for k in range(1, spec.count + 1)]


def bolt_point(spec: AnchorChairs, shell_radius_in: float, chair: Chair) -> tuple[float, float]:
    """Plan (X, Z) of a chair's bolt, ``hole_from_shell_in`` out from the course 1 outside."""
    phi = math.radians(chair.angle_deg)
    reach = shell_radius_in + spec.hole_from_shell_in
    return (-reach * math.sin(phi), reach * math.cos(phi))


def warnings(spec: AnchorChairs, shell_radius_in: float, course_one_in: float | None = None) -> list[str]:
    """What the lisp does not check but a fitter would: chairs touching, the bolt through the bottom plate, the
    chair over the first girth seam."""
    out = []
    spots = chairs(spec)
    if len(spots) > 1:
        angles = sorted(c.angle_deg for c in spots) + [sorted(c.angle_deg for c in spots)[0] + 360.0]
        closest = min(b - a for a, b in zip(angles, angles[1:]))
        if math.radians(closest) * shell_radius_in < spec.top_plate_width_in:
            out.append("Some anchor chairs overlap their neighbors.")
    if spec.hole_from_shell_in - spec.hole_dia_in / 2.0 <= spec.chime_in:
        out.append("The bolt hole is over the bottom plate's projection: the bolt would go through it.")
    top = spec.height_in + spec.washer_thk_in
    if course_one_in is not None and top > course_one_in:
        out.append(f"The chairs stand {top:g} in tall, past the first course ({course_one_in:g} in).")
    return out


def leg_profile(spec: AnchorChairs) -> list[tuple[float, float]]:
    """A leg in the chair's section, (r, y): under the top plate, down the taper to the chime, along the bottom
    plate to the weld clip, and up the shell."""
    top = spec.leg_height_in
    return [(0.0, top), (spec.top_plate_depth_in, top), (spec.chime_in, 0.0), (spec.weld_leg_in, 0.0),
            (0.0, spec.weld_leg_in)]


def front_silhouette(spec: AnchorChairs) -> list[tuple[float, float]]:
    """The whole chair seen from outside, one (t, y) outline: the two legs, the top plate and the washer."""
    w, ww, g, s = spec.top_plate_width_in / 2.0, spec.washer_width_in / 2.0, spec.leg_gap_in / 2.0, spec.leg_thk_in
    legs, top, washer = spec.leg_height_in, spec.height_in, spec.height_in + spec.washer_thk_in
    right = [(g, legs), (g, 0.0), (g + s, 0.0), (g + s, legs), (w, legs), (w, top), (ww, top), (ww, washer)]
    left = [(-t, y) for t, y in reversed(right)]
    return right + left


def front_outlines(spec: AnchorChairs) -> list[tuple[str, list[tuple[float, float]]]]:
    """The chair seen from outside, (t, y) outlines: top plate, washer and both legs."""
    w, ww, g, s = spec.top_plate_width_in / 2.0, spec.washer_width_in / 2.0, spec.leg_gap_in / 2.0, spec.leg_thk_in
    legs, top, washer = spec.leg_height_in, spec.height_in, spec.height_in + spec.washer_thk_in

    def box(t0, t1, y0, y1):
        return [(t0, y0), (t1, y0), (t1, y1), (t0, y1)]

    return [("top plate", box(-w, w, legs, top)), ("washer", box(-ww, ww, top, washer)),
            ("leg", box(-g - s, -g, 0.0, legs)), ("leg", box(g, g + s, 0.0, legs))]
