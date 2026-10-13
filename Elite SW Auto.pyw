"""Double-click launcher (no Command Prompt window)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from swauto.gui import main

raise SystemExit(main())
