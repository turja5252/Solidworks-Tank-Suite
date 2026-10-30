"""A 3D look at the stair before SolidWorks: our own small renderer on a Tk canvas, no new packages.

The faces come from ``stair.scene`` (the build's own placing, with what the rules or the Stair game placed).
Each is projected with a simple perspective camera, shaded by how square it faces a light over the viewer's
shoulder, and drawn back to front (the painter's way), which is plenty for a stair seen from outside; the shell's
weld seams are drawn in red on it. The camera sees the build's right-handed frame as SolidWorks does. Drag with
the left button to turn it as SolidWorks turns a part (what is nearest follows the pointer), the wheel zooms,
the right button pans, and the view keeps up with the Stair game.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from swauto.stair.attachments import shell_from
from swauto.stair.scene import Face, Rails, scene

_LIGHT = (0.35, 0.8, 0.5)
_WELD = "#c62828"
HINT = ("Drag to turn it as in SolidWorks, the wheel zooms, the right button pans. Red lines on the shell are its "
        "welds. With Place by the rules ticked on the Stairway tab it shows the posts, rails, clips and knee braces "
        "too, as the Stair game has them.")


def build_view3d(parent, shared: dict, status_var: tk.StringVar) -> ttk.Frame:
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    bar = ttk.Frame(frame, padding=(0, 0, 0, 4))
    bar.grid(row=0, column=0, sticky="ew")
    canvas = tk.Canvas(frame, background="#eef2f6", highlightthickness=1, width=980, height=520)
    canvas.grid(row=1, column=0, sticky="nsew")
    info_var = tk.StringVar(value=HINT)
    ttk.Label(frame, textvariable=info_var, wraplength=960, justify="left").grid(row=2, column=0, sticky="ew")
    shell_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(bar, text="Shell", variable=shell_var, command=lambda: draw()).pack(side="left")
    def reset() -> None:
        state.update(_home(), turned=False)
        state["yaw"] = state.get("facing", 0.0) + _home()["yaw"]
        draw()

    ttk.Button(bar, text="Reset view", command=reset).pack(side="left", padx=(8, 0))

    state: dict = {"faces": [], "center": (0.0, 0.0, 0.0), "size": 100.0, "drag": None, "pan_from": None, **_home()}

    def refresh() -> None:
        source = shared.get("stairway")
        try:
            arrangement = source() if callable(source) else None
        except ValueError as exc:
            info_var.set(f"The Stairway tab needs a correction first: {exc}")
            arrangement = None
        # What the build will place: the Stairway tab's plan by the rules (with the Stair game's moves), or none.
        plan = None
        try:
            source_plan = shared.get("stair_plan")
            plan = source_plan() if callable(source_plan) and arrangement is not None else None
            shell = shell_from(shared.get("spec"), shared.get("nozzles") or (), shared.get("cleanouts") or (),
                               shared.get("anchors"))
            faces = scene(arrangement, plan, shell=shell, rails=rails()) if arrangement is not None else []
        except (ValueError, IndexError) as exc:
            info_var.set(f"The 3D view could not be drawn: {exc}")
            faces = []
        state["faces"] = faces
        if faces:
            stair = [p for f in faces if f.label != "Shell" for p in f.points]
            lo = [min(p[i] for p in stair) for i in range(3)]
            hi = [max(p[i] for p in stair) for i in range(3)]
            state["center"] = tuple((a + b) / 2.0 for a, b in zip(lo, hi, strict=True))
            state["size"] = max(b - a for a, b in zip(lo, hi, strict=True))
            # Face the stair from outside the tank, square to its middle.
            x, _y, z = state["center"]
            state["facing"] = math.pi - math.atan2(-x, z)
            if not state.get("turned"):
                state["yaw"] = state["facing"] + _home()["yaw"]
            status_var.set(f"3D view: {len(faces)} faces.")
        draw()

    def rails() -> Rails:
        """The Stairway tab's top rail, midrail and grab rail boxes; all on without the tab."""
        source = shared.get("stairway_inputs")
        try:
            given = source() if callable(source) else {}
        except (ValueError, tk.TclError):
            given = {}
        return Rails(top=bool(given.get("top_rail", True)), mid=bool(given.get("mid_rail", True)),
                     grab=bool(given.get("grab_rail", True)))

    def draw() -> None:
        canvas.delete("all")
        faces: list[Face] = [f for f in state["faces"] if shell_var.get() or f.label != "Shell"]
        if not faces:
            canvas.create_text(20, 20, anchor="nw", text="Set the stair on the Stairway tab, then come back here.",
                               font=("TkDefaultFont", 12))
            return
        width, height = max(canvas.winfo_width(), 400), max(canvas.winfo_height(), 300)
        drawn = project(faces, state, width, height)
        for _depth, points, color, label, welds in drawn:
            canvas.create_polygon(*points, fill=color, outline=_shade(color, 0.8), width=1, tags=("face", label))
            for weld in welds:
                canvas.create_line(*weld, fill=_WELD, width=2, tags=("face", "Shell weld"))

    def on_press(event) -> None:
        state["drag"] = (event.x, event.y)

    def on_drag(event) -> None:
        if state["drag"] is None:
            return
        x, y = state["drag"]
        state["yaw"] -= (event.x - x) * 0.01  # what is nearest follows the pointer, as SolidWorks turns a part
        state["turned"] = True
        state["pitch"] = max(-1.4, min(1.4, state["pitch"] + (event.y - y) * 0.01))
        state["drag"] = (event.x, event.y)
        draw()

    def on_wheel(event) -> None:
        state["zoom"] = max(0.2, min(20.0, state["zoom"] * (1.2 if event.delta > 0 else 1 / 1.2)))
        draw()

    def on_pan_start(event) -> None:
        state["pan_from"] = (event.x, event.y)

    def on_pan(event) -> None:
        if state["pan_from"] is None:
            return
        x, y = state["pan_from"]
        px, py = state["pan"]
        state["pan"] = (px + event.x - x, py + event.y - y)
        state["pan_from"] = (event.x, event.y)
        draw()

    def on_motion(event) -> None:
        found = canvas.find_overlapping(event.x - 1, event.y - 1, event.x + 1, event.y + 1)
        tags = [t for item in found[-1:] for t in canvas.gettags(item) if t not in ("face", "current")]
        info_var.set(" ".join(tags) if tags else HINT)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", lambda _e: state.update(drag=None))
    canvas.bind("<MouseWheel>", on_wheel)
    canvas.bind("<ButtonPress-3>", on_pan_start)
    canvas.bind("<B3-Motion>", on_pan)
    canvas.bind("<Motion>", on_motion)
    canvas.bind("<Configure>", lambda _e: draw())
    frame.refresh = refresh  # type: ignore[attr-defined]
    frame.view_state = state  # type: ignore[attr-defined]
    return frame


def _home() -> dict:
    return {"yaw": math.radians(-25.0), "pitch": math.radians(15.0), "zoom": 1.0, "pan": (0.0, 0.0)}


def project(faces: list[Face], view: dict, width: int, height: int) -> list[tuple]:
    """Each face seen by the camera, back to front: (depth, canvas points, shaded colour, label, weld lines), the
    weld lines (x0, y0, x1, y1) on the canvas. Faces behind the camera are left out. The camera looks at the
    stair's middle from ``view``'s yaw (round the vertical) and pitch (a positive one looking down)."""
    cx, cy, cz = view["center"]
    size = max(view["size"], 1.0)
    yaw, pitch = view["yaw"], view["pitch"]
    cyaw, syaw, cpit, spit = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    distance = size * 2.2
    focal = min(width, height) * 1.6 * view["zoom"]
    ox, oy = width / 2.0 + view["pan"][0], height / 2.0 + view["pan"][1]
    out = []
    for face in faces:
        cam = []
        for x, y, z in face.points:
            x, y, z = x - cx, y - cy, z - cz
            x, z = x * cyaw - z * syaw, x * syaw + z * cyaw  # turn about the vertical
            y, z = y * cpit + z * spit, z * cpit - y * spit  # tip the top toward the viewer
            cam.append((x, y, z + distance))
        if any(p[2] < 1.0 for p in cam):
            continue
        normal = _normal(cam)
        if normal is None:
            continue
        light = abs(sum(n * l for n, l in zip(normal, _LIGHT, strict=True))) / math.sqrt(sum(v * v for v in _LIGHT))
        # Looking along +z with y up, a right-handed frame has +x on the left.
        points = [v for x, y, z in cam for v in (ox - focal * x / z, oy - focal * y / z)]
        welds = [(points[2 * i], points[2 * i + 1], points[2 * j], points[2 * j + 1]) for i, j in face.welds]
        depth = sum(p[2] for p in cam) / len(cam)
        out.append((depth, points, _shade(face.color, 0.45 + 0.55 * light), face.label, welds))
    out.sort(key=lambda item: -item[0])
    return out


def _normal(points) -> tuple[float, float, float] | None:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points[0], points[1], points[2]
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    length = math.sqrt(sum(v * v for v in n))
    return None if length < 1e-12 else tuple(v / length for v in n)


def _shade(color: str, k: float) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"#{min(255, int(r * k)):02x}{min(255, int(g * k)):02x}{min(255, int(b * k)):02x}"
