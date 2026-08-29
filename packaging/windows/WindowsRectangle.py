"""PyInstaller entry point for the Windows Rectangle executable."""

from __future__ import annotations

import sys

from windows_rectangle.__main__ import main


if __name__ == "__main__":
    sys.exit(main())
