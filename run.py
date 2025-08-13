#!/usr/bin/env python3
import os
import sys

# Ensure the src/ directory is on sys.path so the package can be imported
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from sof_discord_bot.cli import main

if __name__ == "__main__":
    main()
