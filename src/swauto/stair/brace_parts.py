"""The stair's braces and inner clips as parts (partify, 2026-10-30): under a tread, the L3x3 cross brace from
stringer to stringer with a cap in each end and the 45 degree knee brace from its leg hole down to a clip and pad on
the shell; above a tread, the inner clip, an L4x3 on the inner stringer bolted to a landing clip on a shell pad.

As brace_sw and inner_clip_sw build them, from the tread's own numbers instead of the treads read off the part
(``tread_frame``, ``inner_clip``). A brace is the same piece under every tread, so each piece is one part modelled at
a seat tread and placed turned about the tank axis and lifted to every one. A bolt hole the one-part build cuts
through a cap or a clip and a stringer at once is cut in both parts: ``stringer_holes`` are the stringers' halves.
"""

from __future__ import annotations

import math

from swauto.errors import SolidWorksError
from swauto.stair import brace_sw as b
from swauto.stair import inner_clip_sw as ic
from swauto.stair.grab_sw import _sketch_through
from swauto.stair.platform_parts import _holes_through, _outline, build_knee, build_knee_clip
from swauto.stair.platform_sw import _world
from swauto.stair.stringer import THICKNESS_IN, TREAD_MARK_IN


def tread_frame(where, place) -> b._Frame:
    """Under the tread at ``place``: its centreline angle, the brace's top, and the two stringers' walk faces, as
    brace_sw._frame reads them off the part."""
    layout = where.layout
    return b._Frame(phi=place.phi, y_top=place.y0 - b.DROP_IN, r_a=layout.inner_face_in,
                    r_b=layout.inner_face_in + layout.clear_in)


def knee_layout(frame: b._Frame, shell_r: float) -> b._Knee:
    return b._knee_layout(frame, shell_r)


def _cap_numbers(frame: b._Frame, face_r: float, inward: float):
    cap_back = face_r + inward * b.CAP_THK_IN
    top = frame.y_top - b.LEG_THK_IN
    return cap_back, top, top - b.CAP_IN, frame.y_top - b.LEG_THK_IN - b.CAP_IN / 2.0


def cap_hole(frame: b._Frame, side: str):
    """(centre on the stringer's walk face, axis) of the 13/16 hole through a cap and its stringer: the inner
    stringer's ("In") or the outer's ("Out"), as brace_sw._hole cuts it."""
    face_r = frame.r_a if side == "In" else frame.r_b
    _back, _top, _bottom, y_center = _cap_numbers(frame, face_r, 1.0 if side == "In" else -1.0)
    return frame.world(face_r, 0.0, y_center), frame.radial


def build_cross_brace(model, frame: b._Frame, profile: str, name: str) -> None:
    """The L3x3 from walk face to walk face, flat leg on top under the tread (brace_sw._angle), with the knee's
    bolt hole in its down leg (brace_sw._leg_hole)."""
    b._angle(model, frame, profile, name)
    if not b._leg_hole(model, frame, f"{name}LegHole"):
        raise SolidWorksError(f"{name}: the knee brace's hole was not cut in the down leg.")


def build_cap(model, frame: b._Frame, side: str, name: str) -> None:
    """The 3/8 cap nested in the L at one end (brace_sw._cap), its clipped corner by the down leg, with its hole."""
    face_r, inward = (frame.r_a, 1.0) if side == "In" else (frame.r_b, -1.0)
    cap_back, top, bottom, y_center = _cap_numbers(frame, face_r, inward)
    half, k = b.CAP_IN / 2.0, b.LEG_SIDE
    corners = [frame.world(cap_back, t, y) for t, y in (
        (-k * half, top), (k * (half - b.CAP_CLIP_IN), top), (k * half, top - b.CAP_CLIP_IN), (k * half, bottom),
        (-k * half, bottom),
    )]
    sketch = _sketch_through(model, frame.world(cap_back, 0.0, y_center), frame.radial, f"{name}Sk",
                             _outline(corners, name))
    b._extrude_to(model, sketch, b.CAP_THK_IN, frame.world((face_r + cap_back) / 2.0, 0.0, y_center),
                  b.CAP_IN + 0.1, name)
    point, axis = cap_hole(frame, side)
    _holes_through(model, point, axis, [point], b.HOLE_DIA_IN, b.CAP_THK_IN + 0.1, f"{name}Hole")


def build_tread_knee(model, frame: b._Frame, knee: b._Knee, profile: str, name: str) -> None:
    """The knee brace: L3x3 at 45 degrees with its two bolt holes (platform_parts.build_knee)."""
    build_knee(model, frame, knee, profile, name)


def build_tread_knee_clip(model, frame: b._Frame, knee: b._Knee, name: str) -> None:
    """The 1/4 x 7 x 4 clip on the shell pad, in line with the knee's flat leg, with its bolt hole."""
    build_knee_clip(model, frame, knee, name)


def knee_pad_centre(frame: b._Frame, knee: b._Knee) -> tuple[float, float]:
    """(plan angle, height) of a knee's shell pad middle, where the shared shell pad goes."""
    t_mid, y = b.knee_pad(knee)
    point = frame.world(knee.shell_r, t_mid, y)
    return math.atan2(-point[0], point[2]), y


# ------------------------------------------------------------------------------------------------- inner clips


def inner_clip(where, index: int, shell_r: float) -> ic._Clip:
    """The inner clip above tread ``index`` (1 the lowest), as inner_clip_sw._layout lays it out from the part's
    treads."""
    layout = where.layout
    places = where.places
    place = places[index - 1]
    if index in flight_top_treads(where):
        raise SolidWorksError(f"Tread {index} is the top of its flight: the inner stringer stops there.")
    r_a = layout.inner_face_in
    low, high = next((p, q) for p, q in zip(places, places[1:], strict=False) if q.y0 - p.y0 > 0.01)
    tan_p = (high.y0 - low.y0) / math.remainder(high.phi - low.phi, 2.0 * math.pi) / r_a
    tank_face = r_a - THICKNESS_IN
    reach = max(ic.HEEL_FROM_HOLE_IN, ic.SHORT_LEG_IN - ic.HEEL_FROM_HOLE_IN)
    sag = reach * reach / (2.0 * tank_face) + 0.001
    if tank_face - shell_r < ic.MIN_GAP_IN:
        raise SolidWorksError(f"The gap is {tank_face - shell_r:.2f} in; the inner clip's 4 in leg needs at least "
                              f"{ic.MIN_GAP_IN:g} in.")
    return ic._Clip(phi=ic.clip_phi(place.phi, r_a, tan_p), heel_r=tank_face - sag, tank_face=tank_face,
                    shell_r=shell_r, y0=place.y0 + TREAD_MARK_IN)


def flight_top_treads(where) -> set[int]:
    """Treads at the top of a flight (no inner stringer plate above them), as brace_sw.flight_tops reads them."""
    return b.flight_tops([place.y0 for place in where.places])


def inner_stringer_holes(clip: ic._Clip):
    """(points, axis) of the clip's two holes through its 3 in leg and the inner stringer."""
    return [clip.world(clip.tank_face, 0.0, y) for y in clip.hole_ys], clip.radial


def build_inner_angle(model, clip: ic._Clip, profile: str, name: str) -> None:
    """The L4x3 on the inner stringer's tank face (inner_clip_sw._clip_angle), with its stringer and landing holes."""
    ic._clip_angle(model, clip, profile, name)
    back = clip.heel_r - ic.LEG_THK_IN
    points = [clip.world(back, 0.0, y) for y in clip.hole_ys]
    _holes_through(model, points[0], clip.radial, points, ic.HOLE_DIA_IN, ic.LEG_THK_IN + 0.1, f"{name}Holes")
    _landing_holes(model, clip, f"{name}LandingHoles")


def _landing_holes(model, clip: ic._Clip, name: str) -> None:
    face_t = ic.HEEL_FROM_HOLE_IN + ic.LANDING_THK_IN
    r = clip.heel_r - ic.LANDING_HOLE_IN
    points = [clip.world(r, face_t, y) for y in clip.hole_ys]
    _holes_through(model, points[0], clip.travel, points, ic.HOLE_DIA_IN, ic.LANDING_THK_IN + ic.LEG_THK_IN + 0.06,
                   name)


def build_landing(model, clip: ic._Clip, name: str) -> None:
    """The 3/8 landing clip on the 4 in leg's uphill face, from the pad to 1/2 in short of the stringer, with its
    two holes (inner_clip_sw._landing_and_pad, _landing_holes)."""
    heel_t = ic.HEEL_FROM_HOLE_IN
    root = clip.shell_r + ic.PAD_THK_IN
    tip = clip.tank_face - ic.LANDING_SHORT_IN
    corners = [clip.world(r, heel_t, y) for r, y in ((root, clip.y0), (tip, clip.y0), (tip, clip.y0 + ic.TALL_IN),
                                                     (root, clip.y0 + ic.TALL_IN))]
    sketch = _sketch_through(model, clip.world((root + tip) / 2.0, heel_t, clip.y_mid), clip.travel, f"{name}Sk",
                             _outline(corners, name))
    b._extrude_to(model, sketch, ic.LANDING_THK_IN, clip.world((root + tip) / 2.0, clip.landing_t, clip.y_mid),
                  ic.TALL_IN + 0.1, name)
    _landing_holes(model, clip, f"{name}Holes")


def build_inner_pad(model, clip: ic._Clip, name: str) -> None:
    """The 1/4 x 4 x 8 shell pad behind the landing clip, full-radius ends."""
    root = clip.shell_r + ic.PAD_THK_IN

    def draw(manager, to_sketch):
        b._draw_pad(manager, lambda t, y: to_sketch(clip.world(root, t, y)), clip.landing_t, clip.y_mid,
                    ic.PAD_TALL_IN, name)

    sketch = _sketch_through(model, clip.world(root, clip.landing_t, clip.y_mid), clip.radial, f"{name}Sk", draw)
    b._extrude_to(model, sketch, ic.PAD_THK_IN, clip.world(clip.shell_r + ic.PAD_THK_IN / 2.0, clip.landing_t,
                                                           clip.y_mid), ic.PAD_TALL_IN + 0.1, name)


def build_tall_pad(model, tall: float, shell_r: float, name: str) -> None:
    """A 1/4 x 4 shell pad ``tall`` inches tall with full-radius ends, flat on the shell at its middle at angle 0 and
    height 0: the inner clips' 8 in pad (the knees' 6 in one is platform_parts' shell pad)."""
    def draw(manager, to_sketch):
        b._draw_pad(manager, lambda t, y: to_sketch(_world(0.0, shell_r, t, y)), 0.0, 0.0, tall, name)

    sketch = _sketch_through(model, _world(0.0, shell_r, 0.0, 0.0), (0.0, 0.0, 1.0), name, draw)
    b._extrude_to(model, sketch, ic.PAD_THK_IN, _world(0.0, shell_r + ic.PAD_THK_IN / 2.0, 0.0, 0.0), tall + 0.1,
                  name)


# ---------------------------------------------------------------------------------------------------- the jobs


def brace_holes(where, braces, inner_clips, shell_r: float) -> dict[str, list]:
    """The braces' and inner clips' bolt holes through the stringers, by stringer ("In", "Out"): (index of the tread
    whose flight it is in, points, axis) each."""
    out: dict[str, list] = {"In": [], "Out": []}
    for index in braces:
        frame = tread_frame(where, where.places[index - 1])
        for side in ("In", "Out"):
            point, axis = cap_hole(frame, side)
            out[side].append((index, [point], axis))
    for index in inner_clips:
        points, axis = inner_stringer_holes(inner_clip(where, index, shell_r))
        out["In"].append((index, points, axis))
    return out


def brace_jobs(job, where, braces, knees: bool, inner_clips, shell_r: float, angle_file: str, clip_file: str,
               common: dict, place) -> tuple[list, list]:
    """The PartJobs of the cross braces (with their knees) under ``braces`` and the inner clips above
    ``inner_clips`` (tread indexes, 1 the lowest): each piece modelled at the stair's first tread and put at every
    tread that has it. Also returns the knees' shell pad middles (plan angle, height) for the shared shell pad."""
    out, pads = [], []
    places = where.places
    if braces:
        seat = places[0]
        frame = tread_frame(where, seat)
        moves = tuple(place(places[i - 1].phi - seat.phi, places[i - 1].y0 - seat.y0) for i in braces)
        params = dict(common, shell_od=shell_r)
        out.append(job("Stair cross brace", "Cross brace", dict(params, piece="cross brace"),
                       lambda model: build_cross_brace(model, frame, angle_file, "EliteBrace"), moves))
        for side in ("In", "Out"):
            out.append(job("Stair cross brace cap", f"Cross brace cap {side.lower()}",
                           dict(params, piece=f"cap {side}"),
                           lambda model, side=side: build_cap(model, frame, side, f"EliteBraceCap{side}"), moves))
        if knees:
            knee = knee_layout(frame, shell_r)
            out.append(job("Stair knee brace", "Knee brace", dict(params, piece="knee"),
                           lambda model: build_tread_knee(model, frame, knee, angle_file, "EliteBraceKnee"), moves))
            out.append(job("Stair knee clip", "Knee brace clip", dict(params, piece="knee clip"),
                           lambda model: build_tread_knee_clip(model, frame, knee, "EliteBraceKneeClip"), moves))
            for i in braces:
                own = tread_frame(where, places[i - 1])
                pads.append(knee_pad_centre(own, knee_layout(own, shell_r)))
    if inner_clips:
        seat_index = min(inner_clips)
        seat = inner_clip(where, seat_index, shell_r)
        clips = [inner_clip(where, i, shell_r) for i in inner_clips]
        moves = tuple(place(c.phi - seat.phi, c.y0 - seat.y0) for c in clips)
        params = dict(common, shell_od=shell_r)
        out.append(job("Stair inner clip", "Inner clip angle", dict(params, piece="inner clip"),
                       lambda model: build_inner_angle(model, seat, clip_file, "EliteInnerClip"), moves))
        out.append(job("Stair inner clip landing", "Inner clip landing", dict(params, piece="landing"),
                       lambda model: build_landing(model, seat, "EliteInnerLanding"), moves))
        centres = [ic.clip_pad(c.phi, c.y0, shell_r) for c in clips]
        out.append(job("Stair inner clip pad", "Inner clip shell pad", dict(params, piece="inner pad"),
                       lambda model: build_tall_pad(model, ic.PAD_TALL_IN, shell_r, "EliteInnerPad"),
                       tuple(place(phi, y) for phi, y in centres)))
    return out, pads
