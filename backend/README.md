# bgsim-server

The bg-sim Python backend. M0.2 lays down this project with the contracts
harness only: the JSON Schemas in `../../contracts/schemas/` are turned into
`src/bgsim_server/contracts.py` by `uv run tools/gen_contracts.py`, and
`tests/test_contracts.py` validates every fixture against both the schemas and
the generated pydantic models.

M0.4 adds the FastAPI app, the worker supervisor and the `bgsim` entry point.

    uv run pytest -q
    uv run ruff check .
