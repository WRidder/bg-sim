# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""bg-sim check driver.

Runs the checks of one or more lanes and prints a summary table.

Usage:
    uv run tools/check.py --lane all
    uv run tools/check.py --lane j        # Julia
    uv run tools/check.py --lane p        # Python backend
    uv run tools/check.py --lane w        # Web
    uv run tools/check.py --lane x        # Examples and Playwright e2e
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANES = ("j", "p", "w", "x")
LANE_NAMES = {
    "j": "Julia",
    "p": "Python backend",
    "w": "Web",
    "x": "Examples / e2e",
}


@dataclass
class Step:
    name: str
    args: list[str]
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Result:
    step: str
    status: str  # "pass", "fail", "skip"
    seconds: float
    detail: str = ""


def _print(msg: str) -> None:
    print(msg, flush=True)


def _julia() -> str:
    return os.environ.get("BGSIM_JULIA", "julia")


def julia_steps() -> list[Step] | None:
    project = ROOT / "julia" / "BGSim"
    if not (project / "Project.toml").exists():
        return None
    if not (project / "test" / "runtests.jl").exists():
        return None
    return [
        Step(
            "julia Pkg.test",
            [_julia(), f"--project={project}", "-e", "using Pkg; Pkg.test()"],
            cwd=ROOT,
        )
    ]


def python_steps() -> list[Step] | None:
    backend = ROOT / "backend"
    if not (backend / "pyproject.toml").exists():
        return None
    steps = [Step("pytest", ["uv", "run", "--directory", str(backend), "pytest", "-q"], cwd=ROOT)]
    if (backend / "tests").exists() or (backend / "src").exists():
        steps.append(
            Step("ruff", ["uv", "run", "--directory", str(backend), "ruff", "check", "."], cwd=ROOT)
        )
    return steps


def web_steps() -> list[Step] | None:
    web = ROOT / "web"
    if not (web / "package.json").exists():
        return None
    return [
        Step("typecheck", ["npm", "--prefix", str(web), "run", "typecheck"], cwd=ROOT),
        Step("lint", ["npm", "--prefix", str(web), "run", "lint"], cwd=ROOT),
        Step("vitest", ["npm", "--prefix", str(web), "run", "test", "--", "--run"], cwd=ROOT),
        Step("build", ["npm", "--prefix", str(web), "run", "build"], cwd=ROOT),
    ]


def example_steps() -> list[Step] | None:
    examples = ROOT / "examples"
    if not examples.is_dir() or not any(examples.iterdir()):
        return None
    steps: list[Step] = []
    runner = examples / "run_checks.py"
    if runner.exists():
        steps.append(Step("examples", ["uv", "run", str(runner)], cwd=ROOT))
    e2e = ROOT / "web" / "tests" / "e2e"
    if (ROOT / "web" / "playwright.config.ts").exists() and e2e.exists():
        steps.append(
            Step(
                "playwright",
                ["npx", "playwright", "test"],
                cwd=ROOT / "web",
                env={"BGSIM_FAKE_WORKER": "1"},
            )
        )
    return steps or None


BUILDERS = {"j": julia_steps, "p": python_steps, "w": web_steps, "x": example_steps}


def run_step(step: Step) -> Result:
    _print(f"\n=== {step.name}: {' '.join(step.args)}")
    env = os.environ.copy()
    env.update(step.env)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(step.args, cwd=str(step.cwd or ROOT), env=env)
        dt = time.perf_counter() - t0
        status = "pass" if proc.returncode == 0 else "fail"
        detail = "" if proc.returncode == 0 else f"exit {proc.returncode}"
        return Result(step.name, status, dt, detail)
    except FileNotFoundError as exc:
        dt = time.perf_counter() - t0
        return Result(step.name, "fail", dt, f"not found: {exc.filename}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Run bg-sim checks")
    ap.add_argument("--lane", default="all", choices=(*LANES, "all"))
    ap.add_argument("--filter", default=None, help="Only run steps whose name contains this")
    args = ap.parse_args(argv)

    lanes = LANES if args.lane == "all" else (args.lane,)
    results: list[Result] = []
    skipped_lanes: list[str] = []

    for lane in lanes:
        steps = BUILDERS[lane]()
        if not steps:
            skipped_lanes.append(lane)
            _print(f"\n=== {LANE_NAMES[lane]}: no tests yet")
            results.append(Result(f"{LANE_NAMES[lane]} (lane)", "skip", 0.0, "no tests yet"))
            continue
        for step in steps:
            if args.filter and args.filter not in step.name:
                continue
            results.append(run_step(step))

    _print("\n" + "=" * 64)
    _print(f"{'check':<28} {'status':<8} {'time':>8}  detail")
    _print("-" * 64)
    for r in results:
        _print(f"{r.step:<28} {r.status:<8} {r.seconds:>7.1f}s  {r.detail}")
    _print("=" * 64)

    failed = [r for r in results if r.status == "fail"]
    passed = [r for r in results if r.status == "pass"]
    skipped = [r for r in results if r.status == "skip"]
    _print(f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    if skipped_lanes:
        _print("lanes with no tests yet: " + ", ".join(sorted(skipped_lanes)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
