"""Build FTCOs on the tank part, in place: insert plate, repad, neck, flange, gasket, cover, bottom plate.

The shell must already be built with course 1 open for each insert plate
(``swauto.cleanout.layout.course_one_gaps``). Every flat piece is sketched on a
plane through its own middle and extruded half its thickness each way, so no
piece depends on which way a plane faces. Curved pieces are revolved about the
tank axis like the shell plates, and trimmed with combine.

Local frame of one FTCO, inches: ``s`` out along its centerline from the tank
axis, ``x`` to the right looking at the shell from outside, ``y`` up from the
bottom of course 1 — the "stretchout" view the LISP outlines are drawn in.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from swauto.cleanout.spec import (
    BASEPLATE_PAST_INSERT_IN,
    BOLT_HOLE_DIA_IN,
    FLANGE_HALF_WIDTH_IN,
    INSERT_TO_NECK_GAP_IN,
    LUG_BASE_HALF_IN,
    LUG_HOLE_DIA_IN,
    LUG_HOLE_RISE_IN,
    LUG_RISE_IN,
    LUG_TOP_HALF_IN,
    NECK_PAST_REPAD_IN,
    OPENING_WIDTH_IN,
    PIECES,
    REPAD_TO_NECK_GAP_IN,
    TELLTALE_DIA_IN,
    Cleanout,
    azimuth_rad,
)
from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.features import iter_features
from swauto.nozzle.nozzle_sw import (
    _body_with_feature,
    _close_sketch,
    _delete_feature,
    _drew,
    _extrude_both,
    _extrude_cut_both,
    _latest,
    _open_on,
    _plane_on_shell,
    _start_sketch,
    _swallow,
    _to_sketch,
)
from swauto.params import rebuild, rename_feature
from swauto.parts import extrude_blind, select_plane
from swauto.tank.plates import PlateSector, developed_circumference_in
from swauto.tank.profile import course_radii_m
from swauto.tank.shell import _blank_reference, _build_one_plate, _ensure_tank_axis
from swauto.tank.spec import TankSpec

_INCH = 0.0254
PREFIX = "EliteFtco"
_SWBODYINTERSECT = 15901
_SWBODYCUT = 15902
_ARC_STEPS = 36  # repad corner arcs, drawn as short lines so they wrap onto the shell


@dataclass(frozen=True)
class _Named(PlateSector):
    """A shell-plate revolve under an FTCO feature name."""

    name: str = ""

    @property
    def feature_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class _Frame:
    phi: float  # orientation, radians: 0 is +Z, toward -X
    r_mid: float  # course-1 mid-wall radius, inches; the development radius
    height: float  # course 1

    @property
    def radial(self) -> tuple[float, float, float]:
        return (-math.sin(self.phi), 0.0, math.cos(self.phi))

    @property
    def right(self) -> tuple[float, float, float]:
        """To the right, looking at the shell from outside."""
        return (math.cos(self.phi), 0.0, math.sin(self.phi))

    def world(self, x: float, y: float, s: float) -> tuple[float, float, float]:
        """Model point, inches."""
        r, t = self.radial, self.right
        return (s * r[0] + x * t[0], y, s * r[2] + x * t[2])

    # Paper +x is toward smaller azimuth, so a frame turned to sit at x has phi - x / r_mid.

    def wrapped(self, x: float, s: float) -> float:
        """The straight offset that lands ``x`` of developed length along the shell at radius ``s``."""
        return s * math.sin(x / self.r_mid)


def add_cleanouts(model, spec: TankSpec, cleanouts: Sequence[Cleanout]) -> str:
    """Rebuild every FTCO on ``model``. Earlier FTCO features are removed first."""
    if model is None:
        raise SolidWorksError("Create the tank shell in SolidWorks first.")
    if not cleanouts:
        raise SolidWorksError("Add an FTCO to the list first.")
    delete_cleanouts(model)
    rebuild(model)
    course = spec.active_courses()[0]
    outer_m, inner_m = course_radii_m(spec, course)
    r_mid = (outer_m + inner_m) / 2.0 / _INCH
    circumference = developed_circumference_in(spec, course)
    done = []
    for cleanout in cleanouts:
        frame = _Frame(phi=math.radians(cleanout.orientation_deg), r_mid=r_mid, height=course.height_in)
        try:
            _build_one(model, cleanout, frame, outer_m / _INCH, circumference)
        except SolidWorksError:
            raise
        except Exception as exc:
            raise SolidWorksError(f"{cleanout.mark} failed: {format_com_error(exc)}") from exc
        done.append(cleanout.mark)
    rebuild(model)
    return "FTCO on the shell: " + ", ".join(done) + "."


def delete_cleanouts(model) -> None:
    """Remove every FTCO feature, and the gasket properties the last build listed."""
    named = [feature for feature in iter_features(model) if str(com_value(feature.Name) or "").startswith(PREFIX)]
    for feature in reversed(named):
        _delete_feature(model, feature)
    with _swallow():
        manager = model.Extension.CustomPropertyManager("")
        for name in com_value(manager.GetNames) or ():
            if str(name).startswith("FTCO ") and str(name).endswith(" gasket"):
                manager.Delete(str(name))


def _build_one(model, cleanout: Cleanout, frame: _Frame, shell_outside: float, circumference: float) -> None:
    tag = tag_of(cleanout)
    axis = _ensure_tank_axis(model)
    for piece in PIECES:
        build_piece(model, cleanout, piece, frame, shell_outside, axis)
    _finish(model, cleanout, tag)


def tag_of(cleanout: Cleanout) -> str:
    return PREFIX + "".join(ch for ch in cleanout.mark if ch.isalnum())


def build_piece(model, cleanout: Cleanout, piece: str, frame: _Frame, shell_outside: float, axis) -> None:
    """One FTCO piece into ``model``, in place on the tank: one of ``PIECES``. ``axis`` is the tank axis."""
    tag = tag_of(cleanout)
    dims = cleanout.dims
    insert_in = frame.r_mid - cleanout.insert_thk_in / 2.0
    insert_out = frame.r_mid + cleanout.insert_thk_in / 2.0
    repad_out = insert_out + cleanout.repad_thk_in
    flange_back = repad_out + NECK_PAST_REPAD_IN
    center = azimuth_rad(cleanout.orientation_deg)

    if piece == "Insert":
        # Course 1 between its seams, centered on the mid-wall, opening cut through.
        half = dims.insert_length_in / 2.0 / frame.r_mid
        _sector(model, axis, f"{tag}Insert", center, half, insert_in, insert_out, 0.0, frame.height)
        _arch_cut(model, frame, cleanout, frame.r_mid, cleanout.neck_od_half_in + INSERT_TO_NECK_GAP_IN,
                  cleanout.insert_thk_in, f"{tag}InsertOpening", f"{tag}Insert")
    elif piece == "Repad":
        # A band on the insert, cut to the outline wrapped onto the shell, then opened and drilled.
        repad_mid = insert_out + cleanout.repad_thk_in / 2.0
        band_half = (dims.repad_half_in + 2.0) / frame.r_mid
        _sector(model, axis, f"{tag}RepadBand", center, band_half, insert_out, repad_out, 0.0,
                dims.repad_top_in + 1.0)
        _repad_outline(model, frame, cleanout, repad_mid, f"{tag}RepadKeep")
        _common(model, f"{tag}RepadBand", f"{tag}RepadKeep", f"{tag}Repad")
        _arch_cut(model, frame, cleanout, repad_mid, cleanout.neck_od_half_in + REPAD_TO_NECK_GAP_IN,
                  cleanout.repad_thk_in, f"{tag}RepadOpening", f"{tag}Repad")
        # The telltale goes square through the plate where it is, so it is sketched on the shell there.
        tx, ty = dims.telltale
        at_telltale = _Frame(phi=frame.phi - tx / frame.r_mid, r_mid=frame.r_mid, height=frame.height)
        _hole_cut(model, at_telltale, repad_mid, [(0.0, ty)], TELLTALE_DIA_IN,
                  cleanout.repad_thk_in / 2.0 + 0.5, f"{tag}Telltale", f"{tag}Repad")
    elif piece == "Neck":
        # The opening's walls and arch, from past the insert's inside face out to the flange; trimmed
        # back to the insert's inside face.
        start = insert_in - 3.0
        neck_mid = (start + flange_back) / 2.0
        _flat(model, frame, neck_mid, (flange_back - start) / 2.0, _neck_outline(cleanout), f"{tag}NeckRaw")
        span = (cleanout.neck_od_half_in + 3.0) / frame.r_mid
        _sector(model, axis, f"{tag}NeckTrim", center, span, 1.0, insert_in, -1.0, dims.opening_height_in + 2.0)
        _subtract(model, f"{tag}NeckRaw", f"{tag}NeckTrim", f"{tag}Neck")
    elif piece in ("Flange", "Gasket", "Cover"):
        # Stacked out from the neck end, each with the bolt holes: flange, full-face gasket, cover.
        holes = [((x, y), BOLT_HOLE_DIA_IN / 2.0) for x, y in dims.bolt_holes]
        s = flange_back
        for name, thk, loops in (
            ("Flange", cleanout.flange_thk_in, [_flange_outer(cleanout), _neck_od_closed(cleanout)]),
            ("Gasket", cleanout.gasket_thk_in, [_flange_outer(cleanout), _neck_od_closed(cleanout)]),
            ("Cover", cleanout.cover_thk_in, [_cover_outer(cleanout)]),
        ):
            if name == piece:
                circles = holes + ([((0.0, dims.arch_center_in + LUG_HOLE_RISE_IN), LUG_HOLE_DIA_IN / 2.0)]
                                   if name == "Cover" else [])
                _flat(model, frame, s + thk / 2.0, thk / 2.0, loops, f"{tag}{name}", circles)
                break
            s += thk
    elif piece == "BottomPlate":
        _bottom_plate(model, frame, cleanout, center, shell_outside, flange_back, f"{tag}BottomPlate")
    else:
        raise SolidWorksError(f"{cleanout.mark}: no FTCO piece called {piece!r}.")


def hide_planes(model, tag: str) -> None:
    """The reference planes the pieces were sketched on, out of sight."""
    for feature in list(iter_features(model)):
        name = str(com_value(feature.Name) or "")
        if name.startswith(tag) and str(com_value(feature.GetTypeName2) or "") == "RefPlane":
            _blank_reference(model, feature, name, "PLANE")


def _finish(model, cleanout: Cleanout, tag: str) -> None:
    """Hide the planes, name the bodies for the Solid Bodies folder, and list the gasket for the BOM."""
    hide_planes(model, tag)
    gasket =f"Gasket - {cleanout.gasket_material}" if cleanout.gasket_material else "Gasket"
    for feature, label in (
        ("Insert", "Insert plate"), ("Repad", "Repad"), ("Neck", "Neck"), ("Flange", "Flange"),
        ("Gasket", gasket), ("Cover", "Cover"), ("BottomPlate", "Bottom plate"),
    ):
        body = _body_with_feature(model, f"{tag}{feature}")
        if body is not None:
            with _swallow():
                body.Name = f"{cleanout.mark} {label}"
    if cleanout.gasket_material:
        with _swallow():
            manager = model.Extension.CustomPropertyManager("")
            name = f"FTCO {cleanout.mark} gasket"
            value = (f"{cleanout.size} FTCO full-face gasket, {cleanout.gasket_material}, "
                     f"{cleanout.gasket_thk_in:g} in")
            manager.Add2(name, 30, value)  # 30 is swCustomInfoText
            manager.Set(name, value)
    with _swallow():
        model.GraphicsRedraw2()


# ------------------------------------------------------------------ pieces


def _sector(model, axis, name: str, center: float, half: float, r_in: float, r_out: float, y0: float, y1: float):
    """A curved solid about the tank axis, ``center`` +- ``half`` radians, built like a shell plate."""
    plate = _Named(
        course_no=1, plate_no=0, start_rad=(center - half) % (2.0 * math.pi), sweep_rad=2.0 * half,
        z_bot_m=y0 * _INCH, height_m=(y1 - y0) * _INCH, outer_r_m=r_out * _INCH, inner_r_m=r_in * _INCH,
        length_in=0.0, name=name,
    )
    warning = _build_one_plate(model, plate, axis)
    if _body_with_feature(model, name) is None:
        raise SolidWorksError(f"{name}: the curved plate was not built. {warning or ''}".strip())


def _arch_cut(model, frame: _Frame, cleanout: Cleanout, s: float, radius: float, thk: float, name: str,
              scope: str) -> None:
    """The arched opening through one curved plate: half circle on straight sides to below the course bottom."""
    arch = cleanout.dims.arch_center_in
    loop = _arch_loop(radius, arch, -2.0)
    reach = thk / 2.0 + _sag(s, radius) + 0.5
    sketch = _sketch(model, frame, s, [loop], [], f"{name}Sk")
    _extrude_cut_both(model, sketch, reach * _INCH, reach * _INCH, name, scope)


def _hole_cut(model, frame: _Frame, s: float, centers, dia: float, reach: float, name: str, scope: str) -> None:
    sketch = _sketch(model, frame, s, [], [(c, dia / 2.0) for c in centers], f"{name}Sk")
    _extrude_cut_both(model, sketch, reach * _INCH, reach * _INCH, name, scope)


def _repad_outline(model, frame: _Frame, cleanout: Cleanout, s: float, name: str) -> None:
    """A solid through the repad band in the repad's outline, every point wrapped onto the shell."""
    dims = cleanout.dims
    cx, cy, r = dims.repad_corner_x_in, dims.repad_corner_y_in, dims.repad_corner_r_in
    pts = [(-dims.repad_half_in, -2.0), (dims.repad_half_in, -2.0)]
    for k in range(_ARC_STEPS + 1):  # right corner, 0 to 90 degrees
        a = math.pi / 2.0 * k / _ARC_STEPS
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    for k in range(_ARC_STEPS + 1):  # left corner, 90 to 180 degrees
        a = math.pi / 2.0 + math.pi / 2.0 * k / _ARC_STEPS
        pts.append((-cx + r * math.cos(a), cy + r * math.sin(a)))
    wrapped = [(frame.wrapped(x, s), y) for x, y in pts]
    loop = [("line", wrapped[i], wrapped[(i + 1) % len(wrapped)]) for i in range(len(wrapped))]
    reach = cleanout.repad_thk_in / 2.0 + _sag(s, dims.repad_half_in) + 1.0
    _flat(model, frame, s, reach, [loop], name)


def _bottom_plate(model, frame: _Frame, cleanout: Cleanout, center: float, shell_outside: float,
                  flange_back: float, name: str) -> None:
    """Bottom reinforcing plate under course 1 (FTCO Engine FE:draw-ftco-baseplate-outline).

    Runs 6 in past each insert end, from the chime in by the annular width, and out under the
    neck to the flange's back face. Top at the course bottom.
    """
    dims = cleanout.dims
    half = (dims.insert_length_in / 2.0 + BASEPLATE_PAST_INSERT_IN) / frame.r_mid
    outer = shell_outside + cleanout.chime_in
    inner = outer - cleanout.annular_width_in
    a0, a1 = center - half, center + half

    def polar(a: float, r: float) -> tuple[float, float, float]:
        return (r * math.cos(a), 0.0, r * math.sin(a))

    # Azimuth grows to the left looking from outside, so the a0 end meets the flange's right corner.
    fl_a = frame.world(FLANGE_HALF_WIDTH_IN, 0.0, flange_back)
    fl_b = frame.world(-FLANGE_HALF_WIDTH_IN, 0.0, flange_back)
    mid = (a0 + a1) / 2.0
    outline = [
        ("line", polar(a0, inner), polar(a0, outer)),
        ("line", polar(a0, outer), fl_a),
        ("line", fl_a, fl_b),
        ("line", fl_b, polar(a1, outer)),
        ("line", polar(a1, outer), polar(a1, inner)),
        ("arc", polar(a1, inner), polar(a0, inner), polar(mid, inner)),
    ]
    model.ClearSelection2(True)
    if not select_plane(model, "Top Plane"):
        raise SolidWorksError(f"{name}: could not select the Top plane.")
    sketch = _sketch_world(model, [outline], [], f"{name}Sk")
    thk = cleanout.baseplate_thk_in
    feature = None
    # Reverse sends a Top-plane sketch down (parts.extrude_blind); the other way is the fallback.
    for reverse in (True, False):
        model.ClearSelection2(True)
        sketch.Select2(False, 0)
        feature = extrude_blind(model.FeatureManager, thk * _INCH, merge=False, reverse=reverse)
        rebuild(model)
        body = _body_with_feature(model, str(com_value(feature.Name) or "")) if feature is not None else None
        box = [float(v) for v in body.GetBodyBox()] if body is not None else None
        if box is not None and box[4] < 1e-6:  # top at the course bottom: it went down
            break
        # Delete the extrude only; the default delete takes the absorbed sketch with it.
        model.ClearSelection2(True)
        feature.Select2(False, 0)
        model.Extension.DeleteSelection2(0)
        feature = None
    if feature is None:
        raise SolidWorksError(f"{name}: the plate did not go under the shell.")
    rename_feature(feature, name)
    if cleanout.annular_thk_in > 0.0:
        for side, a in ((1.0, a0), (-1.0, a1)):
            _bevel_end(model, frame, cleanout, a, side, inner, outer, f"{name}Bevel{'A' if side > 0 else 'B'}", name)


def _bevel_end(model, frame: _Frame, cleanout: Cleanout, a: float, inward: float, inner: float, outer: float,
               name: str, scope: str) -> None:
    """Step the plate's end down to the annular thickness (SPE:draw-ftco-baseplate-pad-at-offset).

    The top drops by the annular thickness over the last 1-1/4 in, with a 45 degree chamfer.
    ``inward`` is +1 when the plate lies at larger azimuth from this end.
    """
    ann = cleanout.annular_thk_in
    run = 1.25
    end = _Frame(phi=a - math.pi / 2.0, r_mid=frame.r_mid, height=frame.height)
    # Looking from outside, larger azimuth is to the left (-x).
    sign = -inward
    notch = [(-1.0, -ann), (run - ann, -ann), (run, 0.0), (run, 1.0), (-1.0, 1.0)]
    pts = [(sign * u, v) for u, v in notch]
    loop = [("line", pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    s = (inner + outer) / 2.0
    sketch = _sketch(model, end, s, [loop], [], f"{name}Sk")
    reach = (outer - inner) / 2.0 + 40.0
    _extrude_cut_both(model, sketch, reach * _INCH, reach * _INCH, name, scope)


# ------------------------------------------------------------------ outlines (stretchout, inches)


def _arch_loop(radius: float, arch: float, bottom: float) -> list:
    return [
        ("line", (-radius, bottom), (radius, bottom)),
        ("line", (radius, bottom), (radius, arch)),
        ("arc", (radius, arch), (-radius, arch), (0.0, arch + radius)),
        ("line", (-radius, arch), (-radius, bottom)),
    ]


def _neck_outline(cleanout: Cleanout) -> list:
    """The neck's cross-section: an inverted U, its legs ending at the course bottom."""
    arch = cleanout.dims.arch_center_in
    ri = OPENING_WIDTH_IN / 2.0
    ro = cleanout.neck_od_half_in
    return [[
        ("line", (ro, 0.0), (ro, arch)),
        ("arc", (ro, arch), (-ro, arch), (0.0, arch + ro)),
        ("line", (-ro, arch), (-ro, 0.0)),
        ("line", (-ro, 0.0), (-ri, 0.0)),
        ("line", (-ri, 0.0), (-ri, arch)),
        ("arc", (-ri, arch), (ri, arch), (0.0, arch + ri)),
        ("line", (ri, arch), (ri, 0.0)),
        ("line", (ri, 0.0), (ro, 0.0)),
    ]]


def _neck_od_closed(cleanout: Cleanout) -> list:
    """The flange's opening: the neck's outside, closed along the course bottom."""
    return _arch_loop(cleanout.neck_od_half_in, cleanout.dims.arch_center_in, 0.0)


def _flange_outer(cleanout: Cleanout) -> list:
    dims = cleanout.dims
    r, arch, bottom = FLANGE_HALF_WIDTH_IN, dims.arch_center_in, dims.flange_bottom_in
    return _arch_loop(r, arch, bottom)


def _cover_outer(cleanout: Cleanout) -> list:
    """The flange outline with the lifting lug on top of the arch (FTCO Cover Items)."""
    dims = cleanout.dims
    r, arch, bottom = FLANGE_HALF_WIDTH_IN, dims.arch_center_in, dims.flange_bottom_in
    base_y = arch + math.sqrt(r * r - LUG_BASE_HALF_IN**2)
    top_y = arch + LUG_RISE_IN

    def mid_arc(a0: float, a1: float) -> tuple[float, float]:
        m = (a0 + a1) / 2.0
        return (r * math.cos(m), arch + r * math.sin(m))

    right_a = math.atan2(base_y - arch, LUG_BASE_HALF_IN)
    left_a = math.pi - right_a
    return [
        ("line", (-r, bottom), (r, bottom)),
        ("line", (r, bottom), (r, arch)),
        ("arc", (r, arch), (LUG_BASE_HALF_IN, base_y), mid_arc(0.0, right_a)),
        ("line", (LUG_BASE_HALF_IN, base_y), (LUG_TOP_HALF_IN, top_y)),
        ("line", (LUG_TOP_HALF_IN, top_y), (-LUG_TOP_HALF_IN, top_y)),
        ("line", (-LUG_TOP_HALF_IN, top_y), (-LUG_BASE_HALF_IN, base_y)),
        ("arc", (-LUG_BASE_HALF_IN, base_y), (-r, arch), mid_arc(left_a, math.pi)),
        ("line", (-r, arch), (-r, bottom)),
    ]


# ------------------------------------------------------------------ sketching and combining


def _flat(model, frame: _Frame, s: float, half_thk: float, loops, name: str, circles=()) -> None:
    """A flat piece: ``loops`` and ``circles`` on the plane ``s`` out, extruded ``half_thk`` each way."""
    sketch = _sketch(model, frame, s, loops, circles, f"{name}Sk")
    _extrude_both(model, sketch, half_thk * _INCH, half_thk * _INCH, name)
    rebuild(model)
    if _body_with_feature(model, name) is None:
        raise SolidWorksError(f"{name}: the piece was not built.")


def _sketch(model, frame: _Frame, s: float, loops, circles, name: str):
    """Sketch on the plane square to the FTCO centerline, ``s`` out. Points are (x, y) in the frame."""
    plane = _plane_on_shell(
        model, frame.phi, s * _INCH, tuple(v * _INCH for v in frame.world(0.0, 0.0, s)), frame.radial, f"{name}Pln"
    )
    _open_on(model, plane)

    def lift(p):
        return frame.world(p[0], p[1], s)

    world_loops = [[(kind, *[lift(p) for p in pts]) for kind, *pts in loop] for loop in loops]
    world_circles = [(lift(c), r) for c, r in circles]
    return _draw(model, world_loops, world_circles, name)


def _sketch_world(model, loops, circles, name: str):
    """Sketch on the plane already selected; points are model inches."""
    _start_sketch(model)
    return _draw(model, loops, circles, name)


def _draw(model, loops, circles, name: str):
    manager = model.SketchManager
    try:
        transform = com_value(com_value(model.GetActiveSketch2).ModelToSketchTransform)
        data = [float(v) for v in com_value(transform.ArrayData)]
    except Exception as exc:
        _close_sketch(model)
        raise SolidWorksError(f"{name}: could not read the sketch plane ({format_com_error(exc)}).") from exc

    def at(p):
        x, y, z = _to_sketch(data, [v * _INCH for v in p])
        if abs(z) > 0.01 * _INCH:
            raise SolidWorksError(f"{name}: a point is {z / _INCH:.3f} in off the sketch plane.")
        return x, y

    try:
        for loop in loops:
            for kind, *pts in loop:
                if kind == "line":
                    (ax, ay), (bx, by) = at(pts[0]), at(pts[1])
                    ok = _drew(model, lambda ax=ax, ay=ay, bx=bx, by=by: manager.CreateLine(ax, ay, 0.0, bx, by, 0.0))
                else:
                    (ax, ay), (bx, by), (mx, my) = at(pts[0]), at(pts[1]), at(pts[2])
                    ok = _drew(model, lambda ax=ax, ay=ay, bx=bx, by=by, mx=mx, my=my: manager.Create3PointArc(
                        ax, ay, 0.0, bx, by, 0.0, mx, my, 0.0))
                if not ok:
                    raise SolidWorksError(f"{name}: an edge did not draw.")
        for c, r in circles:
            cx, cy = at(c)
            if not _drew(model, lambda cx=cx, cy=cy, r=r: manager.CreateCircleByRadius(cx, cy, 0.0, r * _INCH)):
                raise SolidWorksError(f"{name}: a hole did not draw.")
    except Exception:
        _close_sketch(model)
        raise
    _close_sketch(model)
    feature = _latest(model)
    rename_feature(feature, name)
    return feature


def _select_bodies(model, picks) -> None:
    model.ClearSelection2(True)
    data = model.SelectionManager.CreateSelectData
    for index, (feature, mark) in enumerate(picks):
        body = _body_with_feature(model, feature)
        if body is None:
            raise SolidWorksError(f"{feature}: the body is missing.")
        data.Mark = mark
        if not body.Select2(index > 0, data):
            raise SolidWorksError(f"{feature}: could not select the body.")


def _combine(model, op: int, picks, name: str) -> None:
    rebuild(model)
    _select_bodies(model, picks)
    import pythoncom
    from win32com.client import VARIANT

    try:
        combined = model.FeatureManager.InsertCombineFeature(
            op, com_nothing(), VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [])
        )
    except Exception as exc:
        raise SolidWorksError(f"{name}: the combine failed ({format_com_error(exc)}).") from exc
    if combined is None:
        raise SolidWorksError(f"{name}: the combine failed.")
    rename_feature(combined, name)


def _common(model, a: str, b: str, name: str) -> None:
    """Keep what two bodies share. SW 2013 takes both selected with mark 2 and no main body."""
    _combine(model, _SWBODYINTERSECT, [(a, 2), (b, 2)], name)


def _subtract(model, main: str, tool: str, name: str) -> None:
    """``main`` less ``tool``: main body with mark 1, tool with mark 2."""
    _combine(model, _SWBODYCUT, [(main, 1), (tool, 2)], name)


def _sag(radius: float, half_width: float) -> float:
    return radius - math.sqrt(max(radius * radius - half_width * half_width, 0.0))
