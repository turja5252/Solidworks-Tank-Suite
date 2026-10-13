"""Build the shell wall revolve profile from Tank Properties (meters)."""

from __future__ import annotations

from swauto.tank.spec import Course, TankSpec
from swauto.units import to_meters


def course_radii_m(spec: TankSpec, course: Course) -> tuple[float, float]:
    """Return (outer_radius_m, inner_radius_m) for one course."""
    dia_m = to_meters(spec.diameter_in, "in")
    thk_m = to_meters(course.thickness_in, "in")
    half = dia_m / 2.0
    if spec.diameter_basis == "outside":
        outer, inner = half, half - thk_m
    elif spec.diameter_basis == "inside":
        inner, outer = half, half + thk_m
    else:  # centerline — plate mid-wall on the given diameter
        outer, inner = half + thk_m / 2.0, half - thk_m / 2.0
    if inner <= 0 or outer <= inner:
        raise ValueError(
            f"Course thickness {course.thickness_in:g}\" is too large for "
            f"diameter {spec.diameter_in:g}\" ({spec.diameter_basis})."
        )
    return outer, inner


def shell_profile_meters(spec: TankSpec) -> list[tuple[float, float]]:
    """Closed polyline (x=radial, y=height) for a 360° revolve, outside/inside stepped wall."""
    spec.validate()
    courses = spec.active_courses()
    heights = [to_meters(c.height_in, "in") for c in courses]
    radii = [course_radii_m(spec, c) for c in courses]

    y_levels = [0.0]
    for h in heights:
        y_levels.append(y_levels[-1] + h)

    # Outer face bottom → top (use each course outer; step if outside grows/shrinks).
    points: list[tuple[float, float]] = []
    points.append((radii[0][0], y_levels[0]))
    for i, (outer, _inner) in enumerate(radii):
        y_bot = y_levels[i]
        y_top = y_levels[i + 1]
        if abs(points[-1][0] - outer) > 1e-12:
            points.append((outer, y_bot))
        points.append((outer, y_top))

    # Inner face top → bottom with thickness steps.
    for i in range(len(courses) - 1, -1, -1):
        _outer, inner = radii[i]
        y_top = y_levels[i + 1]
        y_bot = y_levels[i]
        if abs(points[-1][0] - inner) > 1e-12 or abs(points[-1][1] - y_top) > 1e-12:
            points.append((inner, y_top))
        points.append((inner, y_bot))

    # Close back to first point.
    if points[0] != points[-1]:
        points.append(points[0])
    return points
