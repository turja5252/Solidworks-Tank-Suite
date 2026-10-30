"""A platform's supports as parts (partify, 2026-10-30): at each support (both ends and every radial between, as
``platform_sw._Lines.supports``) the shell tab welded to the inner channel, the shell clip bolted to it and its pad on
the shell; and under the outer channel the hanger, the knee brace and its clip and pad on the shell.

Each piece is built where the one-part build puts it (platform_sw.add_platform_shell_clips and
add_platform_knee_braces), but sketched on planes from the same numbers instead of on the faces of the pieces beside
it, and each cuts its own bolt holes, so no part needs another. Shared files:

* every shell pad, at the shell clips and under the knees, of every platform: one 1/4 x 4 x 6 plate, flat on the shell
  at its middle, turned about the tank axis and lifted to each;
* on a rolled platform the pieces at A and at every radial between are one piece turned about the tank axis; B's are
  their mirror image, so they have files of their own;
* on a straight platform each support's pieces have their own files (their reach changes along the chords).
"""

from __future__ import annotations

import math

from swauto.errors import SolidWorksError
from swauto.project.items import Placement
from swauto.stair import stair_sw as s
from swauto.stair.brace_sw import CLIP_HEIGHT_IN as KNEE_CLIP_TALL_IN
from swauto.stair.brace_sw import CLIP_OUT_IN as KNEE_CLIP_OUT_IN
from swauto.stair.brace_sw import CLIP_THK_IN as KNEE_CLIP_THK_IN
from swauto.stair.brace_sw import KNEE_HOLE_DIA_IN, LEG_THK_IN, _draw_pad, _extrude_to, _knee_angle, knee_pad
from swauto.stair.grab_sw import _sketch_through
from swauto.stair.platform_sw import (
    CHANNEL_IN,
    CLIP_GAUGES_IN,
    CLIP_LEG_IN,
    CLIP_THK_IN,
    HANGER_THK_IN,
    HOLE_DIA_IN,
    HOLE_DOWN_IN,
    SHELL_BOLT_OUT_IN,
    SHELL_BOLT_SPACE_IN,
    SHELL_CLIP_SHORT_IN,
    SHELL_CLIP_THK_IN,
    SHELL_PAD_TALL_IN,
    SHELL_PAD_THK_IN,
    TAB_FROM_END_IN,
    TAB_OUT_IN,
    TAB_THK_IN,
    _channel_ends,
    _clip,
    _hanger,
    _pad_point,
    _radial,
    _travel,
    _web_holes,
    _world,
    platform_knees,
)
from swauto.stair.stringer_sw import _create_circle

_INCH = 0.0254
C_FACE_IN = TAB_FROM_END_IN + TAB_THK_IN  # along the channel from the support: the tab's face the clip bolts to


def _plane_angle(point) -> float:
    """The stair's plan angle of a point (inches): 0 on +Z, as _world counts it."""
    return math.atan2(-point[0], point[2])


def clip_reach(end, shell_r: float) -> float:
    """How far the shell clip runs out from the channel web toward the shell, to the pad's outside face, along the
    tab's line (platform_sw._shell_clip_and_pad)."""
    qx, qz = _pad_point(end, shell_r)
    phi_q = math.atan2(-qx, qz)
    normal = (-math.sin(phi_q), math.cos(phi_q))
    px, pz = end.world(C_FACE_IN, 0.0, 0.0)[0], end.world(C_FACE_IN, 0.0, 0.0)[2]
    face_x, face_z = qx + SHELL_PAD_THK_IN * normal[0], qz + SHELL_PAD_THK_IN * normal[1]
    return ((face_x - px) * normal[0] + (face_z - pz) * normal[1]) / (
        end.inward[0] * normal[0] + end.inward[1] * normal[1])


def pad_centres(lines, shell_r: float) -> list[tuple[float, float]]:
    """(plan angle, height) of the middle of every shell pad of a platform: its shell clips' then its knees'."""
    centres = []
    for end in _channel_ends(lines):
        qx, qz = _pad_point(end, shell_r)
        centres.append((math.atan2(-qx, qz), end.top - CHANNEL_IN / 2.0))
    for _label, frame, knee, _back in platform_knees(lines, shell_r):
        t_mid, y = knee_pad(knee)
        centres.append((_plane_angle(frame.world(shell_r, t_mid, y)), y))
    return centres


def pad_job_placements(platforms: list, shell_r: float, turn: float) -> tuple[tuple[float, float],
                                                                              tuple[Placement, ...]]:
    """The one pad file: modelled at the first platform's first pad, placed at every pad of every platform."""
    centres = [c for _k, lines in platforms for c in pad_centres(lines, shell_r)]
    head = centres[0]
    return head, tuple(Placement(turn + phi - head[0], (0.0, y - head[1], 0.0)) for phi, y in centres)


def support_groups(lines) -> list[tuple[str, list[int]]]:
    """Which supports share files: (file tag, indexes into supports()). Rolled: A with every radial between (one
    piece turned about the axis), B alone. Straight: each on its own."""
    supports = lines.supports()
    if lines.rolled:
        return [("", list(range(len(supports) - 1))), ("B", [len(supports) - 1])]
    return [(label, [i]) for i, (label, _angle, _side) in enumerate(supports)]


# ----------------------------------------------------------------------------------------------- the pieces


def _hole_pair(points, dia_in: float, name: str):
    def draw(manager, to_sketch):
        for point in points:
            sx, sy = to_sketch(point)
            if _create_circle(manager, sx, sy, dia_in / 2.0 * _INCH) is None:
                raise SolidWorksError(f"{name}: hole circle failed.")

    return draw


def _outline(points, name: str):
    def draw(manager, to_sketch):
        pts = [to_sketch(p) for p in points]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1], strict=True):
            if manager.CreateLine(ax, ay, 0.0, bx, by, 0.0) is None:
                raise SolidWorksError(f"{name}: edge failed.")

    return draw


def _holes_through(model, plane_point, normal, points, dia_in: float, depth_in: float, name: str) -> None:
    sketch = _sketch_through(model, plane_point, normal, f"{name}Holes", _hole_pair(points, dia_in, name))
    if s._cut_both_ways(model, sketch, depth_in) is None:
        raise SolidWorksError(f"{name}: its bolt holes were not cut.")


def _shell_bolts(end) -> list[tuple[float, float, float]]:
    y_mid = end.top - CHANNEL_IN / 2.0
    return [end.world(C_FACE_IN, SHELL_BOLT_OUT_IN, y_mid + dy) for dy in (SHELL_BOLT_SPACE_IN / 2.0,
                                                                          -SHELL_BOLT_SPACE_IN / 2.0)]


def build_tab(model, end, name: str) -> None:
    """3/8 tab square to the inner channel's web back, out toward the shell, with its two bolt holes."""
    c0, c1 = TAB_FROM_END_IN, C_FACE_IN
    y0, y1 = end.top - CHANNEL_IN, end.top
    y_mid = (y0 + y1) / 2.0
    corners = [end.world(c, 0.0, y) for c, y in ((c0, y0), (c1, y0), (c1, y1), (c0, y1))]
    sketch = _sketch_through(model, end.world((c0 + c1) / 2.0, 0.0, y_mid), (end.inward[0], 0.0, end.inward[1]),
                             name, _outline(corners, name))
    _extrude_to(model, sketch, TAB_OUT_IN, end.world((c0 + c1) / 2.0, TAB_OUT_IN / 2.0, y_mid), CHANNEL_IN + 0.1,
                name)
    _holes_through(model, _shell_bolts(end)[0], (end.along[0], 0.0, end.along[1]), _shell_bolts(end), HOLE_DIA_IN,
                   TAB_THK_IN + 0.05, name)


def build_shell_clip(model, end, shell_r: float, name: str) -> None:
    """3/8 shell clip on the tab's face toward the platform middle, from just short of the web out to the pad."""
    h0, h1 = SHELL_CLIP_SHORT_IN, clip_reach(end, shell_r)
    y0, y1 = end.top - CHANNEL_IN, end.top
    y_mid = (y0 + y1) / 2.0
    corners = [end.world(C_FACE_IN, h, y) for h, y in ((h0, y0), (h1, y0), (h1, y1), (h0, y1))]
    along = (end.along[0], 0.0, end.along[1])
    sketch = _sketch_through(model, end.world(C_FACE_IN, (h0 + h1) / 2.0, y_mid), along, name,
                             _outline(corners, name))
    _extrude_to(model, sketch, SHELL_CLIP_THK_IN,
                end.world(C_FACE_IN + SHELL_CLIP_THK_IN / 2.0, (h0 + h1) / 2.0, y_mid), CHANNEL_IN + 0.1, name)
    _holes_through(model, _shell_bolts(end)[0], along, _shell_bolts(end), HOLE_DIA_IN, SHELL_CLIP_THK_IN + 0.05,
                   name)


def build_pad(model, phi: float, y: float, shell_r: float, name: str) -> None:
    """1/4 x 4 x 6 pad with full-radius ends, flat on the shell at its middle."""
    radial = _radial(phi)

    def draw(manager, to_sketch):
        _draw_pad(manager, lambda t, yy: to_sketch(_world(phi, shell_r, t, yy)), 0.0, y, SHELL_PAD_TALL_IN, name)

    sketch = _sketch_through(model, _world(phi, shell_r, 0.0, y), radial, name, draw)
    _extrude_to(model, sketch, SHELL_PAD_THK_IN, _world(phi, shell_r + SHELL_PAD_THK_IN / 2.0, 0.0, y),
                SHELL_PAD_TALL_IN + 0.1, name)


def build_hanger(model, frame, knee, back: float, top: float, name: str) -> None:
    """3/8 hanger under the outer channel (platform_sw._hanger), with the knee's top bolt hole."""
    _hanger(model, frame, back, top, knee.side, name)
    r1, y1 = knee.top
    point = frame.world(r1, 0.0, y1)
    _holes_through(model, point, frame.travel, [point], KNEE_HOLE_DIA_IN, HANGER_THK_IN + 0.1, name)


def build_knee(model, frame, knee, profile: str, name: str) -> None:
    """The L3x3x3/8 knee brace (brace_sw._knee_angle), with both bolt holes through its flat leg."""
    _knee_angle(model, frame, knee, profile, name)
    t_in = knee.t_face + knee.side * LEG_THK_IN
    centres = [frame.world(r, t_in, y) for r, y in (knee.top, knee.bottom)]
    _holes_through(model, centres[0], frame.travel, centres, KNEE_HOLE_DIA_IN, LEG_THK_IN + 0.1, name)


def build_knee_clip(model, frame, knee, name: str) -> None:
    """1/4 x 7 x 4 clip on the shell pad, in line with the knee's flat leg, with its bolt hole."""
    r2, y2 = knee.bottom
    t_mid, _y = knee_pad(knee)
    root = knee.shell_r + SHELL_PAD_THK_IN
    half = KNEE_CLIP_TALL_IN / 2.0
    corners = [frame.world(r, knee.t_face, y) for r, y in ((root, y2 - half), (root + KNEE_CLIP_OUT_IN, y2 - half),
                                                          (root + KNEE_CLIP_OUT_IN, y2 + half), (root, y2 + half))]
    sketch = _sketch_through(model, frame.world(r2, knee.t_face, y2), frame.travel, name, _outline(corners, name))
    _extrude_to(model, sketch, KNEE_CLIP_THK_IN, frame.world(root + KNEE_CLIP_OUT_IN / 2.0, t_mid, y2),
                KNEE_CLIP_TALL_IN + 0.1, name)
    point = frame.world(r2, knee.t_face, y2)
    _holes_through(model, point, frame.travel, [point], KNEE_HOLE_DIA_IN, KNEE_CLIP_THK_IN + 0.1, name)


def clip_frame(lines, side: str, label: str) -> tuple[float, float, float, float, float]:
    """(line angle, heel radius, inward, away, hole height) of the L6x6 stringer clip at ``side`` (A or B) on the
    ``label`` (In or Out) stringer, as platform_sw.add_stringer_clips sets it."""
    line_phi = lines.phi_a if side == "A" else lines.phi_b
    away = -1.0 if side == "A" else 1.0  # along the travel, from the channel to that flight
    sag = CLIP_LEG_IN * CLIP_LEG_IN / (2.0 * lines.stringer_b) + 0.001
    heel_r, inward = (lines.r_a, 1.0) if label == "In" else (lines.stringer_b - sag, -1.0)
    return line_phi, heel_r, inward, away, lines.top - HOLE_DOWN_IN


def build_stringer_clip(model, lines, side: str, label: str, profile: str, name: str) -> None:
    """The L6x6x3/8 clip (platform_sw._clip) with its web leg's two holes, which land in the channel web's rounds or
    slots, and its stringer leg's two, on the stringer's end holes."""
    line_phi, heel_r, inward, away, hole_y = clip_frame(lines, side, label)
    _clip(model, line_phi, heel_r, inward, away, lines.top, profile, name)
    gauges = [lines.r_a + g for g in CLIP_GAUGES_IN] if label == "In" else [lines.stringer_b - g
                                                                           for g in CLIP_GAUGES_IN]
    web = [_world(line_phi, r, 0.0, hole_y) for r in gauges]
    _holes_through(model, web[0], _travel(line_phi), web, HOLE_DIA_IN, CLIP_THK_IN + 0.05, f"{name}WebLeg")
    leg = [_world(line_phi, heel_r + inward * CLIP_THK_IN, away * g, hole_y) for g in CLIP_GAUGES_IN]
    _holes_through(model, leg[0], _radial(line_phi), leg, HOLE_DIA_IN, CLIP_THK_IN + 0.05, f"{name}StringerLeg")


def web_holes(model, lines, side: str, name: str) -> None:
    """The rounds (inner stringer) and slots (outer) in the radial channel's web at ``side``, where the stringer
    clips bolt (platform_sw._web_holes, on the channel's own part)."""
    line_phi = lines.phi_a if side == "A" else lines.phi_b
    if not _web_holes(model, lines, line_phi, lines.top - HOLE_DOWN_IN, name):
        raise SolidWorksError(f"{name}: the stringer clip holes were not cut in the channel web.")


def clip_sides(k: int, mid_platforms: int) -> tuple[str, ...]:
    """Where the stringers meet platform ``k`` (1 the lowest): both radial ends on a mid platform, A only on the top
    one, as stair_sw._platforms puts the clips."""
    return ("A", "B") if k <= mid_platforms else ("A",)


def clip_jobs(job, platforms: list, mid_platforms: int, turn: float, profile: str) -> list:
    """The stringer clips of the whole stair: one file per side and stringer (A In, A Out, B In, B Out), modelled at
    the first platform that has it and turned about the tank axis and lifted to the rest; every platform's are the
    same pieces."""
    out = []
    for side in ("A", "B"):
        mine = [(k, lines) for k, lines in platforms if side in clip_sides(k, mid_platforms)]
        if not mine:
            continue
        k0, head = mine[0]
        angle0 = head.phi_a if side == "A" else head.phi_b
        places = tuple(Placement(turn + (lines.phi_a if side == "A" else lines.phi_b) - angle0,
                                 (0.0, lines.top - head.top, 0.0)) for _k, lines in mine)
        for label in ("In", "Out"):
            out.append(job(f"Stair Platform Clip {side} {label}.SLDPRT", f"Stringer clip {side} {label}",
                           lambda model, head=head, side=side, label=label, k0=k0:
                           build_stringer_clip(model, head, side, label, profile,
                                               f"ElitePlatform{k0}Clip{side}{label}"),
                           places))
    return out


# ------------------------------------------------------------------------------------------------ the jobs


def support_jobs(job, k: int, lines, shell_r: float, turn: float, knee_file: str) -> list:
    """The PartJobs (``job`` the PartJob class) of platform ``k``'s tabs, shell clips, hangers, knees and knee
    clips; the pads are one job for the whole stair (``pad_job_placements``)."""
    supports = lines.supports()
    ends = _channel_ends(lines)
    knees = platform_knees(lines, shell_r)
    out = []
    for tag, members in support_groups(lines):
        head = members[0]
        angle0 = supports[head][1]
        if lines.rolled:
            places = tuple(Placement(turn + supports[i][1] - angle0) for i in members)
        else:
            places = (Placement(turn),)
        suffix = f" {tag}" if tag else ""
        stem = f"Stair Platform {k}"
        end, (_label, frame, knee, back) = ends[head], knees[head]
        name = f"ElitePlatform{k}{supports[head][0]}"
        out += [
            job(f"{stem} Tab{suffix}.SLDPRT", f"Platform {k} tab{suffix}",
                lambda model, end=end, name=name: build_tab(model, end, f"{name}Tab"), places),
            job(f"{stem} Shell Clip{suffix}.SLDPRT", f"Platform {k} shell clip{suffix}",
                lambda model, end=end, name=name: build_shell_clip(model, end, shell_r, f"{name}ShellClip"), places),
            job(f"{stem} Hanger{suffix}.SLDPRT", f"Platform {k} hanger{suffix}",
                lambda model, frame=frame, knee=knee, back=back, name=name:
                build_hanger(model, frame, knee, back, lines.top, f"{name}Hanger"), places),
            job(f"{stem} Knee{suffix}.SLDPRT", f"Platform {k} knee brace{suffix}",
                lambda model, frame=frame, knee=knee, name=name: build_knee(model, frame, knee, knee_file,
                                                                           f"{name}Knee"), places),
            job(f"{stem} Knee Clip{suffix}.SLDPRT", f"Platform {k} knee clip{suffix}",
                lambda model, frame=frame, knee=knee, name=name: build_knee_clip(model, frame, knee,
                                                                                f"{name}KneeClip"), places),
        ]
    return out

