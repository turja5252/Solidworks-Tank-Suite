"""Mid platform frame: C4x5.4 channels mitered at all four corners, on an open stair part.

From Stair Platform Top View.lsp (RADIALPLATFORM, Mid, straight connectors),
SpiralShellPlatform.lsp, and Platform_Sideview.lsp. In plan the outside of the
frame runs on four lines. A and B are radial: A where the stringers stop past
the tread the platform follows, B 36 in further on along the walk centerline.
C and D are straight between them, on the tank face of the inner stringer and
the outside face of the outer stringer, so the frame is as wide as the stair
over its stringers. The channels come from the SolidWorks weldment library,
web on that outline and flanges in. The 1-1/4 in grating that goes on top is
flush with the tread top, so the channels' top is 1-1/4 in below it and their
bottom is level with the bottom of the stringer's end drop.

Each stringer end at a platform is tied to the radial channel by an L6x6x3/8
clip 2-1/2 in tall on the walk side of the stringer: one leg flat on the
stringer, the other flat on the channel web, heel in the corner. Both legs have
two 13/16 holes 2-3/16 and 4-11/16 in from the heel, on the stringer end hole
line 2-3/4 in below the channel top, so the clip is flush with the channel
bottom. The web has 13/16 rounds at the inner stringer and 1-5/8 slots along
the channel at the outer stringer; the clips have rounds only.

Two knee braces carry the outer channel, one at each end of the platform
(Stair Platform Streatchout.lsp, Platform_Sideview.lsp): a 3/8 plate 4 in wide
and 5 in tall hangs under the outer channel 1/4 in in from the platform end,
from 1/4 in to 4-1/4 in in from the outside. The stair's L3x3x3/8 knee brace
bolts to it at its middle, 3-1/2 in below the channel, and runs down at 45 deg
on the platform side of the plate to the same 1/4 x 7 x 4 clip and 6 x 4 pad
on the shell, its bolt 5.766 in out from the shell. Each knee is radial.

The inner channel is tied to the shell at both ends (Stair Platform Top
View.lsp, Platform_Sideview.lsp): a 3/8 x 4 in tab welded square to the web
1/4 in in from the channel end, 3-1/2 in out toward the shell, bolted to a 3/8
shell clip as tall as the channel on the tab's face toward the platform middle.
The shell clip runs from a 1/4 pad on the shell (4 in wide, 6 in tall, 2 in
radius ends) to 3/4 in short of the channel. Two 13/16 holes 2 in apart, one
above the other about the channel's mid-height, 2-1/8 in out from the web.
"""

from __future__ import annotations

import contextlib
import math
import os
from dataclasses import dataclass

from swauto.comutil import com_nothing, com_value, format_com_error
from swauto.errors import SolidWorksError
from swauto.params import rename_feature
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import (
    CLIP_BOLT_OUT_IN,
    BraceResult,
    _body_points,
    _draw_pad,
    _extrude_to,
    _face_at,
    _Frame,
    _Knee,
    _knee_angle,
    _knee_clip_and_pad,
    _knee_holes,
    _progress,
    _set_turn,
    _stair_parts,
)
from swauto.stair.development import END_EXT_IN
from swauto.stair.inner_clip_sw import _angle_between, _hand, _leg_axes, _member
from swauto.stair.stringer import CLEAR_IN, THICKNESS_IN, TREAD_DEPTH_IN, TREAD_MARK_IN, PlatformSpec
from swauto.stair.stringer_sw import _create_circle, _names, _rename_new
from swauto.tank.shell import _clear_selection, _close_sketch

_INCH = 0.0254
PROFILE = ("ansi inch", "C Channel", "C4x5.4.SLDLFP")
CLIP_PROFILE = ("ansi inch", "L Angle", "L6x6x0.375.SLDLFP")
CHANNEL_IN = 4.0
WEB_IN = 0.184  # C4x5.4 web
FLANGE_IN = 1.584  # C4x5.4 flange width
# The C4x5.4 library section (SolidWorks 2013, ansi inch) as a channel's end face reads it, t across from the web's
# back and y up from the bottom: the flange tip's square face and its round, the flange's 1:6 sloped inside face,
# and the root round into the web.
TIP_ROUND = ((1.4740, 0.0861), 0.1100)  # centre, radius; the tip's square face runs up to the centre's height
ROOT_ROUND = ((0.4640, 0.6499), 0.2800)
COPE_GAP_IN = 0.0625  # a radial's cope stands clear of the side channel all round (Chris Samm, Elite)
GRATING_IN = 1.25
CLIP_LEG_IN = 6.0
CLIP_THK_IN = 0.375
CLIP_TALL_IN = 2.5
CLIP_GAUGES_IN = (2.1875, 4.6875)  # from the heel on both legs: the stringer end holes' set-back
HOLE_DOWN_IN = 2.75  # below the channel top: the stringer end hole line
HOLE_DIA_IN = 0.8125
SLOT_IN = 1.625
TAB_THK_IN = 0.375
TAB_OUT_IN = 3.5  # from the channel web toward the shell
TAB_FROM_END_IN = 0.25
SHELL_CLIP_THK_IN = 0.375
SHELL_CLIP_SHORT_IN = 0.75  # its end short of the channel web
SHELL_PAD_THK_IN = 0.25
SHELL_PAD_TALL_IN = 6.0
SHELL_BOLT_OUT_IN = 2.125  # from the channel web
SHELL_BOLT_SPACE_IN = 2.0
HANGER_THK_IN = 0.375
HANGER_WIDE_IN = 4.0
HANGER_TALL_IN = 5.0
HANGER_FROM_END_IN = 0.25
HANGER_IN_FROM_OUTSIDE_IN = 0.25
HANGER_BOLT_DOWN_IN = 3.5  # below the channel bottom


@dataclass(frozen=True)
class _Lines:
    """Plan lines of one platform: radial sides A and B; the walk faces of a full-width stair's stringers, the
    frame's inside (the outer one further out on a wider platform); the channel top; the outer stringer's walk
    face, which is further in when the treads are narrower than the platform or the platform wider than the
    stair; whether the sides C and D are rolled about the tank axis; and the radials between A and B."""

    phi_a: float
    phi_b: float
    r_a: float
    r_b: float
    top: float
    stringer_b: float
    rolled: bool = False
    radials: tuple[float, ...] = ()
    held: tuple[float, ...] | None = None  # the radials with a knee brace and shell clip (None: all of them)

    @property
    def r_in(self) -> float:
        return self.r_a - THICKNESS_IN

    @property
    def r_out(self) -> float:
        return self.r_b + THICKNESS_IN

    @property
    def r_mid(self) -> float:
        """The centreline the platform's length runs along."""
        return (self.r_a + self.r_b) / 2.0

    def members(self) -> list[tuple[str, float, float]]:
        """Each radial channel of the frame, the ends and every radial between: its label, the angle of its web's
        back, and the way into the platform from it (+1 toward B)."""
        between = [(f"R{i}", angle, 1.0) for i, angle in enumerate(self.radials, start=1)]
        return [("A", self.phi_a, 1.0), *between, ("B", self.phi_b, -1.0)]

    def supports(self) -> list[tuple[str, float, float]]:
        """The radial channels with a knee brace under the outer side and a shell clip on the inner one: both ends,
        and the radials between that are ``held`` (Chris Samm: one at least every 96 in), as ``members`` labels
        them."""
        held = self.radials if self.held is None else self.held
        return [member for member in self.members()
                if member[0] in ("A", "B") or any(abs(member[1] - angle) < 1e-9 for angle in held)]


def platform_lines(
    *, phi: float, tread_top: float, r_a: float, r_b: float, stringer_b: float | None = None,
    spec: PlatformSpec | None = None,
) -> _Lines:
    """A sits on the inner stringer's end, half a tread plus 1/8 in past the tread centerline at ``phi``.

    ``r_b`` is the stair's own platform's outer walk face; ``stringer_b`` the outer stringer's, if not the same.
    ``spec`` is the platform's shape (the stair's own when None): its length along the centreline sets B, a
    wider one puts the outer side further out, and its radials sit along the centreline between A and B."""
    spec = spec or PlatformSpec()
    stringer = r_b if stringer_b is None else stringer_b
    r_b = r_b + spec.extra_in
    phi_a = phi + (TREAD_DEPTH_IN / 2.0 + END_EXT_IN) / r_a
    r_mid = (r_a + r_b) / 2.0
    return _Lines(
        phi_a, phi_a + spec.length_in / r_mid, r_a, r_b, tread_top - GRATING_IN, stringer, spec.is_rolled,
        tuple(phi_a + along / r_mid for along in spec.radial_positions()),
        tuple(phi_a + along / r_mid for along in spec.support_positions()),
    )


def _library(app, parts) -> str:
    root = str(com_value(app.GetExecutablePath))
    path = os.path.join(root, "lang", "english", "weldment profiles", *parts)
    if not os.path.isfile(path):
        raise SolidWorksError(f"The {parts[-1][:-7]} weldment profile is not at {path}.")
    return path


def platform_profile(app) -> str:
    """The C4x5.4 file in this SolidWorks' weldment library."""
    return _library(app, PROFILE)


def clip_profile(app) -> str:
    """The L6x6x0.375 file in this SolidWorks' weldment library."""
    return _library(app, CLIP_PROFILE)


def _world(phi: float, r: float, t: float, y: float) -> tuple[float, float, float]:
    """Inches: r out along the radial line at ``phi``, t toward the upper treads, y up."""
    c, sn = math.cos(phi), math.sin(phi)
    return (-r * sn - t * c, y, r * c - t * sn)


def add_mid_platform(model, tread_index: int, profile: str, progress=None) -> BraceResult:
    """Platform frame starting where the stringers stop past tread ``tread_index``, read from the part.

    ``profile`` is from ``platform_profile``. The grating top is flush with that tread's top.
    """
    r_a, _r_b, treads = _stair_parts(model)
    if not 1 <= tread_index <= len(treads):
        raise SolidWorksError(f"This stair has {len(treads)} treads; there is no tread {tread_index}.")
    y_bottom, phi, _r = treads[tread_index - 1]
    return place_mid_platform(
        model, tread_index, phi=phi, tread_top=y_bottom + TREAD_MARK_IN, r_a=r_a, r_b=r_a + CLEAR_IN,
        profile=profile, progress=progress,
    )


def place_mid_platform(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, profile: str, progress=None,
    spec: PlatformSpec | None = None,
) -> BraceResult:
    """Platform frame after the tread centered at angle ``phi`` with its top at ``tread_top``, of shape ``spec``.

    ``r_a`` and ``r_b`` are the walk faces of the inner and outer stringers. No
    tread has to be in the part, so a stringers-only stair works. A straight
    frame is mitered at all four corners; a rolled one is built the way Stair
    Platform Top View.lsp draws it, the inner and outer sides rolled the full
    length and the radial sides between them. Radials between the ends stand
    between the sides' webs, their flanges coped clear of the sides'.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b, spec=spec)
    r_in, r_out, phi_a, phi_b = lines.r_in, lines.r_out, lines.phi_a, lines.phi_b
    base = lines.top - CHANNEL_IN
    name = f"ElitePlatform{tread_index:02d}"
    if lines.rolled:
        _rolled_frame(model, lines, base, profile, name)
    else:
        outline = [s._plan_xy(r, a) for r, a in ((r_in, phi_a), (r_out, phi_a), (r_out, phi_b), (r_in, phi_b))]
        if _signed_area(outline) < 0:
            outline.reverse()  # counterclockwise in the sketch puts the flanges inside
        _frame(model, outline, base, profile, name)
        for label, angle, side in lines.members()[1:-1]:
            _radial_member(model, lines, angle, side, base, profile, f"{name}{label}")
    _progress(progress, f"{name} frame placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    with contextlib.suppress(Exception):
        model.GraphicsRedraw2()
    length = (phi_b - phi_a) * lines.r_mid
    radials = len(lines.radials)
    between = f", with {radials} radial{'s' if radials > 1 else ''} between them, coped" if radials else ""
    if lines.rolled:
        note = (
            f"Platform after tread {tread_index}: C4x5.4 frame {length:g} in along its centreline, the inner and "
            f"outer sides rolled about the tank flanges in, {r_in * (phi_b - phi_a):.3f} in long rolled to "
            f"{r_in:.3f} in and {r_out * (phi_b - phi_a):.3f} in long rolled to {r_out:.3f} in (web backs), the "
            f"radial ends between their webs, coped{between}. "
        )
    else:
        inner = 2.0 * r_in * math.sin((phi_b - phi_a) / 2.0)
        outer = 2.0 * r_out * math.sin((phi_b - phi_a) / 2.0)
        note = (
            f"Platform after tread {tread_index}: C4x5.4 frame mitered at all four corners{between}, "
            f"{length:g} in along its centreline. Outside lengths: two radial sides "
            f"{r_out - r_in:.3f} in, inner side {inner:.3f} in, outer side {outer:.3f} in. "
        )
    note += f"Channel tops {GRATING_IN:g} in below the top of tread {tread_index} for the grating."
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _rolled_frame(model, lines: _Lines, base: float, profile: str, name: str) -> None:
    """The inner side C and the outer side D rolled about the tank axis the full length, flanges into the platform
    (D is hung from a plane at its top: SolidWorks turns a channel's flanges toward the axis by hanging it), then
    A, B and each radial between their webs. One closed loop does not do: SolidWorks 2013 silently leaves out the
    arc whose flanges face the axis."""
    _arc_member(model, lines.r_in, lines.phi_a, lines.phi_b, base, 0.0, profile, f"{name}C")
    _arc_member(model, lines.r_out, lines.phi_a, lines.phi_b, base + CHANNEL_IN, math.pi, profile, f"{name}D")
    for label, angle, side in lines.members():
        _radial_member(model, lines, angle, side, base, profile, f"{name}{label}")


def _arc_member(model, r: float, a0: float, a1: float, y: float, turn: float, profile: str, name: str):
    """One C4x5.4 rolled about the tank axis on the arc of radius ``r`` (its web's back) from angle ``a0`` to
    ``a1``, its sketch on a level plane at ``y``: standing on it with its flanges away from the axis (``turn``
    0), or hung under it with its flanges toward the axis (``turn`` pi)."""
    plane = s._offset_from(model, s._plane(model, "Top"), y, f"{name}Pln")

    def draw():
        a, b, m = s._plan_xy(r, a0), s._plan_xy(r, a1), s._plan_xy(r, (a0 + a1) / 2.0)
        if model.SketchManager.Create3PointArc(a[0], a[1], 0.0, b[0], b[1], 0.0, m[0], m[1], 0.0) is None:
            raise SolidWorksError(f"{name}: arc failed.")

    body = _channel_member(model, s._sketch_on(model, plane, f"{name}Sk", draw), profile, turn, name)
    reach = _radii(body)
    flanges = (r, r + FLANGE_IN) if turn == 0.0 else (r - FLANGE_IN, r)
    if abs(reach[0] - flanges[0]) > 0.05 or abs(reach[1] - flanges[1]) > 0.05:
        raise SolidWorksError(f"{name}: the rolled channel's flanges went the wrong way.")
    return body


def _radial_member(model, lines: _Lines, angle: float, side: float, base: float, profile: str, name: str) -> None:
    """A C4x5.4 on the radial line at ``angle`` (its web's back) between the inner side's web and the outer
    side's, flanges toward ``side`` (+1 toward B), standing on the frame's bottom; then its ends coped top and
    bottom clear of the sides' flanges."""
    near = _inner_back(lines, angle) + WEB_IN
    far = _outer_back(lines, angle) - WEB_IN
    plane = s._offset_from(model, s._plane(model, "Top"), base, f"{name}Pln")
    start, end = (far, near) if side > 0 else (near, far)  # drawn in toward the axis, its flanges come out toward B

    def draw():
        a, b = s._plan_xy(start, angle), s._plan_xy(end, angle)
        if model.SketchManager.CreateLine(a[0], a[1], 0.0, b[0], b[1], 0.0) is None:
            raise SolidWorksError(f"{name}: radial line failed.")

    before = s._body_names(model)
    body = _channel_member(model, s._sketch_on(model, plane, f"{name}Sk", draw), profile, 0.0, name)
    turns = [math.remainder(a - angle, 2.0 * math.pi) for a in _angles(body)]  # off its line, whole turns aside
    toward = max(turns) if side > 0 else -min(turns)
    if toward < 0.9 * FLANGE_IN / far:
        raise SolidWorksError(f"{name}: the radial channel's flanges went the wrong way.")
    for inner in (True, False):
        _cope(model, before, lines, angle, side, base, inner, f"{name}Cope{'C' if inner else 'D'}")
    made = [b for b in s._bodies(model) if str(b.Name) not in before]
    if len(made) != 1:
        raise SolidWorksError(f"{name}: expected the one radial channel, found {len(made)} new bodies.")
    # Coped to the sides: its ends stand off both webs by the gap, its web reaching in between their flanges.
    radii = [math.hypot(p[0], p[2]) for p in _vertices(made[0])]
    if min(radii) < near + COPE_GAP_IN - 0.01 or max(radii) > far - COPE_GAP_IN + 0.01:
        raise SolidWorksError(f"{name}: the copes did not stand its ends off the side channels' webs.")
    if min(radii) > _inner_back(lines, angle) + FLANGE_IN or max(radii) < _outer_back(lines, angle) - FLANGE_IN:
        raise SolidWorksError(f"{name}: the copes took its ends back past the side channels' flanges.")
    with contextlib.suppress(Exception):
        made[0].Name = name  # a cut names the body after itself


def _cope(model, before: set[str], lines: _Lines, angle: float, side: float, base: float, inner: bool,
          name: str) -> None:
    """Cope the radial channel at ``angle`` (the one body not in ``before``) to the inner side channel (``inner``)
    or the outer one: cut away whatever of it lies within the side's section grown ``COPE_GAP_IN`` all round, so
    its end stands that far off the side's web and its flanges and web clear the side's flanges, rounds and all.

    The grown section is sketched on the plane square to the side through the middle of the radial's flange
    width, and cut both ways from it on the radial alone. A rolled side's section is the same in every radial
    plane, and the side curves less than 3/1000 in across half a flange; a straight side's is the same all along
    it."""
    reach = FLANGE_IN / 2.0  # the middle of the radial's flange width, off its web's back
    if lines.rolled:
        radius = lines.r_in if inner else lines.r_out
        plane_phi = angle + side * reach / radius
        plane = s._radial_plane(model, plane_phi, f"{name}Pln")
        back = radius
        out = 1.0 if inner else -1.0  # from the side's back toward its flanges

        def at(t: float, y: float):
            return _world(plane_phi, back + out * t, 0.0, base + y)
    else:
        half = (lines.phi_b - lines.phi_a) / 2.0
        mid = lines.phi_a + half
        chord_r = (lines.r_in if inner else lines.r_out) * math.cos(half)  # the side's back on the bisector
        along = chord_r * math.tan(angle - mid) + side * reach  # along the side from the bisector
        plane = _plane_across(model, mid, along, f"{name}Pln")
        out = 1.0 if inner else -1.0

        def at(t: float, y: float):
            return _world(mid, chord_r + out * t, along, base + y)

    def draw(manager, to_sketch):
        for shape in _grown_section(COPE_GAP_IN):
            points = [to_sketch(at(*p)) for p in shape[1:]]
            if shape[0] == "line":
                (ax, ay), (bx, by) = points
                made = manager.CreateLine(ax, ay, 0.0, bx, by, 0.0)
            else:
                (ax, ay), (mx, my), (bx, by) = points
                made = manager.Create3PointArc(ax, ay, 0.0, bx, by, 0.0, mx, my, 0.0)
            if made is None:
                raise SolidWorksError(f"{name}: the cope's outline failed.")

    sketch = _sketch_on_face(model, plane, f"{name}Sk", draw)
    made = [b for b in s._bodies(model) if str(b.Name) not in before]
    if len(made) != 1:
        raise SolidWorksError(f"{name}: expected the one radial channel, found {len(made)} new bodies.")
    feature = _cut_both_ways_in(model, sketch, reach + 0.25, made[0])
    if feature is None:
        raise SolidWorksError(f"{name}: the cope was not cut.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)


def _grown_section(gap: float) -> list[tuple]:
    """The C4x5.4 section grown ``gap`` all round, as a closed run of ("line", a, b) and ("arc", a, middle, b) in
    (t, y): t across from the web's back toward the flanges, y up from the bottom. The square corners grow round;
    the tip round grows by the gap and the root round, on the open side, shrinks by it."""
    (tip_x, tip_y), tip_r = TIP_ROUND
    (root_x, root_y), root_r = ROOT_ROUND
    ux, uy = 1.0 / math.sqrt(37.0), 6.0 / math.sqrt(37.0)  # out of the flange, square to its 1:6 inside face
    s2 = math.sqrt(0.5)
    width, tall, web = FLANGE_IN, CHANNEL_IN, WEB_IN

    def on(cx: float, cy: float, r: float, angle: float) -> tuple[float, float]:
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    tip_end = (tip_x + (tip_r + gap) * ux, tip_y + (tip_r + gap) * uy)
    root_start = (root_x - (root_r - gap) * ux, root_y - (root_r - gap) * uy)
    toward = math.atan2(uy, ux)  # the tip round runs from 0 to here
    away = math.atan2(-uy, -ux) % (2.0 * math.pi)  # the root round runs from here round to a half turn
    bottom = [
        ("arc", (-gap, 0.0), (-gap * s2, -gap * s2), (0.0, -gap)),
        ("line", (0.0, -gap), (width, -gap)),
        ("arc", (width, -gap), (width + gap * s2, -gap * s2), (width + gap, 0.0)),
        ("line", (width + gap, 0.0), (width + gap, tip_y)),
        ("arc", (width + gap, tip_y), on(tip_x, tip_y, tip_r + gap, toward / 2.0), tip_end),
        ("line", tip_end, root_start),
        ("arc", root_start, on(root_x, root_y, root_r - gap, (away + math.pi) / 2.0), (web + gap, root_y)),
    ]

    def flip(p: tuple[float, float]) -> tuple[float, float]:
        return p[0], tall - p[1]

    top = [(shape[0], *(flip(p) for p in reversed(shape[1:]))) for shape in reversed(bottom)]
    return [*bottom, ("line", (web + gap, root_y), (web + gap, tall - root_y)), *top,
            ("line", (-gap, tall), (-gap, 0.0))]


def _plane_across(model, mid: float, along: float, name: str):
    """The plane square to a straight side of a platform (along the travel at the bisector ``mid``), ``along``
    inches from the radial plane at ``mid``: that plane moved along its normal, which way read back."""
    base = s._radial_plane(model, mid, f"{name}Axis")
    travel = _travel(mid)
    for distance in (along, -along):
        plane = s._offset_from(model, base, distance, name)
        rows = [float(v) for v in com_value(com_value(com_value(plane.GetSpecificFeature2).Transform).ArrayData)]
        if abs((rows[9] * travel[0] + rows[11] * travel[2]) / _INCH - along) < 0.01:
            return plane
        s._delete_named(model, (s._feature_name(plane),))
    raise SolidWorksError(f"{name}: the plane across the side did not land.")


def _cut_both_ways_in(model, sketch, depth_in: float, body):
    """A blind cut ``depth_in`` both ways from the sketch, on ``body`` alone."""
    args = (
        False, False, False, 0, 0, depth_in * _INCH, depth_in * _INCH,
        False, False, False, False, 0.0, 0.0, False, False, False, False,
        False, True, False, True,
        True, False, 0, 0.0, False,
    )
    _clear_selection(model)
    if not s._select_feature(model, sketch, "SKETCH", mark=0, append=False):
        raise SolidWorksError("Could not select the cope's sketch.")
    data = model.SelectionManager.CreateSelectData
    data.Mark = 8  # feature scope bodies go in with mark 8
    if not body.Select2(True, data):
        raise SolidWorksError("Could not select the radial channel to cope.")
    try:
        feature = model.FeatureManager.FeatureCut3(*args)
    except Exception:
        feature = None
    return feature if feature not in (None, False) else None


def _channel_member(model, sketch, profile: str, turn: float, name: str):
    """A C4x5.4 structural member on the one segment of ``sketch``, turned ``turn`` about its path; its body."""
    before = s._body_names(model)
    s._select_segments(model, sketch, name, 1)
    try:
        feature = model.FeatureManager.InsertStructuralWeldment2(profile, 1, False, 0.0)
    except Exception as exc:
        raise SolidWorksError(f"{name}: structural member failed ({format_com_error(exc)}).") from exc
    if feature is None:
        raise SolidWorksError(f"{name}: structural member was not made.")
    if turn:
        data = com_value(feature.GetDefinition)
        data.AccessSelections(model, com_nothing())
        data.RotationAngle = turn
        if not feature.ModifyDefinition(data, model, com_nothing()):
            raise SolidWorksError(f"{name}: could not turn the channel.")
    s._rebuild(model)
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)
    bodies = [b for b in s._bodies(model) if str(b.Name) not in before]
    if len(bodies) != 1:
        raise SolidWorksError(f"{name}: expected one channel, got {len(bodies)} bodies.")
    box = s._box_in(bodies[0])
    if abs(box[4] - box[1] - CHANNEL_IN) > 0.01:
        raise SolidWorksError(f"{name}: the channel is {box[4] - box[1]:.3f} in tall, not {CHANNEL_IN:g}.")
    return bodies[0]


def _vertices(body) -> list[list[float]]:
    raw = com_value(body.GetVertices)
    found = list(raw) if isinstance(raw, (list, tuple)) else ([] if raw is None else [raw])
    return [[float(v) / _INCH for v in com_value(vertex.GetPoint)] for vertex in found]


def _radii(body) -> tuple[float, float]:
    radii = [math.hypot(p[0], p[2]) for p in _vertices(body)]
    return min(radii), max(radii)


def _angles(body) -> tuple[float, float]:
    angles = [math.atan2(-p[0], p[2]) for p in _vertices(body)]
    return min(angles), max(angles)


def _inner_back(lines: _Lines, phi: float) -> float:
    """The inner channel's back (its tank face), from the axis along the radial line at ``phi``: its arc when
    rolled, else the straight line between the inner corners."""
    if lines.rolled:
        return lines.r_in
    half = (lines.phi_b - lines.phi_a) / 2.0
    return lines.r_in * math.cos(half) / math.cos(phi - (lines.phi_a + half))


def _signed_area(points) -> float:
    return 0.5 * sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]))


def _frame(model, outline, base: float, profile: str, name: str) -> None:
    """Closed loop on a level plane at the channels' bottom, then one structural member on all four lines.

    SolidWorks miters the corners of a closed loop and sets each channel with
    its web back on the line, its flanges toward the inside, standing up from
    the sketch plane.
    """
    plane = s._offset_from(model, s._plane(model, "Top"), base, f"{name}Pln")

    def draw():
        manager = model.SketchManager
        with contextlib.suppress(Exception):
            manager.AddToDB = True
        for (ax, ay), (bx, by) in zip(outline, outline[1:] + outline[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: frame line failed.")

    sketch = s._sketch_on(model, plane, f"{name}Sk", draw)
    bodies_before = s._body_names(model)
    s._select_segments(model, sketch, name, 4)
    try:
        feature = model.FeatureManager.InsertStructuralWeldment2(profile, 1, False, 0.0)
    except Exception as exc:
        raise SolidWorksError(f"{name}: structural member failed ({format_com_error(exc)}).") from exc
    if feature is None:
        raise SolidWorksError(f"{name}: structural member was not made.")
    with contextlib.suppress(Exception):
        rename_feature(feature, f"{name}Frame")
    s._rebuild(model)
    channels = []
    for body in s._bodies(model):
        with contextlib.suppress(Exception):
            if str(body.Name) not in bodies_before:
                channels.append(s._box_in(body))
    if len(channels) != 4 or any(abs(box[4] - box[1] - CHANNEL_IN) > 0.01 for box in channels):
        raise SolidWorksError(f"{name}: expected four 4 in channels, got {len(channels)} bodies.")
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)


# ------------------------------------------------------------- stringer clips


def add_stringer_clips(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, profile: str,
    sides: tuple[str, ...] = ("A", "B"), stringer_b: float | None = None, progress=None,
    spec: PlatformSpec | None = None,
) -> BraceResult:
    """Clips tying the stringer ends to the platform after tread ``tread_index``, of shape ``spec``.

    Side A is the radial channel where the flight below stops, side B the one
    where the flight above starts. ``profile`` is from ``clip_profile``. The outer
    clip is on the outer stringer, at ``stringer_b`` when the treads are narrower
    than the platform.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b, stringer_b=stringer_b, spec=spec)
    name = f"ElitePlatform{tread_index:02d}"
    hole_y = lines.top - HOLE_DOWN_IN
    sag = CLIP_LEG_IN * CLIP_LEG_IN / (2.0 * lines.stringer_b) + 0.001
    missed = []
    for side in sides:
        line_phi = lines.phi_a if side == "A" else lines.phi_b
        away = -1.0 if side == "A" else 1.0  # along the travel, from the channel to that flight
        tag = f"{name}Clip{side}"
        if not _web_holes(model, lines, line_phi, hole_y, f"{name}Web{side}"):
            missed.append(f"web holes {side}")
        clips = []
        # Inner stringer: walk face convex toward the clip, so the flat leg sits on it at the heel.
        # Outer stringer: walk face concave toward the clip, so the leg is eased in by the sag.
        for label, heel_r, inward in (("In", r_a, 1.0), ("Out", lines.stringer_b - sag, -1.0)):
            body = _clip(model, line_phi, heel_r, inward, away, lines.top, profile, f"{tag}{label}")
            clips.append((body, heel_r, inward))
        _progress(progress, f"{tag} angles placed")
        if not _clip_web_leg_holes(model, lines, line_phi, hole_y, f"{tag}WebLegHoles"):
            missed.append(f"clip web legs {side}")
        for (_body, heel_r, inward), label in zip(clips, ("In", "Out")):
            if not _clip_stringer_leg_holes(model, line_phi, heel_r, inward, away, hole_y, f"{tag}{label}LegHoles"):
                missed.append(f"clip {side} {label.lower()} stringer leg")
        _progress(progress, f"{tag} holes {'missed' if missed else 'cut'}")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: L6x6x3/8 x {CLIP_TALL_IN:g} in clips on side(s) "
        f"{', '.join(sides)}, two 13/16 holes in each leg at 2-3/16 and 4-11/16 in from the heel. "
        "Channel web: rounds at the inner stringer, 1-5/8 slots at the outer."
        + (f" Missed: {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _sketch_on_face(model, face, name: str, draw):
    """Sketch on ``face``; ``draw(manager, to_sketch)`` with model points in inches."""
    _clear_selection(model)
    if face is None or not s._select_face(model, face):
        raise SolidWorksError(f"{name}: could not select the face to sketch on.")
    before = _names(model)
    manager = model.SketchManager
    with contextlib.suppress(Exception):
        manager.AddToDB = True
    manager.InsertSketch(True)
    try:
        sketch = com_value(model.GetActiveSketch2)
        if sketch is None:
            raise SolidWorksError(f"{name}: no sketch opened on the face.")
        data = [float(v) for v in com_value(com_value(sketch.ModelToSketchTransform).ArrayData)]

        def to_sketch(p_in):
            sx, sy, sz = s._to_sketch(data, [v * _INCH for v in p_in])
            if abs(sz) > 0.01 * _INCH:
                raise SolidWorksError(f"{name}: a point is {sz / _INCH:.3f} in off the sketch face.")
            return sx, sy

        draw(manager, to_sketch)
    except Exception:
        s._recover(model)
        raise
    _close_sketch(model)
    return _rename_new(model, before, f"{name}Sk", "hole sketch")


def _cut(model, face, name: str, draw, depth_in: float) -> bool:
    try:
        sketch = _sketch_on_face(model, face, name, draw)
    except SolidWorksError:
        return False
    feature = s._cut_both_ways(model, sketch, depth_in)
    if feature is None:
        s._delete_named(model, (f"{name}Sk",))
        return False
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    s._rebuild(model)
    return True


def _radial(phi: float) -> tuple[float, float, float]:
    return (-math.sin(phi), 0.0, math.cos(phi))


def _travel(phi: float) -> tuple[float, float, float]:
    return (-math.cos(phi), 0.0, -math.sin(phi))


def _channel_face(model, lines: _Lines, line_phi: float):
    """Back of the radial channel web on this side: the platform outline's radial plane."""
    mid = (lines.r_a + lines.r_b) / 2.0
    frame = [b for b in s._bodies(model) if str(b.Name).startswith("ElitePlatform")]
    return _face_at(frame, _world(line_phi, mid, 0.0, lines.top - CHANNEL_IN / 2.0), _travel(line_phi))


def _web_holes(model, lines: _Lines, line_phi: float, hole_y: float, name: str) -> bool:
    """13/16 rounds at the inner stringer and 1-5/8 slots along the channel at the outer, through the web."""
    rounds = [_world(line_phi, lines.r_a + g, 0.0, hole_y) for g in CLIP_GAUGES_IN]
    slots = [_world(line_phi, lines.stringer_b - g, 0.0, hole_y) for g in CLIP_GAUGES_IN]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in rounds:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")
        for point in slots:
            sx, sy = to_sketch(point)
            ax, ay = to_sketch(_world(line_phi, lines.stringer_b - 1.0, 0.0, hole_y))
            bx, by = to_sketch(_world(line_phi, lines.stringer_b, 0.0, hole_y))
            s._slot_along(model, sx, sy, ax - bx, ay - by, SLOT_IN * _INCH, radius)

    if not _cut(model, _channel_face(model, lines, line_phi), name, draw, WEB_IN + 0.06):
        return False
    return all(_hole_in(model, p) for p in rounds)


def _hole_in(model, point_in) -> bool:
    point = [v * _INCH for v in point_in]
    radius = HOLE_DIA_IN / 2.0 * _INCH
    return any(s._has_hole_axis(body, point, radius, 0.1 * _INCH) is True for body in s._bodies(model))


def _clip(model, line_phi: float, heel_r: float, inward: float, away: float, top: float, profile: str, name: str):
    """L6x6 on a vertical line at the heel, turned until one leg runs along the stringer
    away from the channel and the other along the web toward the walk centerline."""
    ys = (top - CHANNEL_IN, top - CHANNEL_IN + CLIP_TALL_IN)
    return _upright_angle(model, line_phi, heel_r, inward, away, ys, CLIP_LEG_IN, profile, name)


def _upright_angle(
    model, line_phi: float, heel_r: float, inward: float, away: float, ys: tuple[float, float], leg_in: float,
    profile: str, name: str, heel_t: float = 0.0,
):
    """Equal-leg angle on a vertical line at the heel from ``ys[0]`` up to ``ys[1]``, turned
    until one leg runs ``away`` along the travel and the other ``inward`` along the radial.
    The heel is ``heel_t`` along the travel from the radial line at ``line_phi``."""
    ends = [_world(line_phi, heel_r, heel_t, y) for y in ys]
    heel = ends[0]
    along = (away * _travel(line_phi)[0], away * _travel(line_phi)[2])
    across = (inward * _radial(line_phi)[0], inward * _radial(line_phi)[2])
    feature, path_sketch, bodies_before = _member(model, profile, ends[0], ends[1], name)

    def body_now():
        for body in s._bodies(model):
            with contextlib.suppress(Exception):
                if str(body.Name) not in bodies_before:
                    return body
        return None

    body = body_now()
    if body is None:
        s._rebuild(model)
        body = body_now()
    placed = _upright_fits(body, line_phi, heel_r, inward, away, leg_in, heel_t)
    axes = None if body is None or placed else _leg_axes(body, heel)
    if axes is not None:
        first, second = axes
        target = along if _hand(first, second) * _hand(along, across) > 0 else across
        turn = _angle_between(first, target)
        for rotation in (turn, -turn):
            if _set_turn(model, feature, rotation) and _upright_fits(
                body_now(), line_phi, heel_r, inward, away, leg_in, heel_t
            ):
                placed = True
                break
    if not placed:
        raise SolidWorksError(f"{name}: could not turn the angle into place.")
    with contextlib.suppress(Exception):
        rename_feature(feature, name)
    _clear_selection(model)
    with contextlib.suppress(Exception):
        if path_sketch.Select2(False, 0):
            model.BlankSketch()
    _clear_selection(model)
    return body_now()


def _upright_fits(
    body, line_phi: float, heel_r: float, inward: float, away: float, leg_in: float, heel_t: float = 0.0,
    tol: float = 0.03,
) -> bool:
    if body is None:
        return False
    points = _body_points(body)
    if not points:
        return False
    rs = [inward * (p[0] * _radial(line_phi)[0] + p[2] * _radial(line_phi)[2] - heel_r) for p in points]
    ts = [away * (p[0] * _travel(line_phi)[0] + p[2] * _travel(line_phi)[2] - heel_t) for p in points]
    return (
        min(rs) > -tol and max(rs) < leg_in + tol and max(rs) - min(rs) > leg_in - tol - 0.01
        and min(ts) > -tol and max(ts) < leg_in + tol and max(ts) - min(ts) > leg_in - tol - 0.01
    )


def _clip_web_leg_holes(model, lines: _Lines, line_phi: float, hole_y: float, name: str) -> bool:
    """Rounds through both clips' web legs, from the web's back face; they land in the web's holes and slots."""
    points = [_world(line_phi, r, 0.0, hole_y) for g in CLIP_GAUGES_IN for r in (lines.r_a + g, lines.stringer_b - g)]
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, _channel_face(model, lines, line_phi), name, draw, CLIP_THK_IN + 0.05):
        return False
    return all(_hole_in(model, p) for p in points)


def _clip_stringer_leg_holes(
    model, line_phi: float, heel_r: float, inward: float, away: float, hole_y: float, name: str
) -> bool:
    """Rounds through the clip's stringer leg only, on the stringer's end holes.

    The cut stops in the gap between the flat leg and the curved stringer, so
    the stringer's own holes and slots are left as they are.
    """
    face_r = heel_r + inward * CLIP_THK_IN
    points = [_world(line_phi, face_r, away * g, hole_y) for g in CLIP_GAUGES_IN]
    clips = [b for b in s._bodies(model) if str(b.Name).startswith(name[: name.index("Clip") + 4])]
    face = _face_at(clips, _world(line_phi, face_r, away * 3.0, hole_y), _radial(line_phi))
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, face, name, draw, CLIP_THK_IN + 0.001):
        return False
    return all(_hole_in(model, p) for p in points)


# --------------------------------------------------------------- knee braces


def add_platform_knee_braces(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, shell_r: float,
    profile: str, progress=None, spec: PlatformSpec | None = None,
) -> BraceResult:
    """Hanger plate under the outer channel and a 45 deg knee brace to the shell, at both platform ends and at
    every radial between (``spec`` the platform's shape).

    ``profile`` is the L3x3x0.375 file (``brace_sw.angle_profile``). The part does not need a shell.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b, spec=spec)
    name = f"ElitePlatform{tread_index:02d}Knee"
    missed = []
    for label, frame, knee, back in platform_knees(lines, shell_r):
        tag = f"{name}{label}"
        _hanger(model, frame, back, lines.top, knee.side, f"{tag}Hanger")
        _knee_angle(model, frame, knee, profile, tag)
        _knee_clip_and_pad(model, frame, knee, tag)
        if not _knee_holes(model, frame, knee, tag):
            missed.append(label)
        _progress(progress, f"{tag} placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: a 3/8 x {HANGER_WIDE_IN:g} x {HANGER_TALL_IN:g} hanger under the "
        f"outer channel at each end{' and each held radial' if len(lines.supports()) > 2 else ''} with an L3x3x3/8 "
        "knee brace at 45 deg down to a clip and pad on the shell."
        + (f" Holes missed at end(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def platform_knees(lines: _Lines, shell_r: float) -> list[tuple[str, _Frame, _Knee, float]]:
    """The knee brace under a platform's outer channel at each support (``_Lines.supports``: both ends and every
    radial between): label, radial frame, knee, and the outer channel back's radius on that line. Raises when
    the shell leaves no room."""
    r_mid_plate = lines.r_out - HANGER_IN_FROM_OUTSIDE_IN - HANGER_WIDE_IN / 2.0
    set_in = HANGER_FROM_END_IN + HANGER_THK_IN  # the hanger stands just past the radial's web, as at A
    knees = []
    for label, angle, side in lines.supports():
        knee_phi = angle + side * set_in / r_mid_plate
        frame = _Frame(phi=knee_phi, y_top=lines.top, r_a=lines.r_a, r_b=lines.r_b)
        back = _outer_back(lines, knee_phi)
        r1 = back - HANGER_IN_FROM_OUTSIDE_IN - HANGER_WIDE_IN / 2.0
        y1 = lines.top - CHANNEL_IN - HANGER_BOLT_DOWN_IN
        r2 = shell_r + CLIP_BOLT_OUT_IN
        if r2 >= r1 - 1.0:
            raise SolidWorksError("The platform knee brace has no room between the platform and the shell.")
        knee = _Knee(t_face=0.0, top=(r1, y1), bottom=(r2, y1 - (r1 - r2)), shell_r=shell_r, side=side)
        knees.append((label, frame, knee, back))
    return knees


def _outer_back(lines: _Lines, phi: float) -> float:
    """The outer channel's back, from the axis along the radial line at ``phi``: its arc when rolled, else the
    straight line between the outer corners."""
    if lines.rolled:
        return lines.r_out
    half = (lines.phi_b - lines.phi_a) / 2.0
    return lines.r_out * math.cos(half) / math.cos(phi - (lines.phi_a + half))


def shell_pads(lines: _Lines, shell_r: float) -> list[tuple[str, float, float]]:
    """The shell pad by each support on a platform's inner channel (both ends and every radial between): label,
    plan angle (taken near the platform's own angles) and middle height. Each pad is 4 in wide by
    SHELL_PAD_TALL_IN, full-radius ends."""
    pads = []
    for end, (label, _angle, _side) in zip(_channel_ends(lines), lines.supports(), strict=True):
        qx, qz = _pad_point(end, shell_r)
        phi_q = lines.phi_a + math.remainder(math.atan2(-qx, qz) - lines.phi_a, 2.0 * math.pi)
        pads.append((label, phi_q, end.top - CHANNEL_IN / 2.0))
    return pads


def _hanger(model, frame: _Frame, back: float, top: float, side: float, name: str) -> None:
    """3/8 plate under the outer channel, on the platform-end side of the knee's contact plane."""
    r0 = back - HANGER_IN_FROM_OUTSIDE_IN - HANGER_WIDE_IN
    r1 = back - HANGER_IN_FROM_OUTSIDE_IN
    y1 = top - CHANNEL_IN
    y0 = y1 - HANGER_TALL_IN
    plane = s._radial_plane(model, frame.phi, f"{name}Pln")

    def draw(manager, to_sketch):
        pts = [to_sketch(frame.world(r, 0.0, y)) for r, y in ((r0, y0), (r1, y0), (r1, y1), (r0, y1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: hanger edge failed.")

    sketch = _sketch_on_face(model, plane, name, draw)
    _extrude_to(
        model, sketch, HANGER_THK_IN, frame.world((r0 + r1) / 2.0, -side * HANGER_THK_IN / 2.0, (y0 + y1) / 2.0),
        HANGER_TALL_IN + 0.1, name,
    )


# --------------------------------------------------------------- shell clips


@dataclass(frozen=True)
class _ChannelEnd:
    """One end of the inner channel's back line C, in plan inches."""

    origin: tuple[float, float]  # the corner, (x, z)
    along: tuple[float, float]  # along C toward the other end
    inward: tuple[float, float]  # square to C, toward the tank axis
    top: float

    def world(self, c: float, h: float, y: float) -> tuple[float, float, float]:
        """c along the channel from this end, h out from the web toward the shell."""
        return (
            self.origin[0] + c * self.along[0] + h * self.inward[0],
            y,
            self.origin[1] + c * self.along[1] + h * self.inward[1],
        )


def _channel_ends(lines: _Lines) -> list[_ChannelEnd]:
    """The inner channel's back at each support (``_Lines.supports``), looking into the platform from it: on the
    straight line between the inner corners, or on the arc when rolled."""
    a = (-lines.r_in * math.sin(lines.phi_a), lines.r_in * math.cos(lines.phi_a))
    b = (-lines.r_in * math.sin(lines.phi_b), lines.r_in * math.cos(lines.phi_b))
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    chord = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    ends = []
    for _label, angle, side in lines.supports():
        ray = (-math.sin(angle), math.cos(angle))
        if lines.rolled:
            origin = (lines.r_in * ray[0], lines.r_in * ray[1])
            along = (-side * math.cos(angle), -side * math.sin(angle))  # the arc's tangent toward the platform
        else:
            # Where the radial line meets the straight inner side.
            reach = (a[0] * chord[1] - a[1] * chord[0]) / (ray[0] * chord[1] - ray[1] * chord[0])
            origin = (reach * ray[0], reach * ray[1])
            along = (side * chord[0], side * chord[1])
        inward = (-along[1], along[0])
        if inward[0] * -origin[0] + inward[1] * -origin[1] < 0:
            inward = (-inward[0], -inward[1])
        ends.append(_ChannelEnd(origin, along, inward, lines.top))
    return ends


def add_platform_shell_clips(
    model, tread_index: int, *, phi: float, tread_top: float, r_a: float, r_b: float, shell_r: float, progress=None,
    spec: PlatformSpec | None = None,
) -> BraceResult:
    """Tab, shell clip, and pad at both ends of the inner channel of the platform after tread ``tread_index``, and
    beside every radial between (``spec`` the platform's shape).

    ``shell_r`` is the shell OD radius; the part does not need a shell.
    """
    lines = platform_lines(phi=phi, tread_top=tread_top, r_a=r_a, r_b=r_b, spec=spec)
    if lines.r_in - shell_r < TAB_OUT_IN + SHELL_PAD_THK_IN + 0.5:
        raise SolidWorksError(f"The {lines.r_in - shell_r:.2f} in gap leaves no room for the platform's shell clips.")
    name = f"ElitePlatform{tread_index:02d}Shell"
    missed = []
    for end, (label, _angle, _side) in zip(_channel_ends(lines), lines.supports(), strict=True):
        tag = f"{name}{label}"
        _shell_tab(model, end, f"{tag}Tab", lines.r_in if lines.rolled else None)
        _shell_clip_and_pad(model, end, shell_r, tag)
        if not _shell_holes(model, end, f"{tag}Holes"):
            missed.append(label)
        _progress(progress, f"{tag} clip placed")
    with contextlib.suppress(Exception):
        s._hide_construction(model)
    note = (
        f"Platform after tread {tread_index}: 3/8 x 4 in tabs welded to the inner channel at both ends"
        f"{' and beside each held radial' if len(lines.supports()) > 2 else ''}, "
        f"bolted to 3/8 shell clips on 1/4 x 4 x 6 pads, two 13/16 holes 2 in apart."
        + (f" Holes missed at end(s) {', '.join(missed)}." if missed else "")
    )
    return BraceResult(title=str(com_value(model.GetTitle) or "Part"), note=note)


def _shell_tab(model, end: _ChannelEnd, name: str, rolled_r: float | None = None) -> None:
    """3/8 tab welded square to the web back, 1/4 in in from the channel end (or the radial), out toward the shell.
    On a rolled inner channel (``rolled_r`` its back's radius) it is sketched on the plane touching the back there:
    its curved face takes no sketch."""
    c0, c1 = TAB_FROM_END_IN, TAB_FROM_END_IN + TAB_THK_IN
    y0, y1 = end.top - CHANNEL_IN, end.top
    if rolled_r is not None:
        web = _tangent_plane(model, math.atan2(-end.origin[0], end.origin[1]), rolled_r, f"{name}Web")
    else:
        frame = [b for b in s._bodies(model) if str(b.Name).startswith("ElitePlatform")]
        web = _face_at(frame, end.world((c0 + c1) / 2.0, 0.0, end.top - CHANNEL_IN / 2.0),
                       (end.inward[0], 0.0, end.inward[1]))

    def draw(manager, to_sketch):
        pts = [to_sketch(end.world(c, 0.0, y)) for c, y in ((c0, y0), (c1, y0), (c1, y1), (c0, y1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: tab edge failed.")

    sketch = _sketch_on_face(model, web, name, draw)
    _extrude_to(
        model, sketch, TAB_OUT_IN, end.world((c0 + c1) / 2.0, TAB_OUT_IN / 2.0, end.top - CHANNEL_IN / 2.0),
        CHANNEL_IN + 0.1, name,
    )


def _pad_point(end: _ChannelEnd, shell_r: float) -> tuple[float, float]:
    """Where the shell clip's mid-plane, carried out to the shell, meets the shell OD: the pad is centred on the
    clip, as the knee brace pads are. (Centred on the tab's face it sat half the clip's thickness off.)"""
    c = TAB_FROM_END_IN + TAB_THK_IN + SHELL_CLIP_THK_IN / 2.0
    px, pz = end.world(c, 0.0, 0.0)[0], end.world(c, 0.0, 0.0)[2]
    b = px * end.inward[0] + pz * end.inward[1]
    k = px * px + pz * pz - shell_r * shell_r
    s_near = -b - math.sqrt(b * b - k)
    return px + s_near * end.inward[0], pz + s_near * end.inward[1]


def _shell_clip_and_pad(model, end: _ChannelEnd, shell_r: float, tag: str) -> None:
    """Shell clip on the tab's face toward the platform middle, then the pad flat on the shell behind it."""
    c_face = TAB_FROM_END_IN + TAB_THK_IN
    qx, qz = _pad_point(end, shell_r)
    phi_q = math.atan2(-qx, qz)
    normal = (-math.sin(phi_q), math.cos(phi_q))
    # Out along the tab's line from the web to the pad's outside face.
    px, pz = end.world(c_face, 0.0, 0.0)[0], end.world(c_face, 0.0, 0.0)[2]
    face_x, face_z = qx + SHELL_PAD_THK_IN * normal[0], qz + SHELL_PAD_THK_IN * normal[1]
    reach = ((face_x - px) * normal[0] + (face_z - pz) * normal[1]) / (end.inward[0] * normal[0] + end.inward[1] * normal[1])
    h0, h1 = SHELL_CLIP_SHORT_IN, reach
    y0, y1 = end.top - CHANNEL_IN, end.top
    tabs = [b for b in s._bodies(model) if str(b.Name).startswith(f"{tag}Tab")]
    tab_face = _face_at(tabs, end.world(c_face, TAB_OUT_IN / 2.0, end.top - CHANNEL_IN / 2.0), (end.along[0], 0.0, end.along[1]))

    def draw_clip(manager, to_sketch):
        pts = [to_sketch(end.world(c_face, h, y)) for h, y in ((h0, y0), (h1, y0), (h1, y1), (h0, y1))]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{tag}: shell clip edge failed.")

    clip_sketch = _sketch_on_face(model, tab_face, f"{tag}ShellClip", draw_clip)
    _extrude_to(
        model, clip_sketch, SHELL_CLIP_THK_IN,
        end.world(c_face + SHELL_CLIP_THK_IN / 2.0, (h0 + h1) / 2.0, end.top - CHANNEL_IN / 2.0),
        CHANNEL_IN + 0.1, f"{tag}ShellClip",
    )

    # The pad sits flat on the shell where the clip's mid-plane meets it, centered on the clip.
    plane = _tangent_plane(model, phi_q, shell_r, f"{tag}Pad")
    y_mid = end.top - CHANNEL_IN / 2.0

    def draw_pad(manager, to_sketch):
        _draw_pad(manager, lambda t, y: to_sketch(_world(phi_q, shell_r, t, y)), 0.0, y_mid, SHELL_PAD_TALL_IN, tag)

    pad_sketch = _sketch_on_face(model, plane, f"{tag}Pad", draw_pad)
    _extrude_to(
        model, pad_sketch, SHELL_PAD_THK_IN, _world(phi_q, shell_r + SHELL_PAD_THK_IN / 2.0, 0.0, y_mid),
        SHELL_PAD_TALL_IN + 0.1, f"{tag}Pad",
    )


def _tangent_plane(model, phi: float, radius: float, name: str):
    """Plane touching the cylinder of ``radius`` at angle ``phi``: the radial plane a quarter turn on,
    moved out ``radius``. The offset side is read back and flipped if SolidWorks went the other way."""
    axis_plane = s._radial_plane(model, phi + math.pi / 2.0, f"{name}AxisPln")
    out = (-math.sin(phi), math.cos(phi))
    for distance in (radius, -radius):
        plane = s._offset_from(model, axis_plane, distance, f"{name}Pln")
        rows = [float(v) for v in com_value(com_value(com_value(plane.GetSpecificFeature2).Transform).ArrayData)]
        if abs((rows[9] * out[0] + rows[11] * out[1]) / _INCH - radius) < 0.01:
            return plane
        s._delete_named(model, (s._feature_name(plane),))
    raise SolidWorksError(f"{name}: the pad plane did not land on the shell.")


def _shell_holes(model, end: _ChannelEnd, name: str) -> bool:
    """Two 13/16 rounds through the tab and the shell clip, from the face they share."""
    c_face = TAB_FROM_END_IN + TAB_THK_IN
    y_mid = end.top - CHANNEL_IN / 2.0
    points = [end.world(c_face, SHELL_BOLT_OUT_IN, y_mid + dy) for dy in (SHELL_BOLT_SPACE_IN / 2.0, -SHELL_BOLT_SPACE_IN / 2.0)]
    tabs = [b for b in s._bodies(model) if str(b.Name).startswith(name.replace("Holes", "Tab"))]
    face = _face_at(tabs, end.world(c_face, TAB_OUT_IN - 0.25, y_mid), (end.along[0], 0.0, end.along[1]))
    radius = HOLE_DIA_IN / 2.0 * _INCH

    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, radius) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    if not _cut(model, face, name, draw, TAB_THK_IN + SHELL_CLIP_THK_IN + 0.05):
        return False
    return all(_hole_in(model, p) for p in points)
