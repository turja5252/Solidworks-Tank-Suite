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
