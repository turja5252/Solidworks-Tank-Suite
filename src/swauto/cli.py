import argparse
import sys

from swauto.cylinder import create_cylinder
from swauto.errors import SolidWorksError, SolidWorksNotRunning, SolidWorksUnavailable
from swauto.report import status_report
from swauto.session import connect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="swauto",
        description="Drive SolidWorks from Python. Run this on the computer where SolidWorks is open.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="Show the SolidWorks version and the active document")
    status.add_argument(
        "--start",
        action="store_true",
        help="Start SolidWorks on this computer if it is not already open",
    )

    cylinder = sub.add_parser("cylinder", help="Create a solid cylinder in a new part")
    cylinder.add_argument("--diameter", type=float, help="Cylinder diameter")
    cylinder.add_argument("--height", type=float, help="Cylinder height")
    cylinder.add_argument(
        "--unit",
        choices=("in", "ft", "mm", "m"),
        default="in",
        help="Unit for diameter and height (default: in)",
    )
    cylinder.add_argument(
        "--start",
        action="store_true",
        help="Start SolidWorks on this computer if it is not already open",
    )

    args = parser.parse_args(argv)
    if args.command == "status":
        return _status(start=args.start)
    if args.command == "cylinder":
        return _cylinder(
            diameter=args.diameter,
            height=args.height,
            unit=args.unit,
            start=args.start,
        )
    return 2


def _status(*, start: bool) -> int:
    try:
        session = connect(start=start)
    except (SolidWorksNotRunning, SolidWorksUnavailable) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(status_report(session.revision(), session.active_document(), started=session.started))
    return 0


def _cylinder(*, diameter: float | None, height: float | None, unit: str, start: bool) -> int:
    try:
        diameter = _ask_length("Diameter", diameter, unit)
        height = _ask_length("Height", height, unit)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        session = connect(start=start)
        result = create_cylinder(session.app, diameter=diameter, height=height, unit=unit)
    except (SolidWorksNotRunning, SolidWorksUnavailable, SolidWorksError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2

    print(f"Created cylinder in {result.title}")
    print(f"Diameter: {result.diameter:g} {result.unit}")
    print(f"Height:   {result.height:g} {result.unit}")
    return 0


def _ask_length(label: str, value: float | None, unit: str) -> float:
    if value is not None:
        if value <= 0:
            raise ValueError(f"{label} must be greater than zero.")
        return value
    raw = input(f"{label} ({unit}): ").strip()
    if not raw:
        raise ValueError(f"{label} is required.")
    number = float(raw)
    if number <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return number
