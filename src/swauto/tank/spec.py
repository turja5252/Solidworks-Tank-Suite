"""Tank Properties data model aligned with Elite AutoLISP ETP keys."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MAX_COURSES = 8
DEFAULT_MAX_PLATE_IN = 480.0  # 40' — matches Shell Plate Layout Editor

# Stagger popup indices (same as AutoLISP Base / Half / Custom)
STAGGER_BASE = "0"
STAGGER_HALF = "1"
STAGGER_CUSTOM = "2"

# Mode popup indices
MODE_EQUAL = "0"
MODE_MAX = "1"
MODE_CUSTOM = "2"
MODE_UNKNOWN = "3"


def default_stagger_for_course(course_no: int) -> str:
    """Odd courses Base, even courses Half — matches SPE:default-stagger."""
    return STAGGER_HALF if course_no % 2 == 0 else STAGGER_BASE


@dataclass(frozen=True)
class Course:
    height_in: float
    thickness_in: float
    max_length_in: float = DEFAULT_MAX_PLATE_IN
    mode: str = MODE_EQUAL  # 0 Equal, 1 Max, 2 Custom, 3 Unknown
    stagger: str = STAGGER_BASE  # 0 Base, 1 Half, 2 Custom
    adjust_in: float = 0.0  # developed circumferential shift (inches)

    def active(self) -> bool:
        return self.height_in > 0 and self.thickness_in > 0


@dataclass
class TankSpec:
    """Core shell inputs. Units are inches unless noted."""

    diameter_in: float = 606.0  # 50'-6"
    diameter_basis: str = "outside"  # outside | inside | centerline
    courses: list[Course] = field(default_factory=list)
    roof_type: str = "Internal Rafter Roof"
    floor_type: str = "Flat Bottom"
    # Global unwrap rotate (developed inches) — SHELLPLATES offsetDist
    seam_offset_in: float = 0.0

    def __post_init__(self) -> None:
        if not self.courses:
            self.courses = [
                Course(96.0, 1.0, stagger=default_stagger_for_course(1))
            ] + [
                Course(0.0, 0.0, stagger=default_stagger_for_course(i))
                for i in range(2, MAX_COURSES + 1)
            ]
        padded: list[Course] = []
        for i in range(MAX_COURSES):
            if i < len(self.courses):
                c = self.courses[i]
                # Preserve caller stagger if set; only default when using bare Course(h,t)
                padded.append(c)
            else:
                padded.append(Course(0.0, 0.0, stagger=default_stagger_for_course(i + 1)))
        self.courses = padded

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
            if course.height_in <= 0 or course.thickness_in <= 0:
                raise ValueError(f"Course {i} needs height and thickness greater than zero.")
            if course.mode != MODE_UNKNOWN and course.max_length_in <= 0:
                raise ValueError(f"Course {i} max plate length must be greater than zero.")

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
            "SHELL_STRETCH_OFFSET": f"{self.seam_offset_in:g}",
        }
        for i in range(MAX_COURSES):
            course = self.courses[i] if i < len(self.courses) else Course(0.0, 0.0)
            n = i + 1
            data[f"SHELL_COURSE_{n}"] = f"{course.height_in:g}"
            data[f"SHELL_THICKNESS_{n}"] = f"{course.thickness_in:g}"
            data[f"SHELL_COURSE_{n}_MAX_LENGTH"] = f"{course.max_length_in:g}"
            data[f"SHELL_COURSE_{n}_MODE"] = course.mode
            data[f"SHELL_COURSE_{n}_STAGGER"] = course.stagger
            data[f"SHELL_COURSE_{n}_ADJUST"] = f"{course.adjust_in:g}"
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
            default_stg = default_stagger_for_course(i)
            stagger = str(data.get(f"SHELL_COURSE_{i}_STAGGER", default_stg) or default_stg)
            mode = str(data.get(f"SHELL_COURSE_{i}_MODE", MODE_EQUAL) or MODE_EQUAL)
            max_raw = data.get(f"SHELL_COURSE_{i}_MAX_LENGTH", DEFAULT_MAX_PLATE_IN)
            max_len = float(max_raw or DEFAULT_MAX_PLATE_IN)
            adjust = float(data.get(f"SHELL_COURSE_{i}_ADJUST", 0) or 0)
            courses.append(
                Course(
                    height_in=float(data.get(f"SHELL_COURSE_{i}", 0) or 0),
                    thickness_in=float(data.get(f"SHELL_THICKNESS_{i}", 0) or 0),
                    max_length_in=max_len if max_len > 0 else DEFAULT_MAX_PLATE_IN,
                    mode=mode,
                    stagger=stagger,
                    adjust_in=adjust,
                )
            )
        offset = float(data.get("SHELL_STRETCH_OFFSET", 0) or 0)
        return cls(
            diameter_in=diameter or 120.0,
            diameter_basis=basis,
            courses=courses,
            roof_type=str(data.get("ROOF_TYPE", "Internal Rafter Roof")),
            floor_type=str(data.get("FLOOR_TYPE", "Flat Bottom")),
            seam_offset_in=offset,
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
            seam_offset_in=float(raw.get("seam_offset_in", 0) or 0),
        )
