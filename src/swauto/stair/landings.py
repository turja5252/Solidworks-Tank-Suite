"""What the stair puts on the shell, worked out without SolidWorks: for the stretchout preview.

Every number comes from the functions the build itself uses (``stair_sw.stair_places``,
``brace_sw._knee_layout`` and ``knee_pad``, ``inner_clip_sw.clip_phi`` and ``clip_pad``,
``platform_sw.platform_lines``, ``platform_knees`` and ``shell_pads``), so the preview shows
where the build puts things. Angles are plan angles the nozzles' way (0 toward +Z, clockwise
seen from above) of the clockwise build; ``StairArrangement.world`` carries them through the
counterclockwise mirror and the turn to the orientation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swauto.errors import SolidWorksError
from swauto.stair.brace_sw import DROP_IN, PAD_TALL_IN, PAD_THK_IN, PAD_WIDE_IN, _Frame, _knee_layout, knee_pad
from swauto.stair.development import develop_both
from swauto.stair import knee2
from swauto.stair.inner_clip_sw import MIN_GAP_IN, clip_pad, clip_phi
from swauto.stair.inner_clip_sw import PAD_TALL_IN as CLIP_PAD_TALL_IN
from swauto.stair.platform_sw import (
    SHELL_PAD_THK_IN,
    TAB_OUT_IN,
    platform_knees,
    platform_lines,
    shell_pads,
)
from swauto.stair.sizing import world_angle
from swauto.stair.splitter import SplitSettings, joints
from swauto.stair.stair_sw import TREAD_CLEAR_IN, stair_places
from swauto.stair.stringer import CLEAR_IN, THICKNESS_IN, TREAD_DEPTH_IN, StringerMock

TREAD = "tread"
STRINGER = "stringer"
SPLICE = "stringer splice"
PLATFORM = "platform"
KNEE_PAD = "knee brace pad"
CLIP_PAD = "inner clip pad"
PLATFORM_PAD = "platform shell clip pad"
PLATFORM_KNEE_PAD = "platform knee brace pad"
PADS = (KNEE_PAD, CLIP_PAD, PLATFORM_PAD, PLATFORM_KNEE_PAD)


@dataclass(frozen=True)
class StairArrangement:
    """A stair as the Stairway tab describes it: the clockwise build, then where it goes."""

    stair: StringerMock
    platforms: int = 0
    top_platform: bool = False
    ground_in: float = 0.0
    turn: float = 0.0
    ccw: bool = False
    braces: tuple[int, ...] = ()
    knees: bool = True
    inner_clips: bool = True
    splits: SplitSettings | None = None
    clips: tuple[int, ...] | None = None  # the inner clips' pans when they are not the braces' (the rules)

    def world(self, angle: float) -> float:
        """A plan angle of the clockwise build, where it lands on the tank."""
        return world_angle(angle, self.turn, self.ccw)


@dataclass(frozen=True)
class Mark:
    """One stair item seen on the shell. ``outline`` is a closed run of (plan angle, y) points, or a pad is
    given by its ``center`` (plan angle, y) and ``size`` (width along the shell, height) with full-radius ends.
    Angles are the clockwise build's; pass them through ``StairArrangement.world``."""

    kind: str
    label: str
    outline: tuple[tuple[float, float], ...] = ()
    center: tuple[float, float] | None = None
    size: tuple[float, float] = (0.0, 0.0)


def shell_marks(arrangement: StairArrangement) -> tuple[list[Mark], list[str]]:
    """Treads, stringers and platforms projected onto the shell, and every pad that lands on it. Notes say
    what the build would refuse (no room for a clip, say), which the preview then leaves out."""
    stair = arrangement.stair
    shell_r = stair.shell_od_in
    where = stair_places(stair, shell_r, arrangement.platforms, arrangement.ground_in)
    layout, places, per_flight = where.layout, where.places, where.per_flight
    r_a = layout.inner_face_in
    r_b = r_a + layout.clear_in
    marks: list[Mark] = []
    notes: list[str] = []

    reach = math.atan2(TREAD_DEPTH_IN / 2.0, r_a + TREAD_CLEAR_IN)  # widest the tread looks from the axis
    for place in places:
        outline = _box(place.phi - reach, place.phi + reach, place.y0, place.y1)
        marks.append(Mark(TREAD, f"Tread {place.index}", outline))

    inner_dev, outer_dev = develop_both(where.flight)
    for k, (turn, lift) in enumerate(where.offsets):
        flight = f" (flight {k + 1})" if len(where.offsets) > 1 else ""
        for dev, side in ((inner_dev, "Inner"), (outer_dev, "Outer")):
            outline = tuple((turn + x / dev.radius_in, lift + y) for x, y in dev.outline)
            marks.append(Mark(STRINGER, f"{side} stringer{flight}", outline))
            if arrangement.splits is None:
                continue
            for joint in joints(dev, stair.rise_in, per_flight, arrangement.splits):
                plate = tuple((turn + x / dev.radius_in, lift + y) for x, y in joint.plate)
                marks.append(Mark(SPLICE, f"{side} stringer{flight} splice over tread {joint.tread}", plate))

    clips = arrangement.braces if arrangement.clips is None else arrangement.clips
    for wanted, mark_of, pans in ((arrangement.knees, knee_mark, arrangement.braces),
                                  (arrangement.inner_clips, clip_mark, clips)):
        for index in pans if wanted else ():
            if not 1 <= index <= len(places):
                notes.append(f"There is no tread {index} for a brace.")
                continue
            found = mark_of(where, arrangement.platforms, index)
            (notes if isinstance(found, str) else marks).append(found)

    for k in range(arrangement.platforms + (1 if arrangement.top_platform else 0)):
        lines, last = platform_frame(arrangement, where, k)
        name = platform_name(arrangement, k)
        marks.append(Mark(PLATFORM, f"{name} (after tread {last.index})",
                          _box(lines.phi_a, lines.phi_b, lines.top - lines.section.depth_in, lines.top)))
        found, said = platform_pad_marks(lines, shell_r, name)
        marks += found
        notes += said
    return marks, notes


def platform_frame(arrangement: StairArrangement, where, k: int):
    """Platform ``k``'s plan lines (0 the lowest, the top one after the mid ones), from ``stair_places``, and the
    tread it follows."""
    last = where.places[(k + 1) * where.per_flight - 1]
    r_a = where.layout.inner_face_in
    lines = platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN,
                           spec=arrangement.stair.platform(k))
    return lines, last


def platform_name(arrangement: StairArrangement, k: int) -> str:
    return "Top platform" if k >= arrangement.platforms else f"Platform {k + 1}"


def platform_pad_marks(lines, shell_r: float, name: str) -> tuple[list[Mark], list[str]]:
    """The shell pads of a platform's supports (both ends and every held radial between): a shell clip pad by each on
    the inner side and a knee brace pad under each on the outer side, and notes where the shell leaves no room."""
    marks: list[Mark] = []
    notes: list[str] = []
    if lines.r_in - shell_r < TAB_OUT_IN + SHELL_PAD_THK_IN + 0.5:
        notes.append(f"{name}: no room for its shell clips.")
    else:
        for label, angle, y in shell_pads(lines, shell_r):
            marks.append(Mark(PLATFORM_PAD, f"{name} shell clip pad {label}", center=(angle, y),
                              size=(PAD_WIDE_IN, lines.section.pad_tall_in)))
    try:
        knees = platform_knees(lines, shell_r)
    except SolidWorksError as exc:
        notes.append(f"{name}: {exc}")
        return marks, notes
    for label, frame, knee, _back in knees:
        t, y = knee2.pad_middle(knee) if lines.knee == 2 else knee_pad(knee)
        angle = frame.phi + math.atan2(t, shell_r + PAD_THK_IN)
        marks.append(Mark(PLATFORM_KNEE_PAD, f"{name} knee brace pad {label}", center=(angle, y),
                          size=(PAD_WIDE_IN, knee2.PAD_TALL_IN if lines.knee == 2 else PAD_TALL_IN)))
    return marks, notes


def knee_mark(where, platforms: int, index: int) -> Mark | str:
    """The shell pad of the knee brace under pan ``index`` (1 the lowest, every pan counted), from ``stair_places``,
    or why the build would refuse it."""
    shell_r = where.flight.shell_od_in
    r_a = where.layout.inner_face_in
    place = where.places[index - 1]
    frame = _Frame(phi=place.phi, y_top=place.y0 - DROP_IN, r_a=r_a, r_b=r_a + where.layout.clear_in)
    try:
        knee = _knee_layout(frame, shell_r)
    except SolidWorksError as exc:
        return f"Knee brace at tread {index}: {exc}"
    t, y = knee_pad(knee)
    return Mark(KNEE_PAD, f"Knee brace pad, tread {index}", center=(place.phi + math.atan2(t, shell_r + PAD_THK_IN), y),
                size=(PAD_WIDE_IN, PAD_TALL_IN))


def clip_mark(where, platforms: int, index: int) -> Mark | str:
    """The shell pad of the inner clip at pan ``index``, or why the build would refuse it: no clip at a flight's
    top tread, nor in a gap under ``MIN_GAP_IN``."""
    if index in {k * where.per_flight for k in range(1, platforms + 2)}:
        return f"No inner clip at tread {index}: it tops its flight."
    shell_r = where.flight.shell_od_in
    r_a = where.layout.inner_face_in
    if (r_a - THICKNESS_IN) - shell_r < MIN_GAP_IN:
        return f"No inner clip at tread {index}: the gap is under {MIN_GAP_IN:g} in."
    place = where.places[index - 1]
    angle, y = clip_pad(clip_phi(place.phi, r_a, _pitch(where.places, index, r_a)), place.y1, shell_r)
    return Mark(CLIP_PAD, f"Inner clip pad, tread {index}", center=(angle, y), size=(PAD_WIDE_IN, CLIP_PAD_TALL_IN))


STRAIGHT_CLEAR_IN = 1.0  # the least between a straight inner side and the shell


def platform_problems(arrangement: StairArrangement) -> list[str]:
    """What the platforms' shapes run into: straight sides on a platform long enough that its inner side bows in
    toward the shell between its ends, to within ``STRAIGHT_CLEAR_IN`` of it."""
    stair = arrangement.stair
    shell_r = stair.shell_od_in
    where = stair_places(stair, shell_r, arrangement.platforms, arrangement.ground_in)
    r_a = where.layout.inner_face_in
    problems = []
    for k in range(1, arrangement.platforms + (1 if arrangement.top_platform else 0) + 1):
        last = where.places[k * where.per_flight - 1]
        spec = stair.platform(k - 1)
        lines = platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN, spec=spec)
        if lines.rolled:
            continue
        clear = lines.r_in * math.cos((lines.phi_b - lines.phi_a) / 2.0) - shell_r  # at the straight side's middle
        if clear < STRAIGHT_CLEAR_IN:
            name = "The top platform" if k > arrangement.platforms else f"Platform {k}"
            problems.append(f"{name}: straight sides {spec.length_in:g} in long come within {clear:.2f} in of the "
                            "shell at the inner side's middle; roll them.")
    return problems


def _box(a0: float, a1: float, y0: float, y1: float) -> tuple[tuple[float, float], ...]:
    return ((a0, y0), (a1, y0), (a1, y1), (a0, y1))


def _pitch(places, index: int, r_a: float) -> float:
    """Slope of the inner stringer's top edge at its walk face: one step up the same flight, as the build reads
    it off the treads (a mid platform turns the stair without rising)."""
    low, high = next((a, b) for a, b in zip(places, places[1:], strict=False) if b.y0 - a.y0 > 0.01)
    return (high.y0 - low.y0) / (high.phi - low.phi) / r_a
