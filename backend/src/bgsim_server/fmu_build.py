"""Build an FMU from a C/FMU export directory (plan/EXPORT_PLAN.md, work package P-EX1).

The Julia side (``BGSim.Export.export_model``) writes ``sources/``, ``modelDescription.xml``
and ``export.json`` into an export directory. This module turns that into an ``.fmu``:

1. compile the hot-path objects (``model.c``, ``bg_solver.c``, ``fmi2_cs.c``,
   ``bg_intrinsics.c``, ``bg_mech.c``) and check their undefined symbols: no allocator, no
   stdio, no ``exit``/``abort`` (D-EX4, plan 8);
2. check that the sources also compile as C++17 (a compatibility check for embedding in a
   C++ application; C is the only target);
3. link the shared library for the host platform;
4. run the counting harness (``alloc_check.c`` from the runtime): 0 memory callbacks after
   ``fmi2Instantiate`` over ``harness_steps`` ``fmi2DoStep`` calls, and the step time, which
   is written back into ``export.json`` as ``build``;
5. zip ``modelDescription.xml``, ``binaries/<platform>/`` and ``sources/``.

A source-only FMU is still written when no compiler is found. Cross targets (``zig cc``,
P-EX2) are not part of this module yet.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

#: Symbols the hot-path objects must never import.
FORBIDDEN_SYMBOLS = frozenset({
    "malloc", "calloc", "realloc", "free", "aligned_alloc", "posix_memalign",
    "printf", "fprintf", "vfprintf", "sprintf", "snprintf", "vsnprintf", "puts", "fputs",
    "fopen", "fwrite", "fread", "exit", "abort", "_exit",
})

#: The objects that run inside ``fmi2DoStep``.
HOT_PATH_SOURCES = ("model.c", "bg_solver.c", "fmi2_cs.c", "bg_intrinsics.c", "bg_mech.c")

C_FLAGS = ("-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-fno-math-errno")


@dataclass
class BuildResult:
    """What ``build_fmu`` did. ``ok`` is false when a check failed or the build broke."""

    fmu: Path | None = None
    ok: bool = False
    platform: str | None = None
    compiler: str | None = None
    undefined_symbols: list[str] = field(default_factory=list)
    forbidden_symbols: list[str] = field(default_factory=list)
    cxx_ok: bool | None = None
    allocations_after_instantiate: int | None = None
    step_time_mean_us: float | None = None
    step_time_max_us: float | None = None
    log: list[str] = field(default_factory=list)
    error: str | None = None


def host_platform() -> str:
    """The FMI 2.0 platform folder name of this machine (``win64``, ``linux64``, ...)."""
    system = platform.system()
    bits = "64" if platform.architecture()[0] == "64bit" else "32"
    if system == "Windows":
        return "win" + bits
    if system == "Darwin":
        return "darwin" + bits
    return "linux" + bits


def find_compiler() -> str | None:
    """A gcc or clang on PATH (the ``cl`` on PATH may be Open Watcom, so it is not used)."""
    for name in ("gcc", "clang", "cc"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _cxx_for(cc: str) -> str | None:
    base = Path(cc).name.lower()
    candidates = ["g++"] if base.startswith("gcc") else ["clang++"] if "clang" in base else []
    for name in candidates + ["c++"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def _nm_for(cc: str) -> str | None:
    sibling = Path(cc).with_name("nm.exe" if Path(cc).suffix.lower() == ".exe" else "nm")
    if sibling.exists():
        return str(sibling)
    return shutil.which("nm") or shutil.which("llvm-nm")


def _run(cmd: list, result: BuildResult) -> subprocess.CompletedProcess:
    result.log.append(" ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], text=True, capture_output=True)


def _library_suffix(plat: str) -> str:
    return ".dll" if plat.startswith("win") else ".dylib" if plat.startswith("darwin") else ".so"


def build_fmu(export_dir: Path, *, runtime_dir: Path, harness_steps: int = 100_000,
              compiler: str | None = None) -> BuildResult:
    """Compile, check and zip the export in ``export_dir`` into ``<identifier>.fmu``.

    ``runtime_dir`` is ``julia/BGSim/export/runtime`` (it holds the harness).
    """
    export_dir = Path(export_dir)
    report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    ident = report["identifier"]
    src = export_dir / "sources"
    build = export_dir / "build"
    build.mkdir(exist_ok=True)
    result = BuildResult()
    cc = compiler or find_compiler()
    result.compiler = cc
    binary: Path | None = None
    plat = host_platform()

    if cc is not None:
        result.platform = plat
        objects = []
        for name in HOT_PATH_SOURCES:
            obj = build / (Path(name).stem + ".o")
            res = _run([cc, *C_FLAGS, "-c", src / name, "-I", src, "-o", obj], result)
            if res.returncode != 0:
                result.error = f"compiling {name} failed:\n{res.stdout}{res.stderr}"
                return result
            objects.append(obj)

        nm = _nm_for(cc)
        if nm is not None:
            undefined: set[str] = set()
            for obj in objects:
                res = _run([nm, "-u", obj], result)
                for token in res.stdout.split():
                    if token != "U":
                        undefined.add(re.sub(r"^_+", "", token))
            result.undefined_symbols = sorted(undefined)
            result.forbidden_symbols = sorted(undefined & FORBIDDEN_SYMBOLS)

        cxx = _cxx_for(cc)
        if cxx is not None:
            result.cxx_ok = all(
                _run([cxx, "-x", "c++", "-std=c++17", "-fsyntax-only", "-Wall", "-Werror",
                      "-I", src, src / name], result).returncode == 0
                for name in ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c"))

        binary = build / (ident + _library_suffix(plat))
        res = _run([cc, *C_FLAGS, "-shared", "-fPIC", "-static-libgcc", "-I", src,
                    *[src / n for n in HOT_PATH_SOURCES], "-o", binary, "-lm"], result)
        if res.returncode != 0:
            result.error = f"linking the FMU binary failed:\n{res.stdout}{res.stderr}"
            return result

        harness = build / ("alloc_check" + (".exe" if plat.startswith("win") else ""))
        res = _run([cc, "-std=c11", "-O2", "-I", src, runtime_dir / "alloc_check.c",
                    *[src / n for n in HOT_PATH_SOURCES], "-o", harness, "-lm"], result)
        if res.returncode != 0:
            result.error = f"building the allocation harness failed:\n{res.stdout}{res.stderr}"
            return result
        per = max(1, round(report["step"] / report["dt"]))
        res = _run([harness, per, harness_steps], result)
        match = re.search(r"after instantiate (\d+)", res.stdout)
        result.allocations_after_instantiate = int(match.group(1)) if match else None
        match = re.search(r"mean ([0-9.]+) us, max ([0-9.]+) us", res.stdout)
        if match:
            result.step_time_mean_us = float(match.group(1))
            result.step_time_max_us = float(match.group(2))
        if res.returncode not in (0, 1):
            result.error = f"the harness failed (a step diverged?):\n{res.stdout}{res.stderr}"
        # The measured step time joins the export report (plan 5.2, step 4).
        report["build"] = {
            "platform": plat, "harnessDoSteps": harness_steps, "internalStepsPerDoStep": per,
            "allocationsAfterInstantiate": result.allocations_after_instantiate,
            "doStepMeanUs": result.step_time_mean_us, "doStepMaxUs": result.step_time_max_us,
        }
        (export_dir / "export.json").write_text(json.dumps(report, indent=4), encoding="utf-8")

    fmu = export_dir / f"{ident}.fmu"
    with zipfile.ZipFile(fmu, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(export_dir / "modelDescription.xml", "modelDescription.xml")
        if binary is not None:
            archive.write(binary, f"binaries/{plat}/{binary.name}")
        for path in sorted(src.iterdir()):
            archive.write(path, f"sources/{path.name}")
    result.fmu = fmu
    result.ok = (
        result.error is None
        and not result.forbidden_symbols
        and result.cxx_ok is not False
        and (cc is None or result.allocations_after_instantiate == 0)
    )
    return result
