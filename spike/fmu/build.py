"""Build an FMU from a generated model directory (spike).

    uv run spike/fmu/build.py spike/fmu/out/<model-dir>

Compiles the generated model.c with the hand-written solver and FMI wrapper (MSYS2 gcc),
checks that the hot-path objects import no allocation or I/O symbols, compiles the sources
as C++ too, runs the allocation/timing harness, and zips the FMU (binary + sources).
"""

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HAND = ["bg_solver.c", "fmi2_cs.c", "bg_runtime.h"]
FMI = HERE / "fmi2"
FORBIDDEN = {"malloc", "calloc", "realloc", "free", "printf", "fprintf", "puts", "fopen",
             "fwrite", "sprintf", "snprintf", "vfprintf", "exit", "abort"}
CFLAGS = ["-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
          "-fno-math-errno"]


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    res = subprocess.run(cmd, text=True, capture_output=True, **kw)
    if res.returncode != 0:
        sys.exit(f"FAIL ({res.returncode}):\n{res.stdout}{res.stderr}")
    return res


def main(model_dir: Path) -> None:
    meta = json.loads((model_dir / "meta.json").read_text())
    ident = meta["identifier"]
    src = model_dir / "sources"
    for f in HAND:
        shutil.copy(HERE / f, src / f)
    for h in FMI.glob("*.h"):
        shutil.copy(h, src / h.name)
    build = model_dir / "build"
    build.mkdir(exist_ok=True)

    # 1. Objects of the hot path, and their undefined symbols.
    objs = []
    for c in ["model.c", "bg_solver.c", "fmi2_cs.c"]:
        o = build / (Path(c).stem + ".o")
        run(["gcc", *CFLAGS, "-c", src / c, "-I", src, "-o", o])
        objs.append(o)
    undefined = set()
    for o in objs:
        out = run(["nm", "-u", o]).stdout.split()
        undefined |= {s.lstrip("_") for s in out if s not in ("U",)}
    bad = sorted(undefined & FORBIDDEN)
    print("undefined symbols of model.o + bg_solver.o + fmi2_cs.o:", sorted(undefined))
    if bad:
        sys.exit(f"FAIL: forbidden symbols in the FMU objects: {bad}")
    print("OK: no allocation or I/O symbols in the FMU objects")

    # 2. The same sources compile as C++.
    for c in ["model.c", "bg_solver.c"]:
        run(["g++", "-x", "c++", "-std=c++17", "-fsyntax-only", "-Wall", "-Werror",
             "-I", src, src / c])
    print("OK: model.c and bg_solver.c compile as C++17")

    # 3. The FMU binary.
    dll = build / f"{ident}.dll"
    run(["gcc", *CFLAGS, "-shared", "-static-libgcc", "-I", src, *[src / c for c in ["model.c", "bg_solver.c", "fmi2_cs.c"]],
         "-o", dll, "-lm"])

    # 4. Allocation and timing harness.
    exe = build / "alloc_check.exe"
    run(["gcc", "-std=c11", "-O2", "-Wall", "-I", src, HERE / "alloc_check.c",
         *[src / c for c in ["model.c", "bg_solver.c", "fmi2_cs.c"]], "-o", exe, "-lm"])
    per = round(1e-3 / meta["dt"])
    res = subprocess.run([str(exe), str(per), "100000"], text=True, capture_output=True)
    print(res.stdout.strip(), res.stderr.strip())
    if res.returncode != 0:
        sys.exit("FAIL: allocation during stepping, or a step failed")

    # 5. Zip the FMU.
    fmu = model_dir / f"{ident}.fmu"
    with zipfile.ZipFile(fmu, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(model_dir / "modelDescription.xml", "modelDescription.xml")
        z.write(dll, f"binaries/win64/{ident}.dll")
        for f in sorted(src.iterdir()):
            z.write(f, f"sources/{f.name}")
    print("wrote", fmu)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
