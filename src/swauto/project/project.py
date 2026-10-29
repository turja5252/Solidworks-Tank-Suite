"""The project file: a tank's inputs, and what each part file was last built from.

``<folder>/<name>.elite.json`` sits beside the part files and ``<name>.SLDASM``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from swauto.cleanout.layout import course_one_gaps
from swauto.cleanout.spec import Cleanout
from swauto.nozzle.roof_spec import RoofNozzle
from swauto.nozzle.spec import Nozzle
from swauto.project.items import Item, ftco_items, nozzle_items, shell_items
from swauto.tank.spec import Course, TankSpec

SUFFIX = ".elite.json"
VERSION = 1

# Item statuses.
NEW = "new"
CHANGED = "changed"
BUILT = "built"
FAILED = "failed"


@dataclass
class Project:
    folder: Path
    name: str
    spec: TankSpec
    cleanouts: list[Cleanout] = field(default_factory=list)
    nozzles: list[Nozzle] = field(default_factory=list)
    # Kept with the project's inputs; they go onto the one-part roof, not into the assembly yet.
    roof_nozzles: list[RoofNozzle] = field(default_factory=list)
    # Part file name -> {"fingerprint", "built_at", "status", "error"}
    built: dict[str, dict] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.folder / f"{self.name}{SUFFIX}"

    @property
    def assembly_path(self) -> Path:
        return self.folder / f"{self.name}.SLDASM"

    def items(self) -> list[Item]:
        """Everything this project builds: the shell plates (holes cut, course 1 open for FTCOs), the
        nozzles and the FTCOs."""
        gaps = course_one_gaps(self.spec, self.cleanouts) if self.cleanouts else []
        built = {name: rec.get("fingerprint", "") for name, rec in self.built.items()}
        return (
            shell_items(self.spec, gaps, built, self.nozzles)
            + nozzle_items(self.spec, self.nozzles, built)
            + ftco_items(self.spec, self.cleanouts, built)
        )

    def status(self, item: Item) -> str:
        record = self.built.get(item.file)
        if record is None or not (self.folder / item.file).exists():
            return NEW
        if record.get("status") == FAILED and record.get("fingerprint") == item.fingerprint:
            return FAILED
        return BUILT if record.get("fingerprint") == item.fingerprint else CHANGED

    def mark(self, item: Item, error: str = "") -> None:
        """Record a build: done, or failed with ``error``. A failed part keeps the old file's fingerprint."""
        when = datetime.now().isoformat(timespec="seconds")
        if error:
            record = dict(self.built.get(item.file, {}))
            record.update(status=FAILED, error=error, tried_at=when, fingerprint=item.fingerprint)
            self.built[item.file] = record
        else:
            self.built[item.file] = {"fingerprint": item.fingerprint, "built_at": when, "status": BUILT}

    def save(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        data = {
            "version": VERSION,
            "name": self.name,
            "tank": asdict(self.spec),
            "cleanouts": [asdict(cleanout) for cleanout in self.cleanouts],
            "nozzles": [asdict(nozzle) for nozzle in self.nozzles],
            "roof_nozzles": [asdict(nozzle) for nozzle in self.roof_nozzles],
            "built": self.built,
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # never leave a half-written project file
        return self.path

    @classmethod
    def load(cls, path: str | Path) -> Project:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        tank = dict(data.get("tank") or {})
        courses = [Course(**dict(course)) for course in tank.pop("courses", [])]
        spec = TankSpec(courses=courses, **tank)
        name = str(data.get("name") or path.name.removesuffix(SUFFIX))
        return cls(
            folder=path.parent,
            name=name,
            spec=spec,
            cleanouts=[Cleanout(**dict(c)) for c in data.get("cleanouts", [])],
            nozzles=[Nozzle(**dict(n)) for n in data.get("nozzles", [])],
            roof_nozzles=[RoofNozzle(**dict(n)) for n in data.get("roof_nozzles", [])],
            built=dict(data.get("built") or {}),
        )


def safe_name(text: str) -> str:
    """A project name that is also a good file name."""
    keep = "".join(ch if ch.isalnum() or ch in " -_.()" else " " for ch in str(text))
    name = " ".join(keep.split()).strip(" .")
    if not name:
        raise ValueError("Enter a project name.")
    return name
