# Contracts

`schemas/*.schema.json` (JSON Schema 2020-12) is the single source of truth for the shapes the
Julia worker, the Python backend and the TypeScript web app exchange. Every schema carries
`"$id": "https://bgsim.local/schemas/<name>.schema.json"`, cross-schema references use that
absolute id, and both test suites register all eight schemas by `$id` before validating.

`fixtures/<name>/valid/**/*.json` must validate (the walkers use a recursive glob, so
`run.synthetic/` counts); `fixtures/<name>/invalid/*.json` must fail for the reason written in
their top-level `"$comment"` (for the array-rooted `diagnostic` schema, in the offending item).
Invalid fixtures stay invalid by omitting a required field or by a wrong type/enum, never because
of the comment, and `$comment` is an allowed property wherever the fixtures use it. A
`fixtures/<name>/semantic/*.json` fixture is schema-valid on purpose and states the failure the
language lanes must raise in a top-level `$comment` of the form `expected E<code>: ...`.

Conventions the plan leaves open: `required` is the plan's core of a shape and defaultable extras
(rotation, flipX, params, constants, starts, ui, plots, scene, bindings, stats, route, label) are
optional; `output.mode` is `points` or `interval`; `modelHash` is a sha256 hex digest, optionally
`sha256:`-prefixed; catalog `size` arrays are the default expansion of structural constants; a
diagnostic `path` is an instance path or a scene target (`joint:`/`link:`/`frame:`/`visual:`).

Data files (plan 3.5): `columns.f64` is the time column followed by one column per manifest signal,
`stream.f64` is row-major `[t, v1 ... vn]`, both little-endian Float64 and gitignored, written by
`fixtures/run-manifest/valid/run.synthetic/generate.py`; event instants are recorded twice with the
same `t` (left and right limit). Generated code lives in `backend/src/bgsim_server/contracts.py`
(pydantic v2) and `web/src/contracts/` (one `.ts` per schema plus `index.ts`); regenerate both with
`uv run tools/gen_contracts.py`, and never edit the generated files by hand.
