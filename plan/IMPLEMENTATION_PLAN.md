# bg-sim: design and implementation plan

Status: v1.1, 2026-10-22 (adds milestone M5, live debugging: decisions D20 to D27, sections 3.8, 5.13 and 7.9). v1: 2026-10-21. Source spec: `spec/Modeling Language Spec v0.1.md` (called "the spec" below).
Audience: an orchestrator agent that delegates the work packages (WPs) below to sub-agents and runs them in one session through milestone M3 and then M5 (debugging), with M4 as a stretch goal.

> **Version naming.** The milestones of this plan (M0 to M5) are not the spec's release tags. The spec tags components as v0.1, v0.2 or v0.3. This plan implements:
> - the **spec v0.1 catalog**;
> - the spec v0.2 *language* features we need (discrete clocks, events, Vec/Mat);
> - the spec's planar mechanics as a stretch goal (M4);
> - live debugging of simulation runs (M5). The spec does not cover debugging; section 5.13 and decisions D20 to D27 define it.
>
> Spatial (3D) multibody mechanics, thermal, `CC`/`II`, state machines and every export target are **out of scope**. See section 12.

---

## 0. How to run this plan (read first)

### 0.1 Orchestrator protocol
1. Work through the milestones in this order: M0, M1, M2, M3, **M5**, then M4. (M5 was added in v1.1, after M4 was numbered; it is in scope, and M4 stays the stretch goal.) Inside a milestone, start every WP whose `Depends` are done, in parallel, one sub-agent per WP.
2. Give each sub-agent:
   - the full text of its WP;
   - sections 0.2, 1 and 2 of this plan;
   - the sections the WP lists under `Read`;
   - the spec when the WP says so.
3. After each WP:
   - run its acceptance commands yourself;
   - mark it `done`, `failed` or `rescoped` in `plan/STATUS.md`, with a 1 to 3 line note;
   - commit it (`git commit -m "<WP-ID>: <summary>"`).
4. After each milestone, run the **integration gate** (section 10.3). Never start the next milestone with a red gate. Fix it in a dedicated `FIX-<milestone>-n` WP.
5. If a WP fails twice:
   - split it, or move the failing part to a later milestone, and record why in `STATUS.md`;
   - never mark a WP done with stubs, skipped tests or weakened assertions.
6. A sub-agent may need a contract change, such as a field missing from a JSON Schema.
   - It stops and reports the change it needs.
   - The orchestrator runs a short `CONTRACT-n` WP that updates the schema, the fixtures and all three language bindings together, then resumes the blocked WP.
7. **Julia precompilation is shared state.** Run M0.3 alone, so ModelingToolkit and the solvers are precompiled once. Later Julia WPs can run in parallel, but if one adds a dependency, the orchestrator runs `Pkg.resolve` / `Pkg.precompile` once before the other Julia WPs continue.

### 0.2 Rules for every sub-agent
- Touch only the paths listed under `Owns` in your WP, plus new test files next to them. Read anything.
- **Never guess a third-party API.** ModelingToolkit changed its API in v10:
  - use `System` (not `ODESystem`) and `mtkcompile` (not `structural_simplify`);
  - `ODEProblem(sys, op, tspan)` takes one merged operating-point map.
  - Before you use any MTK, SciML, xyflow, uPlot, CodeMirror or Babylon API, check it in the installed package (Julia: `@doc`, `methods`, the source under `~/.julia/packages`; JS: the `.d.ts` files in `node_modules`) or in the official docs. Write a 10-line probe script first when you are unsure.
- Python: run it only through `uv run`, and add dependencies only with `uv add`. Julia: always `--project=julia/BGSim`. Node: `npm` inside `web/`.
- Every WP adds tests. "Done" means its acceptance commands pass on this Windows machine.
- Don't leave TODOs in delivered code paths. If something is deferred, say so in your report and in `plan/STATUS.md` (the orchestrator writes `STATUS.md`).
- Errors must point at user code (spec principle 6). Every diagnostic uses the contract in section 3.4.
- End with a report of at most 15 lines:
  - the files you added or changed;
  - your decisions;
  - any deviations from the plan;
  - the exact commands you ran and their results.

### 0.3 Environment facts
- Windows 11, PowerShell default, Git Bash available. Repo root `D:\bg-sim`. The repo is not under git yet; M0.1 runs `git init`.
- Julia 1.13.2 through juliaup, with a fresh depot (no packages yet).
  - If ModelingToolkit or OrdinaryDiffEq cannot be resolved or precompiled on 1.13, run `juliaup add 1.12` and `juliaup override set 1.12` in the repo, then record that in `STATUS.md`.
- uv 0.13.4 and no system Python. Use `uv python pin 3.13`.
- Node v24.21.0, npm 11.19.
- The reference viewer is at `D:\CtrlX Agentic Machine Control\framework\hmi\src\viewer\` (read only; copy from it, never edit it).

---

## 1. Decisions and assumptions

### 1.1 Confirmed with the user
| Topic | Decision |
| --- | --- |
| Scope | Plan milestones M0 to M3, with M4 (planar mechanics) as a stretch goal. Spatial mechanics is out of scope. |
| Export | **Simulation only.** No juliac build, no fixed-step step function, no C ABI, no ctrlX/SIL. W203 and E104 (which concern `dt`) are deferred. |
| Simulation engine | Our own front end (parse, validate, flatten, junctions, domains, causality, units) emits a **ModelingToolkit v10+ `System`**. It is then compiled with `mtkcompile`, built into an `ODEProblem`, and solved with OrdinaryDiffEq. |
| Deployment | Local, single user. One command (`uv run bgsim`) starts the backend and the Julia worker on `127.0.0.1`. Projects are plain files on disk, and there is no auth. |
| Examples | DC motor; bouncing ball; reaction-wheel cube (1D balancer, plus 3D corner balancer); robot arm (planar and 3D); drivetrain (DC motor, gearbox, wheel, flexible rod, wheel) with a Kalman filter and state-space control; RLC as iconic vs bond graph; quarter-car; hydraulic cylinder servo. |
| Multibody | The 3D arm and the 3D cube are hand-derived equation blocks, with the equations given in section 9. Planar components arrive in M4, where they rebuild the planar arm and the 1D balancer and are cross-checked against the earlier versions. |
| Debugging | In scope as **M5**: live debugging of simulation runs in the editor. That covers line breakpoints in discrete code, signal (watch), time and event breakpoints, stepping, inspecting values, changing parameters while paused, rewind by deterministic re-run, and "explain this signal". Triggered traces on a real controller and lockstep SIL debugging are out of scope (section 12). |

### 1.2 Decided by this plan (the spec's open questions and gaps)
| # | Spec item | Decision | Why |
| --- | --- | --- | --- |
| D1 | `~` versus `=` in equations | Only `~` is accepted. `=` in `@equations` gives `E001`, with the hint "use `~` for equations". | Unambiguous, as the spec argues. A quick-fix button in the editor rewrites it. |
| D2 | Unit checking | Our own small dimension checker in Julia (section 5.3). No Unitful. | Trim-compatible later, small, and gives full control of messages. |
| D3 | Discrete scheduling | Our own scheduler around the continuous integrator, using the OrdinaryDiffEq integrator interface (section 5.8). MTK clocks are not used. | It gives deterministic tick order exactly as the spec describes, and it maps one-to-one onto a future fixed-step export. |
| D4 | Parameters in simulation | Every `@parameters` entry stays a runtime MTK parameter, whether tunable or not. Only `@constants` are folded. | A parameter-only change re-simulates without recompiling (`remake`). Folding is an export concern. |
| D5 | `@components` / `@connections` (the spec's open item) | Added as scopes in M2 (WP J2.6). They are the textual form of a subsystem. | Needed for the spec's `GearWithBacklash` example and for composite library blocks. |
| D6 | `@causality` syntax (the spec gives one example only) | `@causality p => :effort_out` is preferred causality. `@causality p => (:effort_out, :fixed)` is fixed causality. `@causality (p1, p2) => :transformer` or `:gyrator` declares a two-port causal relation. No declaration means free causality. | It completes the spec's example in the same style. |
| D7 | Connection semantics (the spec says "exactly two ports per bond" but its iconic examples need nodes) | Three kinds (section 5.5):<br>• **Bond**: a two-port connection that touches at least one `Generic` port. It has a direction, and the half arrow sets positive power.<br>• **Wire**: a connection between concrete-domain power ports. It forms a node with 2 or more ports; the across variables are equal and the through variables sum to zero.<br>• **Signal**: one output to many inputs. | This is what the spec's sign convention and its `GearBacklash` example imply (`w ~ a.f - b.f`, so velocity is the across variable). |
| D8 | Across/through per domain | Electrical, Hydraulic: across = `e` (potential, pressure) and through = `f`. Translation, Rotation, Planar: across = `f` (velocity) and through = `e` (force, torque). | Follows from "power positive into each port" and the spec examples. |
| D9 | Generic-domain units | Inside `Generic` blocks, unit strings may use the pseudo-dimensions `effort` and `flow` (for example `c` has `unit = "flow*s/effort"`). They are substituted once the domain has been adopted. | The spec says "a C on an electrical bond takes farads". This makes that checkable. |
| D10 | Variable-arity ports (`u[]`) | Declared as `@inputs u::Vec{N}` with `N` a structural constant. The editor shows `N` handles, and connecting to a ghost "+" handle increments `N`. | Static sizes, as spec principle 5 requires. |
| D11 | String-valued parameters (Sum signs `"+-+"`, interpolation method) | Strings stay forbidden. Signs are `Vec{N}` of ±1, and enumerations are `Int` with an `options` attribute (for example `[options = ["hold", "linear"]]`). The inspector shows text or a drop-down. | Spec principle: no strings. |
| D12 | Lookup tables, noise, delay | Implemented as **stdlib intrinsics**: `interp1`, `interp2`, `noise_normal(seed, k)` and `delay`. They are registered with Symbolics as opaque functions and may be called only from blocks under `stdlib/`, except `interp1` and `interp2`, which users may call too. | The spec already allows opaque registered functions (spatial section). An unrolled table search would blow up symbolically. |
| D13 | Sizes that depend on parameter values (TF numerator/denominator, state-space matrices) | Structural constants that can be overridden per instance. When the user enters an array of a different length, the inspector updates the matching constant automatically. A change is structural and triggers a recompile. | Static sizes. |
| D14 | Diagnostic codes the spec lacks | `E000` syntax error (parser stage); `E106` causal conflict on a fixed-causality element; `E107` unresolved Generic domain (a bond island with no concrete domain is accepted as dimensionless, so this is a warning, `W205`); `E900` internal compiler error (always with a block path when one is known); `E901` solver failure (with time and the last state); `W206` the event limit was reached (Zeno). | Every failure mode needs a code. |
| D15 | Recording | By default **all** signals are recorded: every unknown, every observed variable and every port `e`/`f` of every instance. Each power port also gets a derived power signal `e*f`. | "Essentially all signals can be plotted." |
| D16 | Plot/Scope blocks | A Scope block is an editor object. It opens a plot panel preset with its connected signals and has no effect on simulation. | Every signal is recorded anyway. |
| D18 | Temporaries in discrete code (the spec is silent) | In `@discrete` and `@events` only, assigning to an undeclared name creates a block-local temporary of type `Real` (or of the assigned value's type and size). It is not stored between ticks. In `@equations`, an undeclared name is always E003. | Readable controller code (see `LQGController`, 9.5). |
| D19 | Event direction | `cond => begin … end`. `cond` is a real expression `c` (fires when `c` crosses zero upward) or a comparison `a < b` / `a > b` (fires when it becomes true; normalized to `c = b - a` or `c = a - b`). | The spec says "crossing zero from negative to positive"; comparisons are friendlier. |
| D17 | Visual style | A professional engineering-tool look of our own, in light and dark themes. The HMI's ISA-101 operator style guide does **not** apply. Only the HMI's *viewer setup* is reused. | The audience is engineers, not operators. |
| D20 | Debug runs (M5) | A run started with `debug` set compiles its discrete partitions in a **debug variant** that has statement hooks (5.13). The MTK system, the continuous problem and the solver settings are the same as in a normal run. The debug flag is part of the cache key of the discrete partition functions only. | Debugging costs nothing when it is off, and a debug run computes the same numbers as a normal run. |
| D21 | Where line breakpoints exist (M5) | Only on `@discrete` lines that hold a statement. `@events` bodies lower to MTK affects, so they get **event breakpoints** instead: a pause right after the event fired, located at its `cond`. A line breakpoint in `@equations`, `@initial` or a declaration gives **E401**, with the hint "equations do not execute in order; add a watch breakpoint on a signal instead". | The compiler sorts and solves acausal equations, so a line has no moment at which it runs. |
| D22 | Watch (signal) breakpoints (M5) | A watch is an expression in a read-only `watch` scope: literals, whitelisted functions, `t`, parameters, and signals written as `s"Motor1/i"` (a non-standard string literal, so JuliaSyntax parses it; it is never evaluated). Bare names resolve relative to an optional context instance. A watch fires on the **upward crossing**, like `@events` conditions (D19). All watches live in one pool of 16 slots of a single vector continuous callback that every debug run installs, and they read values through SymbolicIndexingInterface observed functions. | The pause lands on the exact crossing, watches can change while paused without recompiling, and variables that `mtkcompile` eliminated can be watched. |
| D23 | Pausing (M5) | A paused run is a run task blocked on its command channel at a safe point: after an integrator step, after a tick, after an event, or at a statement hook. It never pauses inside the solver. `debug.pause` sets an atomic flag that is checked where the cancel flag is checked. `run.cancel` wakes a paused run and ends it as `cancelled`. While a run is paused, the worker keeps serving other requests. | It reuses the scheduler loop of D3 as it is, with no solver support needed. |
| D24 | Changes while paused (M5) | Parameters can always be changed, through `setp` on the integrator (D4 keeps every parameter a runtime value). States can be changed only if they are differential states and the compiled system has no algebraic equations; otherwise **E402**. Discrete locals and held outputs are read-only. Structural changes need a new run. | Changing a DAE state needs a consistent re-initialization, which M5 does not attempt. |
| D25 | Reproducibility (M5) | Every change made while paused is appended to the run's `debug.edits` as `(t, target, value)`. **Replay** runs the model as a normal run that applies the edits at those times. **Rewind** to time t starts a new run (`parentRun`, `branchAt = t`) that replays the parent up to t and pauses there. There are no in-memory checkpoints in M5. | Runs are deterministic, so a re-run is an exact rewind, and every debug session can be reproduced from its manifest. |
| D26 | Breakpoint storage (M5) | Breakpoints are editor state, saved per model in `localStorage` (wrapped in try/catch), not in the model document. A run's manifest records the breakpoints that were active. | Breakpoints must not change the model hash or the compile cache. |
| D27 | Evaluating expressions while paused (M5) | `debug.evaluate` uses the constant-folding interpreter (4.3), extended with signal lookups and, at a statement pause, the frame's locals. It is read-only and never uses `eval`. Errors are E001 to E006 with `scope = "watch"`. New codes: **E401** (no statement on that line), **E402** (state change refused) and **W401** (the breakpoint's block is not used in this model, so it stays unverified). | The same safety rule as all user code. |

### 1.3 Assumptions (change them here if wrong)
- There is a single model per editor tab, and a project holds several models plus a project library.
- Browser target: current Chromium and Firefox on desktop. Touch is not a goal.
- Language version stamp `"0.1.0"` goes in every saved model and block.

---

## 2. Architecture

### 2.1 Process model
```
Browser (React app, Vite build)
   │  HTTP JSON + WebSocket (JSON control, binary frames)
   ▼
Python backend  (FastAPI/uvicorn, 127.0.0.1:8765)   ── serves web/dist in production
   │  owns: projects on disk, run storage, decimation, streaming, mesh conversion,
   │        worker supervision, request validation (pydantic from contracts)
   │  localhost TCP, length-prefixed frames (section 3.6)
   ▼
Julia worker  (julia --project=julia/BGSim --threads=2, long-lived, warm)
      owns: language parser/validator, library catalog, flattening, causality, units,
            MTK lowering, simulation, recording (writes run files directly)
```
- A single worker process serves everything. Requests are handled on Julia tasks. A simulation runs on its own task, and cancellation uses an atomic flag that is checked every integrator step.
- The backend restarts the worker if it crashes, and reports `worker_restarted` to the UI.
- Warm-up: the worker precompiles through a PrecompileTools workload in BGSim, and on start-up it compiles and runs a tiny RC model in the background. `/api/health` reports `warming` until that finishes.

### 2.2 Repository layout
```
bg-sim/
  CLAUDE.md
  spec/                         # the language spec (input, read-only)
  plan/IMPLEMENTATION_PLAN.md   # this file
  plan/STATUS.md                # orchestrator-maintained progress log
  contracts/
    schemas/*.schema.json       # single source of truth for data shapes
    fixtures/**                 # valid + invalid examples, used by all three test suites
  julia/BGSim/
    Project.toml  Manifest.toml
    src/BGSim.jl
    src/syntax/   parse.jl ast.jl scopes.jl whitelist.jl
    src/units/    dims.jl unitparse.jl unitcheck.jl
    src/ir/       blockdef.jl modeldoc.jl flat.jl
    src/library/  loader.jl catalog.jl intrinsics.jl
    src/compile/  instantiate.jl connect.jl domains.jl junctions.jl balance.jl
                  causality.jl events.jl discrete.jl pipeline.jl explain.jl (M5)
    src/lower/    mtk.jl fnmap.jl
    src/sim/      simulate.jl scheduler.jl recorder.jl
                  debug.jl hooks.jl watch.jl edits.jl          # M5
    src/worker/   protocol.jl server.jl
    src/diagnostics.jl
    stdlib/       bondgraph/ sources/ continuous/ discrete/ electrical/
                  translation/ rotation/ hydraulic/ converters/ planar/
    test/         runtests.jl  + per-module test files, golden/ fixtures/
  backend/                      # uv project "bgsim-server"
    pyproject.toml  uv.lock  .python-version
    src/bgsim_server/  app.py config.py worker.py projects.py runs.py
                       decimate.py stream.py meshes.py contracts.py (generated)
                       debug.py fake_debug.py (M5)
    tests/
  web/                          # Vite + React + TS
    package.json  vite.config.ts  tsconfig*.json  playwright.config.ts
    src/app/ src/api/ src/state/ src/contracts/ (generated) src/theme/
        src/library/ src/editor/ src/inspector/ src/code/ src/diagnostics/
        src/plot/ src/viewer/ src/scene/ src/examples/ src/debug/ (M5)
    tests/e2e/ tests/perf/
  examples/                     # example projects (copied into a user project on "open example")
    <name>/bgsim.project.json, models/, library/, scenes/, design/ (uv scripts)
  tools/
    check.py                    # runs all lanes' checks (uv run tools/check.py [--lane j|p|w|x])
    gen_contracts.py            # schema → pydantic; npm script → TS
    dev.py                      # starts backend + vite dev server
  .gitignore .gitattributes
```

### 2.3 Lanes (for parallel work)
| Lane | Prefix | Owns |
| --- | --- | --- |
| Contracts | C | `contracts/`, `tools/gen_contracts.py`, the generated files |
| Julia | J | `julia/BGSim/` |
| Python | P | `backend/` |
| Web | W | `web/` |
| Examples and integration | X | `examples/`, `web/tests/e2e/` for the example flows |

The web lane never waits for the Julia lane. It develops against `contracts/fixtures` (a catalog fixture, a diagnostics fixture and a synthetic run) and against a **mock mode** in the backend (`BGSIM_FAKE_WORKER=1`), which answers from the fixtures.

---

## 3. Contracts (WP C0 formalizes these as JSON Schema)

Every shape below becomes `contracts/schemas/<name>.schema.json` (JSON Schema 2020-12). Each one gets at least one valid fixture and one invalid fixture.
- Python: pydantic v2 models are generated with `datamodel-code-generator`.
- TypeScript: types are generated with `json-schema-to-typescript`.
- Julia: plain structs are parsed with JSON3. The Julia tests check them against the fixtures.

### 3.1 Identifiers and signal names
- **Instance path:** subsystem names joined by `/`, for example `Plant/Motor1`. Instance names match `[A-Za-z_][A-Za-z0-9_]*` and are unique within their diagram.
- **Signal ID:** `<instance path>/<name>` for variables, inputs and outputs, for example `Plant/Motor1/w`. Port fields use `.`: `Plant/Motor1/shaft.e`, `Plant/Motor1/shaft.f`, `Plant/Motor1/shaft.P` (the derived power).
- **Array elements:** `Ctrl/xhat[2]`, 1-based. Matrix elements: `Ctrl/P[1,2]`.
- **Block reference:**
  - `stdlib:electrical/Resistor` for the standard library;
  - `project:MyGear` for the project library;
  - `inline:<node-id>` for an equation or code block embedded in the model.

### 3.2 Library catalog (`catalog.schema.json`), produced by the worker
```jsonc
{ "language": "0.1.0",
  "blocks": [{
    "ref": "stdlib:bondgraph/C", "name": "C", "group": "Bond graph", "release": "0.1",
    "description": "Capacitive storage", "icon": "bg-C",
    "constants": [{ "name": "N", "type": "Int", "default": 2, "structural": true }],
    "parameters": [{ "name": "c", "type": "Real", "default": "1.0", "unit": "flow*s/effort",
                     "min": 0, "max": null, "tunable": false, "description": "", "options": null }],
    "inputs":  [{ "name": "u", "type": "Real", "size": [], "unit": null }],
    "outputs": [{ "name": "y", "type": "Real", "size": [], "unit": null }],
    "ports":   [{ "name": "p", "domain": "Generic", "size": [] }],
    "variables": [{ "name": "q", "type": "Real", "size": [], "unit": "flow*s", "start": "0.0", "state": "prefer" }],
    "causality": [{ "ports": ["p"], "kind": "preferred", "value": "effort_out" }],
    "source": "@block C begin ... end",   // full text, for "open source" and "copy to project"
    "path": "stdlib/bondgraph/C.jl"
  }],
  "junctions": [{ "ref": "junction:0" }, { "ref": "junction:1" }],
  "domains": [{ "name": "Electrical", "effort": {"name":"voltage","unit":"V"}, "flow": {"name":"current","unit":"A"},
                "across": "e", "size": 1 }, ... ]
}
```

### 3.3 Model document (`model.schema.json`): what the editor saves (`models/<name>.bgmodel.json`)
```jsonc
{ "format": "bgsim.model", "language": "0.1.0", "name": "DCMotorSpeed",
  "diagram": {                                  // root diagram; subsystems nest the same shape
    "nodes": [{
      "id": "n7",                               // stable UUID-ish, never shown
      "name": "Motor1",                         // instance name (path segment)
      "block": { "ref": "stdlib:converters/DCMotor" }        // or:
           //  { "junction": "0" } | { "inline": { "source": "@block ... end" } }
           //  | { "subsystem": { "ports": [...], "diagram": { ...same shape... } } }
      "position": { "x": 120, "y": 80 }, "rotation": 0, "flipX": false,
      "params":    { "R": "2.0", "kt": "0.05" },             // expression strings (section 5.2.4)
      "constants": { "N": 3 },
      "starts":    { "w": "0.0" },                           // start-value overrides
      "ui": { "showLabel": true, "color": null }
    }],
    "connections": [{
      "id": "c3", "kind": "bond" | "wire" | "signal",
      "from": { "node": "n7", "port": "p" },    // for junction nodes "port" is omitted
      "to":   { "node": "n2", "port": "a" },    // bond: half arrow at "to" (power from → to)
      "route": [{ "x": 0, "y": 0 }],            // optional waypoints
      "label": null
    }],
    "subsystemPorts": [],                        // only inside subsystems: exposed ports {name, kind, ...}
    "annotations": [{ "id": "a1", "kind": "text", "text": "Plant", "x": 0, "y": 0, "w": 200, "h": 120 }]
  },
  "settings": { "t_start": 0.0, "t_end": 1.0, "solver": "auto", "reltol": 1e-6, "abstol": 1e-8,
                "max_step": null, "output": { "mode": "points", "points": 5000 }, "event_limit": 10000 },
  "plots": [{ "id": "p1", "title": "Speed", "signals": ["Motor1/shaft.f"] }],
  "scene": { "file": "scenes/drivetrain.sdf" },
  "bindings": [ /* the spec's binding schema, section "Visualization and bindings" */ ]
}
```
- Project file `bgsim.project.json`: `{ format, language, name, models: [...], libraryDir: "library", scenesDir: "scenes" }`.
- Project library: `library/<BlockName>.jl`, one `@block` per file, with the file name equal to the block name.

### 3.4 Diagnostic (`diagnostic.schema.json`)
```jsonc
{ "code": "E103", "severity": "error" | "warning" | "info",
  "message": "14 unknowns, 13 equations",
  "hint": "Motor1 declares 3 variables but has 2 equations",
  "path": "Plant/Motor1",                       // instance path, null for model-wide
  "block": "stdlib:converters/DCMotor",         // block ref, if any
  "scope": "@equations",                        // if source-level
  "source": { "kind": "stdlib" | "project" | "inline", "ref": "...",
              "range": { "line": 12, "col": 5, "endLine": 12, "endCol": 19 } },
  "node": "n7", "connection": null,             // editor ids for canvas highlighting
  "related": [ { "path": "...", "message": "..." } ] }
```

### 3.5 Run manifest and data (`run.schema.json`)
- Each run lives in `<project>/runs/<run-id>/`. The folder is gitignored, and the UI keeps the last 20 runs per model, configurable.
- `manifest.json`:
  ```jsonc
  { "id", "model", "modelHash", "created", "status": "running" | "done" | "failed" | "cancelled",
    "settings", "stats": { "compile_s", "sim_s", "steps", "events", "states", "equations" },
    "signals": [ { "id": "Motor1/shaft.f", "unit": "rad/s", "kind": "state" | "algebraic" | "observed" | "port" | "power" | "discrete" | "input" | "output", "path": "Motor1", "type": "Real" | "Int" | "Bool" } ],
    "time": { "n": 5001, "t0": 0.0, "t1": 1.0 }, "diagnostics": [ ... ],
    "layout": "columnar-f64-v1" }
  ```
- `stream.f64`: row-major `[t, v1 … vn]` little-endian Float64 rows, appended while the simulation runs. It matches the spec's frame layout.
- `columns.f64`: written at the end. It holds the time column, then one column per signal in manifest order, each `n` Float64 values (this is the spec's playback file).
- Bool and Int signals are stored as Float64.
- Event instants are recorded twice, as left and right limits with the same `t`, so steps render as vertical edges.
- **M5 additions** (WP C5.0): `status` gains `paused`. Optional fields: `debug: { breakpoints, edits, pauses: [{ t, reason }] }`, plus `parentRun` and `branchAt` for branch runs (3.8, 5.13).

### 3.6 Worker protocol (`worker-rpc.schema.json`)
- Transport: the backend listens on a random localhost TCP port and starts Julia with `BGSIM_PORT=<port>`, and the worker connects back. Each frame is a `u32 LE length`, a `u8 kind` (0 = JSON, 1 = binary) and a payload.
- Julia stdout and stderr are only logs. They are captured to `backend/logs/worker.log` and are never protocol.
- Requests: `{ "id": 17, "method": "...", "params": {...} }`. Responses: `{ "id": 17, "result": ... }` or `{ "id": 17, "error": { "message", "diagnostics": [] } }`.
- Notifications carry no `id`: `{ "method": "run.progress", "params": {...} }`.

| Method | Params | Result |
| --- | --- | --- |
| `ping` | none | `{ version, julia, warm }` |
| `catalog.get` | `{ projectLibraryDir }` | the catalog (3.2), including project blocks |
| `block.check` | `{ source, ref }` | `{ diagnostics, interface }` for the fast as-you-type pass, with a target under 150 ms warm |
| `model.check` | `{ model, projectDir }` | `{ diagnostics, domains: {connId: domain}, causality: {connId: {strokeAt: "from" or "to"}}, unitFactors: {connId: factor}, signals: [...], stats }` |
| `run.start` | `{ runId, model, projectDir, runDir }` | `{ accepted: true }`, then notifications |
| `run.cancel` | `{ runId }` | `{ ok }` |
| `cache.clear` | none | `{ ok }` |

Notifications:
- `run.phase` `{ runId, phase: "parse" | "flatten" | "causality" | "mtkcompile" | "init" | "simulate" | "write", t_s }`
- `run.progress` `{ runId, t, rows }` at most 20 per second
- `run.done` `{ runId, status, stats, diagnostics }`
- `log` `{ level, message }`

M5 adds the debug methods and notifications of section 3.8.

### 3.7 HTTP and WebSocket API (backend)
| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | `{ backend, worker: "starting" \| "warming" \| "ready" \| "crashed", versions }` |
| `GET /api/catalog?project=` | Proxies `catalog.get`. Cached, and invalidated when files in the project library change. |
| `GET/POST /api/projects`, `GET /api/projects/{p}` | List, create (from an example or empty), open. `projects_root` is configurable (default `~/bgsim-projects`). |
| `GET/PUT/DELETE /api/projects/{p}/models/{m}` | Model documents, validated against `model.schema.json` on PUT. |
| `GET/PUT/DELETE /api/projects/{p}/library/{block}` | Project library sources. |
| `POST /api/check/block`, `POST /api/check/model` | Proxy to the worker. |
| `POST /api/projects/{p}/runs` | `{ model }` gives `{ runId }`. |
| `DELETE /api/runs/{id}` | Cancel. |
| `GET /api/runs/{id}` | The manifest. |
| `GET /api/runs/{id}/data?ids=a,b&t0=&t1=&px=1600` | Binary: `u32 n_signals`, `u32 n_points`, then a time column and value columns (Float64). Min/max (M4-style) decimated to at most `2*px` points per signal over `[t0, t1]`. A `px=0` request returns raw data. |
| `GET /api/runs/{id}/export.csv?ids=` | CSV export. |
| `WS /ws/runs/{id}` | Phases, progress, done, and a live decimated tail for subscribed signal ids (the client sends `{subscribe: [...]}`). |
| `WS /ws/stream/{id}` | The spec's viewer stream: JSON handshake, then binary frames `[t, v...]` at no more than 60 Hz, for a live or a finished run (`?mode=live` or `playback`). |
| `GET/PUT /api/projects/{p}/scenes/{file}`, `POST /api/projects/{p}/meshes` | SDF files, and mesh upload (STL, OBJ, DAE, GLB), which is converted to GLB with trimesh. |

### 3.8 Debug protocol (M5)
WP C5.0 adds `debug.schema.json`. It defines `Breakpoint`, `PausedInfo`, `Frame`, `Edit` and `ExplainResult`, which the worker RPC, the HTTP API and the run manifest use. Decisions D20 to D27; the simulator side is 5.13.

```jsonc
// Breakpoint
{ "id": "bp3", "enabled": true,
  "kind": "line" | "watch" | "time" | "event" | "exception",
  "line":  { "ref": "project:LQGController", "line": 14, "path": "Ctrl" | null },  // path null = every instance
  "watch": { "expr": "s\"Motor1/i\" > 5", "context": "Motor1" | null },          // D22
  "time":  { "t": 0.25 },
  "event": { "path": "Ball" | null },              // after an @events firing (of this instance)
  "exception": { "on": ["E901", "W206"] },         // pause before the run ends on these
  "condition": "k == 5" | null,                    // line breakpoints only, evaluated in the frame
  "hitCount": 3 | null }                           // line and watch: pause on the n-th hit
// PausedInfo (the debug.paused notification)
{ "runId": "...", "t": 0.4123, "tick": 412 | null,
  "reason": "entry" | "breakpoint" | "step" | "pause" | "event" | "exception" | "time",
  "breakpointId": "bp3" | null,
  "location": { "path": "Ctrl", "ref": "project:LQGController", "scope": "@discrete",
                "range": { "line": 14, "col": 9, "endLine": 14, "endCol": 31 } } | null,
  "frame": { "locals":   [{ "name": "v", "type": "Real", "size": [], "value": 0.12 }],
             "held":     [{ "name": "u", "type": "Real", "size": [], "value": 3.4 }],
             "previous": [] } | null,              // statement pauses only
  "diagnostics": [] }
// Edit (also stored in the manifest's debug.edits)
{ "t": 0.2, "kind": "parameter" | "state", "target": "Motor1/R", "value": 2.5 }
```

**Worker methods** (added to `worker-rpc.schema.json`):

| Method | Params | Result |
| --- | --- | --- |
| `run.start` (extended) | `{ ..., debug: { breakpoints, pauseOnEntry } \| null }` | as before |
| `debug.setBreakpoints` | `{ runId, breakpoints }`, always the full set | `{ breakpoints: [{ id, verified, resolved: { hooks, paths }, diagnostics }] }` |
| `debug.pause` | `{ runId }` | `{ ok }`, then `debug.paused` with reason `pause` |
| `debug.continue` | `{ runId }` | `{ ok }`, then `debug.resumed` |
| `debug.step` | `{ runId, granularity: "statement" \| "tick" \| "solverStep" \| "event" }` | `{ ok }`, then `debug.paused` with reason `step` |
| `debug.runTo` | `{ runId, t }` | `{ ok }` (a one-shot time breakpoint) |
| `debug.evaluate` | `{ runId, expr, context }` | `{ value, type, size, unit, diagnostics }` |
| `debug.values` | `{ runId, ids }` | `{ t, values }` at the pause |
| `debug.setParameter` | `{ runId, name, value }` | `{ ok, edit }`, or diagnostics |
| `debug.setState` | `{ runId, id, value }` | `{ ok, edit }`, or E402 |
| `run.replay` | `{ runId, newRunId, runDir }` | `{ accepted }`: a normal run that applies the parent's edits |
| `run.branch` | `{ runId, newRunId, runDir, t }` | `{ accepted }`: a debug run that replays the parent up to `t` and pauses |
| `model.explain` | `{ model, projectDir, signal }` | `ExplainResult` (5.13); needs no run |

- New notifications: `debug.paused` (a `PausedInfo`) and `debug.resumed { runId }`.
- A debug command on a run that is not paused, or is not a debug run, returns an RPC error (`"run is not paused"`), not a diagnostic.

**HTTP and WebSocket** (backend, WP P5.1):

| Endpoint | Purpose |
| --- | --- |
| `POST /api/projects/{p}/runs` | The body gains an optional `debug` object (`breakpoints`, `pauseOnEntry`). |
| `PUT /api/runs/{id}/breakpoints` | Proxies `debug.setBreakpoints`. |
| `POST /api/runs/{id}/debug/{command}` | `pause`, `continue`, `step`, `runTo`, `setParameter`, `setState`; the body is the method's params. |
| `POST /api/runs/{id}/evaluate`, `GET /api/runs/{id}/values?ids=` | Proxies `debug.evaluate` and `debug.values`. |
| `POST /api/runs/{id}/replay`, `POST /api/runs/{id}/branch` (`{ t }`) | Create the new run and return `{ runId }`. |
| `POST /api/check/explain` | Proxies `model.explain`. |
| `WS /ws/runs/{id}` | Also carries `debug.paused` and `debug.resumed`. The recorder flushes on every pause, so `/data` and the live tails reach the pause time. |

---

## 4. The language front end (applies to all J WPs)

The spec is normative. This section only adds implementation detail.

### 4.1 Parsing
- Use **JuliaSyntax.jl**: `JuliaSyntax.parseall(SyntaxNode, text; filename, ignore_errors=false)`.
- Parse errors become `E000` (syntax error) with the parser's range. (E000 is added to the code table; it is the parser stage.)
- Walk the `SyntaxNode` tree. **Never `eval` user code.** Convert it into our own AST (`src/syntax/ast.jl`): small immutable structs, each carrying `SourceRange(file, line, col, endLine, endCol)`.
- The top level is one or more `@block Name begin ... end`. Inside, only the scope macros are allowed: `@constants @parameters @inputs @outputs @ports @variables @initial @equations @discrete @events @causality @components @connections`. A scope macro may take a single declaration or a `begin` block.

### 4.2 Whitelist (per scope)
- `whitelist.jl` is the single table: syntax kind, then allowed scopes, then a lowering rule. It encodes the spec's tables "Operators and statements per scope" and "Built-in function whitelist" row by row.
- Each table row has one test, with an allowed case and a rejected case giving `E001` or `E002`.
- **Intrinsics** (D12) live in a separate table with a `stdlib_only` flag.

### 4.3 Declarations
- Form: `name::Type = default, [attrs]`. `Type` is one of `Real`, `Int`, `Bool`, `Vec{N}` or `Mat{N,M}` (M4 adds `Power{Planar}`), and defaults to `Real` when omitted.
- Port types: `Power{Domain}`.
- Attributes:
  - `unit`, `min`, `max`, `tunable`, `description`, `nominal`, `state`, `options` (D11);
  - `structural` (constants only, implied).
- Defaults are constant expressions: literals, `@constants`, other parameters, and whitelisted pure functions. They are evaluated at instantiation by a small constant-folding interpreter, never by `eval`.

### 4.4 Block-level checks (fast pass, `block.check`)
- E000 to E006 and W204.
- Name resolution (E003). Names are local; `t` is predefined; ports give `p.e` and `p.f`. Shadowing a whitelisted function gives E003 with "shadows built-in".
- Type checking (E004). Bool only in conditions and logic. Int only in discrete code, indices and constants. Real to Int never happens implicitly.
- Sizes (E005). Static indices must be in range, and `for i in 1:N` needs `N` constant.
- Units (E006). See 5.3.
- Per-block balance precheck (E103 at block level, reported as a warning when the block is checked alone). The rule:
  - `#equations = #variables + #outputs + #powerports`;
  - counting scalars, with Vec/Mat expanded;
  - `ddt(x)` does not count as an unknown;
  - discrete-scope variables are excluded;
  - `if` equations count their branch;
  - `for` loops are unrolled.

  Worked counts:
  - `C`: q, plus port p, gives 2 equations. ✓
  - `GearBacklash`: phi, w, T, plus ports a and b, gives 5. ✓
  - `PIController`: x, plus output u, gives 2. ✓

---

## 5. Julia library `BGSim` (compiler and simulator)

### 5.1 Internal IR
- `BlockDef`: the parsed and checked block. It holds:
  - name, ref and source;
  - its declarations, the equations/initial/discrete/events AST;
  - causality, components and connections;
  - the interface (as in the catalog).
- `ModelDoc`: the parsed model JSON.
- `FlatModel`: the output of flattening. It holds:
  - scalarized variables `FlatVar(id::String, kind, type, unit::Dims, start, attrs, origin::Origin)`, where `Origin` is the instance path, block ref and source range;
  - parameters (with values);
  - continuous equations (`FlatEq(lhs, rhs, origin)`, in our AST form with fully qualified names);
  - initial equations;
  - events;
  - discrete partitions;
  - the bond graph (for SCAP);
  - the connection metadata (for the editor).

### 5.2 Instantiation and flattening (`instantiate.jl`, `connect.jl`, `junctions.jl`)
1. Resolve each node's block: stdlib, project or inline. Parse and cache it by source hash.
2. Bind constants: the defaults first, then the instance overrides. This fixes every size.
3. Expand subsystems recursively. Prefix names with the path.
4. Bind parameter expressions. In the model JSON, parameters are expression strings. They are parsed with the same front end (as an expression in a "defaults" scope) and may reference model-level parameters (a later feature) or literals. Bad expressions give E001 to E003, pointing at node and parameter.
5. Generate the connection equations (5.5) and the junction equations (5.4).
6. Unconnected inputs give E101. Unconnected power ports give E101 too, with the hint "connect it or add a source (Se/Sf, Fixed, Ground)". Unconnected outputs are fine.
7. Model-level balance check (E103). When it fails, rank the blocks by local imbalance and name the worst.

### 5.3 Units (`units/`)
- `Dims`: an integer exponent vector over (m, kg, s, A, K, mol, cd) plus a Float64 scale.
  - Derived units: N, J, W, V, Ohm, F, H, Pa, bar, Hz, rpm, rad (dimensionless), deg (scale π/180), mm, cm, g, min, h, L.
  - The parser handles `*`, `/`, `^` with integer exponents, and parentheses.
- Pseudo-dimensions `effort` and `flow` (D9) are two extra symbolic slots, substituted after domain adoption.
- Checking:
  - `+ - ~` and comparisons need equal dimensions;
  - `* /` add or subtract exponents;
  - `^` needs an integer literal exponent;
  - functions need dimensionless arguments, except `abs sign min max clamp hypot` (same dimension in and out) and `sqrt` (halves the exponents).
- Variables and parameters without a unit are **wildcards**. This is not inference; a wildcard term skips the check.
- Signal connections:
  - the same dimension with a different scale inserts a factor, returned as `unitFactors` for the editor badge;
  - different dimensions give E102 (spec: "Units").

### 5.4 Junctions
- 0 and 1 junction nodes get ports `p1` to `pn` in connection order. Every bond between a junction and an element defines the bond variables `(e_b, f_b)`.
- Signs: for a junction, `s_i = +1` if bond i points **into** the junction, otherwise `-1`.
  - 0-junction: all `e_b` are equal, and `Σ s_i f_b,i = 0`.
  - 1-junction: all `f_b` are equal, and `Σ s_i e_b,i = 0`.
- Junction-to-junction bonds are allowed; they are ordinary bonds.

### 5.5 Connection semantics (D7, D8)
- **Bond** (direction from X to Y, so power flows X → Y): `Y.e = e_b`, `Y.f = f_b`, `X.e = e_b`, `X.f = -f_b`.
  - Port variables are always defined with power positive *into* their element (spec).
  - The editor only creates bonds when at least one end is `Generic` or a junction.
- **Wire node** (2 or more concrete-domain power ports, found by union-find over wire connections, all in one domain): the across variables of all ports are equal, and `Σ through = 0`.
  - Across is `e` for Electrical and Hydraulic, and `f` for Translation, Rotation and Planar (component-wise for `Vec{3}`).
- **Signal:** `input = output` per input. An input with two sources gives E102 ("an input has exactly one source").
- **Mixed:** a bond between a Generic port and a concrete iconic port is a bond (the rule above). Its Generic side adopts the concrete domain.

### 5.6 Domain adoption (`domains.jl`)
- Union-find over every bond and junction island. Each island collects the concrete domains it touches:
  - 0 domains: dimensionless `Generic` (W205);
  - 1 domain: adopted;
  - more than 1: E102, naming the two ports.
- The adopted domain gives units to the Generic ports and substitutes `effort` and `flow` in the block units (D9).
- The result goes back to the editor as `domains`, which colours the bonds.

### 5.7 Causality (SCAP, `causality.jl`)
- Runs on the bond graph part (junctions, Generic elements and bonds) before lowering.
- Standard SCAP:
  1. fixed (Se, Sf, Ground-like) with propagation;
  2. preferred integral causality on C and I with propagation;
  3. arbitrary causality on remaining free R ports with propagation.
- Propagation rules:
  - 0-junction: exactly one bond imposes effort on the junction;
  - 1-junction: exactly one bond imposes flow;
  - TF: effort in on one side means effort out on the other;
  - GY: both sides are effort-out or both effort-in.
- Results:
  - a storage element forced into derivative causality gives **W201**;
  - a conflict on a fixed element gives **E106**;
  - a loop of free elements that needed an arbitrary choice gives **W202** ("algebraic loop through R1, R3").
- The stroke position for each bond is returned to the editor. The causal stroke sits at the end of the bond where effort is the **input** to that element.
- After `mtkcompile`, every variable that appears under `ddt` but was not kept as a differential state is also reported as W201 (this covers iconic models), with the origin path.

### 5.8 Lowering to ModelingToolkit (`lower/mtk.jl`)
- Use MTK ≥ v10:
  - `using ModelingToolkit: t_nounits as t, D_nounits as D`;
  - create variables programmatically (`only(@variables $(Symbol(name))(t))` or the documented equivalent) and keep a `Dict{String, Num}` from our signal ID to the symbolic variable. **Never parse MTK's generated names.**
- Map the AST to Symbolics: whitelisted functions come from `fnmap.jl`, `ddt` becomes `D`, `int(x, x0)` becomes a new state, and `ifelse` becomes `ifelse`. Nonsmooth functions that Symbolics cannot handle are rewritten into `ifelse` forms.
- Intrinsics (`interp1`, `interp2`, `noise_normal`) are registered with `@register_symbolic`. Each has a plain-Julia implementation that does not allocate.
- Build the system:
  ```julia
  System(eqs, t, vars, pars; name=:model, continuous_events=..., initialization_eqs=...)
  ```
  then `mtkcompile(sys)`, then `ODEProblem(sys, op, (t0, t1))`.
- Solvers:
  - `"auto"` means `Rodas5P()` when the system has a mass matrix or algebraic equations, and `Tsit5()` otherwise;
  - the user can also pick `FBDF`, `Rodas5P`, `Tsit5` or `Vern7`.
  - Depend on the split OrdinaryDiffEq sub-packages (`OrdinaryDiffEqRosenbrock`, `OrdinaryDiffEqTsit5`, `OrdinaryDiffEqBDF`, `OrdinaryDiffEqVerner`) to keep load time down.
- **Nonsmooth events** (spec): collect the switching conditions from every `ifelse`, `abs`, `sign`, `min`, `max`, `clamp`, `floor`, `ceil`, `round`, `saturate` and `deadzone` in continuous equations. Add each as a condition-only continuous event (`c ~ 0`, no affect) so the integrator lands on the switching instants.
- **`@events`:** `cond => begin ... end`. `cond` is a real expression or a comparison `a < b`, normalized to `c = b - a`. It fires on the upward crossing of `c` only (spec).
  - Lower to a `SymbolicContinuousCallback` with the affect on the rising edge only. Probe the MTK API for one-directional events (`affect_neg`) before you use it.
  - `reinit(x, v)` becomes the affect equation `x ~ v` evaluated with `Pre(...)` values.
  - Affects that also touch discrete variables use MTK's imperative/functional affect. Probe the API first.
- **Compile cache:** key it on the structural hash (block sources, constants, topology, settings that affect structure). Parameter values and start values are **not** part of the key. On a hit, reuse the compiled system and the problem through `remake(prob; u0, p)` (D4).
  - Measure this: a parameter-only re-run of the DC motor model must start simulating in under 300 ms when warm.

### 5.9 Discrete scheduler (`sim/scheduler.jl`, D3)
- Each `@discrete Ts = …` partition becomes a generated Julia function. It is produced from our validated AST (so it is not user `eval`) through `RuntimeGeneratedFunctions` or `eval` into a private module.
  - Signature: `step!(dstate, inputs, params, t)`.
  - It writes `dstate`, and the held outputs live in `dstate`.
- **Times as integer nanoseconds.** `Ts` and `offset` are converted exactly. When `Ts * 1e9` is not an integer within 1e-6, report E104 with the hint "use a period that is a whole number of nanoseconds". The base tick is the gcd.
- Held discrete outputs that continuous equations read are **MTK parameters**: `discrete parameters` that are never folded. Continuous values that discrete code reads are fetched with `SymbolicIndexingInterface.getu(sys, syms)` getters, built once.
- The run loop:
  ```julia
  integ = init(prob, alg; tstops = all_tick_times_in_span, ...)
  while integ.t < t_end
      step!(integ)
      if integ.t is a tick time
          # 1. sample  2. run due partitions in topological order
          # 3. write held outputs through setp(sys, params) on integ
          # 4. u_modified!(integ, true)
      end
      # record; check cancel flag; emit progress
  end
  ```
- Order of partitions:
  - topological over the signal connections between discrete partitions;
  - a cycle that is not broken by `previous(x)` gives **E105**, naming the cycle.
- `previous(x)` reads the value from before this tick; `hold(x)` samples a continuous signal explicitly.
- Recording uses an output grid (`saveat`-like, done by our own loop with `integ(t)` interpolation), plus each event and each tick that changes a held output, recorded as left and right values.
- Golden tests:
  - multi-rate (1 ms and 5 ms) with a known integer sequence;
  - a ZOH with exact values;
  - E105 detection;
  - `previous` breaking a cycle.

### 5.10 Recorder (`sim/recorder.jl`)
- Builds one `getu` getter for all recorded symbols: states, observed values, port variables, discrete values.
- Appends rows to `stream.f64`, using a buffered write and flushing at least every 100 ms. At the end it writes `columns.f64` and `manifest.json`.
- Unknowns removed by `mtkcompile` are still reachable as observed values (spec: "the compiler retains every bound signal as an observable").

### 5.11 Diagnostics (`diagnostics.jl`)
- One constructor per code. Each diagnostic always carries `origin` (path, ref, range), the code and the message, plus a hint where possible.
- MTK exceptions are caught and mapped:
  - `ExtraEquationsSystemException` or `ExtraVariablesSystemException` become E103, after our own precheck failed to find the cause;
  - singular initialization becomes E103 with "initial conditions inconsistent";
  - anything else becomes E900, with the exception text in `hint` and the path of the most recently touched block.
- Solver `retcode`s other than Success become E901, with `t` and the 5 states with the largest magnitude.

### 5.12 Performance targets (Julia, warm worker)
| Item | Target |
| --- | --- |
| `block.check` on a 40-line block | < 150 ms |
| `model.check` on a 60-element model | < 1.5 s |
| First run of the DC motor (compile + sim 1 s) | < 10 s |
| Parameter-only re-run | < 300 ms to first data |
| Worker cold start to `ready` | Measure it and record it in STATUS. Try to get it under 60 s using a PrecompileTools workload. |

### 5.13 Debugging (`sim/debug.jl`, `sim/hooks.jl`, `sim/watch.jl`, `sim/edits.jl`, `compile/explain.jl`; M5)
Debugging is part of the simulator, not a separate tool. A debug run is a normal run (5.8 to 5.10) with a debug context attached. Decisions D20 to D27, protocol 3.8.

**Debug context.** Each debug run has a `DebugCtx`: the command channel, the atomic pause flag, the breakpoint table, the step mode, the watch pool, the edits list and the last `PausedInfo`. The scheduler loop of 5.9 gets checkpoints:
```julia
while integ.t < t_end
    step!(integ)
    dbg_after_step!(ctx, integ)          # pause flag, solverStep stepping, runTo, events, exceptions
    if integ.t is a tick time
        sample(...)
        run_partitions!(...)             # the debug variant calls dbg_hook! at statements
        dbg_after_tick!(ctx, integ)      # tick stepping
    end
    record(...); check cancel; emit progress
end
```
`dbg_pause!` flushes the recorder, sets the manifest status to `paused`, sends `debug.paused`, and blocks on `take!(ctx.commands)`. Evaluate, values, breakpoint and edit commands are answered while the run stays paused; continue, step and cancel release it.

**Statement hooks (D20, D21).** In the debug variant, the partition generator of 5.9 emits this before every statement:
```julia
if ctx.armed[k] | ctx.stepping
    dbg_hook!(ctx, k, (; y, v, xhat, z))  # k indexes a static table: path, ref, scope, range
end
```
- The NamedTuple of locals (the declared names in scope plus the D18 temporaries assigned so far) is built only when the hook fires.
- `ctx.armed` is a `BitVector` indexed by hook. `debug.setBreakpoints` resolves a line breakpoint `(ref, line, path)` to the hooks of every instance of that block (or of the one `path`). If the line holds no statement, it reports E401. If no instance uses the block, it reports W401 and `verified = false`.
- Conditions are parsed in the frame scope and compiled once by the generator; user text is never `eval`ed. Hit counts are kept per breakpoint.
- Step `statement` pauses at the next hook of any partition. Step `tick` pauses after the next tick's partitions have run.
- Event breakpoints (D21): pause after an integrator step in which an `@events` condition fired. Detect this with the mechanism J2.3 uses to record events (left and right values). The `location` is the event's `cond` range.

**Watch pool (D22).** One `VectorContinuousCallback` with 16 slots is passed to `init` together with the callbacks MTK put into the problem. Probe how `init` merges a `callback` keyword with the problem's callbacks, and record it in NOTES.md.
- Slot i evaluates `c_i(u, p, t)`, built from the watch AST with `SymbolicIndexingInterface.observed(sys, expr)`. A disabled slot returns `1.0`.
- The affect pauses with reason `breakpoint` only when the slot is enabled and the crossing is upward.
- Adding, changing or removing a watch while paused must never cause a spurious pause. A 17th watch is refused with "at most 16 watch breakpoints".
- Time breakpoints and `runTo` use `add_tstop!`. Exception breakpoints pause before the run ends on E901 or W206, so the state at failure can be inspected.

**Edits, replay and branch (D24, D25).**
- `setParameter` applies `setp(sys, name)(integ, value)` and `u_modified!(integ, true)`, then appends an `Edit` and rewrites the manifest's `debug.edits`.
- `setState` first checks that the name is a differential state and that the system has no algebraic equations (E402 otherwise).
- `run.replay` builds a normal run whose loop applies each edit at its `t`, through `add_tstop!` and the same calls.
- `run.branch` replays the parent's edits before `t`, pauses at `t`, and records `parentRun` and `branchAt`.

**Determinism requirements** (tested in J5.1 to J5.4):
- A debug run with no breakpoints writes a `columns.f64` that is bit-identical to a normal run of the same model.
- Pausing at line breakpoints, ticks, solver steps, events or `debug.pause` and then continuing does not change the results either.
- A watch pause adds an integrator step at the located crossing, and a time breakpoint or `runTo` adds a tstop. Results after them match a normal run within the solver tolerances, not bit for bit.
- A replay reproduces an interactive session's `columns.f64` bit for bit when its edits were made at tick, statement, step, time or pause-request pauses, and within the solver tolerances when they were made at a watch pause.

**Explain (`model.explain`).** It needs no run; it uses the compile cache (J2.8). For one signal ID it returns:
- its kind after `mtkcompile`: differential state, algebraic unknown, observed, alias, parameter, or discrete held output;
- for observed and alias signals, the defining expression from `observed(sys)`, rendered with our signal IDs (through the reverse of the `Dict{String, Num}` of 5.8);
- the source equations that mention it, with their origins (`FlatEq.origin`);
- the W201 and W202 findings that involve it.

**Targets (warm worker).**

| Item | Target |
| --- | --- |
| Debug run with no breakpoints, wall time | ≤ 1.3 × a normal run (dc-motor, drivetrain-kalman) |
| `debug.pause` to `debug.paused` | < 100 ms |
| `debug.step` (tick) round trip | < 50 ms |
| `model.explain` | < 300 ms |

---

## 6. Python backend (`backend/`)

- Create it with `uv init --package bgsim-server`, then `uv python pin 3.13`.
- Dependencies: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `numpy`, `watchfiles`; later `trimesh` (M3) and `scipy` (examples).
- Dev dependencies: `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `datamodel-code-generator`.
- Entry point `bgsim` (`[project.scripts]`) starts uvicorn on `127.0.0.1:8765` and serves `web/dist` at `/` when it exists.
- `worker.py`:
  - spawns `julia --project=<repo>/julia/BGSim --threads=2 -e "using BGSim; BGSim.Worker.main()"`; the executable comes from the `BGSIM_JULIA` env var, or `julia` on PATH;
  - async TCP framing, request and response correlation, a notification fan-out (asyncio queues per run);
  - a health state machine, auto-restart with backoff, and the request timeouts (`block.check` 5 s, `model.check` 60 s, runs unlimited).
  - `BGSIM_FAKE_WORKER=1` replaces it with a fixture-driven fake. The fake makes runs by writing a synthetic `columns.f64` (sines and steps) with real timing, so the UI can develop on its own.
- `decimate.py`:
  - opens the run files with `numpy.memmap`;
  - selects `[t0, t1]` by `searchsorted`;
  - returns per-pixel-bucket min/max plus the first and last points, vectorized through `np.minimum.reduceat` and `np.maximum.reduceat`. Event duplicates must be kept.
  - Target: 1e7 points × 10 signals in under 50 ms.
- `stream.py`: the spec stream (handshake plus 60 Hz binary frames). For live runs it follows the `stream.f64` tail.
- `projects.py`: safe path handling (no `..`), atomic writes (temp file plus `os.replace`), validation with the generated pydantic models, and "create from example", which copies `examples/<name>`.
- `meshes.py` (M3): trimesh loads STL, OBJ or DAE and exports GLB into `<project>/meshes/`.
- `debug.py` and `fake_debug.py` (M5): the debug endpoints of 3.8, and debug runs in the fake worker so the web lane can develop without Julia.
- Tests:
  - pytest for every endpoint, using the fake worker;
  - one marked `@pytest.mark.julia` integration test that runs the real worker on the RC fixture. It is skipped by default and run by `tools/check.py --lane x`.

---

## 7. Web application (`web/`)

### 7.1 Stack (versions pinned exactly; copy the HMI's where they overlap)
- Copy these from `D:\CtrlX Agentic Machine Control\framework\hmi\package.json`:

  | Package | Version |
  | --- | --- |
  | `react`, `react-dom` | 19.3.0 |
  | `zustand` | 5.0.15 |
  | `@babylonjs/core`, `@babylonjs/loaders` | 9.28.0 |
  | `vite` | 8.3.1 |
  | `@vitejs/plugin-react` | 6.1.1 |
  | `typescript` | 6.0.3 |
  | `vitest` | 5.0.2 |
  | `@testing-library/react` | 16.3.3 |
  | `jsdom` | 29.1.1 |
  | `@playwright/test` | 1.63.0 |
  | `eslint` | 10.11.0 |
  | `typescript-eslint` | 8.70.1 |
- Added. Pin the latest stable version at install time (`npm view <pkg> version`) and record it in STATUS:
  - `@xyflow/react` (graph canvas);
  - `uplot` (charts);
  - `@codemirror/view`, `@codemirror/state`, `@codemirror/language`, `@codemirror/lint`, `@codemirror/autocomplete`, `@codemirror/legacy-modes` (Julia mode);
  - `react-resizable-panels`;
  - `immer`;
  - `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono`;
  - dev: `json-schema-to-typescript`.
- Vite dev server proxies `/api` and `/ws` to `127.0.0.1:8765`.

### 7.2 Layout
```
┌ Top bar: project ▸ model tabs │ ▶ Run ■ Stop │ t_end, solver, tol │ status: worker/compile/progress ┐
├──────────────┬──────────────────────────────────────────────────────┬─────────────────────────┤
│ Library      │  Center tabs: [Diagram: Plant ▸ Motor1] [Code: PI.jl] │ Inspector               │
│  (search,    │  Canvas (xyflow) with breadcrumbs for subsystems     │  name, block, params    │
│  groups,     │                                                      │  (units, min/max, desc),│
│  drag to add)│                                                      │  ports, starts,         │
│ Model tree   │                                                      │  "Open source", "Copy   │
│  (outline)   │                                                      │   to project library"   │
├──────────────┴──────────────────────────────────────────────────────┴─────────────────────────┤
│ Bottom dock tabs: Plots (n panels) │ 3D View │ Diagnostics (badge counts) │ Signals │ Log        │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```
- All splitters are resizable, and the layout persists in `localStorage` (wrapped in try/catch).
- The 3D view can also be popped into the centre tab area.

### 7.3 Visual language (domains, ports, bonds)
- **Domain colours** are CSS custom properties in `src/theme/tokens.css`, with light and dark variants:

  | Domain | Colour |
  | --- | --- |
  | Electrical | blue `#2F6FDE` |
  | Translation | green `#2E9E5B` |
  | Rotation | violet `#7A5AF8` |
  | Hydraulic | cyan `#0EA5C6` |
  | Planar | brown `#8D6E63` |
  | Generic, unresolved | grey `#6B7280`, **dashed** |
  | Real signal | ink, 1.25 px, with an arrowhead |
  | Bool signal | dashed |
  | Int signal | dotted |

  Error `#D92D20` and warning `#F79009` are reserved and never used for domains. Colour is never the only cue: each port also shows a domain letter (E/T/R/H/P/G) on hover, and the legend is in the canvas corner.
- **Port glyphs:**
  - power port: a filled square;
  - signal input: a hollow triangle pointing in;
  - signal output: a filled triangle pointing out;
  - vector ports are drawn with a double outline.
- **Bonds:**
  - straight or polyline;
  - a half arrow at the `to` end (power direction);
  - a causal stroke (a perpendicular bar) at the end given by `model.check`;
  - the colour of the adopted domain;
  - hovering shows the e/f names, units and the values at the plot cursor time.
- **Junctions:** small circles labelled `0` and `1`. Bonds attach floating to the circle edge.
- **Iconic components:** SVG schematic symbols in `src/editor/icons/`, one per catalog `icon` id. They include:
  - resistor, capacitor, inductor, ground and sources;
  - mass, spring, damper, fixed and friction;
  - inertia, gear, motor ("M" in a circle) and sensors;
  - orifice, cylinder and tank.

  Bond graph elements render as their letters (`C`, `I`, `R`, `Se`, `MSf`, …) in a serif font, the classic look. Wires route orthogonally, and a dot marks every node with 3 or more ports.
- **Unit factor badge** on a signal wire, for example `×0.001` (from `unitFactors`).
- **Dragging a connection:**
  - compatible ports highlight and incompatible ports fade;
  - dropping on an incompatible port shows a tooltip with the reason: "Electrical port cannot connect to Rotation; use a converter (DC motor, EM converter)", "Input u already has a source", "Bool cannot connect to Real; insert a Type conversion".
  - These rules are a TS port of 5.5 and 5.6 (kind, domain, type, size, single source). The backend still re-checks them (E102).
- **Errors on the canvas:** the element gets a red or amber outline and a badge with its count. Hovering lists the messages. Clicking a diagnostic in the panel selects and pans to the element, or opens the code tab at the line.
- **Live feedback loop:** after every edit (debounced 400 ms) the app calls `POST /api/check/model`. It updates domains, strokes, unit badges and diagnostics, and the canvas never blocks. While the worker is warming, a non-intrusive status shows instead.

### 7.4 Editing features
- Drag from the library. Double-click an element to open its parameters (inspector focus). Double-click a subsystem to enter it.
- Rotate (R), flip (F), delete (Del), copy/paste (Ctrl+C/V, with renaming), and multi-select.
- Bonds can be reversed from the context menu ("Reverse bond direction").
- **Undo/redo** (Ctrl+Z / Ctrl+Y): every document mutation is an immer-producing command in the zustand store, with patches kept on a history stack of 200. This is designed in M1, not bolted on later.
- **Create subsystem from selection:** the cut connections become subsystem ports.
- **Equation block and Discrete code block:** a node whose source is inline. Double-click opens a CodeMirror tab, its interface (ports) updates from `block.check`, and connections to ports that were removed turn red (E101).
- **Copy to project library:** forks a stdlib block into `library/<Name>.jl`, opens it in the code editor, and re-points the instance (the spec's "copy the element and edit its equations").
- Auto-save is a debounced PUT, plus an explicit "Saved" indicator. A dirty model is marked in its tab.

### 7.5 Plotting (performance-critical)
- **Signal browser:**
  - a tree by instance path, with search;
  - kinds are shown by icon (state, algebraic, port e/f/P, discrete, input/output);
  - units are shown;
  - drag a signal onto a plot, or double-click to add it to the active plot.
  - The canvas context menu on a port, bond or instance offers "Plot effort / flow / power" and "Plot all outputs".
- **Plot panels:**
  - 1 to n stacked uPlot instances, with time axes linked through `cursor.sync`;
  - one y-axis per unit group (at most 2 per panel, then a new panel is suggested);
  - a legend with values at the cursor;
  - wheel or drag to zoom, double-click to reset;
  - a zoom change re-requests `/data` with `t0`, `t1` and `px = canvas width × devicePixelRatio`;
  - an LRU cache keyed `(run, id, t0, t1, px)`.
- **Live:** while running, subscribe through `/ws/runs/{id}` to the tails of the plotted signals, which are appended to the in-memory series, and auto-scroll unless the user has zoomed.
- **Compare runs:** pin a previous run, and its signals overlay as dashed lines in the same colour.
- **Cursor sync:** the plot cursor time is the global "inspect time". It drives the 3D viewer playback head and the bond hover values.
- Budgets (Playwright perf test): 20 signals × 1e6 points, zoom/pan re-render under 50 ms after the data arrives, and 60 fps while live-streaming 10 signals.

### 7.6 3D viewer: replicate the HMI setup
Copy and adapt these from `D:\CtrlX Agentic Machine Control\framework\hmi\src\viewer\`. Read `README.md` there first.

| Take | From | Notes |
| --- | --- | --- |
| `renderScheduler.ts` | verbatim | On-demand rendering: draw only when invalidated or still moving, never with `runRenderLoop`. Includes `hardwareScaling(dpr, cap=1.5)`. |
| Engine and lifecycle pattern | `Viewer.tsx:125-149, 265-411` | `new Engine(canvas, true, { useHighPrecisionMatrix: true, stencil: true, preserveDrawingBuffer: false, adaptToDeviceRatio: false })`. The engine factory is an injectable `createEngine` prop (for NullEngine tests). One `useEffect` per scene creates engine, scene and scheduler. A `disposed` flag guards async loads (StrictMode-safe). Cleanup disposes the scheduler, the scene and then the engine. A `ResizeObserver` triggers `engine.resize()` and invalidate. If engine creation throws, show "no 3D rendering on this device". `onContextMenu` is prevented, and a non-passive wheel listener stops page scroll. Visibility gating uses `visibilitychange`, an `IntersectionObserver` and the active tab. |
| Scene constructor | `scene.ts:229-264` | `useRightHandedSystem = true`, transparent `clearColor`, `skipPointerMovePicking = true`. `ArcRotateCamera` with `minZ 0.01`, `lowerRadiusLimit 0.05`, `wheelDeltaPercentage 0.02`, `pinchDeltaPercentage 0.004`, `panningSensibility 2000`, and `attachControl(false, true, 2)` (right button pans). A three-light directional rig (key 1.0, fill 0.5, rim 0.8) re-aimed in camera space on every view-matrix change. |
| `fit()`, camera presets, orthographic toggle | `scene.ts:104-109, 856-888` | Iso, top, front and side presets in model (Z-up) coordinates. |
| `toon.ts` | verbatim | A material plugin with a soft three-band ramp. Attach it to all scene materials. |
| Picking | `picking.ts`, `scene.ts:897-919` | Tap ≤ 10 px picks: a ray first, then the nearest projected entity within 24 px. Selection uses `renderOutline` (side-effect import `@babylonjs/core/Rendering/outlineRenderer`). |
| Playback clock and interpolation pattern | `playback.ts`, `timeline.ts`, `PlaybackBar.tsx` | Binary search plus lerp/slerp, held at the ends. `PlaybackClock` (wall time × speed, re-anchored on seek). Live mode delays by 1.5 × the sample interval and never extrapolates. |
| Deep ES-module imports and side-effect imports | `scene.ts:28-30` | `@babylonjs/core/Culling/ray`, `.../Rendering/outlineRenderer`, `@babylonjs/loaders/glTF/2.0/glTFLoader`. Load GLB with `LoadAssetContainerAsync(..., { pluginExtension: ".glb" })`. |
| Tests | `Viewer.test.tsx`, `acceptance.test.ts` | `NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true })`, injected through `createEngine`. Assert that unmount leaves `engine.scenes.length === 0`, and expose `data-state` for e2e. Add a Playwright perf test that counts frames: at most 2 fps when stationary and 0 fps when hidden. |

Don't copy anything PP-02-specific: the sidecar contract, ACS transmissions, closure solver, gripper, roller stripes, carrier labels, collision drafts, ctrlX csys naming, layer registry, glow paths or Data Layer bindings.

**Z-up.** SDF is Z-up and right-handed. Create one root `TransformNode` named `sdf_root` with `rotation.x = -Math.PI / 2`; this maps SDF +Z to Babylon +Y. Parent everything to it. Write a unit test that SDF point (0,0,1) lands at world (0,1,0).

**SDF subset → scene graph** (`src/scene/sdf.ts`, parsed with `DOMParser`):
- `<model>`, nested models, `<link>`, `<visual>` with `<box>`, `<cylinder>`, `<sphere>` and `<mesh uri>` (GLB only), `<material><diffuse>`;
- `<joint type=revolute|continuous|prismatic|fixed>` with `<parent>`, `<child>`, `<axis><xyz>`;
- `<frame>`, and `<pose relative_to>`. Supported `relative_to` values are the parent model frame (the default), a link name and a frame name.
- Poses are `x y z roll pitch yaw`, with `R = Rz(yaw)·Ry(pitch)·Rx(roll)`.
- SDF 1.7+ defaults:
  - a link pose is relative to the model frame;
  - a joint pose is relative to the child link;
  - the axis is expressed in the joint frame.

**Kinematic tree** (the same structure as the HMI's "static frame node, child = pure joint motion"):
- For each joint: `jointFrame` (a TransformNode under the parent link node, with local transform `X_parent⁻¹·X_child·X_childJoint` in the model frame) → `jointMotion` (a TransformNode whose local transform is the joint motion only) → the child link node (local = `X_childJoint⁻¹`).
- Root links hang directly under the model node.
- Unsupported elements produce viewer diagnostics (`E3xx`, below) and are skipped.

**Bindings** (exactly the spec's schema):
- Properties: `position` on joints, `pose` (7 signals) on links and frames, `scale.x|y|z` on visuals, `color` with `colormap` (`heat`, `viridis`, `coolwarm`) and `range` on visuals, and `visible`.
- Validation runs in the browser against the scene and the `signals` list from `model.check`. It reports:
  - `E301` unknown target;
  - `E302` unknown signal;
  - `E303` unit mismatch (rad versus m for joint position);
  - `E304` wrong signal count.
- These use the same diagnostic shape and panel as the model diagnostics.
- **Apply loop:** each frame, take the playback clock (or the plot cursor), binary-search the bracketing samples, interpolate (lerp, or slerp for quaternions), apply `gain` and `offset`, set the properties, and call `scheduler.invalidate()` while playing.
- **Binding editor:** a table (target picker from the scene tree, property, signal picker from the signal browser, gain, offset). Hovering a row highlights the target in 3D.

### 7.7 Code editor
- CodeMirror 6 with the Julia legacy mode, plus an extra highlighter for the scope macros and `~`.
- Lint integration: `block.check`, debounced 300 ms, provides the diagnostics for `@codemirror/lint`.
- Autocomplete: whitelisted functions, the declared names in the current block, the port fields (`p.e`, `p.f`), and units inside `unit = "..."`.
- Read-only for stdlib sources, with a "Copy to project library" banner.

### 7.8 Design quality bar
- Inter for the UI and JetBrains Mono for code and values, both self-hosted through fontsource.
- A 4 px spacing scale, and a dense but calm layout. Light and dark themes are both complete; dark is not an afterthought.
- Empty states have guidance. The start page shows the example gallery with thumbnails and one-line descriptions.
- Every error message tells the user what to do next. Status (worker warming, compiling, simulating with progress t / t_end, done in X s) is always visible in the top bar.
- Keyboard: Ctrl+Enter runs, Esc cancels a drag or leaves a subsystem, `/` focuses library search.
- Accessibility: focus rings, ARIA labels on toolbar buttons, and colour-plus-glyph encoding everywhere.

### 7.9 Debugging UI (M5)
- **Run bar.** A **Debug** button next to Run. F5 starts a debug run, or continues a paused one.
  - While debugging: Continue (F5), Pause (F6), Step statement (F10), Step tick (F11), Step event and Step solver step (in a menu), Run to time (a number field), Stop (Shift+F5).
  - The status reads, for example, "Paused at t = 0.4123 s: LQGController line 14 (Ctrl)".
- **Code editor gutter** (the CodeMirror of W2.1):
  - click the gutter, or press F9 on the current line, to toggle a line breakpoint;
  - a filled marker is verified; a hollow one is unverified, and hovering it shows the W401 or E401 message;
  - right-click edits the condition and the hit count;
  - at a statement pause, the code tab opens at the location, highlights the line, and shows the instance path in its title;
  - stdlib sources accept breakpoints, although they are read-only.
- **Debug dock tab** (bottom dock, next to Diagnostics):
  - *Variables:* the frame (locals, held outputs, `previous` values) at a statement pause, and the selected instance's signals at any pause;
  - *Watch expressions:* re-evaluated at every pause through `debug.evaluate`;
  - *Breakpoints:* all breakpoints with enable toggles and kind icons, the use of the 16 watch slots, and the "break on" switches (events, solver failure E901, event limit W206);
  - *Edits:* the changes made in this session, with "Replay" and "Save parameters to model".
- **Creating watches.** The context menus of the signal browser and the canvas (port, bond, instance) offer "Break when…". It opens a small dialog with a signal, a comparison and a value, and writes the watch expression. An "Advanced" field accepts any watch expression, with completion.
- **At a pause:**
  - plots show the data up to the pause with a vertical "paused" marker, and the inspect time (plot cursor) jumps to the pause time;
  - bond and port hover values and the 3D view follow the inspect time, so they show the paused state without changes to the editor or viewer code;
  - the inspector edits parameters in **live mode**: a change is sent as `setParameter` and listed under Edits, and it is written to the model document only through "Save parameters to model";
  - the plot context menu offers "Rewind to here", which starts a branch run at the cursor time.
- **Explain.** "Explain signal" in the signal browser, the bond hover and the inspector opens a popover with the `model.explain` result. Source origins are links that open the code tab at the line.
- Breakpoints persist per model in `localStorage` (D26), and everything works without it.

---

## 8. Standard library (what ships when)

All library elements are `.jl` files under `julia/BGSim/stdlib/<group>/`, written in the language. Each one needs:
- a `description` for every parameter;
- a golden test in `julia/BGSim/test/golden/` with an analytic solution, or a reference hand-written as an MTK model, within `rtol 1e-6`.

The spec tables ("Component catalog") give ports and parameters. The release column below is this plan's.

| Group | M1 (walking skeleton) | M2 (rest of the spec v0.1 catalog) |
| --- | --- | --- |
| Bond graph | Se, Sf, MSe, C, I, R, TF, GY, De, Df, junctions 0 and 1 | MSf, MR, MTF, MGY |
| Sources and sinks | Constant, Step, Sine | Ramp, Pulse, Chirp, Time, TimeTable, Noise, Scope (editor-only), Recorder (no-op, decimation ignored) |
| Continuous | Gain, Sum, Integrator, PI (`PIController` from the spec) | Product/divide, Filtered derivative, TransferFunction, StateSpace, First/second order, Lead-lag, PID, Saturation, Dead zone, Rate limiter, Relay with hysteresis, Lookup 1D/2D, Transport delay (`delay` intrinsic: a variable-step implementation using a history buffer with interpolation; flagged as experimental), Switch, Min/max/abs/sign, Math function, Equation block, Subsystem |
| Discrete and logic | none | All the spec v0.1 rows: Unit delay, ZOH, Rate transition, Discrete integrator, Discrete TF, Discrete SS, Discrete PID, FIR/IIR, Quantizer, Counter, Compare, AND/OR/NOT/XOR, Edge detect, SR flip-flop, On/off-delay timer, Type conversion, Discrete code block |
| Electrical | Resistor, Capacitor, Inductor, Ground, VoltageSource (constant and signal) | CurrentSource, Ideal diode, Ideal switch, Ideal transformer |
| Translation | Mass, Spring, Damper, Fixed, ForceSource | Spring-damper, Velocity source, Friction (Coulomb, viscous and Stribeck, smoothed with `tanh(v/v_eps)` when `v_eps > 0`, or an `ifelse` switch otherwise), Hard stop |
| Rotation | Inertia, Torsion spring, Rotational damper, Fixed shaft, Torque source, Ideal gear | Speed source, Rotational friction, Elastic shaft, `GearBacklash`, `LossyGear` and `GearWithBacklash` from the spec (the last as a composite through `@components`) |
| Hydraulic | none | Pressure source, Flow source, Tank, Volume, Orifice (regularized: `Q = Cd*A*sqrt(2/rho) * dp / (dp^2 + p_tr^2)^(1/4)`), plus `VariableOrifice` (area from an input) |
| Converters and sensors | DCMotor, Speed sensor, Angle sensor | EM converter (gyrator), Rack and pinion, Ball screw, Wheel, Hydraulic cylinder (with chamber compressibility: dead volumes plus `A·x`), Position/velocity/acceleration sensor, Force/torque sensor, Voltage/current sensor, Pressure/flow sensor, Power sensor, Export input/output/parameter (the interface markers; an Export input acts as a constant or table source in simulation) |
| Planar (M4) | none | World, RigidBody2D, Revolute2D, Prismatic2D (optional), FixedJoint2D, Gravity is part of the body, PoseSensor2D |

The DCMotor is a composite through `@components` once J2.6 lands. In M1 it is written flat:
- `v = R*i + L*di/dt + k*w_rel`;
- `T = k*i`;
- the rotor inertia `J` and damping `d` sit between `shaft` and `housing`;
- the electrical ports are `p` and `n`, and the Rotation ports are `shaft` and `housing`.

---

## 9. Example models

Each example lives at `examples/<name>/` and holds:
- a project file and models;
- any scene (`scenes/*.sdf`) and bindings;
- a `README.md` (what it shows and what to try);
- an `expected.json` with the acceptance checks, which `tools/check.py --lane x` runs through the real worker.

Design scripts are uv scripts with inline dependencies (`# /// script` with `numpy`, `scipy`), run with `uv run examples/<name>/design/design.py`. They write their gains into the model JSON parameters. Their outputs are committed.

### 9.1 `dc-motor`, milestone M1 (the walking skeleton)
- **Models:**
  - `iconic`: a VoltageSource (12 V Step at t = 0.01 s) drives the DCMotor, whose `n` pin goes to Ground. `housing` goes to a Fixed shaft. The motor's internal damping is set to 0, and a Rotational damper with d sits between `shaft` and a second Fixed shaft, because an unconnected `shaft` would give E101.
  - `bondgraph`: Se(12 V) → 1-junction (R, I_L) → GY(k) → 1-junction (I_J, R_d).
  - M2 adds `speed-control`: a discrete PI (Ts = 1 ms) on the speed sensor, with voltage saturation of ±24 V and a reference step of 100 rad/s.
- **Parameters:** R = 2 Ω, L = 0.5 mH, k = 0.05 N·m/A, J = 1e-5 kg·m², d = 1e-6 N·m·s/rad (the total viscous damping).
- **Checks:**
  - steady state `ω = k·V/(R·d + k²) = 239.81 rad/s` (rtol 1e-4);
  - iconic and bond graph agree (max abs difference < 1e-6 rad/s);
  - speed-control reaches 100 ± 1 rad/s by t = 0.1 s.
- **3D (M3):** a motor can (cylinder) with a rotating shaft and flag, bound to the rotor angle.

### 9.2 `bouncing-ball`, milestone M2 (events)
- **Model:** an equation block written as follows. `t_end = 3.5 s` stays before the Zeno point at about 4.06 s, and `event_limit` gives W206 when it is exceeded.
  ```julia
  @block Ball begin
      @parameters begin
          g::Real = 9.81, [unit = "m/s^2"]
          e::Real = 0.8, [min = 0, max = 1, description = "restitution"]
      end
      @variables begin
          h::Real = 1.0, [unit = "m"]
          v::Real = 0.0, [unit = "m/s"]
      end
      @outputs height::Real
      @equations begin
          ddt(h) ~ v
          ddt(v) ~ -g
          height ~ h
      end
      @events begin
          h < 0 => begin
              reinit(v, -e * v)
          end
      end
  end
  ```
- **Checks:**
  - first impact at `t1 = sqrt(2/9.81) = 0.45152 s` (abs 1e-6);
  - second at `t1 + 2·0.8·4.42945/9.81 = 1.17396 s` (abs 1e-5);
  - the peak after the first bounce is `0.64 m` (rtol 1e-4).
- **3D:** a sphere whose link pose is bound to `(0, 0, h + r)` with a constant identity quaternion, over a ground box.

### 9.3 `rlc-dual`, milestone M2 (the one-IR principle)
- **Models:**
  - iconic: a series RLC with a VoltageSource step of 1 V.
  - bond graph: Se → 1-junction with R, I and C.
  - Both sit in one model, as two subsystems.
- **Parameters:** R = 10 Ω, L = 10 mH, C = 100 µF, which gives ω0 = 1000 rad/s and ζ = 0.5.
- **Checks:**
  - the capacitor voltages agree within 1e-8;
  - overshoot is 16.3 % ± 0.1 %;
  - SCAP gives integral causality on every storage element, with no W201.
- **What it shows:** causal strokes, adopted-domain colouring (Generic ports turn Electrical blue), and power plots.

### 9.4 `quarter-car`, milestone M2 (Translation, events, tables, copying a library block)
- **Model:**
  - sprung mass `ms = 300 kg`;
  - suspension Spring `ks = 20 kN/m` in parallel with Damper `cs = 1500 N·s/m`, plus a Hard stop at ±0.08 m;
  - unsprung mass `mu = 40 kg`;
  - tire as `OneSidedSpring` with `kt = 200 kN/m`. It is copied from Spring into the project library and edited so that `F = ifelse(x > 0, kt*x, 0)`, which allows lift-off;
  - road as a Velocity source from a TimeTable: +0.5 m/s for 0.1 s at t = 0.5 s, then 0, then −0.5 m/s at t = 1.5 s, giving a 5 cm plateau bump;
  - gravity preload through Force sources.
- **Checks:**
  - the body mode frequency from an FFT of free decay is 1.24 Hz ± 5 %;
  - the wheel-hop mode is about 11.8 Hz ± 5 %;
  - the tire force is never negative.
- **3D:** body and wheel boxes, and springs as scaled cylinders (`scale.z` bound to the deflection, with gain).

### 9.5 `drivetrain-kalman`, milestone M2 (multi-domain, discrete Mat code, KF plus state feedback)
The control-engineering classic. It has three parts.

**Plant**
- DCMotor: R = 1 Ω, L = 1 mH, k = 0.1, J_m = 5e-5.
- IdealGear, n = 10.
- Wheel 1: Inertia J1 = 1e-3.
- The flexible rod, lumped as 3 × ElasticShaft (k_seg = 150 N·m/rad, d_seg = 0.02) with 2 intermediate Inertias of 6.7e-5 kg·m² each. That makes the rod's total stiffness 50 N·m/rad.
- Wheel 2: Inertia J2 = 2e-3.
- A load torque step of −0.5 N·m at t = 1.0 s (Torque source).
- A variant model `drivetrain-backlash` swaps IdealGear for `GearWithBacklash` (gap 0.02 rad).

**Sensors**
- Motor angle → Quantizer (2π/4096) through a discrete sample.
- Motor current sensor.
- No load-side sensor.

**Controller** (one Discrete code block, Ts = 1 ms, all matrices static `Mat`/`Vec`):
```julia
@block LQGController begin
    @constants begin
        nx = 4
        nu = 1
        ny = 1
    end
    @parameters begin
        Ad::Mat{4,4} = ...        # from design.py (literal matrices written into the model JSON)
        Bd::Vec{4} = ...          # single input, so Vec
        Cd::Vec{4} = ...          # single output: y = dot(Cd, x)
        L::Vec{4} = ...           # steady-state Kalman gain
        K::Vec{4} = ...           # LQR state gain
        Ki::Real = ...            # integral gain
        umax::Real = 24.0, [unit = "V"]
    end
    @inputs begin
        theta_m::Real
        w_ref::Real
    end
    @outputs begin
        u::Real = 0.0
        w_load_hat::Real = 0.0
    end
    @variables begin
        xhat::Vec{4} = [0.0, 0.0, 0.0, 0.0]
        z::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        y = theta_m
        xhat = xhat + L * (y - dot(Cd, xhat))            # measurement update
        z += Ts * (w_ref - xhat[4])                      # integral of load-speed error
        v = -dot(K, xhat) + Ki * z
        u = clamp(v, -umax, umax)
        if abs(v) > umax
            z -= Ts * (w_ref - xhat[4])                  # anti-windup: undo integration
        end
        xhat = Ad * xhat + Bd * u                        # time update
        w_load_hat = xhat[4]
    end
end
```
- **Design model** (`design.py`):
  - states `[θ_m', ω_m', θ_L, ω_L]`, motor side reflected through the gear;
  - input voltage, with quasi-static electrics `T = k(V − k·ω_m)/R`;
  - the rod as a single spring of k = 50 to J2;
  - discretized with ZOH at 1 ms;
  - LQR with integral augmentation;
  - steady-state KF via DARE (Q_n from the torque disturbance, R_n from the quantization variance `(2π/4096)²/12`).
  - It writes Ad, Bd, Cd, L, K and Ki into the model JSON. It needs `scipy`.
  - Local variables in `@discrete` (`y`, `v`) are implicitly declared temporaries (D18).
- **Checks:**
  - after the reference step `w_ref = 10 rad/s` at 0.1 s, `ω_L` is within 2 % by t = 0.6 s;
  - after the disturbance, it is back within 2 % by t = 1.3 s;
  - the RMS of `w_load_hat − ω_L` over [0.5, 2] s is below 0.2 rad/s;
  - `|u| ≤ 24` V.
  - The backlash variant only needs to complete without error (it documents a limit cycle).
- **3D:** two wheels (cylinders with spokes) and a rod drawn as 4 segments. Each segment's revolute joint is bound to its node angle, so the twist is visible.

### 9.6 `hydraulic-servo`, milestone M2 (hydraulic domain and converters)
- **Model:**
  - Pressure source 100 bar and Tank 1 bar;
  - a 4/3 valve built in a subsystem from 4 `VariableOrifice` elements (P→A, B→T, P→B, A→T); the area is `A_max·max(±spool, 0)` plus leakage area 1e-9 m², with `A_max = 1e-5 m²`, `Cd = 0.62`, `rho = 850` and `p_tr = 1e5 Pa`;
  - a Hydraulic cylinder: piston 2e-3 m², annulus 1e-3 m², dead volumes 5e-5 m³, bulk modulus 1.4e9 Pa;
  - a Mass of 50 kg with a viscous Damper of 500 N·s/m;
  - a discrete PID (Ts = 1 ms) from position error to spool, saturated to ±1;
  - a reference step of 0.1 m at 0.1 s.
- **Checks:**
  - the position reaches 0.1 ± 0.002 m by t = 1.0 s;
  - the chamber pressures stay within [0, 100.5 bar];
  - no solver failure.
- **3D:** the cylinder body plus a prismatic rod bound to the position.

### 9.6b `industrial-servo`, milestone M2 (requested addition: PMSM servo drive with variants)

A Delta ASDA-A3-style industrial servo (the structure applies to Yaskawa/Panasonic/Siemens
servo drives too; an induction-motor VFD would add slip and flux estimation): a
permanent-magnet synchronous motor with a high-resolution encoder, a sampled cascaded
controller and an inverter. One project, several **variants of the same case** so each
fidelity step can be compared against the baseline:
- **`baseline`** — averaged inverter (ideal voltage source saturated at `V_dc/√3`), PMSM in
  the **dq frame**, rigid inertia, cascaded discrete loops: current PI on `i_d`/`i_q` with
  cross-coupling decoupling and back-EMF feedforward at 8 kHz, speed PI at 1 kHz, position P
  with trajectory feedforward at 200 Hz, one-sample computation delay, ideal encoder.
- **`two-mass`** — baseline plus a flexible coupling (spring/damper) and load inertia, the
  usual mechanical resonance; a speed-loop notch filter and/or low-pass is added to show the
  suppression.
- **`switching`** — baseline with a two-level switching inverter (PWM carrier, dead time and
  device voltage drops) instead of the averaged source; shows current/torque ripple.
- **`encoder`** — baseline with a 24-bit absolute encoder (quantization) and a differenced
  speed estimate (with a low-pass or observer), for low-speed smoothness.
- **`full`** — all of the above together: switching inverter, two-mass mechanics with notch
  filter, and 24-bit encoder quantization with the estimated speed. This is the realistic
  drive model and the one to use for a real bandwidth/ripple/quantization study.

**Plant (continuous):** `v_d = R·i_d + L_d·di_d/dt − ω_e·L_q·i_q`, `v_q = R·i_q +
L_q·di_q/dt + ω_e·(L_d·i_d + ψ_m)`, `ω_e = p·ω_m`, `T_e = 1.5·p·(ψ_m·i_q + (L_d−L_q)·i_d·i_q)`,
`J·dω/dt = T_e − B·ω − T_load`; surface-mount PMSM so `L_d ≈ L_q` and `T_e ≈ 1.5·p·ψ_m·i_q`.
The PMSM is a project-library equation block with signal inputs `v_d`/`v_q` and a Rotation
shaft port; the mechanical plant of the two-mass variant is a bond graph (I–C–R) so the
sample exercises both modeling styles.

**Controller (discrete):** the drive firmware as explicit `@discrete` blocks with their own
`Ts` and a one-sample delay; the cascade is tuned inner-to-outer (current ≫ speed ≫
position), current PI by pole-zero cancellation (`K_i/K_p = R/L`). Add the averaged
inverter limit and, in the variants, the switching/dead-time and encoder quantization.

**Checks (per variant):** current-loop step response (rise/overshoot/settling), speed-loop
step (bandwidth/overshoot/steady error), position step settling, the `V_dc/√3` saturation,
two-mass resonance peak and its notch suppression, switching ripple, encoder quantization
and low-speed smoothness, and a baseline-vs-variant `compare_signals`. The runner will need
a `step_response` check kind (rise time, overshoot, settling) and a ripple measure.

**3D (M3):** a motor can, shaft and a load plate; bind the motor angle to the shaft.

### 9.7 `reaction-wheel-1d`, milestone M3 (1D cube-on-edge balancer, iconic Rotation)
- **Model:**
  - an `InvertedPendulumBody` equation block, copied from Inertia, with:
    ```julia
    J*ddt(w) ~ m*g*l*sin(theta) + a.e + b.e
    ddt(theta) ~ w
    a.f ~ w
    b.f ~ w
    ```
    and `J = 4e-3 kg·m²` about the edge, `m = 0.6 kg`, `l = 0.085 m`, start `theta = 0.05 rad`;
  - the DCMotor `housing` on the body node and `shaft` → wheel Inertia `J_w = 6e-4`, with k = 0.0335, R = 1 Ω, L = 0.1 mH;
  - sensors: the body angle and speed (absolute), and the wheel speed relative to the body (Sum of two Speed sensors);
  - a discrete LQR (Ts = 2 ms) on `[θ, θ̇, ω_rel]` with voltage saturation of ±12 V. `design.py` linearizes the equations analytically.
- **Checks:**
  - `|θ| < 0.2°` within 2 s;
  - the wheel speed stays under 300 rad/s;
  - `|u| ≤ 12`.
- **3D:** a cube rotating about one edge, with a wheel disk inside, bound to θ and to the wheel angle.

### 9.8 `robot-arm-3d`, milestone M3 (RRR arm as an equation block, 3D bindings)
- **`ArmDynamics3R`:** a hand-derived block in Hamiltonian form with point masses. It has three `Power{Rotation}` ports `j1`, `j2` and `j3`, where `port.f = q̇_i` and `port.e = τ_i` (into the arm). The geometry:
  - joint 1: base yaw about world z;
  - joint 2: shoulder pitch, where q2 is the elevation of the upper arm above horizontal;
  - joint 3: elbow, where q3 is relative to the upper arm;
  - point masses m2 at the elbow and m3 at the tip, base yaw inertia Jb.

  The quantities:
  ```
  r_e = l2 cos q2            z_e = l2 sin q2
  r_t = r_e + l3 cos(q2+q3)  z_t = z_e + l3 sin(q2+q3)
  M11 = Jb + m2 r_e² + m3 r_t²,  M12 = M13 = 0
  M22 = m2 l2² + m3 (l2² + l3² + 2 l2 l3 cos q3)
  M23 = m3 (l3² + l2 l3 cos q3),  M33 = m3 l3²
  ∂M11/∂q2 = −2 (m2 r_e z_e + m3 r_t z_t)
  ∂M11/∂q3 = −2 m3 r_t l3 sin(q2+q3)
  ∂M22/∂q3 = −2 m3 l2 l3 sin q3,   ∂M23/∂q3 = −m3 l2 l3 sin q3
  ∂V/∂q2 = g (m2 r_e + m3 r_t),    ∂V/∂q3 = g m3 l3 cos(q2+q3)
  ```
  The equations:
  ```julia
  ddt(q) ~ qd
  p ~ M * qd                                      # p::Vec{3} momenta, M::Mat{3,3} built from the formulas
  ddt(p) ~ tau + dTdq - dVdq
  dTdq[1] ~ 0
  dTdq[2] ~ 0.5 * dM11dq2 * qd[1]^2
  dTdq[3] ~ 0.5 * dM11dq3 * qd[1]^2 + 0.5 * dM22dq3 * qd[2]^2 + dM23dq3 * qd[2] * qd[3]
  ```
  Ports: `tau ~ [j1.e, j2.e, j3.e]` and `[j1.f, j2.f, j3.f] ~ qd`.
  Parameters: l2 = 0.4, l3 = 0.3, m2 = 2, m3 = 1, Jb = 0.05.
- **Drives:** 3 × (DCMotor → IdealGear n = 50). Controller: a discrete PD plus gravity compensation (Ts = 1 ms). The gravity compensation uses `∂V/∂q` from the measured q, in a code block. References come from TimeTables (minimum-jerk point-to-point, generated by `design.py`).
- **Checks:**
  - an energy-conservation test with the motors removed and g = 0 (free motion): the total energy drifts less than 1e-6 relative over 5 s;
  - the tracking error is below 0.01 rad after the moves settle.
- **3D SDF:** base cylinder, upper arm box, forearm box.
  - joint1 axis `0 0 1`;
  - joint2 and joint3 axis `0 -1 0` (positive q raises the arm: rotating +x toward +z is a rotation about −y);
  - each joint's `position` is bound to its q.

### 9.9 `cube-3d`, milestone M3, last example (3D corner-balancing cube, equation block)
- **Body frame:** the axes lie along the cube edges, and the pivot is the corner at the origin. Wheels spin about the body x, y and z axes.
- **States:**
  - quaternion `qw, qx, qy, qz` (body to world), start = equilibrium tilted by 2°;
  - body rates `ω::Vec{3}`;
  - wheel rates relative to the body `wr::Vec{3}`.
- **Parameters:**
  - m = 0.42 kg, side a = 0.15 m;
  - `r = (a/2)·(1,1,1)`;
  - `Θc = Θcm + m(|r|²I − r rᵀ)` with `Θcm = 3e-3·I`;
  - `Θw = 6e-4` per wheel;
  - g = 9.81.
- **Equations** (explicit ODE, no algebraic loop):
  ```
  R(q) from quaternion (explicit 3x3 entries)
  g_b = transpose(R) * [0, 0, -g]
  Lw  = Θw * (ω + wr)                         # wheel momenta (body frame)
  L   = Θc * ω + Lw
  ω̇   = Θc \ ( -cross(ω, L) + cross(r, m*g_b) - T )
  ẇr  = T / Θw - ω̇
  q̇   = 0.5 * Ω(ω) * q                        # standard quaternion kinematics
  ```
  The block has three Rotation ports `m1`, `m2` and `m3`, one per wheel joint, with `mi.f ~ wr[i]` and `T[i] ~ mi.e`. Each is driven by a DCMotor whose `shaft` goes to `mi` and whose `housing` goes to a Fixed shaft. That is correct because the reaction torque on the cube is already inside the block (the `−T` term), and the power `Σ T_i·wr_i` is the motors' mechanical power. Set the motor rotor inertia to 0, since the wheel inertia `Θw` includes it.
- **Equilibrium:** the body diagonal points up. `q0` rotates `(1,1,1)/√3` onto `(0,0,1)`: axis `(1,−1,0)/√2`, angle `acos(1/√3)`.
- **Control** (design.py):
  - linearize numerically by finite differences of a numpy replica;
  - reduced state `[tilt (2: g_b/g projected onto a basis ⟂ n0), ω (3), wr (3)]`;
  - discrete LQR at Ts = 2 ms. Vertical angular momentum is conserved, so its mode is uncontrollable at eigenvalue 1. Solve the DARE on `(A/ρ, B/ρ)` with ρ = 1.0005.
  - Fallback if the design fails its checks: per-axis PD on tilt plus wheel-speed damping, with hand-tuned gains, and relax the check to "balances for 5 s".
- **Checks:** the tilt is below 0.5° after 3 s, the wheel speeds stay under 400 rad/s, and the quaternion norm error stays under 1e-6.
- **3D:** the pivot corner sits at the world origin. The cube link's `pose` is bound to 7 signals: position `(0, 0, 0)` from Constant blocks, plus the quaternion. The cube's visual is offset by `(a/2, a/2, a/2)` inside the link, and the 3 wheel joints are bound to the integrated wheel angles (`int(wr[i], 0)` as outputs).

### 9.10 `robot-arm-planar` and `reaction-wheel-planar`, milestone M4 (planar mechanics)
- Rebuild the 2-link vertical arm and the 1D balancer with the M4 planar components.
- **Cross-checks:**
  - the planar arm matches `ArmDynamics3R` with q1 locked (Jb → ∞, done by holding q1 with a Fixed shaft) within 1e-4 rad over 3 s;
  - the planar balancer matches 9.7 within 1e-4 rad.
- Joint drift: the separation of the joint points stays below 1e-6 m over 5 s.

---

## 10. Milestones and work packages

Each WP is described by these fields:
- **Lane / Depends / Owns**: who does it, what must be done first, and which paths it may change.
- **Deliverables**: what it produces.
- **Acceptance**: the commands and checks that prove it.

### M0: Foundations (mostly sequential; about 5 WPs)

**M0.1 Repo scaffold** · Lane X · Depends: none · Owns: the root files, `tools/`, the skeleton directories
- `git init`; `.gitignore` (`node_modules`, `dist`, `.venv`, `runs/`, `logs/`, `__pycache__`, `*.f64`); `.gitattributes` (`* text=auto eol=lf`).
- `plan/STATUS.md` with a WP table.
- `tools/check.py`: a uv script with `--lane j|p|w|x|all`. It runs:
  - **Julia lane:** `julia --project=julia/BGSim -e "using Pkg; Pkg.test()"`;
  - **Python lane:** `uv run --directory backend pytest -q` and `ruff check`;
  - **Web lane:** `npm --prefix web run typecheck`, `lint`, `test` and `build`;
  - **Examples lane:** example checks plus Playwright e2e;
  - and prints a summary table.
- Acceptance: `uv run tools/check.py --lane all` runs and reports "no tests yet" per lane without crashing.

**M0.2 Contracts v1** · Lane C · Depends: M0.1 · Owns: `contracts/`, `tools/gen_contracts.py`, `backend/src/bgsim_server/contracts.py`, `web/src/contracts/`
- The schemas of section 3: catalog, model, diagnostic, run manifest, worker RPC, stream handshake, bindings.
- Fixtures:
  - `catalog.min.json`, covering the M1 blocks with realistic ports and parameters;
  - `model.dcmotor.json`;
  - `diagnostics.sample.json`, with one of each code;
  - `run.synthetic/`, a manifest plus a generator script for `columns.f64`;
  - invalid fixtures.
- Code generation for Python and TypeScript.
- Acceptance: a pytest validates every fixture (valid ones pass, invalid ones fail); a vitest does the same with `ajv` (dev dependency); the generated code is committed.

**M0.3 Julia package and toolchain proof** · Lane J · Depends: M0.1 · Owns: `julia/BGSim/` (skeleton)
- `Pkg.generate`.
- Add `ModelingToolkit`, `OrdinaryDiffEqRosenbrock`, `OrdinaryDiffEqTsit5`, `OrdinaryDiffEqBDF`, `OrdinaryDiffEqVerner`, `SymbolicIndexingInterface`, `Symbolics`, `JuliaSyntax`, `JSON3`, `StaticArrays`, `PrecompileTools`, `RuntimeGeneratedFunctions` and `Sockets` (stdlib), plus `Test`.
- Record the resolved versions in STATUS.
- `test/runtests.jl` with an **MTK smoke test**: an RC circuit built programmatically (`System` → `mtkcompile` → `ODEProblem` → `solve(Rodas5P())`), compared against the analytic result. A second test reads an `ifelse` and a `continuous_events` bounce through MTK directly. This proves the APIs that section 5.8 relies on.
- Probe and record in `julia/BGSim/NOTES.md`:
  - how to create variables from strings;
  - how to read observed values with `getu`;
  - how to set parameters on the integrator with `setp`;
  - the one-directional continuous events API;
  - the imperative affect API.
- Acceptance: `julia --project=julia/BGSim -e "using Pkg; Pkg.test()"` passes. Record the first-precompile time.

**M0.4 Backend skeleton** · Lane P · Depends: M0.2 · Owns: `backend/`
- uv project, FastAPI app, `/api/health`.
- The worker supervisor with TCP framing, plus a Julia stub `BGSim.Worker.main()` that answers `ping`. The stub goes in `julia/BGSim/src/worker/`; coordinate by having M0.4 own only that file.
- The fake-worker mode.
- `uv run bgsim` serves the API.
- Acceptance: pytest covers the health endpoint and the framing round-trip (fake); the marked test does a real `ping` against Julia.

**M0.5 Web skeleton** · Lane W · Depends: M0.2 · Owns: `web/`
- A Vite React TS app with the pinned versions (7.1).
- Theme tokens (light and dark, domain colours), fonts, and the layout shell (7.2) with empty panels.
- The API client and a health indicator.
- ESLint and Vitest set up, and Playwright set up with one smoke e2e test (the app loads; the health shows fake-worker ready).
- Acceptance: `npm run typecheck && npm run lint && npm test && npm run build` pass; `npx playwright test` smoke passes against `uv run bgsim` with `BGSIM_FAKE_WORKER=1`.

### M1: v0.1, the walking skeleton (DC motor end to end)

**J1.1 Parser and whitelist core** · Depends: M0.3 · Owns: `src/syntax/`, `src/diagnostics.jl`
- Section 4.1 to 4.4 for the scopes `@constants @parameters @inputs @outputs @ports @variables @equations @causality`, with types Real, Int and Bool.
- E000 to E005 and W204.
- Golden parse and check tests for the spec's `C`, `PIController`, `GearBacklash` and `LossyGear`, plus `I`, `R` and `Se`.
- A negative test for every E-code, asserting the exact line and column.
- Acceptance: Pkg.test passes, and there are at least 40 parser and check tests.

**J1.2 Units** · Depends: M0.3 · Owns: `src/units/`
- Section 5.3: parsing, dimensions, the checks and the pseudo-dimensions.
- Hooked into J1.1's checker through a function interface `check_units(block)::Vector{Diagnostic}`; agree on this signature in the WP text.
- Acceptance: tests for 30 or more unit strings, 15 or more E006 cases, and the scale factors mm→m and rpm→rad/s.

**J1.3 Library loader, catalog and M1 stdlib** · Depends: J1.1 · Owns: `src/library/`, `stdlib/` (the M1 rows)
- Write the M1 blocks of section 8.
- `catalog.get` output conforms to `catalog.schema.json`. A test validates it against the schema with the JSON fixtures, by checking structural fields in Julia.
- Acceptance: the catalog has every M1 block; every block passes `block.check` with zero errors.

**J1.4 Flatten, connect, junctions and domains** · Depends: J1.1, J1.2, J1.3 · Owns: `src/ir/`, `src/compile/{instantiate,connect,junctions,domains,balance,pipeline}.jl`
- Sections 5.2, 5.4, 5.5 and 5.6.
- E101, E102 and E103 with paths. W205.
- `model.check` result: diagnostics, domains, signals and unitFactors. Causality is empty until J2.4.
- Acceptance: the fixture models (DC motor iconic and bond graph, RLC both forms) flatten to the expected equation and unknown counts, and 10 negative models give the expected codes on the expected `node` and `connection` ids.

**J1.5 Lowering and simulation (continuous only)** · Depends: J1.4 · Owns: `src/lower/`, `src/sim/{simulate,recorder}.jl`
- Section 5.8 without events and discrete parts, and 5.10.
- Run files (section 3.5), solver selection, cancellation flag, progress, E901.
- Acceptance: the DC motor examples meet the 9.1 checks inside the Julia tests; the `columns.f64` layout round-trips; a parameter-only re-run hits the cache.

**J1.6 Worker protocol** · Depends: J1.5, M0.4 · Owns: `src/worker/`
- The methods and notifications of 3.6. Requests run concurrently (`block.check` while a run is going).
- Logging goes to stderr.
- A PrecompileTools workload.
- Acceptance: the backend's marked integration tests (catalog, `model.check`, and a run end to end producing a manifest) pass.

**P1.1 Projects API** · Depends: M0.4 · Owns: `backend/src/bgsim_server/projects.py` and its tests
- 3.7: projects, models, library and create-from-example.
- Acceptance: pytest covers CRUD, path traversal, atomic writes and schema rejection.

**P1.2 Runs, decimation and CSV** · Depends: M0.4 · Owns: `runs.py`, `decimate.py` and their tests
- Start, cancel, the run WS (phases, progress, live tails), `/data` decimation and CSV.
- Acceptance: decimation is correct against a brute-force reference on random data with spikes, an event duplicate is preserved, and the performance target from section 6 holds.

**W1.1 Library and canvas** · Depends: M0.5 · Owns: `web/src/{library,editor,state}/`
- The library browser from the catalog (fake catalog fixture).
- xyflow canvas: custom node types (block, junction), the port glyphs, icons for the M1 blocks (bond graph letters plus SVG symbols), drag to add, and the three connection kinds with the client-side compatibility rules and refusal tooltips.
- Bond half arrows, reverse bond, delete, move, rotate.
- The zustand document store with immer undo/redo.
- Save and load through the API.
- Acceptance: vitest for the compatibility rules (every rule, with the exact message); Playwright: build the DC motor iconic model by drag-and-drop, save, reload, and see it identical; undo/redo across 10 operations.

**W1.2 Inspector** · Depends: W1.1 · Owns: `web/src/inspector/`
- Parameters with unit, min/max inline validation, description and expression strings. Rename with uniqueness checks. Constants and starts.
- Acceptance: vitest plus Playwright: edit R, then undo it.

**W1.3 Diagnostics panel and canvas markers** · Depends: W1.1 · Owns: `web/src/diagnostics/`
- The panel (filter by severity, group by path), canvas outlines and badges, and click-to-navigate.
- The debounced `model.check` loop. Domain colouring comes from `domains`.
- Acceptance: with the fake diagnostics fixture, each item navigates to its node.

**W1.4 Run controls and Plot v1** · Depends: W1.1 · Owns: `web/src/plot/`, `web/src/app/RunBar*`
- Run, stop, settings and progress.
- Signal browser, one or more uPlot panels, zoom re-fetch and a legend.
- Acceptance: against the fake worker, run, plot 3 signals, zoom, and see the data re-requested with the new `t0`/`t1`.

**X1.1 DC motor example and the M1 e2e** · Depends: J1.6, P1.1, P1.2, W1.1 to W1.4 · Owns: `examples/dc-motor/`, `web/tests/e2e/dcmotor.spec.ts`
- Acceptance: with the real worker, open the example, run it, plot the speed, and the cursor readout at t = 0.2 s shows 239.8 ± 0.1. `expected.json` checks pass.

**M1 gate** (10.3).

### M2: v0.2, complete language, catalog and editor

**J2.1 Language completion** · Depends: M1 · Owns: `src/syntax/`, `src/units/`
- Vec/Mat types and literals, indexing, `for` unrolling, `if` equations with equal counts.
- `ifelse`, the whole function whitelist and the intrinsics table.
- The `@initial`, `@discrete` and `@events` scopes: parsing and checking only.
- The discrete-scope local temporaries (D18).
- Acceptance: a test for every whitelist row (allowed and rejected), and golden checks for `SpeedMonitor`, `LQGController` and `Ball`.

**J2.2 Discrete scheduler** · Depends: J2.1 · Owns: `src/compile/discrete.jl`, `src/sim/scheduler.jl`
- Section 5.9 in full, plus E104 and E105.
- Acceptance: the golden tests listed in 5.9, and a discrete PI against a hand-computed sequence over 10 ticks, bit-exact.

**J2.3 Events and nonsmooth** · Depends: J2.1 · Owns: `src/compile/events.jl` and the event parts of `src/lower/`
- `@events` lowering, nonsmooth condition extraction, event recording (left and right values), and W206.
- Acceptance: the bouncing-ball checks; a relay with hysteresis switching times within 1e-8 of analytic.

**J2.4 Causality (SCAP) and W201/W202/E106** · Depends: M1 · Owns: `src/compile/causality.jl`
- Section 5.7. Stroke positions go into `model.check`.
- Acceptance:
  - the textbook cases: RLC (all integral);
  - two springs in series with no mass between them, giving W201 on one C;
  - an Se–Se conflict on a 0-junction, giving E106;
  - an R–R loop, giving W202.

**J2.5 Units completion** · Depends: J2.1 · Owns: `src/units/`
- The connection unit factors, the Generic substitution after adoption, and the E006 messages naming both units.
- Acceptance: a C on an Electrical bond reports its `c` unit as `F`; mm→m signal wires produce a factor of 0.001.

**J2.6 `@components` / `@connections` and composites** · Depends: J2.1 · Owns: the instantiate/connect extensions
- The textual subsystems from the spec example. DCMotor is rewritten as a composite, and `GearWithBacklash` added.
- Acceptance: the spec's `GearWithBacklash` example compiles and simulates. A model built from the text composite equals the same structure built through model-JSON subsystems, bit for bit on the same solver.

**J2.7a to J2.7g Stdlib completion** (7 parallel WPs, one per group of section 8) · Depends: J2.1, plus J2.2 for discrete, plus J2.3 for the nonsmooth and event blocks · Owns: `stdlib/<group>/` and `test/golden/<group>/`
- Acceptance: one golden test per block; every block passes `block.check` clean; the catalog grows accordingly.

**J2.8 Compile cache and remake** · Depends: J1.5 · Owns: `src/compile/pipeline.jl` (the cache parts)
- Acceptance: the timing target of 5.12 for a parameter-only re-run, and a structural edit invalidates the cache.

**P2.1 Live tails and check fast path** · Depends: M1 · Owns: `runs.py`, `stream.py`
- Live decimated tails of subscribed signals (no more than 20 messages per second), `/api/check/block` with request coalescing (the latest request wins), and run history pruning.
- Acceptance: pytest with the fake worker and a synthetic live run.

**W2.1 Code editor and inline blocks** · Depends: M1 · Owns: `web/src/code/`
- Section 7.7. Equation and Discrete code nodes, copy to project library, and a read-only stdlib view.
- Acceptance: Playwright: type an error, see a squiggle with the code; fix it, and the canvas node's ports update.

**W2.2 Subsystems** · Depends: M1 · Owns: `web/src/editor/subsystem*`
- Create from selection, breadcrumbs, the model tree, and subsystem ports.
- Acceptance: Playwright: group 3 elements and the connections persist; the run results are unchanged.

**W2.3 Domain visual language complete** · Depends: J2.4, J2.5 (contract fields), W1.3 · Owns: `web/src/editor/{edges,ports,legend}*`
- Causal strokes, adopted domain colours, unit badges, hover values at the cursor, and the legend.
- Acceptance: the RLC-dual screenshot test (Playwright `toHaveScreenshot`, with a tolerance) shows strokes on the correct ends.

**W2.4 Plot v2** · Depends: P2.1, W1.4 · Owns: `web/src/plot/`
- Multiple panels, a synced cursor as the global inspect time, multiple axes, compare-runs overlay, live streaming, plotting from the canvas context menu, and CSV export.
- Plus the perf test (7.5).
- Acceptance: the perf budget passes.

**X2.1 to X2.5 Examples** (parallel once the blocks they need exist) · Owns: `examples/<name>/`
- `bouncing-ball`, `rlc-dual`, `quarter-car`, `drivetrain-kalman` (plus `design.py`), `hydraulic-servo`, and `dc-motor/speed-control`.
- Acceptance: each `expected.json` passes through `tools/check.py --lane x`, and each example opens and runs in Playwright.

**X2.6 Example `industrial-servo` (requested addition)** · Depends: J2.2, J2.7c, J2.7e · Owns: `examples/industrial-servo/`, `web/tests/e2e/industrial-servo.spec.ts`
- The variants of section 9.6b: `baseline` (averaged inverter, dq PMSM, rigid inertia, cascaded discrete loops), `two-mass` (compliance + notch), `switching` (PWM/dead time), `encoder` (24-bit quantization + speed estimate), `full` (all of them together). Each has its own expected checks; the runner gains a `step_response` check kind (rise/overshoot/settling) and a ripple measure. Acceptance: every variant's `expected.json` passes and Playwright opens, runs and switches between the variants.

**M2 gate.**

### M3: v0.3, 3D visualization, the remaining examples and polish

**W3.1 Viewer core port** · Depends: M2 · Owns: `web/src/viewer/`
- Section 7.6 table: the scheduler, engine lifecycle, scene, camera, lights, toon, fit/ortho/presets and picking.
- NullEngine tests, plus the perf test (at most 2 fps idle, 0 fps hidden).
- Acceptance: vitest and Playwright perf pass.

**W3.2 SDF parser and scene builder** · Depends: W3.1 · Owns: `web/src/scene/`
- The SDF subset, the Z-up root, the kinematic tree, primitives and GLB meshes, and the scene tree in the outliner.
- Acceptance: unit tests for pose composition (a two-joint chain against hand-computed world matrices, 1e-9 tolerance) and for the Z-up mapping; the fixture SDFs of all examples load.

**W3.3 Bindings and playback** · Depends: W3.2, W2.4 · Owns: `web/src/viewer/bindings*`, `web/src/viewer/PlaybackBar*`
- Binding validation (E301 to E304), the binding editor, the apply loop, the playback bar, and two-way sync with the plot cursor. Live mode through `/ws/stream`.
- Acceptance: vitest for interpolation (lerp/slerp), validation and gain/offset; Playwright: scrub the plot cursor and the 3D joint angle follows.

**P3.1 Stream endpoint and meshes** · Depends: M2 · Owns: `stream.py`, `meshes.py`
- The spec stream format (live and playback), and the GLB conversion.
- Acceptance: pytest on the handshake and frame layout; an STL upload gives a valid GLB.

**X3.1 Scenes for the M1/M2 examples** · Depends: W3.2 · Owns: `examples/*/scenes`, bindings in the models
- Acceptance: each scene loads with zero binding diagnostics.

**X3.2 `reaction-wheel-1d`**, **X3.3 `robot-arm-3d`**, **X3.4 `cube-3d`** · Depends: M2 (X3.4 last) · Owns: `examples/<name>/`
- Acceptance: the section 9 checks.

**W3.4 Polish** · Depends: W3.3 · Owns: `web/src/app/`, `web/src/examples/`
- The start page and example gallery (thumbnails captured by Playwright), keyboard shortcuts, block help (from the descriptions), the empty states, a full dark-theme pass, and an accessibility pass.
- Acceptance: no axe violations at serious level or above on the main screens (`@axe-core/playwright`, dev dependency).

**M3 gate**, including a full manual-style e2e walkthrough script that opens each example, runs it, plots a signal and plays the 3D view.

### M4: stretch, planar mechanics

**J4.1 Planar domain** · Owns: `src/compile/{domains,connect}.jl`, `src/units/`
- `Power{Planar}` with `Vec{3}` e/f in the order (τ, fx, fy) and (ω, vx, vy). These are world-frame components at the port point.
- Component-wise wire nodes, with per-component units.
- A frame-tag check is **not** implemented. Everything is expressed in the world frame, and spatial frame typing waits for the spec's v0.3.

**J4.2 Planar components** · Owns: `stdlib/planar/`
- `World` (twist = 0).
- `RigidBody2D`:
  - parameters m, J, attachment offsets `ra` and `rb` in the body frame, and g;
  - states φ, x_c, y_c, v_c and ω;
  - for each port i: `d_i = R(φ) r_i`, and `port.f = (ω, v_cx − ω d_iy, v_cy + ω d_ix)`;
  - `m v̇_c = Σ F_i + m g`, and `J ω̇ = Σ (τ_i + d_i × F_i)`.
- `Revolute2D`:
  - `parent` and `child` Planar ports, plus a `drive` Rotation port;
  - `ω_c = ω_p + q̇`, a coincident point velocity, and the drive torque applied to the child and reacted on the parent;
  - outputs q and qd.
- `FixedJoint2D`, and `PoseSensor2D`.
- Constraints are at velocity level. The planar arm example measures drift, and the fallback if it is too large is a Baumgarte-style position correction term on the joint.

**X4.1 Planar examples and cross-checks** (9.10).

**M4 gate.**

### M5: debugging (runs after the M3 gate, before the M4 stretch)

M5 was added in plan v1.1, after M4 was numbered; section 0.1 gives the run order. It builds on the scheduler (J2.2), events (J2.3), the compile cache (J2.8), the code editor (W2.1), Plot v2 (W2.4) and bindings and playback (W3.3). Every M5 WP reads sections 3.8, 5.13 and 7.9 and decisions D20 to D27.

**C5.0 Debug contracts** · Lane C · Depends: M3 · Owns: `contracts/`, `tools/gen_contracts.py`, the generated files
- `debug.schema.json` (3.8), the worker methods and notifications of 3.8, and the run manifest additions of 3.5.
- The diagnostic fixtures gain E401, E402 and W401.
- Acceptance: as M0.2 (valid fixtures pass and invalid ones fail in pytest and vitest; the generated code is committed).

**J5.1 Debug run engine** · Lane J · Depends: C5.0 · Owns: `src/sim/debug.jl`, the debug checkpoints in `src/sim/scheduler.jl`
- `DebugCtx`; pause and continue; step `tick`, `solverStep` and `event`; `runTo` and time breakpoints; pause on entry; event and exception breakpoints; cancel while paused; recorder flush and manifest status on pause.
- Acceptance:
  - a debug run with no breakpoints is bit-identical to a normal run (dc-motor, drivetrain-kalman, bouncing-ball);
  - step `tick` advances exactly one base tick (drivetrain-kalman);
  - an event breakpoint pauses at the first bounce of bouncing-ball within 1e-6 of `t1 = 0.45152 s`;
  - cancel while paused ends the run as `cancelled`, with valid run files;
  - the pause latency, step round trip and 1.3 × overhead targets of 5.13 are met.

**J5.2 Statement hooks and line breakpoints** · Lane J · Depends: J5.1 · Owns: the debug variant in `src/compile/discrete.jl`, `src/sim/hooks.jl`
- The hook table, breakpoint resolution (`verified`, E401, W401), conditions, hit counts, step `statement`, and frame capture.
- Acceptance:
  - a breakpoint on an `LQGController` line pauses at every tick of that partition, and the frame's `xhat` equals the value recorded by a normal run at the same tick;
  - in a test block with a tick counter `k`, the condition `k == 5` pauses only at the fifth tick;
  - a breakpoint on an `@equations` line gives E401, and one in a block the model does not use gives W401;
  - continuing through 100 hits leaves `columns.f64` bit-identical to a normal run.

**J5.3 Watch pool, evaluate and explain** · Lane J · Depends: J5.1, J2.8 · Owns: `src/sim/watch.jl`, `src/syntax/watch.jl`, `src/compile/explain.jl`
- Probe first and record in NOTES.md:
  - `observed(sys, expr)` for an eliminated variable, called inside a callback condition;
  - how `init` merges a `VectorContinuousCallback` with the problem's MTK callbacks;
  - `add_tstop!` on a running integrator.
- The `watch` expression scope (`s"..."` signal references, context-relative names), the 16-slot pool, `debug.evaluate`, `debug.values` and `model.explain`.
- Acceptance:
  - a watch on the dc-motor current exceeding 5 A pauses within 1e-8 s of a reference crossing time from a tight-tolerance solve;
  - a watch on a variable that `mtkcompile` eliminated works;
  - adding, changing and removing watches while paused never causes a spurious pause (a randomized test over 50 changes);
  - a 17th watch is refused;
  - `model.explain` on dc-motor reports a state, an observed signal and an alias with correct origins, within 300 ms.

**J5.4 Edits, replay and branch** · Lane J · Depends: J5.1 · Owns: `src/sim/edits.jl`
- `debug.setParameter`, `debug.setState` (E402), the manifest's `debug.edits`, `run.replay` and `run.branch`.
- Acceptance:
  - pause dc-motor with `debug.runTo` at t = 0.2 s, change `R`, continue; replaying that run's manifest is bit-identical to it;
  - a branch at t = 0.1 s matches the parent's rows up to 0.1 s bit for bit, then pauses;
  - `setState` works on a drivetrain-kalman plant state, and gives E402 on a test model with a nonlinear algebraic loop that `mtkcompile` cannot eliminate (check that the compiled system really keeps an algebraic equation).

**J5.5 Worker debug methods** · Lane J · Depends: J5.2, J5.3, J5.4 · Owns: `src/worker/`
- Wire the methods and notifications of 3.8. Debug commands keep working while `block.check` and `model.check` requests run.
- Acceptance: the `@pytest.mark.julia` tests of P5.1 pass against the real worker.

**P5.1 Debug API and fake debugger** · Lane P · Depends: C5.0 · Owns: `backend/src/bgsim_server/debug.py`, `backend/src/bgsim_server/fake_debug.py`, their tests
- The endpoints of 3.8, forwarding of the debug notifications on the run WebSocket, and history pruning that keeps a parent run while its branches exist.
- The fake worker learns debug runs: a scripted run that pauses at line breakpoints on fake ticks, answers `evaluate` and `values` from the synthetic signals, and records edits. The web lane develops against it.
- Acceptance: pytest for every endpoint with the fake; a `@pytest.mark.julia` test that starts a debug run of dc-motor, pauses on a watch, sets a parameter, continues and finishes (it needs J5.5, so the gate runs it).

**W5.1 Debug controls and gutter breakpoints** · Lane W · Depends: P5.1, W2.1 · Owns: `web/src/debug/` (controls and the breakpoint store), `web/src/code/breakpoints*`
- From 7.9: the run bar debug controls and shortcuts, gutter breakpoints with conditions and hit counts, pause location highlighting, and breakpoint persistence (D26).
- Acceptance: vitest for the breakpoint store, including persistence without `localStorage`; Playwright against the fake: set a breakpoint, start debugging, pause at the line, step 3 statements, continue to the end.

**W5.2 Debug panels, watches and explain** · Lane W · Depends: W5.1 · Owns: `web/src/debug/panels*`, `web/src/debug/explain*`
- The Debug dock tab (Variables, Watch expressions, Breakpoints, Edits), "Break when…" from the signal browser and canvas menus, and the Explain popover.
- Acceptance: Playwright against the fake: create a watch from the signal browser, pause on it, see the variables, evaluate an expression, open Explain.

**W5.3 Pause-aware plots and live inspector** · Lane W · Depends: W5.1, W2.4, W3.3 · Owns: `web/src/plot/pause*`, `web/src/inspector/live*`
- The pause marker and the inspect-time jump, live parameter edits (not written to the model unless saved), and "Rewind to here".
- Acceptance: Playwright against the fake: at a pause, the plots end at the pause time with the marker; a live parameter edit appears under Edits and the model document is unchanged; "Rewind to here" opens the branch run, paused.

**X5.1 Debugging walkthrough e2e** · Lane X · Depends: J5.5, P5.1, W5.1 to W5.3 · Owns: `web/tests/e2e/debug.spec.ts`
- Against the real worker:
  1. drivetrain-kalman: a line breakpoint in `LQGController`, inspect `xhat`, step 3 statements, continue to the end;
  2. bouncing-ball: an event breakpoint, change the restitution `e` to 0.6, continue, then Replay, and the replay's results equal the session's;
  3. dc-motor: "Break when" the motor current exceeds 5 A, "Rewind to here" at an earlier cursor time, and Explain on an eliminated signal.
- Acceptance: the spec passes.

**M5 gate** (10.3), with the 5.13 targets recorded in STATUS.

### 10.3 Integration gate (after every milestone)
1. `uv run tools/check.py --lane all` passes, including the Julia tests, pytest, the web typecheck, lint, vitest and build, and the example checks.
2. Playwright e2e passes against `uv run bgsim`, which serves the built web app, with the real worker.
3. Record the performance numbers (5.12, 6, 7.5) in STATUS, and flag any regressions.
4. Write a STATUS summary: what works, known gaps, and the decisions that differ from this plan.

---

## 11. Risks and fallbacks

| Risk | Signal | Fallback |
| --- | --- | --- |
| MTK or OrdinaryDiffEq on Julia 1.13 (resolve or precompile fails) | M0.3 fails | Use juliaup 1.12 with a repo override, and record it. |
| MTK API differs from section 5.8 | Probe scripts in M0.3 | Follow the probe results. NOTES.md becomes the authority for the J lane. |
| Slow cold start (MTK TTFX) | More than 2 min to `ready` | Use a PrecompileTools workload; then optionally build a PackageCompiler sysimage as a separate tool `tools/build_sysimage.py`, never required. The UI shows a warming state and remains usable for editing. |
| `mtkcompile` too slow for the large examples | Over 30 s | Keep the arrays in the arm and cube as scalar equations, and check that MTK keeps array variables unscalarized where possible. As a last resort, use a smaller example size. |
| One-directional events or imperative affects unsupported as assumed | M0.3 probe | Lower upward-only crossing as a two-sided event with a guard in the affect (`if Pre(c_prev) < 0`). For discrete-variable updates, use the scheduler path. |
| Velocity-level planar constraints drift | X4.1 drift check | Baumgarte position correction in `Revolute2D`, or pose-level across variables (Modelica PlanarMechanics style), recorded as a deviation from the spec. |
| Cube LQR design fails | X3.4 | The structured hand-tuned gains in 9.9, with the check relaxed. |
| xyflow cannot draw bonds with causal strokes nicely | W1.1 | A custom edge component rendering SVG paths; xyflow still handles pan, zoom and selection. |
| Windows process quirks (julia alias in WindowsApps, signals) | M0.4 | `BGSIM_JULIA` with an absolute path; cancel through the protocol, not through OS signals. |
| A debug run is not bit-identical to a normal run (M5) | J5.1 acceptance | Find the cause first (an always-installed watch callback is the usual suspect). If the empty watch pool changes stepping, install it only when the run has a watch, and make adding the first watch while paused re-`init` the integrator from the current state, accepting tolerance-level differences after that point. Record the deviation. |
| `init` does not merge an extra callback with MTK's problem callbacks (M5) | J5.3 probe | Build the `CallbackSet` explicitly from the problem's callbacks plus the watch pool, as the probe shows. |
| Events cannot be detected after `step!` (M5) | J5.1 | Pause at the next recorder row after J2.3 records the event's left and right values; the location stays the event's `cond`. |

---

## 12. Out of scope for this session (keep the door open)

Out of scope:
- Target build: `juliac` trimmed library, fixed-step step function, C ABI, FMU, ctrlX Data Layer and SIL sources. Also W203 and the E104 `dt` rule.
- Spatial (SE3) mechanics, frame typing (E007), SDF-to-model import, `pose_of` and `jacobian`.
- Thermal domain, `RS`, `CC`/`II`, state machines, the spec v0.2 hydraulic and electrical components.
- Multi-user, auth, cloud hosting.
- Language migrations (only the version stamp is written).
- Debugging beyond M5: triggered traces on a real controller, lockstep SIL debugging, changing discrete locals or DAE states while paused, in-memory checkpoints for faster rewind, and debugging the BGSim compiler itself (use the standard Julia tools on the worker).

Design choices that keep these open:
- The whitelist table carries a per-row "export-ready" flag for the future target build.
- Discrete partitions are already generated functions with explicit state (D3).
- `@constants` folding is isolated in one pass.
- Signal IDs are the stable interface names that a later export will use.

### 12.1 Post-session roadmap (requested additions)

These are explicitly **not** part of M0–M5; they are recorded so the architecture keeps the
door open.

- **Transfer function between two points.** Select two signals in the same physical domain
  (for example `Motor1/shaft.f` → `Wheel2/a.f`, both rotational speed; or `V1/p.e` →
  `Motor1/i`, both electrical) and compute the small-signal transfer function from the
  first (input) to the second (output): linearize the compiled system at an operating
  point (the global inspect time or the settled steady state), keep that SISO pair, reduce
  it to a rational function, and show gain/phase (Bode) plus poles and zeros. **Same-domain
  restriction (the user's rule):** the two signals must have the same dimension vector;
  a cross-domain pair is refused with a diagnostic naming both units, because the gain
  would mix physical quantities. A same-domain pair such as torque → speed is still a
  meaningful mechanical impedance. Sketch of the seams: J
  `src/compile/transfer.jl` (MTK `linearize` around the operating point, SISO reduction;
  an own polynomial path or ControlSystemsBase for num/den), P
  `POST /api/transfer {model, projectDir, input, output, at}` (or a run-scoped variant
  that reuses the run's operating point), W a "Transfer function" action in the canvas /
  plot context menu and a Bode + pole-zero panel, X an example check (drivetrain motor
  torque → far-wheel speed, analytic two-inertia TF). Deferred because it needs a stable
  operating-point definition, the linearization API, and a rational-function dependency;
  the existing `compile_key`/linearization seam and the recorded signal IDs are the
  pieces that make it a later addition rather than a redesign.
