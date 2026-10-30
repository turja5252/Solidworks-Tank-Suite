"""Platform shapes (2026-10-30): any length along the centreline, wider than the stair, rolled sides, and radials
between the ends of a long platform, each with a knee brace and a shell clip."""

import math

import pytest

from swauto.stair.development import flight_turns, platform_centreline
from swauto.stair.landings import StairArrangement, platform_problems, shell_marks
from swauto.stair.platform_sw import _channel_ends, platform_knees, platform_lines, shell_pads
from swauto.stair.scene import scene
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import CLEAR_IN, THICKNESS_IN, PlatformSpec, StringerMock

STAIR = StringerMock(treads=21)


def _lines(spec: PlatformSpec):
    where = stair_places(STAIR, STAIR.shell_od_in, 1)
    last = where.places[where.per_flight - 1]
    r_a = where.layout.inner_face_in
    return platform_lines(phi=last.phi, tread_top=last.y1, r_a=r_a, r_b=r_a + CLEAR_IN, spec=spec)


def test_a_long_platform_gets_radials_no_more_than_the_spacing_apart():
    assert PlatformSpec().radial_positions() == ()
    assert PlatformSpec(40.0).radial_positions() == ()
    assert PlatformSpec(96.0).radial_positions() == pytest.approx((32.0, 64.0))
    assert PlatformSpec(120.0).radial_positions() == pytest.approx((40.0, 80.0))
    assert PlatformSpec(41.0).radial_positions() == pytest.approx((20.5,))
    assert PlatformSpec(96.0, radials=(50.0, 30.0)).radial_positions() == (30.0, 50.0)


def test_sides_roll_on_their_own_over_36_in_unless_chosen():
    assert not PlatformSpec().is_rolled and PlatformSpec(48.0).is_rolled
    assert not PlatformSpec(48.0, rolled=False).is_rolled and PlatformSpec(rolled=True).is_rolled
    with pytest.raises(ValueError, match="never narrower"):
        PlatformSpec(width_in=30.0).validate()


def test_a_longer_platform_turns_the_flights_above_it_round_by_its_extra_length():
    flight = StringerMock(treads=11)
    plain = flight_turns(flight, 2)
    longer = flight_turns(StringerMock(treads=11, platform_specs=(PlatformSpec(96.0),)), 2)
    inner_face = flight.shell_od_in + flight.gap_in + THICKNESS_IN
    extra = 60.0 / platform_centreline(inner_face, PlatformSpec())
    assert longer[1] - plain[1] == pytest.approx(extra)
    assert longer[2] - plain[2] == pytest.approx(extra)  # the second platform is the stair's own


def test_the_lines_follow_the_shape():
    plain, long_wide = _lines(PlatformSpec()), _lines(PlatformSpec(96.0, 48.0))
    assert (long_wide.phi_b - long_wide.phi_a) * long_wide.r_mid == pytest.approx(96.0)
    assert long_wide.r_b - plain.r_b == pytest.approx(12.0) and long_wide.r_a == plain.r_a
    assert long_wide.stringer_b == pytest.approx(plain.r_b)  # the stair stops short of the wider platform
    assert long_wide.rolled and not plain.rolled
    assert [label for label, _a, _s in long_wide.supports()] == ["A", "R1", "R2", "B"]
    for angle, along in zip(long_wide.radials, (32.0, 64.0), strict=True):
        assert (angle - long_wide.phi_a) * long_wide.r_mid == pytest.approx(along)


def test_every_support_gets_a_knee_brace_and_a_shell_clip():
    lines = _lines(PlatformSpec(96.0))
    knees = platform_knees(lines, STAIR.shell_od_in)
    pads = shell_pads(lines, STAIR.shell_od_in)
    assert [k[0] for k in knees] == [p[0] for p in pads] == ["A", "R1", "R2", "B"]
    # A rolled outer side: the knees hang under the arc, all the same distance out.
    assert len({round(back, 6) for *_rest, back in knees}) == 1
    # On a rolled inner side each clip starts on the arc, looking into the platform along it.
    for end, (_label, angle, side) in zip(_channel_ends(lines), lines.supports(), strict=True):
        assert math.hypot(*end.origin) == pytest.approx(lines.r_in)
        tangent = (-side * math.cos(angle), -side * math.sin(angle))
        assert end.along == pytest.approx(tangent)
    # The stair's own platform keeps its two, at the ends of its straight sides.
    plain = _lines(PlatformSpec())
    assert [k[0] for k in platform_knees(plain, STAIR.shell_od_in)] == ["A", "B"]


def test_straight_sides_that_would_bow_into_the_shell_are_refused():
    def problems(spec):
        return platform_problems(StairArrangement(StringerMock(treads=21, platform_specs=(spec,)), platforms=1))

    assert problems(PlatformSpec()) == []
    assert problems(PlatformSpec(110.0)) == []  # rolled by default
    assert "roll them" in problems(PlatformSpec(110.0, rolled=False))[0]


def test_the_shell_and_the_3d_view_get_every_support():
    arrangement = StairArrangement(StringerMock(treads=21, platform_specs=(PlatformSpec(96.0),)), platforms=1)
    labels = [m.label for m in shell_marks(arrangement)[0]]
    for name in ("A", "R1", "R2", "B"):
        assert f"Platform 1 shell clip pad {name}" in labels and f"Platform 1 knee brace pad {name}" in labels
    faces = scene(arrangement)
    knees = {f.label.rsplit(" ", 1)[-1] for f in faces if "knee brace pad" in f.label}
    assert knees == {"A", "R1", "R2", "B"}
    deck = [p for f in faces if f.label == "Platform after tread 11" for p in f.points]
    lines = _lines(PlatformSpec(96.0))
    radii = [math.hypot(p[0], p[2]) for p in deck]
    assert min(radii) == pytest.approx(lines.r_in) and max(radii) == pytest.approx(lines.r_out)


# ---------------------------------------------------------------------------------- the rules and the game


def _long():
    from swauto.stair.landings import StairArrangement

    return StairArrangement(StringerMock(treads=21, platform_specs=(PlatformSpec(96.0),)), platforms=1)


def test_the_rules_put_radials_and_posts_on_a_long_platform_and_hand_them_on():
    from swauto.stair.attachments import INNER, OUTER, PLATFORM_POST, RADIAL, Rules, Spot, applied, check, plan

    arrangement = _long()
    rules = Rules(sides=(OUTER, INNER))
    result = plan(arrangement, rules=rules)
    assert [s.tread for s in result.of_kind(RADIAL)] == [32, 64]
    for side in (OUTER, INNER):
        assert [s.tread for s in result.of_kind(PLATFORM_POST, side)] == [4, 36, 68, 92]
    # A pinned radial stays; the rest re-flow so no bay passes the 40 in spacing.
    pinned = plan(arrangement, rules=rules, pins=(Spot(RADIAL, 0, 20),))
    assert [(s.tread, s.pinned) for s in pinned.of_kind(RADIAL)] == [(20, True), (58, False)]
    assert applied(arrangement, pinned).stair.platform(0).radials == (20.0, 58.0)
    # Red: a post on a radial's end, a radial on top of a pinned one, one past the ends.
    assert not check(arrangement, result, Spot(PLATFORM_POST, 0, 33, OUTER), rules=rules)[0]
    assert not check(arrangement, result, Spot(PLATFORM_POST, 0, 40, OUTER), rules=rules)[0]  # by the one at 36
    assert check(arrangement, result, Spot(PLATFORM_POST, 0, 48, OUTER), rules=rules)[0]
    assert not check(arrangement, pinned, Spot(RADIAL, 0, 23), rules=rules)[0]
    assert not check(arrangement, result, Spot(RADIAL, 0, 3), rules=rules)[0]


def test_a_radial_slides_off_a_weld_and_keeps_the_bays_within_the_spacing():
    from swauto.stair.attachments import RADIAL, Rules, Shell, _Context, _radial_marks, plan
    from swauto.stretchout.model import Seam, x_of_angle

    arrangement = _long()
    girth = 2.0 * math.pi * STAIR.shell_od_in
    ctx = _Context(arrangement, stair_places(arrangement.stair, STAIR.shell_od_in, 1), None, Rules())
    knee = next(m for m in _radial_marks(ctx, 0, 32.0) if "knee" in m.label)
    x = x_of_angle(arrangement.world(knee.center[0]), girth) % girth
    shell = Shell(girth, 400.0, (Seam(x, 0.0, x, 400.0, "the test seam"),))
    radials = [s.tread for s in plan(arrangement, shell).of_kind(RADIAL)]
    assert radials[0] != 32 and abs(radials[0] - 32) <= 20 and radials[1] == 64
    bounds = [0, *radials, 96]
    assert max(b - a for a, b in zip(bounds, bounds[1:], strict=False)) <= 40.0


def test_the_game_drops_a_radial_on_a_platform_and_keeps_one_the_rules_need(tk_window):
    import tkinter as tk
    from tkinter import ttk

    from swauto.stair.attachments import RADIAL, Spot
    from swauto.stair.game import TRAY
    from swauto.stretchout.game_gui import TILE_H
    from swauto.stretchout.gui import GAME_VIEW, build_stretchout_tab

    class At:
        def __init__(self, x, y, delta=0):
            self.x, self.y, self.delta = x, y, delta

    book = ttk.Notebook(tk_window)
    page = ttk.Frame(book)
    book.add(page)
    shared = {"stairway": _long}
    build_stretchout_tab(page, tk.StringVar(master=tk_window), shared)
    book.select(page)
    tk_window.update()
    (view,) = [w for w in _all(page) if isinstance(w, ttk.Combobox) and GAME_VIEW in w.cget("values")]
    view.set(GAME_VIEW)
    view.event_generate("<<ComboboxSelected>>")
    tk_window.update()
    frame = next(w for w in page.winfo_children() if hasattr(w, "game_events"))
    press, release = frame.game_events["press"], frame.game_events["release"]
    game = shared["stair_game"]
    index = [p.name for p in TRAY].index("Platform radial")
    press(At(100, 30 + index * TILE_H + 20))
    release(At(*frame.platform_px("outer", Spot(RADIAL, 0, 20))))
    assert [(s.tread, s.pinned) for s in game.plan.of_kind(RADIAL)] == [(20, True), (58, False)]
    # The rules' radial at 58 has to stay: thrown in the bin, it comes straight back, and the game says so.
    press(At(*frame.platform_px("inner", Spot(RADIAL, 0, 58))))  # inside, where no post stands beside it
    box = frame.game_state["bin"]
    release(At((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
    assert [s.tread for s in game.plan.of_kind(RADIAL)] == [20, 58]
    assert "has to stay" in frame.said.get()


def _all(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _all(child)
