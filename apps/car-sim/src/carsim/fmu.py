"""The vehicle model: the racecar-sim or buggy-sim FMU (co-simulation, FMI 2.0) driven through fmpy.

The FMUs are exported by bg-sim (``examples/export_cars.jl``) with a fixed communication step of
5 ms and a fixed-step integrator inside (the export report says which, see ``build/build.json``).
This class only knows the FMU's interface: the inputs, the outputs and the parameters, by their
FMI names.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

INPUTS = ("steer", "throttle", "brake", "reverse", "handbrake", "mu_fl", "mu_fr", "mu_rl", "mu_rr")
CORNERS = ("fl", "fr", "rl", "rr")
POSE = ("px", "py", "pz", "qw", "qx", "qy", "qz")
REQUIRED = tuple(f"chassis_{k}" for k in POSE) + tuple(f"{c}_{k}" for c in CORNERS for k in POSE) + (
    "speed", "kmh", "yaw", "soc", "battery_v", "battery_a", "battery_w", "motor_r_rpm", "motor_r_torque",
    "motor_r_power", "fl_spin", "fl_xc", "fl_yc")
STEP = 0.005  # s, the communication step the FMUs were exported for


@dataclass
class Start:
    """A start: the chassis CG position and heading, and the battery charge."""

    label: str
    x0: float
    y0: float
    z0: float
    yaw0: float
    soc0: float = 0.9

    @staticmethod
    def load_all(path: Path) -> list["Start"]:
        return [Start(**rec) for rec in json.loads(Path(path).read_text(encoding="utf-8"))]


class VehicleModel:
    """One FMU instance. ``reset`` (re)instantiates it at a start; ``step`` advances one
    communication step with the given inputs; ``y`` holds the outputs after the last step."""

    def __init__(self, fmu: Path, workdir: Path | None = None):
        from fmpy import extract, read_model_description

        self.fmu = Path(fmu)
        if not self.fmu.exists():
            raise FileNotFoundError(f"{self.fmu} does not exist: run `uv run build_fmu.py` first")
        self.md = read_model_description(str(self.fmu))
        self.unzip = extract(str(self.fmu), unzipdir=str(workdir) if workdir else None)
        self._own_unzip = workdir is None
        vr = {v.name: v.valueReference for v in self.md.modelVariables}
        self.outputs = tuple(v.name for v in self.md.modelVariables if v.causality == "output")
        missing = [n for n in INPUTS + REQUIRED + ("x0", "y0", "z0", "yaw0", "soc0") if n not in vr]
        if missing:
            raise ValueError(f"the FMU lacks {missing}: rebuild it from the current model")
        self.vr = vr
        self.in_vr = [vr[n] for n in INPUTS]
        self.out_vr = [vr[n] for n in self.outputs]
        self.index = {n: k for k, n in enumerate(self.outputs)}
        exp = self.md.defaultExperiment
        self.step_size = float(exp.stepSize) if exp is not None and exp.stepSize else STEP
        self.slave = None
        self.time = 0.0
        self.y = np.zeros(len(self.outputs))
        self.u = np.zeros(len(INPUTS))
        self.motors = [m for m in ("f", "r") if f"motor_{m}_rpm" in vr]

    def reset(self, start: Start, params: dict[str, float] | None = None) -> None:
        from fmpy.fmi2 import FMU2Slave

        # fmpy's freeInstance also unloads the library, so a reset is a fresh FMU2Slave.
        self.close_instance()
        self.slave = FMU2Slave(guid=self.md.guid, unzipDirectory=self.unzip,
                               modelIdentifier=self.md.coSimulation.modelIdentifier, instanceName="carsim")
        self.slave.instantiate()
        p = {"x0": start.x0, "y0": start.y0, "z0": start.z0, "yaw0": start.yaw0, "soc0": start.soc0, **(params or {})}
        self.slave.setReal([self.vr[k] for k in p], [float(v) for v in p.values()])
        self.slave.setupExperiment(startTime=0.0)
        self.slave.enterInitializationMode()
        self.slave.exitInitializationMode()
        self.time = 0.0
        self.u[:] = 0.0
        self.u[INPUTS.index("mu_fl"):] = 1.0
        self.slave.setReal(self.in_vr, list(self.u))
        self.y[:] = self.slave.getReal(self.out_vr)

    def step(self, u) -> None:
        """One communication step with the inputs ``u`` (in INPUTS order) held over it."""
        self.u[:] = u
        self.slave.setReal(self.in_vr, list(self.u))
        self.slave.doStep(currentCommunicationPoint=self.time, communicationStepSize=self.step_size)
        self.time += self.step_size
        self.y[:] = self.slave.getReal(self.out_vr)

    def __getitem__(self, name: str) -> float:
        return float(self.y[self.index[name]])

    def get(self, name: str, default: float = 0.0) -> float:
        k = self.index.get(name)
        return default if k is None else float(self.y[k])

    def snapshot(self) -> dict[str, float]:
        return {n: float(v) for n, v in zip(self.outputs, self.y)}

    def close_instance(self) -> None:
        if self.slave is not None:
            try:
                self.slave.terminate()
                self.slave.freeInstance()
            except Exception:  # noqa: BLE001 - closing after an FMU error
                pass
            self.slave = None

    def close(self) -> None:
        self.close_instance()
        if self._own_unzip:
            shutil.rmtree(self.unzip, ignore_errors=True)


def quat_matrix(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """Rotation matrix of a unit quaternion (body to world; both z up, right-handed)."""
    s = qw * qw + qx * qx + qy * qy + qz * qz
    w, x, y, z = qw, qx, qy, qz
    return np.array([
        [w * w + x * x - y * y - z * z, 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), w * w - x * x + y * y - z * z, 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), w * w - x * x - y * y + z * z],
    ]) / s
