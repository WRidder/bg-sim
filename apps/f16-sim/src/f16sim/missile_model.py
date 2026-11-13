"""The AIM-9X FMU instances: FMI only, no rendering.

One instance is a fire-and-forget shot. The host sets the launch state and the guidance limits
before initialisation, then feeds the target's launch-relative NED position and velocity every
5 ms communication step. The FMU's model frame is x north, y west, z up; its `north_m` and
`west_m` outputs are relative to the launch point, and its `alt_m` is absolute. The launch frame
is rotated to the aircraft's heading by ``Simulation``/``Game``.

The FMU has no ``StopSimulation`` at the fuze: the host latches ``fuze``/``hit`` and retires the
instance after the flash. Instances share one extracted FMU but are never freed one by one:
fmpy's ``freeInstance`` unloads the shared library, so all are kept until reset or app close.
"""

from __future__ import annotations

import math
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

INPUTS = ("target_north_m", "target_east_m", "target_down_m", "target_vn_mps", "target_ve_mps",
          "target_vd_mps", "target_ir_w", "seeker_on")
OUTPUTS = (
    "north_m", "west_m", "alt_m", "q_w", "q_x", "q_y", "q_z", "phi_deg", "theta_deg", "psi_deg",
    "gamma_deg", "vt_mps", "alpha_deg", "beta_deg", "qbar_pa", "mach", "n_z_g", "n_y_g", "mass_kg",
    "lock", "range_m", "range_rate_mps", "min_range_m", "t_go_s", "fuze", "hit", "thrust_n",
    "fin1_deg", "fin2_deg", "fin3_deg", "fin4_deg", "p_dps", "q_dps", "r_dps",
)
OUT = {name: i for i, name in enumerate(OUTPUTS)}
PARAMS = ("vt0", "h0", "alpha0", "tvc_on", "nav_N", "a_max_g")
STEP = 0.005
T_REF = 20000.0
IR_W = 1.0e6


@dataclass(frozen=True)
class Launch:
    """Where and how a shot leaves the aircraft: world NED position, heading and true speed."""

    north: float
    east: float
    alt: float
    heading_deg: float
    speed: float
    station: int


@dataclass
class Missile:
    id: int
    launch: Launch
    target_id: int
    model: MissileModel
    time: float = 0.0
    y_prev: np.ndarray = field(default_factory=lambda: np.zeros(len(OUTPUTS)))
    y: np.ndarray = field(default_factory=lambda: np.zeros(len(OUTPUTS)))
    fuze_latched: bool = False
    done_at: float | None = None
    done: bool = False
    killed: bool = False

    @property
    def fuze(self) -> float:
        return float(self.y[OUT["fuze"]])

    @property
    def hit(self) -> float:
        return float(self.y[OUT["hit"]])

    @property
    def thrust(self) -> float:
        return float(self.y[OUT["thrust_n"]])

    def step(self, target: object | None) -> None:
        if self.done:
            return
        self.y_prev[:] = self.y
        self.model.set_inputs(target_input(self.launch, target) if target is not None else self.model.u)
        self.model.step()
        self.time += self.model.step_size
        self.y[:] = self.model.y
        if not self.fuze_latched and (self.fuze > 0.5 or self.hit > 0.5):
            self.fuze_latched = True
            self.done_at = self.time
        if self.done_at is not None and self.time >= self.done_at + 0.8:
            self.done = True

    def close(self) -> None:
        self.model.close()


class MissileModel:
    """One FMI co-simulation instance (FMI 2.0), built by ``build_fmu.py``."""

    def __init__(self, md, unzip: str, instance: str):
        from fmpy.fmi2 import FMU2Slave

        self.md = md
        self.step_size = float(md.defaultExperiment.stepSize) if md.defaultExperiment else STEP
        self.slave = FMU2Slave(guid=md.guid, unzipDirectory=unzip,
                               modelIdentifier=md.coSimulation.modelIdentifier,
                               instanceName=instance)
        self.slave.instantiate()
        self.u = np.zeros(len(INPUTS))
        self.time = 0.0

    def start(self, vt0: float, h0: float, inputs) -> None:
        vr = self.vr()
        params = {
            "vt0": min(700.0, max(100.0, vt0)),
            "h0": min(20000.0, max(0.0, h0)),
            "alpha0": 2.0,
            "tvc_on": 1.0,
            "nav_N": 4.0,
            "a_max_g": 60.0,
        }
        self.slave.setReal([vr[k] for k in PARAMS], [params[k] for k in PARAMS])
        self.slave.setupExperiment(startTime=0.0, stopTime=100.0)
        self.slave.enterInitializationMode()
        self.slave.exitInitializationMode()
        self.set_inputs(inputs)
        self.y = np.asarray(self.slave.getReal(self.out_vr), dtype=float)
        self.time = 0.0

    def vr(self) -> dict[str, int]:
        if not hasattr(self, "_vr"):
            self._vr = {v.name: v.valueReference for v in self.md.modelVariables}
            missing = [n for n in INPUTS + OUTPUTS + PARAMS if n not in self._vr]
            if missing:
                raise ValueError(f"the AIM-9X FMU lacks {missing}: rebuild it from the current model")
            self.in_vr = [self._vr[n] for n in INPUTS]
            self.out_vr = [self._vr[n] for n in OUTPUTS]
        return self._vr

    def set_inputs(self, u) -> None:
        self.vr()
        self.u[:] = np.asarray(u, dtype=float)
        self.slave.setReal(self.in_vr, [float(v) for v in self.u])

    def step(self) -> None:
        self.slave.doStep(currentCommunicationPoint=self.time, communicationStepSize=self.step_size)
        self.time += self.step_size
        self.y = np.asarray(self.slave.getReal(self.out_vr), dtype=float)

    def close(self) -> None:
        try:
            self.slave.terminate()
            self.slave.freeInstance()
        except Exception:  # noqa: BLE001 - closing after an FMU error
            self.slave = None
        else:
            self.slave = None


class MissileManager:
    """The live shots and the FMU extraction shared by them."""

    def __init__(self, fmu: Path, max_shots: int = 2):
        from fmpy import extract, read_model_description

        self.fmu = Path(fmu)
        if not self.fmu.exists():
            raise FileNotFoundError(f"{self.fmu} does not exist: run `uv run build_fmu.py` first")
        self.md = read_model_description(str(self.fmu))
        self.unzip = tempfile.mkdtemp(prefix="f16sim-aim9x-")
        extract(str(self.fmu), unzipdir=self.unzip)
        self.max_shots = max_shots
        self.missiles: list[Missile] = []
        self.next_id = 1
        self.used: set[int] = set()
        self.step_size = STEP

    def fire(self, launch: Launch, target) -> Missile | None:
        if len(self.used) >= self.max_shots or launch.station in self.used:
            return None
        model = MissileModel(self.md, self.unzip, f"aim9x-{self.next_id}")
        try:
            model.start(launch.speed, launch.alt, target_input(launch, target))
        except Exception:
            model.close()
            raise
        missile = Missile(self.next_id, launch, target.id, model)
        missile.y[:] = model.y
        missile.y_prev[:] = model.y
        self.next_id += 1
        self.used.add(launch.station)
        self.missiles.append(missile)
        return missile

    def step(self, drones) -> None:
        for m in self.missiles:
            target = drones.by_id(m.target_id)
            m.step(target if target is not None and target.alive else None)
            if m.fuze_latched and not m.killed:
                drones.kill(m.target_id)
                m.killed = True

    def reset(self) -> None:
        for m in self.missiles:
            m.close()
        self.missiles.clear()
        self.used.clear()
        self.next_id = 1

    def close(self) -> None:
        self.reset()
        shutil.rmtree(self.unzip, ignore_errors=True)


def target_input(launch: Launch, drone) -> list[float]:
    """Launch-relative NED target data for the FMU (down is absolute, i.e. -altitude)."""
    psi = math.radians(launch.heading_deg)
    c, s = math.cos(psi), math.sin(psi)
    dn, de = drone.north - launch.north, drone.east - launch.east
    vn = drone.speed * math.cos(math.radians(drone.heading_deg))
    ve = drone.speed * math.sin(math.radians(drone.heading_deg))
    return [c * dn + s * de, -s * dn + c * de, -drone.alt,
            c * vn + s * ve, -s * vn + c * ve, 0.0, IR_W, 1.0]


def local_to_world(launch: Launch, north_m: float, west_m: float, alt_m: float) -> tuple[float, float, float]:
    """The model's launch-local north/west and absolute altitude in world north/east/alt."""
    psi = math.radians(launch.heading_deg)
    c, s = math.cos(psi), math.sin(psi)
    return (launch.north + c * north_m + s * west_m,
            launch.east + s * north_m - c * west_m,
            alt_m)


def attitude_world(launch: Launch, qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """Model FLU-in-local-NWU quaternion -> global NED body-to-NED matrix (body FRD)."""
    from .fmu import body_to_ned

    # NWU -> NED and FLU -> FRD both flip y and z: q becomes (w, x, -y, -z).
    R_local = body_to_ned(qw, qx, -qy, -qz)
    psi = math.radians(launch.heading_deg)
    c, s = math.cos(psi), math.sin(psi)
    Rz = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
    return Rz @ R_local
