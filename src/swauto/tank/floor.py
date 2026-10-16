"""Lap-welded flat floor.

This step builds the shoulder plates the way SOLDIERPLATES does.
Plate width runs across the centerline. Plate length runs square to that.
Plate on centerline centers one plate on the line. Seam on centerline
centers the lap on the line, seam half a lap to the right. Full plates
continue left and right until the next one would leave the circle.
The whole row can then be rotated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

CENTER_PLATE = "cp"
CENTER_SEAM = "cl"

END_MIN_FT = 3.0
END_MAX_FT = 15.0

ARC_STEP_DEG = 3.0
_MIN_PLATE_AREA_SQIN = 0.5
_EPS = 1e-6
_FULL_TOL = 0.05

ROW_COLORS = (
    (0.61, 0.69, 0.77),
    (0.83, 0.57, 0.23),
    (0.50, 0.62, 0.53),
    (0.71, 0.54, 0.60),
)


def row_color_hex(row_number: int) -> str:
    red, green, blue = ROW_COLORS[(row_number - 1) % len(ROW_COLORS)]
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


@dataclass(frozen=True)
class FloorSpec:
    """Flat-bottom plate inputs. Units are inches except the end-cap length."""

    diameter_in: float = 606.0
    thickness_in: float = 0.25
    plate_width_in: float = 96.0
    max_length_in: float = 480.0
    lap_in: float = 2.0
    projection_in: float = 2.0
    center: str = CENTER_PLATE
    end_long_ft: float = END_MAX_FT
    center_shift_in: float = 0.0
    soldier_courses: int = 3
    soldier_edge_in: float = 0.0
    rotation_deg: float = 0.0

    def trim_radius_in(self) -> float:
        return self.diameter_in / 2.0 + self.projection_in

    def validate(self) -> None:
        if self.diameter_in <= 0:
            raise ValueError("Floor diameter must be greater than zero.")
        if self.thickness_in <= 0:
            raise ValueError("Floor thickness must be greater than zero.")
        if self.plate_width_in <= 0 or self.max_length_in <= 0:
            raise ValueError("Plate width and max length must be greater than zero.")
        if self.lap_in < 0:
            raise ValueError("Lap cannot be negative.")
        if self.lap_in >= self.plate_width_in or self.lap_in >= self.max_length_in:
            raise ValueError("Lap must be smaller than the plate width and the max length.")
        if self.projection_in < 0:
            raise ValueError("Arc offset cannot be negative.")
        if self.center not in (CENTER_PLATE, CENTER_SEAM):
            raise ValueError("Center must be CP or CL.")
        if not END_MIN_FT - 1e-9 <= self.end_long_ft <= END_MAX_FT + 1e-9:
            raise ValueError(f"End cap must be from {END_MIN_FT:g} ft to {END_MAX_FT:g} ft.")
        if self.soldier_courses < 1 or self.soldier_courses % 2 == 0:
            raise ValueError("Soldier courses must be an odd number (1, 3, 5, …) so the band stays centered.")
        if self.soldier_edge_in < 0:
            raise ValueError("Soldier edge cannot be negative. Use 0 to place it from the end cap.")

    def lap_note(self) -> str:
        """Usual shop lap is 1 in or five times the thickness, whichever is larger."""
        usual = max(1.0, 5.0 * self.thickness_in)
        if self.lap_in + 1e-9 < usual:
            return f"Lap is under the usual {usual:g} in (1 in or 5× thickness)."
        return ""


@dataclass(frozen=True)
class FloorPlate:
    """One floor plate. ``polygon_in`` is the outline in plan (x, z), inches."""

    row: int
    row_k: int
    plate_no: int
    x0_in: float
    x1_in: float
    z0_in: float
    z1_in: float
    polygon_in: tuple[tuple[float, float], ...]

    @property
    def feature_name(self) -> str:
        return f"EliteFloorR{self.row:02d}P{self.plate_no:02d}"

    @property
    def sketch_name(self) -> str:
        return f"{self.feature_name}Sk"


def floor_rows(plates: list[FloorPlate]) -> list[list[FloorPlate]]:
    rows: list[list[FloorPlate]] = []
    for plate in plates:
        if not rows or rows[-1][0].row != plate.row:
            rows.append([plate])
        else:
            rows[-1].append(plate)
    return rows


def soldier_outer_edge(spec: FloorSpec) -> float:
    """Inches from center to the outer vertical edge of the last soldier plate."""
    _radius, _soldier, edge = _soldier_layout(spec)
    return edge


def layout_floor(spec: FloorSpec) -> list[FloorPlate]:
    """Shoulder plates only, in the SOLDIERPLATES order, then rotated as a group."""
    spec.validate()
    groups = _shoulder_row(spec)

    plates: list[FloorPlate] = []
    for row_number, stock in enumerate(groups, start=1):
        for plate_no, (row_k, z0, z1, x0, x1, polygon) in enumerate(stock, start=1):
            polygon = _rotate_poly(polygon, spec.rotation_deg)
            xs = [point[0] for point in polygon]
            zs = [point[1] for point in polygon]
            x0, x1 = min(xs), max(xs)
            z0, z1 = min(zs), max(zs)
            plates.append(
                FloorPlate(
                    row=row_number,
                    row_k=row_k,
                    plate_no=plate_no,
                    x0_in=x0,
                    x1_in=x1,
                    z0_in=z0,
                    z1_in=z1,
                    polygon_in=polygon,
                )
            )
    return plates


def _shoulder_row(spec: FloorSpec) -> list[list[tuple]]:
    """One soldier row: width across the centerline, length square to it."""
    width = spec.plate_width_in
    length = spec.max_length_in
    lap = spec.lap_in
    cx = spec.center_shift_in
    half = length / 2.0
    z0 = -half
    z1 = half
    radius = spec.diameter_in / 2.0
    limit = 0.0 if half >= radius - _EPS else math.sqrt(radius * radius - half * half)
    groups: list[list[tuple]] = []

    if spec.center == CENTER_SEAM:
        seam = cx + lap / 2.0
        right = (seam - lap, seam - lap + width)
        left = (seam - width, seam)
        rx1, rx2 = _advance_if_fits(right, limit, lap, width, True)
        lx1, lx2 = _advance_if_fits(left, limit, lap, width, False)
        _add_pair(groups, 1, z0, z1, right, left, limit)
    else:
        plate = (cx - width / 2.0, cx + width / 2.0)
        groups.append([(0, z0, z1, *_rect(plate[0], plate[1], z0, z1))])
        rx1, rx2 = plate[1] - lap, plate[1] - lap + width
        lx2, lx1 = plate[0] + lap, plate[0] + lap - width

    step = 2 if spec.center == CENTER_SEAM else 1
    for index in range(step, step + 500):
        right = (rx1, rx2)
        left = (lx1, lx2)
        if not _add_pair(groups, index, z0, z1, right, left, limit):
            break
        rx1, rx2 = rx2 - lap, rx2 - lap + width
        lx2, lx1 = lx1 + lap, lx1 + lap - width
    return groups


def _fits_plate(x0: float, x1: float, limit: float) -> bool:
    return max(abs(x0), abs(x1)) <= limit + 1e-6


def _advance_if_fits(span: tuple[float, float], limit: float, lap: float, width: float, right: bool):
    x0, x1 = span
    if not _fits_plate(x0, x1, limit):
        return x0, x1
    if right:
        return x1 - lap, x1 - lap + width
    return x0 + lap - width, x0 + lap


def _add_pair(groups, row_k: int, z0: float, z1: float, right: tuple[float, float], left: tuple[float, float], limit: float) -> bool:
    stock = []
    if _fits_plate(right[0], right[1], limit):
        stock.append((row_k, z0, z1, *_rect(right[0], right[1], z0, z1)))
    if _fits_plate(left[0], left[1], limit):
        stock.append((-row_k, z0, z1, *_rect(left[0], left[1], z0, z1)))
    if stock:
        groups.append(stock)
    return bool(stock)


def _soldier_layout(spec: FloorSpec) -> tuple[float, list[tuple[int, float, float]], float]:
    spec.validate()
    radius = spec.trim_radius_in()
    half = spec.soldier_courses // 2
    inside = []
    for band in _bands(spec, radius):
        row_k, z0, z1 = band
        if abs(row_k) <= half and abs(z0) <= radius + _EPS and abs(z1) <= radius + _EPS:
            inside.append(band)
    if len(inside) < spec.soldier_courses:
        raise ValueError(
            f"Only {len(inside)} soldier course(s) fit inside this diameter. "
            f"Lower the soldier courses or the plate width."
        )
    z_top = max(band[2] for band in inside)
    z_bot = min(band[1] for band in inside)
    x_top = _x_at(z_top, radius, True)
    x_bot = _x_at(z_bot, radius, True)
    if x_top is None or x_bot is None:
        raise ValueError("Soldier band does not sit inside the floor circle.")
    x_arc = min(x_top, x_bot)
    lap = spec.lap_in
    if spec.soldier_edge_in > _EPS:
        edge = spec.soldier_edge_in
        if edge + _EPS >= x_arc:
            raise ValueError("Soldier edge is outside the circle. Move it toward the center.")
        return radius, inside, edge
    high = x_arc - END_MIN_FT * 12.0
    low = max(x_arc - END_MAX_FT * 12.0, lap)
    if high <= lap:
        raise ValueError("Soldier band is too close to the shell for a side sketch.")
    x_inner = _clamp(x_arc - spec.end_long_ft * 12.0, low, high)
    return radius, inside, x_inner + lap


def _soldier_rects(spec: FloorSpec, z0: float, z1: float, edge: float) -> list[tuple]:
    length = spec.max_length_in
    lap = spec.lap_in
    step = length - lap if length - lap > _EPS else length
    right_base, left_base, center = _center_plates(spec.center, spec.center_shift_in, length, lap, z0, z1)
    if edge <= _EPS:
        return [item for item in center if _area(item[2]) >= _MIN_PLATE_AREA_SQIN]
    plates = center + _side_plates(right_base, left_base, length, lap, step, z0, z1, edge, -edge)
    trimmed = _trim_to_stops(plates, -edge, edge, lap, z0, z1)
    return [item for item in trimmed if _area(item[2]) >= _MIN_PLATE_AREA_SQIN]


def _side_sketches(z0: float, z1: float, edge: float, lap: float, radius: float) -> list[tuple]:
    """Left and right sketch plates on one soldier course. Both use the same vertical edge."""
    x_inner = edge - lap
    sketches = []
    for right in (False, True):
        x_use = x_inner if right else -x_inner
        x_bottom = _x_at(z0, radius, right)
        x_top = _x_at(z1, radius, right)
        if x_bottom is None or x_top is None:
            continue
        plate = _endcap_plate((x_use, x_bottom, x_top), z0, z1, radius, right=right)
        if plate is not None and _area(plate[2]) >= _MIN_PLATE_AREA_SQIN:
            sketches.append(plate)
    sketches.sort(key=lambda item: item[0])
    return sketches


def _tagged(row_k: int, z0: float, z1: float, stock: list) -> list[tuple]:
    return [(row_k, z0, z1, x0, x1, polygon) for x0, x1, polygon in stock]


def _add_group(groups: list, row_k: int, z0: float, z1: float, stock: list) -> None:
    tagged = _tagged(row_k, z0, z1, stock)
    if tagged:
        groups.append(tagged)


def _split_sketches(stock: list, radius: float) -> tuple[list, list]:
    rectangles: list = []
    sketches: list = []
    for item in stock:
        if _touches_circle(item[2], radius):
            sketches.append(item)
        else:
            rectangles.append(item)
    return rectangles, sketches


def _touches_circle(polygon, radius: float) -> bool:
    return any(abs(math.hypot(x, z) - radius) <= 0.2 for x, z in polygon)


def _finish_crescent(spec: FloorSpec, radius: float, y_inner: float, top: bool) -> list[tuple]:
    """Sketch plates from the last row out to the circle."""
    half = _x_at(y_inner, radius, True)
    if half is None or half <= _EPS:
        return []
    length = spec.max_length_in
    lap = spec.lap_in
    step = length - lap if length - lap > _EPS else length
    shift = spec.center_shift_in
    spans: list[tuple[float, float]] = []
    if spec.center == CENTER_SEAM:
        spans.append((shift + lap / 2.0 - length, shift + lap / 2.0))
        spans.append((shift - lap / 2.0, shift - lap / 2.0 + length))
        edge = shift - lap / 2.0 + length
        other = shift + lap / 2.0 - length
    else:
        spans.append((shift - length / 2.0, shift + length / 2.0))
        edge = shift + length / 2.0
        other = shift - length / 2.0
    x_left = edge - lap
    while x_left < half - _EPS:
        spans.append((x_left, x_left + length))
        x_left += step
        if len(spans) > 500:
            break
    x_right = other + lap
    while x_right > -half + _EPS:
        spans.append((x_right - length, x_right))
        x_right -= step
        if len(spans) > 500:
            break

    stock: list[tuple] = []
    seen: set[tuple[int, int]] = set()
    for x0, x1 in spans:
        nx0 = max(x0, -half)
        nx1 = min(x1, half)
        if nx1 - nx0 <= lap + _EPS:
            continue
        key = (round(nx0, 3), round(nx1, 3))
        if key in seen:
            continue
        seen.add(key)
        polygon = _sketch_cap(nx0, nx1, y_inner, radius, top)
        if polygon is None or _area(polygon) < _MIN_PLATE_AREA_SQIN:
            continue
        stock.append((nx0, nx1, polygon))
    stock.sort(key=lambda item: item[0])
    return stock


def _sketch_cap(x0: float, x1: float, y_inner: float, radius: float, top: bool):
    z0 = _z_at(x0, radius, top)
    z1 = _z_at(x1, radius, top)
    if z0 is None or z1 is None:
        return None
    if top and max(z0, z1) < y_inner - 0.05:
        return None
    if not top and min(z0, z1) > y_inner + 0.05:
        return None
    arc = _minor_arc(x1, z1, x0, z0, radius)
    return _clean([(x0, y_inner), (x1, y_inner), (x1, z1), *arc, (x0, z0)])


def _z_at(x: float, radius: float, top: bool) -> float | None:
    value = radius * radius - x * x
    if value < 0.0:
        if value >= -(2.0 * abs(radius) * _EPS + _EPS * _EPS):
            value = 0.0
        else:
            return None
    offset = math.sqrt(value)
    return offset if top else -offset


def _bands(spec: FloorSpec, radius: float) -> list[tuple[int, float, float]]:
    width = spec.plate_width_in
    pitch = width - spec.lap_in
    if pitch <= _EPS:
        raise ValueError("Lap must be smaller than the plate width.")
    k_max = 0
    while (k_max + 1) * pitch - width / 2.0 < radius:
        k_max += 1
        if k_max > 500:
            raise ValueError("Plate width is too small for this diameter.")
    bands: list[tuple[int, float, float]] = []
    for k in range(-k_max, k_max + 1):
        z0 = k * pitch - width / 2.0
        z1 = z0 + width
        if z1 <= -radius or z0 >= radius:
            continue
        bands.append((k, z0, z1))
    return bands


def _cap_row(spec: FloorSpec, radius: float, z0: float, z1: float) -> list[tuple]:
    """One SHCAPTOPROW row whose top and bottom both lie inside the circle."""
    length = spec.max_length_in
    lap = spec.lap_in
    step = length - lap if length - lap > _EPS else length
    shift = spec.center_shift_in
    x_left_min = max(_x_at(z0, radius, False), _x_at(z1, radius, False))
    x_right_max = min(_x_at(z0, radius, True), _x_at(z1, radius, True))
    right_base, left_base, center = _center_plates(spec.center, shift, length, lap, z0, z1)

    end_long = spec.end_long_ft * 12.0
    end_min = END_MIN_FT * 12.0
    end_max = END_MAX_FT * 12.0
    right_info = _end_right(radius, z0, z1, end_long, end_min, end_max)
    left_info = _end_left(radius, z0, z1, end_long, end_min, end_max)
    if spec.center == CENTER_SEAM and right_info is not None and left_info is not None:
        right_info, left_info = _align_endcaps(
            right_base, left_base, length, lap, step, right_info, left_info, radius, z0, z1, end_min, end_max
        )

    x_stop_r = right_info[0] + lap if right_info is not None else x_right_max
    x_stop_l = left_info[0] - lap if left_info is not None else x_left_min
    rectangles = _trim_to_stops(
        center + _side_plates(right_base, left_base, length, lap, step, z0, z1, x_stop_r, x_stop_l),
        x_stop_l,
        x_stop_r,
        lap,
        z0,
        z1,
    )
    ends: list[tuple] = []
    if right_info is not None:
        ends.append(_endcap_plate(right_info, z0, z1, radius, right=True))
    if left_info is not None:
        ends.append(_endcap_plate(left_info, z0, z1, radius, right=False))
    stock = [item for item in rectangles + ends if item is not None and _area(item[2]) >= _MIN_PLATE_AREA_SQIN]
    stock.sort(key=lambda item: item[0])
    return stock


def _center_plates(
    center: str,
    shift: float,
    length: float,
    lap: float,
    z0: float,
    z1: float,
) -> tuple[float, float, list[tuple]]:
    plates: list[tuple] = []
    if center == CENTER_SEAM:
        x_seam = shift + lap / 2.0
        x_lap = shift - lap / 2.0
        left = (x_seam - length, x_seam)
        right = (x_lap, x_lap + length)
        plates.append(_rect(left[0], left[1], z0, z1))
        plates.append(_rect(right[0], right[1], z0, z1))
        return right[1], left[0], plates
    x0 = shift - length / 2.0
    x1 = shift + length / 2.0
    plates.append(_rect(x0, x1, z0, z1))
    return x1, x0, plates


def _end_right(radius: float, z0: float, z1: float, end_long: float, end_min: float, end_max: float):
    x_bottom = _x_at(z0, radius, True)
    x_top = _x_at(z1, radius, True)
    if x_bottom is None or x_top is None:
        return None
    low = max(x_top - end_max, x_bottom - end_max)
    high = min(x_top - end_min, x_bottom - end_min)
    if low > high:
        low, high = high, low
    x_long = max(x_bottom, x_top)
    x_use = _clamp(x_long - end_long, low, high)
    return (x_use, x_bottom, x_top, low, high)


def _end_left(radius: float, z0: float, z1: float, end_long: float, end_min: float, end_max: float):
    x_bottom = _x_at(z0, radius, False)
    x_top = _x_at(z1, radius, False)
    if x_bottom is None or x_top is None:
        return None
    low = max(x_top + end_min, x_bottom + end_min)
    high = min(x_top + end_max, x_bottom + end_max)
    if low > high:
        low, high = high, low
    x_long = min(x_bottom, x_top)
    x_use = _clamp(x_long + end_long, low, high)
    return (x_use, x_bottom, x_top, low, high)


def _align_endcaps(right_base, left_base, length, lap, step, right_info, left_info, radius, z0, z1, end_min, end_max):
    """CL mode: move the end seam onto the plate grid when the 3–15 ft rule allows it."""
    x_use_r, x_rb, x_rt, low_r, high_r = right_info
    x_stop_r = x_use_r + lap
    x_r0 = (right_base - lap) + length
    n_lo = _lisp_ceil((low_r + lap - x_r0) / step)
    n_hi = _lisp_floor((high_r + lap - x_r0) / step)
    n = _clamp(_lisp_round((x_stop_r - x_r0) / step), n_lo, n_hi)
    desired = x_r0 + n * step
    if abs(desired - x_stop_r) > _EPS:
        end_long = _clamp(max(x_rb, x_rt) - (desired - lap), end_min, end_max)
        updated = _end_right(radius, z0, z1, end_long, end_min, end_max)
        if updated is not None:
            right_info = updated

    x_use_l, x_lb, x_lt, low_l, high_l = left_info
    x_stop_l = x_use_l - lap
    x_l0 = (left_base + lap) - length
    n_lo = _lisp_ceil((x_l0 - (high_l - lap)) / step)
    n_hi = _lisp_floor((x_l0 - (low_l - lap)) / step)
    n = _clamp(_lisp_round((x_l0 - x_stop_l) / step), n_lo, n_hi)
    desired = x_l0 - n * step
    if abs(desired - x_stop_l) > _EPS:
        end_long = _clamp((desired + lap) - min(x_lb, x_lt), end_min, end_max)
        updated = _end_left(radius, z0, z1, end_long, end_min, end_max)
        if updated is not None:
            left_info = updated
    return right_info, left_info


def _trim_to_stops(plates: list[tuple], x_stop_l: float, x_stop_r: float, lap: float, z0: float, z1: float) -> list[tuple]:
    """Keep rectangle plates between the end seams, lapping each end plate by the lap.

    A plate longer than that opening is trimmed. That is the row where a full
    center plate does not fit and the AutoLISP command would otherwise leave
    the middle empty.
    """
    trimmed: list[tuple] = []
    for x0, x1, polygon in plates:
        nx0 = max(x0, x_stop_l)
        nx1 = min(x1, x_stop_r)
        if nx1 - nx0 <= lap + _EPS:
            continue
        if abs(nx0 - x0) <= _EPS and abs(nx1 - x1) <= _EPS:
            trimmed.append((x0, x1, polygon))
        else:
            trimmed.append(_rect(nx0, nx1, z0, z1))
    return trimmed


def _side_plates(right_base, left_base, length, lap, step, z0, z1, x_stop_r, x_stop_l) -> list[tuple]:
    plates: list[tuple] = []
    index = 0
    while True:
        x_left = right_base - lap + index * step
        x_right = x_left + length
        if x_right <= x_stop_r + _EPS:
            plates.append(_rect(x_left, x_right, z0, z1))
            if abs(x_right - x_stop_r) <= _EPS:
                break
            index += 1
            continue
        if x_left < x_stop_r and x_stop_r - x_left > lap + _EPS:
            width = x_stop_r - x_left
            if abs(width - length) <= _FULL_TOL:
                plates.append(_rect(x_left, x_left + length, z0, z1))
            else:
                plates.append(_rect(x_left, x_stop_r, z0, z1))
        break

    index = 0
    while True:
        x_right = left_base + lap - index * step
        x_left = x_right - length
        if x_left >= x_stop_l - _EPS:
            plates.append(_rect(x_left, x_right, z0, z1))
            if abs(x_left - x_stop_l) <= _EPS:
                break
            index += 1
            continue
        if x_right > x_stop_l and x_right - x_stop_l > lap + _EPS:
            width = x_right - x_stop_l
            if abs(width - length) <= _FULL_TOL:
                plates.append(_rect(x_right - length, x_right, z0, z1))
            else:
                plates.append(_rect(x_stop_l, x_right, z0, z1))
        break
    return plates


def _clipped_row(spec: FloorSpec, radius: float, z0: float, z1: float) -> list[tuple]:
    """Top or bottom row that crosses the circle. Rectangles are cut to the arc."""
    length = spec.max_length_in
    lap = spec.lap_in
    step = length - lap if length - lap > _EPS else length
    shift = spec.center_shift_in
    circle = _circle_points(radius, ARC_STEP_DEG)
    if spec.center == CENTER_SEAM:
        origins = [shift + lap / 2.0 - length, shift - lap / 2.0]
        reach = max(radius + length, length)
    else:
        origins = [shift - length / 2.0]
        reach = max(radius + length, length)
    spans: list[tuple[float, float]] = []
    for origin in origins:
        x_left = origin
        while x_left > -reach:
            x_left -= step
        x_left += step
        while x_left < reach:
            spans.append((x_left, x_left + length))
            x_left += step
    stock: list[tuple] = []
    seen: set[tuple[int, int]] = set()
    for x0, x1 in spans:
        key = (round(x0, 4), round(x1, 4))
        if key in seen:
            continue
        seen.add(key)
        polygon = _clip_circle_to_rect(circle, x0, x1, z0, z1)
        polygon = _clean(polygon)
        if _area(polygon) < _MIN_PLATE_AREA_SQIN:
            continue
        xs = [point[0] for point in polygon]
        stock.append((min(xs), max(xs), polygon))
    stock.sort(key=lambda item: item[0])
    return stock


def _endcap_plate(info, z0: float, z1: float, radius: float, *, right: bool):
    x_use, x_bottom, x_top = info[0], info[1], info[2]
    if right and x_use >= min(x_bottom, x_top) - _EPS:
        return None
    if not right and x_use <= max(x_bottom, x_top) + _EPS:
        return None
    arc = _minor_arc(x_bottom, z0, x_top, z1, radius)
    if right:
        polygon = _clean([(x_use, z0), (x_bottom, z0), *arc, (x_top, z1), (x_use, z1)])
        return (x_use, max(x_bottom, x_top), polygon)
    polygon = _clean([(x_use, z0), (x_bottom, z0), *arc, (x_top, z1), (x_use, z1)])
    return (min(x_bottom, x_top), x_use, polygon)


def _rect(x0: float, x1: float, z0: float, z1: float) -> tuple:
    if x1 < x0:
        x0, x1 = x1, x0
    return (x0, x1, ((x0, z0), (x1, z0), (x1, z1), (x0, z1)))


def _x_at(z: float, radius: float, right: bool) -> float | None:
    value = radius * radius - z * z
    if value < 0.0:
        if value >= -(2.0 * abs(radius) * _EPS + _EPS * _EPS):
            value = 0.0
        else:
            return None
    offset = math.sqrt(value)
    return offset if right else -offset


def _minor_arc(x0: float, z0: float, x1: float, z1: float, radius: float) -> list[tuple[float, float]]:
    start = math.atan2(z0, x0)
    end = math.atan2(z1, x1)
    delta = (end - start + math.pi) % (2.0 * math.pi) - math.pi
    if abs(delta) < 1e-9:
        return []
    steps = max(1, int(round(abs(math.degrees(delta)) / ARC_STEP_DEG)))
    points = []
    for index in range(1, steps):
        angle = start + delta * index / steps
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def _rotate_poly(polygon, degrees: float) -> tuple[tuple[float, float], ...]:
    if abs(degrees) < 1e-9:
        return tuple(polygon)
    angle = math.radians(degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return tuple((x * cosine - z * sine, x * sine + z * cosine) for x, z in polygon)


def _clamp(value: float, low: float, high: float) -> float:
    if low > high:
        low, high = high, low
    return min(max(value, low), high)


def _lisp_floor(value: float) -> int:
    whole = int(value)
    if value >= 0.0 or value == whole:
        return whole
    return whole - 1


def _lisp_ceil(value: float) -> int:
    whole = int(value)
    if value <= 0.0 or value == whole:
        return whole
    return whole + 1


def _lisp_round(value: float) -> int:
    if value >= 0.0:
        return int(value + 0.5)
    return int(value - 0.5)


def _circle_points(radius: float, step_deg: float) -> list[tuple[float, float]]:
    count = max(12, int(round(360.0 / step_deg)))
    points = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def _clip_circle_to_rect(
    circle: list[tuple[float, float]],
    x0: float,
    x1: float,
    z0: float,
    z1: float,
) -> list[tuple[float, float]]:
    polygon = circle
    polygon = _clip_halfplane(polygon, lambda point: point[0] >= x0 - 1e-8, lambda a, b: _hit_vertical(a, b, x0))
    polygon = _clip_halfplane(polygon, lambda point: point[0] <= x1 + 1e-8, lambda a, b: _hit_vertical(a, b, x1))
    polygon = _clip_halfplane(polygon, lambda point: point[1] >= z0 - 1e-8, lambda a, b: _hit_horizontal(a, b, z0))
    polygon = _clip_halfplane(polygon, lambda point: point[1] <= z1 + 1e-8, lambda a, b: _hit_horizontal(a, b, z1))
    return polygon


def _clip_halfplane(polygon, keep, intersect) -> list[tuple[float, float]]:
    if not polygon:
        return []
    output: list[tuple[float, float]] = []
    previous = polygon[-1]
    previous_inside = keep(previous)
    for current in polygon:
        current_inside = keep(current)
        if current_inside:
            if not previous_inside:
                output.append(intersect(previous, current))
            output.append(current)
        elif previous_inside:
            output.append(intersect(previous, current))
        previous = current
        previous_inside = current_inside
    return output


def _hit_vertical(start, end, x: float) -> tuple[float, float]:
    dx = end[0] - start[0]
    if abs(dx) < 1e-15:
        return (x, start[1])
    t = (x - start[0]) / dx
    return (x, start[1] + t * (end[1] - start[1]))


def _hit_horizontal(start, end, z: float) -> tuple[float, float]:
    dz = end[1] - start[1]
    if abs(dz) < 1e-15:
        return (start[0], z)
    t = (z - start[1]) / dz
    return (start[0] + t * (end[0] - start[0]), z)


def _clean(points: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    cleaned: list[tuple[float, float]] = []
    for x, z in points:
        if cleaned and math.hypot(x - cleaned[-1][0], z - cleaned[-1][1]) < 0.02:
            continue
        cleaned.append((float(x), float(z)))
    if len(cleaned) >= 2 and math.hypot(cleaned[0][0] - cleaned[-1][0], cleaned[0][1] - cleaned[-1][1]) < 0.02:
        cleaned.pop()
    return tuple(cleaned)


def _area(polygon: tuple[tuple[float, float], ...] | list[tuple[float, float]]) -> float:
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    x0, z0 = polygon[-1]
    for x1, z1 in polygon:
        total += x0 * z1 - x1 * z0
        x0, z0 = x1, z1
    return abs(total) * 0.5
