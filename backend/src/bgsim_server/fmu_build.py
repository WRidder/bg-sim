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
   ``fmi2Instantiate`` over ``harness_steps`` ``fmi2DoStep`` calls, and the step time;
5. zip ``modelDescription.xml``, ``binaries/<platform>/`` and ``sources/``.

A source-only FMU is still written when no compiler is found (D-EX15). Either way the build
results go into ``export.json`` as ``build`` (the ``ExportBuild`` contract in
``contracts/schemas/export-report.schema.json``). The compiler is ``BGSIM_CC``, a gcc or
clang on PATH, or MSYS2's gcc in its default place; its folder is put first on PATH for the
build commands, so MSYS2's gcc finds its DLLs. Cross targets (``zig cc``, P-EX2) are not part
of this module yet.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
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

#: Where MSYS2 installs a compiler on Windows; tried after ``BGSIM_CC`` and PATH.
WINDOWS_COMPILERS = ("C:/msys64/mingw64/bin/gcc.exe", "C:/msys64/ucrt64/bin/gcc.exe",
                     "C:/msys64/clang64/bin/clang.exe")

SOURCE_ONLY_NOTE = ("no C compiler was found (BGSIM_CC, gcc or clang on PATH, or MSYS2 in "
                    "C:/msys64), so the FMU holds the sources only; compile them for the target")


@dataclass
class BuildResult:
    """What ``build_fmu`` did. ``ok`` is false when a check failed or the build broke."""

    fmu: Path | None = None
    ok: bool = False
    platform: str | None = None
    compiler: str | None = None
    undefined_symbols: list[str] = field(default_factory=list)
    forbidden_symbols: list[str] = field(default_factory=list)
    symbol_check_ran: bool = False
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
    """``BGSIM_CC``, a gcc or clang on PATH, or MSYS2's compiler on Windows.

    The ``cl`` on PATH may be Open Watcom (D-EX15), so it is never used."""
    override = os.environ.get("BGSIM_CC")
    if override:
        return shutil.which(override) or (override if Path(override).is_file() else None)
    for name in ("gcc", "clang", "cc"):
        path = shutil.which(name)
        if path:
            return path
    if platform.system() == "Windows":
        for candidate in WINDOWS_COMPILERS:
            if Path(candidate).is_file():
                return candidate
    return None


def harness_steps_for(substeps: int) -> int:
    """``doStep`` calls of the counting harness: 20000, fewer when one ``doStep`` takes many
    internal steps (at least 200), as the X-EX0 gate does."""
    return max(200, min(20_000, 20_000_000 // max(1, int(substeps))))


def _tool_env(cc: str | None) -> dict[str, str] | None:
    """The environment with the compiler's folder first on PATH (MSYS2 needs its DLLs)."""
    if cc is None:
        return None
    env = dict(os.environ)
    env["PATH"] = str(Path(cc).parent) + os.pathsep + env.get("PATH", "")
    return env


def _cxx_for(cc: str) -> str | None:
    base = Path(cc).name.lower()
    names = ["g++"] if base.startswith("gcc") else ["clang++"] if "clang" in base else []
    suffix = Path(cc).suffix
    for name in names + ["c++"]:
        sibling = Path(cc).with_name(name + suffix)
        if sibling.exists():
            return str(sibling)
        path = shutil.which(name)
        if path:
            return path
    return None


def _nm_for(cc: str) -> str | None:
    sibling = Path(cc).with_name("nm.exe" if Path(cc).suffix.lower() == ".exe" else "nm")
    if sibling.exists():
        return str(sibling)
    return shutil.which("nm") or shutil.which("llvm-nm")


def _run(cmd: list, result: BuildResult, env: dict[str, str] | None = None
         ) -> subprocess.CompletedProcess:
    result.log.append(" ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], text=True, capture_output=True, env=env)


def _library_suffix(plat: str) -> str:
    return ".dll" if plat.startswith("win") else ".dylib" if plat.startswith("darwin") else ".so"


def build_fmu(export_dir: Path, *, runtime_dir: Path, harness_steps: int = 100_000,
              compiler: str | None = None) -> BuildResult:
    """Compile, check and zip the export in ``export_dir`` into ``<identifier>.fmu``.

    ``runtime_dir`` is ``julia/BGSim/export/runtime`` (it holds the harness). The build
    results are written into ``export.json`` as ``build``.
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
    plat = host_platform()
    env = _tool_env(cc)
    started = time.monotonic()
    binary: Path | None = None
    per: int | None = None

    def run(cmd: list) -> subprocess.CompletedProcess:
        return _run(cmd, result, env)

    def finish() -> BuildResult:
        result.ok = (
            result.error is None
            and not result.forbidden_symbols
            and result.cxx_ok is not False
            and (cc is None or result.allocations_after_instantiate == 0)
        )
        # The build results join the export report (plan 5.2, step 4; ExportBuild).
        report["build"] = {
            "compilerFound": cc is not None, "compiler": cc,
            "sourceOnly": result.fmu is not None and binary is None,
            "platform": result.platform, "ok": result.ok,
            "forbiddenSymbols": result.forbidden_symbols,
            "symbolCheck": (not result.forbidden_symbols) if result.symbol_check_ran else None,
            "cxxOk": result.cxx_ok,
            "harnessDoSteps": harness_steps if result.allocations_after_instantiate is not None
            else None,
            "internalStepsPerDoStep": per,
            "allocationsAfterInstantiate": result.allocations_after_instantiate,
            "doStepMeanUs": result.step_time_mean_us, "doStepMaxUs": result.step_time_max_us,
            "buildS": time.monotonic() - started,
            "error": result.error,
            "note": SOURCE_ONLY_NOTE if cc is None else None,
        }
        (export_dir / "export.json").write_text(json.dumps(report, indent=4), encoding="utf-8")
        return result

    if cc is not None:
        objects = []
        for name in HOT_PATH_SOURCES:
            obj = build / (Path(name).stem + ".o")
            res = run([cc, *C_FLAGS, "-c", src / name, "-I", src, "-o", obj])
            if res.returncode != 0:
                result.error = f"compiling {name} failed:\n{res.stdout}{res.stderr}"
                return finish()
            objects.append(obj)

        nm = _nm_for(cc)
        if nm is not None:
            undefined: set[str] = set()
            for obj in objects:
                res = run([nm, "-u", obj])
                for token in res.stdout.split():
                    if token != "U":
                        undefined.add(re.sub(r"^_+", "", token))
            result.symbol_check_ran = True
            result.undefined_symbols = sorted(undefined)
            result.forbidden_symbols = sorted(undefined & FORBIDDEN_SYMBOLS)

        cxx = _cxx_for(cc)
        if cxx is not None:
            result.cxx_ok = all(
                run([cxx, "-x", "c++", "-std=c++17", "-fsyntax-only", "-Wall", "-Werror",
                     "-I", src, src / name]).returncode == 0
                for name in ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c"))

        library = build / (ident + _library_suffix(plat))
        res = run([cc, *C_FLAGS, "-shared", "-fPIC", "-static-libgcc", "-I", src,
                   *[src / n for n in HOT_PATH_SOURCES], "-o", library, "-lm"])
        if res.returncode != 0:
            result.error = f"linking the FMU binary failed:\n{res.stdout}{res.stderr}"
            return finish()
        binary = library
        result.platform = plat

        harness = build / ("alloc_check" + (".exe" if plat.startswith("win") else ""))
        res = run([cc, "-std=c11", "-O2", "-I", src, runtime_dir / "alloc_check.c",
                   *[src / n for n in HOT_PATH_SOURCES], "-o", harness, "-lm"])
        if res.returncode != 0:
            result.error = f"building the allocation harness failed:\n{res.stdout}{res.stderr}"
            return finish()
        per = max(1, round(report["step"] / report["dt"]))
        res = run([harness, per, harness_steps])
        match = re.search(r"after instantiate (\d+)", res.stdout)
        result.allocations_after_instantiate = int(match.group(1)) if match else None
        match = re.search(r"mean ([0-9.]+) us, max ([0-9.]+) us", res.stdout)
        if match:
            result.step_time_mean_us = float(match.group(1))
            result.step_time_max_us = float(match.group(2))
        if res.returncode not in (0, 1):
            result.error = f"the harness failed (a step diverged?):\n{res.stdout}{res.stderr}"

    fmu = export_dir / f"{ident}.fmu"
    with zipfile.ZipFile(fmu, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(export_dir / "modelDescription.xml", "modelDescription.xml")
        if binary is not None:
            archive.write(binary, f"binaries/{plat}/{binary.name}")
        for path in sorted(src.iterdir()):
            archive.write(path, f"sources/{path.name}")
    result.fmu = fmu
    return finish()
