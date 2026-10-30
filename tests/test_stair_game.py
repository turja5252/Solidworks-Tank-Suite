"""The stair game's moves, without Tk: drop, move, bin, undo, auto place, and where a pointer snaps."""

import math

from swauto.stair.attachments import CLIP, KNEE, OUTER, POST, RAIL_SPLIT, SPLICE, Rules, Shell, Spot
from swauto.stair.development import develop_both
from swauto.stair.game import TRAY, Game, Piece, slot, spot_xy
from swauto.stair.landings import StairArrangement
from swauto.stair.splitter import SplitSettings
from swauto.stair.stair_sw import stair_places
from swauto.stair.stringer import StringerMock
from swauto.stretchout.model import build_stretchout
from swauto.tank.profile import course_radii_m
from swauto.tank.spec import Course, TankSpec

TANK = TankSpec(diameter_in=600.0, diameter_basis="od", courses=[Course(96.0, 1.0)] + [Course(96.0, 0.5)] * 4)
OD = course_radii_m(TANK, TANK.active_courses()[0])[0] / 0.0254
STAIR = StringerMock(shell_od_in=OD, gap_in=8.0, treads=65, rise_in=480.0 / 65, run_in=10.5)
ARRANGEMENT = StairArrangement(STAIR, turn=math.radians(30), splits=SplitSettings())
SHELL = Shell.of(build_stretchout(TANK))
PIECE = {piece.name: piece for piece in TRAY}


def _game() -> Game:
    return Game(ARRANGEMENT, SHELL, Rules())


def test_the_tray_has_every_piece():
    from swauto.stair.attachments import RADIAL

    # A post goes on a flight or on a platform's side, so platform posts have no piece of their own.
    assert {p.kind for p in TRAY} == {POST, CLIP, KNEE, SPLICE, RAIL_SPLIT, RADIAL}


def test_a_good_drop_pins_and_a_bad_one_says_why():
    game = _game()
    ok, reason = game.drop(PIECE["Post (outside)"], 0, 14)
    assert not ok and "cut" in reason and game.history == []  # stands on the cut after tread 13
    ok, _reason = game.drop(PIECE["Post (outside)"], 0, 12)
    assert ok
    posts = game.plan.of_kind(POST, OUTER)
    assert any(s.tread == 12 and s.pinned for s in posts)


def test_moving_a_splitter_moves_the_cut_and_the_braces_reflow():
    game = _game()
    old = next(s for s in game.plan.of_kind(SPLICE) if s.tread == 26)
    assert game.drop(PIECE["Stringer splitter"], 0, 30, moving=old)[0]
    assert game.plan.cuts == (13, 30, 39, 52)
    knees = [s.tread for s in game.plan.of_kind(KNEE)]
    assert any(14 <= t <= 30 for t in knees) and any(31 <= t <= 39 for t in knees)


def test_the_bin_throws_away_and_undo_brings_it_back():
    game = _game()
    knee = game.plan.of_kind(KNEE)[0]
    game.throw_away(knee)
    assert knee.key() not in [s.key() for s in game.plan.spots]
    assert game.undo()
    assert knee.key() in [s.key() for s in game.plan.spots]
    assert not game.undo()


def test_auto_place_keeps_the_pins_and_brings_back_the_thrown():
    game = _game()
    game.drop(PIECE["Post (outside)"], 0, 12)
    clip = game.plan.of_kind(CLIP)[0]
    game.throw_away(clip)
    game.auto_place()
    assert clip.key() in [s.key() for s in game.plan.spots]
    assert any(s.tread == 12 and s.pinned for s in game.plan.of_kind(POST, OUTER))
    game.start_over()
    assert not any(s.pinned for s in game.plan.spots)


def test_binning_every_cut_leaves_the_stringers_whole():
    game = _game()
    for cut in list(game.plan.cuts):
        game.throw_away(Spot(SPLICE, 0, cut))
    assert game.plan.cuts == ()


def test_the_pointer_snaps_to_the_tread_a_piece_belongs_to():
    where = stair_places(STAIR, STAIR.shell_od_in)
    inner, _outer = develop_both(where.flight)
    for t in (3, 10, 20):
        x, _y = spot_xy(inner, Spot(POST, 0, t))
        assert slot(inner, POST, x + 0.4) == t
        x, _y = spot_xy(inner, Spot(SPLICE, 0, t))
        assert slot(inner, SPLICE, x - 0.4) == t
        x, _y = spot_xy(inner, Spot(CLIP, 0, t))
        assert slot(inner, CLIP, x) == t
    posts = (2, 6, 10)
    x, _y = spot_xy(inner, Spot(RAIL_SPLIT, 0, 6), posts)
    assert slot(inner, RAIL_SPLIT, x, posts) == 6


def test_a_rail_splitter_goes_between_posts_only():
    game = _game()
    posts = [s.tread for s in game.plan.of_kind(POST, OUTER)]
    assert game.try_drop(PIECE["Rail splitter (outside)"], 0, posts[0])[0]
    assert not game.try_drop(PIECE["Rail splitter (outside)"], 0, posts[-1])[0]
    assert Piece("x", POST, OUTER).lanes() == (OUTER,)


class _At:
    def __init__(self, x: float, y: float, delta: int = 0) -> None:
        self.x, self.y, self.delta = x, y, delta


def test_the_game_is_played_with_the_mouse_on_the_stretchout_tab(tk_window):
    import tkinter as tk
    from tkinter import ttk

    from swauto.stretchout.game_gui import TILE_H
    from swauto.stretchout.gui import GAME_VIEW, build_stretchout_tab

    book = ttk.Notebook(tk_window)
    first, page = ttk.Frame(book), ttk.Frame(book)
    book.add(first)
    book.add(page)
    shared = {"spec": TANK, "nozzles": [], "cleanouts": [], "stairway": lambda: ARRANGEMENT}
    build_stretchout_tab(page, tk.StringVar(master=tk_window), shared)
    book.select(page)
    tk_window.update()
    (view,) = [w for w in _widgets(page) if isinstance(w, ttk.Combobox) and GAME_VIEW in w.cget("values")]
    view.set(GAME_VIEW)
    view.event_generate("<<ComboboxSelected>>")
    tk_window.update()
    frame = next(w for w in page.winfo_children() if hasattr(w, "game_events"))
    press, motion, release, wheel = (frame.game_events[k] for k in ("press", "motion", "release", "wheel"))
    game = shared["stair_game"]
    devs = frame.game_state["devs"]

    def tile(name):
        index = [p.name for p in TRAY].index(name)
        return _At(100, 30 + index * TILE_H + 20)

    def at(side, spot, posts=()):
        return _At(*frame.lane_px(side, spot.flight, *spot_xy(devs[side], spot, posts)))

    # A post from the tray onto a cut is red, and nothing changes.
    press(tile("Post (outside)"))
    motion(at(OUTER, Spot(POST, 0, 14, OUTER)))
    assert "cut" in frame.said.get()
    release(at(OUTER, Spot(POST, 0, 14, OUTER)))
    assert not any(s.pinned for s in game.plan.spots)
    # At tread 12 it is green and goes in, pinned.
    press(tile("Post (outside)"))
    release(at(OUTER, Spot(POST, 0, 12, OUTER)))
    assert any(s.tread == 12 and s.pinned for s in game.plan.of_kind(POST, OUTER))
    # A knee brace dragged into the bin is thrown away.
    knee = game.plan.of_kind(KNEE)[0]
    for _ in range(8):  # zoom in on it, the point under the wheel staying put: the whole stair is small here
        before = at("inner", knee)
        wheel(_At(before.x, before.y, delta=120))
        after = at("inner", knee)
        assert abs(after.x - before.x) < 0.5 and abs(after.y - before.y) < 0.5
    top = at("inner", knee)
    _flight, pad = frame.game_state["pads"][knee.key()]  # its shell pad, where the brace runs down to
    low = frame.lane_px("inner", knee.flight, (pad[0] + pad[2]) / 2.0, (pad[1] + pad[3]) / 2.0)
    assert low[1] > top.y  # under the tread
    press(_At(top.x + 0.6 * (low[0] - top.x), top.y + 0.6 * (low[1] - top.y)))  # down the brace, off the clip
    box = frame.game_state["bin"]
    release(_At((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
    assert knee.key() not in [s.key() for s in game.plan.spots]


def _widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _widgets(child)


def test_a_pinned_rail_splitter_keeps_the_other_pieces_within_stock():
    from swauto.stair.attachments import rail_step_in

    game = _game()
    assert game.drop(PIECE["Rail splitter (outside)"], 0, 6)[0]
    posts = [s.tread for s in game.plan.of_kind(POST, OUTER)]
    splits = [s.tread for s in game.plan.of_kind(RAIL_SPLIT, OUTER)]
    assert 6 in splits and len(splits) >= 2
    ends = [posts[0]] + [(t + posts[posts.index(t) + 1]) / 2.0 for t in splits] + [posts[-1]]
    step = rail_step_in(stair_places(STAIR, STAIR.shell_od_in), OUTER)
    assert max(b - a for a, b in zip(ends, ends[1:], strict=False)) * step <= 480.0 + 1e-6


def test_the_foot_clip_and_its_piece_clip_come_and_go_on_their_own():
    from swauto.stair.attachments import GROUND

    game = _game()
    ground = next(s for s in game.plan.of_kind(CLIP) if s.side == GROUND)
    middle = [s.tread for s in game.plan.of_kind(CLIP) if s.side != GROUND and s.tread <= 13]
    game.throw_away(ground)
    assert [s.tread for s in game.plan.of_kind(CLIP) if s.tread <= 13] == middle
    game.undo()
    assert game.drop(PIECE["Inner clip"], 0, 2, moving=ground)[0]
    clips = game.plan.of_kind(CLIP)
    assert any(s.tread == 2 and s.side == GROUND and s.pinned for s in clips)
    assert [s.tread for s in clips if s.side != GROUND and s.tread <= 13] == middle


def test_binned_cuts_stay_out_when_later_pins_move_the_splitter():
    game = _game()
    for cut in list(game.plan.cuts):
        game.throw_away(Spot(SPLICE, 0, cut))
    assert game.drop(PIECE["Post (outside)"], 0, 13)[0]
    assert game.plan.cuts == ()


def test_a_cut_is_red_beside_a_piece_pinned_on_another_flight():
    arrangement = StairArrangement(STAIR, platforms=1, turn=math.radians(30), splits=SplitSettings())
    game = Game(arrangement, SHELL, Rules())
    assert game.drop(PIECE["Post (outside)"], 1, 16)[0]
    ok, reason = game.try_drop(PIECE["Stringer splitter"], 0, 15)
    assert not ok and "Flight 2" in reason


def test_an_inside_post_is_red_while_the_handrail_is_outside():
    ok, reason = _game().try_drop(PIECE["Post (inside)"], 0, 12)
    assert not ok and "Handrail on" in reason
