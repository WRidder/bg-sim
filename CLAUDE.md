# bg-sim

A bond-graph / block-diagram / equation modeling and simulation tool:
- a web editor (React + TypeScript + Vite)
- a Python backend (FastAPI)
- a Julia library for everything model-related (parsing, compiling, simulating)

## Key documents
- Language and semantics spec: `spec/Modeling Language Spec v0.1.md`
- Implementation plan (milestones, work packages, contracts): `plan/IMPLEMENTATION_PLAN.md`
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
- The 3D viewer follows the setup of `D:\CtrlX Agentic Machine Control\framework\hmi\src\viewer` (see the plan, section 7.6).
