# bgsim-server

The bg-sim Python backend (plan sections 2.1, 3.7 and 6).

- `src/bgsim_server/contracts.py` — generated pydantic v2 models (M0.2, written by
  `uv run tools/gen_contracts.py`).
- `src/bgsim_server/config.py` — settings (`BGSIM_PORT_HTTP`, `BGSIM_PROJECTS_ROOT`,
  `BGSIM_JULIA`, `BGSIM_FAKE_WORKER`, `BGSIM_REPO`).
- `src/bgsim_server/worker.py` — the Julia worker supervisor: length-prefixed TCP
  framing (plan 3.6), request/response correlation, per-method timeouts,
  notification fan-out, the health state machine and auto-restart with backoff.
  `BGSIM_FAKE_WORKER=1` swaps the Julia process for a fixture-driven fake that
  speaks the same framing over a real socket.
- `src/bgsim_server/app.py` — the FastAPI app: `GET /api/health`, plus the built
  web app (`web/dist`) at `/` with an SPA fallback.
- `src/bgsim_server/__main__.py` — the `bgsim` entry point (uvicorn on
  `127.0.0.1:8765`).

## Run

`uv run bgsim` must be run from this directory (uv project discovery stops at the
repository root, where there is no `pyproject.toml`); from the repository root use:

    uv run --directory backend bgsim
    BGSIM_FAKE_WORKER=1 uv run --directory backend bgsim

Check the health state:

    curl.exe -s http://127.0.0.1:8765/api/health

## Tests

    uv run --directory backend pytest -q            # fake worker, no Julia needed
    uv run --directory backend ruff check .
    uv run --directory backend pytest -q -m julia   # real `ping` against Julia
