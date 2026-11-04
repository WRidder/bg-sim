# bg-sim

A bond-graph / block-diagram / equation modeling and simulation tool:
- a web editor (React + TypeScript + Vite)
- a Python backend (FastAPI)
- a Julia library for everything model-related (parsing, compiling, simulating)

## Key documents
- Language and semantics spec: `spec/Modeling Language Spec v0.1.md`
- Implementation plan (milestones, work packages, contracts): `plan/IMPLEMENTATION_PLAN.md`
- M3 multibond mechanics detail (2D/3D elements, WPs, visual contract): `plan/MULTIBOND_PLAN.md`
- C/FMU export (real-time target, WPs, spike results): `plan/EXPORT_PLAN.md`, spike in `spike/fmu/`
- Global parameters (SolidWorks-style globals/equations, override hook, FMU exposure design): `plan/GLOBAL_PARAMETERS.md`
- RL controllers (rsl_rl PPO on exported FMUs, domain randomisation, policy import, progress table): `plan/RL_PLAN.md`
- Robust classical pendulum control (multi-model LQR, worst-case swing-up, energy-based swing-up, comparison with RL): `plan/ROBUST_CLASSICAL_PLAN.md`
- Modelling assistant (chat panel, draft and Apply, runners, code cells, hosted profiles): `plan/ASSISTANT_PLAN.md`
- Web games (FMU in the browser via Wasm, no backend, single HTML file): `plan/WEB_APPS_PLAN.md`, code in `apps/web/`
- Background literature (PDFs, read-only): `background/`

## Toolchain (this machine: Windows 11)
- **Julia is available.** Julia 1.13.2 is installed through `juliaup` (`julia`, `juliaup` on PATH).
  - Run the Julia package with `julia --project=julia/BGSim ...`.
  - Never install Julia packages into the global environment.
- **Use `uv` for every Python application, script and tool.** There is no system Python (the `python` alias points to the Microsoft Store stub).
  - Run with `uv run ...`.
  - Add dependencies with `uv add ...` (or `uv add --dev ...`).
  - Pin the interpreter with `uv python pin`.
  - Never use `pip install` or a bare `python`.
- Node 24 and npm are available for the web app (`web/`).
- Shells: PowerShell is the default, and Git Bash is available. Use forward slashes in scripts, and keep line endings LF (`.gitattributes`).

## Conventions
- Contracts live in `contracts/` as JSON Schema plus fixtures. They are the single source of truth for the TypeScript, Python and Julia data shapes. Never change a shape in only one language.
- User manual: `web/src/manual/pages/*.md` (help icon in the top bar / F1). Every user-visible feature change updates the relevant manual page in the same branch; a new page also goes into the page list of `web/tests/user-manual.test.tsx`.
- The 3D viewer follows the setup of `D:\CtrlX Agentic Machine Control\framework\hmi\src\viewer` (see the plan, section 7.6).
