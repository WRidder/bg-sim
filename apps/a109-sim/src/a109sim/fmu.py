"""The flight model: the a109-sim FMU (co-simulation, FMI 2.0) driven through fmpy.

The FMU is exported by bg-sim (``apps/a109-sim/export_fmu.jl``) with a fixed communication step of
5 ms and an explicit fixed-step integrator inside (``build/build.json`` says which). It is the
whole helicopter: the airframe on its landing gear, the main and tail rotor, the drivetrain with
its governor, the rigging and the SCAS. This class only knows its interface: inputs, outputs and
the start parameters, by their FMI names.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

INPUTS = ("collective", "cyclic_lon", "cyclic_lat", "pedals", "wind_n", "wind_e", "wind_d", "scas")
OUTPUTS = (
    "north_m", "east_m", "alt_m", "phi_deg", "theta_deg", "psi_deg", "p_dps", "q_dps", "r_dps",
    "u_mps", "v_mps", "w_mps", "vs_mps", "tas_mps", "kts", "beta_deg", "rotor_pct", "power_hp", "thrust_n",
    "a1_deg", "b1_deg", "theta0_deg", "B1_deg", "A1_deg", "theta_tr_deg", "fn_nose", "fn_left", "fn_right", "wow",
)
# the start state: set together (a trim, or the helicopter parked on its gear; build/starts.json)
START = ("qw0", "qx0", "qy0", "qz0", "x0", "y0", "z0", "Pwx0", "Pwy0", "Pwz0", "Pvx0", "Pvy0", "Pvz0",
         "a10", "b10", "Lrot0", "xi0")
STEP = 0.005  # s, the communication step the FMU was exported for


@dataclass
class Start:
    """A start condition: the FMU's start parameters, the controls that hold it and the time the
    host lets it settle before the flight starts (the parked helicopter settles on its gear)."""

    label: str
    values: dict[str, float]                      # START -> value
    controls: dict[str, float] = field(default_factory=dict)   # INPUTS -> value at the start
    airborne: bool = False
    settle: float = 0.0

    @staticmethod
    def load_all(path: Path) -> list["Start"]:
        return [Start(**rec) for rec in json.loads(Path(path).read_text(encoding="utf-8"))]


class FlightModel:
    """One FMU instance. ``reset`` (re)instantiates it at a start; ``step`` advances one
    communication step with the given inputs; ``y`` holds the outputs after the last step.
    ``time`` is the flight time (from the end of the settling); ``fmu_time`` the FMU's own."""

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
        self.fmu_time = 0.0
        self.t0 = 0.0
        self.y = np.zeros(len(OUTPUTS))
        self.u = np.zeros(len(INPUTS))
        self.start: Start | None = None

    @property
    def time(self) -> float:
        return self.fmu_time - self.t0

    def reset(self, start: Start, u0=None) -> None:
        from fmpy.fmi2 import FMU2Slave

        # fmpy's freeInstance also unloads the library, so a reset is a fresh FMU2Slave.
        self.close_instance()
        self.slave = FMU2Slave(guid=self.md.guid, unzipDirectory=self.unzip,
                               modelIdentifier=self.md.coSimulation.modelIdentifier, instanceName="a109sim")
        self.slave.instantiate()
        self.slave.setReal([self.vr[k] for k in START], [float(start.values[k]) for k in START])
        self.slave.setupExperiment(startTime=0.0)
        self.slave.enterInitializationMode()
        self.slave.exitInitializationMode()
        self.fmu_time = self.t0 = 0.0
        self.start = start
        self.u[:] = default_inputs(start) if u0 is None else u0
        self.slave.setReal(self.in_vr, list(self.u))
        self.y[:] = self.slave.getReal(self.out_vr)
        # the parked start settles on its gear (and the governor on the flat-pitch torque) with the
        # start's controls before the flight time starts
        for _ in range(round(start.settle / self.step_size)):
            self.step(self.u)
        self.t0 = self.fmu_time

    def step(self, u) -> None:
        """One communication step with the inputs ``u`` (in INPUTS order) held over it."""
        self.u[:] = u
        self.slave.setReal(self.in_vr, list(self.u))
        self.slave.doStep(currentCommunicationPoint=self.fmu_time, communicationStepSize=self.step_size)
        self.fmu_time += self.step_size
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
    """The inputs at a start: its controls, the SCAS on and calm air otherwise."""
    u = np.zeros(len(INPUTS))
    u[INPUTS.index("scas")] = 1.0
    for k, v in start.controls.items():
        if k in INPUTS:
            u[INPUTS.index(k)] = v
    return u


def euler_to_world(phi: float, theta: float, psi: float) -> np.ndarray:
    """Rotation matrix of the body (x forward, y left, z up) to the model's world (x north, y west,
    z up) from the aviation Euler angles (rad: bank right, nose up, heading clockwise from north)."""
    cf, sf, ct, st, cp, sp = np.cos(phi), np.sin(phi), np.cos(theta), np.sin(theta), np.cos(psi), np.sin(psi)
    R_ned = np.array([
        [ct * cp, sf * st * cp - cf * sp, cf * st * cp + sf * sp],
        [ct * sp, sf * st * sp + cf * cp, cf * st * sp - sf * cp],
        [-st, sf * ct, cf * ct],
    ])
    F = np.diag([1.0, -1.0, -1.0])   # NED <-> (north, west, up) and FRD <-> FLU
    return F @ R_ned @ F


def ground_velocity(y: dict[str, float] | "FlightModel") -> tuple[float, float, float]:
    """The velocity over the ground (north, east, up; m/s) from the body velocities u, v, w (the
    FMU's inertial body-axis velocities, FRD) and the attitude."""
    R = euler_to_world(*np.radians([y["phi_deg"], y["theta_deg"], y["psi_deg"]]))
    v = R @ np.array([y["u_mps"], -y["v_mps"], -y["w_mps"]])      # FRD -> FLU, then to (north, west, up)
    return float(v[0]), float(-v[1]), float(v[2])
