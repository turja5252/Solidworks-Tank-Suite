from swauto.tank.spec import Course, TankSpec


def test_etp_roundtrip():
    spec = TankSpec(
        diameter_in=606,
        diameter_basis="centerline",
        stack="od",
        courses=[Course(96, 1.0), Course(96, 0.5)] + [Course(0, 0)] * 6,
    )
    data = spec.to_etp_dict()
    assert data["DIAMETER_FT"] == "50"
    assert data["TANK_DIAMETER"] == "mw"
    assert data["SHELL_STACK"] == "od"
    assert data["SHELL_COURSE_1"] == "96"
    back = TankSpec.from_etp_dict(data)
    assert back.diameter_in == 606
    assert back.diameter_basis == "mw"
    assert back.stack == "od"
    assert back.courses[0].thickness_in == 1.0


def test_shell_height():
    spec = TankSpec(courses=[Course(96, 1), Course(48, 0.5)] + [Course(0, 0)] * 6)
    assert spec.shell_height_in() == 144
