"""Stringer tab: build the formed helical plate in SolidWorks."""

from __future__ import annotations

import contextlib
import math
from dataclasses import replace
import tkinter as tk
from tkinter import messagebox, ttk

from swauto import runlog
from swauto.comutil import com_value, format_com_error
from swauto.errors import BuildStopped, SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.session import connect
from swauto.stair.brace_sw import (
    add_cross_brace,
    add_knee_brace,
    angle_profile,
    remove_cross_brace,
    stair_flight_tops,
)
from swauto.stair.development import MAX_PLATFORMS, flight_treads, stair_plan
from swauto.stair.grab_sw import GRAB_TOP_IN, GrabRail
from swauto.stair.inner_clip_sw import add_inner_clip, clip_angle_profile
from swauto.stair.landings import StairArrangement
from swauto.stair.post_sw import PLATFORM_POST_IN, RAIL_TOP_IN, read_post_treads
from swauto.stair.rail_sw import PLATFORM_MID_TOP_IN, check_platform_mid_top
from swauto.stair.splitter import HOLE_ROW_IN as SPLIT_HOLE_ROW_IN
from swauto.stair.splitter import LIMIT as SPLIT_LIMIT
from swauto.stair.splitter import MAX_SPAN_FT as SPLIT_MAX_SPAN_FT
from swauto.stair.splitter import SEGMENT_COUNT as SPLIT_SEGMENTS_DEFAULT
from swauto.stair.splitter import SEGMENTS as SPLIT_SEGMENTS
from swauto.stair.splitter import SplitSettings
from swauto.stair.sizing import (
    AUTO_RISE_IN,
    auto_treads,
    end_angles,
    orientation_deg,
    placement_turn,
    rise_run,
    slopes_deg,
    stair_height_in,
    tread_lap_in,
    world_angle,
)
from swauto.stair.stringer import (
    CLEAR_IN,
    THICKNESS_IN,
    TREAD_DEPTH_IN,
    TREAD_MARK_IN,
    TREAD_WIDTHS_IN,
    StringerLayout,
    StringerMock,
    layout_stringer,
)
from swauto.stair.stair_sw import create_stair as build_stair
from swauto.stair.stair_sw import flight_suffix, is_counterclockwise, mirror_stair, split_joints, turn_stair
from swauto.stair.stringer_sw import create_stringer_try
from swauto.stair.tread_joint import TreadJointSpec, layout_tread_joint
from swauto.stair.tread_joint_sw import create_tread_joint
from swauto.tank.follow import follow_tank
from swauto.tank.profile import course_radii_m

_PLAN = 280
CLOCKWISE = "cw"
COUNTERCLOCKWISE = "ccw"
START = "start"
END = "end"


def _tank_od_radius_in(shared: dict | None) -> float | None:
    """Shell OD radius of the tank on the Tank Properties tab, if it has one."""
    if not shared:
        return None
    tank = shared.get("spec")
    if tank is None:
        return None
    try:
        outer_m, _inner_m = course_radii_m(tank, tank.active_courses()[0])
    except Exception:  # noqa: BLE001
        return None
    return outer_m / 0.0254


def _fmt_num(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _offset_text(offset_in: float, where: str) -> str:
    """Where an end sits for its offset, + down: "at the floor", "6 in below the floor"."""
    if abs(offset_in) < 1e-9:
        return f"at {where}"
    return f"{_fmt_num(abs(offset_in))} in {'below' if offset_in > 0 else 'above'} {where}"


def slope_deg(rise_in: float, run_in: float) -> float:
    """Stair slope in degrees. Angle = atan(rise / run)."""
    return math.degrees(math.atan(rise_in / run_in))


def parse_brace_treads(text: str) -> tuple[int, ...]:
    """Tread numbers for cross braces, like "2, 5". Tread 1 is the lowest. Blank is none."""
    picks: set[int] = set()
    for part in text.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            number = float(part)
        except ValueError as exc:
            raise ValueError(f"Brace treads are tread numbers like 2, 5 (not {part!r}).") from exc
        if number != int(number) or number < 1:
            raise ValueError("Brace treads are whole tread numbers, 1 or more.")
        picks.add(int(number))
    return tuple(sorted(picks))


def _progress_percent(done: int, total: int) -> int:
    if total <= 0 or done <= 0:
        return 0
    if done >= total:
        return 100
    return (100 * done) // total


def _inner_clip(model, index: int, tops: set[int], profile: str, shell_radius_in, progress) -> str:
    """Inner clip at a braced tread. The top tread of a flight has no stringer above it, so it gets none."""
    if index in tops:
        return f"No inner clip at tread {index}: it tops its flight, and the inner stringer stops at its top."
    return add_inner_clip(model, index, profile, shell_radius_in=shell_radius_in, progress=progress).note


def _flight_tops(treads: int, platforms: int) -> set[int]:
    per_flight = flight_treads(treads, platforms)
    return {k * per_flight for k in range(1, platforms + 2)}


def _brace_stage_plan(
    braces, *, knees: bool = False, inner: bool = False, tops: set[int] | frozenset[int] = frozenset()
) -> list[tuple[frozenset[str], str]]:
    """Four shares per brace (angle, each cap with its hole, leg hole), three more per knee,
    three more per inner clip. ``tops`` are the treads that end a flight, which get no inner clip."""
    plan: list[tuple[frozenset[str], str]] = []
    for index in braces:
        key = f"EliteBrace{index:02d}"
        plan.append((frozenset({f"{key} angle placed"}), f"brace {index} angle"))
        plan.append((frozenset({f"{key} in cap placed"}), f"brace {index} inner cap"))
        plan.append((frozenset({f"{key} out cap placed"}), f"brace {index} outer cap"))
        plan.append((frozenset({f"{key} leg hole cut", f"{key} leg hole missed"}), f"brace {index} leg hole"))
        if knees:
            knee = f"{key}Knee"
            plan.append((frozenset({f"{knee} angle placed"}), f"knee brace {index}"))
            plan.append((frozenset({f"{knee} clip placed"}), f"knee brace {index} clip and pad"))
            plan.append((frozenset({f"{knee} holes cut", f"{knee} holes missed"}), f"knee brace {index} holes"))
        if inner and index not in tops:
            clip = f"{key}Inner"
            plan.append((frozenset({f"{clip} angle placed"}), f"inner clip {index}"))
            plan.append((frozenset({f"{clip} landing clip placed"}), f"inner clip {index} landing clip and pad"))
            plan.append((frozenset({f"{clip} holes cut", f"{clip} holes missed"}), f"inner clip {index} holes"))
    return plan


def _stair_stage_plan(
    treads: int, *, shell: bool = True, braces=(), knees: bool = False, inner: bool = False,
    platforms: int = 0, top_platform: bool = False, posts=(), top_rail: bool = False, mid_rail: bool = False,
    grab: bool = False, ccw: bool = False, turned: bool = False, split_treads: tuple[int, ...] = (),
) -> list[tuple[frozenset[str], str]]:
    """One equal share per progress line the stair build actually emits.

    Missed holes and missed bolts are the same stage as a clean cut, so a
    miss moves the percent forward and never back. Without the tank, the
    shell stage is left out; the stringers are unchanged. Mid platforms add
    a flight of stringers each, the extra pan level with each platform, the
    platform frames, and their clips. ``posts`` are tread numbers in a flight.
    A counterclockwise stair ends with its mirror and the clockwise one's delete, and a
    stair turned to its orientation with the turn. ``split_treads`` are each flight's splitter
    joints (their lower treads), cut on both stringers after the bolts.
    """
    per_flight = flight_treads(treads, platforms)
    plan: list[tuple[frozenset[str], str]] = []
    if shell:
        plan.append((frozenset({"shell built"}), "shell"))
    for flight in range(platforms + 1):
        suffix = flight_suffix(flight)
        where = f" (flight {flight + 1})" if platforms else ""
        sides = ((f"EliteStringerIn{suffix}", f"inner{where}"), (f"EliteStringerOut{suffix}", f"outer{where}"))
        for key, side in sides:
            plan.append((frozenset({f"{key} rolled"}), f"{side} stringer rolled"))
        for key, side in sides:
            plan.append((frozenset({f"{key} top edge cut"}), f"{side} stringer top edge"))
            plan.append((frozenset({f"{key} 9 in edge cut"}), f"{side} stringer 9 in edge"))
            plan.append((frozenset({f"{key} ends formed"}), f"{side} stringer cut"))
        for key, side in sides:
            plan.append(
                (frozenset({f"{key} end holes cut", f"{key} end holes missed"}), f"{side} connecting holes")
            )
    pans = per_flight * (platforms + 1)
    for index in range(1, pans + 1):
        plan.append((frozenset({f"tread {index} placed"}), f"tread {index}"))
        for side in ("in", "out"):
            plan.append(
                (
                    frozenset(
                        {
                            f"tread {index} {side} bolts through",
                            f"tread {index} {side} bolts missed",
                        }
                    ),
                    f"tread {index} {side} bolts",
                )
            )
    for flight in range(platforms + 1) if split_treads else ():
        for side in ("In", "Out"):
            name = f"EliteSplit{side}{flight_suffix(flight)}"
            where = f" (flight {flight + 1})" if platforms else ""
            for tread in split_treads:
                plan.append((frozenset({f"{name}T{tread:02d} cut"}), f"{side.lower()}er stringer split{where}"))
                plan.append((frozenset({f"{name}T{tread:02d} splice placed"}), f"splice plate{where}"))
            plan.append((frozenset({f"{name} splices trimmed"}), f"splice plates trimmed{where}"))
            for tread in split_treads:
                plan.append((frozenset({f"{name}T{tread:02d} holes cut", f"{name}T{tread:02d} holes missed"}),
                             f"splice holes{where}"))
    for k in range(1, platforms + 1 + (1 if top_platform else 0)):
        key = f"ElitePlatform{k * per_flight:02d}"
        plan.append((frozenset({f"{key} frame placed"}), f"platform after tread {k * per_flight}"))
        for side in ("A", "B") if k <= platforms else ("A",):
            plan.append((frozenset({f"{key}Clip{side} angles placed"}), f"platform clips {k * per_flight}{side}"))
            plan.append(
                (frozenset({f"{key}Clip{side} holes cut", f"{key}Clip{side} holes missed"}),
                 f"platform clip holes {k * per_flight}{side}")
            )
        for end in ("A", "B"):
            plan.append((frozenset({f"{key}Shell{end} clip placed"}), f"platform shell clip {k * per_flight}{end}"))
        for end in ("A", "B"):
            plan.append((frozenset({f"{key}Knee{end} placed"}), f"platform knee brace {k * per_flight}{end}"))
    for index in (k * per_flight + pick for k in range(platforms + 1) for pick in posts):
        key = f"ElitePost{index:02d}"
        plan.append((frozenset({f"{key} placed"}), f"handrail post {index}"))
        plan.append((frozenset({f"{key} holes cut", f"{key} holes missed"}), f"handrail post {index} holes"))
    for k in range(1, platforms + 1 + (1 if top_platform else 0)) if posts else ():
        for end in ("A", "B"):
            key = f"ElitePlatform{k * per_flight:02d}Post{end}"
            plan.append((frozenset({f"{key} placed"}), f"platform post {k * per_flight}{end}"))
            plan.append(
                (frozenset({f"{key} holes cut", f"{key} holes missed"}), f"platform post holes {k * per_flight}{end}")
            )
    for k in range(1, platforms + 1 + (1 if top_platform else 0)) if posts else ():
        plan.append((frozenset({f"ElitePlatform{k * per_flight:02d}Toe placed"}), f"toe plate {k * per_flight}"))
    landings = platforms + (1 if top_platform else 0)
    for run, label, wanted in (("Rail", "top rail", top_rail), ("Mid", "midrail", mid_rail)):
        for k in range(platforms + 1) if wanted and posts else ():
            plan.append((frozenset({f"Elite{run}F{k + 1} placed"}), f"{label} flight {k + 1}"))
            if k < landings:
                key = f"ElitePlatform{(k + 1) * per_flight:02d}{run}"
                for end in ("A", "B") if k < platforms else ("A",):
                    plan.append((frozenset({f"{key}{end} placed"}), f"{label} landing {(k + 1) * per_flight}{end}"))
                plan.append((frozenset({f"{key} placed"}), f"platform {label} {(k + 1) * per_flight}"))
    if top_rail and mid_rail and posts:
        plan.append((frozenset({"EliteRailBottomEnd placed"}), "rail end at the foot"))
    for k in range(platforms + 1) if grab and posts else ():
        plan.append((frozenset({f"EliteGrabF{k + 1} placed"}), f"grab rail flight {k + 1}"))
    for index in (k * per_flight + pick for k in range(platforms + 1) for pick in posts) if grab else ():
        key = f"EliteGrabBracket{index:02d}"
        plan.append((frozenset({f"{key} placed", f"{key} skipped"}), f"grab rail connector {index}"))
    plan.extend(_brace_stage_plan(braces, knees=knees, inner=inner, tops=_flight_tops(treads, platforms)))
    if ccw:
        plan.append((frozenset({"stair mirrored"}), "counterclockwise mirror"))
        plan.append((frozenset({"clockwise stair deleted"}), "clockwise stair deleted"))
    if turned:
        plan.append((frozenset({"stair turned"}), "turned to its orientation"))
    return plan


def build_stringer_tab(parent: ttk.Frame, status_var: tk.StringVar, shared: dict | None = None) -> None:
    spec = StringerMock()
    tank_radius = _tank_od_radius_in(shared)
    if tank_radius is not None:
        spec = StringerMock(shell_od_in=round(tank_radius, 4))
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    scroller = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=scroller.yview)
    scroller.configure(yscrollcommand=scrollbar.set)
    scroller.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")
    top = ttk.Frame(scroller, padding=12)
    top_id = scroller.create_window((0, 0), window=top, anchor="nw")
    scroller.bind("<Configure>", lambda event: scroller.itemconfigure(top_id, width=event.width))
    top.bind("<Configure>", lambda _event: scroller.configure(scrollregion=scroller.bbox("all")))

    ttk.Label(top, text="Spiral stringer", font=("", 11, "bold")).grid(row=0, column=0, columnspan=8, sticky="w")
    ttk.Label(
        top,
        text=(
            "Create builds a bent 3/8 in outer stringer with the burn holes. "
            "It is already sheet metal. Click Flatten, then File > Save As > DXF. "
            "The bent plate stays on screen until you click Flatten."
        ),
        justify="left",
        wraplength=640,
    ).grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 8))

    diameter_var = tk.StringVar(value=_fmt_num(spec.shell_od_in * 2.0))
    gap_var = tk.StringVar(value=_fmt_num(spec.gap_in))
    shell_height_var = tk.StringVar(value=_fmt_num(spec.treads * spec.rise_in))
    top_offset_var = tk.StringVar(value="0")
    bottom_offset_var = tk.StringVar(value="0")
    treads_var = tk.StringVar(value=str(spec.treads))
    treads_note = tk.StringVar(value="auto")
    slope_var = tk.StringVar(value=_fmt_num(slope_deg(spec.rise_in, spec.run_in)))
    stair_height_var = tk.StringVar(value="")
    rise_var = tk.StringVar(value="")
    run_var = tk.StringVar(value="")
    hand_var = tk.StringVar(value=CLOCKWISE)
    orient_var = tk.StringVar(value="0")
    orient_end_var = tk.StringVar(value=START)
    plate_var = tk.StringVar(value=_fmt_num(spec.plate_width_in))
    wall_var = tk.StringVar(value="0.5")
    tread_var = tk.StringVar(value=_fmt_num(spec.tread_in))

    _field(top, 2, 0, "Diameter", diameter_var, "in")
    _field(top, 2, 3, "Gap", gap_var, "in")

    def from_tank() -> None:
        radius = _tank_od_radius_in(shared)
        if radius is None:
            messagebox.showinfo("Stringer", "Enter a tank on the Tank Properties tab first.")
            return
        diameter_var.set(_fmt_num(radius * 2.0))
        shell_height_var.set(_fmt_num(shared["spec"].shell_height_in()))

    ttk.Button(top, text="From Tank Properties", command=from_tank).grid(
        row=2, column=6, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0)
    )
    # The diameter and the shell height follow Tank Properties until they are typed over.
    follow_tank(
        parent, shared, [diameter_var, shell_height_var],
        lambda tank: [
            _fmt_num(course_radii_m(tank, tank.active_courses()[0])[0] / 0.0254 * 2.0),
            _fmt_num(tank.shell_height_in()),
        ],
    )
    _field(top, 3, 0, "Shell height", shell_height_var, "in")
    ttk.Label(top, text="Treads").grid(row=3, column=3, sticky="w", pady=(4, 0))
    treads_entry = ttk.Entry(top, textvariable=treads_var, width=10)
    treads_entry.grid(row=3, column=4, sticky="w", pady=(4, 0))
    ttk.Label(top, textvariable=treads_note).grid(row=3, column=5, sticky="w", padx=(2, 10), pady=(4, 0))
    tread_options = ttk.Frame(top)
    tread_options.grid(row=3, column=6, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0))
    ttk.Label(tread_options, text="Tread width").pack(side="left")
    for width in TREAD_WIDTHS_IN:
        ttk.Radiobutton(
            tread_options, text=f"{width:g} in", variable=tread_var, value=_fmt_num(width)
        ).pack(side="left", padx=(6, 0))
    _field(top, 4, 0, "Top offset", top_offset_var, "in, + down")
    _field(top, 4, 3, "Bottom offset", bottom_offset_var, "in, + down")
    _field(top, 5, 0, "Slope", slope_var, "deg")
    hand_options = ttk.Frame(top)
    hand_options.grid(row=5, column=3, columnspan=5, sticky="w", pady=(4, 0))
    ttk.Label(hand_options, text="Climbs, seen from above").pack(side="left")
    for value, text in ((CLOCKWISE, "Clockwise"), (COUNTERCLOCKWISE, "Counterclockwise")):
        ttk.Radiobutton(hand_options, text=text, variable=hand_var, value=value).pack(side="left", padx=(6, 0))
    _field(top, 6, 0, "Orientation", orient_var, "deg")
    end_options = ttk.Frame(top)
    end_options.grid(row=6, column=3, columnspan=5, sticky="w", pady=(4, 0))
    ttk.Label(end_options, text="at the").pack(side="left")
    for value, text in ((START, "Start (foot)"), (END, "End (top)")):
        ttk.Radiobutton(end_options, text=text, variable=orient_end_var, value=value).pack(side="left", padx=(6, 0))
    _shown(top, 7, 0, "Stair height", stair_height_var, "in")
    _shown(top, 7, 3, "Rise", rise_var, "in")
    run_shown = ttk.Frame(top)
    run_shown.grid(row=7, column=6, columnspan=2, sticky="w", padx=(6, 0), pady=(4, 0))
    ttk.Label(run_shown, text="Run").pack(side="left")
    ttk.Entry(run_shown, textvariable=run_var, width=10, state="readonly").pack(side="left", padx=(6, 0))
    ttk.Label(run_shown, text="in").pack(side="left", padx=(2, 0))
    _field(top, 8, 0, "Plate width", plate_var, "in")
    _field(top, 8, 3, "Pan wall", wall_var, "in")

    state = {"busy": False, "stop": False}
    create_btn = ttk.Button(top, text="Create flatten plate in SolidWorks")
    create_btn.grid(row=9, column=0, columnspan=3, sticky="w", pady=(10, 4))
    stair_btn = ttk.Button(top, text="Create stair on tank in SolidWorks")
    stair_btn.grid(row=9, column=3, columnspan=4, sticky="w", pady=(10, 4))

    def request_stop() -> None:
        if state["busy"]:
            state["stop"] = True
            stop_btn.configure(state="disabled")

    stop_btn = ttk.Button(top, text="Stop", state="disabled", command=request_stop)
    stop_btn.grid(row=9, column=7, sticky="w", pady=(10, 4))
    include_shell = tk.BooleanVar(value=True)

    def sync_stair_button() -> None:
        if include_shell.get():
            stair_btn.configure(text="Create stair on tank in SolidWorks")
        else:
            stair_btn.configure(text="Create stair without tank in SolidWorks")

    ttk.Checkbutton(
        top,
        text="Include tank shell",
        variable=include_shell,
        command=sync_stair_button,
    ).grid(row=10, column=0, columnspan=3, sticky="w")
    braces_var = tk.StringVar(value="")
    ttk.Label(top, text="Braces under treads").grid(row=10, column=3, sticky="w", pady=(4, 0))
    ttk.Entry(top, textvariable=braces_var, width=10).grid(row=10, column=4, sticky="w", pady=(4, 0))
    brace_btn = ttk.Button(top, text="Add braces to open stair")
    brace_btn.grid(row=10, column=5, columnspan=3, sticky="w", padx=(6, 0), pady=(4, 0))
    platforms_var = tk.StringVar(value="0")
    top_platform_var = tk.BooleanVar(value=False)
    platform_options = ttk.Frame(top)
    platform_options.grid(row=11, column=0, columnspan=3, sticky="w")
    ttk.Label(platform_options, text="Mid platforms").pack(side="left")
    ttk.Entry(platform_options, textvariable=platforms_var, width=4).pack(side="left", padx=(6, 0))
    ttk.Checkbutton(platform_options, text="Top platform", variable=top_platform_var).pack(side="left", padx=(12, 0))
    posts_var = tk.StringVar(value="")
    post_in_out_var = tk.StringVar(value=_fmt_num(PLATFORM_POST_IN))
    post_in_inner_var = tk.StringVar(value=_fmt_num(PLATFORM_POST_IN))
    post_options = ttk.Frame(top)
    post_options.grid(row=12, column=0, columnspan=8, sticky="w", pady=(4, 0))
    ttk.Label(post_options, text="Posts at flight treads").pack(side="left")
    ttk.Entry(post_options, textvariable=posts_var, width=8).pack(side="left", padx=(6, 0))
    ttk.Label(post_options, text="Platform posts in from the ends: outer").pack(side="left", padx=(12, 0))
    ttk.Entry(post_options, textvariable=post_in_out_var, width=5).pack(side="left", padx=(6, 0))
    ttk.Label(post_options, text="inner").pack(side="left", padx=(8, 0))
    ttk.Entry(post_options, textvariable=post_in_inner_var, width=5).pack(side="left", padx=(6, 0))
    top_rail_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(post_options, text="Top rail", variable=top_rail_var).pack(side="left", padx=(12, 0))
    mid_rail_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(post_options, text="Midrail", variable=mid_rail_var).pack(side="left", padx=(12, 0))
    mid_top_var = tk.StringVar(value=_fmt_num(PLATFORM_MID_TOP_IN))
    ttk.Label(post_options, text="top on platforms").pack(side="left", padx=(6, 0))
    ttk.Entry(post_options, textvariable=mid_top_var, width=5).pack(side="left", padx=(6, 0))
    grab_var = tk.BooleanVar(value=True)
    grab_top_var = tk.StringVar(value=_fmt_num(GRAB_TOP_IN))
    grab_low_var = tk.StringVar(value="0")
    grab_high_var = tk.StringVar(value="0")
    grab_options = ttk.Frame(top)
    grab_options.grid(row=13, column=0, columnspan=8, sticky="w", pady=(4, 0))
    ttk.Checkbutton(grab_options, text="Grab rail", variable=grab_var).pack(side="left")
    ttk.Label(grab_options, text="pipe top").pack(side="left", padx=(6, 0))
    ttk.Entry(grab_options, textvariable=grab_top_var, width=5).pack(side="left", padx=(6, 0))
    ttk.Label(grab_options, text="ends +/-: low").pack(side="left", padx=(12, 0))
    ttk.Entry(grab_options, textvariable=grab_low_var, width=5).pack(side="left", padx=(6, 0))
    ttk.Label(grab_options, text="high").pack(side="left", padx=(8, 0))
    ttk.Entry(grab_options, textvariable=grab_high_var, width=5).pack(side="left", padx=(6, 0))
    split_var = tk.BooleanVar(value=False)
    split_mode_var = tk.StringVar(value=SPLIT_LIMIT)
    split_span_var = tk.StringVar(value=_fmt_num(SPLIT_MAX_SPAN_FT))
    split_count_var = tk.StringVar(value=str(SPLIT_SEGMENTS_DEFAULT))
    split_plate_var = tk.StringVar(value="")
    split_row_var = tk.StringVar(value=_fmt_num(SPLIT_HOLE_ROW_IN))
    split_options = ttk.Frame(top)
    split_options.grid(row=14, column=0, columnspan=8, sticky="w", pady=(4, 0))
    ttk.Checkbutton(split_options, text="Split stringers", variable=split_var).pack(side="left")
    ttk.Radiobutton(split_options, text="Max span", variable=split_mode_var, value=SPLIT_LIMIT).pack(
        side="left", padx=(10, 0)
    )
    ttk.Entry(split_options, textvariable=split_span_var, width=5).pack(side="left", padx=(4, 0))
    ttk.Label(split_options, text="ft").pack(side="left", padx=(2, 0))
    ttk.Radiobutton(split_options, text="Segments", variable=split_mode_var, value=SPLIT_SEGMENTS).pack(
        side="left", padx=(10, 0)
    )
    ttk.Entry(split_options, textvariable=split_count_var, width=4).pack(side="left", padx=(4, 0))
    ttk.Label(split_options, text="plate height").pack(side="left", padx=(12, 0))
    ttk.Entry(split_options, textvariable=split_plate_var, width=6).pack(side="left", padx=(4, 0))
    ttk.Label(split_options, text="in (blank: Auto)  hole rows").pack(side="left", padx=(2, 0))
    ttk.Entry(split_options, textvariable=split_row_var, width=6).pack(side="left", padx=(4, 0))
    ttk.Label(split_options, text="in off the cut").pack(side="left", padx=(2, 0))
    knee_var = tk.BooleanVar(value=True)
    inner_var = tk.BooleanVar(value=True)
    brace_options = ttk.Frame(top)
    brace_options.grid(row=11, column=3, columnspan=5, sticky="w")
    ttk.Checkbutton(brace_options, text="Knee brace to the shell", variable=knee_var).pack(side="left")
    ttk.Checkbutton(brace_options, text="Inner clip to the shell", variable=inner_var).pack(
        side="left", padx=(12, 0)
    )
    ttk.Label(
        top,
        text=(
            "Sizing works like the lisp launcher's Height/Angle. The full height runs from the floor, where "
            "the shell's chime sits, to the top of the shell: Shell height follows Tank Properties until you "
            "type your own. Top offset moves the top tread down from the top of the shell and Bottom offset "
            "moves the ground down from the floor (negative moves either up); Stair height is what is left, "
            "from the ground to the top tread's walking surface. The ground is tread zero, so tread 1 is one "
            "rise up and every rise is the same. Treads is picked from the stair height, the fewest that keep "
            f"every rise at {AUTO_RISE_IN:g} in or under and split into equal flights around the mid platforms, "
            "until you type your own (clear it and click away to pick again). Rise is the stair height over "
            "the treads and Run the rise over tan(slope), both at the walk centerline.\n"
            "Orientation puts the start (the foot of the first flight's stringers) or the end (the top of the "
            "last flight's) on that line, in degrees like the nozzles: 0 toward +Z, clockwise seen from above. "
            "The stair is built at its own angle, then turned there in one move. Counterclockwise builds it "
            "clockwise, braces and all, and mirrors it through the Right plane first, as the lisp does; the "
            "stringers still flatten. Add braces to open stair works on a clockwise stair only.\n"
            "Stair: both climbing stringers, every tread as a pan (top and four walls, no bottom), "
            "and the two bolts per side located from each tread's front face, cut through the inner "
            "and the outer stringer into that tread end wall. Include tank shell adds the shell at "
            "the diameter above. Uncheck it to build the same stair with no shell. Stop ends the "
            "build after the step it is on and leaves the part as far as it got.\n"
            "Cross braces: type the tread numbers, like 2 or 2, 5 (tread 1 is the lowest). Each is "
            "an L3x3x3/8 from the weldment library under that tread with nested end caps and 13/16 "
            "holes through the stringers. The stair button adds them at the end of a new stair. "
            "Add braces to open stair puts them on the stair part open in SolidWorks and replaces "
            "any brace already under those treads. Knee brace to the shell adds, with each cross "
            "brace, an L3x3x3/8 at 45 deg from its leg hole down to a 1/4 clip and pad on the shell. "
            "Inner clip to the shell adds, at each braced tread but the top of a flight, an L4x3x3/8 on "
            "the tank side of the inner stringer just above the tread, bolted to a 3/8 landing clip and "
            "pad on the shell.\n"
            "Tread width 30 in narrows the stair: the outer stringer comes 6 in in and everything on the flights "
            "follows it, but platforms stay 36 in, lined up on the inner stringer, so their outer edge stands "
            "out past the flights.\n"
            "Mid platforms (0 to 3) split the treads into equal flights, as the lisp does: the tread "
            "level with each platform belongs to both flights, so 7 treads with 1 platform are two "
            "flights of 4. Each platform is a C4x5.4 frame mitered at the corners, 36 in along the walk "
            "centerline, with L6x6x3/8 clips at every stringer end, a 3/8 tab, shell clip and pad "
            "tying each end of its inner channel to the shell, and an L3x3x3/8 knee brace from a hanger "
            "plate under each end of its outer channel down to a clip and pad on the shell. Top platform puts the same frame past "
            "the top tread. Brace tread numbers count every pan, the extra one at each platform too.\n"
            "Posts at flight treads: tread numbers in one flight, like 2, 4, repeated in every flight. Each "
            "gets an L2x2x1/4 handrail post on the outside of the outer stringer just in front of it, "
            "standing on the tread below (so not tread 1), its top cut along the rail 3/4 in under the "
            "42 in top rail and its outstanding leg cut back 45 degrees so fingers sliding along the rail "
            "clear it, bolted through the stringer with two 13/16 holes. With posts, each platform "
            "also gets one near each end of its outer channel, bolted through the web, its heel the "
            "outer distance in from the platform end, cut back the same way and stopping the same 3/4 in "
            "under the rail for the weld. The inner distance is for "
            "the inner rail, which is not built yet. Top rail runs an L2x2x1/4 42 in up over the outer "
            "posts, rolled to a helix on each flight with the library angle's 3/16 root fillet and toe "
            "rounds, mitered to a level piece where it reaches a platform, and bolted to the platform "
            "post through a short vertical end piece, cut back with the post; each platform has its own "
            "rail between its posts. On 30 in treads the flight's top rail runs on square to the platform's "
            "side over an end angle welded under its end; that stands back to back with a post on the side "
            "channel just outside the rail and bolts to it, so nothing is welded in the field. Both come up "
            "to the underside of their rail's top leg. The platform's rails run round its outer edge, mitered at the "
            "corners and back along each side to the post. Each platform gets a 1/4 x 6 toe plate on its "
            "outer channel, wrapped the same way on 30 in and on past the post to the stringer. "
            "Midrail runs a 2 x 1/4 flat bar on the walk side of the posts, 21 in up on the flights and "
            "its top on platforms (24 in by default) across them, level to 1/4 in short of the same end "
            "pieces, which come down to its bottom; on 30 in it runs on to the platform's side, the end "
            "angle welded on it. With both rails, an L2x2x1/4 drops from the top rail's "
            "foot, mitered to it, to the midrail's bottom, and the midrail butts against it.\n"
            "Grab rail runs a 1-1/2 in Sch 40 pipe, its top at the pipe top over the stringer's top edge "
            "(34 in by default), rolled to a helix on the walk side of the outer posts. It starts over "
            "tread 1's front edge and stops at each platform where the midrail meets the platform's, cut "
            "square with a 1-5/8 in round cap welded on each end; ends +/- lengthens or shortens every "
            "flight's pipe at its low and high end. Each flight post holds it on a PC #34, a 3/4 x 3/4 "
            "quarter turn cut from 3/4 plate hanging under it: the foot's end welded to the post, the "
            "upright under the pipe and cut to its slope."
        ),
        justify="left",
        wraplength=640,
    ).grid(row=15, column=0, columnspan=8, sticky="w", pady=(0, 4))

    summary_var = tk.StringVar(value="")
    ttk.Label(top, textvariable=summary_var, justify="left", wraplength=640).grid(
        row=16, column=0, columnspan=8, sticky="w", pady=(4, 4)
    )

    ttk.Label(
        top, text="Plan from above, 0° at 12 o'clock and clockwise: red ends, the dashed arrow climbs"
    ).grid(row=17, column=0, columnspan=8, sticky="w")
    plan = tk.Canvas(top, width=_PLAN, height=_PLAN, background="#f4f1ea", highlightthickness=1)
    plan.grid(row=18, column=0, columnspan=8, sticky="w")

    def tab_inputs() -> dict[str, object]:
        """Everything on the tab, for the run log."""
        return {
            "diameter": diameter_var.get(), "gap": gap_var.get(), "shell_height": shell_height_var.get(),
            "top_offset": top_offset_var.get(), "bottom_offset": bottom_offset_var.get(),
            "treads": treads_var.get(), "slope": slope_var.get(), "tread_width": tread_var.get(),
            "climbs": hand_var.get(), "orientation": orient_var.get(), "orientation_at": orient_end_var.get(),
            "plate_width": plate_var.get(), "pan_wall": wall_var.get(), "include_shell": include_shell.get(),
            "braces": braces_var.get(), "knee_braces": knee_var.get(), "inner_clips": inner_var.get(),
            "mid_platforms": platforms_var.get(), "top_platform": top_platform_var.get(), "posts": posts_var.get(),
            "post_in_outer": post_in_out_var.get(), "post_in_inner": post_in_inner_var.get(),
            "top_rail": top_rail_var.get(), "mid_rail": mid_rail_var.get(), "mid_top": mid_top_var.get(),
            "grab_rail": grab_var.get(), "grab_top": grab_top_var.get(), "grab_low": grab_low_var.get(),
            "grab_high": grab_high_var.get(),
            "split": split_var.get(), "split_mode": split_mode_var.get(), "split_span_ft": split_span_var.get(),
            "split_segments": split_count_var.get(), "split_plate": split_plate_var.get(),
            "split_hole_row": split_row_var.get(),
        }

    def read_wall() -> float:
        try:
            wall = float(wall_var.get().strip())
        except ValueError as exc:
            raise ValueError("Pan wall must be numeric.") from exc
        if wall <= 0 or wall >= TREAD_MARK_IN or wall * 2 >= TREAD_DEPTH_IN:
            raise ValueError("Pan wall must be greater than zero and thinner than the tread.")
        return wall

    def read_offsets() -> tuple[float, float]:
        """Top and bottom offsets, inches, + down. Blank is 0."""
        try:
            return float(top_offset_var.get().strip() or "0"), float(bottom_offset_var.get().strip() or "0")
        except ValueError as exc:
            raise ValueError("The top and bottom offsets must be numbers of inches.") from exc

    def read_height() -> float:
        """Ground to the top tread's surface: the shell height less the top offset, plus the bottom one."""
        try:
            shell_height = float(shell_height_var.get().strip())
        except ValueError as exc:
            raise ValueError("Shell height must be numeric.") from exc
        if shell_height <= 0:
            raise ValueError("Shell height must be greater than zero.")
        return stair_height_in(shell_height, *read_offsets())

    def read_rise_run() -> tuple[int, float, float]:
        """Treads, rise and run from the stair height, the treads and the slope."""
        height = read_height()
        try:
            treads_num = float(treads_var.get().strip())
            slope = float(slope_var.get().strip())
        except ValueError as exc:
            raise ValueError("Treads and slope must be numeric.") from exc
        if abs(treads_num - round(treads_num)) > 1e-6:
            raise ValueError("Treads must be a whole number.")
        treads = int(round(treads_num))
        rise, run = rise_run(height, treads, slope)
        return treads, rise, run

    def read_turn(current: StringerMock, platforms: int) -> tuple[float, tuple[float, float]]:
        """The turn that puts the chosen end at the orientation, and the two ends' angles before it."""
        try:
            orientation = float(orient_var.get().strip() or "0")
        except ValueError as exc:
            raise ValueError("Orientation must be a number of degrees.") from exc
        ends = end_angles(current, platforms)
        turn = placement_turn(
            orientation, *ends, at_top=orient_end_var.get() == END, ccw=hand_var.get() == COUNTERCLOCKWISE
        )
        return turn, ends

    def read_spec() -> StringerMock:
        try:
            diameter = float(diameter_var.get().strip())
            gap = float(gap_var.get().strip())
            plate = float(plate_var.get().strip())
        except ValueError as exc:
            raise ValueError("Stair values must be numeric.") from exc
        if diameter <= 0:
            raise ValueError("Diameter must be greater than zero.")
        treads, rise, run = read_rise_run()
        if gap < 0:
            raise ValueError("Gap cannot be negative.")
        if plate <= 0:
            raise ValueError("Plate width must be greater than zero.")
        return StringerMock(
            shell_od_in=diameter / 2.0,
            gap_in=gap,
            treads=treads,
            rise_in=rise,
            run_in=run,
            plate_width_in=plate,
            outside_face=True,
            tread_in=float(tread_var.get()),
        )

    def read_platforms(treads: int) -> int:
        text = platforms_var.get().strip() or "0"
        try:
            count = float(text)
        except ValueError as exc:
            raise ValueError("Mid platforms must be a whole number, 0 to 3.") from exc
        if count != int(count) or not 0 <= count <= MAX_PLATFORMS:
            raise ValueError(f"Mid platforms must be a whole number, 0 to {MAX_PLATFORMS}.")
        flight_treads(treads, int(count))
        return int(count)

    auto = {"treads": treads_var.get()}  # the count last picked from the height

    def pick_treads(*_args) -> None:
        """Pick the treads from the height and the mid platforms, unless someone typed their own."""
        if treads_var.get().strip() not in (auto["treads"], ""):
            return
        try:
            platforms = float(platforms_var.get().strip() or "0")
            count = str(auto_treads(read_height(), int(platforms)))
        except ValueError:
            return
        auto["treads"] = count
        if treads_var.get() != count:
            treads_var.set(count)

    def note_treads(*_args) -> None:
        treads_note.set("auto" if treads_var.get().strip() == auto["treads"] else "typed")

    def refresh(*_args) -> None:
        for var in (stair_height_var, rise_var, run_var):
            var.set("")
        with contextlib.suppress(ValueError):
            stair_height_var.set(_fmt_num(read_height()))
            _treads, rise, run = read_rise_run()
            rise_var.set(_fmt_num(rise))
            run_var.set(_fmt_num(run))
        try:
            current = read_spec()
            read_wall()
            current.validate()
            platforms = read_platforms(current.treads)
            drawn = layout_stringer(current)
            treads_at, spans = stair_plan(current, platforms, bool(top_platform_var.get()))
            turn, ends = read_turn(current, platforms)
            top_offset, bottom_offset = read_offsets()
        except ValueError as exc:
            summary_var.set(str(exc))
            plan.delete("all")
            if not state["busy"]:
                status_var.set("Stringer needs a correction.")
            return
        ccw = hand_var.get() == COUNTERCLOCKWISE
        flights = (
            f" in {platforms + 1} flights of {flight_treads(current.treads, platforms)} ({len(treads_at)} pans)"
            if platforms else ""
        )
        slopes = slopes_deg(current)
        lap = tread_lap_in(current.run_in)
        if lap > 1e-6:
            lap_text = f"each tread laps the next by {lap:.3f} in"
        elif lap < -1e-6:
            lap_text = f"{-lap:.3f} in gap between treads"
        else:
            lap_text = "treads meet flush"
        foot, top_end = (orientation_deg(world_angle(end, turn, ccw)) for end in ends)
        summary_var.set(
            f"Climbs {'counterclockwise' if ccw else 'clockwise'} seen from above, {current.treads} treads{flights}: "
            f"the ground {_offset_text(bottom_offset, 'the floor')}, tread 1 one rise of {current.rise_in:.3f} in up, "
            f"the top tread {current.treads * current.rise_in:.3f} in above the ground and "
            f"{_offset_text(top_offset, 'the top of the shell')}. The foot is at {foot:.2f}° and the top end at "
            f"{top_end:.2f}° (0° toward +Z, clockwise seen from above, like the nozzles).\n"
            f"Slope {slopes['centerline']:.2f}° at the walk centerline, {slopes['inner']:.2f}° inner stringer, "
            f"{slopes['outer']:.2f}° outer stringer, {slopes['shell']:.2f}° at the shell OD (mid-walls, as the "
            f"lisp's Audit) · {lap_text} at the centerline (depth {TREAD_DEPTH_IN:g} in) · sweep "
            f"{math.degrees(max([treads_at[-1]] + [b for _a, b in spans])):.2f}° · outside face radius "
            f"{drawn.outside_radius_in:.2f} in"
        )
        _draw_plan(plan, drawn, treads_at, spans, ends=ends, turn=turn, ccw=ccw)
        if not state["busy"]:
            status_var.set("Stringer ready.")

    def create() -> None:
        if state["busy"]:
            return
        runlog.inputs("Create flatten plate", tab_inputs())
        try:
            current = read_spec()
            current.validate()
        except ValueError as exc:
            messagebox.showerror("Stringer", str(exc))
            return
        state["busy"] = True
        create_btn.configure(state="disabled")
        status_var.set("Building the formed stringer…")
        parent.update_idletasks()
        try:
            session = connect()
            result = create_stringer_try(session.app, current)
            if hand_var.get() == COUNTERCLOCKWISE:
                result.note = f"{result.note}\n\n{mirror_stair(result.model)}"
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            state["busy"] = False
            create_btn.configure(state="normal")
            status_var.set("Stringer build failed.")
            messagebox.showerror("Stringer", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            state["busy"] = False
            create_btn.configure(state="normal")
            status_var.set("Stringer build failed.")
            messagebox.showerror("Stringer", format_com_error(exc))
            return
        state["busy"] = False
        create_btn.configure(state="normal")
        status_var.set(f"Stringer → {result.title}")
        messagebox.showinfo("Stringer", f"{result.title}\n\n{result.note}")

    def read_post_in(var: tk.StringVar, side: str) -> float:
        try:
            value = float(var.get().strip())
        except ValueError as exc:
            raise ValueError(f"The {side} platform post distance must be a number of inches.") from exc
        if value < 0:
            raise ValueError(f"The {side} platform post distance cannot be negative.")
        return value

    def read_braces(count: int) -> tuple[int, ...]:
        braces = parse_brace_treads(braces_var.get())
        over = [index for index in braces if index > count]
        if over:
            raise ValueError(f"The stair has {count} treads; there is no tread {over[0]} for a brace.")
        return braces

    def create_stair() -> None:
        if state["busy"]:
            return
        runlog.inputs("Create stair", tab_inputs())
        try:
            current = read_spec()
            current.validate()
            wall = read_wall()
            platforms = read_platforms(current.treads)
            per_flight = flight_treads(current.treads, platforms)
            braces = read_braces(per_flight * (platforms + 1))
            posts = read_post_treads(posts_var.get(), per_flight)
            post_in = read_post_in(post_in_out_var, "outer")
            read_post_in(post_in_inner_var, "inner")
            top_rail = bool(top_rail_var.get()) and bool(posts)
            mid_rail = bool(mid_rail_var.get()) and bool(posts)
            try:
                mid_top = float(mid_top_var.get().strip())
            except ValueError as exc:
                raise ValueError("The platform midrail top must be a number of inches.") from exc
            check_platform_mid_top(mid_top)
            grab = None
            if bool(grab_var.get()) and posts:
                try:
                    grab = GrabRail(
                        top=float(grab_top_var.get().strip()),
                        low=float(grab_low_var.get().strip() or "0"),
                        high=float(grab_high_var.get().strip() or "0"),
                    )
                except ValueError as exc:
                    raise ValueError("The grab rail's pipe top and end adjustments must be numbers of inches.") from exc
                if not 0.0 < grab.top < RAIL_TOP_IN:
                    raise ValueError(f"The grab rail's pipe top must be above 0 and under the {RAIL_TOP_IN:g} in top rail.")
            shell_height = float(shell_height_var.get().strip())
            splits = read_splits()
            _top_offset, bottom_offset = read_offsets()
            turn, ends = read_turn(current, platforms)
        except ValueError as exc:
            messagebox.showerror("Stair", str(exc) if str(exc) else "Pan wall must be numeric.")
            return
        with_shell = bool(include_shell.get())
        knees = bool(knee_var.get())
        inner = bool(inner_var.get())
        top_platform = bool(top_platform_var.get())
        tops = _flight_tops(current.treads, platforms)
        ccw = hand_var.get() == COUNTERCLOCKWISE
        turned = abs(turn) > 1e-9
        foot, top_end = (orientation_deg(world_angle(end, turn, ccw)) for end in ends)

        def work(progress):
            session = connect()
            result = build_stair(
                session.app, current, wall, progress=progress, shell=with_shell, platforms=platforms,
                top_platform=top_platform, posts=posts, platform_post_in=post_in, top_rail=top_rail,
                mid_rail=mid_rail, platform_mid_top=mid_top, grab=grab, ground_in=-bottom_offset,
                shell_height_in=shell_height, splits=splits,
            )
            notes = [result.note]
            if braces:
                profile = angle_profile(session.app)
                clip_profile = clip_angle_profile(session.app) if inner else ""
                for index in braces:
                    notes.append(add_cross_brace(result.model, index, profile, progress=progress).note)
                    if knees:
                        knee = add_knee_brace(
                            result.model, index, profile, shell_radius_in=current.shell_od_in, progress=progress
                        )
                        notes.append(knee.note)
                    if inner:
                        notes.append(
                            _inner_clip(result.model, index, tops, clip_profile, current.shell_od_in, progress)
                        )
            # Last: the braces and clips find the treads by their clockwise angles where they were built.
            if ccw:
                notes.append(mirror_stair(result.model, result.shell_bodies, progress=progress))
            if turned:
                notes.append(turn_stair(result.model, turn, result.shell_bodies, progress=progress))
            notes.append(
                f"The foot is at {foot:.2f}° and the top end at {top_end:.2f}° "
                "(0° toward +Z, clockwise seen from above, like the nozzles)."
            )
            return result.title, "\n\n".join(notes)

        stages = _stair_stage_plan(
            current.treads, shell=with_shell, braces=braces, knees=knees, inner=inner, platforms=platforms,
            top_platform=top_platform, posts=posts, top_rail=top_rail, mid_rail=mid_rail, grab=grab is not None,
            ccw=ccw, turned=turned, split_treads=tuple(
                joint.tread for joint in (split_joints(replace(current, treads=per_flight), splits)["In"]
                                          if splits else ())
            ),
        )
        run_job("Stair", stages, work)

    def add_braces() -> None:
        if state["busy"]:
            return
        runlog.inputs("Add braces to open stair", tab_inputs())
        try:
            braces = parse_brace_treads(braces_var.get())
        except ValueError as exc:
            messagebox.showerror("Braces", str(exc))
            return
        if not braces:
            messagebox.showinfo("Braces", "Type the tread numbers first, like 2 or 2, 5. Tread 1 is the lowest.")
            return
        knees = bool(knee_var.get())
        inner = bool(inner_var.get())
        try:
            shell_radius = float(diameter_var.get().strip()) / 2.0
        except ValueError:
            shell_radius = None

        def work(progress):
            session = connect()
            model = com_value(session.app.ActiveDoc)
            if model is None:
                raise ValueError("Open the stair part in SolidWorks first.")
            if is_counterclockwise(model):
                raise ValueError(
                    "This stair climbs counterclockwise: it was mirrored once it was built, and braces find "
                    "the treads by their clockwise angles. Type the brace treads and create the stair again."
                )
            count, tops = stair_flight_tops(model)
            over = [index for index in braces if index > count]
            if over:
                raise ValueError(f"The open stair has {count} treads; there is no tread {over[0]}.")
            profile = angle_profile(session.app)
            clip_profile = clip_angle_profile(session.app) if inner else ""
            notes = []
            for index in braces:
                remove_cross_brace(model, index)
                notes.append(add_cross_brace(model, index, profile, progress=progress).note)
                if knees:
                    knee = add_knee_brace(model, index, profile, shell_radius_in=shell_radius, progress=progress)
                    notes.append(knee.note)
                if inner:
                    notes.append(_inner_clip(model, index, tops, clip_profile, shell_radius, progress))
            return str(com_value(model.GetTitle) or "Part"), "\n\n".join(notes)

        run_job("Braces", _brace_stage_plan(braces, knees=knees, inner=inner), work)

    def run_job(title: str, stages, work) -> None:
        """Run a SolidWorks job with the percent on the status line and Stop live."""
        start = f"0% — starting the {title.lower()}"
        state["busy"] = True
        state["stop"] = False
        for button in (create_btn, stair_btn, brace_btn):
            button.configure(state="disabled")
        stop_btn.configure(state="normal")
        status_var.set(start)
        # While SolidWorks works, only Stop takes clicks, so no second build can start.
        stop_btn.grab_set()
        parent.update_idletasks()
        done = {"count": 0}
        last = {"status": start}

        def progress(text: str) -> None:
            label = text
            for index in range(done["count"], len(stages)):
                keys, stage_label = stages[index]
                if text in keys:
                    done["count"] = index + 1
                    label = stage_label
                    break
            percent = _progress_percent(done["count"], len(stages))
            last["status"] = f"{percent}% — {label}"
            status_var.set(last["status"])
            # A Stop click waits here until the step SolidWorks is on finishes.
            parent.update()
            if state["stop"]:
                raise BuildStopped(last["status"])

        def finish(status: str) -> None:
            with contextlib.suppress(tk.TclError):
                stop_btn.grab_release()
            state["busy"] = False
            stop_btn.configure(state="disabled")
            for button in (create_btn, stair_btn, brace_btn):
                button.configure(state="normal")
            status_var.set(status)

        try:
            heading, note = work(progress)
        except BuildStopped:
            finish(f"Stopped at {last['status']}")
            messagebox.showinfo(
                title,
                "Stopped. The part stays in SolidWorks as far as it got. Close it without saving.",
            )
            return
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            finish(f"100% — {title.lower()} failed")
            messagebox.showerror(title, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            finish(f"100% — {title.lower()} failed")
            messagebox.showerror(title, format_com_error(exc))
            return
        finish(f"100% — {title} → {heading}")
        messagebox.showinfo(title, f"{heading}\n\n{note}")

    create_btn.configure(command=create)
    stair_btn.configure(command=create_stair)
    brace_btn.configure(command=add_braces)
    def on_height(*_args) -> None:
        # Pick the treads before refreshing, so the summary sees the new count.
        pick_treads()
        refresh()

    def on_treads(*_args) -> None:
        note_treads()
        refresh()

    def on_treads_left(_event=None) -> None:
        # Cleared and left: pick from the height again. Not while typing: typing over the count empties it first.
        if not treads_var.get().strip():
            pick_treads()

    treads_entry.bind("<FocusOut>", on_treads_left)

    for var in (shell_height_var, top_offset_var, bottom_offset_var, platforms_var):
        var.trace_add("write", on_height)
    treads_var.trace_add("write", on_treads)
    for var in (
        diameter_var, gap_var, slope_var, plate_var, wall_var, top_platform_var, tread_var, hand_var, orient_var,
        orient_end_var,
    ):
        var.trace_add("write", refresh)

    def read_splits() -> SplitSettings | None:
        """The splitter settings, or None when the stringers are not split."""
        if not split_var.get():
            return None
        try:
            plate = split_plate_var.get().strip()
            return SplitSettings(
                mode=split_mode_var.get(),
                segments=int(float(split_count_var.get().strip() or "0")),
                max_span_ft=float(split_span_var.get().strip() or "0"),
                plate_height_in=float(plate) if plate else None,
                hole_row_in=float(split_row_var.get().strip() or "0"),
            )
        except ValueError as exc:
            raise ValueError(f"Stringer splitters: {exc}") from exc

    def arrangement() -> StairArrangement:
        """The stair as the tab stands, for the Stretchout tab. Raises ValueError with what is wrong."""
        current = read_spec()
        current.validate()
        platforms = read_platforms(current.treads)
        braces = read_braces(flight_treads(current.treads, platforms) * (platforms + 1))
        turn, _ends = read_turn(current, platforms)
        _top_offset, bottom_offset = read_offsets()
        return StairArrangement(
            current, platforms=platforms, top_platform=bool(top_platform_var.get()), ground_in=-bottom_offset,
            turn=turn, ccw=hand_var.get() == COUNTERCLOCKWISE, braces=braces, knees=bool(knee_var.get()),
            inner_clips=bool(inner_var.get()), splits=read_splits(),
        )

    if shared is not None:
        shared["stairway"] = arrangement

    def on_wheel(event) -> None:
        scroller.yview_scroll(int(-event.delta / 120), "units")

    _bind_wheel(top, on_wheel)
    scroller.bind("<MouseWheel>", on_wheel)
    refresh()


def build_tread_joint_tab(parent: ttk.Frame, status_var: tk.StringVar) -> None:
    """Tread Joint tab: pan tread between two straight stringer pieces, with the four bolts."""
    top = ttk.Frame(parent, padding=12)
    top.pack(fill="both", expand=True)
    _build_joint_section(top, parent, status_var, {"busy": False}, start_row=0)


def _build_joint_section(top: ttk.Frame, parent: ttk.Frame, status_var: tk.StringVar, state: dict, *, start_row: int) -> None:
    joint = TreadJointSpec()
    ttk.Label(top, text="Tread joint", font=("", 11, "bold")).grid(
        row=start_row + 1, column=0, columnspan=8, sticky="w"
    )
    ttk.Label(
        top,
        text=(
            "Create builds one pan tread (top and four walls, no bottom) between two straight "
            "stringer pieces. The two 7/16 in bolts per side are located from the tread front face "
            "(2-13/16 in back, 7 in apart, 3/4 in above the open bottom) and cut through each "
            "stringer into that tread end wall."
        ),
        justify="left",
        wraplength=640,
    ).grid(row=start_row + 2, column=0, columnspan=8, sticky="w", pady=(0, 8))

    wall_var = tk.StringVar(value=f"{joint.wall_in:g}")
    length_var = tk.StringVar(value=f"{joint.stringer_length_in:g}")
    width_var = tk.StringVar(value=f"{joint.plate_width_in:g}")
    _field(top, start_row + 3, 0, "Pan wall", wall_var, "in")
    _field(top, start_row + 3, 3, "Stringer piece", length_var, "in")
    _field(top, start_row + 4, 0, "Plate width", width_var, "in")

    joint_btn = ttk.Button(top, text="Create tread joint in SolidWorks")
    joint_btn.grid(row=start_row + 5, column=0, columnspan=3, sticky="w", pady=(10, 4))
    joint_summary = tk.StringVar(value="")
    ttk.Label(top, textvariable=joint_summary, justify="left", wraplength=640).grid(
        row=start_row + 6, column=0, columnspan=8, sticky="w", pady=(4, 4)
    )

    def read_joint() -> TreadJointSpec:
        try:
            return TreadJointSpec(
                wall_in=float(wall_var.get().strip()),
                stringer_length_in=float(length_var.get().strip()),
                plate_width_in=float(width_var.get().strip()),
            )
        except ValueError as exc:
            raise ValueError("Tread joint values must be numeric.") from exc

    def refresh_joint(*_args) -> None:
        try:
            drawn = layout_tread_joint(read_joint())
        except ValueError as exc:
            joint_summary.set(str(exc))
            return
        joint_summary.set(
            f"Tread {drawn.tread_x1 - drawn.tread_x0:g} in deep × {drawn.tread_y1 - drawn.tread_y0:g} in high, "
            f"end walls {drawn.tread_z0:g} in off each stringer · bolts at {drawn.bolt_xs[0]:.4g} and "
            f"{drawn.bolt_xs[1]:.4g} in from tread center, {drawn.bolt_y - drawn.tread_y0:g} in above the open bottom"
        )

    def create_joint() -> None:
        if state["busy"]:
            return
        try:
            current = read_joint()
            current.validate()
        except ValueError as exc:
            messagebox.showerror("Tread joint", str(exc))
            return
        state["busy"] = True
        joint_btn.configure(state="disabled")
        status_var.set("Building the tread joint…")
        parent.update_idletasks()
        try:
            session = connect()
            result = create_tread_joint(session.app, current)
        except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
            state["busy"] = False
            joint_btn.configure(state="normal")
            status_var.set("Tread joint build failed.")
            messagebox.showerror("Tread joint", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            state["busy"] = False
            joint_btn.configure(state="normal")
            status_var.set("Tread joint build failed.")
            messagebox.showerror("Tread joint", format_com_error(exc))
            return
        state["busy"] = False
        joint_btn.configure(state="normal")
        status_var.set(f"Tread joint → {result.title}")
        messagebox.showinfo("Tread joint", f"{result.title}\n\n{result.note}")

    joint_btn.configure(command=create_joint)
    for var in (wall_var, length_var, width_var):
        var.trace_add("write", refresh_joint)
    refresh_joint()


def _field(parent, row: int, column: int, label: str, variable: tk.StringVar, unit: str) -> None:
    ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=(4, 0))
    ttk.Entry(parent, textvariable=variable, width=10).grid(row=row, column=column + 1, sticky="w", pady=(4, 0))
    ttk.Label(parent, text=unit).grid(row=row, column=column + 2, sticky="w", padx=(2, 10), pady=(4, 0))


def _shown(parent, row: int, column: int, label: str, variable: tk.StringVar, unit: str) -> None:
    """A worked-out value: shown like a field, but read-only."""
    ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", pady=(4, 0))
    ttk.Entry(parent, textvariable=variable, width=10, state="readonly").grid(
        row=row, column=column + 1, sticky="w", pady=(4, 0)
    )
    ttk.Label(parent, text=unit).grid(row=row, column=column + 2, sticky="w", padx=(2, 10), pady=(4, 0))


def _bind_wheel(widget, handler) -> None:
    widget.bind("<MouseWheel>", handler)
    for child in widget.winfo_children():
        _bind_wheel(child, handler)


def plan_xy(radius: float, angle: float) -> tuple[float, float]:
    """Plan point seen from above the way Elite draws a plan: 0 at 12 o'clock, clockwise (+X to the left, +Z up).
    ``angle`` is the nozzles' way: 0 toward +Z, clockwise seen from above."""
    return (radius * math.sin(angle), radius * math.cos(angle))


def _draw_plan(
    canvas: tk.Canvas, layout: StringerLayout, treads_at: list[float], spans: list[tuple[float, float]],
    *, ends: tuple[float, float] = (0.0, 0.0), turn: float = 0.0, ccw: bool = False,
) -> None:
    """Shell, stringer faces, a line per tread, each platform's outline, the climb and both ends, over the whole
    stair, where it lands on the tank: the clockwise build's angles mirrored for ``ccw``, then turned."""
    canvas.delete("all")
    sweep = max([treads_at[-1]] + [b for _a, b in spans]) if treads_at else layout.sweep_rad
    label_r = _platform_out(layout) + 8.0
    radii = (layout.shell_od_in, layout.inner_face_in, layout.outside_radius_in, _platform_out(layout), label_r)

    def world(angle: float) -> float:
        return world_angle(angle, turn, ccw)

    points = [
        plan_xy(radius, world(-0.12 + (sweep + 0.24) * step / 16))
        for radius in radii
        for step in range(17)
    ]
    _paint(
        canvas, _PLAN, _PLAN, points,
        lambda locate: _plan_marks(canvas, layout, sweep, treads_at, spans, locate, world, ends, label_r),
    )


def _plan_marks(
    canvas: tk.Canvas, layout: StringerLayout, sweep: float, treads_at, spans, locate, world, ends, label_r: float
) -> None:
    def at(radius: float, angle: float) -> tuple[float, float]:
        return locate(*plan_xy(radius, world(angle)))

    for label, angle in zip(("foot", "top"), ends, strict=True):
        canvas.create_line(*at(layout.shell_od_in, angle), *at(_platform_out(layout), angle), fill="#b3261e", width=2)
        canvas.create_text(*at(label_r, angle), text=label, fill="#b3261e")
    canvas.create_line(*_arc(layout.shell_od_in, sweep, at), fill="#8d96a0", width=2, smooth=True)
    canvas.create_line(*_arc(layout.inner_face_in, sweep, at), fill="#5c6770", width=1, smooth=True)
    canvas.create_line(*_arc(layout.outside_radius_in, sweep, at), fill="#2f6f86", width=4, smooth=True)
    walk = layout.inner_face_in + layout.clear_in / 2.0
    canvas.create_line(*_arc(walk, sweep, at), fill="#9a6b2f", dash=(4, 3), arrow="last", smooth=True)

    for angle in treads_at:
        canvas.create_line(*at(layout.inner_face_in, angle), *at(layout.outside_radius_in, angle), fill="#243038")
    for side_a, side_b in spans:
        corners = (
            at(layout.inner_face_in, side_a), at(_platform_out(layout), side_a),
            at(_platform_out(layout), side_b), at(layout.inner_face_in, side_b),
        )
        canvas.create_polygon(*[v for corner in corners for v in corner], outline="#b5651d", fill="", width=2)


def _platform_out(layout: StringerLayout) -> float:
    """A platform's outer edge: always full width from the inner stringer, past narrower treads."""
    return layout.inner_face_in + CLEAR_IN + THICKNESS_IN


def _paint(canvas: tk.Canvas, width: int, height: int, points: list[tuple[float, float]], draw) -> None:
    margin = 16
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
    origin_x = margin - min_x * scale
    origin_y = height - margin + min_y * scale

    def locate(x_in: float, y_in: float) -> tuple[float, float]:
        return origin_x + x_in * scale, origin_y - y_in * scale

    draw(locate)


def _arc(radius: float, sweep: float, at) -> list[float]:
    coords: list[float] = []
    for step in range(41):
        coords.extend(at(radius, sweep * step / 40))
    return coords
