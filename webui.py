#!/usr/bin/env python3
"""Launcher for BCSFE WebUI - run from the project root."""

import sys
from pathlib import Path

# Ensure we use the local source, not the installed package
src_dir = str(Path(__file__).resolve().parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from bcsfe.webui import run_webui

run_webui()
