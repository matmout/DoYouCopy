"""PyInstaller entry point: MyWhisper.exe."""

import sys

from mywhisper.app import main

if __name__ == "__main__":
    sys.exit(main())
