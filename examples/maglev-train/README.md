# Maglev train

An electromagnetic-suspension (EMS) train in the style of the Transrapid: levitation magnets pull up towards the rail under the guideway, the gap (about 10 mm) is open-loop unstable and is held by state feedback, a long stator (LSM) drives the car, and the car body is a 3D rigid body on a guideway of sagging spans.

All plants are bond graphs. The magnet and coil are the stdlib `converters/Electromagnet` (an energy-conserving IC-field, as in `examples/maglev`), the car body is `spatial/RigidBody3D` on `spatial/Free3D`.

## Models

| model | what it shows |
| --- | --- |
| `maglev-module` | One levitation module carrying a quarter of a car (chassis 1.5 t, body share 11.75 t on a 1 Hz secondary suspension). Lift-off from the skids at 0.45 s, gap regulation at 10 mm, a 1 mm guideway step at 2 s and a 2 t payload step at 4 s. LQR state feedback (`design/design.py`). |
| `maglev-module-open-loop` | The same module without feedback, released 10 nm from its trim gap: the gap deviation grows with the unstable pole of the linearisation (52.68 1/s). |
| `maglev-vehicle` | A 53 t car section on two such modules (heave and pitch of a 3D car body), LSM and speed profile (1 m/s² to 430 km/h, 30 s cruise, braking), guideway of 24.768 m spans with a 3 mm sag and one 2 mm bump. Ride readouts: vertical acceleration, pitch rate. The two modules `ModF` and `ModR` are instances of the library subsystem `LevitationModule` (`library/LevitationModule.bgsub.json`: coil, chassis, skids, secondary suspension and gap controller behind six ports); the rear lever's `FlipR` stays outside it. |

## Layout

```
bgsim.project.json
models/*.bgmodel.json       written by design/build_model.py
library/                    GapController, LsmController, Guideway, Bias (blocks); LevitationModule (subsystem, written by build_model.py)
scenes/                     maglev-module.sdf, maglev-train.sdf
design/design.py            trim, linearisation, LQR gains, nonlinear scipy simulations -> design.json
design/build_model.py       models, scenes and expected.json (reads design.json)
design/vehicle_ref.json     scipy planar simulation of the whole run (cached: design.py --fast reuses it)
expected.json               acceptance checks
```

Rebuild: `uv run examples/maglev-train/design/design.py` (about 2.5 min, the vehicle reference run is slow; `--fast` reuses `vehicle_ref.json`), then `uv run examples/maglev-train/design/build_model.py`.

## Physics

Gap $h = z_\mathrm{rail} - z_\mathrm{bogie}$, coil $L(h)\,\dot i = v - R i + 2\alpha i\,\dot h/h^2$ with $L(h) = L_\infty + 2\alpha/h$, force $F = \alpha i^2/h^2$. The magnet carries the weight when $i = c_\mathrm{trim}\,h$, $c_\mathrm{trim} = \sqrt{(m_b + m_c) g/\alpha} = 15000$ A/m.

Controller (`library/GapController.jl`): $v = R i_\mathrm{ff} + a_1 e_h + a_2 \dot h_f + a_3 (i - i_\mathrm{ff}) + a_4 \int e_h$ with $i_\mathrm{ff} = c_\mathrm{trim} h_\mathrm{ref}$, limited to +-800 V with anti-windup; gains from an LQR design of the bogie plant (weights 1 mm, 0.05 m/s, 20 A, integral weight 1e-4). Closed-loop poles of the seven-state loop: -1073, -126 +- 176j, -36, -8.6, -1.8 +- 6.1j 1/s; open loop: +52.7, -67.1, -18.7, -2.0 +- 5.9j.

## Parameters: published or estimated

| quantity | value | status |
| --- | --- | --- |
| nominal gap | 10 mm | **published** (constant gap of about 10 mm: Wikipedia "Transrapid"; Meisinger, "40 years of Maglev") |
| cruise speed | 430 km/h | **published** (Shanghai Transrapid operating speed; not re-checked in this session) |
| acceleration | 1 m/s^2 | **published** (Wikipedia "Transrapid") |
| Cd, frontal area | 0.26, 16 m^2 | **published** (Wikipedia "Transrapid"; the area is marked "citation needed" there) |
| car section | 27.0 m, 3.7 m wide, 4.2 m high, 53 t empty | **published** (Transrapid vehicle brochure; passenger end section, TR generation not named) |
| levitation chassis | four per section, 12-pole magnets | **published** (Schneider et al. 2022, TR08 simulations; read through a search summary only) |
| span of the guideway | 24.768 m | **recalled** from Transrapid guideway literature, not checked |
| chassis mass 1.5 t per quarter, body 47 t | | estimate (the 53 t is split by assumption) |
| magnet constant alpha = 5.777e-4 H m | | estimate: F = W at 10 mm and i_0 = 150 A (an equivalent magnet of 100 turns, 0.18 m^2 pole area, B = 0.94 T) |
| coil R = 0.55 Ohm, L_inf = 30 mH | | estimate (R i_0^2 = 0.93 kW/t, below the published 1.7 kW/t that includes the electronics) |
| chopper rail +-800 V, 1 ms derivative filter | | estimate |
| secondary suspension | 1 Hz, zeta 0.3 | estimate |
| skid gap 16 mm, touch-down stop 4 mm, contact 2e8 N/m | | estimate |
| guideway sag 3 mm, bump 2 mm x 12 m, bump at 8.5 km | | estimate |
| LSM 150 kN, 50 ms lag, speed PI | | estimate |
| module positions +-9.5 m, guidance stiffness | | estimate |
| inertia (27 x 3.7 x 4.2 m homogeneous box) | | estimate from the published size |

## Validation data

Searched: Wikipedia "Transrapid", the FRA/VNTSC report on TR08 vibration characteristics (Emsland test facility, 2001; only the abstract was readable, the PDF returned 403, and it covers ground vibration), Schneider et al. 2022 (access denied), Meisinger "40 years of Maglev" (only the introduction text). **No levitation-gap, coil-current or body-acceleration time series of a real EMS vehicle was found**, so none is compared with. The numbers the checks use:

- analytic: trim current, weight balance, rest height, constant acceleration, drag at cruise, distance of the profile, the unit quaternion;
- the open-loop unstable pole from the 5-state linearisation (scipy eigenvalue) against the simulated growth rate (52.64 vs 52.68 1/s);
- nonlinear scipy simulations of the same equations (module scenario; the whole 276 s run of the car, planar, `design/design.py`);
- two published values as plausibility checks: the 1 m/s^2 acceleration and the drag power of about 3.53 MW at 400 km/h (the model gives 3.42 MW with the same Cd and area, so this checks units and the drag law, not Cd).

## 3D elements and what is scalar

- 3D: `GroundSpatial`, `Free3D` (floating base: quaternion and position), `RigidBody3D` (spatial inertia, Coriolis term, gravity from the pose). Heave, pitch and the track motion go through the six drive ports of `Free3D`. Lateral, roll and yaw are held by spring-dampers (guidance) and are not excited by the symmetric load; the checks assert that.
- Scalar: the levitation modules (one coil, one gap, one chassis; the force acts along one axis), the lever to the module points (`RackAndPinion`, a 0-junction and a modulated `MTF` for the vertical component of the forward speed), the LSM and the drag. The stdlib has no converter from a spatial port to a scalar one, so the `Free3D` drive ports are the interface.
- Not modelled: the longitudinal inertia of the chassis (6 t of 53 t; they would have to move with the body through a rigid link), yaw and lateral dynamics, the elasticity of the car body and the guideway beams, eddy-current and magnetic drag, guidance magnet detail.

## What to try

- `maglev-module`: change the guideway step or the payload on the dashboard. Only the current changes with the weight at steady state; the gap goes back to 10 mm.
- `maglev-module-open-loop`: plot `Growth/y`; it settles on the unstable pole.
- `maglev-vehicle`: raise the bump to 6 mm or the sag to 8 mm on the dashboard and look at the gaps and `AccZ/y`; lower the cruise speed. The 3D view exaggerates gap, heave and pitch 100 times.
