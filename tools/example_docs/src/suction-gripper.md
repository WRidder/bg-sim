@@ figures transfer
{
  "diagram": {"kind": "diagram", "model": "transfer"},
  "scene": {"kind": "scene", "model": "transfer", "t": 1.9},
  "run": {
    "kind": "plot", "model": "transfer", "xlim": [0, 4.15],
    "rows": [
      {"ylabel": "accel. [m/s²]", "series": [{"signal": "Path/ax", "label": "Path/ax (along the path)"}, {"signal": "Path/az", "label": "Path/az (vertical)"}], "legend": true},
      {"ylabel": "utilisation U [-]", "series": [{"signal": "Cup1/U", "label": "Cup1/U (trailing)"}, {"signal": "Cup3/U", "label": "Cup3/U (middle)"}, {"signal": "Cup5/U", "label": "Cup5/U (leading)"}], "hlines": [{"y": 0.5, "label": "1/S = 0.5"}], "legend": true},
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp", "scale": 0.001}, {"signal": "Gen/dp", "label": "Gen/dp (manifold)", "scale": 0.001, "style": "--"}], "legend": true},
      {"ylabel": "position [m]", "series": [{"signal": "Pose/px", "label": "Pose/px"}, {"signal": "Pose/pz", "label": "Pose/pz"}], "legend": true}
    ]
  },
  "pickup": {
    "kind": "plot", "model": "transfer", "xlim": [0, 0.6],
    "rows": [
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp", "scale": 0.001}, {"signal": "Gen/dp", "label": "Gen/dp", "scale": 0.001, "style": "--"}], "hlines": [{"y": 29.31, "label": "lift-ready (S = 2)"}], "legend": true},
      {"ylabel": "flow [l/min]", "series": [{"signal": "Gen/Q", "label": "Gen/Q", "scale": 60000}, {"signal": "Cup1/Q_leak", "label": "Cup1/Q_leak", "scale": 60000}, {"signal": "Cup1/Q_por", "label": "Cup1/Q_por", "scale": 60000}], "legend": true}
    ]
  },
  "minmove": {"kind": "svg", "svg": "minmove"}
}
@@ svg transfer minmove
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 340" font-family="sans-serif" font-size="12">
<rect width="760" height="340" fill="#ffffff"/>
<line x1="60" y1="270.0" x2="740" y2="270.0" stroke="#e0e0e0"/>
<text x="54" y="274.0" text-anchor="end" fill="#333">0</text>
<line x1="60" y1="235.7" x2="740" y2="235.7" stroke="#e0e0e0"/>
<text x="54" y="239.7" text-anchor="end" fill="#333">0.5</text>
<line x1="60" y1="201.4" x2="740" y2="201.4" stroke="#e0e0e0"/>
<text x="54" y="205.4" text-anchor="end" fill="#333">1</text>
<line x1="60" y1="167.1" x2="740" y2="167.1" stroke="#e0e0e0"/>
<text x="54" y="171.1" text-anchor="end" fill="#333">1.5</text>
<line x1="60" y1="132.9" x2="740" y2="132.9" stroke="#e0e0e0"/>
<text x="54" y="136.9" text-anchor="end" fill="#333">2</text>
<line x1="60" y1="98.6" x2="740" y2="98.6" stroke="#e0e0e0"/>
<text x="54" y="102.6" text-anchor="end" fill="#333">2.5</text>
<line x1="60" y1="64.3" x2="740" y2="64.3" stroke="#e0e0e0"/>
<text x="54" y="68.3" text-anchor="end" fill="#333">3</text>
<line x1="60" y1="30.0" x2="740" y2="30.0" stroke="#e0e0e0"/>
<text x="54" y="34.0" text-anchor="end" fill="#333">3.5</text>
<text x="14" y="150.0" transform="rotate(-90 14 150.0)" text-anchor="middle" fill="#333">shortest safe transfer time [s]</text>
<rect x="77.0" y="172.3" width="25.2" height="97.7" fill="#1f77b4"/>
<text x="89.6" y="169.3" text-anchor="middle" font-size="10" fill="#333">1.43</text>
<rect x="104.2" y="150.9" width="25.2" height="119.1" fill="#d95f02"/>
<text x="116.8" y="147.9" text-anchor="middle" font-size="10" fill="#333">1.74</text>
<text x="145.0" y="266" text-anchor="middle" fill="#888">&gt;</text>
<rect x="158.6" y="138.9" width="25.2" height="131.1" fill="#1b9e77"/>
<text x="171.2" y="135.9" text-anchor="middle" font-size="10" fill="#333">1.91</text>
<rect x="185.8" y="135.9" width="25.2" height="134.1" fill="#a6761d"/>
<text x="198.4" y="132.9" text-anchor="middle" font-size="10" fill="#333">1.96</text>
<text x="145.0" y="286" text-anchor="middle" fill="#333">trapezoid</text>
<rect x="247.0" y="172.3" width="25.2" height="97.7" fill="#1f77b4"/>
<text x="259.6" y="169.3" text-anchor="middle" font-size="10" fill="#333">1.43</text>
<rect x="274.2" y="159.4" width="25.2" height="110.6" fill="#d95f02"/>
<text x="286.8" y="156.4" text-anchor="middle" font-size="10" fill="#333">1.61</text>
<rect x="301.4" y="36.9" width="25.2" height="233.1" fill="#7570b3"/>
<text x="314.0" y="33.9" text-anchor="middle" font-size="10" fill="#333">3.40</text>
<rect x="328.6" y="169.7" width="25.2" height="100.3" fill="#1b9e77"/>
<text x="341.2" y="166.7" text-anchor="middle" font-size="10" fill="#333">1.46</text>
<rect x="355.8" y="132.9" width="25.2" height="137.1" fill="#a6761d"/>
<text x="368.4" y="129.9" text-anchor="middle" font-size="10" fill="#333">2.00</text>
<text x="315.0" y="286" text-anchor="middle" fill="#333">S-curve</text>
<rect x="417.0" y="183.9" width="25.2" height="86.1" fill="#1f77b4"/>
<text x="429.6" y="180.9" text-anchor="middle" font-size="10" fill="#333">1.26</text>
<rect x="444.2" y="167.1" width="25.2" height="102.9" fill="#d95f02"/>
<text x="456.8" y="164.1" text-anchor="middle" font-size="10" fill="#333">1.50</text>
<rect x="471.4" y="62.6" width="25.2" height="207.4" fill="#7570b3"/>
<text x="484.0" y="59.6" text-anchor="middle" font-size="10" fill="#333">3.02</text>
<rect x="498.6" y="190.3" width="25.2" height="79.7" fill="#1b9e77"/>
<text x="511.2" y="187.3" text-anchor="middle" font-size="10" fill="#333">1.16</text>
<rect x="525.8" y="150.9" width="25.2" height="119.1" fill="#a6761d"/>
<text x="538.4" y="147.9" text-anchor="middle" font-size="10" fill="#333">1.74</text>
<text x="485.0" y="286" text-anchor="middle" fill="#333">polynomial 3-4-5</text>
<rect x="587.0" y="179.6" width="25.2" height="90.4" fill="#1f77b4"/>
<text x="599.6" y="176.6" text-anchor="middle" font-size="10" fill="#333">1.32</text>
<rect x="614.2" y="164.6" width="25.2" height="105.4" fill="#d95f02"/>
<text x="626.8" y="161.6" text-anchor="middle" font-size="10" fill="#333">1.54</text>
<rect x="641.4" y="57.4" width="25.2" height="212.6" fill="#7570b3"/>
<text x="654.0" y="54.4" text-anchor="middle" font-size="10" fill="#333">3.10</text>
<rect x="668.6" y="188.1" width="25.2" height="81.9" fill="#1b9e77"/>
<text x="681.2" y="185.1" text-anchor="middle" font-size="10" fill="#333">1.19</text>
<rect x="695.8" y="144.9" width="25.2" height="125.1" fill="#a6761d"/>
<text x="708.4" y="141.9" text-anchor="middle" font-size="10" fill="#333">1.82</text>
<text x="655.0" y="286" text-anchor="middle" fill="#333">cycloidal</text>
<rect x="60" y="318" width="12" height="12" fill="#1f77b4"/>
<text x="76" y="328" fill="#333">sealed</text>
<rect x="142" y="318" width="12" height="12" fill="#d95f02"/>
<text x="158" y="328" fill="#333">cardboard</text>
<rect x="248" y="318" width="12" height="12" fill="#7570b3"/>
<text x="264" y="328" fill="#333">porous</text>
<rect x="330" y="318" width="12" height="12" fill="#1b9e77"/>
<text x="346" y="328" fill="#333">cardboard + tilt</text>
<rect x="492" y="318" width="12" height="12" fill="#a6761d"/>
<text x="508" y="328" fill="#333">cardboard, yaw 90°</text>
</svg>
@@ page transfer overview - | Overview
# Suction gripper: pick, transfer, place

A six-cup bellows vacuum gripper on a gantry picks a closed 10 kg carton (0.5 x 0.3 x 0.3 m) from a conveyor, lifts it 0.15 m, moves it 1 m, lowers it onto the place table and releases it. The parcel is a free rigid body. It hangs on six [SuctionCup](block:Cup1) elements. Each cup holds by its vacuum, has a compliant bellows, slips by friction, peels when a tilting moment lifts one side of the lip, and leaks air through its lip, through the material and through a lifted lip. A [VacuumGenerator](block:Gen) with an ejector characteristic evacuates a [manifold](block:Manifold), and a [line](block:Line1) runs from the manifold to each cup.

![The model canvas|900](@fig:diagram)

The example answers three questions:

1. **How fast can the parcel move without losing it, with a safety factor of 2?** The answer depends on the parcel: sealed (plastic film), cardboard (the default) or porous.
2. **Does the motion profile matter?** The example compares trapezoid, S-curve, polynomial 3-4-5 and cycloidal profiles at equal move time and at equal peak acceleration.
3. **Does the orientation matter?** The example checks (a) the yaw of the cup pattern relative to the path and (b) tilting the gripper along the specific force, like a waiter's tray.

It also covers the air side: the operating vacuum against generator size and porosity, the pick-up time, and one leaking cup on a shared manifold versus flow valves, restrictor nozzles or a generator per cup.

The default run is this model: an S-curve transfer of 1.75 s, which keeps every cup at U ≤ 0.5 with cardboard (the shortest such S-curve is 1.61 s, see [results](page:results)).

## What to try

1. Press **Run** and open the **Dashboard** tab. The two plots show the cup utilisation and the vacuum. The indicator and the counter show whether the parcel is held and how many cups are lost.
2. Set **Profile** to 1 (trapezoid) and **Transfer time** to 0.74 s, then run again. At the deceleration step the bellows ring, the cups peel one after the other, and all six lose their seal.
3. Keep 0.74 s and set the profile to 2 (S-curve). The peak acceleration rises to 11.7 m/s², yet no cup is lost.
4. Set **Parcel permeance** to 2e-6 (porous) and **Generator flow** to 6e-4 (36 l/min). The vacuum drops to 21.6 kPa and a 1.1 s move tears the parcel off.
5. Set **Tilt gain** to 1, or **Yaw of the cup pattern** to 45°, to see the effect of the tray tilt and of the pattern orientation.

All of these are global parameters. The Parameters tab lists them and the dashboard sliders change them. A change keeps the compiled plant, so a rerun takes about a second.

## 3D view

`scenes/suction-gripper.sdf` draws the gantry, the conveyor, the place table with its yellow mark, the gripper with six bellows cups, and the carton with its tape. The bindings colour each cup by its utilisation, from blue (U = 0) to red (U ≥ 1). A lost cup turns grey. The picture is taken at 1.9 s, mid transfer.

![3D view at t = 1.9 s|600](@fig:scene)

Continue with [the gripper model](page:plant), [the air side](page:air), [the sizing](page:sizing) and [the results](page:results).
@@ page transfer plant overview | Gripper, cups and motion
# Gripper, cups and motion

## Mechanics (spatial multibond)

The gripper is a prescribed motion. [Path](block:Path) turns the profiles into the gripper pose and twist: x along the path, z for lift and lower, and the tilt about the transverse axis. [Grip](block:Grip), an `SfSpatial` on the 1-junction `GJ`, imposes that twist. The carton is a [RigidBody3D](block:Parcel) of 10 kg with the box inertia. [Pose](block:Pose) integrates its pose.

Each cup sits between two `FixedTransform3DNeutral` mounts:

- [GMount1](block:GMount1) carries the cup frame on the gripper.
- [PMount1](block:PMount1) carries the attach point on the carton top.

The cups form a 2 x 3 pattern, 0.36 m along the carton and 0.16 m across. Cups 1/2 trail, 3/4 sit in the middle and 5/6 lead, for a move in +x at yaw 0.

Four corner contacts ([Floor1](block:Floor1) to `Floor4`, instances of the library subsystem `ContactFoot`: a mount and a [ContactPoint](block:Floor1/Contact) each) carry the carton on the conveyor and on the place table until the lift and after the release.

## The suction cup

`stdlib:contact/SuctionCup` (new) is a two-port spatial element with a pneumatic port `vac`. The relative pose of the attach point in the cup frame is a state. Its loads are:

| part | law |
| --- | --- |
| bellows axial | $F_s = k_{ax}(s - L_0) + d_{ax}\dot s + A_{fold}\,\Delta p - F_{bot}$ (pull > 0) |
| bottoming | $F_{bot} = k_{bot}\,x_b (x_b/x_{bot})^{n_{bot}-1}$, $x_b$ the compression beyond $s_{bot}$ (smooth) |
| side stiffness | $k_{lat}$ and $k_{tilt}$ times $k_f = (1 + c_{vac}\Delta p/p_{atm})\,e^{-c_{ext}(s - L_0)/L_0}$ |
| holding capacity | $F_{cap} = A_{eff}\,\Delta p$ |
| transmitted pull | $T = \mathrm{smin}(F_s, F_{cap})$, with lip contact $N = F_{cap} - T$ |
| bending, torsion | $M = 2 q_w (k_f k_{tilt} q_x, k_f k_{tilt} q_y, k_{tor} q_z) + d_{rot}\,\omega$ |
| peeling | lip gap $h = \mathrm{pos}((F_s + 4\lvert M_{xy}\rvert/D_{lip} - F_{cap})/k_{ax})$ |
| shear | bellows deflection $e$ plus a Dahl slip law: elastic below $\mu N$, sliding at it |

The utilisation index combines pull-off, peel and slip in one number:

$$U = \frac{T + 4\lvert M_{xy}\rvert / D_{lip} + \lvert F_{lat}\rvert/\mu}{F_{cap}}$$

U = 1 is the edge of loss. A safety factor S means U ≤ 1/S, so S = 2 means U ≤ 0.5. The cup sets its `lost` latch when the lip gap exceeds 2 mm. [Monitor](block:Monitor) counts lost cups in [Monitor/n_lost](signal:Monitor/n_lost). It clears [Monitor/held](signal:Monitor/held) when the carton has dropped 5 cm away from the gripper before the release.

The cup parameters are those of a 50 mm two-fold bellows cup:

- effective area 14 cm², so 58 kPa holds 81 N;
- axial stiffness 5 kN/m, lateral 2.5 kN/m, tilt 3 N·m/rad;
- μ = 0.5 on cardboard;
- chamber volume 20 cm³;
- nonlinear bellows (estimates): the folds bottom after 10 mm of compression ($k_{bot}$ = 5e4 N/m, cubic), the vacuum pulls the bellows 6 mm short ($A_{fold}$ = 5 cm²), and the side stiffness rises by 59 % under 60 kPa and falls as the cup is pulled long ($c_{vac}$ = 1, $c_{ext}$ = 3). With all of them zero the cup is the linear one.

## Motion

Lift and lower are S-curves of 0.15 m (2.5 m/s², 40 m/s³). The vacuum valve opens at t = 0, the lift starts at 0.35 s, and the transfer starts at 0.956 s. The transfer profile is chosen by the global `kind`:

| kind | profile | peak acceleration for L in T |
| --- | --- | --- |
| 1 | trapezoid (1/3 acceleration, 1/3 cruise, 1/3 deceleration) | $4.5\,L/T^2$ |
| 2 | S-curve, jerk phases λ = 0.3 of each ramp | $4.5\,L/T^2/(1-\lambda)$ |
| 3 | polynomial 3-4-5 | $5.77\,L/T^2$ |
| 4 | cycloidal | $2\pi\,L/T^2$ |

[Profile](block:Profile) selects the transfer profile. A second set of the same profiles, [Preview](block:Preview), runs $2/\omega_{tilt}$ earlier and feeds the tilt servo. With `k_tilt` > 0 the gripper tilts towards $\theta_c = \theta_{max}\tanh(k\,\mathrm{atan}(a/(g + a_z))/\theta_{max})$, following a critically damped second-order servo at 15 rad/s. The pivot is the carton centre of mass, so the tilt adds no translation. The preview cancels the servo lag, so the tilt arrives together with the acceleration.

`psi` (yaw) turns the cup pattern relative to the path.
@@ page transfer air overview | Air: generator, leaks, supply
# Air flow

Pressures are gauge pressures, so vacuum is negative. Flows are free-air volume flows in m³/s, as generator datasheets give them. The pneumatics reuse the hydraulic domain. The [Manifold](block:Manifold) is a `Volume` with bulk modulus $p_{atm}$, which is the isothermal gas law.

## Generator

`stdlib:contact/VacuumGenerator` (new) follows its suction curve:

$$Q = Q_{max}\left(1 - x\lvert x\rvert^{n-1}\right),\quad x = \Delta p/\Delta p_{max}$$

n = 1 is the straight line of an ejector, and n = 2 to 4 gives the flatter curve of a displacement pump. The example uses an ejector with $\Delta p_{max}$ = 60 kPa and $Q_{max}$ = 60 l/min (1e-3 m³/s). [Valve](block:Valve) switches the generator on at t = 0 and to release (vent) when the gripper has pressed the carton onto the table.

## Leaks per cup

Each cup chamber is a capacitance: $\dot p = p_{atm}(Q_{leak} + Q_{por} + Q_{vac})/V$. It has three leaks:

- **Lip roughness**: an orifice of $A_{lip0}$ = 0.03 mm², with the regularised law $Q = C_d A\,\Delta p\sqrt{2/(\rho\sqrt{\Delta p^2 + p_{tr}^2})}$.
- **Lifted lip**: the same law, with the gap ring $\pi D_{lip} h$ added to the area. A peeling cup therefore loses vacuum, which lowers its capacity and makes it peel further. This feedback is the loss mechanism.
- **Darcy flow through the material**: $Q_{por} = k_{perm} A_{eff}\,\Delta p$. The example uses $k_{perm}$ = 0 for a sealed parcel, 4e-7 for cardboard and 2e-6 m/(s·Pa) for porous material.

## Supply topology

[Line1](block:Line1) to `Line6` are `CupValve` blocks: an orifice of 7 mm² (a 3 mm line) with two options. A flow-closing valve shuts to a 2 % bleed when the pressure drop exceeds `dp_close`. A check valve is the reverse-flow fraction `r_rev`. The three supply variants are:

| variant | how | model |
| --- | --- | --- |
| common manifold | plain lines | `transfer`, `edge-leak` |
| per-cup flow valves | `dp_close` = 8 kPa | `edge-leak-valves` |
| restrictor nozzles | `A_line` = 1 mm² | design.py |
| a generator per cup | six 10 l/min generators, no manifold | `separate-generators` |

## Pick-up

![Vacuum build-up and flows (cardboard, 60 l/min)|800](@fig:pickup)

When the valve opens, the generator first evacuates the manifold and the six chambers. The steady state is where the generator curve meets the leak demand. With cardboard and 60 l/min this is 48.3 kPa per cup, with a free-air flow of 11.6 l/min.
@@ page transfer sizing overview | Sizing: analytic derivation
# Analytic sizing

`design/sizing.py` contains the hand calculation. `design/design.py` runs it together with the simulations, and `design/results.json` holds the numbers.

## Operating vacuum

The steady state is found by bisection on the manifold vacuum $\Delta p_m$. For each $\Delta p_m$ the cup vacuum $\Delta p_c$ follows from the balance between the line flow and the cup leaks, $Q_{line}(\Delta p_c - \Delta p_m) = Q_{leak}(\Delta p_c) + Q_{por}(\Delta p_c)$. The line law is inverted in closed form. The operating point is where the generator flow $Q_{gen}(\Delta p_m)$ equals the sum of the six line flows.

| parcel | 20 l/min | 30 l/min | 45 l/min | 60 l/min | 90 l/min |
| --- | --- | --- | --- | --- | --- |
| sealed | 54.1 | 56.0 | 57.3 | 58.0 | 58.6 |
| cardboard | 34.4 | 40.3 | 45.4 | 48.3 | 51.7 |
| porous | 14.1 | 19.1 | 24.7 | 29.0 | 35.0 |

The table gives the operating vacuum per cup in kPa. A sealed parcel is limited by the generator's end vacuum, so a larger generator adds little. A porous parcel is limited by the flow, so the vacuum scales almost with the generator size.

## Cup loads

For a steady acceleration $a$ along the path, the cups must apply the specific force $\mathbf f = \mathbf a - \mathbf g$ to the carton, expressed in the gripper frame (rotated by yaw ψ and tilt θ). The bellows are nonlinear, so `sizing.operating_cup` linearises them about the hanging parcel: it solves the axial law $k_{ax}\,ext + A_{fold}\Delta p - F_{bot}(ext) = m g/6$ for the extension and takes the tangent stiffnesses there, with $k_f$ on the lateral and tilt springs. The carton moves rigidly relative to the gripper by a translation $\mathbf u$ and a small rotation $\boldsymbol\varphi$. Cup $i$ at $\mathbf r_i$ from the centre of mass deflects by $\mathbf d_i = \mathbf u + \boldsymbol\varphi\times\mathbf r_i$, so the 6 x 6 statics are

$$\sum_i K\mathbf d_i = -m\mathbf f,\qquad \sum_i \mathbf r_i\times K\mathbf d_i + K_r\boldsymbol\varphi = 0$$

with $K = \mathrm{diag}(k_{lat}, k_{lat}, k_{ax})$. The axial load per cup follows the bolt-group formula: an equal share $m f_z/6$ plus a linear couple that balances the moment $m h f_x$ of the shear about the centre of mass. Here h = 0.15 m is the height of the cup plane above the centre of mass. The leading cups take more pull: under acceleration the inertia acts backwards at the centre of mass, below the cups, and tips the carton nose-down. The U of each cup is computed from $T_i$, $F_{lat,i}$ and $M$, as defined in [the cup model](page:plant).

At rest the U is 0.20 (sealed), 0.24 (cardboard) and 0.40 (porous). Solving max U = 1/S = 0.5 for $a$ gives the quasi-static limit:

| parcel | Δp [kPa] | yaw 0 | yaw 0, tilt | yaw 45° | yaw 45°, tilt | yaw 90° | yaw 90°, tilt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sealed | 58.0 | 3.84 | 6.93 | 2.73 | 5.86 | 2.69 | 5.81 |
| cardboard | 48.3 | 2.82 | 5.83 | 2.02 | 5.00 | 2.00 | 4.98 |
| porous | 29.0 | 0.66 | 2.95 | 0.48 | 2.64 | 0.48 | 2.65 |

Values are in m/s², at S = 2 and 60 l/min. Tilt means k_tilt = 1, with θ ≤ 20°.

## Generator size for S = 2

Turned around, a required acceleration needs a vacuum, and that vacuum needs a generator flow:

| acceleration | vacuum needed | sealed | cardboard | porous |
| --- | --- | --- | --- | --- |
| 1 m/s² | 32.0 kPa | 3.2 l/min | 17.1 l/min | 73 l/min |
| 2 m/s² | 40.9 kPa | 5.3 l/min | 31.3 l/min | 138 l/min |
| 3 m/s² | 50.0 kPa | 11.3 l/min | 73 l/min | 340 l/min |

Porous parcels need a pump-sized generator or a slower move. For a sealed parcel the ejector size hardly matters.

## Pick-up time

`sizing.pickup` integrates the lumped manifold and six-chamber model. "Lift-ready" is the time at which the cup vacuum reaches 29.3 kPa, the vacuum at which the lift acceleration of 2.5 m/s² keeps S = 2.

| parcel | 20 l/min | 30 l/min | 45 l/min | 60 l/min | 90 l/min |
| --- | --- | --- | --- | --- | --- |
| sealed | 0.285 s | 0.185 s | 0.121 s | 0.090 s | 0.060 s |
| cardboard | 0.442 s | 0.233 s | 0.139 s | 0.100 s | 0.064 s |
| porous | never | never | never | never | 0.094 s |

Below 90 l/min a porous parcel never reaches the lift-ready vacuum, because 29.0 kPa is the operating point at 60 l/min. The lift at 0.35 s therefore runs at S < 2 for porous parcels.
@@ page transfer results overview | Results and checks
# Results

![The default transfer: acceleration, cup utilisation, vacuum, parcel position|900](@fig:run)

## Simulation against the hand calculation

| quantity | simulation | analytic |
| --- | --- | --- |
| operating vacuum, sealed | 57 970.5 Pa | 57 971.2 Pa |
| operating vacuum, cardboard | 48 329.7 Pa | 48 329.9 Pa |
| operating vacuum, porous | 29 022.4 Pa | 29 022.6 Pa |
| vacuum 50 ms after the valve opens (sealed / cardboard / porous) | 18 731 / 18 062 / 15 693 Pa | 18 733 / 18 064 / 15 695 Pa |
| pull of cup 5 / 1 at 1.6 m/s² (sealed, slow S-curve) | 19.47 / 13.36 N | 19.53 / 13.17 N |
| shear per cup | 2.54 to 2.78 N | 2.68 N |
| U of cup 5 / 1 | 0.320 / 0.253 | 0.327 / 0.248 |

The slow-move loads agree within 1.0 % for the pull and 5.1 % for the shear. The difference comes from the dynamic loads the hand calculation ignores.

## Dynamic amplification and jerk

At the same peak acceleration of 4 m/s², the dynamic U divided by the quasi-static U is:

| profile | jerk [m/s³] | DAF |
| --- | --- | --- |
| trapezoid | ∞ | 1.80 |
| S-curve λ = 0.1 | 107 | 1.63 |
| S-curve λ = 0.2 | 51 | 1.37 |
| S-curve λ = 0.3 | 32 | 1.35 |
| S-curve λ = 0.5 | 16 | 0.96 |

The bellows and the carton form lightly damped modes: about 6 Hz laterally and 9 Hz axially for six cups on 10 kg. A jerk phase much shorter than their period acts like a step, so λ = 0.1 is little better than the trapezoid. From λ = 0.2 the amplification drops to about 1.36, and λ = 0.5 is quasi-static. With the linear bellows of the first version λ = 0.1 was even worse than the trapezoid (2.51 against 1.90).

## Q2: the profile at equal time

All profiles move 1 m in the same time (max U 2 means lost):

| profile | 0.70 s: peak a / max U | 0.74 s: peak a / max U | 0.80 s: peak a / max U |
| --- | --- | --- | --- |
| trapezoid | 9.18 / 2 (lost) | 8.22 / 2 (lost) | 7.03 / 1.13 |
| S-curve | 13.12 / 2 (lost) | 11.74 / 1.53 | 10.04 / 1.39 |
| polynomial 3-4-5 | 11.78 / 1.33 | 10.54 / 1.15 | 9.02 / 1.08 |
| cycloidal | 12.82 / 1.30 | 11.47 / 1.14 | 9.82 / 1.06 |

Peak accelerations are in m/s². At 0.74 s the trapezoid has the lowest peak acceleration yet is the only profile that loses the parcel; at 0.7 s the S-curve, with 43 % more peak, is lost too, and at 0.8 s all four hold. Its acceleration steps excite the bellows mode and make the leading cups peel. The others pass the U = 1 mark only briefly and hold through the lip friction margin. None of them is safe with S = 2.

## Q1 and Q3: the shortest safe move

`design.py` bisects the transfer time until the maximum U over the transfer is 0.5, for each profile, parcel, yaw and tilt (a coarse grid, then three bisection rounds, with the real simulator):

![Shortest safe transfer time per profile and parcel (yaw 0, with and without tilt)|800](@fig:minmove)

| parcel | trapezoid | S-curve | polynomial | cycloidal |
| --- | --- | --- | --- | --- |
| sealed | 1.43 / 1.61 | 1.43 / 1.39 | 1.26 / 1.08 | 1.32 / 1.08 |
| cardboard | 1.74 / 1.91 | 1.61 / 1.46 | 1.50 / 1.16 | 1.54 / 1.19 |
| porous | > 3.9 / 3.60 | 3.40 / 2.50 | 3.03 / 2.38 | 3.10 / 2.13 |

Times are T_min in seconds at yaw 0, level / tilted. The profile matters at equal peak acceleration as well. All profiles share the same quasi-static limit, but the dynamic surcharge differs (see the DAF table). A smooth profile can therefore run closer to the quasi-static limit. It also needs a higher peak for the same move time (4.5 against 5.8 to 6.4 L/T²). For cardboard the safe peak accelerations are 1.49 m/s² (trapezoid), 2.47 (S-curve), 2.57 (polynomial) and 2.66 (cycloidal), against the quasi-static limit of 2.82.

**Yaw.** At yaw 45° or 90° the short pattern side lies along the path, so the couple that balances the tipping moment has a shorter lever arm. T_min grows by 10 to 31 % (cardboard S-curve: 1.61 to 1.96 s at 45° and 2.00 s at 90°). Keep the long side of the pattern along the path.

**Tilt.** Tilting along the specific force turns most of the shear and the tipping moment into pull, which the cups carry better. For the polynomial and the cycloid T_min drops by 14 to 31 % (cardboard polynomial: 1.50 to 1.16 s, cycloidal 1.54 to 1.19 s), for the S-curve by 3 to 26 %. In `tilt-tray` the max U falls from 0.62 (level) to 0.45 at the same 1.25 s. The trapezoid gets 10 to 13 % slower with the tilt (sealed, cardboard). Its acceleration jumps, so a smooth tilt servo arrives either too early (wrong for the phase before) or too late, and the ringing peak at the step decides.

## Recommendations

- Use a smooth profile (polynomial or cycloidal) with the long side of the cup pattern along the path. Add the tray tilt if the axis is available. For cardboard this is 1.16 s against 1.74 s for a trapezoid.
- Size the generator for the most porous parcel. Porous parcels need about twice the move time, or a pump of about 140 l/min.
- With a common manifold, one cup off the parcel edge drops every cup (see `edge-leak`). Per-cup flow valves or restrictor nozzles keep the other five cups at 48.7 and 40.9 kPa.

## Checks (`expected.json`)

The 43 checks of the eight models cover the following (plus one docs check per model):

- the operating vacuum and generator flow against `sizing.operating_vacuum`;
- the pick-up vacuum at 50 ms;
- U ≤ 0.5 for every cup over the safe transfers;
- the held flag and the placed position;
- the loss of the parcel in the aggressive and porous scenarios, at the right phase;
- the topology numbers of the edge-leak variants;
- the scene bindings.
@@ page transfer notes overview | Notes and limitations
# Notes and limitations

- **Solver.** All models set `FBDF`. The cup chambers are stiff, with a time constant of a few milliseconds against a mechanics timescale of seconds. With `auto` the run picks Tsit5, which is about 5 times slower and stops with `MaxIters` in the porous and edge-leak cases.
- **Seal model.** The holding force is a capacity ($A_{eff}\Delta p$), not a pressure force on a moving membrane. The lip is a ring with a single gap: a lift on one side opens the gap for the whole circumference. The cup does not model a progressive peel of the lip.
- **Air.** The model is isothermal with free-air flows and one lumped chamber per cup. There is no line dynamics beyond the orifice. The Darcy law is linear in the vacuum.
- **Release.** At release the generator vents through `G_rel`. The cups do not model blow-off.
- **Regenerating.** `uv run examples/suction-gripper/design/build_model.py` writes all eight models and the scene. `uv run examples/suction-gripper/design/design.py --procs 7` reruns the analysis, which takes about 25 minutes on 7 Julia processes.
@@ page aggressive-trapezoid overview - | Aggressive trapezoid
# Aggressive trapezoid: the parcel is lost

This model is the `transfer` plant with `kind` = 1 (trapezoid) and `T_move` = 0.74 s, which gives a peak acceleration of 8.2 m/s² with infinite jerk.

![Utilisation, lost cups and vacuum|900](@fig:run)

The carton survives the acceleration (U briefly goes past 1) and the cruise. The deceleration step at t ≈ 1.45 s sets the bellows ringing, and within 70 ms the U of the trailing cups 1/2 goes past 1: braking reverses the tipping moment, so they now take the extra pull. A lifted lip leaks, the vacuum in that cup drops, and the capacity falls with it. The first cups lose their seal at 1.51 s, the load moves to the others, and [Monitor/n_lost](signal:Monitor/n_lost) reaches 6 at 1.55 s. The carton leaves the gripper still moving forward and is not placed.

Compare with `aggressive-scurve`: the same 0.74 s as an S-curve holds. (With the linear bellows of the first version the trapezoid was already lost at 0.7 s and the S-curve still held there; the nonlinear bellows shift both limits, so the pair now runs at 0.74 s.)
@@ figures aggressive-trapezoid
{
  "run": {
    "kind": "plot", "model": "aggressive-trapezoid", "xlim": [0.8, 2.4],
    "rows": [
      {"ylabel": "accel. [m/s²]", "series": [{"signal": "Path/ax", "label": "Path/ax"}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup1/U", "label": "Cup1/U"}, {"signal": "Cup3/U", "label": "Cup3/U"}, {"signal": "Cup5/U", "label": "Cup5/U"}], "hlines": [{"y": 1.0, "label": "U = 1"}], "legend": true},
      {"ylabel": "lost cups", "series": [{"signal": "Monitor/n_lost", "label": "Monitor/n_lost", "color": "#d95f02"}]},
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp", "scale": 0.001}, {"signal": "Cup5/dp", "label": "Cup5/dp", "scale": 0.001}], "legend": true}
    ]
  }
}
@@ page aggressive-scurve overview - | Aggressive S-curve
# Aggressive S-curve: the same time, held

This model is the `transfer` plant with `kind` = 2 and `T_move` = 0.74 s. The peak acceleration is 11.7 m/s², 43 % more than the trapezoid in `aggressive-trapezoid`, but the jerk is finite (λ = 0.3).

![Utilisation and position|900](@fig:run)

The maximum U reaches 1.53 for a moment, so the safety factor is gone, but no cup loses its seal, and the carton is placed at [Pose/px](signal:Pose/px) = 1.000 m.
@@ figures aggressive-scurve
{
  "run": {
    "kind": "plot", "model": "aggressive-scurve", "xlim": [0.8, 3.1],
    "rows": [
      {"ylabel": "accel. [m/s²]", "series": [{"signal": "Path/ax", "label": "Path/ax"}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup1/U", "label": "Cup1/U"}, {"signal": "Cup3/U", "label": "Cup3/U"}, {"signal": "Cup5/U", "label": "Cup5/U"}], "hlines": [{"y": 1.0, "label": "U = 1"}], "legend": true},
      {"ylabel": "x [m]", "series": [{"signal": "Pose/px", "label": "Pose/px"}]}
    ]
  }
}
@@ page tilt-tray overview - | Tilt tray
# Tilt tray: the waiter's tray

This model runs a cycloidal transfer of 1.25 s (peak 4.0 m/s²) with `k_tilt` = 1. The gripper tilts along the specific force (a - g), up to [Path/theta](signal:Path/theta) = 15.2°. The preview profiles drive the tilt servo 2/ω = 0.13 s ahead of the motion, so the tilt and the acceleration coincide.

![Tilt, acceleration and utilisation|900](@fig:run)

The maximum U is 0.45, which is safe with S = 2. Held level, the same move reaches U = 0.62 (design.py). The cycloid needs 1.54 s level and 1.19 s tilted for cardboard.
@@ figures tilt-tray
{
  "run": {
    "kind": "plot", "model": "tilt-tray", "xlim": [0.6, 2.6],
    "rows": [
      {"ylabel": "accel. [m/s²]", "series": [{"signal": "Path/ax", "label": "Path/ax"}]},
      {"ylabel": "tilt [deg]", "series": [{"signal": "Path/theta", "label": "Path/theta", "scale": 57.29577951308232}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup1/U", "label": "Cup1/U"}, {"signal": "Cup3/U", "label": "Cup3/U"}, {"signal": "Cup5/U", "label": "Cup5/U"}], "hlines": [{"y": 0.5, "label": "1/S"}], "legend": true}
    ]
  }
}
@@ page porous-undersized overview - | Porous, undersized generator
# Porous parcel on an undersized generator

The carton material leaks 2e-6 m/(s·Pa) per cup area (`perm`), and the generator delivers only 36 l/min (`Q_max` = 6e-4). Air through the material sets the operating point. The cups reach only [21.6 kPa](signal:Cup1/dp), and the generator runs at 64 % of its free flow just to feed the leaks.

![Vacuum, flow and lost cups|900](@fig:run)

The carton survives the lift and the acceleration of a 1.1 s S-curve (5.3 m/s²) and is lost in the deceleration: the first cup at 1.80 s, all six at 1.83 s. With 60 l/min (29.0 kPa) the same move holds with a max U of 1.14. A safe move (U ≤ 0.5) needs 3.4 s as an S-curve even at 60 l/min, or a much larger generator (see the sizing page of the `transfer` model).
@@ figures porous-undersized
{
  "run": {
    "kind": "plot", "model": "porous-undersized",
    "rows": [
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp", "scale": 0.001}, {"signal": "Gen/dp", "label": "Gen/dp", "scale": 0.001, "style": "--"}], "legend": true},
      {"ylabel": "flow [l/min]", "series": [{"signal": "Gen/Q", "label": "Gen/Q", "scale": 60000}, {"signal": "Cup1/Q_por", "label": "Cup1/Q_por", "scale": 60000}], "legend": true},
      {"ylabel": "lost cups", "series": [{"signal": "Monitor/n_lost", "label": "Monitor/n_lost", "color": "#d95f02"}]}
    ]
  }
}
@@ page edge-leak overview - | Edge leak, common manifold
# One cup over the edge: common manifold

Cup 1 sits partly over the carton edge, which adds 20 mm² of leak area (`A_edge`). All six lines join one manifold.

![Cup vacuum and lost cups|900](@fig:run)

Cup 1 cannot build vacuum ([1.9 kPa](signal:Cup1/dp)). Its open leak also draws the manifold down, so through the lines every other cup sits at [16.7 kPa](signal:Cup3/dp). That is the analytic operating point of `sizing.operating_vacuum` with the extra leak. Five cups at 16.7 kPa cannot lift 10 kg, so all cups are lost at the lift and the carton stays on the conveyor.

Compare `edge-leak-valves` (flow valves) and `separate-generators` (a generator per cup).
@@ figures edge-leak
{
  "run": {
    "kind": "plot", "model": "edge-leak", "xlim": [0, 1.6],
    "rows": [
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp (over the edge)", "scale": 0.001}, {"signal": "Cup3/dp", "label": "Cup3/dp", "scale": 0.001}, {"signal": "Gen/dp", "label": "Gen/dp", "scale": 0.001, "style": "--"}], "legend": true},
      {"ylabel": "lost cups", "series": [{"signal": "Monitor/n_lost", "label": "Monitor/n_lost", "color": "#d95f02"}]},
      {"ylabel": "z [m]", "series": [{"signal": "Pose/pz", "label": "Pose/pz"}]}
    ]
  }
}
@@ page edge-leak-valves overview - | Edge leak, flow valves
# One cup over the edge: per-cup flow valves

This is the same leaking cup 1 as in `edge-leak`, but every line has a flow-closing valve (`dp_close` = 8 kPa, 2 % bleed), like an SCR ball valve. Cup 1 sucks open air, the pressure drop over its line exceeds the closing pressure, and the valve shuts to the bleed. The manifold no longer sees the leak.

![Cup vacuum and line areas|900](@fig:run)

Cup 1 stays at atmosphere and is lost. The five good cups reach [48.7 kPa](signal:Cup3/dp), slightly more than with six sealed cups because one cup less leaks into the manifold. Five cups carry the carton to the place position.

A fixed restrictor nozzle of 1 mm² per line has a similar effect (design.py): the good cups reach 40.9 kPa. The nozzle has no moving parts but slows the pick-up.
@@ figures edge-leak-valves
{
  "run": {
    "kind": "plot", "model": "edge-leak-valves",
    "rows": [
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp (over the edge)", "scale": 0.001}, {"signal": "Cup3/dp", "label": "Cup3/dp", "scale": 0.001}], "legend": true},
      {"ylabel": "line area [mm²]", "series": [{"signal": "Line1/A", "label": "Line1/A", "scale": 1e6}, {"signal": "Line3/A", "label": "Line3/A", "scale": 1e6}], "legend": true},
      {"ylabel": "lost cups", "series": [{"signal": "Monitor/n_lost", "label": "Monitor/n_lost", "color": "#d95f02"}]}
    ]
  }
}
@@ page separate-generators overview - | Separate generators
# One cup over the edge: a generator per cup

Each cup has its own 10 l/min generator (`Gen1` to `Gen6`), with no manifold. Cup 1 leaks over the edge as in `edge-leak`.

![Cup vacuum|900](@fig:run)

The leak of cup 1 stays in its own circuit. A good cup reaches [48.33 kPa](signal:Cup3/dp), the same as with the shared 60 l/min generator on a sealed pattern. Five cups carry the carton. The cost is six generators and six supply lines.
@@ figures separate-generators
{
  "run": {
    "kind": "plot", "model": "separate-generators",
    "rows": [
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup1/dp", "label": "Cup1/dp (over the edge)", "scale": 0.001}, {"signal": "Cup3/dp", "label": "Cup3/dp", "scale": 0.001}], "legend": true},
      {"ylabel": "lost cups", "series": [{"signal": "Monitor/n_lost", "label": "Monitor/n_lost", "color": "#d95f02"}]}
    ]
  }
}
