"""Build the batched C environment (rl/cenv/bgenv.c) against an export's sources, and load it.

The compiler is the one the FMU build uses (``bgsim_server.fmu_build.find_compiler``: BGSIM_CC,
gcc/clang on PATH, or MSYS2's gcc), with the FMU build's flags plus ``-fopenmp``. The generated
``model.c`` and the runtime (without the FMI wrapper) are linked into one shared library.
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from . import RL, ROOT

sys.path.insert(0, str(ROOT / "backend" / "src"))
from bgsim_server.fmu_build import C_FLAGS, _tool_env, find_compiler  # noqa: E402

SOURCES = ("model.c", "bg_solver.c", "bg_intrinsics.c", "bg_mech.c")


def state_names(export_dir: Path) -> list[str]:
    """The state names from the ``/* x[k] = name */`` comments of the generated model.c."""
    text = (Path(export_dir) / "sources" / "model.c").read_text(encoding="utf-8")
    found = {int(k): name for k, name in re.findall(r"/\* x\[(\d+)\] = (.+?) \*/", text)}
    return [found[k] for k in range(len(found))]


def output_names(export_dir: Path) -> list[str]:
    import json

    report = json.loads((Path(export_dir) / "export.json").read_text(encoding="utf-8"))
    return [o["name"] for o in report["outputs"]] + list(report.get("locals", []))


def build(export_dir: Path, out_dir: Path | None = None, openmp: bool = True) -> Path:
    export_dir = Path(export_dir)
    src = export_dir / "sources"
    out_dir = Path(out_dir or export_dir / "cenv")
    out_dir.mkdir(parents=True, exist_ok=True)
    cc = find_compiler()
    if cc is None:
        raise RuntimeError("no C compiler (BGSIM_CC, gcc/clang on PATH, or MSYS2)")
    env = _tool_env(cc)
    lib = out_dir / ("bgenv.dll" if os.name == "nt" else "libbgenv.so")
    flags = [*C_FLAGS, "-fPIC"] + (["-fopenmp"] if openmp else [])
    objs = []
    for name in (*SOURCES, "bgenv.c"):
        path = (RL / "cenv" / name) if name == "bgenv.c" else (src / name)
        obj = out_dir / (Path(name).stem + ".o")
        if not obj.exists() or obj.stat().st_mtime < path.stat().st_mtime:
            cmd = [cc, *flags, "-c", str(path), "-I", str(src), "-o", str(obj)]
            r = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"compiling {name} failed:\n{r.stdout}{r.stderr}")
        objs.append(str(obj))
    link = [cc, "-shared", "-static-libgcc", *objs, "-o", str(lib), "-lm"]
    if openmp:
        link.insert(2, "-fopenmp")
        if os.name == "nt":
            link += ["-Wl,-Bstatic", "-lgomp", "-lpthread", "-Wl,-Bdynamic"]
    r = subprocess.run(link, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("linking bgenv failed:\n" + r.stdout + r.stderr)
    return lib


_DLL_DIRS: list = []


def load(lib: Path) -> ctypes.CDLL:
    cc = find_compiler()
    if os.name == "nt" and cc is not None:
        _DLL_DIRS.append(os.add_dll_directory(str(Path(cc).parent)))  # libgomp, libwinpthread
    dll = ctypes.CDLL(str(lib))
    P = ctypes.c_void_p
    D = ctypes.POINTER(ctypes.c_double)
    I = ctypes.POINTER(ctypes.c_int)
    B = ctypes.POINTER(ctypes.c_ubyte)
    sig = {
        "bgenv_nx": ([], ctypes.c_int), "bgenv_np": ([], ctypes.c_int), "bgenv_nu": ([], ctypes.c_int),
        "bgenv_ny": ([], ctypes.c_int), "bgenv_dt": ([], ctypes.c_double), "bgenv_method": ([], ctypes.c_int),
        "bgenv_p_name": ([ctypes.c_int], ctypes.c_char_p), "bgenv_u_name": ([ctypes.c_int], ctypes.c_char_p),
        "bgenv_p_kind": ([ctypes.c_int], ctypes.c_int), "bgenv_p_min": ([ctypes.c_int], ctypes.c_double),
        "bgenv_p_max": ([ctypes.c_int], ctypes.c_double), "bgenv_p0": ([ctypes.c_int], ctypes.c_double),
        "bgenv_set_threads": ([ctypes.c_int], None), "bgenv_threads": ([], ctypes.c_int),
        "bgenv_create": ([ctypes.c_int], P), "bgenv_free": ([P], None),
        "bgenv_reset": ([P, B, I, ctypes.c_int, D, I, ctypes.c_int, D], ctypes.c_int),
        "bgenv_step": ([P, D, ctypes.c_int, D, I], ctypes.c_int),
        "bgenv_plant_seconds": ([P], ctypes.c_double), "bgenv_outputs": ([P, D], None),
        "bgenv_get_x": ([P, D], None), "bgenv_set_x": ([P, ctypes.c_int, D], None),
        "bgenv_time": ([P, ctypes.c_int], ctypes.c_double),
    }
    for name, (args, res) in sig.items():
        f = getattr(dll, name)
        f.argtypes = args
        f.restype = res
    return dll


def ptr(a: np.ndarray, ctype=ctypes.c_double):
    return a.ctypes.data_as(ctypes.POINTER(ctype))


class BatchedPlant:
    """N instances of the exported plant, stepped together (numpy in, numpy out)."""

    def __init__(self, export_dir: Path, n: int, threads: int = 1, lib: Path | None = None):
        self.export_dir = Path(export_dir)
        self.dll = load(lib or build(self.export_dir))
        d = self.dll
        self.nx, self.np_, self.nu, self.ny = d.bgenv_nx(), d.bgenv_np(), d.bgenv_nu(), d.bgenv_ny()
        self.dt = d.bgenv_dt()
        self.p_names = [d.bgenv_p_name(i).decode() for i in range(self.np_)]
        self.u_names = [d.bgenv_u_name(i).decode() for i in range(self.nu)]
        self.p_kind = [d.bgenv_p_kind(i) for i in range(self.np_)]
        self.p_range = {self.p_names[i]: (d.bgenv_p_min(i), d.bgenv_p_max(i)) for i in range(self.np_)}
        self.p0 = {self.p_names[i]: d.bgenv_p0(i) for i in range(self.np_)}
        self.x_names = state_names(self.export_dir)
        self.y_names = output_names(self.export_dir)
        assert len(self.x_names) == self.nx and len(self.y_names) == self.ny
        self.n = n
        d.bgenv_set_threads(threads)
        self.h = d.bgenv_create(n)
        if not self.h:
            raise MemoryError("bgenv_create")
        self.u = np.zeros((n, self.nu))
        self.y = np.zeros((n, self.ny))
        self.status = np.zeros(n, dtype=np.int32)

    def close(self):
        if self.h:
            self.dll.bgenv_free(self.h)
            self.h = None

    def __del__(self):
        self.close()

    def settable(self) -> list[str]:
        """The parameters set before initialisation (the exposed globals)."""
        return [self.p_names[i] for i in range(self.np_) if self.p_kind[i] == 0]

    def reset(self, mask: np.ndarray | None, params: dict[str, np.ndarray] | None = None,
              states: dict[int, np.ndarray] | None = None) -> None:
        """Reset the instances in ``mask`` (bool, n) with ``params`` (name -> n values) set before
        initialisation and ``states`` (state index -> n values) written after it."""
        m = np.ones(self.n, np.uint8) if mask is None else np.ascontiguousarray(mask, np.uint8)
        params = params or {}
        states = states or {}
        pidx = np.array([self.p_names.index(k) for k in params], dtype=np.int32)
        pv = np.ascontiguousarray(np.stack([np.broadcast_to(v, self.n) for v in params.values()], 1)
                                  if params else np.zeros((self.n, 0)), dtype=float)
        xidx = np.array(list(states), dtype=np.int32)
        xv = np.ascontiguousarray(np.stack([np.broadcast_to(v, self.n) for v in states.values()], 1)
                                  if states else np.zeros((self.n, 0)), dtype=float)
        bad = self.dll.bgenv_reset(self.h, ptr(m, ctypes.c_ubyte), ptr(pidx, ctypes.c_int), len(pidx),
                                   ptr(pv), ptr(xidx, ctypes.c_int), len(xidx), ptr(xv))
        if bad:
            k = bad - 1
            raise ValueError(f"reset of instance {k} refused: a parameter outside its range "
                             f"{ {n: float(pv[k, j]) for j, n in enumerate(params)} } or a failed init")
        self.status[m.astype(bool)] = 0
        self.dll.bgenv_outputs(self.h, ptr(self.y))

    def step(self, u: np.ndarray, nsub: int) -> np.ndarray:
        """Advance every instance by ``nsub`` internal steps with the inputs ``u`` (n x nu)."""
        self.u[:] = u
        self.dll.bgenv_step(self.h, ptr(self.u), nsub, ptr(self.y), ptr(self.status, ctypes.c_int))
        return self.y

    def plant_seconds(self) -> float:
        return self.dll.bgenv_plant_seconds(self.h)

    def get_x(self) -> np.ndarray:
        x = np.zeros((self.n, self.nx))
        self.dll.bgenv_get_x(self.h, ptr(x))
        return x
