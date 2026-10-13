from swauto.tank.spec import Course, TankSpec


def test_etp_roundtrip():
    spec = TankSpec(
        diameter_in=606,
        diameter_basis="centerline",
        courses=[Course(96, 1.0)] + [Course(0, 0)] * 7,
    )
    data = spec.to_etp_dict()
    assert data["DIAMETER_FT"] == "50"
    assert data["SHELL_COURSE_1"] == "96"
    back = TankSpec.from_etp_dict(data)
    assert back.diameter_in == 606
    assert back.courses[0].thickness_in == 1.0


def test_shell_height():
    spec = TankSpec(courses=[Course(96, 1), Course(48, 0.5)] + [Course(0, 0)] * 6)
    assert spec.shell_height_in() == 144
