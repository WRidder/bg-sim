# Global parameters (SolidWorks "Global Variables / Equations")

Status: implemented on branch `global-params` (contract, Julia, web, tests). The language rules
are in the spec, section "Global parameters"; this file records the design decisions, where the
code lives, the hook for the dashboard, and the next step (exposing globals in the FMU).

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
| G7 | Not runtime tunables: the flat model, simulation and the C/FMU export see numbers only (verified by `test_globals.jl`: no global name in `model.c` or `modelDescription.xml`). | "All should be statically evaluated." The export option in "Next step" keeps this default. |
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

## Next step: "Expose global parameters as FMU parameters" (designed, not implemented)

Default stays G7 (fold to constants). The option makes each global an FMI 2.0 variable with
`causality="parameter"`, `variability="fixed"` (settable only before initialization), and computes
everything that depends on it once, at initialization, in the generated C. The real-time step
cost is unchanged because nothing is recomputed per step.

Why it is not a small change today: the export works on the ModelingToolkit system after
`structural_simplify`, where every parameter value and every start value is already a number
(`export.jl`: `p0`, `fold_subs`, "start values computed at export"). The dependency on the
globals is gone by then. The work:

1. **Flat model keeps the equation.** `_bind_parameters!`/`_bind_starts!` record, for every
   instance value that mentions a global, the folded AST over global names
   (`FlatParam.attrs[:global_expr]`, and the same for a start on `FlatVar.attrs`). Structural
   constants that depend on a global (sizes) cannot be exposed: the export refuses to expose such a
   global with a warning (proposed W215) and folds it.
2. **Export settings.** `ExportSettings.expose_globals::Bool = false` (export-request contract
   `settings.exposeGlobals`, export dialog checkbox "Expose global parameters as FMU parameters").
3. **Classification in `export.jl`.** A parameter with `:global_expr` is neither folded nor
   tunable: it becomes a `calculatedParameter` (`causality="calculatedParameter"`,
   `variability="fixed"`) stored in `m->p[]`, and every global becomes a `parameter`/`fixed`
   variable in `m->g[]`. `fold_subs` must not substitute these parameters (`simplify=true` keeps
   them symbolic), so the Jacobian and right-hand side read `m->p[k]`.
4. **Generated init.** `model.c` gets `bg_compute_parameters(m)`: the globals in topological order
   (the order `evaluate_globals` already returns), then each dependent parameter and start from its
   expression, emitted with the existing C expression printer (the constant folder's functions all
   have C intrinsics). `fmi2ExitInitializationMode` calls it before the start-value computation.
5. **Starts and initialization.** A start that depends on a global is recomputed at init. A model
   whose consistent initialization (algebraic states, `structural_simplify` observed equations)
   depends on a global needs the initialization solve in C, which the export does not have: refuse
   exposure (E110 naming the global and the dependent algebraic variable) until it exists.
6. **Tests.** An FMU with an exposed global set before init (fmpy `start_values`) must match a
   folded export built with that value (same `dt`, bitwise or within 1e-12); `fmpy validate`; the
   allocation-free and real-time checks of `test_export.jl`/`examples/export_checks.py` stay green;
   `modelDescription.xml` lists the globals with their unit (from `ModelGlobalParameter.unit`) and
   description.

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
