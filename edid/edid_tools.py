from __future__ import annotations

import sys
from pathlib import Path


_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from edid.cli import main


if __name__ == "__main__":
    argv = sys.argv[1:]
    if getattr(sys, "frozen", False) and not argv:
        argv = ["gui"]
    raise SystemExit(main(argv))
