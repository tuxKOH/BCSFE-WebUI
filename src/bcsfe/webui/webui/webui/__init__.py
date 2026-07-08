from __future__ import annotations

"""WebUI package for BCSFE - Battle Cats Save File Editor."""

import os
import sys

from bcsfe.webui.app import create_app

__all__ = ["create_app", "run_webui"]


def run_webui():
    """Entry point for the WebUI server."""
    app = create_app()
    host = os.environ.get("BCSFE_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("BCSFE_WEB_PORT", "5005"))
    debug = os.environ.get("BCSFE_WEB_DEBUG", "").lower() in ("1", "true", "yes")
    print(f"BCSFE WebUI starting on http://{host}:{port}")
    print("Press Ctrl+C to stop")
    try:
        app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
