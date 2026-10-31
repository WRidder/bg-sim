# Dashboard tab: plan and status

A **Dashboard** centre tab (next to Diagram, Code and Docs), in the spirit of a Home Assistant
dashboard: a grid of cards that **show recorded signals** in sync with playback, and cards that
**set block parameters for the next run**. Step 1 is described here; the open points are at the
end.

## 1. Design

### 1.1 Where the dashboard lives

- The dashboard is part of the model document: an optional top-level `dashboard` object in
  `model.schema.json` (`{cards[], autoRerun?}`). It is saved, undone and redone with the model
  (`documentStore.editDashboard`, value gestures coalesce into one undo step).
- The Julia parser and the FMU/C export ignore it. It never changes the equations.
- An input card's value is a **dashboard override**, not a model edit. The block parameter in the
  model keeps its value. The inspector shows a `dashboard: <value>` badge (or
  `dashboard: schedule`) next to the parameter field (`DashboardOverrideBadge`, one line in
  `NodeInspector.tsx`).

### 1.2 Cards

| Kind | Role | Binding | Notes |
|---|---|---|---|
| `plot` | display | 1+ signals | uPlot, the shared cursor (`PLOT_SYNC_KEY`) and the plot panel's configuration |
| `value` | display | 1 signal | big number, unit, decimals, optional sparkline, zone tone chip |
| `gauge` | display | 1 signal | SVG 270° dial, `role="meter"`, colour zones on an outer ring |
| `bar` | display | 1 signal | vertical or horizontal scale, zones, `role="meter"` |
| `indicator` | display | 1 signal | on/off light at a threshold (`above`/`below`), `role="status"` with a text label |
| `text` | display | none | plain text or Markdown (react-markdown + GFM, sanitised) |
| `number` | input | `<instance path>/<param>` or `global:<name>` | typed value (same parser as the inspector's live edit) |
| `slider` | input | parameter or global | native range: min/max/step from the card, else from the catalog |
| `knob` | input | parameter or global | SVG `role="slider"`: vertical drag, wheel, arrow keys, Page Up/Down, Home/End |
| `toggle` | input | `Bool` parameter | `role="switch"` |
| `select` | input | enumeration (`Int` with options) | 1-based options from the catalog |
| `schedule` | input | parameter columns | table: t (s) plus one column per parameter |

Sizes are presets `1x1`, `2x1`, `1x2`, `2x2`, `4x2` on a plain CSS grid (column count from the
tab width, about 170 px per column). Status zones (`good`/`warn`/`bad`/`info`) always come with an
icon and a label, never colour alone. All colours are theme tokens.

### 1.3 Display cards and time

Display cards read the same series as the plot panel (`useRunSeries`). While a run is live they
show the latest sample. When the user scrubs, plays back or pauses, they show the value at the
global inspect time (`cursorTime`), the same time as the plot cursor. The signal ids that cards
bind are added to the run's data and live-tail requests (`runStore.setDashboardSignals`), so a
card shows a signal even when no plot does.

### 1.4 Editing

- **Edit / Done** toggles edit mode. In edit mode each card shows a toolbar: move earlier/later,
  a size select, settings (⚙) and remove (×). Cards can also be reordered by dragging.
- **+ Add card** opens a picker grouped into display and input cards.
- The **settings dialog** (focus-trapped, Escape closes) holds the title, size, binding (a
  searchable signal list, or a typed id before the first run; a searchable parameter list for
  inputs), min/max/step, unit label, decimals, colour zones, and kind-specific options.
- **Signals tab → card**: dropping a signal (signalDnd MIME type) on a display card binds it.
  Dropping it on the empty grid adds a Value card.
- A parameter may be bound by **one** input card or schedule column only. The parameter picker
  disables taken parameters, and a conflict in a saved model is reported as a problem.

### 1.5 Run inputs

At run start the web app computes the run inputs from the dashboard (`dashboardRunInputs`):

- each bound input card with a value gives a `parameterOverrides` entry `{target, value}` (Bool as
  a boolean, Int rounded);
- each schedule row gives one `parameterSchedule` step `{t, target, value}` per column.

A dashboard problem (unknown parameter, binding conflict, invalid schedule cell) **refuses the
run** with a "Dashboard: ..." message instead of running with half the inputs. The toolbar shows a
summary ("Next run: 2 parameter overrides, 3 scheduled changes", or the problem count).

**Auto re-run** (a checkbox, off by default, stored in the dashboard) starts a new run about
300 ms after the last input change. A change made while a run is running waits for it to end.

### 1.6 Schedule semantics

- Rows are sorted by t. From a row's t on, its parameters take the row's values (piecewise
  constant). Before the first row the model's values apply.
- Validation: every cell is a number, t lies in `[t_start, t_end]`, no two rows share a t, no
  duplicate column. Columns are Real/Int block parameters (not Bool, not enumerations).
- In the worker a step at or before `t_start` becomes a start override; steps after `t_end` are
  dropped. The other steps become run-loop targets: the integrator stops exactly at t, records
  the left value, sets the parameter (`setp`), re-initialises (algebraic reinit for DAEs,
  `reeval_internals_due_to_modification!` without a new initialisation), and records the right
  value at the same t. A replay or branch of the run applies the same steps.

## 2. Contracts

- `model.schema.json`: `dashboard`, `dashboardCard`, `dashboardCardOptions`, `dashboardZone`,
  `dashboardSchedule`, `dashboardScheduleRow`. The valid fixture `model.dashboard.json` has one
  card of each common kind; invalid fixtures cover a bad kind, a bad size and a schedule row
  without values.
- `run-manifest.schema.json`: `parameterOverride {target, kind?, value}` and
  `parameterStep {t, target, value}`; the manifest records `parameterOverrides` and
  `parameterSchedule`, so a run says which inputs it used.
- `worker-rpc.schema.json`: `run.start` params take the same two optional arrays. The backend's
  `POST /api/projects/{p}/runs` body takes them too and passes them on unchanged (the fake worker
  copies them into its manifest).
- **Global parameters.** `parameterOverride.kind` is `"block"` (the default: `target` is
  `<instance path>/<param>`) or `"global"` (`target` is `global:<name>`, the key of
  `BGSim.IR.override_globals`; when `kind` is absent the prefix decides). A number, slider or
  knob card can bind a global (`parameter: "global:m"`, fixture `model.dashboard-global.json`);
  the Parameters tab shows the same `dashboard: <value>` badge on the global's row. Globals are
  folded to numbers at compile time, so a global override is applied before static evaluation
  (dependents re-fold, the structure and the compile key may change) and **globals cannot be
  scheduled** (the schema's step pattern, the web schedule column picker and the Julia parser
  all refuse them).

## 3. Julia

`src/sim/overrides.jl`:

- global overrides go through `IR.override_globals` first; block overrides are then applied to
  the IR `ModelDoc` (node and subsystem parameters) **before** flattening, so derived initial
  values and parameter expressions see them. Every block parameter is a runtime MTK parameter
  (D4) and `compile_key` excludes parameter values, so a block override never recompiles. A
  target that is not in the document falls back to `set_parameter_values`.
- `check_schedule_targets` refuses unknown or discrete targets with an E003 diagnostic
  (`run.start` answers with an RPC error before the run starts).
- `_simulate_flat(...; parameter_schedule, manifest_extra)` merges the steps into the run-loop
  targets.
- `write_run_model` stores the inputs next to the run's model, so `replay` and `branch` reapply
  them.

## 4. Status

### Done (step 1)

- Contracts, generated pydantic and TypeScript types, fixtures, contracts README.
- Backend pass-through, fake worker, tests (`test_runs.py`).
- Julia overrides and schedule, replay/branch, worker RPC, tests (`test_overrides.jl`: an override
  changes the result, a subsystem override, a schedule step at t = 1 against the analytic
  solution with left and right rows, an off-grid step, replay bit-identical, a global override
  (re-folded dependents, mixed with a block override, replay), bad inputs;
  `test_worker.jl`: `run.start` with a dashboard, overrides and a schedule on the real worker,
  a global override, and bad targets).
- Web: the tab, all twelve card kinds, edit mode, settings dialog, signal drag and drop, run
  inputs, auto re-run, the inspector badge. Unit tests (`tests/dashboard.test.tsx`) and an e2e
  spec (`tests/e2e/dashboard.spec.ts`: add Value + Slider + Schedule, the POST body and manifest
  carry the overrides and schedule, the value card shows a number, the inspector badge; a full
  dashboard in both themes, axe-clean in use and edit mode and in the settings dialog).

### Open

- **Detach** the dashboard into a popup window (like the 3D viewer) is not done.
- **Auto re-run** only works while the Dashboard tab is mounted.
- The **unit** option is a display label, not a unit conversion.
- Display values come from the decimated series the plots use; a value between two kept samples
  is held from the previous one.
- Schedule columns for Bool and enumeration parameters; ramps instead of steps.
- Input cards that change a parameter **during** a paused or live run (today the inputs apply at
  the next run; live edits stay in the inspector).
