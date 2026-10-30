"""The Stairway tab's Build stair as parts (2026-10-30): what it hands the parts build, its steps, and the project
keeping what each stair part was built from."""

import pytest

from swauto.project.project import Project
from swauto.stair.parts_build import jobs, stair_items
from swauto.stair.parts_project import stages, stair_parts
from swauto.stair.stair_sw import InnerRail
from swauto.stair.stringer import StringerMock
from swauto.tank.spec import Course, TankSpec

COMMON = {"platforms": 0, "top_platform": False, "posts": (2, 4), "ground_in": -6.0, "turn": 0.5, "top_rail": True,
          "mid_rail": True, "post_in": 4.0, "mid_top": 24.0, "grab": None, "braces": (3,), "knees": True,
          "inner_clips": (3,), "splits": None}


def test_the_tab_becomes_the_parts_builds_stair_and_says_what_it_leaves_out():
    parts, left = stair_parts(StringerMock(treads=8), 0.1875, ccw=False, rail_splits=(("outer", 2), ("inner", 2)),
                              inner_rail=InnerRail(posts=((2,),)), **COMMON)
    assert parts.ground_in == -6.0 and parts.turn == 0.5 and parts.braces == (3,) and parts.inner_clips == (3,)
    assert parts.rail_splits == (("outer", 2),)
    assert left == ["the inside handrail", "the inside handrail's splices"]
    with pytest.raises(ValueError, match="counterclockwise"):
        stair_parts(StringerMock(treads=8), 0.1875, ccw=True, rail_splits=(), inner_rail=None, **COMMON)


def test_each_part_file_is_a_step_whether_it_is_built_or_kept():
    parts, _left = stair_parts(StringerMock(treads=8), 0.1875, ccw=False, rail_splits=(), inner_rail=None, **COMMON)
    steps = stages(parts, {})
    items = stair_items(jobs(parts))
    assert len(steps) == len(items)
    keys, label = steps[0]
    assert keys == {f"{items[0].file} built", f"{items[0].file} kept"} and label == items[0].label


def test_the_project_keeps_what_each_stair_part_was_built_from(tmp_path):
    spec = TankSpec(courses=[Course(96.0, 0.5)])
    project = Project(folder=tmp_path, name="Tank", spec=spec, stair_built={"Stair tread A.SLDPRT": "0123abcd"})
    loaded = Project.load(project.save())
    assert loaded.stair_built == {"Stair tread A.SLDPRT": "0123abcd"}
    assert loaded.built == {}  # the tank's own parts, which the tank's build syncs, are apart
