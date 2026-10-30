"""Write the model docs of `robird` (W5.6 format): `models/robird.docs/` (docs.json, pages/*.md; assets come from verify.py).

    uv run examples/robird/design/build_docs.py

The numbers in the text come from `design/results.json` (written by `design.py verify`), `design/identify.json`, `design/trim.json`
and `design/params.py`; the figures are `assets/<12 hex sha256>.png` rendered from the real run by verify.py.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402
import params as P  # noqa: E402

DOCS = ROOT / "models" / "robird.docs"
R = json.loads((HERE / "results.json").read_text())
FIG = json.loads((HERE / "_runs" / "figures.json").read_text())
IDF = json.loads((HERE / "identify.json").read_text()) if (HERE / "identify.json").exists() else {}
SZ = d.sizing()
TR = d.TRIM


def g(x, n=2):
    return f"{x:.{n}f}"


def pages() -> dict[str, str]:
    A, B = d.SIZE["A"], d.SIZE["B"]
    span = 2 * (P.WING_ROOT[1] + P.L1 + P.L2)
    area = 2 * P.wing_area()
    out: dict[str, str] = {}

    out["overview"] = f"""# Robird: a robotic peregrine falcon flying a figure of eight

A multibond and bond-graph model of the **Robird**, the flapping-wing robotic peregrine falcon of Clear Flight Solutions, built after

> B. A. van der Grinten, G. A. Folkertsma, N. Nijenhuis, S. Stramigioli, *The bird is the word: port based Hamiltonian modelling of
> flapping wing aeroelasticity using vacuum chamber and wind tunnel measurements*, MSc thesis, University of Twente (RaM), 2015.

The thesis models the wing as a small number of rigid bodies (4, 11 and 24) connected by 6D spring-damper elements, with quasi-steady
strip-theory aerodynamics, and it leaves open whether such a model can fly a simulated bird. This example closes that loop with
the 4-body class of wing: the bird **flaps at {g(TR['f0'])} Hz and flies a {g(2 * A, 0)} m x {g(2 * B, 0)} m horizontal 1:2
Lissajous figure of eight at {g(d.SIZE['U'], 0)} m/s with a gentle altitude Lissajous component**, completing the whole figure in {g(SZ['period'], 0)} s,
under a discrete cycle-averaged flight controller. Nothing is kinematic: the fuselage is a 6-DOF free body, the wings are flexible multibody chains
and every force on the bird comes from the strip aerodynamics of its surfaces.

![Top view of the flown path against the Lissajous reference and the tracking error|900](assets/{FIG['path']})

| quantity | value |
| --- | --- |
| mass, span, wing area | {g(P.M_TOTAL)} kg, {g(span)} m, {g(area, 3)} m$^2$ |
| flapping | 2 wings, stroke $\\pm {g(P.PHI_FLAP)}$ rad, {g(R['f_min'])} to {g(R['f_max'])} Hz, mean {g(R['f_mean'])} Hz |
| figure | $x = A\\sin\\vartheta$, $y = B\\sin 2\\vartheta$, $z = z_0 + C_z \\sin\\vartheta$ with $A$ = {g(A, 0)} m, $B$ = {g(B, 0)} m, $C_z$ = {g(d.SIZE['Cz'])} m, $z_0$ = {g(d.SIZE['z0'], 0)} m |
| length, period at {g(d.SIZE['U'], 0)} m/s | {g(SZ['lap_length'], 0)} m, {g(SZ['period'])} s; smallest turn radius {g(SZ['rmin'])} m (bank {g(SZ['bank_at_rmin_deg'], 1)} deg) |
| tracking after 8 s | cross-track RMS {g(R['cross_rms'])} m, peak {g(R['cross_max'])} m; altitude band {g(R['z_min'], 1)} to {g(R['z_max'], 1)} m |

Pages: [the multibond structure](page:structure), [the aerodynamic model](page:aero), [the flapping drive and the aeroelastic wing](page:wing),
[the controller design](page:controller) and [the results](page:results). The README of the example lists which parameters come from the thesis and which are assumed.
"""

    out["structure"] = f"""# The multibond structure

```
 World (GroundSpatial) -- Free (Free3D, 6 DOF) -- Body (RigidBody3D: fuselage, {g(P.M_FUS)} kg)
     Body.p -- MountL1 -- JL1 (WingJoint, flap) -- LinkL1 -- BL1 (inner wing segment) -- MountL2 -- JL2 (WingJoint, bend) -- LinkL2 -- BL2 (outer segment)
     Body.p -- MountR1 ... (right wing, mirrored)
     Body.p -- MountTL -- JTL (Revolute3DCompliant) -- BTL (left elevon)   (right elevon, rudder alike)
 every body: ExternalWrenchSpatial <-- StripAero (wings, tail) / FuselageAero
 pose chain: Free.pose o LocalPose o joint.pose o LocalPose ... -> the world pose of every body (gravity, aerodynamics, scene)
```

* **Fuselage.** [World](block:World) -> [Free](block:Free) -> [Body](block:Body): `GroundSpatial -> Free3D -> RigidBody3D`, 13 states
  (quaternion, position, six momenta), gravity inside the body, six zero-effort `Se` on the unused drive ports. Body frame: $x$ forward, $y$ left, $z$ up, origin at the centre of mass.
  The load of the air on the fuselage ([FusAero](block:FusAero)) enters through an `ExternalWrenchSpatial` ([FusWrench](block:FusWrench)).
* **Wing segments** (4 bodies: inner "arm" and outer "hand" of each wing). Each is a `RigidBody3D` with its own gravity and its own `ExternalWrenchSpatial`:
  [BL1](block:BL1), [BL2](block:BL2) and the mirrored [BR1](block:BR1), [BR2](block:BR2). The joint frames are mounted with `FixedTransform3DNeutral` ([MountL1](block:MountL1), [LinkL1](block:LinkL1)).
  The 4-body class of the thesis (Figure 7) is reduced here to two spanwise segments per wing; the chordwise division is replaced by the torsion degree of freedom of the root joints (see [the aeroelastic wing](page:wing)).
* **Joints.** [JL1](block:JL1) (the flap joint, about the forward axis, up positive) and [JL2](block:JL2) (the bend of the outer segment against the inner one, about the same axis direction) are
  `WingJoint`, an example-local copy of the stdlib `Revolute3DCompliant` whose held rotation about the span axis is a soft torsion spring; all other held directions (sweep, three pivot translations) are stiff spring-dampers, so every state is integral and there is no W201.
* **Tail.** Two all-moving elevon halves ([BTL](block:BTL), [BTR](block:BTR)) and a rudder ([BTV](block:BTV)), each on a `Revolute3DCompliant` hinge driven by a first-order position servo
  ([ServoTL](block:ServoTL)) through an effort source. The weight of the fixed tail frame is part of the fuselage.
* **Power balance.** The aerodynamic wrench enters as an external wrench on each body, so the power given to the air is exactly $-\\sum F_i\\cdot v_i$ ([PaSum](block:PaSum), taps `Pa` of every aerodynamic block); with the
  flapping drive it closes the energy budget: the aerodynamic power averages {g(R['p_air_mean'], 1)} W against {g(R['p_el_mean'], 1)} W electrical.

Bond orientation matters in this framework: the mount transform is bonded **towards** the parent body (`Mount.b -> Body.p`), the joint child through a link **towards** the child body (`Link.b -> Body.p`);
the opposite orientation of the mount flips the sign of the parent twist (the first version of this model failed at $t = 0$ with a relative velocity of $2 U$).

States: about 107 continuous states by count (fuselage 13, each wing segment 12, each tail flap 12, motor current and speed, crank angle, two shaft twists, three servo filters, power average, motor-controller integrator), solved by the `auto` stiff solver at `reltol` 1e-4; {g(R['wall'], 0)} s of wall time for the {g(d.SIZE['t_end'], 0)} s run.
"""

    out["aero"] = f"""# The aerodynamic model

Quasi-steady **modified strip theory** as in the thesis (section III-E): the lift and the drag of every strip follow from the speed relative to the air and the angle of attack,

$$F_L = \\tfrac12 \\rho v^2 S\\, C_L(\\alpha), \\qquad F_D = \\tfrac12 \\rho v^2 S\\, C_D(\\alpha),$$
$$C_L(\\alpha) = L_a \\alpha + L_b, \\qquad C_D(\\alpha) = D_b + D_a |\\alpha| .$$

The coefficients are affine in $\\alpha$ (thesis eq. 10-11; for the drag mirrored in $\\alpha$, smoothed at 0), valid up to about 15 degrees; beyond a stall limit $\\alpha_{{max}}$ = {g(P.AMAX)} rad the angle is limited smoothly by
$\\alpha_{{max}} \\tanh(\\alpha/\\alpha_{{max}})$. The example-local block `StripAero` computes, for each strip $i$ of a segment with position $r_i$ in the body frame,

$$w_i = v + \\omega \\times r_i - R^\\top v_{{wind}}, \\qquad \\alpha_i = \\operatorname{{atan2}}(-w_i\\cdot e_n,\\; w_i \\cdot e_{{le}}),$$
$$F_i = \\tfrac12\\rho\\,|w_i|^2 S_i\\left[C_L\\,\\hat l_i + C_D\\,\\hat d_i\\right], \\qquad \\hat d_i = -\\frac{{w_{{p}}}}{{|w_{{p}}|}},\\quad \\hat l_i = \\frac{{(w\\cdot e_{{le}})\\,e_n - (w\\cdot e_n)\\,e_{{le}}}}{{|w_p|}},$$

with $e_{{le}}$ the unit chord vector towards the leading edge, $e_n$ the surface normal, $w_p$ the part of $w_i$ in the chord-normal plane. The wrench about the body origin is $\\sum_i (F_i,\\; r_i \\times F_i)$ and goes to
`stdlib:multibond/ExternalWrenchSpatial`, whose port effort is the negative of the wrench, so the power is exact. The centre of pressure sits at 25 % chord and the torsion axis at {g(100 * P.XEA, 0)} % chord, so a wing under lift is twisted nose-down by its own
lift moment - the aeroelastic pitch that turns the plunging motion of the flapping stroke into thrust.

| block | what it loads | strips | area (m$^2$) |
| --- | --- | --- | --- |
| [AeroL1](block:AeroL1), [AeroR1](block:AeroR1) | inner wing segments, {g(P.L1)} m | {P.NS} | {g(sum(P.segment_strips(P.L1, *P.C1)[1]), 4)} each |
| [AeroL2](block:AeroL2), [AeroR2](block:AeroR2) | outer wing segments, {g(P.L2)} m | {P.NS} | {g(sum(P.segment_strips(P.L2, *P.C2)[1]), 4)} each |
| [AeroTL](block:AeroTL), [AeroTR](block:AeroTR), [AeroTV](block:AeroTV) | elevon halves and rudder | 2 | {g(P.FLAP_SPAN * P.FLAP_CHORD, 4)}, {g(P.FLAP_SPAN * P.FLAP_CHORD, 4)}, {g(P.RUD_SPAN * P.RUD_CHORD, 4)} |
| [FusAero](block:FusAero) | `FuselageAero`: quadratic drag per body axis (drag areas {P.CDA_FUS[0]}, {P.CDA_FUS[1]}, {P.CDA_FUS[2]} m$^2$) and rotational damping | - | - |

Parameters: $L_a$ = {P.LA} /rad, $L_b$ = {P.LB}, $D_a$ = {P.DA} /rad, $D_b$ = {P.DB} (assumed; the thesis estimates them with a genetic algorithm but its fitted values are not in the paper), tail $L_a$ = {P.LA_TAIL}.
`Air` ([Air](block:Air)) is a constant wind vector (zero for the nominal runs). Limits of the model, as in the thesis: the lift depends only on the *current* angle of attack (no unsteady or dynamic-stall effects) and there is no induced downwash; the model is
good for forces and moments to the 10 to 20 % level, which is enough for the controller design but not for a quantitative power claim.
"""

    out["wing"] = f"""# The flapping drive and the aeroelastic wing

## Drive

```
 Drv (ElectricDrive: R = {P.R_W} Ohm, k_t = {P.K_MOTOR} N m/A, J = {P.J_M:g} kg m^2) -- Gear (IdealGear, N = {P.N_GEAR:g}) -- Crank -- ShaftL (ElasticShaft) -- JL1.drive
                                                                         \\-- ShaftR (ElasticShaft) -- JR1.drive
```

[Drv](block:Drv) is the stdlib bond-graph DC motor, [Gear](block:Gear) an ideal gear of ratio {P.N_GEAR:g}, and [Crank](block:Crank) a power-conserving **modulated transformer with three rotation ports**
for the crank-rocker linkage of the thesis' actuation (a four-bar linkage in the real bird, reduced here to its kinematic map with a second harmonic for the asymmetric up/down stroke):

$$\\varphi(\\psi) = \\Phi\\,[\\sin\\psi + h_2\\sin(2\\psi + \\varphi_2)], \\qquad \\dot\\varphi_{{L,R}} = a_{{L,R}}\\,\\varphi'(\\psi)\\,\\dot\\psi, \\qquad \\tau_{{crank}} = -\\varphi'(\\psi)\\,(a_L\\tau_L + a_R\\tau_R),$$

$\\Phi$ = {P.PHI_FLAP} rad, $h_2$ = {P.H2}. The factors $a_L, a_R$ (nominally 1) scale the stroke amplitude of each wing: **asymmetric flapping amplitude**, the roll input of the flight controller next to the tail.
Each wing hangs on the crank through an `ElasticShaft` ({P.K_SHAFT:g} N m/rad): a rigid coupling of the motor inertia to the multibond joint rate is derivative-causal (W201), the shaft keeps every storage element integral and models the compliance of the real linkage.
[FlapCtl](block:FlapCtl) is the analogue speed regulator of the motor (PI plus the motor model as feed-forward, back-calculation anti-windup, voltage limit $0.98\\,V_{{bat}}$ = {g(0.98 * P.V_BAT, 1)} V of the 6S pack) that makes the crank turn at the commanded flapping frequency $f$: measured within-stroke speed ripple
{g(R['w_track_rms'], 1)} rad/s RMS on the motor, i.e. {g(100 * R['w_track_rms'] / (2 * math.pi * P.N_GEAR * R['f_mean']), 1)} % of the mean speed. The measured flapping frequency of the full run is {g(R['f_min'])} to {g(R['f_max'])} Hz (thesis: 2 to 4 Hz).

The **rear rod** of the thesis' actuator ("the rear rod has a phase lag with respect to the front rod. This creates a changing angle of attack for the up and down-stroke of the wing") is the kinematic rest angle of the torsion spring of the root joint,
$\\theta_{{rest}} = \\Theta\\sin(\\psi + \\psi_s) - \\theta_{{inc}}$ ($\\Theta$ = {P.THETA_ROD} rad, $\\psi_s$ = {P.PS_ROD} rad, rigging incidence $\\theta_{{inc}}$ = {P.INCIDENCE} rad): like the thesis, both rods are velocity-controlled inputs (`Crank.pitL`, `pitR`).

## Aeroelastic wing

[JL1](block:JL1) and [JL2](block:JL2) are `WingJoint`s: the joint coordinate $q$ (flap, resp. bend) is exact; the other held directions are springs with dampers.

| joint | spring | value | thesis source |
| --- | --- | --- | --- |
| flap, root | drive through the crank | - | actuation rods |
| torsion about the span axis | $k_{{r,p}}$ on $d\\theta_x - \\theta_{{rest}}$ | {P.KP_TORS[0]} (root), {P.KP_TORS[1]} (outer) N m/rad, damping {P.BP_TORS[0]}, {P.BP_TORS[1]} | $K_o$, $R$ of the 6D connector (eq. 4-7, 15, 17), values assumed |
| bend, outer against inner | $k$, $b$ on $q$ | {P.K_BEND2} N m/rad ($E I / L$, $E I$ = 2.4 N m$^2$ of two carbon rods), {P.B_BEND2} N m s/rad | $E_f I_x + E_r I_r$ (eq. 15), assumed moduli |
| sweep | held rotation | {P.K_SWEEP} N m/rad | $K_o$ |
| pivot translations | held, three directions | {P.K_PIVOT:.0e} N/m, damping {P.B_PIVOT} N s/m | $K_t$ (eq. 16) |

Measured in the full run (after 8 s): flap stroke $\\pm {g(R['flap_amp'])}$ rad, root torsion up to {g(R['tors_max'])} rad, bend up to {g(R['bend_max'])} rad.

![Flapping: stroke, bend and torsion over 1.5 s, flapping frequency over the run|900](assets/{FIG['flapping']})
"""

    out["controller"] = f"""# The controller design

## Structure: cycle-averaged, discrete, ideal state feedback

The flapping makes every signal of the bird oscillate at the flapping frequency; the controllers work on the **cycle average**. The design is done in four steps (`design/design.py`):

1. **Sizing of the figure from a turn-radius estimate.** The figure $x = A\\sin\\vartheta$, $y = B\\sin 2\\vartheta$ has a smallest radius of curvature $r_{{min}}$ at the crossing; at the cruise speed $U$ a coordinated turn needs the bank
   $\\phi = \\arctan(U^2/(g\\,r_{{min}}))$. With $A$ = {g(A, 0)} m and $B$ = {g(B, 0)} m: lap {g(SZ['lap_length'], 0)} m, $r_{{min}}$ = {g(SZ['rmin'])} m, **bank {g(SZ['bank_at_rmin_deg'], 1)} deg**, period {g(SZ['period'], 1)} s at {g(d.SIZE['U'], 0)} m/s
   (measured peak bank {g(math.degrees(R['phi_max']), 1)} deg, limit 34 deg). For comparison a smaller figure with $A$ = 60 m, $B$ = 25 m has $r_{{min}}$ = 13.9 m and would need 47 deg of bank at this speed.
2. **Trim from the full flapping model** (`design.py trim`): the closed loop with the path following switched off flies straight for 34 s; the cycle averages over the last 10 s are the trim:
   $f_0$ = {g(TR['f0'], 3)} Hz, pitch $\\theta_0$ = {g(math.degrees(TR['th0']), 2)} deg, elevator $\\delta_{{e0}}$ = {g(TR['de0'], 3)} rad, speed {g(TR.get('speed', 12), 2)} m/s, vertical speed {g(TR.get('vz', 0), 3)} m/s,
   electrical power {g(TR.get('P_el', 0), 1)} W, aerodynamic power {g(TR.get('P_air', 0), 1)} W.
3. **Sensitivities from the full model** (`design.py identify`): short open-loop runs around the trim (two flapping cycles after a 0.3 s settling window; table in the README) give the cycle-averaged acceleration per unit of every input
   (flapping frequency $f$, pitch attitude, elevator $\\delta_e$, differential tail $\\delta_a$, rudder $\\delta_r$, amplitude asymmetry $\\eta$). They fix the signs and the order of magnitude of each loop; the short window contains the strong aerodynamic damping of the flapping wings, so the
   gains were then **tuned by iterating in the full closed-loop flapping model**, not computed from a linear model. No loop margins are claimed.
4. **Verification in the full flapping model**, always (this page's results).

## Blocks

| block | rate | role |
| --- | --- | --- |
| [Guide](block:Guide) `Guidance` | 50 Hz | path table (2 m spacing); nearest point, along-track and cross-track error $e$; heading law $\\dot\\psi = U\\kappa(s + t_{{lead}}U) + k_\\chi(\\chi_{{des}} - \\chi)$, $\\chi_{{des}} = -\\arctan(e/L)$ ($L$ = {GAINS_L} m look-ahead, $k_\\chi$ = 1 /s, $t_{{lead}}$ = 0.6 s to cancel the roll lag); altitude reference with climb-rate feed-forward |
| [Fctl](block:Fctl) `FlightCtrl` | 100 Hz | the inner loops below, with notch filters at $f$ and $2f$ (pole radius 0.95, unit DC gain) on every feedback signal for the cycle average |
| [FlapCtl](block:FlapCtl) | analogue | motor speed PI, see [the drive](page:wing) |
| [ServoTL](block:ServoTL) | servo | first-order command lag 40 ms, PD torque, stall 0.3 N m |

Inner loops (`FlightCtrl`; nose-up pitch $\\theta$, roll $\\phi$ with left wing up positive, $n = 1/\\cos\\phi$):

$$f = f_0 + K_{{pu}}(U_c - U) + I_u + K_{{fn}}(n - 1), \\qquad \\theta_c = \\theta_0 + K_{{\\theta n}}(n-1) + K_{{pv}}(v_{{z,c}} - v_z) + I_{{vz}},\\quad v_{{z,c}} = K_z(z_c - z) + v_{{z,ff}}$$
$$\\delta_e = \\delta_{{e0}} - K_\\theta(\\theta_c - \\theta) + K_q\\,q_{{up}}, \\qquad \\phi_c = -\\arctan\\frac{{U\\dot\\psi}}{{g}}, \\qquad \\delta_a = K_\\phi(\\phi_c - \\phi) - K_p p + I_\\phi, \\qquad \\delta_r = -K_r(\\dot\\psi\\cos\\phi - r)$$

The elevons get $\\delta_e \\pm \\delta_a$, the rudder $\\delta_r$, the flapping drive $f$ and the amplitude asymmetry $\\eta = K_\\eta(\\phi_c - \\phi)$ ($K_\\eta$ = 0 here: the tail has enough roll authority at this size).
Gains: $K_\\theta$ = {GAINS_KTH}, $K_q$ = {GAINS_KQ} s, $K_{{pu}}$ = 0.3 Hz s/m, $K_{{iu}}$ = 0.15 Hz/m, $K_z$ = 0.25 /s, $K_{{pv}}$ = 0.06 rad s/m, $K_\\phi$ = 0.8, $K_p$ = 0.05 s, $K_r$ = 0.15 s (defaults of `library/FlightCtrl.jl`, listed in the README).
All commands are limited (flapping frequency {P.F_MIN} to {P.F_MAX} Hz, tail deflection $\\pm 0.45$ rad, bank 0.6 rad) and the integrators are clamped.

**Honesty notes.** The controller feeds back the ideal truth (`Truth`: attitude, rates, ground velocity, position), not sensor models: the example is about the flapping flight dynamics, not about estimation (see `quadcopter` for a full sensor chain). The loop is **speed-controlled flapping, not torque-controlled**:
the within-stroke ripple of the motor speed is a result of the model. The measured flapping frequency saturates at the upper limit of {P.F_MAX} Hz for a short time in the turns.
"""

    out["results"] = f"""# Results

![Top view and tracking error|900](assets/{FIG['path']})

![Altitude, speed and bank angle along the figure|900](assets/{FIG['altitude']})

![Tail deflections, motor voltage and current, average aerodynamic power|900](assets/{FIG['tail_drive']})

## Measured (real worker, reltol 1e-4, {g(d.SIZE['t_end'], 0)} s, statistics after {g(d.SIZE['t_stat'], 0)} s)

| quantity | value |
| --- | --- |
| figure completed | $x$ from {g(R['x_min'], 1)} to {g(R['x_max'], 1)} m ($A$ = {g(A, 0)}), $y$ from {g(R['y_min'], 1)} to {g(R['y_max'], 1)} m ($B$ = {g(B, 0)}); {R['nx']:.0f} sign changes of $x$ and {R['ny']:.0f} of $y$ in the rest of the lap |
| cross-track error | RMS {g(R['cross_rms'])} m, peak {g(R['cross_max'])} m ([Guide/e_ct](signal:Guide/e_ct)) |
| altitude | {g(R['z_min'], 2)} to {g(R['z_max'], 2)} m (reference 23.5 to 26.5 m); error RMS {g(R['alt_rms'])} m, peak {g(R['alt_err_max'])} m ([Guide/e_z](signal:Guide/e_z)) |
| speed | {g(R['speed_min'])} to {g(R['speed_max'])} m/s (command {g(d.SIZE['U'], 0)}) |
| flapping | {g(R['f_min'])} to {g(R['f_max'])} Hz, stroke amplitude {g(R['flap_amp'])} rad ([JL1/qout](signal:JL1/qout)) |
| tail | elevons up to {g(R['tail_max'])} rad (the start-up transient), rudder {g(R['rudder_max'], 3)} rad; bank peak {g(math.degrees(R['phi_max']), 1)} deg |
| drive | motor voltage peak {g(R['u_max'], 1)} V, current peak {g(R['i_max'], 1)} A, mean {g(R['i_mean'], 1)} A; electrical {g(R['p_el_mean'], 1)} W, aerodynamic {g(R['p_air_mean'], 1)} W |
| cost | {g(R['wall'], 0)} s wall time for {g(d.SIZE['t_end'], 0)} s of flight (compile included), {R['rows']} recorded rows |

## Checks (`expected.json`)

- the start: [Truth/z](signal:Truth/z) = 25 m at $t = 0$ and the start velocity along the tangent of the figure;
- periodic flapping: the dominant frequency of the flap angle and the motor-speed tracking of the commanded frequency;
- cross-track error at most 1.5 m and its RMS; altitude error at most 1.5 m, altitude band 21.5 to 28.5 m;
- the figure-eight completed: the extents $\\pm A$, $\\pm B$ within 3 m and the number of zero crossings of $x$ and $y$;
- actuators: elevons and rudder within $\\pm 0.5$ rad, motor voltage below the duty limit, current below 12 A, bank below 0.6 rad, speed between 10 and 14 m/s;
- energy sanity: the average aerodynamic power ([PaSum/Pavg](signal:PaSum/Pavg)) about 16 W and positive;
- `scene_bindings`, and no error diagnostics. The `robird-trim` model (open loop at the trim command, 3 s) checks the flapping frequency and the stroke.
"""
    return out


GAINS_L = d.GAINS["guide"]["Llook"]
GAINS_KTH = d.GAINS["fc"]["Kth"]
GAINS_KQ = d.GAINS["fc"]["Kq"]


def main() -> int:
    pg = pages()
    (DOCS / "pages").mkdir(parents=True, exist_ok=True)
    for name, text in pg.items():
        (DOCS / "pages" / f"{name}.md").write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    manifest = {
        "format": "bgsim.docs", "version": 1,
        "pages": [{
            "id": "overview", "title": "Overview", "file": "pages/overview.md",
            "children": [
                {"id": "structure", "title": "The multibond structure", "file": "pages/structure.md", "children": []},
                {"id": "aero", "title": "The aerodynamic model", "file": "pages/aero.md", "children": []},
                {"id": "wing", "title": "Flapping drive and aeroelastic wing", "file": "pages/wing.md", "children": []},
                {"id": "controller", "title": "Controller design", "file": "pages/controller.md", "children": []},
                {"id": "results", "title": "Results", "file": "pages/results.md", "children": []},
            ],
        }],
    }
    (DOCS / "docs.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", DOCS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
