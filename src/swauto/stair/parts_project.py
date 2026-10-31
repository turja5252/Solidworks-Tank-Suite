"""The stair built as parts into a project (partify, 2026-10-30): the Stairway tab's Build stair as parts.

``stair_parts`` turns what the tab reads (as Create stair reads it) into the parts build's StairParts and names what
the parts build leaves out for now. ``build_in_project`` builds it into the project's folder as Stair.SLDASM, keeping
every part whose shape has not changed since the last build, records what each file was built from in the project,
and puts Stair.SLDASM into the tank's assembly once, at the tank's origin; the tank's own build leaves it alone.
"""

from __future__ import annotations

from swauto.project.items import Item, Placement
from swauto.stair.heights import RAIL_TOP_IN
from swauto.stair.parts_build import ASSEMBLY, StairParts, build, jobs, stair_items

STAIR_ASSEMBLY = "stair assembly"


def stair_parts(stair, wall_in: float, *, platforms: int, top_platform: bool, posts, ground_in: float, turn: float,
                ccw: bool, top_rail: bool, mid_rail: bool, post_in: float, mid_top: float, grab, rail_splits, braces,
                knees: bool, inner_clips, splits, inner_rail, rail_top: float = RAIL_TOP_IN,
                flight_mid: float | None = None) -> tuple[StairParts, list[str]]:
    """The parts build's StairParts for the stair the tab describes, and what of it the parts build leaves out."""
    if ccw:
        raise ValueError("A stair that climbs counterclockwise is not built as parts yet: Create stair builds it.")
    left = []
    if inner_rail is not None:
        left.append("the inside handrail")
    if any(side != "outer" for side, _pan in rail_splits):
        left.append("the inside handrail's splices")
    parts = StairParts(
        stair, stair.shell_od_in, wall_in, platforms=platforms, posts=tuple(posts), ground_in=ground_in, turn=turn,
        top_platform=top_platform, top_rail=top_rail, mid_rail=mid_rail, post_in=post_in, mid_top=mid_top, grab=grab,
        rail_top=rail_top, flight_mid=flight_mid,
        rail_splits=tuple((side, pan) for side, pan in rail_splits if side == "outer"), braces=tuple(braces),
        knees=knees, inner_clips=tuple(inner_clips), splits=splits,
    )
    return parts, left


def stages(parts: StairParts, built) -> list[tuple[set[str], str]]:
    """The build's steps for the Stairway tab's percent: each part file, built or kept."""
    return [({f"{item.file} built", f"{item.file} kept"}, item.label) for item in stair_items(jobs(parts), built)]


def build_in_project(app, project, parts: StairParts, progress=None) -> tuple[str, str]:
    """Build the stair's parts into ``project``'s folder and Stair.SLDASM, record them in the project and save it,
    and put Stair.SLDASM in the tank's assembly. Returns (heading, note)."""
    from swauto.project.build_sw import _close, sync_assembly
    from swauto.project.project import Project

    _close(app, project.assembly_path, save=True)  # it holds Stair.SLDASM, and Stair.SLDASM the stair's parts
    note, built = build(app, parts, project.folder, ASSEMBLY, progress, project.stair_built)
    project.stair_built = built
    project.save()
    tank = Project(folder=project.folder, name=project.name, spec=project.spec)
    stair = Item(f"{ASSEMBLY}.SLDASM", STAIR_ASSEMBLY, "The stair", {}, (Placement(0.0),))
    sync_assembly(app, tank, [stair])
    return f"{ASSEMBLY}.SLDASM in {project.assembly_path.name}", note
