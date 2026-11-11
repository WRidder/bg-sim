# Planetary set: kinematics

The THS-II planetary set alone. A 60 N·m torque step at 0.5 s on the carrier (the engine)
drives the sun and the ring against viscous loads: 0.05 N·m·s/rad on the sun (inertia 0.02
kg·m²) and 0.4 N·m·s/rad on the ring (0.2 kg·m²).

![Diagram: the bond-graph planetary (top) and the stdlib PlanetaryGear twin (bottom)|900](assets/57ee6b6323e6.png)

Blocks: [Engine](block:Engine) (MSe, fed by [EngineStep](block:EngineStep)) on the
[Carrier](block:Carrier) 1-junction, the [Planetary](block:Planetary) subsystem (TFc, TFs, TFr
around the mesh 0-junction), the [Sun](block:Sun) and [Ring](block:Ring) 1-junctions with
their inertias and loads. Below them is the same set built with the stdlib
[Gear](block:Gear) (`PlanetaryGear`).

## What it shows

- **Torque split**: [SunTorque/y](signal:SunTorque/y) : [RingTorque/y](signal:RingTorque/y) =
  30 : 78 at every instant, from the mesh force [Planetary/MeshForce/y](signal:Planetary/MeshForce/y).
- **Willis**: $30\,\omega_s + 78\,\omega_r - 108\,\omega_c = 0$ to 1e-15 over the run.
- **Steady state**: $T_s = 30/108 \cdot 60 = 16.67$ N·m $= 0.05\,\omega_s$, so
  [SunSpeed/y](signal:SunSpeed/y) → 333.3 rad/s; $T_r = 43.33$ N·m $= 0.4\,\omega_r$, so
  [RingSpeed/y](signal:RingSpeed/y) → 108.3 rad/s; and [CarrierSpeed/y](signal:CarrierSpeed/y) →
  170.8 rad/s.
- **Power**: [PCarrier/y](signal:PCarrier/y) = [PSun/y](signal:PSun/y) + [PRing/y](signal:PRing/y).

![Speeds and powers; the stdlib twin lies on the bond-graph ring speed|900](assets/58e48eea47ab.png)

## What to try

- Change the teeth on the dashboard (Zs, Zr): the split and the steady speeds follow.
- Plot [Ring2Speed/y](signal:Ring2Speed/y) against [RingSpeed/y](signal:RingSpeed/y): the two
  sets agree exactly.
