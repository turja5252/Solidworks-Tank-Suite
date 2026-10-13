"""Tank Properties data model aligned with Elite AutoLISP ETP keys."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_COURSES = 8


@dataclass(frozen=True)
class Course:
    height_in: float
    thickness_in: float

    def active(self) -> bool:
        return self.height_in > 0 and self.thickness_in > 0


@dataclass
class TankSpec:
    """Core shell inputs (slice 1). Units are inches unless noted."""

    diameter_in: float = 606.0  # 50'-6"
    diameter_basis: str = "outside"  # outside | inside | centerline
    courses: list[Course] = field(default_factory=list)
    roof_type: str = "Internal Rafter Roof"
    floor_type: str = "Flat Bottom"

    def __post_init__(self) -> None:
        if not self.courses:
            self.courses = [Course(96.0, 1.0)] + [Course(0.0, 0.0) for _ in range(MAX_COURSES - 1)]
        if len(self.courses) < MAX_COURSES:
            self.courses = list(self.courses) + [Course(0.0, 0.0)] * (MAX_COURSES - len(self.courses))
        self.courses = list(self.courses[:MAX_COURSES])

    def active_courses(self) -> list[Course]:
        return [c for c in self.courses if c.active()]

    def shell_height_in(self) -> float:
        return sum(c.height_in for c in self.active_courses())

    def validate(self) -> None:
        if self.diameter_in <= 0:
            raise ValueError("Diameter must be greater than zero.")
        if self.diameter_basis not in {"outside", "inside", "centerline"}:
            raise ValueError("Diameter basis must be outside, inside, or centerline.")
        active = self.active_courses()
        if not active:
            raise ValueError("Enter at least one course with height and thickness.")
        for i, course in enumerate(active, start=1):
            if course.thickness_in * 2 >= self.diameter_in and self.diameter_basis != "outside":
                # Still allow; geometry helper will raise if inner radius collapses.
                pass
            if course.height_in <= 0 or course.thickness_in <= 0:
                raise ValueError(f"Course {i} needs height and thickness greater than zero.")

    def to_etp_dict(self) -> dict[str, str]:
        """Export keys compatible with Elite *_tank_properties style."""
        dia = float(self.diameter_in)
        feet = int(dia // 12)
        inches = dia - 12 * feet
        data = {
            "TANK_DIAMETER": self.diameter_basis,
            "DIAMETER_FT": str(feet),
            "DIAMETER_IN": f"{inches:g}",
            "TANK_SHELL_HEIGHT_FT": str(int(self.shell_height_in() // 12)),
            "TANK_SHELL_HEIGHT_IN": f"{self.shell_height_in() % 12:g}",
            "ROOF_TYPE": self.roof_type,
            "FLOOR_TYPE": self.floor_type,
        }
        for i in range(MAX_COURSES):
            course = self.courses[i] if i < len(self.courses) else Course(0.0, 0.0)
            data[f"SHELL_COURSE_{i + 1}"] = f"{course.height_in:g}"
            data[f"SHELL_THICKNESS_{i + 1}"] = f"{course.thickness_in:g}"
        return data

    @classmethod
    def from_etp_dict(cls, data: dict) -> TankSpec:
        basis = str(data.get("TANK_DIAMETER", "outside")).strip().lower()
        if basis not in {"outside", "inside", "centerline"}:
            basis = "outside"
        feet = float(data.get("DIAMETER_FT", 0) or 0)
        inches = float(data.get("DIAMETER_IN", 0) or 0)
        diameter = feet * 12.0 + inches
        courses: list[Course] = []
        for i in range(1, MAX_COURSES + 1):
            courses.append(
                Course(
                    height_in=float(data.get(f"SHELL_COURSE_{i}", 0) or 0),
                    thickness_in=float(data.get(f"SHELL_THICKNESS_{i}", 0) or 0),
                )
            )
        return cls(
            diameter_in=diameter or 120.0,
            diameter_basis=basis,
            courses=courses,
            roof_type=str(data.get("ROOF_TYPE", "Internal Rafter Roof")),
            floor_type=str(data.get("FLOOR_TYPE", "Flat Bottom")),
        )

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> TankSpec:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        courses = [Course(**c) for c in raw.get("courses", [])]
        return cls(
            diameter_in=float(raw.get("diameter_in", 120)),
            diameter_basis=str(raw.get("diameter_basis", "outside")),
            courses=courses,
            roof_type=str(raw.get("roof_type", "Internal Rafter Roof")),
            floor_type=str(raw.get("floor_type", "Flat Bottom")),
        )
