"""Nozzles that run into each other: both rows say so (nozzle.clash), on the shell and on the roof."""

from swauto.nozzle import roof_gui
from swauto.nozzle.clash import note
from swauto.nozzle.gui import blank_row, check_rows
from swauto.tank.roof import RoofSpec
from swauto.tank.spec import Course, TankSpec

SHELL = TankSpec(diameter_in=240.0, diameter_basis="od", courses=[Course(96.0, 0.5), Course(96.0, 0.375)])


def _shell_row(mark: str, size: str, rotation: float, elevation: float, repad: str = "None",
               style: str = "Circular") -> dict:
    values = blank_row()
    values.update(mark=mark, size=size, rotation=str(rotation), elevation=str(elevation), osp="10", isp="2",
                  repad=repad, style=style)
    return values


def _roof_row(mark: str, item: str, size: str, degree: float, radial: float, repad: str = "None") -> dict:
    return {"mark": mark, "service": "", "item": item, "size": size, "degree": str(degree), "radial": str(radial),
            "offset": "", "mode": "Direct OSP", "value": "12", "isp": "", "inside_flange": "None", "repad": repad,
            "pad_od": "", "pad_id": "", "pad_thk": "", "style": "Circular", "blind": False, "gasket": False,
            "gasket_material": "", "gasket_thk": "", "schedule": "STD"}


def test_shell_nozzles_whose_pads_overlap_say_so_on_both_rows():
    # Two 12 in nozzles 10 deg apart on a 20 ft tank: their 27 in pads' middles are 20.9 in apart round the shell.
    checks = check_rows([_shell_row("N1", "12", 30, 48, "Default"), _shell_row("N2", "12", 40, 48, "Default"),
                         _shell_row("N3", "6", 200, 48, "Default")], SHELL)
    assert all(check.ok for check in checks)
    assert checks[0].message.endswith(", runs into N2")
    assert checks[1].message.endswith(", runs into N1")
    assert "runs into" not in checks[2].message


def test_round_zero_degrees_and_down_a_tombstone_pad():
    across = check_rows([_shell_row("N1", "12", 359, 48, "Default"), _shell_row("N2", "12", 1, 48, "Default")], SHELL)
    assert all("runs into" in check.message for check in across)
    # A tombstone pad runs down to the floor, so a small nozzle under it, beside its middle, runs into it.
    tomb = check_rows([_shell_row("N1", "6", 90, 100, "Default", "Tombstone"), _shell_row("N2", "2", 92, 30)], SHELL)
    assert tomb[0].message.endswith(", runs into N2") and tomb[1].message.endswith(", runs into N1")
    round_pad = check_rows([_shell_row("N1", "6", 90, 100, "Default"), _shell_row("N2", "2", 92, 30)], SHELL)
    assert not any("runs into" in check.message for check in round_pad)  # its round pad stops well above


def test_a_roof_nozzle_inside_a_manways_pad_says_so():
    # The 24 in manway's 46 in pad reaches 23 in from its middle; the 2 in nozzle stands 20 in out from it.
    checks = roof_gui.check_rows([_roof_row("M1", "Manway", "24", 90, 150, "Default"),
                                  _roof_row("R1", "Class 150 weld neck", "2", 90, 170),
                                  _roof_row("R2", "Class 150 weld neck", "2", 270, 150)], RoofSpec())
    assert all(check.ok for check in checks)
    assert checks[0].message.endswith(", runs into R1") and checks[1].message.endswith(", runs into M1")
    assert "runs into" not in checks[2].message


def test_the_note_names_every_one():
    assert note([]) == ""
    assert note(["N2"]) == ", runs into N2"
    assert note(["N2", "N5"]) == ", runs into N2 and N5"
    assert note(["N2", "N3", "N5"]) == ", runs into N2, N3 and N5"
