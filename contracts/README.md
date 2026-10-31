# Contracts

`schemas/*.schema.json` (JSON Schema 2020-12) is the single source of truth for the shapes the
Julia worker, the Python backend and the TypeScript web app exchange. Every schema carries
`"$id": "https://bgsim.local/schemas/<name>.schema.json"`, cross-schema references use that
absolute id, and both test suites register all thirteen schemas by `$id` before validating.

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
Multibond fixture equations are component-wise (`p.e[k]`, `p.f[k]`) by contract (D-MB10); a
whole-field write on a multibond port is E006, so do not reintroduce one in a fixture.

Node images (plan 3.3): `ui.image` is `{ mime, data, fit }`, where `data` is bare standard base64
of at most 699052 characters (512 KiB decoded). `model.subsystem-images.json` carries a PNG
(`contain`) and an SVG (`stretch`). The invalid fixtures `model.image-*.json` cover a bad mime, a bad
fit and a `data:` URL in `data`. The size limit is tested in code (`test_contracts.py`,
`contracts.test.ts`) rather than with a 700 KB fixture.

Data files (plan 3.5): `columns.f64` is the time column followed by one column per manifest signal,
`stream.f64` is row-major `[t, v1 ... vn]`, both little-endian Float64 and gitignored, written by
`fixtures/run-manifest/valid/run.synthetic/generate.py`; event instants are recorded twice with the
same `t` (left and right limit). Generated code lives in `backend/src/bgsim_server/contracts.py`
(pydantic v2) and `web/src/contracts/` (one `.ts` per schema plus `index.ts`); regenerate both with
`uv run tools/gen_contracts.py`, and never edit the generated files by hand.

Debugging (M4, plan 3.8): `debug.schema.json` holds the shared debug shapes (`breakpoint`, a
`oneOf` of the five kinds, each requiring its own kind object; `pausedInfo`, `frame`, `edit`,
`runDebugInfo`, `breakpointStatus`, `evaluateResult`, `valuesResult`, `explainResult`, ...).
`worker-rpc` references them for the debug methods and the `debug.paused`/`debug.resumed`
notifications, and `run-manifest` for the optional `debug`, `parentRun` and `branchAt` fields
(status `paused`). `frameValue.value` nests at most three array levels (a Mat of Vecs), because
the code generators reject recursive `$ref`s.

Sticky notes: `diagram.annotations` (on every diagram level, a subsystem's nested diagram
included) are the canvas notes, `kind: "text"` with Markdown `text`, a frame `x`/`y`/`w`/`h` and
an optional `color` (`yellow`, `blue`, `green`, `pink`, `grey`; absent means yellow, so the editor
never writes `yellow`). They are editor state like positions: the Julia parser drops them, so
compile, simulation, the compile key and the C/FMU export do not change
(`model.sticky-notes.json` flattens exactly like `model.subsystem-port-ui.json`).

Canvas shapes: `diagram.shapes` (every diagram level) are background drawings behind notes,
wires and blocks, in z order (the first entry is the back-most). `kind` is `rectangle`,
`roundedRectangle`, `ellipse`, `line` or `arrow`; a line runs from (`x`, `y`) to
(`x + w`, `y + h`). Optional `fill`/`stroke` (`shapeColor`: the note palette plus `ink` and
`none`; absent fill is none, absent stroke is ink), `strokeWidth`, `strokeStyle`, `opacity`,
`text` and `locked`; the editor never writes a default. Editor state like notes: the Julia parser
drops them (`model.canvas-shapes.json` flattens like `model.subsystem-port-ui.json`, and the
export test checks an identical `model.c`).

Dashboard (DASHBOARD_PLAN.md): the model's optional top-level `dashboard` (`cards` in grid order;
display cards bind `signals`, input cards bind one `parameter` with an override `value`, a
schedule card holds a `schedule` table of block `parameters` x `rows`) is editor state; the
compiler and the export ignore it. What a run uses travels separately: `run.start` takes optional
`parameterOverrides` (`{target, kind?, value}`, applied before flattening) and
`parameterSchedule` (`{t, target, value}`, applied at `t` during the run), both defined in
`run-manifest.schema.json` and recorded in the manifest. `kind` `block` (the default) targets
`<instance path>/<param>`; `kind` `global` targets a global parameter as `global:<name>` (the key
of `BGSim.IR.override_globals`, applied before the globals are evaluated, so dependents re-fold).
Globals cannot be scheduled.
