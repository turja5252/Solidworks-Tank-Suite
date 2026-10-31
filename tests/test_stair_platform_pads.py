"""A platform's shell pads: each centred on its shell clip, as the knee brace pads are."""

import math

import pytest

from swauto.stair.platform_sw import (
    SHELL_CLIP_THK_IN,
    TAB_FROM_END_IN,
    TAB_THK_IN,
    _channel_ends,
    _pad_point,
    platform_lines,
    shell_pads,
)


def test_each_shell_pad_is_centred_on_its_clip():
    shell_r = 120.0
    lines = platform_lines(phi=0.8, tread_top=120.0, r_a=128.375, r_b=164.5)
    middle = TAB_FROM_END_IN + TAB_THK_IN + SHELL_CLIP_THK_IN / 2.0  # the clip's mid-plane, along the channel
    for end, (_label, phi_q, _y) in zip(_channel_ends(lines), shell_pads(lines, shell_r), strict=True):
        qx, qz = _pad_point(end, shell_r)
        assert math.hypot(qx, qz) == pytest.approx(shell_r)
        assert math.remainder(math.atan2(-qx, qz) - phi_q, 2.0 * math.pi) == pytest.approx(0.0, abs=1e-12)
        along = (qx - end.origin[0]) * end.along[0] + (qz - end.origin[1]) * end.along[1]
        assert along == pytest.approx(middle)  # on the clip's middle, not its face on the tab


@pytest.mark.parametrize("spec", [None, "60 straight", "96 rolled"])
def test_a_shell_clip_stops_at_its_pad_with_neither_edge_in_it(spec):
    # On a straight platform the clip's end, square to the tab's line, is a few degrees off the pad lying flat on the
    # shell; it stops where its nearer edge meets the pad (one corner went 0.03 in into it; found 2026-10-31).
    from swauto.stair.platform_sw import SHELL_PAD_THK_IN, clip_reach
    from swauto.stair.stringer import PlatformSpec

    shapes = {None: None, "60 straight": PlatformSpec(60.0, rolled=False), "96 rolled": PlatformSpec(96.0)}
    shell_r = 120.0
    lines = platform_lines(phi=0.8, tread_top=120.0, r_a=128.375, r_b=164.5, spec=shapes[spec])
    into = []  # how far each edge of each clip's end goes into its pad: under 0 is a gap
    for end in _channel_ends(lines):
        reach = clip_reach(end, shell_r)
        qx, qz = _pad_point(end, shell_r)
        phi_q = math.atan2(-qx, qz)
        normal = (-math.sin(phi_q), math.cos(phi_q))
        face = shell_r + SHELL_PAD_THK_IN  # the pad's outside face, out along its normal
        for c in (TAB_FROM_END_IN + TAB_THK_IN, TAB_FROM_END_IN + TAB_THK_IN + SHELL_CLIP_THK_IN):
            x, _y, z = end.world(c, reach, 0.0)
            into.append(face - (x * normal[0] + z * normal[1]))
    assert max(into) == pytest.approx(0.0, abs=1e-9)  # one edge on the pad, neither in it
    assert min(into) > -0.1  # the other a few hundredths off it
