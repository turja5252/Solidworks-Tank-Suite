"""The stringer splices as parts (2026-10-30): a part for each piece of a cut stringer, and one splice plate part per
joint and side, placed on every flight."""

from swauto.stair.parts_build import StairParts, jobs, stair_items
from swauto.stair.split_parts import stringer_joints
from swauto.stair.splitter import SplitSettings
from swauto.stair.stringer import StringerMock


def test_a_split_stringer_is_a_part_for_each_piece_and_each_joint_has_a_plate_on_every_flight():
    splits = SplitSettings(mode="segments", segments=2)
    parts = StairParts(StringerMock(treads=22), 120.0, 0.1875, platforms=2, splits=splits)
    where = parts.where
    cuts = stringer_joints(where, splits, "In")
    assert len(cuts) == 1
    built = {job.label: job for job in jobs(parts)}
    for k in (1, 2, 3):
        for word in ("inner", "outer"):
            assert {f"Flight {k} {word} stringer piece {i} of 2" for i in (1, 2)} <= set(built)
    plate = built[f"Inner stringer splice plate at tread {cuts[0].tread}"]
    assert [p.azimuth_rad for p in plate.placements] == [parts.flight_move(k)[0] for k in range(3)]
    items = stair_items(list(built.values()))
    inner = [item for item in items if item.params["family"] == "Stair stringer inner"]
    # The first flight's pieces have no foot holes; the two flights above share theirs.
    assert [len(item.placements) for item in inner] == [1, 1, 2, 2]


def test_without_the_splitter_each_stringer_is_one_part():
    parts = StairParts(StringerMock(treads=13), 120.0, 0.1875)
    labels = [job.label for job in jobs(parts) if job.family.startswith("Stair stringer ")]
    assert labels == ["Flight 1 inner stringer", "Flight 1 outer stringer"]
    assert not any(job.family == "Stair splice plate" for job in jobs(parts))
