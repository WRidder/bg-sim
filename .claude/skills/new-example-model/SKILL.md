---
name: new-example-model
description: Guidelines and checklist for building a new bg-sim model or example project (examples/<name>/): bond-graph-first modelling, project layout, build script, expected checks, docs, dashboard, gallery card. Use whenever the user asks for a new model, a new example, or a new variant of an existing example.
---

# Building a new (example) model

## 1. Model with bond-graph elements first

Unless the user asks for something else:

- **Build the physics from standard library elements**, in this order of preference:
  1. bond-graph elements: `stdlib:bondgraph/` (`Se`, `Sf`, `R`, `C`, `I`, `TF`, `GY`, the `0`/`1` junctions, and the modulated `MSe`, `MSf`, `MTF`, `MGY`, `MR`). For multibond mechanics, use `stdlib:multibond/`, `planar/` and `spatial/`.
  2. the domain components (`electrical/`, `rotation/`, `translation/`, `hydraulic/`, `thermal/`, `drives/`, `contact/`, `motion/`) where the user wants an iconic diagram, or where a component already bundles a standard law.
  3. signal blocks (`continuous/`, `discrete/`, `sources/`, `converters/`) for controllers, references and measurements.
- **Avoid custom blocks.** Write a project library block (`examples/<name>/library/*.jl`) only when no combination of standard elements expresses the law. Examples are a nonlinear constitutive law (a tunnel diode, a friction curve or a tyre model, as a nonlinear `R`/`C` with `@causality`), a lookup or fitted table, an estimator or controller with real algorithmic content, or a policy network.
  - Keep each custom block small and physical: one law, ports with units, and parameters with units and limits.
  - Never use a custom block to hide a whole plant as one `@equations` block. The bond graph is the point of the tool.
- **Prefer a diagram the user can read**: junction structure visible, causality strokes clean, and subsystems for repeated or nested parts (a motor, a leg, an axle).
- Use **global parameters** for the quantities a user will tune (masses, gains, set points). See `plan/GLOBAL_PARAMETERS.md`.

## 2. Look before you build

- Read the relevant spec sections in `spec/Modeling Language Spec v0.1.md`: the component catalog, ports and bond-graph elements, units, and discrete/event semantics.
- Find the closest existing example in `examples/` and copy its structure. Small ones are `dc-motor` and `van-der-pol`; larger ones are `pendulum-double-cart-lab`, `cessna` and `suction-gripper`.
- Check the stdlib block's source (`julia/BGSim/stdlib/<category>/<Block>.jl`) for exact port names, parameters and units. Never guess them.

## 3. Project layout

```
examples/<name>/
  bgsim.project.json        format, language, name, models[], libraryDir, scenesDir
  README.md                 what it models, parameters table, reference values, "what to try"
  models/<model>.bgmodel.json
  library/*.jl              only if section 1 allows it
  scenes/*.sdf              3D scene (optional), bound through the model's bindings
  design/build_model.py     writes models, scene and expected.json (uv script, deterministic)
  design/design.json|.py    the reference numbers (analytic, scipy, literature), if any
  expected.json             acceptance checks
```

- **Generate the models with `design/build_model.py`.** Write it as a `uv run` script with an inline `# /// script` header, so that rebuilding is one command. Don't hand-edit large model JSON.
- The model shape follows `contracts/schemas/model.schema.json`. Never invent fields.
- Give blocks meaningful names (`Motor`, `Cart`, `Rod1`). Signal ids (`Cart/p.f`) appear in checks, docs and dashboards.

## 4. Checks: `expected.json`

- Every model gets checks against **independent reference values**: analytic steady states, energy balance, a scipy/textbook simulation, or literature data. Add a `note` saying where each number comes from.
- Add `scene_bindings` when there is a scene, `no_diagnostics` for the causality warnings (W201/W202/E106), and `compare_signals` when two models (for example an iconic and a bond-graph version) must agree.
- Run the checks with `uv run examples/run_checks.py --only <name>`. The model must also flatten and compile without errors.
- Fix the model, not the tolerance. A wider tolerance needs a reason in the `note`.

## 5. What the user sees

- **Docs.** Every model needs short docs: what you're looking at, what to try, and the key parameters. Text shared by all models of the example goes in the **project docs** (`@@ page @project …`).
  - The sources are `tools/example_docs/src/<name>.md`; build with `uv run tools/example_docs/build.py --only <name>`.
  - Use `block:` and `signal:` links in model pages.
- **Dashboard and plots.** Each model gets a simple dashboard (the main inputs or globals, two or three readouts, one or two plots) and saved plots of the main signals. The checker verifies that they name recorded signals.
- **Gallery.** Add the example to `web/src/examples/gallery.json` (title, one-line description, hasScene, models). Make the thumbnail with `npm run capture-thumbnails` in `web/`, into `web/src/examples/thumbnails/<name>.png`.
- **Manual.** If the example shows a new feature or block, update the relevant `web/src/manual/pages/*.md`.

## 6. Finish

- Run only the targeted checks: the new example's checks, the docs lint, and any Julia or web tests the change touches.
- After merging, run `npm run build` in `web/` so the user's app serves the new gallery card.
- Follow `CLAUDE.md`: use `uv` for Python, never global Julia packages, LF line endings, and never port 8765. Commit and merge locally only; the user pushes.
