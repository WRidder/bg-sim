"""``uv run bgsim``: serve the API on 0.0.0.0:8765 and supervise the worker."""

from __future__ import annotations

import uvicorn

from .app import create_app
from .config import Settings

#: Seconds an idle keep-alive connection stays open. Uvicorn's default of 5 closes it while a
#: client can be sending its next request on it, and that request dies with a connection reset:
#: a Playwright spec's POST and DELETE share a socket, an idle gap of a test's length apart.
KEEP_ALIVE_S = 300


def main() -> None:
    settings = Settings.from_env()
    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info",
                timeout_keep_alive=KEEP_ALIVE_S)


if __name__ == "__main__":
    main()
