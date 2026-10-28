"""Shared tank project — one coherent model every module reads and writes.

Tank Properties owns the shell ``TankSpec``. Floor, roof, stair, and later
openings/access modules derive host geometry from that shell, keep their own
module-local params, and attach to the same live SolidWorks document when one
exists. Listeners let the GUI tabs stay in sync without copying a loose dict.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from swauto.tank.floor import FloorSpec
from swauto.tank.profile import course_radii_m
from swauto.tank.roof import RoofSpec, roof_from_tank
from swauto.tank.spec import TankSpec

_INCH = 0.0254

Listener = Callable[["TankProject", str], None]


@dataclass
class StairParams:
    """Stair / stringer params that are not implied by the shell OD."""

    gap_in: float = 8.0
    treads: int = 8
    rise_in: float = 7.5
    run_in: float = 10.5
    plate_width_in: float = 9.0
    platforms: int = 0
    top_platform: bool = False


@dataclass
class TankProject:
    """Coherent tank: shell hub + module specs + optional live SolidWorks part."""

    shell: TankSpec = field(default_factory=TankSpec)
    floor: FloorSpec = field(default_factory=FloorSpec)
    roof: RoofSpec = field(default_factory=RoofSpec)
    stair: StairParams = field(default_factory=StairParams)
    # When True, derived dims (floor OD, roof radii/height, stair OD) track the shell.
    follow_shell: bool = True
    live: Any = field(default=None, repr=False, compare=False)
    _listeners: list[Listener] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.follow_shell:
            self.sync_derived(notify=False)

    # --- subscribe ---------------------------------------------------------

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener(project, reason)`` on changes. Returns an unsubscribe."""
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _unsubscribe

    def _notify(self, reason: str) -> None:
        for listener in list(self._listeners):
            listener(self, reason)

    # --- shell hub ---------------------------------------------------------

    def set_shell(self, shell: TankSpec, *, reason: str = "shell") -> None:
        self.shell = shell
        if self.follow_shell:
            self.sync_derived(notify=False)
        self._notify(reason)

    def set_live(self, live: Any, *, reason: str = "live") -> None:
        self.live = live
        self._notify(reason)

    def set_follow_shell(self, follow: bool) -> None:
        self.follow_shell = follow
        if follow:
            self.sync_derived(notify=False)
        self._notify("follow")

    # --- derived geometry from shell ---------------------------------------

    def course1_od_in(self) -> float:
        """Outside diameter of course 1 (inches)."""
        self.shell.validate()
        courses = self.shell.active_courses()
        outer_m, _inner_m = course_radii_m(self.shell, courses[0])
        return (outer_m * 2.0) / _INCH

    def course1_od_radius_in(self) -> float:
        return self.course1_od_in() / 2.0

    def top_course_radii_in(self) -> tuple[float, float]:
        """(inside_radius_in, outside_radius_in) of the top active course."""
        self.shell.validate()
        courses = self.shell.active_courses()
        outer_m, inner_m = course_radii_m(self.shell, courses[-1])
        return inner_m / _INCH, outer_m / _INCH

    def sync_derived(self, *, notify: bool = True) -> None:
        """Push shell-implied dims into floor, roof, and stair module specs."""
        try:
            od = self.course1_od_in()
        except ValueError:
            return
        floor = self.floor
        self.floor = FloorSpec(
            diameter_in=od,
            thickness_in=floor.thickness_in,
            plate_width_in=floor.plate_width_in,
            max_length_in=floor.max_length_in,
            lap_in=floor.lap_in,
            projection_in=floor.projection_in,
            center=floor.center,
            end_long_ft=floor.end_long_ft,
            center_shift_in=floor.center_shift_in,
            soldier_courses=floor.soldier_courses,
            soldier_edge_in=floor.soldier_edge_in,
            rotation_deg=floor.rotation_deg,
        )
        try:
            derived = roof_from_tank(
                self.shell,
                slope_in_per_ft=self.roof.slope_in_per_ft,
                thickness_in=self.roof.thickness_in,
            )
        except ValueError:
            derived = None
        if derived is not None:
            roof = self.roof
            self.roof = RoofSpec(
                inside_radius_in=derived.inside_radius_in,
                outside_radius_in=derived.outside_radius_in,
                shell_height_in=derived.shell_height_in,
                slope_in_per_ft=roof.slope_in_per_ft,
                thickness_in=roof.thickness_in,
                ring=roof.ring,
                ring_top_offset_in=roof.ring_top_offset_in,
                landing_inset_in=roof.landing_inset_in,
                bar_width_in=roof.bar_width_in,
                bar_height_in=roof.bar_height_in,
                angle_horizontal_in=roof.angle_horizontal_in,
                angle_vertical_in=roof.angle_vertical_in,
                angle_thickness_in=roof.angle_thickness_in,
                ignore_pie=roof.ignore_pie,
                plate_width_in=roof.plate_width_in,
                plate_length_in=roof.plate_length_in,
                plate_lap_in=roof.plate_lap_in,
            )
        stair = self.stair
        self.stair = StairParams(
            gap_in=stair.gap_in,
            treads=stair.treads,
            rise_in=stair.rise_in,
            run_in=stair.run_in,
            plate_width_in=stair.plate_width_in,
            platforms=stair.platforms,
            top_platform=stair.top_platform,
        )
        # Stair OD is read via course1_od_radius_in(); StairParams stays module-local.
        if notify:
            self._notify("sync")

    def set_floor(self, floor: FloorSpec, *, reason: str = "floor") -> None:
        self.floor = floor
        self._notify(reason)

    def set_roof(self, roof: RoofSpec, *, reason: str = "roof") -> None:
        self.roof = roof
        self._notify(reason)

    def set_stair(self, stair: StairParams, *, reason: str = "stair") -> None:
        self.stair = stair
        self._notify(reason)

    def model(self) -> Any:
        """SolidWorks model doc from the live shell, if any."""
        live = self.live
        return getattr(live, "model", None) if live is not None else None

    # --- persistence -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "follow_shell": self.follow_shell,
            "shell": asdict(self.shell),
            "floor": asdict(self.floor),
            "roof": asdict(self.roof),
            "stair": asdict(self.stair),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TankProject:
        from swauto.tank.spec import Course

        shell_raw = dict(raw.get("shell") or {})
        courses = [Course(**dict(c)) for c in shell_raw.get("courses") or []]
        shell_kwargs: dict[str, Any] = {
            "diameter_in": float(shell_raw.get("diameter_in", 606)),
            "diameter_basis": str(shell_raw.get("diameter_basis", "mw")),
            "stack": str(shell_raw.get("stack", "mw")),
            "roof_type": str(shell_raw.get("roof_type", "Internal Rafter Roof")),
            "floor_type": str(shell_raw.get("floor_type", "Flat Bottom")),
            "seam_offset_in": float(shell_raw.get("seam_offset_in", 0) or 0),
        }
        if courses:
            shell_kwargs["courses"] = courses
        shell = TankSpec(**shell_kwargs)
        floor_raw = raw.get("floor")
        roof_raw = raw.get("roof")
        stair_raw = raw.get("stair")
        project = cls(
            shell=shell,
            floor=FloorSpec(**dict(floor_raw)) if floor_raw else FloorSpec(),
            roof=RoofSpec(**dict(roof_raw)) if roof_raw else RoofSpec(),
            stair=StairParams(**dict(stair_raw)) if stair_raw else StairParams(),
            follow_shell=bool(raw.get("follow_shell", True)),
        )
        return project

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> TankProject:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def snapshot(self) -> TankProject:
        """Deep copy of specs without listeners or live COM handles."""
        return TankProject.from_dict(deepcopy(self.to_dict()))

    # --- dict-shaped bridge for existing holder/shared call sites ----------

    def get(self, key: str, default: Any = None) -> Any:
        if key == "spec":
            return self.shell
        if key == "live":
            return self.live
        if key == "project":
            return self
        return default

    def __getitem__(self, key: str) -> Any:
        if key == "spec":
            return self.shell
        if key == "live":
            return self.live
        if key == "project":
            return self
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "spec":
            self.set_shell(value, reason="shell")
            return
        if key == "live":
            self.set_live(value, reason="live")
            return
        raise KeyError(key)
