"""Platform shapes (2026-10-30): any length along the centreline, wider than the stair, rolled sides, and radials
between the ends of a long platform no more than 48 in apart, with a knee brace and a shell clip at least every 96 in
(Chris Samm)."""

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
    assert PlatformSpec(48.0).radial_positions() == ()
    assert PlatformSpec(96.0).radial_positions() == pytest.approx((48.0,))
    assert PlatformSpec(120.0).radial_positions() == pytest.approx((40.0, 80.0))
    assert PlatformSpec(49.0).radial_positions() == pytest.approx((24.5,))
    assert PlatformSpec(96.0, radials=(50.0, 30.0)).radial_positions() == (30.0, 50.0)


def test_a_knee_brace_and_shell_clip_at_least_every_96_in_on_a_radial_as_chris_samm_set_it():
    """Chris Samm, 2026-10-30: "a 96 in platform gets one radial with no support, 120 in one support, 150 in the
    middle radial"; the ends always have one."""
    assert PlatformSpec(96.0).support_positions() == ()
    assert PlatformSpec(120.0).support_positions() == pytest.approx((40.0,))
    assert PlatformSpec(150.0).support_positions() == pytest.approx((75.0,))
    assert PlatformSpec(200.0).support_positions() == pytest.approx((80.0, 120.0))
    assert PlatformSpec(150.0, supports=(37.5, 112.5)).support_positions() == pytest.approx((37.5, 112.5))
    for length in (100.0, 180.0, 250.0, 400.0):
        spec = PlatformSpec(length)
        stops = [0.0, *spec.support_positions(), length]
        assert max(b - a for a, b in zip(stops, stops[1:], strict=False)) <= 96.0


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
    assert [label for label, _a, _s in long_wide.members()] == ["A", "R1", "B"]
    assert [label for label, _a, _s in long_wide.supports()] == ["A", "B"]  # 96 in: no support between
    for angle, along in zip(long_wide.radials, (48.0,), strict=True):
        assert (angle - long_wide.phi_a) * long_wide.r_mid == pytest.approx(along)
    longer = _lines(PlatformSpec(150.0))
    assert [label for label, _a, _s in longer.supports()] == ["A", "R2", "B"]


def test_every_support_gets_a_knee_brace_and_a_shell_clip():
    lines = _lines(PlatformSpec(150.0))
    knees = platform_knees(lines, STAIR.shell_od_in)
    pads = shell_pads(lines, STAIR.shell_od_in)
    assert [k[0] for k in knees] == [p[0] for p in pads] == ["A", "R2", "B"]
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
    arrangement = StairArrangement(StringerMock(treads=21, platform_specs=(PlatformSpec(150.0),)), platforms=1)
    labels = [m.label for m in shell_marks(arrangement)[0]]
    for name in ("A", "R2", "B"):
        assert f"Platform 1 shell clip pad {name}" in labels and f"Platform 1 knee brace pad {name}" in labels
    assert "Platform 1 knee brace pad R1" not in labels  # the radials either side of R2 need none
    faces = scene(arrangement)
    knees = {f.label.rsplit(" ", 1)[-1] for f in faces if "knee brace pad" in f.label}
    assert knees == {"A", "R2", "B"}
    deck = [p for f in faces if f.label == "Platform after tread 11" for p in f.points]
    lines = _lines(PlatformSpec(150.0))
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
    assert [s.tread for s in result.of_kind(RADIAL)] == [48]
    for side in (OUTER, INNER):
        assert [s.tread for s in result.of_kind(PLATFORM_POST, side)] == [4, 52, 92]
    # A pinned radial stays; the rest re-flow so no bay passes the 48 in spacing.
    pinned = plan(arrangement, rules=rules, pins=(Spot(RADIAL, 0, 20),))
    assert [(s.tread, s.pinned) for s in pinned.of_kind(RADIAL)] == [(20, True), (58, False)]
    assert applied(arrangement, pinned).stair.platform(0).radials == (20.0, 58.0)
    # Red: a post on a radial's end, a radial on top of a pinned one, one past the ends.
    assert not check(arrangement, result, Spot(PLATFORM_POST, 0, 49, OUTER), rules=rules)[0]
    assert not check(arrangement, result, Spot(PLATFORM_POST, 0, 56, OUTER), rules=rules)[0]  # by the one at 52
    assert check(arrangement, result, Spot(PLATFORM_POST, 0, 66, OUTER), rules=rules)[0]
    assert not check(arrangement, pinned, Spot(RADIAL, 0, 23), rules=rules)[0]
    assert not check(arrangement, result, Spot(RADIAL, 0, 3), rules=rules)[0]


def test_a_held_radial_slides_off_a_weld_no_more_than_6_in_and_keeps_the_bays_within_the_spacing():
    from swauto.stair.attachments import RADIAL, Rules, Shell, _Context, _radial_marks, plan
    from swauto.stretchout.model import Seam, x_of_angle

    arrangement = StairArrangement(StringerMock(treads=21, platform_specs=(PlatformSpec(150.0),)), platforms=1)
    girth = 2.0 * math.pi * STAIR.shell_od_in
    ctx = _Context(arrangement, stair_places(arrangement.stair, STAIR.shell_od_in, 1), None, Rules())
    knee = next(m for m in _radial_marks(ctx, 0, 75.0) if "knee" in m.label)  # the middle radial: the held one
    x = x_of_angle(arrangement.world(knee.center[0]), girth) % girth
    shell = Shell(girth, 400.0, (Seam(x, 0.0, x, 400.0, "the test seam"),))
    radials = [s.tread for s in plan(arrangement, shell).of_kind(RADIAL)]
    assert radials[1] != 75 and abs(radials[1] - 75) <= 6
    assert radials[0] == round(37.5) and radials[2] == round(112.5)  # nothing on the shell: they stay put
    bounds = [0, *radials, 150]
    assert max(b - a for a, b in zip(bounds, bounds[1:], strict=False)) <= 48.0


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


# ---------------------------------------------------------------------------------------- the build's side


def test_posts_between_the_ends_stand_beside_the_radials_or_where_the_plan_put_them():
    from swauto.stair.attachments import PLATFORM_POST, OUTER, Spot, applied, plan

    assert PlatformSpec(96.0).post_positions() == pytest.approx((52.0,))
    assert PlatformSpec(96.0, posts=(50.0, 20.0)).post_positions() == (20.0, 50.0)
    arrangement = _long()
    result = plan(arrangement, pins=(Spot(PLATFORM_POST, 0, 30, OUTER),))
    shape = applied(arrangement, result).stair.platform(0)
    assert shape.posts == (30.0, 52.0)  # the end ones (4 in from the ends) are the build's own


def test_a_post_frame_sits_on_the_outer_side_straight_or_rolled():
    from swauto.stair.post_sw import platform_post_frame

    rolled = _lines(PlatformSpec(96.0))
    angle, web_r, heel_t = platform_post_frame(rolled, "A", None, 4.0)
    assert (angle - rolled.phi_a) * rolled.r_out == pytest.approx(4.0) and web_r == rolled.r_out and heel_t == 0.0
    assert platform_post_frame(rolled, "M1", 1.0, 4.0) == (1.0, rolled.r_out, 0.0)
    straight = _lines(PlatformSpec())
    mid, chord_r, heel_a = platform_post_frame(straight, "A", None, 4.0)
    _mid, _chord, heel_b = platform_post_frame(straight, "B", None, 4.0)
    assert heel_a == pytest.approx(-heel_b) and heel_a < 0
    # A post between the ends lands on the straight side where its radial line crosses it.
    _m, _c, heel = platform_post_frame(straight, "M1", mid + 0.05, 4.0)
    assert heel == pytest.approx(chord_r * math.tan(0.05))


def test_the_build_stages_count_every_radial_and_post():
    from swauto.stair.stringer_gui import _stair_stage_plan

    labels = {key for keys, _label in _stair_stage_plan(21, platforms=1, posts=(2,), shapes=(PlatformSpec(150.0),))
              for key in keys}
    for name in ("ShellR2 clip placed", "KneeR2 placed", "PostM1 placed", "PostM3 holes cut"):
        assert f"ElitePlatform11{name}" in labels
    assert "ElitePlatform11KneeR1 placed" not in labels  # only the held radial has a knee brace
    plain = {key for keys, _label in _stair_stage_plan(21, platforms=1, posts=(2,)) for key in keys}
    assert "ElitePlatform11ShellR1 clip placed" not in plain


def test_the_cope_outline_is_the_channel_section_grown_a_sixteenth_all_round():
    from swauto.stair.platform_sw import COPE_GAP_IN, _grown_section

    loop = _grown_section(COPE_GAP_IN)
    # Closed: every piece starts where the one before it ends.
    for shape, following in zip(loop, loop[1:] + loop[:1], strict=True):
        assert shape[-1] == pytest.approx(following[1], abs=1e-9)
    points = [p for shape in loop for p in shape[1:]]
    ts, ys = [p[0] for p in points], [p[1] for p in points]
    assert min(ts) == pytest.approx(-COPE_GAP_IN) and max(ts) == pytest.approx(1.584 + COPE_GAP_IN)
    assert min(ys) == pytest.approx(-COPE_GAP_IN) and max(ys) == pytest.approx(4.0 + COPE_GAP_IN)
    # The web's face stands off by the gap, and the 1:6 inside face of each flange moves out square to itself.
    assert any(shape[0] == "line" and shape[1][0] == pytest.approx(0.184 + COPE_GAP_IN)
               and shape[2][0] == pytest.approx(0.184 + COPE_GAP_IN) for shape in loop)
    sloped = [shape for shape in loop if shape[0] == "line" and abs(shape[1][1] - shape[2][1]) > 0.1
              and abs(shape[1][0] - shape[2][0]) > 0.5]
    assert len(sloped) == 2
    for _kind, a, b in sloped:
        assert abs((b[1] - a[1]) / (b[0] - a[0])) == pytest.approx(1.0 / 6.0, rel=1e-3)  # as the library has it
    (_kind, a, b), = [s for s in sloped if s[1][1] < 2.0]
    # The library's own inside face runs through (0.4180, 0.3737); grown, it is a sixteenth off it, square to it.
    nx, ny = 1.0 / math.sqrt(37.0), 6.0 / math.sqrt(37.0)
    assert (a[0] - 0.4180) * nx + (a[1] - 0.3737) * ny == pytest.approx(COPE_GAP_IN, abs=1e-3) or \
        (b[0] - 0.4180) * nx + (b[1] - 0.3737) * ny == pytest.approx(COPE_GAP_IN, abs=1e-3)


# ---------------------------------------------------------------------------------------------- C6 platforms


def test_a_platform_channel_is_c4_or_c6_typed_one_per_platform():
    from swauto.stair.stringer_gui import platform_channels

    assert PlatformSpec().channel == "C4"
    PlatformSpec(channel="C6").validate()
    with pytest.raises(ValueError, match="C4 or C6"):
        PlatformSpec(channel="C8").validate()
    assert platform_channels("c4, 6", "Mid platform channels") == ["C4", "C6"]
    with pytest.raises(ValueError, match="C4 or C6"):
        platform_channels("C5", "Mid platform channels")


def test_a_c6_platform_keeps_its_top_and_drops_its_bottom_and_knee_braces_2_in():
    c4, c6 = _lines(PlatformSpec(150.0)), _lines(PlatformSpec(150.0, channel="C6"))
    assert (c4.section.name, c6.section.name) == ("C4x5.4", "C6x8.2")
    assert c6.top == c4.top  # flush with the treads under the grating
    assert c6.top - c6.section.depth_in == pytest.approx(c4.top - c4.section.depth_in - 2.0)
    # The hanger hangs from the channel's bottom, so each knee brace and its pad sit 2 in lower.
    for (_l4, _f4, k4, _b4), (_l6, _f6, k6, _b6) in zip(platform_knees(c4, STAIR.shell_od_in),
                                                        platform_knees(c6, STAIR.shell_od_in), strict=True):
        assert k6.top == pytest.approx((k4.top[0], k4.top[1] - 2.0))
        assert k6.bottom == pytest.approx((k4.bottom[0], k4.bottom[1] - 2.0))
    # The shell clips' pads stay on the channel's middle and reach 1 in past its top and bottom: 8 in on a C6.
    for (_l4, a4, y4), (_l6, a6, y6) in zip(shell_pads(c4, STAIR.shell_od_in), shell_pads(c6, STAIR.shell_od_in),
                                            strict=True):
        assert a6 == pytest.approx(a4) and y6 == pytest.approx(y4 - 1.0)
    assert (c4.section.pad_tall_in, c6.section.pad_tall_in) == (6.0, 8.0)
    arrangement = StairArrangement(StringerMock(treads=21, platform_specs=(PlatformSpec(150.0, channel="C6"),)),
                                   platforms=1)
    pads = [m for m in shell_marks(arrangement)[0] if "shell clip pad" in m.label]
    assert pads and all(m.size[1] == 8.0 for m in pads)


def test_a_c6_cope_is_the_c6_library_section_grown_a_sixteenth_all_round():
    from swauto.stair.platform_sw import C6, COPE_GAP_IN, _grown_section

    loop = _grown_section(COPE_GAP_IN, C6)
    for shape, following in zip(loop, loop[1:] + loop[:1], strict=True):
        assert shape[-1] == pytest.approx(following[1], abs=1e-9)
    points = [p for shape in loop for p in shape[1:]]
    ts, ys = [p[0] for p in points], [p[1] for p in points]
    assert min(ts) == pytest.approx(-COPE_GAP_IN) and max(ts) == pytest.approx(1.920 + COPE_GAP_IN)
    assert min(ys) == pytest.approx(-COPE_GAP_IN) and max(ys) == pytest.approx(6.0 + COPE_GAP_IN)
    assert any(shape[0] == "line" and shape[1][0] == pytest.approx(0.200 + COPE_GAP_IN)
               and shape[2][0] == pytest.approx(0.200 + COPE_GAP_IN) for shape in loop)
    # The library's C6x8.2 inside face runs through (0.4507, 0.4446) at 1:6; grown, it is a sixteenth off it.
    (_kind, a, b), = [shape for shape in loop if shape[0] == "line" and abs(shape[1][0] - shape[2][0]) > 0.5
                      and abs(shape[1][1] - shape[2][1]) > 0.1 and shape[1][1] < 3.0]
    nx, ny = 1.0 / math.sqrt(37.0), 6.0 / math.sqrt(37.0)
    assert (b[1] - a[1]) / (b[0] - a[0]) == pytest.approx(-1.0 / 6.0, rel=1e-3)
    assert (a[0] - 0.4507) * nx + (a[1] - 0.4446) * ny == pytest.approx(COPE_GAP_IN, abs=1e-3)
