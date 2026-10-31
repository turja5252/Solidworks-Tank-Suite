"""The stair game on the Stretchout tab: pick a piece from the tray, drop it on a stringer, see green or red.

One canvas: the tray of pieces and the bin down the left, then two views of the whole stair, ground to top with
its platforms, on the shell's stretchout seen from outside as the Shell view draws it: the outside stringer over,
the inside stringer under. Behind each are the shell's plates with their weld seams in red dashes, and the
nozzles, FTCOs and anchor chairs. Outside are the posts, the top rail, the midrail and the grab rail; inside, the
inside posts and pipe, the inner clips and knee braces with their pads where they land on the shell, and the
platforms' shell pads. A piece snaps to the tread it would go at as it is dragged, green where the rules let it
go and red with the reason where they don't; let go on green and it is placed and pinned, and everything the
rules placed re-flows round it. Drag a placed piece to move it, or into the bin to throw it away. Undo, Auto
place and Start over are over the views. The left button plays; the wheel zooms and the right button pans.
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import replace
from tkinter import ttk

from swauto.errors import SolidWorksError
from swauto.stair.attachments import (
    CLIP,
    INNER,
    KNEE,
    ON_PLATFORMS,
    OUTER,
    PLATFORM_POST,
    POST,
    RADIAL,
    RAIL_SPLIT,
    SPLICE,
    Rules,
    Shell,
    Spot,
    applied,
)
from swauto.stair.development import develop_both, tread_rect
from swauto.stair.game import (
    TRAY,
    Game,
    Piece,
    edge_y,
    lane_rails,
    pad_box,
    post_top,
    slot,
    span_at,
    spot_xy,
    view_angle,
    view_x,
)
from swauto.stair.heights import RailHeights, snap
from swauto.stair.landings import PLATFORM, PLATFORM_KNEE_PAD, PLATFORM_PAD, platform_frame, shell_marks
from swauto.stair.platform_sw import GRATING_IN, platform_knees
from swauto.stair.post_sw import TOP_GAP_IN
from swauto.stair.stair_sw import stair_places
from swauto.stretchout.model import (
    ANCHORS,
    FTCOS,
    NOZZLES,
    PLATES,
    PLATFORM_PADS,
    PLATFORMS,
    TREADS,
    Stretchout,
    build_stretchout,
)
from swauto.stretchout.svg import COURSE_FILLS, STYLE
from swauto.tank.spec import TankSpec

TRAY_W = 200
TILE_H = 54
_ROOM_TOP_IN = 48.0  # room over a stringer's top edge a piece is still dropped on it: the posts and the rails
_ROOM_LOW_IN = 6.0  # and under it; inside, down to the lowest knee brace pad
_MARGIN_IN = 24.0  # shell shown past the stair's ends
_TITLE_H = 18  # pixels over each view for its name
_GOOD = "#1a9e3a"
_MEASURE = "#6a1b9a"
_BAD = "#d40000"
_WELD = "#c62828"
_STRINGER = "#2f6f86"
_COLORS = {POST: "#f2c500", CLIP: "#2f6fdb", KNEE: "#ef7d00", SPLICE: "#0f766e", RAIL_SPLIT: "#c2185b",
           RADIAL: "#546e7a", PLATFORM_POST: "#f2c500"}
_RAIL_COLORS = {"Top rail": "#e0b400", "Midrail": "#e0b400", "Grab rail": "#a0522d", "Pipe": "#a0522d"}
# Each rail the game draws, the height box it moves, and what that box is called.
_RAIL_BOXES = {"Top rail": "rail_top", "Midrail": "flight_mid", "Platform midrail": "mid_top", "Grab rail": "grab_top",
               "Pipe": "inner_top"}
_BOX_NAMES = (("rail_top", "top rail"), ("flight_mid", "flights' midrail"), ("mid_top", "platforms' midrail"),
              ("grab_top", "grab rail"), ("inner_top", "inside pipe"))
_BEHIND = (PLATES, NOZZLES, FTCOS, ANCHORS)
HINT = ("Pick a piece from the tray and drop it on a stringer: green goes, red says why not. Drag a piece to move "
        "it, or into the bin. Both views are the whole stair on the shell's stretchout, seen from outside: red "
        "dashes are the shell's welds, and the clips' and knee braces' pads are where they land on the shell. "
        "Hover over anything for what it is. The wheel zooms, the right button pans. The Stairway tab builds what "
        "is here when its Place by the rules box is ticked (the handrail side is set there too).")


def build_game(parent, shared: dict, status_var: tk.StringVar) -> ttk.Frame:
    """The game's frame in ``parent``; the Stretchout tab shows it for its Stair game view. ``shared["stair_game"]``
    keeps the game between refreshes, so the Stairway tab can build what was placed."""
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    bar = ttk.Frame(frame, padding=(0, 0, 0, 4))
    bar.grid(row=0, column=0, sticky="ew")
    canvas = tk.Canvas(frame, background="#fbfaf6", highlightthickness=1, width=980, height=560)
    canvas.grid(row=1, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient="horizontal")
    scroll.grid(row=3, column=0, sticky="ew")
    heights_row = ttk.Frame(frame, padding=(0, 4, 0, 0))
    heights_row.grid(row=2, column=0, sticky="ew")
    defaults = RailHeights()
    height_vars = dict(shared.get("stairway_vars") or {
        "rail_top": tk.StringVar(value=f"{defaults.top:g}"), "flight_mid": tk.StringVar(value=""),
        "mid_top": tk.StringVar(value=f"{defaults.platform_mid:g}"),
        "grab_top": tk.StringVar(value=f"{defaults.grab:g}"),
        "inner_top": tk.StringVar(value=f"{defaults.inner:g}")})
    ttk.Label(heights_row, text="Rail heights, in:").pack(side="left")
    for key, label in _BOX_NAMES:
        ttk.Label(heights_row, text=label).pack(side="left", padx=(10, 0))
        ttk.Entry(heights_row, textvariable=height_vars[key], width=5).pack(side="left", padx=(4, 0))
    ttk.Label(heights_row, text="(or drag a rail up or down in the views; the flights' midrail blank is halfway)",
              foreground="#555555").pack(side="left", padx=(10, 0))
    say_var = tk.StringVar(value=HINT)
    say = tk.Label(frame, textvariable=say_var, font=("TkDefaultFont", 12, "bold"), anchor="w", justify="left",
                   wraplength=960, foreground="#333333", background=frame.winfo_toplevel().cget("background"))
    say.grid(row=4, column=0, sticky="ew", pady=(4, 0))
    warn_var = tk.StringVar(value="")
    ttk.Label(bar, textvariable=warn_var, foreground="#8a5a00", wraplength=700, justify="left").pack(side="left")

    state: dict = {"game": None, "sheet": None, "geo": None, "bands": {}, "drag": None, "zoom": 1.0,
                   "pan": (0.0, 0.0), "pan_from": None, "panning": False, "marks": [], "tiles": [], "bin": None,
                   "spot_of": {}, "said_of": {}, "pads": {}, "devs": {}, "rail_drag": None}
    measure_var = tk.BooleanVar(value=False)

    def tell(text: str, good: bool | None = None) -> None:
        say_var.set(text)
        say.configure(foreground="#333333" if good is None else (_GOOD if good else _BAD))

    def refresh() -> None:
        """Take the stair and the tank as the other tabs have them; keep what the user did if the stair is the
        same size."""
        source = shared.get("stairway_base") or shared.get("stairway")
        try:
            arrangement = source() if callable(source) else None
        except ValueError as exc:
            arrangement = None
            tell(f"The Stairway tab needs a correction first: {exc}", False)
        if arrangement is None:
            state["game"] = None
            draw()
            return
        sheet = None
        spec = shared.get("spec")
        if isinstance(spec, TankSpec) and spec.active_courses():
            try:
                sheet = build_stretchout(spec, nozzles=list(shared.get("nozzles") or []),
                                         cleanouts=list(shared.get("cleanouts") or []), anchors=shared.get("anchors"))
            except ValueError:
                sheet = None
        read_rules = shared.get("stair_rules")
        rules = read_rules() if callable(read_rules) else Rules()
        old: Game | None = shared.get("stair_game")
        game = Game(arrangement, Shell.of(sheet) if sheet is not None else None, rules)
        if old is not None and old.arrangement.stair == arrangement.stair \
                and old.arrangement.platforms == arrangement.platforms:
            game.choice, game.history = old.choice, old.history
        shared["stair_game"] = state["game"] = game
        state["sheet"] = sheet
        draw()

    def rail_heights() -> RailHeights:
        """The rails' heights as the boxes have them (a box that will not read keeps its default), with a rail being
        dragged at where it is now."""
        def number(key: str, default: float | None) -> float | None:
            try:
                text = height_vars[key].get().strip()
                return float(text) if text else default
            except (ValueError, tk.TclError):
                return default

        heights = RailHeights(number("rail_top", defaults.top), number("flight_mid", None),
                              number("mid_top", defaults.platform_mid), number("grab_top", defaults.grab),
                              number("inner_top", defaults.inner))
        drag = state["rail_drag"]
        if drag is not None:
            field = {"rail_top": "top", "flight_mid": "mid", "mid_top": "platform_mid", "grab_top": "grab",
                     "inner_top": "inner"}[drag["key"]]
            heights = replace(heights, **{field: drag["value"]})
        try:
            heights.validate()
        except ValueError:
            return defaults if drag is None else heights
        return heights

    def height_of(heights: RailHeights, key: str) -> float:
        return {"rail_top": heights.top, "flight_mid": heights.flight_mid, "mid_top": heights.platform_mid,
                "grab_top": heights.grab, "inner_top": heights.inner}[key]

    def rail_flags() -> dict:
        """The Stairway tab's top rail, midrail and grab rail boxes; all on without the tab."""
        source = shared.get("stairway_inputs")
        try:
            given = source() if callable(source) else {}
        except (ValueError, tk.TclError):
            given = {}
        return {"top": bool(given.get("top_rail", True)), "mid": bool(given.get("mid_rail", True)),
                "grab": bool(given.get("grab_rail", True)), "heights": rail_heights()}

    # ------------------------------------------------------------------------------------------ geometry

    def geometry() -> dict | None:
        """The stair on the shell's stretchout: where each flight's lanes are, the stretch of shell to show, the
        platforms, and the two views on the canvas."""
        game: Game | None = state["game"]
        if game is None:
            return None
        arrangement = game.arrangement
        where = stair_places(arrangement.stair, arrangement.stair.shell_od_in, arrangement.platforms,
                             arrangement.ground_in)
        inner, outer = develop_both(where.flight)
        devs = {OUTER: outer, INNER: inner}
        sheet: Stretchout | None = state["sheet"]
        girth = sheet.girth_in if sheet is not None else 2.0 * math.pi * arrangement.stair.shell_od_in
        pads = {}
        for spot in game.plan.spots:
            if spot.kind in (CLIP, KNEE):
                box = pad_box(arrangement, where, inner, spot)
                if box is not None:
                    pads[spot.key()] = (spot.flight, box)
        placed = applied(arrangement, game.plan)  # the platforms with the plan's radials
        count = arrangement.platforms + (1 if arrangement.top_platform else 0)
        marks = [m for m in shell_marks(placed)[0] if m.kind in (PLATFORM, PLATFORM_PAD, PLATFORM_KNEE_PAD)]
        geo = {"arrangement": arrangement, "where": where, "devs": devs, "girth": girth, "pads": pads,
               "marks": marks, "rooms": {}, "platforms": [platform_frame(placed, where, k)[0] for k in range(count)]}
        for side, dev in devs.items():
            low = _ROOM_LOW_IN
            if side == INNER:
                for _flight, (x0, y0, x1, _y1) in pads.values():
                    low = max(low, _span(dev, (x0 + x1) / 2.0)[0] - y0 + 3.0)
            geo["rooms"][side] = low
        xs, ys = [], [0.0]
        for side, dev in devs.items():
            for k in range(len(where.offsets)):
                for x, y in dev.outline:
                    at_x, at_y = lane_point(geo, side, k, x, y)
                    xs.append(at_x)
                    ys += [at_y - geo["rooms"][side], at_y + _ROOM_TOP_IN]
        for mark in marks:
            points = mark.outline or ((mark.center[0], mark.center[1]),)
            xs += [view_x(arrangement, a, girth) for a, _y in points]
        geo["window"] = (min(xs) - _MARGIN_IN, max(xs) + _MARGIN_IN)
        geo["heights"] = (min(ys) - 4.0, max(ys))
        state["pads"], state["devs"] = pads, devs
        width, height = max(canvas.winfo_width(), 600), max(canvas.winfo_height(), 320)
        left, right = TRAY_W + 16, width - 8
        band_h = (height - 14 - 2 * _TITLE_H) / 2.0
        (xa, xb), (ya, yb) = geo["window"], geo["heights"]
        fit = min((right - left - 12) / (xb - xa), (band_h - 12) / (yb - ya))
        # Fill the views at the fit: more shell either side of the stair, or over it.
        grow = ((right - left - 12) / fit - (xb - xa)) / 2.0
        xa, xb = xa - grow, xb + grow
        yb = ya + (band_h - 12) / fit
        geo["window"], geo["heights"] = (xa, xb), (ya, yb)
        scale = fit * state["zoom"]
        pan_x, pan_y = state["pan"]
        state["span"] = ((xb - xa) * scale + 12, right - left)
        bands = {}
        top = 4 + _TITLE_H
        for side in (OUTER, INNER):
            box = (left, top, right, top + band_h)
            bands[side] = {"side": side, "box": box, "scale": scale,
                           "ox": left + 6 + pan_x - xa * scale, "oy": box[3] - 6 + pan_y + ya * scale}
            top += band_h + 6 + _TITLE_H
        state["bands"] = bands
        return geo

    def lane_point(geo: dict, side: str, flight: int, x: float, y: float) -> tuple[float, float]:
        """A point (x, y in) on ``flight``'s ``side`` lane, on the shell's stretchout: its angle round the tank
        across, its height up."""
        dev = geo["devs"][side]
        turn, lift = geo["where"].offsets[flight]
        return view_x(geo["arrangement"], turn + x / dev.radius_in, geo["girth"]), lift + y

    def to_px(band: dict, x: float, y: float) -> tuple[float, float]:
        return band["ox"] + x * band["scale"], band["oy"] - y * band["scale"]

    def lane_px(side: str, flight: int, x: float, y: float) -> tuple[float, float]:
        """A lane point on the canvas, in its side's view."""
        return to_px(state["bands"][side], *lane_point(state["geo"], side, flight, x, y))

    def poly(band: dict, points, **options) -> int | None:
        cut = _clip_polygon([to_px(band, *p) for p in points], band["box"])
        return canvas.create_polygon(*[v for p in cut for v in p], **options) if len(cut) >= 3 else None

    def line(band: dict, a, b, **options) -> int | None:
        cut = _clip_line(to_px(band, *a), to_px(band, *b), band["box"])
        return canvas.create_line(*cut[0], *cut[1], **options) if cut else None

    def said(text: str) -> tuple[str, str]:
        """Tags that make an item tell ``text`` when the pointer is over it."""
        tag = f"said{len(state['said_of'])}"
        state["said_of"][tag] = text
        return ("said", tag)

    # ------------------------------------------------------------------------------------------- drawing

    def draw() -> None:
        canvas.delete("all")
        state["spot_of"], state["said_of"] = {}, {}
        try:
            state["geo"] = geo = geometry()
        except ValueError as exc:  # a stair the build would refuse
            state["geo"] = geo = None
            tell(f"The Stairway tab needs a correction first: {exc}", False)
        draw_tray()
        total, shown = state.get("span", (1.0, 1.0))
        first = min(max(-state["pan"][0] / total, 0.0), 1.0) if total > 0 else 0.0
        scroll.set(first, min(first + shown / total, 1.0) if total > 0 else 1.0)
        game: Game | None = state["game"]
        if game is None or geo is None:
            canvas.create_text(TRAY_W + 60, 60, anchor="nw", font=("TkDefaultFont", 12),
                               text="Set the stair on the Stairway tab, then come back here.")
            return
        current = game.plan
        warn_var.set(" ".join(current.warnings[:3]) + (" …" if len(current.warnings) > 3 else ""))
        flags = rail_flags()
        for side, band in state["bands"].items():
            x0, y0, x1, y1 = band["box"]
            name = ("Outside stringer" if side == OUTER else "Inside stringer, by the shell") + \
                ": the whole stair on the shell's stretchout, seen from outside"
            canvas.create_text(x0, y0 - 2, anchor="sw", text=name, font=("TkDefaultFont", 10, "bold"))
            canvas.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#8c8170")
            draw_shell(band, geo)
            draw_stair(band, geo, current, flags)
        canvas.tag_bind("placed", "<Enter>", on_hover)
        canvas.tag_bind("said", "<Enter>", on_hover_said)
        draw_marks()

    def draw_marks() -> None:
        """The measuring tool's points and, with two, the line between them and what it measures."""
        marks = state["marks"]
        band = state["bands"].get(marks[0][0]) if marks else None
        if band is None:
            return
        points = [to_px(band, x, y) for _side, x, y in marks]
        for px, py in points:
            canvas.create_line(px - 7, py, px + 7, py, fill=_MEASURE, width=2)
            canvas.create_line(px, py - 7, px, py + 7, fill=_MEASURE, width=2)
        if len(points) == 2:
            canvas.create_line(*points[0], *points[1], fill=_MEASURE, width=2, dash=(6, 3))
            (_s, x0, y0), (_s2, x1, y1) = marks
            canvas.create_text((points[0][0] + points[1][0]) / 2.0, (points[0][1] + points[1][1]) / 2.0 - 10,
                               text=measured(x1 - x0, y1 - y0), fill=_MEASURE, font=("TkDefaultFont", 10, "bold"))

    def draw_shell(band: dict, geo: dict) -> None:
        """The shell behind: its plates, weld seams, nozzles, FTCOs and anchor chairs, the degrees round it."""
        sheet: Stretchout | None = state["sheet"]
        x0, y0, x1, y1 = band["box"]
        xa, xb = (x0 - band["ox"]) / band["scale"], (x1 - band["ox"]) / band["scale"]  # what the view shows
        if sheet is None:
            canvas.create_text(x0 + 8, y0 + 8, anchor="nw", fill="#8a5a00", font=("TkDefaultFont", 9),
                               text="Set the tank on Tank Properties to see the shell behind.")
            return
        girth = sheet.girth_in
        shifts = [k * girth for k in range(math.floor(xa / girth) - 1, math.ceil(xb / girth) + 1)]
        for shift in shifts:
            for layer in _BEHIND:
                fill, outline = STYLE[layer]
                for item in sheet.items:
                    if item.layer != layer or item.box[2] + shift < xa or item.box[0] + shift > xb:
                        continue
                    points = [(x + shift, y) for x, y in item.outline]
                    if layer == PLATES:
                        poly(band, points, fill=COURSE_FILLS[int(item.label.split()[0][1:]) % 2], outline=outline,
                             tags=said(item.info or item.label))
                    else:
                        poly(band, points, fill=fill, outline=outline, width=2, tags=said(item.info or item.label))
        for shift in shifts:  # over every plate, the next turn's too
            for seam in sheet.seams:
                if max(seam.x0, seam.x1) + shift < xa or min(seam.x0, seam.x1) + shift > xb:
                    continue
                line(band, (seam.x0 + shift, seam.y0), (seam.x1 + shift, seam.y1), fill=_WELD, width=2,
                     dash=(6, 4), tags=said(f"Shell weld: {seam.label}."))
        line(band, (xa, 0.0), (xb, 0.0), fill=_WELD, width=2, dash=(6, 4),
             tags=said("Shell weld: the floor weld, shell to bottom."))
        step = 5 if girth * band["scale"] > 2400 else (15 if girth * band["scale"] > 900 else 30)
        for degrees in range(0, 360, step):
            for shift in shifts:
                px = to_px(band, girth * (1.0 - degrees / 360.0) + shift, 0.0)[0]
                if x0 + 14 < px < x1 - 14:
                    canvas.create_line(px, y0, px, y0 + 6, fill="#333333")
                    canvas.create_text(px, y0 + 7, text=f"{degrees}°", anchor="n", font=("TkDefaultFont", 8))
        for seam in sorted((s for s in sheet.seams if not s.vertical), key=lambda s: s.y0):
            py = to_px(band, xa, seam.y0)[1]
            if y0 + 20 < py < y1 - 4:
                canvas.create_text(x0 + 4, py - 1, text=f"EL {seam.y0:g}", anchor="sw", font=("TkDefaultFont", 8),
                                   fill="#555555")

    def draw_stair(band: dict, geo: dict, current, flags: dict) -> None:
        """One side's stringer of every flight, its treads, the platforms, the handrail and the pieces."""
        side = band["side"]
        arrangement, girth, dev = geo["arrangement"], geo["girth"], geo["devs"][side]
        for mark in geo["marks"]:
            if mark.kind == PLATFORM:
                fill, outline = STYLE[PLATFORMS]
                poly(band, [(view_x(arrangement, a, girth), y) for a, y in mark.outline], fill=fill, outline=outline,
                     width=2, tags=said(mark.label))
            elif side == INNER:  # its shell pads, on the shell by the inside stringer
                fill, outline = STYLE[PLATFORM_PADS]
                x, y = view_x(arrangement, mark.center[0], girth), mark.center[1]
                wide, tall = mark.size
                poly(band, _rect(x - wide / 2.0, y - tall / 2.0, x + wide / 2.0, y + tall / 2.0), fill=fill,
                     outline=outline, tags=said(mark.label))
        draw_platforms(band, geo, current)
        tread_fill, tread_outline = STYLE[TREADS]
        for k in range(len(geo["where"].offsets)):
            outline = [lane_point(geo, side, k, x, y) for x, y in dev.outline]
            for a, b in zip(outline, outline[1:] + outline[:1], strict=True):
                line(band, a, b, fill=_STRINGER, width=2)
            for number, center in enumerate(dev.tread_centers, start=1):
                poly(band, [lane_point(geo, side, k, *p) for p in tread_rect(center)], fill=tread_fill,
                     outline=tread_outline, tags=said(f"Flight {k + 1}, tread {number}"))
                if number == 1 or number % 5 == 0:
                    at = to_px(band, *lane_point(geo, side, k, center[0], center[1] - 4.0))
                    if _inside(band, at):
                        canvas.create_text(*at, text=str(number), font=("TkDefaultFont", 8), fill="#444444",
                                           anchor="n")
            foot = to_px(band, *lane_point(geo, side, k, dev.tread_centers[0][0], dev.tread_centers[0][1] - 12.0))
            if _inside(band, foot):
                canvas.create_text(*foot, text=f"Flight {k + 1}", font=("TkDefaultFont", 9, "bold"),
                                   fill=_STRINGER, anchor="n")
            posts = tuple(s.tread for s in current.of_kind(POST, side) if s.flight == k)
            for rail in lane_rails(dev, side, posts, **flags):
                corners = ((rail.x0, rail.y0), (rail.x1, rail.y1), (rail.x1, rail.y1 - rail.tall),
                           (rail.x0, rail.y0 - rail.tall))
                text = f"{rail.name}, flight {k + 1}" + (" (1-1/2 in pipe)" if rail.name in ("Grab rail", "Pipe")
                                                         else "")
                poly(band, [lane_point(geo, side, k, *p) for p in corners], fill=_RAIL_COLORS[rail.name],
                     outline="#5b4500", tags=(*said(text), "rail", f"rail={rail.name}"))
            for spot in current.spots:
                if spot.flight == k and spot.kind not in ON_PLATFORMS and side in _lanes_of(spot):
                    tag = f"spot{len(state['spot_of'])}"
                    draw_piece(band, spot, posts, tags=("placed", tag))
                    state["spot_of"][tag] = spot

    def draw_platforms(band: dict, geo: dict, current) -> None:
        """Each platform's knee braces (inside, to their pads), its rails between its outer posts (outside), and
        its radials and posts as game pieces."""
        side = band["side"]
        arrangement, girth = geo["arrangement"], geo["girth"]
        for k, lines in enumerate(geo["platforms"]):
            floor = lines.top + GRATING_IN
            if side == INNER:
                try:
                    knees = platform_knees(lines, arrangement.stair.shell_od_in)
                except SolidWorksError:
                    knees = []
                for label, frame, knee, _back in knees:
                    x = view_x(arrangement, frame.phi, girth)
                    line(band, (x, knee.top[1]), (x, knee.bottom[1]), fill=_COLORS[KNEE], width=3,
                         tags=said(f"Platform {k + 1}: knee brace {label}"))
            posts = sorted(s.tread for s in current.of_kind(PLATFORM_POST, side) if s.flight == k)
            if side == OUTER and len(posts) > 1:
                ends = [view_x(arrangement, lines.phi_a + t / lines.r_mid, girth) for t in (posts[0], posts[-1])]
                heights = rail_heights()
                for above, name, rail in ((heights.top, "top rail", "Top rail"),
                                          (heights.platform_mid, "midrail", "Platform midrail")):
                    line(band, (ends[0], floor + above), (ends[1], floor + above), fill=_RAIL_COLORS["Top rail"],
                         width=3, tags=(*said(f"Platform {k + 1}: {name}"), "rail", f"rail={rail}"))
            for spot in current.spots:
                if spot.kind in ON_PLATFORMS and spot.flight == k and side in _lanes_of(spot):
                    tag = f"spot{len(state['spot_of'])}"
                    draw_platform_piece(band, spot, tags=("placed", tag))
                    state["spot_of"][tag] = spot

    def platform_point(spot: Spot, height: float) -> tuple[float, float] | None:
        """Where a platform piece is in view inches: its angle along the platform, at ``height`` over its top."""
        geo = state["geo"]
        if geo is None or not 0 <= spot.flight < len(geo["platforms"]):
            return None
        lines = geo["platforms"][spot.flight]
        return view_x(geo["arrangement"], lines.phi_a + spot.tread / lines.r_mid, geo["girth"]), lines.top + height

    def draw_platform_piece(band: dict, spot: Spot, outline: str = "#222222", tags=()) -> None:
        anchor = platform_point(spot, 0.0)
        if anchor is None or not _inside(band, to_px(band, *anchor)):
            return
        cx, cy = to_px(band, *anchor)
        if spot.kind == RADIAL:  # the radial channel's end, seen from outside: 4 or 6 in deep under the grating
            depth = state["geo"]["platforms"][spot.flight].section.depth_in
            low = to_px(band, anchor[0], anchor[1] - depth)[1]
            canvas.create_rectangle(cx - 4, min(cy, low - 6), cx + 4, max(low, cy + 6), fill=_COLORS[RADIAL],
                                    outline=outline, width=2, tags=tags)
        else:
            top = to_px(band, anchor[0], anchor[1] + GRATING_IN + rail_heights().top - TOP_GAP_IN)
            canvas.create_line(cx, cy, top[0], max(top[1], band["box"][1]), fill=_COLORS[POST], width=7, tags=tags)
            canvas.create_line(cx, cy, top[0], max(top[1], band["box"][1]), fill=outline, width=1, tags=tags)
        if spot.pinned:
            canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#000000", outline="", tags=tags)

    def draw_tray() -> None:
        state["tiles"] = []
        canvas.create_rectangle(0, 0, TRAY_W, 2000, fill="#efe9dc", outline="")
        canvas.create_text(12, 8, anchor="nw", text="Pieces", font=("TkDefaultFont", 11, "bold"))
        for index, piece in enumerate(TRAY):
            y = 30 + index * TILE_H
            canvas.create_rectangle(8, y, TRAY_W - 8, y + TILE_H - 6, fill="#ffffff", outline="#b9b09c", width=2)
            icon(piece.kind, 34, y + (TILE_H - 6) / 2.0, big=True)
            canvas.create_text(62, y + (TILE_H - 6) / 2.0, anchor="w", text=piece.name, font=("TkDefaultFont", 10))
            state["tiles"].append((piece, (8, y, TRAY_W - 8, y + TILE_H - 6)))
        y = 30 + len(TRAY) * TILE_H + 6
        canvas.create_rectangle(8, y, TRAY_W - 8, y + 56, fill="#f7e1e1", outline="#b34040", width=2, dash=(4, 3))
        canvas.create_text(TRAY_W / 2.0, y + 28, text="🗑  Bin: drop here to remove", font=("TkDefaultFont", 10))
        state["bin"] = (8, y, TRAY_W - 8, y + 56)

    def icon(kind: str, x: float, y: float, big: bool = False, outline: str = "#222222", tags=()) -> None:
        k = 1.6 if big else 1.0
        color = _COLORS[kind]
        if kind == POST:
            canvas.create_rectangle(x - 3 * k, y - 12 * k, x + 3 * k, y + 12 * k, fill=color, outline=outline,
                                    tags=tags)
        elif kind == CLIP:
            canvas.create_rectangle(x - 6 * k, y - 6 * k, x + 6 * k, y + 6 * k, fill=color, outline=outline, tags=tags)
        elif kind == KNEE:
            canvas.create_line(x - 7 * k, y - 7 * k, x + 7 * k, y + 7 * k, fill=color, width=5 * k, tags=tags)
            canvas.create_oval(x + 4 * k, y + 4 * k, x + 10 * k, y + 10 * k, fill=color, outline=outline, tags=tags)
        elif kind == SPLICE:
            canvas.create_rectangle(x - 4 * k, y - 10 * k, x + 4 * k, y + 10 * k, fill=color, outline=outline,
                                    tags=tags)
        elif kind == RADIAL:  # a channel end: web and two flanges
            canvas.create_polygon(x - 5 * k, y - 10 * k, x + 5 * k, y - 10 * k, x + 5 * k, y - 7 * k, x - 2 * k,
                                  y - 7 * k, x - 2 * k, y + 7 * k, x + 5 * k, y + 7 * k, x + 5 * k, y + 10 * k,
                                  x - 5 * k, y + 10 * k, fill=color, outline=outline, tags=tags)
        else:
            canvas.create_polygon(x, y - 8 * k, x + 8 * k, y, x, y + 8 * k, x - 8 * k, y, fill=color, outline=outline,
                                  tags=tags)

    def pad_of(spot: Spot) -> tuple | None:
        """The shell pad of a clip or knee brace at ``spot`` on its inside lane, placed or being dragged."""
        if spot.key() in state["pads"]:
            return state["pads"][spot.key()][1]
        geo = state["geo"]
        return pad_box(geo["arrangement"], geo["where"], geo["devs"][INNER], spot) if geo is not None else None

    def draw_piece(band: dict, spot: Spot, posts: tuple[int, ...], outline: str = "#222222", tags=()) -> None:
        side, flight = band["side"], spot.flight
        dev = state["geo"]["devs"][side]
        x, y = spot_xy(dev, spot, posts, rail_heights())
        cx, cy = lane_px(side, flight, x, y)
        if not _inside(band, (cx, cy)):
            return
        pad = pad_of(spot) if spot.kind in (CLIP, KNEE) else None
        if pad is not None:  # the pad on the shell, and the member out to it
            corners = [lane_point(state["geo"], side, flight, *p) for p in _rect(*pad)]
            line(band, lane_point(state["geo"], side, flight, x, y),
                 lane_point(state["geo"], side, flight, (pad[0] + pad[2]) / 2.0, (pad[1] + pad[3]) / 2.0),
                 fill=_COLORS[spot.kind], width=6 if spot.kind == KNEE else 3, tags=tags)
            poly(band, corners, fill=_COLORS[spot.kind], outline=outline, width=2, tags=tags)
        if spot.kind == POST:
            top = lane_px(side, flight, x, post_top(dev, side, x, rail_heights()))
            canvas.create_line(cx, cy, top[0], max(top[1], band["box"][1]), fill=_COLORS[POST], width=7, tags=tags)
            canvas.create_line(cx, cy, top[0], max(top[1], band["box"][1]), fill=outline, width=1, tags=tags)
        elif spot.kind == KNEE:
            if pad is None:  # not to scale: the build would not place it here
                line(band, lane_point(state["geo"], side, flight, x, y),
                     lane_point(state["geo"], side, flight, x + 12.0, y - 24.0), fill=_COLORS[KNEE], width=6,
                     tags=tags)
            canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=_COLORS[KNEE], outline=outline, tags=tags)
        elif spot.kind == SPLICE:
            bottom = lane_px(side, flight, x, y - 7.0)
            top = lane_px(side, flight, x, y + 7.0)
            canvas.create_rectangle(cx - 5, top[1], cx + 5, bottom[1], fill=_COLORS[SPLICE], outline=outline,
                                    tags=tags)
        else:
            icon(spot.kind, cx, cy, outline=outline, tags=tags)
        if spot.pinned:
            canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#000000", outline="", tags=tags)

    # ----------------------------------------------------------------------------------------- the game

    def band_at(event) -> dict | None:
        for band in state["bands"].values():
            x0, y0, x1, y1 = band["box"]
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                return band
        return None

    def target(event, piece: Piece) -> tuple[dict, int, int, Piece] | None:
        """Where the dragged piece would snap: its view, its flight (or platform) and tread (or inches along the
        platform), and the piece as it goes there (a post on a platform is a platform post); None off the stair."""
        band = band_at(event)
        game: Game | None = state["game"]
        geo = state["geo"]
        if band is None or game is None or geo is None or band["side"] not in piece.lanes():
            return None
        side = band["side"]
        dev = geo["devs"][side]
        x_view = (event.x - band["ox"]) / band["scale"]
        height = (band["oy"] - event.y) / band["scale"]
        angle = view_angle(geo["arrangement"], x_view, geo["girth"])
        for k, lines in enumerate(geo["platforms"]):
            ends = sorted(view_x(geo["arrangement"], a, geo["girth"]) for a in (lines.phi_a, lines.phi_b))
            if ends[0] - 4.0 <= x_view <= ends[1] + 4.0 and lines.top - 24.0 <= height <= lines.top + 54.0:
                kind = {POST: PLATFORM_POST, PLATFORM_POST: PLATFORM_POST, RADIAL: RADIAL}.get(piece.kind)
                if kind is None:
                    return None
                return band, k, round((angle - lines.phi_a) * lines.r_mid), replace(piece, kind=kind)
        if piece.kind == RADIAL:
            return None
        xs = [x for x, _y in dev.outline]
        for flight, (turn, lift) in enumerate(geo["where"].offsets):
            x = (angle - turn) * dev.radius_in
            if not min(xs) - 12.0 <= x <= max(xs) + 12.0:
                continue
            bottom, top = _span(dev, x)
            if bottom - geo["rooms"][side] - 4.0 <= height - lift <= max(top, edge_y(dev, x)) + _ROOM_TOP_IN + 4.0:
                posts = tuple(s.tread for s in game.plan.of_kind(POST, piece.side) if s.flight == flight)
                kind = POST if piece.kind == PLATFORM_POST else piece.kind
                return band, flight, slot(dev, kind, x, posts), replace(piece, kind=kind)
        return None

    def in_box(event, box) -> bool:
        return box is not None and box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]

    def on_press(event) -> None:
        if measure_var.get():
            measure_at(event)
            return
        for piece, box in state["tiles"]:
            if in_box(event, box):
                state["drag"] = (piece, None)
                tell(f"{piece.name}: drop it on {_where(piece)}.")
                return
        for item in reversed(canvas.find_overlapping(event.x - 3, event.y - 3, event.x + 3, event.y + 3)):
            spot = next((state.get("spot_of", {}).get(tag) for tag in canvas.gettags(item)
                         if tag.startswith("spot")), None)
            if spot is not None:
                state["drag"] = (_piece_of(spot), spot)
                tell(f"Moving the {spot.label().lower()}.")
                return
        rail, band = rail_at(event), band_at(event)
        if rail is not None and band is not None:
            key = _RAIL_BOXES[rail]
            value = height_of(rail_heights(), key)
            state["rail_drag"] = {"rail": rail, "key": key, "y": event.y, "start": value, "value": value,
                                  "scale": band["scale"]}
            tell(f"The {rail.lower()}, {inches(value)} up: drag it up or down; it goes in 1/4 in steps.")
            return
        # Empty space: dragging it moves the view, as the right button does.
        state["panning"] = True
        on_pan_start(event)

    def rail_at(event) -> str | None:
        """The rail under the pointer, the one whose middle line is nearest where rails lie close together."""
        best = None
        for item in canvas.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4):
            rail = next((tag[5:] for tag in canvas.gettags(item) if tag.startswith("rail=")), None)
            if rail is None:
                continue
            points = canvas.coords(item)
            pts = list(zip(points[0::2], points[1::2], strict=True))
            if len(pts) >= 4:  # a rail's band: its middle line, from the middle of one end to the other's
                a = ((pts[0][0] + pts[-1][0]) / 2.0, (pts[0][1] + pts[-1][1]) / 2.0)
                b = ((pts[1][0] + pts[2][0]) / 2.0, (pts[1][1] + pts[2][1]) / 2.0)
            else:
                a, b = pts[0], pts[-1]
            gap = _to_segment((event.x, event.y), a, b)
            if best is None or gap < best[0]:
                best = (gap, rail)
        return None if best is None else best[1]

    def measure_at(event) -> None:
        """A point for the measuring tool, to the nearest 1/4 in on a view; a third starts a new measure."""
        band = band_at(event)
        if band is None:
            tell("Measure: click two points on one of the views.")
            return
        x = _snap((event.x - band["ox"]) / band["scale"])
        y = _snap((band["oy"] - event.y) / band["scale"])
        marks = state["marks"]
        if len(marks) >= 2 or (marks and marks[0][0] != band["side"]):
            marks.clear()
        marks.append((band["side"], x, y))
        draw()
        if len(marks) == 2:
            (_s, x0, y0), (_s2, x1, y1) = marks
            tell(f"Measured {measured(x1 - x0, y1 - y0)}. Click again for a new measure.", True)
        else:
            tell("Measure: now click the second point.")

    def on_motion(event) -> None:
        if state["panning"]:
            on_pan(event)
            return
        drag = state["rail_drag"]
        if drag is not None:
            drag["value"] = snap(drag["start"] + (drag["y"] - event.y) / drag["scale"])
            draw()
            tell(f"The {drag['rail'].lower()}: {inches(drag['value'])} up. Let go to set it.")
            return
        drag = state["drag"]
        if drag is None:
            return
        piece, moving = drag
        canvas.delete("ghost")
        if in_box(event, state["bin"]):
            tell("Let go to throw it away." if moving is not None else "That's the bin: drop pieces on a stringer.",
                 moving is not None)
            icon(piece.kind, event.x, event.y, big=True, tags=("ghost",))
            return
        found = target(event, piece)
        if found is None:
            icon(piece.kind, event.x, event.y, big=True, tags=("ghost",))
            tell(f"{piece.name} goes on {_where(piece)}.", None)
            return
        band, flight, tread, piece = found
        ok, reason = state["game"].try_drop(piece, flight, tread, moving)
        spot = Spot(piece.kind, flight, tread, piece.side)
        if piece.kind in ON_PLATFORMS:
            draw_platform_piece(band, spot, outline=_GOOD if ok else _BAD, tags=("ghost",))
            cx, cy = to_px(band, *platform_point(spot, 0.0))
            where = f"Platform {flight + 1}, {tread} in along it"
        else:
            posts = tuple(s.tread for s in state["game"].plan.of_kind(POST, piece.side) if s.flight == flight)
            draw_piece(band, spot, posts, outline=_GOOD if ok else _BAD, tags=("ghost",))
            cx, cy = lane_px(band["side"], flight, *spot_xy(state["geo"]["devs"][band["side"]], spot, posts))
            where = f"Flight {flight + 1}, tread {tread}"
        canvas.create_oval(cx - 14, cy - 14, cx + 14, cy + 14, outline=_GOOD if ok else _BAD, width=3,
                           tags=("ghost",))
        tell(f"{where}: {reason}", ok)

    def on_release(event) -> None:
        if state["panning"]:
            state["panning"], state["pan_from"] = False, None
            return
        drag, state["rail_drag"] = state["rail_drag"], None
        if drag is not None:
            height_vars[drag["key"]].set(f"{drag['value']:g}")
            try:
                rail_heights().validate()
            except ValueError as exc:
                height_vars[drag["key"]].set(f"{drag['start']:g}")
                tell(f"Not there: {exc}", False)
            else:
                tell(f"The {drag['rail'].lower()} is {inches(drag['value'])} up now.", True)
            draw()
            return
        drag, state["drag"] = state["drag"], None
        canvas.delete("ghost")
        if drag is None:
            return
        piece, moving = drag
        game: Game = state["game"]
        if in_box(event, state["bin"]) and moving is not None:
            game.throw_away(moving)
            if moving.kind == RADIAL and any(s.flight == moving.flight and abs(s.tread - moving.tread) <= 1
                                             for s in game.plan.of_kind(RADIAL)):
                game.undo()  # the rules put it straight back: the bay would be too long without it
                tell("That radial has to stay: without it a bay would pass the platform's radial spacing. "
                     "Drag it along instead.", False)
                return
            tell(f"Thrown away: {moving.label().lower()}.", True)
            changed()
            return
        found = target(event, piece)
        if found is None:
            tell(f"Not placed: {piece.name.lower()} goes on {_where(piece)}.", None)
            return
        _band, flight, tread, piece = found
        ok, reason = game.drop(piece, flight, tread, moving)
        where = f"platform {flight + 1}, {tread} in along it" if piece.kind in ON_PLATFORMS else \
            f"flight {flight + 1}, tread {tread}"
        tell(f"Placed at {where}." if ok else f"Not there: {reason}", ok)
        if ok:
            changed()

    def on_hover(event) -> None:
        if state["drag"] is not None:
            return
        for item in canvas.find_overlapping(event.x - 2, event.y - 2, event.x + 2, event.y + 2):
            spot = next((state.get("spot_of", {}).get(tag) for tag in canvas.gettags(item)
                         if tag.startswith("spot")), None)
            if spot is not None:
                tell(f"{spot.label()}{' (you placed it)' if spot.pinned else ' (by the rules)'}. Drag to move it.")
                return

    def on_hover_said(event) -> None:
        if state["drag"] is not None:
            return
        for item in reversed(canvas.find_overlapping(event.x - 2, event.y - 2, event.x + 2, event.y + 2)):
            text = next((state["said_of"].get(tag) for tag in canvas.gettags(item) if tag.startswith("said")), None)
            if text is not None:
                tell(text)
                return

    def changed() -> None:
        status_var.set(f"Stair game: {len(state['game'].plan.spots)} pieces placed.")
        draw()
        hook = shared.get("stair_game_changed")
        if callable(hook):
            hook()

    def undo() -> None:
        if state["game"] is not None and state["game"].undo():
            tell("Undone.", True)
            changed()

    def auto() -> None:
        if state["game"] is not None:
            state["game"].auto_place()
            tell("Placed by the rules; your pinned pieces stayed.", True)
            changed()

    def start_over() -> None:
        if state["game"] is not None:
            state["game"].start_over()
            tell("Started over: everything by the rules.", True)
            changed()

    def on_wheel(event) -> None:
        factor = 1.25 if event.delta > 0 else 0.8
        zoom = max(0.5, min(40.0, state["zoom"] * factor))
        factor = zoom / state["zoom"]
        band = band_at(event) or state["bands"].get(OUTER)
        if band is None:
            return
        # Keep the point under the pointer still.
        pan_x, pan_y = state["pan"]
        left, bottom = band["box"][0] + 6, band["box"][3] - 6
        state["pan"] = (event.x - left - (event.x - left - pan_x) * factor,
                        event.y - bottom + (bottom + pan_y - event.y) * factor)
        state["zoom"] = zoom
        draw()

    def on_pan_start(event) -> None:
        state["pan_from"] = (event.x, event.y)

    def on_pan(event) -> None:
        if state["pan_from"] is not None:
            (pan_x, pan_y), (x, y) = state["pan"], state["pan_from"]
            state["pan"] = (pan_x + event.x - x, pan_y + event.y - y)
            state["pan_from"] = (event.x, event.y)
            draw()

    def on_scroll(*args) -> None:
        total, shown = state.get("span", (1.0, 1.0))
        pan_x, pan_y = state["pan"]
        if args[0] == "moveto":
            pan_x = -float(args[1]) * total
        else:
            pan_x -= int(args[1]) * (shown * 0.9 if args[2] == "pages" else 40.0)
        state["pan"] = (min(0.0, max(pan_x, shown - total)) if total > shown else 0.0, pan_y)
        draw()

    def on_measure() -> None:
        state["marks"].clear()
        draw()
        tell("Measure: click two points on a view; they snap to 1/4 in." if measure_var.get() else HINT)

    scroll.configure(command=on_scroll)
    ttk.Checkbutton(bar, text="Measure", variable=measure_var, command=on_measure).pack(side="right", padx=(6, 0))
    ttk.Button(bar, text="Undo", command=undo).pack(side="right")
    ttk.Button(bar, text="Start over", command=start_over).pack(side="right", padx=(0, 6))
    ttk.Button(bar, text="Auto place", command=auto).pack(side="right", padx=(0, 6))
    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_motion)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<ButtonPress-3>", on_pan_start)
    canvas.bind("<B3-Motion>", on_pan)
    canvas.bind("<Configure>", lambda _e: draw())
    for var in height_vars.values():  # a height typed in a box shows at once
        var.trace_add("write", lambda *_a: draw() if state["rail_drag"] is None else None)
    # For the tab, and for the tests to play it.
    frame.refresh = refresh  # type: ignore[attr-defined]
    frame.game_events = {  # type: ignore[attr-defined]
        "press": on_press, "motion": on_motion, "release": on_release, "wheel": on_wheel}
    frame.measure = measure_var  # type: ignore[attr-defined]
    frame.height_vars = height_vars  # type: ignore[attr-defined]
    frame.game_state = state  # type: ignore[attr-defined]
    frame.lane_px = lane_px  # type: ignore[attr-defined]
    frame.platform_px = lambda side, spot: (  # type: ignore[attr-defined]
        to_px(state["bands"][side], *platform_point(spot, 0.0)))
    frame.said = say_var  # type: ignore[attr-defined]
    return frame


def _to_segment(p, a, b) -> float:
    """How far point ``p`` is from the segment ``a``-``b``, in canvas pixels."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    k = 0.0 if length == 0.0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return math.hypot(p[0] - a[0] - k * dx, p[1] - a[1] - k * dy)


def _snap(value: float) -> float:
    """To the nearest 1/4 in."""
    return round(value * 4.0) / 4.0


def inches(value: float) -> str:
    """A length to the nearest 1/16 in, as feet and inches from a foot up: 4'-2 1/4", or 7 1/2"."""
    sixteenths = round(abs(value) * 16.0)
    feet, rest = divmod(sixteenths, 192)
    whole, part = divmod(rest, 16)
    fraction = ""
    if part:
        top, bottom = part, 16
        while top % 2 == 0:
            top, bottom = top // 2, bottom // 2
        fraction = f"{top}/{bottom}"
    if feet:
        return f"{feet}'-{whole} {fraction}\"" if fraction else f"{feet}'-{whole}\""
    return (f"{whole} {fraction}" if whole and fraction else fraction or f"{whole}") + '"'


def measured(across: float, up: float) -> str:
    """What the measuring tool shows: straight between the points, across the shell's stretchout, and up."""
    return f"{inches(math.hypot(across, up))} ({inches(across)} across, {inches(up)} up)"


def _span(dev, x: float) -> tuple[float, float]:
    """The stringer's bottom and top over ``x``, held at its ends past them."""
    xs = [p[0] for p in dev.outline]
    return span_at(dev.outline, min(max(x, min(xs) + 1e-6), max(xs) - 1e-6)) or (0.0, 0.0)


def _rect(x0: float, y0: float, x1: float, y1: float) -> tuple[tuple[float, float], ...]:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _inside(band: dict, point) -> bool:
    x0, y0, x1, y1 = band["box"]
    return x0 <= point[0] <= x1 and y0 <= point[1] <= y1


def _clip_polygon(points, box) -> list[tuple[float, float]]:
    """``points`` (a closed polygon on the canvas) cut to the rectangle ``box``: (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    kept = list(points)
    for keep, meet in ((lambda p: p[0] >= x0, at_x(x0)), (lambda p: p[0] <= x1, at_x(x1)),
                       (lambda p: p[1] >= y0, at_y(y0)), (lambda p: p[1] <= y1, at_y(y1))):
        if not kept:
            break
        out = []
        for i, p in enumerate(kept):
            q = kept[i - 1]
            if keep(p):
                if not keep(q):
                    out.append(meet(q, p))
                out.append(p)
            elif keep(q):
                out.append(meet(q, p))
        kept = out
    return kept


def _clip_line(a, b, box):
    """The part of the segment ``a``-``b`` inside the rectangle ``box``, or None."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)


def _lanes_of(spot: Spot) -> tuple[str, ...]:
    if spot.kind in (POST, RAIL_SPLIT, PLATFORM_POST):
        return (spot.side,)
    if spot.kind in (CLIP, KNEE):
        return (INNER,)
    return (INNER, OUTER)


def _piece_of(spot: Spot) -> Piece:
    kind = POST if spot.kind == PLATFORM_POST else spot.kind  # the tray's post goes on flights and platforms
    return next(p for p in TRAY if p.kind == kind and (p.side == spot.side or not p.side))


def _where(piece: Piece) -> str:
    if piece.kind == POST:
        return (f"the {'outside' if piece.side == OUTER else 'inside'} stringer, in a gap between treads, or a "
                "platform's side")
    if piece.kind == RAIL_SPLIT:
        return f"the {'outside' if piece.side == OUTER else 'inside'} rail, between two posts"
    if piece.kind == SPLICE:
        return "either stringer, in a gap between two treads (both stringers are cut there)"
    if piece.kind == RADIAL:
        return "a platform, between its ends (it carries a knee brace and a shell clip)"
    return "the inside stringer, at a tread"
