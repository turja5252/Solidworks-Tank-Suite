"""Instant tank preview geometry — pure math, no SolidWorks.

Builds a lightweight scene from ``TankProject`` (or shell/floor/roof specs)
so the UI can show elevation, plan, and a simple 3/4 view before any COM build.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from swauto.tank.floor import FloorPlate, FloorSpec, layout_floor
from swauto.tank.plates import PlateSector, layout_plates
from swauto.tank.profile import course_radii_m, shell_profile_meters
from swauto.tank.project import TankProject
from swauto.tank.roof import RoofSpec, cone_profile_in, roof_from_tank
from swauto.tank.spec import TankSpec

_INCH = 0.0254


@dataclass(frozen=True)
class PreviewScene:
    """Everything the preview canvases need, in inches."""

    shell: TankSpec
    floor: FloorSpec
    roof: RoofSpec
    shell_od_in: float
    shell_height_in: float
    # Right-half wall profile (radius, height) closed polyline.
    shell_section_in: tuple[tuple[float, float], ...]
    roof_section_in: tuple[tuple[float, float], ...]
    floor_plates: tuple[FloorPlate, ...]
    shell_plates: tuple[PlateSector, ...]
    course_bands_in: tuple[tuple[float, float, float, float], ...]  # z0, z1, r_out, r_in
    stair_od_in: float
    stair_gap_in: float
    errors: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


def build_preview(project: TankProject) -> PreviewScene:
    """Snapshot the coherent tank into preview geometry."""
    errors: list[str] = []
    notes: list[str] = []
    shell = project.shell
    floor = project.floor
    roof = project.roof
    try:
        shell.validate()
    except ValueError as exc:
        errors.append(f"Shell: {exc}")
        return _empty_scene(shell, floor, roof, errors)

    try:
        od = project.course1_od_in()
    except ValueError as exc:
        errors.append(str(exc))
        od = shell.diameter_in

    height = shell.shell_height_in()
    try:
        profile_m = shell_profile_meters(shell)
        shell_section = tuple((r / _INCH, z / _INCH) for r, z in profile_m)
    except ValueError as exc:
        errors.append(f"Shell profile: {exc}")
        shell_section = ()

    bands: list[tuple[float, float, float, float]] = []
    z = 0.0
    for course in shell.active_courses():
        try:
            outer_m, inner_m = course_radii_m(shell, course)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        bands.append((z, z + course.height_in, outer_m / _INCH, inner_m / _INCH))
        z += course.height_in

    try:
        plates = tuple(layout_plates(shell))
    except ValueError as exc:
        plates = ()
        notes.append(f"Shell plates: {exc}")

    try:
        floor.validate()
        floor_plates = tuple(layout_floor(floor))
    except ValueError as exc:
        floor_plates = ()
        notes.append(f"Floor: {exc}")

    try:
        if project.follow_shell:
            roof = roof_from_tank(shell, roof.slope_in_per_ft, roof.thickness_in)
            # Preserve module-local roof options from the project copy.
            src = project.roof
            roof = RoofSpec(
                inside_radius_in=roof.inside_radius_in,
                outside_radius_in=roof.outside_radius_in,
                shell_height_in=roof.shell_height_in,
                slope_in_per_ft=src.slope_in_per_ft,
                thickness_in=src.thickness_in,
                ring=src.ring,
                ring_top_offset_in=src.ring_top_offset_in,
                landing_inset_in=src.landing_inset_in,
                bar_width_in=src.bar_width_in,
                bar_height_in=src.bar_height_in,
                angle_horizontal_in=src.angle_horizontal_in,
                angle_vertical_in=src.angle_vertical_in,
                angle_thickness_in=src.angle_thickness_in,
                ignore_pie=src.ignore_pie,
                plate_width_in=src.plate_width_in,
                plate_length_in=src.plate_length_in,
                plate_lap_in=src.plate_lap_in,
            )
        roof.validate()
        roof_section = cone_profile_in(roof)
    except ValueError as exc:
        roof_section = ()
        notes.append(f"Roof: {exc}")

    stair_od = od
    stair_gap = project.stair.gap_in
    return PreviewScene(
        shell=shell,
        floor=floor,
        roof=roof,
        shell_od_in=od,
        shell_height_in=height,
        shell_section_in=shell_section,
        roof_section_in=roof_section,
        floor_plates=floor_plates,
        shell_plates=plates,
        course_bands_in=tuple(bands),
        stair_od_in=stair_od,
        stair_gap_in=stair_gap,
        errors=tuple(errors),
        notes=tuple(notes),
    )


def _empty_scene(shell, floor, roof, errors: list[str]) -> PreviewScene:
    return PreviewScene(
        shell=shell,
        floor=floor,
        roof=roof,
        shell_od_in=0.0,
        shell_height_in=0.0,
        shell_section_in=(),
        roof_section_in=(),
        floor_plates=(),
        shell_plates=(),
        course_bands_in=(),
        stair_od_in=0.0,
        stair_gap_in=0.0,
        errors=tuple(errors),
    )


def summary_line(scene: PreviewScene) -> str:
    if scene.errors:
        return scene.errors[0]
    parts = [
        f"OD {scene.shell_od_in:g}\" · H {scene.shell_height_in:g}\"",
        f"{len(scene.shell.active_courses())} courses",
        f"{len(scene.shell_plates)} shell plates",
        f"{len(scene.floor_plates)} floor plates",
    ]
    if scene.roof_section_in:
        parts.append(f"roof slope {scene.roof.slope_in_per_ft:g} in/ft")
    if scene.notes:
        parts.append(scene.notes[0])
    return " · ".join(parts)


def isometric_ring(
    radius_in: float,
    z_in: float,
    *,
    yaw_deg: float = 35.0,
    pitch_deg: float = 28.0,
    steps: int = 48,
) -> list[tuple[float, float]]:
    """Project a horizontal circle at height ``z_in`` into a simple 3/4 view (inches → screen space units)."""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    points: list[tuple[float, float]] = []
    for i in range(steps + 1):
        ang = 2.0 * math.pi * i / steps
        x = radius_in * math.cos(ang)
        y = radius_in * math.sin(ang)
        # Rotate about Z then tip about X.
        xr = x * cy - y * sy
        yr = x * sy + y * cy
        # screen x = xr, screen y = yr*cp - z*sp (up positive in model → down later in canvas)
        points.append((xr, yr * cp - z_in * sp))
    return points
