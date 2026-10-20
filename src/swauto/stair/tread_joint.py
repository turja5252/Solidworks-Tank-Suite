"""Tread-to-stringer joint: one pan tread between two straight stringer pieces.

The tread is a five-face pan (top and four walls, no bottom). Both bolt pairs
are located from the tread's front face, the way the spiral stair side profile
draws them, then cut separately through the inner stringer and the outer
stringer into that tread end wall.

Lengths are inches. Z runs from the inner stringer toward the outer stringer,
X is the direction of travel (front face at +X), Y is up.
"""

from __future__ import annotations

from dataclasses import dataclass

from swauto.stair.stringer import (
    BOLT_DIA_IN,
    BOLT_FROM_FRONT_IN,
    BOLT_SPACE_IN,
    BOLT_UP_IN,
    CLEAR_IN,
    THICKNESS_IN,
    TREAD_DEPTH_IN,
    TREAD_MARK_IN,
    TREAD_PLATE_IN,
)


@dataclass(frozen=True)
class TreadJointSpec:
    wall_in: float = 0.5
    stringer_length_in: float = 24.0
    plate_width_in: float = 9.0
    tread_depth_in: float = TREAD_DEPTH_IN
    tread_height_in: float = TREAD_MARK_IN

    def validate(self) -> None:
        if self.wall_in <= 0 or self.wall_in * 2 >= min(self.tread_depth_in, TREAD_PLATE_IN):
            raise ValueError("Pan wall must be greater than zero and thinner than half the tread.")
        if self.wall_in >= self.tread_height_in:
            raise ValueError("Pan wall must be thinner than the tread height.")
        if self.stringer_length_in < self.tread_depth_in:
            raise ValueError("Stringer piece must be at least as long as the tread.")
        if self.plate_width_in < self.tread_height_in:
            raise ValueError("Plate width must be at least the tread height.")


@dataclass(frozen=True)
class TreadJointLayout:
    inner_face_z: float
    inner_back_z: float
    outer_face_z: float
    outer_back_z: float
    tread_z0: float
    tread_z1: float
    tread_x0: float
    tread_x1: float
    tread_y0: float
    tread_y1: float
    wall_in: float
    bolt_xs: tuple[float, float]
    bolt_y: float
    bolt_dia_in: float
    cut_depth_in: float
    stringer_length_in: float
    plate_width_in: float


def layout_tread_joint(spec: TreadJointSpec) -> TreadJointLayout:
    spec.validate()
    clear = (CLEAR_IN - TREAD_PLATE_IN) / 2.0
    half = spec.tread_depth_in / 2.0
    y0 = spec.plate_width_in / 2.0 - spec.tread_height_in / 2.0
    first = half - BOLT_FROM_FRONT_IN
    return TreadJointLayout(
        inner_face_z=0.0,
        inner_back_z=-THICKNESS_IN,
        outer_face_z=CLEAR_IN,
        outer_back_z=CLEAR_IN + THICKNESS_IN,
        tread_z0=clear,
        tread_z1=clear + TREAD_PLATE_IN,
        tread_x0=-half,
        tread_x1=half,
        tread_y0=y0,
        tread_y1=y0 + spec.tread_height_in,
        wall_in=spec.wall_in,
        bolt_xs=(first, first - BOLT_SPACE_IN),
        bolt_y=y0 + BOLT_UP_IN,
        bolt_dia_in=BOLT_DIA_IN,
        cut_depth_in=THICKNESS_IN + clear + spec.wall_in + 0.25,
        stringer_length_in=spec.stringer_length_in,
        plate_width_in=spec.plate_width_in,
    )
