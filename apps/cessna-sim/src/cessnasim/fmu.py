"""The flight model: the cessna-sim FMU (co-simulation, FMI 2.0) driven through fmpy.

The FMU is exported by bg-sim (``examples/export_cessna.jl``) with a fixed communication step of
5 ms and an explicit fixed-step integrator inside (``build/build.json`` says which). It is the
whole aircraft: the airframe on its landing gear, the engine and propeller, the flaps and the
autopilot. This class only knows its interface: inputs, outputs and the start parameters, by
their FMI names.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

INPUTS = (
    "yoke_pitch", "yoke_roll", "pedals", "throttle", "mixture", "flaps", "trim", "brake_l", "brake_r",
    "ap_roll_mode", "ap_alt_mode", "ap_hdg_deg", "ap_alt_m", "wind_n", "wind_e", "wind_d",
)
OUTPUTS = (
    "north_m", "east_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg", "kias", "ktas",
    "vs_fpm", "alt_ft", "agl_ft", "turn_dps", "slip", "on_ground", "alpha_deg", "beta_deg", "gs_mps", "rpm", "hp",
    "map_inhg", "ff_gph", "thrust_n", "flap_deg", "elevator_deg", "aileron_deg", "rudder_deg", "steer_rad",
    "prop_angle", "stall_flag", "fn_nose", "fn_left", "fn_right", "ap_pitch", "ap_roll",
)
# the start state: set together (a trim or the runway equilibrium, build/starts.json)
START = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
         "hrot0", "map0", "xad0", "flap0", "qn0", "ql0", "qr0")
STEP = 0.005  # s, the communication step the FMU was exported for


@dataclass
class Start:
    """A start condition: the FMU's start parameters and the controls that hold it."""

    label: str
    values: dict[str, float]                      # START -> value
    controls: dict[str, float] = field(default_factory=dict)   # INPUTS -> value at the start
    airborne: bool = False

    @staticmethod
    def load_all(path: Path) -> list["Start"]:
        return [Start(**rec) for rec in json.loads(Path(path).read_text(encoding="utf-8"))]


class FlightModel:
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
        missing = [n for n in INPUTS + OUTPUTS + START if n not in vr]
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

    def reset(self, start: Start, u0=None) -> None:
        from fmpy.fmi2 import FMU2Slave

        # fmpy's freeInstance also unloads the library, so a reset is a fresh FMU2Slave.
        self.close_instance()
        self.slave = FMU2Slave(guid=self.md.guid, unzipDirectory=self.unzip,
                               modelIdentifier=self.md.coSimulation.modelIdentifier, instanceName="cessnasim")
        self.slave.instantiate()
        self.slave.setReal([self.vr[k] for k in START], [float(start.values[k]) for k in START])
        self.slave.setupExperiment(startTime=0.0)
        self.slave.enterInitializationMode()
        self.slave.exitInitializationMode()
        self.time = 0.0
        self.start = start
        self.u[:] = default_inputs(start) if u0 is None else u0
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


def default_inputs(start: Start) -> np.ndarray:
    """The inputs at a start: its controls, full-rich mixture and the autopilot off otherwise."""
    u = np.zeros(len(INPUTS))
    u[INPUTS.index("mixture")] = 1.0
    for k, v in start.controls.items():
        if k in INPUTS:
            u[INPUTS.index(k)] = v
    return u


def body_to_world(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """Rotation matrix of the body (x forward, y left, z up) to the model's world (x north,
    y west, z up) from the FMU's quaternion."""
    w, x, y, z = qw, qx, qy, qz
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def euler_to_world(phi: float, theta: float, psi: float) -> np.ndarray:
    """The same rotation from the aviation Euler angles (rad: bank right, nose up, heading
    clockwise from north)."""
    cf, sf, ct, st, cp, sp = np.cos(phi), np.sin(phi), np.cos(theta), np.sin(theta), np.cos(psi), np.sin(psi)
    R_ned = np.array([
        [ct * cp, sf * st * cp - cf * sp, cf * st * cp + sf * sp],
        [ct * sp, sf * st * sp + cf * cp, cf * st * sp - sf * cp],
        [-st, sf * ct, cf * ct],
    ])
    F = np.diag([1.0, -1.0, -1.0])   # NED <-> (north, west, up) and FRD <-> FLU
    return F @ R_ned @ F
