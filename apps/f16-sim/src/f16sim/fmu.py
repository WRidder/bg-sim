"""The flight model: the f16-sim FMU (co-simulation, FMI 2.0) driven through fmpy.

The FMU is exported by bg-sim (``examples/export_f16.jl``) with a fixed communication step of
5 ms and an explicit fixed-step integrator inside (the export report says which, see
``build/build.json``). This class only knows the FMU's interface: the inputs, the outputs and the
parameters, by their FMI names.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

INPUTS = ("stick_pitch", "stick_roll", "pedals", "throttle", "wind_n", "wind_e", "wind_d")
OUTPUTS = (
    "north_m", "east_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg", "gamma_deg",
    "p_dps", "q_dps", "r_dps", "u_mps", "v_mps", "w_mps", "vs_mps", "tas_mps", "cas_mps", "mach", "qbar_pa",
    "alpha_deg", "beta_deg", "nz_g", "ny_g", "stab_deg", "ail_deg", "rdr_deg", "power_pct", "thrust_n",
    "p_lim_dps", "nz_cmd_g", "limiter_active", "departed", "ground_contact",
)
TRIM = ("vt0", "h0", "alpha0", "el0", "thtl0")
SWITCHES = ("limiter", "turn_comp", "roll_law", "yaw_damper", "beta_hold", "ari", "vv_roll")
STEP = 0.005  # s, the communication step the FMU was exported for


@dataclass
class Start:
    """A start condition: a level-flight trim (the five trim globals go together) and the CG."""

    label: str
    vt0: float      # m/s
    h0: float       # m
    alpha0: float   # deg
    el0: float      # deg
    thtl0: float    # 0..1
    xcg: float = 0.35

    @staticmethod
    def load_all(path: Path) -> list["Start"]:
        return [Start(**rec) for rec in json.loads(Path(path).read_text(encoding="utf-8"))]


@dataclass
class Settings:
    """FMU parameters other than the trim: the law switches (1 on, 0 off) and an optional mass."""

    switches: dict[str, float] = field(default_factory=lambda: {k: 1.0 for k in SWITCHES})
    mass: float | None = None   # kg; None keeps the model's mass (the trims are for that mass)


class FlightModel:
    """One FMU instance. ``reset`` (re)instantiates it at a start condition; ``step`` advances
    one communication step with the given inputs; ``y`` holds the outputs after the last step."""

    def __init__(self, fmu: Path, workdir: Path | None = None):
        from fmpy import extract, read_model_description

        self.fmu = Path(fmu)
        if not self.fmu.exists():
            raise FileNotFoundError(f"{self.fmu} does not exist: run `uv run build_fmu.py` first")
        self.md = read_model_description(str(self.fmu))
        self.unzip = extract(str(self.fmu), unzipdir=str(workdir) if workdir else None)
        self._own_unzip = workdir is None
        vr = {v.name: v.valueReference for v in self.md.modelVariables}
        missing = [n for n in INPUTS + OUTPUTS + TRIM if n not in vr]
        if missing:
            raise ValueError(f"the FMU lacks {missing}: rebuild it from the current model")
        self.vr = vr
        self.in_vr = [vr[n] for n in INPUTS]
        self.out_vr = [vr[n] for n in OUTPUTS]
        self.index = {n: k for k, n in enumerate(OUTPUTS)}
        exp = self.md.defaultExperiment
        self.step_size = float(exp.stepSize) if exp is not None and exp.stepSize else STEP
        self.slave = None
        self.time = 0.0
        self.y = np.zeros(len(OUTPUTS))
        self.u = np.zeros(len(INPUTS))
        self.start: Start | None = None

    def reset(self, start: Start, settings: Settings | None = None) -> None:
        from fmpy.fmi2 import FMU2Slave

        settings = settings or Settings()
        # fmpy's freeInstance also unloads the library, so a reset is a fresh FMU2Slave.
        self.close_instance()
        self.slave = FMU2Slave(guid=self.md.guid, unzipDirectory=self.unzip,
                               modelIdentifier=self.md.coSimulation.modelIdentifier, instanceName="f16sim")
        self.slave.instantiate()
        params = {"vt0": start.vt0, "h0": start.h0, "alpha0": start.alpha0, "el0": start.el0, "thtl0": start.thtl0,
                  "xcg": start.xcg, **{k: float(v) for k, v in settings.switches.items()}}
        if settings.mass is not None:
            params["mass"] = settings.mass
        self.slave.setReal([self.vr[k] for k in params], list(params.values()))
        self.slave.setupExperiment(startTime=0.0)
        self.slave.enterInitializationMode()
        self.slave.exitInitializationMode()
        self.time = 0.0
        self.start = start
        self.u[:] = 0.0
        self.u[INPUTS.index("throttle")] = start.thtl0
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

    def snapshot(self) -> dict[str, float]:
        return {n: float(v) for n, v in zip(OUTPUTS, self.y)}

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


def body_to_ned(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """Rotation matrix of the body (x forward, y right, z down) to NED from the FMU's quaternion."""
    w, x, y, z = qw, qx, qy, qz
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def euler_to_ned(phi: float, theta: float, psi: float) -> np.ndarray:
    """The same rotation from the 3-2-1 Euler angles (rad)."""
    cf, sf, ct, st, cp, sp = np.cos(phi), np.sin(phi), np.cos(theta), np.sin(theta), np.cos(psi), np.sin(psi)
    return np.array([
        [ct * cp, sf * st * cp - cf * sp, cf * st * cp + sf * sp],
        [ct * sp, sf * st * sp + cf * cp, cf * st * sp - sf * cp],
        [-st, sf * ct, cf * ct],
    ])
