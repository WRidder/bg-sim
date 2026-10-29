"""Serve the bg-sim backend with a chosen web app directory (used by render-models.mjs).

``bgsim`` always serves ``<repo>/web/dist``; the settings dataclass can point elsewhere,
so this launcher swaps in ``BGSIM_WEB_DIST`` without touching the real ``web/dist``.
With ``BGSIM_CATALOG_JSON`` the fake worker serves that (real, previously captured)
catalog instead of the minimal fixture, so every block draws with its real ports.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import uvicorn

from bgsim_server.app import create_app
from bgsim_server.config import Settings
from bgsim_server.worker import FakeWorker


def serve_cached_catalog(path: Path) -> None:
    """Make the fake worker answer catalog.get with a catalog captured from the real worker."""
    catalog = json.loads(path.read_text(encoding="utf-8"))
    original = FakeWorker._dispatch

    async def dispatch(self, method, params):  # type: ignore[no-untyped-def]
        if method == "catalog.get":
            return catalog
        return await original(self, method, params)

    FakeWorker._dispatch = dispatch  # type: ignore[method-assign]


def main() -> None:
    settings = Settings.from_env()
    dist = os.environ.get("BGSIM_WEB_DIST")
    if dist:
        settings = replace(settings, web_dist=Path(dist))
    cached = os.environ.get("BGSIM_CATALOG_JSON")
    if cached:
        serve_cached_catalog(Path(cached))
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
