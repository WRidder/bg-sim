@@ figures ball-gripper
{
  "diagram": {"kind": "diagram", "model": "ball-gripper"},
  "scene": {"kind": "scene", "model": "ball-gripper", "t": 1.1},
  "forces": {
    "kind": "plot", "model": "ball-gripper", "xlim": [0, 2.7],
    "rows": [
      {"ylabel": "force per jaw [N]", "ylim": [0, 70], "series": [{"signal": "Grip/F_grip", "label": "grip force F_grip"}, {"signal": "Grip/F_reqS", "label": "required, S = 2", "style": "--"}, {"signal": "Grip/F_req", "label": "required, S = 1", "style": ":"}, {"signal": "Ctrl/F_cmd", "label": "setting F_set", "color": "#888888", "style": "-."}], "legend": true},
      {"ylabel": "friction [N]", "series": [{"signal": "Grip/need", "label": "needed m|a - g|"}, {"signal": "Grip/demand", "label": "delivered by the jaws", "style": "--"}, {"signal": "Grip/cap", "label": "capacity mu (fnA + fnB)", "style": ":"}], "legend": true},
      {"ylabel": "acceleration [m/s^2]", "series": [{"signal": "Carriage/a_h", "label": "horizontal a_h"}, {"signal": "Carriage/a_v", "label": "vertical a_v"}], "legend": true}
    ]
  },
  "closing": {
    "kind": "plot", "model": "ball-gripper", "xlim": [0, 0.7],
    "rows": [
      {"ylabel": "jaw travel [mm]", "series": [{"signal": "JawPos/y", "label": "JawPos/y", "scale": 1000}]},
      {"ylabel": "jaw speed [mm/s]", "series": [{"signal": "JawVel/y", "label": "JawVel/y", "scale": 1000}, {"signal": "Ctrl/v_ref", "label": "v_ref", "scale": 1000, "style": "--"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "Motor/isense/y", "label": "motor current"}, {"signal": "Ctrl/I_lim", "label": "current limit", "style": "--"}], "legend": true},
      {"ylabel": "grip force [N]", "series": [{"signal": "Grip/F_grip", "label": "F_grip"}], "hlines": [{"y": 46, "label": "setting 46 N"}, {"y": 115, "label": "back-driving 115 N"}], "legend": true}
    ]
  },
  "undergrip": {
    "kind": "plot", "model": "ball-gripper", "overrides": {"Ctrl/F_set": 12.0}, "xlim": [0, 2.7],
    "rows": [
      {"ylabel": "force per jaw [N]", "ylim": [0, 50], "series": [{"signal": "Grip/F_grip", "label": "grip force (setting 12 N)"}, {"signal": "Grip/F_req", "label": "required, S = 1", "style": ":"}], "legend": true},
      {"ylabel": "ball rel. to jaws [mm]", "series": [{"signal": "Grip/dy", "label": "dy", "scale": 1000}, {"signal": "Grip/dz", "label": "dz", "scale": 1000}], "legend": true},
      {"ylabel": "slip speed [mm/s]", "series": [{"signal": "JawA/slip", "label": "JawA/slip", "scale": 1000}]},
      {"ylabel": "holds", "series": [{"signal": "Grip/holds", "label": "Grip/holds"}]}
    ]
  },
  "slipramp": {
    "kind": "plot", "model": "ball-gripper", "overrides": {"Transfer/t_start": 10.0, "Lower/t_start": 10.0, "Retreat/t_start": 10.0, "Ctrl/t_open": 10.0, "Ctrl/t_ramp": 0.8, "Ctrl/ramp": 10.0},
    "settings": {"t_end": 5.5, "output": {"mode": "points", "points": 5501}}, "xlim": [0.5, 5.5],
    "rows": [
      {"ylabel": "force [N]", "ylim": [0, 70], "series": [{"signal": "Grip/F_grip", "label": "grip force"}, {"signal": "Ctrl/F_cmd", "label": "setting (falls at 10 N/s)", "style": "--"}], "hlines": [{"y": 10.08, "label": "Coulomb threshold m g/(2 mu) = 10.08 N"}], "legend": true},
      {"ylabel": "slip speed [mm/s]", "ylim": [0, 5], "series": [{"signal": "JawA/slip", "label": "JawA/slip", "scale": 1000}], "hlines": [{"y": 2, "label": "detection 2 mm/s"}], "legend": true}
    ]
  },
  "impact": {
    "kind": "plot", "model": "ball-gripper", "overrides": {"Ctrl/v_grip": 0.02}, "settings": {"t_end": 0.8, "output": {"mode": "points", "points": 801}}, "xlim": [0.2, 0.6],
    "rows": [
      {"ylabel": "grip force [N]", "series": [{"signal": "Grip/F_grip", "label": "F_grip at v_grip = 20 mm/s"}], "hlines": [{"y": 148.45, "label": "reduced model peak 148.5 N"}, {"y": 115, "label": "back-driving 115 N"}], "legend": true},
      {"ylabel": "jaw speed [mm/s]", "series": [{"signal": "JawVel/y", "label": "JawVel/y", "scale": 1000}]}
    ]
  }
}
@@ page ball-gripper overview - | Overview
# Electric parallel gripper: grip-force sizing

An electric parallel-jaw gripper on a pick-and-place carriage picks a **50 mm steel ball** (0.514 kg), lifts it, moves it 0.4 m sideways with a fast jerk-limited transfer (20 m/s²), sets it down and lets go. The question is the one every gripper selection starts with: **what grip force does the part need, and does the gripper deliver it?**

The ball is a free 3D rigid body ([Ball](block:Ball), [BallPose](block:BallPose)) held only by compliant contacts with regularised Coulomb friction ([JawA](block:JawA), [JawB](block:JawB), [Table](block:Table)), so holding, creeping, slipping and dropping all come out of the contact physics. The drive train is a bond graph from the motor current to the jaw node; the monitor [Grip](block:Grip) compares what the ball needs with what the jaws deliver.

![The model|900](@fig:diagram)

![The 3D view in the transfer (1.1 s): pads coloured by the friction utilisation|600](@fig:scene)

## What to try

- Run it and open the **3D View**: the pads turn from blue towards red while the transfer loads the friction ([JawA/util](signal:JawA/util)), the status light on the housing stays blue ([Grip/holds](signal:Grip/holds)); it turns red when the ball slips.
- **Dashboard**: lower the grip setting to 12 N and the ball slips in the transfer (at 8 N it falls out of the jaws); raise the transfer acceleration and the requirement grows with it (the sized setting still holds at the 40 m/s² slider end: the 56.8 N locked in by the closing carry up to about 54 m/s²). Raise the closing speed at the part to see the impact lock in a larger force.
- The second model, `block-gripper`, holds a block above its centre of mass: the transfer acceleration also tilts it.

Continue with [the mechanism](page:mechanism), [the contact model](page:contact), [the sizing](page:sizing) and [the validation](page:validation).
@@ page ball-gripper mechanism overview | Mechanism and bond graph
# Mechanism and bond graph

| part | blocks | model |
| --- | --- | --- |
| motor | [Motor](block:Motor) (`CurrentControlledDrive`) | ideal current loop, $\tau = k_t\,i$, $k_t = 0.012$ N·m/A, rotor $J_m = 1.5\cdot10^{-6}$ kg·m² |
| gearhead | [Gearhead](block:Gearhead) | ideal 3:1 transformer |
| spindle | [Spindle](block:Spindle) (project `LeadScrew`) | 3 mm lead, efficiency $\eta = 0.7$ driving, $\eta_b = 2 - 1/\eta = 0.571$ back-driven |
| wedge hook | [Wedge](block:Wedge) (project `WedgeHook`) | jaw speed = 0.5 × nut speed |
| jaw guides | [Guides](block:Guides) (project `JawGuides`) | Stribeck friction of both guides: 4 N static, 3 N Coulomb, 10 N·s/m |
| jaws | the jaw node: both jaws share the closing travel $x$ | [JawPos](block:JawPos), [JawVel](block:JawVel) |
| controller | [Ctrl](block:Ctrl) (project `GripController`) | speed loop with a current clamp, grip zone before the part |
| carriage | [Lift](block:Lift), [Transfer](block:Transfer), [Lower](block:Lower), [Retreat](block:Retreat) (`SCurveProfile`), [Carriage](block:Carriage) | prescribed position, velocity and acceleration |

The gearhead, spindle and wedge make one transformer from the motor angle to the jaw travel: per jaw the ideal force per motor torque is

$$G = \frac{2\pi N}{\ell \cdot 2\, i_w} = \frac{2\pi \cdot 3}{0.003 \cdot 2 \cdot 0.5} = 6283\ \mathrm{N\ per\ N\,m},$$

and the rotor inertia appears on the jaw travel as $J_m (2\pi N / (\ell\, i_w))^2 = 237$ kg.

## The lead screw: direction-dependent efficiency

Power from the screw to the nut (driving) loses $1 - \eta$; power from the nut to the screw (back-driving) passes only $\eta_b$. With the nut force $F_b$ and the smoothed direction $s = \tanh(\omega/w_\varepsilon)$, $w_\varepsilon = 10^{-3}$ rad/s, the screw torque is

$$\tau_a = -\frac{\ell}{2\pi} F_b + \tau_{loss},\qquad \tau_{loss} = \frac{\ell}{2\pi}\Big(\tfrac12 |F_b|\, s\,(1/\eta - \eta_b) - \tfrac12 F_b\, s^2 (1/\eta - 2 + \eta_b)\Big),$$

which is $\tau_a = -\ell F_b/(2\pi\eta)$ while driving against the load and $\tau_a = -\ell \eta_b F_b/(2\pi)$ while back-driven. A stalled drive (motor torque $\tau$) therefore holds any jaw force in the **friction band**

$$\eta\, G\, \tau \;\le\; F \;\le\; G\,\tau / \eta_b,$$

and creeps at most at the smoothing speed. For the 46 N setting the band is [46, 115] N.

## The controller

Outside the grip zone the jaws travel at 30 mm/s with the full 2.5 A. From 1 mm before the expected part (`x_pre`) the speed limit blends to `v_grip` = 3 mm/s and the current limit to the grip current $I_{grip} = F_{set}/(\eta\, k_t\, G)$. On the part the speed error saturates the current at $I_{grip}$, so the motor torque, and through the drive train the grip force, is set by the current limit:

![Closing: travel, speed, current and grip force|900](@fig:closing)
@@ page ball-gripper contact overview | Contact model
# Contact model: `MovingPlaneContact`

The jaw pads are the stdlib block [JawA](block:JawA) / [JawB](block:JawB) (`stdlib:contact/MovingPlaneContact`): a sphere of radius $r$ (or a point, $r = 0$) of a spatial body against a finite rectangular face that moves. The face is carried by the carriage (inputs `pc`, `vc`) and slides along the jaw axis $a$ by the Translation port `j`; its origin is $p_c + o + a\,x_s$ with the jaw travel $x_s$.

**Normal force.** With the face normal $n$ and the sphere centre $c$, the penetration is $\delta = r - n\cdot(c - p_c - o - a x_s)$. The Hunt-Crossley law (as `ContactPoint`)

$$f_n = G_e\, k\, x \sqrt{x/x_{ref}}\,(1 + c_d\,\dot x)$$

uses a smooth positive part $x$ of $\delta$ and a smooth no-pull clamp. The edge gate $G_e = q_1 q_2$, $q_i = \tfrac14 (1 + \tanh((w_i - u_i)/w_e))(1 + \tanh((w_i + u_i)/w_e))$, fades the force out beyond the face half-widths $w_i$, so a part can slide off the face.

**Friction.** The slip velocity at the contact point is $u = v - r(\omega\times n) - v_p$, $v_p = v_c + a\,\dot x_s$, projected on the two face tangents. The friction is isotropic regularised Coulomb,

$$F_t = -\mu f_n \tanh(|s|/v_s)\, \frac{s}{|s|},$$

so below the slip limit a held part creeps at $|s| = v_s\, \mathrm{atanh}(|F_t|/(\mu f_n))$ (the regularisation error); the output `util` $= |F_t|/(\mu f_n)$ is the share of the friction limit in use.

**Ports.** The wrench on the body goes to `p` in the point frame (torque $r\,(n \times F_t)$ about the centre); the jaw receives $j.e = F\cdot a$; the carriage power is $P_c = F\cdot v_c$. The balance $p.P + j.P + P_c = \dot E_c + P_d$ is checked in the golden test.

Ball pads: polyurethane, $k = 1.2\cdot10^5$ N/m at $x_{ref} = 0.1$ mm (the Hertz constant of the 50 mm ball, $K = 1.2\cdot10^7$ N/m$^{1.5}$), $c_d = 5$ s/m, $\mu = 0.25$, $v_s = 1$ mm/s, 24 × 24 mm faces. The table is the same block with a static carrier ([TableFrame](block:TableFrame)).
@@ page ball-gripper sizing overview | Derivation and sizing
# Derivation and sizing

The ball must follow the carriage, whose acceleration is $a = (0, a_h, a_v)$. Newton for the ball, $m a = m g_{vec} + F_A + F_B$, so the jaws must supply $F_A + F_B = m(a - g_{vec})$. The jaw normal is horizontal (x) and the motion is in y and z, so all of it is friction, and two jaws with the grip force $F$ each carry at most $2\mu F$:

$$m\sqrt{(g + a_v)^2 + a_h^2} \;\le\; 2\mu F \quad\Rightarrow\quad F \;\ge\; S\,\frac{m\sqrt{(g + a_v)^2 + a_h^2}}{2\mu}.$$

| case | $a_v$, $a_h$ (m/s²) | $F$ per jaw, $S = 1$ |
| --- | --- | --- |
| at rest | 0, 0 | 10.08 N |
| lift | 4, 0 | 14.19 N |
| transfer | 0, 20 | **22.89 N** |

The lift and the transfer do not overlap, so the transfer sizes the gripper: with $S = 2$, **46 N per jaw**. The grip current is the current at which a closing drive reaches 46 N, through the forward efficiency:

$$I_{grip} = \frac{F_{set}}{\eta\, k_t\, G} = \frac{46}{0.7\cdot 0.012\cdot 6283} = 0.872\ \mathrm{A},\qquad \tau = k_t I = 10.5\ \mathrm{mN\,m}.$$

[Grip](block:Grip) evaluates the rule over time: [Grip/need](signal:Grip/need) is $m|a - g|$, [Grip/F_req](signal:Grip/F_req) the force for $S = 1$, [Grip/demand](signal:Grip/demand) the friction the jaws actually deliver and [Grip/S_act](signal:Grip/S_act) the safety in effect:

![Grip force vs requirement, friction delivered vs needed, carriage acceleration|900](@fig:forces)

## Does the gripper deliver it?

The setting is the **lower bound** of the friction band. The closing decides where in the band the force ends: the 237 kg reflected inertia meets the pads at `v_grip` and compresses them beyond the forward value, and the drive friction keeps the extra force as long as it stays below the back-driving value. A reduced 1-DOF model of the closing (in `design/design.py`: jaw mass $\eta\cdot 237$ kg, the speed loop, the Hertz pads and the guide friction) predicts it:

| `v_grip` | reduced model peak | simulation peak | after the impact |
| --- | --- | --- | --- |
| 3 mm/s (default) | 57.39 N | 56.86 N | 56.8 N, locked in |
| 10 mm/s | 93.12 N | 92.56 N | 92.4 N, locked in |
| 20 mm/s | 148.45 N | 147.45 N | 92.0 N, back-driven into the band |
| 30 mm/s | 207.28 N | 205.79 N | 50.9 N, back-driven into the band |

So the sized ball is held at 56.8 N (safety in effect 2.48), but **the extra force depends on the closing and must not be counted on**: size the setting.

![Closing at 20 mm/s: the peak exceeds the back-driving force, the drive gives way and the force falls back into the band|900](@fig:impact)
@@ page ball-gripper validation overview | Validation
# Validation

Every claim is a check in `expected.json` (`uv run examples/run_checks.py --only gripper`); the reference values come from `design/design.py`.

**(a) Static slip threshold and the regularisation error.** With the transfer, lowering and opening moved past the end, the grip setting falls at 10 N/s from 0.8 s while the ball hangs in the jaws. The Coulomb threshold is $F^* = m g/(2\mu) = 10.080$ N. The regularised friction slips earlier: the slip ODE

$$m\,\dot s = m g - 2\mu F(t)\tanh(s/v_s),\qquad \dot F = -\frac{10}{\eta\,\eta_b}\ \mathrm{N/s}$$

(the force of a back-driven drive follows the band top) reaches the detection speed 2 mm/s at **10.4242 N**, 3.4 % above $F^*$; the simulation latches [Grip/F_slip](signal:Grip/F_slip) = **10.4249 N**. While held, the ball creeps at $v_s\,\mathrm{atanh}(\text{need}/(2\mu F))$: 0.149 mm/s at 0.9 s (checked to 1 %).

![Slip-threshold run: the setting falls, the band top follows it, the ball slips|900](@fig:slipramp)

**(b) Friction demand vs requirement.** [Grip/demand](signal:Grip/demand) follows [Grip/need](signal:Grip/need) $= m\sqrt{(g + a_v)^2 + a_h^2}$ to 6 mN over the whole move; the peak is 11.445 N in the transfer.

**(c) Under-gripped vs sized.** At a 12 N setting the drive holds 21.8 N: enough for the lift (14.2 N), not for the transfer (22.9 N). The ball starts to slip at 0.98 s as the transfer acceleration builds up, and [Grip/holds](signal:Grip/holds) drops. At 46 N it holds and moves less than 0.25 mm in the jaws.

![Under-gripped (12 N): the ball slips in the transfer|900](@fig:undergrip)

**(d) Motor current and torque.** 0.872 A and 10.46 mN·m hold the ball; the delivered force (56.8 N) lies inside the friction band [46, 115] N.

**(e) Closing impact vs closing speed.** The peaks of the table on [the sizing page](page:sizing) agree with the reduced model within 1 %.

| check | reference | simulation |
| --- | --- | --- |
| transfer requirement per jaw | 22.890 N | 22.890 N |
| slip detection force | 10.4242 N | 10.4249 N |
| grip force after closing (3 mm/s) | 57.37 N | 56.83 N |
| grip current | 0.8716 A | 0.8716 A |
| under-grip force at the slip | 22.41 N | 21.81 N |
| impact peak, 10 / 20 / 30 mm/s | 93.1 / 148.5 / 207.3 N | 92.6 / 147.4 / 205.8 N |
@@ figures block-gripper
{
  "scene": {"kind": "scene", "model": "block-gripper", "t": 1.1},
  "sized": {
    "kind": "plot", "model": "block-gripper", "xlim": [0, 2.7],
    "rows": [
      {"ylabel": "force per jaw [N]", "ylim": [0, 140], "series": [{"signal": "Grip/F_grip", "label": "grip force (setting 123 N)"}, {"signal": "Grip/F_req", "label": "required with the moment, S = 1", "style": ":"}], "legend": true},
      {"ylabel": "tilt [deg]", "series": [{"signal": "Grip/tilt", "label": "Grip/tilt", "scale": 57.29578}]},
      {"ylabel": "point normal force [N]", "series": [{"signal": "JawA1/f_n", "label": "JawA1"}, {"signal": "JawA2/f_n", "label": "JawA2"}, {"signal": "JawA3/f_n", "label": "JawA3"}, {"signal": "JawA4/f_n", "label": "JawA4"}], "legend": true}
    ]
  },
  "forceonly": {
    "kind": "plot", "model": "block-gripper", "overrides": {"Ctrl/F_set": 31.0}, "xlim": [0, 2.7],
    "rows": [
      {"ylabel": "force per jaw [N]", "ylim": [0, 80], "series": [{"signal": "Grip/F_grip", "label": "grip force (setting 31 N)"}, {"signal": "Grip/F_req", "label": "required with the moment, S = 1", "style": ":"}], "hlines": [{"y": 48.1, "label": "limit-surface estimate 48.1 N"}], "legend": true},
      {"ylabel": "tilt [deg]", "series": [{"signal": "Grip/tilt", "label": "Grip/tilt", "scale": 57.29578}]},
      {"ylabel": "pad utilisation", "ylim": [0, 1.2], "series": [{"signal": "PadA/util", "label": "PadA/util (mean of the points)"}, {"signal": "PadA/util_res", "label": "PadA/util_res (resultant only)", "style": "--"}], "legend": true}
    ]
  }
}
@@ page block-gripper overview - | Overview
# Block in the gripper: the tilting moment

The same gripper and move as `ball-gripper`, with a **40 × 40 × 80 mm aluminium block** (0.346 kg) gripped 28 mm above its centre of mass. Each flat pad touches the block at four points at ±6 mm ([JawA1](block:JawA1) … [JawB4](block:JawB4), point `MovingPlaneContact`s summed by [PadA](block:PadA) and [PadB](block:PadB)); four more points carry it on the table. The block is gripped at 1 mm/s (its stiff point contacts would lock in a much larger closing force than the soft ball contact).

![The block in the transfer (1.1 s)|600](@fig:scene)

## Sizing with the moment

The transfer acceleration acts at the centre of mass, $e = 28$ mm below the grip line, and turns the block about the jaw axis with $M = m\,a_h\,e = 0.194$ N·m. The four points of each pad carry it by friction at the torsion lever $r = \sqrt2\cdot 6$ mm $= 8.5$ mm. Adding force and moment for the worst point gives the sizing rule

$$F \;\ge\; S\,\frac{m|a - g| + M/r}{2\mu}:\qquad 15.40\ \mathrm{N\ (force\ only)} \;\to\; 61.01\ \mathrm{N\ with\ the\ moment},\ S = 2:\ 123\ \mathrm{N}\ (2.33\ \mathrm{A}).$$

A pad that slides as a whole has a limit surface closer to $\sqrt{F_t^2 + (M/r)^2} \le 2\mu F$, 48.1 N: less conservative, still three times the force-only value. [Grip](block:Grip) adds the moment term with `kM` $= e/r$, and reports the tilt [Grip/tilt](signal:Grip/tilt).

![Sized with the moment: holds, tilts 0.26 deg|900](@fig:sized)

## Sized for the force only

With the force-only setting (31 N, $S = 2$) the drive holds 36.9 N, below even the limit-surface estimate. In the transfer the block swings by 26° in the grip ([Grip/holds](signal:Grip/holds) drops at 0.976 s). The pad utilisation of the resultant force (`util_res`) stays low: it is the torsion that saturates the points (`util`).

![Sized for the force only: the block tilts in the transfer|900](@fig:forceonly)
