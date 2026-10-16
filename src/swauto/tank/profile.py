"""Build the shell wall revolve profile from Tank Properties (meters)."""

from __future__ import annotations

from swauto.tank.spec import WALL_ID, WALL_OD, Course, TankSpec, normalize_wall
from swauto.units import to_meters


def _radii_for_reference(reference_m: float, thickness_m: float, wall: str) -> tuple[float, float]:
    """Place a wall of ``thickness_m`` on a radius that is OD, ID, or mid-wall."""
    if wall == WALL_OD:
        return reference_m, reference_m - thickness_m
    if wall == WALL_ID:
        return reference_m + thickness_m, reference_m
    mid = reference_m
    return mid + thickness_m / 2.0, mid - thickness_m / 2.0


def _check_radii(outer: float, inner: float, course: Course, spec: TankSpec) -> tuple[float, float]:
    if inner <= 0 or outer <= inner:
        raise ValueError(
            f"Course thickness {course.thickness_in:g}\" is too large for "
            f"diameter {spec.diameter_in:g}\" ({spec.diameter_basis})."
        )
    return outer, inner


def course_radii_m(spec: TankSpec, course: Course) -> tuple[float, float]:
    """Return (outer_radius_m, inner_radius_m).

    The typed diameter is the first course only: OD, ID, or mid-wall.
    ``spec.stack`` is one choice for the whole shell. Every course lines
    that same face up with the first course.
    """
    active = spec.active_courses() or [course]
    first = active[0]
    basis = normalize_wall(spec.diameter_basis, what="First course diameter")
    first_outer, first_inner = _check_radii(
        *_radii_for_reference(to_meters(spec.diameter_in, "in") / 2.0, to_meters(first.thickness_in, "in"), basis),
        first,
        spec,
    )
    if course is first:
        return first_outer, first_inner

    stack = normalize_wall(spec.stack, what="Shell stack")
    thickness_m = to_meters(course.thickness_in, "in")
    if stack == WALL_OD:
        reference = first_outer
    elif stack == WALL_ID:
        reference = first_inner
    else:
        reference = 0.5 * (first_outer + first_inner)
    return _check_radii(*_radii_for_reference(reference, thickness_m, stack), course, spec)


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
