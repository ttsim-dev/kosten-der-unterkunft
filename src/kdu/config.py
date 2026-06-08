"""Project paths."""

from pathlib import Path

SRC = Path(__file__).parent.resolve()
ROOT = SRC.parent.parent
BLD = ROOT / "bld"
DATA = ROOT / "data"
