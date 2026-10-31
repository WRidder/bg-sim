# Global parameters (SolidWorks "Global Variables / Equations")

Status: implemented on branch `global-params` (contract, Julia, web, tests). The language rules
are in the spec, section "Global parameters"; this file records the design decisions, where the
code lives, the hook for the dashboard, and exposing globals in the FMU (implemented on branch
`jex8-tunables` with J-EX8, see the section below).

## User request

> A notion of global parameters, which elements in the model can refer to, a bit SolidWorks
> style, where you can set global parameters (which in themselves can be composed by simple
> arithmetic on other params). All should be statically evaluated.

Follow-up: follow SolidWorks closely. Any value is either a plain value or an equation; a
driven value gets a Σ marker, shows its evaluated value and its equation as a tooltip; the
Equations manager has the views Global variables, Equations and (evaluation) Order.

## Decisions

| # | Decision | Why |
| --- | --- | --- |
| G1 | Contract: optional top-level `parameters: [{ name, value, unit?, description? }]` (`$defs/globalParameter`, `ModelGlobalParameter`). `value` is a constant expression **string**; `unit`/`description` are documentation, not checked. | One localized schema change (top-level property + one `$def`), easy to merge with the `dashboard` and `sticky-notes` branches. Strings keep `4*m` and `2` uniform. |
| G2 | Scope: the globals are the only names an instance value (params, starts, string constants) can use, at every diagram level including subsystems. Not visible in block source. | Instance values were already literal-only (the wrapper block of `_parse_value` declares nothing else), so there is no shadowing to define and no surprise; blocks stay self-contained. |
| G3 | Names: identifier, unique, not reserved (`t`, `Ts`, `ifelse`, `true`, `false`, `pi`, Julia keywords) and not a built-in function: E003. | Same rule family as declaration names (E003). `pi` is reserved because the browser gives it a fixed meaning. |
| G4 | Static evaluation in `Compile.evaluate_globals` before instantiation: parse with the block front end, E003 for unknown names, Kahn topological order, **E113** for a cycle (path `a -> b -> a`), a non-finite result or a domain error, E004 for a Bool; dependents of a failed global fail (E113). Int stays Int. | One new code only. Int-preservation lets a global size a structural constant. |
| G5 | Instance values: `_parse_value` declares each mentioned, folded global as an `@constants` line of its wrapper block with the folded value, so the checker and the folder are unchanged. A mention of a failed global is E113 on the instance. | Reuses the exact checker; no second interpreter. |
| G6 | Diagnostics of a global are model-wide: `path = null`, `scope = "global:<name>"`. | The diagnostic schema's path pattern is an instance path; a global is not an instance. The diagnostics panel shows them in its Model group. |
| G7 | Not runtime tunables: the flat model, simulation and the C/FMU export see numbers only (verified by `test_globals.jl`: no global name in `model.c` or `modelDescription.xml`). | "All should be statically evaluated." The export option "Expose global parameters as FMU parameters" (below) keeps this default. |
| G8 | Start-time override hook: `BGSim.IR.override_globals(md, overrides)` returns a copy of the document whose globals named by `"global:<name>"` keys take the new value *before* evaluation, so dependents re-fold. Other keys (block parameter ids `Inst/param`) are ignored, so a run request's `parameterOverrides` map can be passed as is; an unknown global throws `ArgumentError`. | The dashboard branch adds `parameterOverrides`/`parameterSchedule` on the run request; a `:` never occurs in an instance path, so `global:` cannot collide. A schedule entry for a global would need a re-fold (re-compile) at that instant; globals are not tunables, so that is out of scope here. |
| G9 | Rename rewrites whole identifiers via the expression tokenizer (`identifierSpans`/`renameIdentifier` in `web/src/inspector/expression.ts`): not inside numbers (`1e-3`), not dotted names, not function calls. Other globals and every instance value at every level, one undo step. Deleting a used global is refused with the list of users. | Regex on substrings would rename `k2` or the `e` of `1e-3`. |
| G10 | UI home: the Inspector when nothing is selected becomes the **Model inspector** with the Equations manager (Global variables, Equations, Order) and an "Open manager..." button for a wide modal with unit and comment columns. | The user reported "Nothing selected" as wasted space; SolidWorks keeps its equations next to the model, not in the library column. The left panel is already split between the library and the model tree. |
| G11 | Driven fields: any value that is not a plain literal gets the Σ badge, `= value unit` readout, an `Equation: ...` tooltip, global-name completion (prefix, then substring; Tab/Enter accept), and the catalog min/max check on the evaluated value. A leading `=` is accepted and stripped (SolidWorks prefix); the stored value is the bare expression. | SolidWorks parity, small change to the shared `TextField` (`completions`, `readout`, `inputTitle` props) so the dashboard branch's inspector badge merges cleanly. |
| G12 | Instance-to-instance references (`Motor1.R`, SolidWorks' dimension-to-dimension equations) are **not** added. | They would turn the instance value scope into a model-wide dependency graph over block parameters (ordering across subsystems, renames of instances and parameters, aliases of composite parameters). Globals cover the use case: define the shared value once and point both blocks at it. Open point. |

## Where the code lives

- Contract: `contracts/schemas/model.schema.json` (`parameters`, `$defs/globalParameter`); fixtures
  `model/valid/model.global-parameters.json` (globals in a subsystem and a start),
  `model/invalid/model.global-parameter-{bad-name,no-value}.json`,
  `model/semantic/model.e113-global-cycle.json`; `diagnostic/valid/diagnostics.sample.json` (E113).
- Julia: `src/ir/modeldoc.jl` (`GlobalParam`, `ModelDoc.globals`, `override_globals`,
  `GLOBAL_OVERRIDE_PREFIX`), `src/compile/globals.jl` (`evaluate_globals`, `GlobalEnv`,
  `global_names_in`), `src/compile/instantiate.jl` (`Builder.globals`, `_parse_value`).
  Tests: `test/test_globals.jl`.
- Web: `src/globals/globals.ts` (evaluation mirror, usages, driven fields, rename walker),
  `src/globals/globalEdits.ts` (store edit plans), `src/globals/EquationsManager.tsx`
  (Model inspector, manager, dialog), `src/globals/equationField.tsx` (Σ decoration),
  `src/inspector/expressionCompletion.tsx`, `src/inspector/expression.ts` (evaluation with names,
  `identifierSpans`, `renameIdentifier`, `isPlainLiteral`, `stripEquationPrefix`),
  `src/state/documentStore.ts` (`addGlobalParameter`, `updateGlobalParameter`,
  `renameGlobalParameter`, `deleteGlobalParameter`, `moveGlobalParameter`, `setFieldExpression`).
  Tests: `tests/globals.test.ts`, `tests/equations-manager.test.tsx`, `tests/e2e/globals.spec.ts`.
- FMU exposure (J-EX8): `src/ir/flat.jl` (`GlobalInfo`, `FlatModel.globals`),
  `src/compile/instantiate.jl` (`_file_global_value!`), `src/export/tunables.jl`
  (`plan_tunables`, `start_targets`, `check_initialization`), `src/export/export.jl`
  (classification, `bg_init_values`), `export/runtime/bg_solver.c` (`bg_init`),
  `export/runtime/fmi2_cs.c` (fixed/calculated/range refusals); web
  `src/export/exportTunables.ts` and the dialog's Tunable parameters section.

## Expose global parameters as FMU parameters (implemented with J-EX8, branch `jex8-tunables`)

Default stays G7 (fold to constants). The option makes each exposed global an FMI 2.0 variable
with `causality="parameter"`, `variability="fixed"` (settable only before initialization), and
computes everything that depends on it once, at initialization, in the generated C. The
real-time step is unchanged in structure (nothing is recomputed per step); its cost grows only by
the operations the calculated parameters no longer fold away (the report's `rhsOps` against
`rhsOpsFolded`). The same machinery keeps a picked block parameter settable before
initialization (the W-EX1 tunables editor, plan/EXPORT_PLAN.md J-EX8).

What was built, against the design that stood here before:

1. **Flat model keeps the equation.** As designed, but not on the attributes: `_parse_value`
   remembers the folded AST and the globals it used (`Builder.global_last`), and each binding
   site files it (`_file_global_value!`) by flat id into `Builder.global_param_exprs` /
   `global_start_exprs` (a scalar, or one element of a vector literal), or, for a structural
   constant or a non-scalar value, into `global_fixed` (global => what it sets).
   `FlatModel.globals::Flat.GlobalInfo` carries the names, evaluation order, values, the ASTs of
   the globals themselves (`GlobalEnv.exprs`), units, descriptions and those three maps. A model
   without globals has `globals = nothing`.
2. **Export settings.** `ExportSettings.expose_globals::Bool = false` (export-request
   `settings.exposeGlobals`), plus `tunables` (ids: `Inst/param` or `global:<name>`) and
   `ranges` (id => (min, max), D-EX16) for a per-global choice. The dialog uses the per-id list
   with a one-click "Expose all globals (n)" instead of a checkbox, so each global gets its
   range next to it.
3. **Classification** (`src/export/tunables.jl`, `plan_tunables`). Only an independent global
   (its value a literal) is exposed; a driven global (`k = 3*m`) is recomputed from the
   exposed ones, never set (W215 if requested). Every global is lowered to Symbolics: an exposed
   one is a fresh parameter symbol, a driven one that depends on an exposed one its lowered
   expression, every other its number. A block parameter whose instance value mentions a live
   global becomes a calculated parameter (`causality="calculatedParameter"`,
   `variability="fixed"`, `initial="calculated"`, listed in `InitialUnknowns`) stored in
   `m->p[]`; the exposed globals are extra slots of `m->p[]` (not a separate `m->g[]`: one
   value-reference range, one `SetReal` path) that no equation reads. The calculated
   parameters are not folded or substituted by `simplify`, so the right-hand side and the
   Jacobian read `m->p[k]`.
4. **Generated init.** `model.c` gets `bg_init_values(m, t, x)` (the design called it
   `bg_compute_parameters`): each calculated parameter, each recomputed start, and each held
   value computed from a global, as C expressions over the exposed slots. It runs once in
   `fmi2ExitInitializationMode` through the runtime's `bg_init`, before the DAE Newton.
5. **Starts and initialization.** A start that is an expression over a global is recomputed
   (followed along the alias chain to the state MTK kept). Consistent initialization of a DAE is
   no longer a refusal: `bg_init` runs a bounded Newton (50 iterations) on the algebraic block
   (J-EX8). What the C cannot reproduce is refused with E110: at export, each tunable is
   perturbed inside its range and MTK's initialization (a Julia run with that value) is compared
   with the emulated C one (relative 1e-6). The probes are in `report.tunables.initializationChecks`.
6. **Refusals.** W215 (warning, the global stays folded): a global that sets a structural
   constant or a non-scalar value (or a global driven by it does), a driven global, an unknown
   name, a block parameter whose value is an expression over globals (expose the global), a
   runtime-tunable parameter computed from an exposed global (it keeps its own value). E110: a
   range that leaves out the model's value; an initialization the C cannot reproduce.
7. **Ranges** (D-EX16). A global has no catalog range: the user gives one in the dialog, or the
   range is open (W210, the step is proven at the model's value only). The ranged globals join the
   spectrum scan through the parameters calculated from them (the scan runs over
   `q = [p; globals]`). The FMU refuses (`fmi2Error`, logged with the name, the value and the
   range) a value outside the range; it never clamps.
8. **Tests.** `julia/BGSim/test/test_export_tunables.jl`: the globals fixture exported with `m`
   exposed (calculated `Source/Rate/value`, recomputed start of `Int1/x`, units and
   descriptions in `modelDescription.xml`); in C, `m = 3` set before init gives
   `Int1/y(1) = sqrt(3) + 0.5 + 12` and equals the folded export of the model with `m = 3`
   (`override_globals`, same `dt`) to 1e-13; a calculated parameter and an out-of-range value
   are refused. `examples/export_tunables_check.py` repeats this in fmpy on dc-motor
   speed-control with `Rm`, `Jr` exposed and `Lm = 2.5e-4*Rm` driven (results in
   plan/EXPORT_PLAN.md J-EX8).

Dashboard inputs and schedules stay out of the export (the dashboard branch owns them).

## Open points

- Instance-to-instance references (G12).
- Vector/matrix globals (`[1.0, 2.0]`): the Julia folder could fold them, but the browser's
  expression parser has no array syntax; scalars only for now.
- `pi` evaluates in the browser but not in the Julia folder (pre-existing; the spec lists no `pi`
  constant). Either add `pi` to the folder or drop it from the browser.
- A unit check of a global against the parameters that use it (the unit is documentation today).
- Dashboard binding: an input card bound to `global:<name>`; a schedule entry for a global needs a
  re-fold, i.e. a recompile at that instant (not a tunable `setp`).
