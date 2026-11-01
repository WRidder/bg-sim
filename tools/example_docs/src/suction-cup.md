@@ figures hold-release
{
  "diagram": {"kind": "diagram", "model": "hold-release"},
  "scene": {"kind": "scene", "model": "hold-release", "t": 1.5, "zoom": 6},
  "run": {
    "kind": "plot", "model": "hold-release", "xlim": [0, 3.49],
    "rows": [
      {"ylabel": "height [mm]", "series": [{"signal": "Tool/g[7]", "label": "Tool/g[7] (cup mount)", "scale": 1000}, {"signal": "Pose/g[7]", "label": "Pose/g[7] (box centre)", "scale": 1000}], "legend": true},
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup/dp", "label": "Cup/dp", "scale": 0.001}]},
      {"ylabel": "ext [mm]", "ylim": [-4, 2], "series": [{"signal": "Cup/ext", "label": "Cup/ext", "scale": 1000}], "hlines": [{"y": -1.668, "label": "hang: (m g - A_fold dp)/k_ax"}], "legend": true},
      {"ylabel": "U [-]", "ylim": [-0.1, 0.5], "series": [{"signal": "Cup/U", "label": "Cup/U"}]}
    ]
  },
  "liftoff": {
    "kind": "plot", "model": "hold-release", "xlim": [0, 0.45],
    "rows": [
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup/dp", "label": "Cup/dp", "scale": 0.001}]},
      {"ylabel": "box centre z [mm]", "series": [{"signal": "Pose/g[7]", "label": "Pose/g[7]", "scale": 1000}], "hlines": [{"y": 19.962, "label": "resting on the table"}, {"y": 21.630, "label": "rest + 1.668 mm (hand)"}], "legend": true}
    ]
  }
}
@@ page hold-release overview - | Overview
# Suction cup: one bellows cup and a box

One bellows suction cup holds a small box. The cup is a [SuctionCup](block:Cup), the 1.5-fold bellows cup of the `fanuc-pick` example (lip 32 mm, rest length 30 mm), with the nonlinear bellows switched on. It sits on a tool with a prescribed motion ([CupTool](block:Tool)). One compact ejector ([Gen](block:Gen)) evacuates it. The box is a free [RigidBody3D](block:Box) of 0.6 kg (120 x 120 x 40 mm). It starts on a table (four [ContactPoint](block:Floor1) corners), is lifted 60 mm, put through one motion, put back and released.

![The model canvas|900](@fig:diagram)

![The 3D view: the see-through bellows between the tool flange and the box, the lip coloured by U|700](@fig:scene)

The example shows what the cup model does dynamically:

1. **Vacuum lift stroke.** The vacuum on the folds pulls the bellows shut. At 59 kPa that is 10 N, more than the weight of the box, so the cup lifts the box off the table before the tool moves.
2. **Axial spring-mass mode and bottoming.** The box rings on the bellows at 10.3 Hz. Driven hard, the folds stack up and the bellows hardens.
3. **Sway and tilt.** A lateral load moves the bellows sideways and tilts the box. That gives two lateral modes and a peeling moment on the lip.
4. **Holding limit.** The utilisation [U](signal:Cup/U) shows the margin. Past 1 the lip lifts, leaks and the seal is lost.

Every model is the same plant. The global `motion` picks the excitation:

| model | motion |
| --- | --- |
| `hold-release` (this one) | vacuum build-up, lift, hold, lower, release |
| `bounce` | a 4 mm step down, then a vertical chirp 3 to 20 Hz |
| `steps` | horizontal acceleration pulses of 1.5, 3 and 4.5 m/s² |
| `swing` | a slow tool tilt to 30° and back, then a fast ±10° swing |
| `chirp` | a lateral chirp 1.5 to 20 Hz, with the transmissibility |
| `overload` | a 0.8 kg box on pulses of 3, 6 and 9 m/s²: lost |
| `linear-vs-nonlinear` | the bounce with a second cup whose nonlinear terms are 0 |

## What to try

1. Press **Run** and open the **Dashboard** tab. The XY plot shows the force the cup transmits against its stroke while it is sealed ([Mon/T_c](signal:Mon/T_c) against [Mon/ext_c](signal:Mon/ext_c)). U, the vacuum, the lip gap and the deflections are read out next to it.
2. Raise **Payload mass** to 1.5 kg. The box now weighs more than the 10 N vacuum lift, so it stays on the table until the tool lifts it. The lift acceleration takes U to 0.86.
3. Lower **Vacuum level** to 30 kPa. The operating vacuum falls to 29.7 kPa, the capacity halves and the hold U doubles to 0.39. The lift force (5 N) no longer lifts the box off the table.
4. Open `bounce` and raise **Motion amplitude** to 1.05. The folds bottom harder (135 N), and the rebound tears the cup off at 4.93 s.
5. Move **Centre of mass offset x** to 0.03 m. The box hangs off-centre: the peeling moment $m g c_x$ = 0.18 N·m counts as $4M/D_{lip}$ = 22 N against the 29.6 N capacity, and the lip peels as soon as the box leaves the table.
@@ page hold-release plant overview | Cup, tool and box
# Cup, tool and box

## Mechanics

The tool is a prescribed motion. [Tool](block:Tool) turns three S-curve profiles ([Lift](block:Lift), [Lower](block:Lower), [Retract](block:Retract)) and the excitation of the chosen motion into the tool pose and twist. [Grip](block:Grip), an `SfSpatial` on the 1-junction `TJ`, imposes that twist.

The cup sits between two `FixedTransform3DNeutral` mounts. [GMount](block:GMount) carries the cup frame on the tool, and [PMount](block:PMount) carries the attach point on the top of the box. The cup axis is the −z axis of the mount frame. The start state is `rz = -L0`.

[Pose](block:Pose) integrates the box pose. [Mon](block:Mon) draws the bellows and the lip in the 3D view, computes the box tilt relative to the tool ([Mon/sway](signal:Mon/sway)) and clears [Mon/held](signal:Mon/held) when the lip has moved 20 mm away from the box before the release.

## The cup and its nonlinear bellows

The cup is the linear `SuctionCup` (holding capacity $F_{cap} = A_{eff}\Delta p$, Kelvin bellows, lip friction, peeling and seal loss) with the optional nonlinear bellows terms:

| term | law | value |
| --- | --- | --- |
| bellows force | $F_s = k_{ax}\,ext + A_{fold}\,\Delta p - F_{bot} - d_{ax}\,\dot{ext}$ | $k_{ax}$ 2500 N/m, $d_{ax}$ 8 N·s/m |
| vacuum lift | $A_{fold}\,\Delta p$ pulls the folds shut | $A_{fold}$ 1.7 cm² |
| bottoming | $F_{bot} = k_{bot}\,x_b\,(x_b/x_{bot})^{n_{bot}-1}$, $x_b$ = compression beyond $s_{bot}$ | $s_{bot}$ 6 mm, $k_{bot}$ 25 kN/m, $n_{bot}$ 3, $x_{bot}$ 1 mm |
| side stiffness factor | $k_f = (1 + c_{vac}\Delta p/p_{atm})\,e^{-c_{ext}\,ext/L_0}$ on $k_{lat}$ and $k_{tilt}$ | $c_{vac}$ 1, $c_{ext}$ 3 |

`ext` is the stretch of the bellows (negative is compressed). The utilisation combines pull, peel and slip:

$$U = \frac{T + 4\lvert M_{xy}\rvert / D_{lip} + \lvert F_{lat}\rvert/\mu}{F_{cap}}$$

The other cup values are those of `fanuc-pick`: $A_{eff}$ 5 cm², $D_{lip}$ 32 mm, $k_{lat}$ 1500 N/m, $k_{tilt}$ 1 N·m/rad, μ 0.5, chamber 8 cm³. The nonlinear values are estimates for a 1.5-fold cup, not datasheet values.

The `linear-vs-nonlinear` model has a second cup (`CupL`) with $k_{bot}$, $A_{fold}$, $c_{vac}$ and $c_{ext}$ at 0. That is exactly the linear cup.

## Air

The ejector curve is $Q = Q_{max}(1 - \Delta p/\Delta p_{max})$ with 60 kPa end vacuum and 12 l/min free air. The box surface is sealed, so the only leak is past the lip. The [Valve](block:Valve) step switches the ejector off at the release, and the cup vents.

## Motion

The vacuum is on from t = 0. The lift (60 mm S-curve, 3 m/s², 60 m/s³) starts at 0.4 s, and the excitation starts at 0.937 s. After the excitation the tool lowers the box onto the table, presses 3 mm, releases and retracts 50 mm.
@@ page hold-release analysis overview | Hand calculation
# Hand calculation

`design/analysis.py` computes these numbers. `expected.json` checks the simulations against them.

## Operating vacuum

The ejector curve meets the leak past the sealed lip: $Q_{max}(1 - \Delta p/\Delta p_{max}) = Q_{leak}(\Delta p)$ gives $\Delta p$ = 59 152 Pa. The holding capacity is $A_{eff}\Delta p$ = 29.58 N, and the static utilisation of the 0.6 kg box is $mg/F_{cap}$ = 0.199.

## Static hold and lift stroke

At rest the bellows force carries the box: $k_{ax}\,ext + A_{fold}\Delta p - F_{bot} = m g$. The vacuum lift is $A_{fold}\Delta p$ = 10.06 N, which alone would contract an unloaded cup by 4.022 mm. The box weighs 5.88 N, so

$$ext = \frac{m g - A_{fold}\Delta p}{k_{ax}} = \frac{5.884 - 10.056}{2500} = -1.668\ \text{mm}$$

The hanging cup is shorter than its rest length, so on the table the cup lifts the box 1.668 mm. The linear cup stretches to +2.354 mm instead.

## Axial mode

At the hang the folds do not touch ($-ext < s_{bot}$), so the tangent stiffness is $k_{ax}$:

$$\omega_n = \sqrt{k_{ax}/m} = 64.55\ \text{rad/s}\ (10.27\ \text{Hz}),\qquad \zeta = \frac{d_{ax}}{2\sqrt{k_{ax} m}} = 0.103$$

## Lateral modes

The box hangs on the bellows with its centre of mass $h$ = 20 mm below the lip. With the lateral bellows deflection $e$ and the box tilt $\varphi$ as coordinates, linearised about the hang:

$$\begin{bmatrix} m & -m h \\ 0 & J \end{bmatrix}\ddot q + \begin{bmatrix} k & 0 \\ h k & k_t + m g h \end{bmatrix} q = -\begin{bmatrix} m \\ 0 \end{bmatrix}\ddot x_T$$

with $k = k_{lat}k_f$, $k_t = k_{tilt}k_f$ and $k_f$ = 1.871 at the hang. The two modes are 6.55 Hz (sway: the box swings sideways) and 13.20 Hz (tilt: the box rocks on the lip). The linear cup ($k_f$ = 1) has 4.89 and 9.69 Hz. The steady-state transmissibility from the tool to the box's centre of mass peaks at 4.58 near 6.5 Hz.

## Quasi-static utilisation

For a steady tool acceleration $a$ along x: $U = (m g + 4 m a h / D_{lip} + m a/\mu)/F_{cap}$. That is 0.34, 0.47 and 0.61 for the steps at 1.5, 3 and 4.5 m/s², and the limit U = 1 is at 8.8 m/s². The 0.8 kg overload box reaches 0.996 at 6 m/s².

For a steady tool tilt θ, gravity splits into the pull $mg\cos\theta$ and the shear $mg\sin\theta$. At 30° U = 0.620 and the lateral deflection is $mg\sin\theta/(k_{lat}k_f)$ = 1.016 mm, with $k_f$ evaluated at the axial load $mg\cos\theta$.
@@ page hold-release results overview | Results and checks
# Results

![The hold-release run: heights, vacuum, stroke and utilisation|900](@fig:run)

The vacuum builds up in about 0.1 s. While the box still rests on the table, the lift stroke pulls it up:

![Vacuum build-up and lift-off|900](@fig:liftoff)

## Simulation against the hand calculation

| quantity | simulation | hand calculation |
| --- | --- | --- |
| operating vacuum | 59 152.1 Pa | 59 152.3 Pa |
| holding capacity | 29.576 N | 29.576 N |
| hanging extension (t = 2 s) | −1.6680 mm | −1.6680 mm |
| side stiffness factor $k_f$ | 1.8713 | 1.8713 |
| static U | 0.1983 | 0.1990 |
| axial mode (bounce ring-down) | 64.547 rad/s, ζ 0.1033 | 64.55 rad/s, ζ 0.1033 |
| lateral modes (steps coast, FFT) | 6.59 / 13.13 Hz | 6.55 / 13.20 Hz |
| lateral deflection at 30° tilt | 1.013 mm | 1.016 mm |
| U at 30° tilt | 0.603 | 0.620 |
| linear vs nonlinear hang | +2.345 / −1.678 mm | +2.354 / −1.668 mm |

The hand values hold where the motion is slow or small. The dynamic runs go beyond them:

- **Steps.** The sudden pulses overshoot. U reaches 0.90 at 4.5 m/s², against 0.61 quasi-static.
- **Chirp.** The swept transmissibility peaks at 2.75 and 3.28. The steady-state model gives 4.58 at the sway mode. The 1.85 Hz/s sweep crosses each resonance in a few cycles, and the demodulator low-pass smooths the peak.
- **Bounce.** The bottoming makes the axial spring harden, so the peak response moves from 10.3 Hz to about 13.9 Hz.

`expected.json` checks every row of this table, the bottoming force, the transmissibility peaks, the loss of the overloaded box and the held outcome of every other model.
@@ page hold-release notes overview | Notes and limitations
# Notes and limitations

- **Solver.** All models use `FBDF`: the cup chamber is stiff.
- **Estimates.** The nonlinear bellows parameters (`s_bot`, `k_bot`, `A_fold`, `c_vac`, `c_ext`) are estimates for a 1.5-fold cup.
- **U below zero.** U has a smooth floor at −1. A bellows pushed hard against the box (compression, no pull) reads −1, so the bounce plots dip to −1.
- **Seal model.** The lip is a ring with one gap. A lift on one side opens the gap for the whole circumference.
- **Release.** After the release the tool retracts and the lip leaves the box: `sealed` drops to 0, but `held` stays 1 because the box was put down.
- **Regenerating.** `uv run examples/suction-cup/design/build_model.py` writes all seven models and the scenes. `uv run examples/suction-cup/design/analysis.py --sim` reruns the hand calculation and compares it with the hold and swing runs.
@@ page bounce overview - | Vertical bounce
# Vertical bounce: axial mode and bottoming

The tool steps down 4 mm in 40 ms. The box rings on the bellows, and the ring-down gives the axial mode: [Cup/ext](signal:Cup/ext) decays at 64.55 rad/s (10.27 Hz) with ζ = 0.103, exactly $\sqrt{k_{ax}/m}$ and $d_{ax}/(2\sqrt{k_{ax}m})$. The ring stays inside the 6 mm compression stroke, so nothing bottoms.

Then a vertical chirp sweeps 3 to 20 Hz in 5 s, with the amplitude rising to 1.7 mm. Near resonance the box drives the bellows past $s_{bot}$. The folds stack up, and [Cup/F_bot](signal:Cup/F_bot) reaches 69 N. The stiffer spring raises the natural frequency, so the large response follows the chirp beyond 10.3 Hz. The hardest bottoming is at about 13.9 Hz, after which the response drops. The seal survives: the peak U is 0.87.

![Chirp frequency, extension, bottoming force and U|900](@fig:run)

![Force-stroke: the bellows force against the extension. The linear branch is offset by the lift force; the knee below -6 mm is the bottoming|700](@fig:fs)

Raise **Motion amplitude** to 1.05 and the bottoming rebound peels the lip: the box is lost at 4.93 s.
@@ figures bounce
{
  "run": {
    "kind": "plot", "model": "bounce", "xlim": [0.8, 7.2],
    "rows": [
      {"ylabel": "chirp f [Hz]", "series": [{"signal": "Tool/f", "label": "Tool/f"}]},
      {"ylabel": "ext [mm]", "series": [{"signal": "Cup/ext", "label": "Cup/ext", "scale": 1000}], "hlines": [{"y": -6, "label": "-s_bot"}], "legend": true},
      {"ylabel": "F_bot [N]", "series": [{"signal": "Cup/F_bot", "label": "Cup/F_bot"}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup/U", "label": "Cup/U"}], "hlines": [{"y": 1.0, "label": "U = 1"}], "legend": true}
    ]
  },
  "fs": {
    "kind": "plot", "model": "bounce", "row_height": 4.0, "width": 800,
    "rows": [
      {"ylabel": "Fs [N]", "x": "Cup/ext", "x_scale": 1000, "xlabel": "ext [mm]", "xlim": [-8, 8], "ylim": [-90, 35], "series": [{"signal": "Cup/Fs", "label": "Cup/Fs", "lw": 0.8}]}
    ]
  }
}
@@ page steps overview - | Horizontal steps
# Horizontal steps: sway, tilt and peel

The tool makes three moves along x with alternating direction. Each move is an acceleration pulse of 0.15 s, a coast of 0.6 s and a deceleration pulse, at 1.5, 3 and 4.5 m/s². The pulses have 8 ms edges, so they are close to steps.

The box lags behind, the bellows shears ([Cup/ex](signal:Cup/ex)) and the box tilts ([Mon/sway](signal:Mon/sway)). The lateral load and the tilting moment raise the lip load on one side. Each pulse rings both lateral modes: the FFT of the coast after the first pulse gives 6.59 Hz (sway) and 13.13 Hz (tilt), against 6.55 and 13.20 Hz from the linearised model.

![Tool acceleration, lateral deflection, box tilt and U|900](@fig:run)

The peak U is 0.90 at the 4.5 m/s² pulse. The quasi-static value is 0.61: a sudden pulse overshoots the static deflection. The lip never lifts, and the box is held.

![Lateral force against the lateral deflection: the bellows spring with its damping loops|700](@fig:lat)
@@ figures steps
{
  "run": {
    "kind": "plot", "model": "steps", "xlim": [0.8, 6.0],
    "rows": [
      {"ylabel": "a_x [m/s²]", "series": [{"signal": "Tool/ax", "label": "Tool/ax"}]},
      {"ylabel": "ex [mm]", "series": [{"signal": "Cup/ex", "label": "Cup/ex", "scale": 1000}]},
      {"ylabel": "box tilt [°]", "series": [{"signal": "Mon/sway", "label": "Mon/sway"}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup/U", "label": "Cup/U"}], "hlines": [{"y": 1.0, "label": "U = 1"}], "legend": true}
    ]
  },
  "lat": {
    "kind": "plot", "model": "steps", "row_height": 4.0, "width": 800,
    "rows": [
      {"ylabel": "Flx [N]", "x": "Cup/ex", "x_scale": 1000, "xlabel": "ex [mm]", "xlim": [-1.6, 1.6], "series": [{"signal": "Cup/Flx", "label": "Cup/Flx", "lw": 0.8}]}
    ]
  }
}
@@ page swing overview - | Tool-tilt swing
# Tool-tilt swing: tilt compliance and moment capacity

The tool tilts about its flange to 30° in 0.8 s, holds for 0.6 s and returns. Gravity now has a component across the cup: the pull falls to $mg\cos\theta$, and the shear $mg\sin\theta$ deflects the bellows sideways and tilts the box. At 30° the lateral deflection is 1.013 mm (hand: 1.016 mm) and U is 0.603 (hand: 0.620).

Then the tool swings ±10° at 1.5 Hz for three cycles. The fast swing adds the inertia of the box to the shear and the moment: U peaks at 0.84, and the box is held.

![Tool angle, lateral deflection, box tilt and U|900](@fig:run)
@@ figures swing
{
  "run": {
    "kind": "plot", "model": "swing", "xlim": [0.8, 6.8],
    "rows": [
      {"ylabel": "tool tilt [°]", "series": [{"signal": "Tool/theta", "label": "Tool/theta"}]},
      {"ylabel": "ex [mm]", "series": [{"signal": "Cup/ex", "label": "Cup/ex", "scale": 1000}], "hlines": [{"y": 1.016, "label": "hand, 30°"}], "legend": true},
      {"ylabel": "box tilt [°]", "series": [{"signal": "Mon/sway", "label": "Mon/sway"}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup/U", "label": "Cup/U"}], "hlines": [{"y": 0.62, "label": "hand, 30°"}], "legend": true}
    ]
  }
}
@@ page chirp overview - | Lateral chirp
# Lateral chirp: transmissibility

The tool moves sideways with a chirp from 1.5 to 20 Hz in 10 s. The amplitude rises from 0.12 to 0.4 mm. [Transmissibility](block:Trans) demodulates the lateral motion of the box's centre of mass and of the tool at the chirp phase. It low-pass filters both and divides them: [Trans/TR](signal:Trans/TR) against the filtered frequency [Trans/fl](signal:Trans/fl).

![Chirp frequency, transmissibility, lateral deflection and U|900](@fig:run)

![Transmissibility against frequency|700](@fig:tr)

The curve has two peaks: 2.75 at 6.6 Hz (sway) and 3.28 at 13.4 Hz (tilt). Between them, near 8 Hz, the box hardly moves (TR 0.34). The steady-state linear model gives a peak of 4.58 at 6.5 Hz. The sweep crosses each resonance in a few cycles, too fast to reach the steady state, and the demodulator smooths the peak. The tilt resonance loads the lip most: U peaks at 0.71 there.
@@ figures chirp
{
  "run": {
    "kind": "plot", "model": "chirp", "xlim": [0.8, 11.5],
    "rows": [
      {"ylabel": "chirp f [Hz]", "series": [{"signal": "Tool/f", "label": "Tool/f"}]},
      {"ylabel": "TR [-]", "series": [{"signal": "Trans/TR", "label": "Trans/TR"}]},
      {"ylabel": "ex [mm]", "series": [{"signal": "Cup/ex", "label": "Cup/ex", "scale": 1000}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup/U", "label": "Cup/U"}]}
    ]
  },
  "tr": {
    "kind": "plot", "model": "chirp", "row_height": 3.6, "width": 800,
    "rows": [
      {"ylabel": "TR [-]", "x": "Trans/fl", "xlabel": "frequency [Hz]", "xlim": [1.5, 19], "ylim": [0, 3.6], "series": [{"signal": "Trans/TR", "label": "Trans/TR"}], "vlines": [{"x": 6.55, "label": "sway 6.55 Hz"}, {"x": 13.2, "label": "tilt 13.2 Hz"}], "legend": true}
    ]
  }
}
@@ page overload overview - | Overload
# Overload: the box is lost

This model uses the `steps` motion with a 0.8 kg box and pulses of 3, 6 and 9 m/s².

The first move (3 m/s²) holds, with U up to 0.87. In the 6 m/s² pulse of the second move (quasi-static U 0.996) the dynamic load passes the capacity. U reaches 1, the peeling moment lifts the lip ([Cup/h](signal:Cup/h)), the gap leaks, the vacuum collapses within 20 ms, and the `sealed` latch drops at 2.51 s. The box falls onto the table, and [Mon/held](signal:Mon/held) drops to 0.

![Tool acceleration, U, lip gap, vacuum and held flag|900](@fig:run)
@@ figures overload
{
  "run": {
    "kind": "plot", "model": "overload", "xlim": [0.8, 3.2],
    "rows": [
      {"ylabel": "a_x [m/s²]", "series": [{"signal": "Tool/ax", "label": "Tool/ax"}]},
      {"ylabel": "U [-]", "series": [{"signal": "Cup/U", "label": "Cup/U"}], "hlines": [{"y": 1.0, "label": "U = 1"}], "legend": true},
      {"ylabel": "lip gap [mm]", "series": [{"signal": "Cup/h", "label": "Cup/h", "scale": 1000}]},
      {"ylabel": "vacuum [kPa]", "series": [{"signal": "Cup/dp", "label": "Cup/dp", "scale": 0.001}]},
      {"ylabel": "flags", "series": [{"signal": "Cup/sealed", "label": "Cup/sealed"}, {"signal": "Mon/held", "label": "Mon/held", "style": "--"}], "legend": true}
    ]
  }
}
@@ page linear-vs-nonlinear overview - | Linear vs nonlinear
# Linear vs nonlinear cup

Two identical cups and boxes hang side by side on the `bounce` motion. [Cup](block:Cup) (left, blue box) has the nonlinear bellows. [CupL](block:CupL) (right, sand box) has $k_{bot}$, $A_{fold}$, $c_{vac}$ and $c_{ext}$ at 0, which is the linear cup.

![Both cups in the 3D view|700](@fig:scene)

- **Hang.** The linear cup stretches to +2.35 mm. The nonlinear cup is pulled shut by the vacuum and hangs at −1.68 mm. The difference is the lift stroke $A_{fold}\Delta p/k_{ax}$ = 4.02 mm, so the nonlinear box hangs 4 mm higher.
- **Small motions.** Both ring at the same 10.27 Hz after the step. The lift stroke shifts the operating point but not the axial stiffness.
- **Large motions.** In the chirp the nonlinear cup starts 1.7 mm closer to its 6 mm compression limit and bottoms (69 N). The rebound raises its peak U to 0.87. The linear cup never bottoms, and its peak U is 0.64. Both hold. With 3 % more amplitude the nonlinear cup loses the box and the linear one does not.
- **Sideways.** The nonlinear cup is 1.87 times stiffer sideways (vacuum and compression), so its lateral modes are 6.6 / 13.2 Hz against 4.9 / 9.7 Hz.

![Extension, bottoming force and U of both cups|900](@fig:run)

![Force-stroke of the nonlinear cup (top) and the linear cup (bottom)|700](@fig:fs)
@@ figures linear-vs-nonlinear
{
  "scene": {"kind": "scene", "model": "linear-vs-nonlinear", "t": 1.5, "zoom": 5},
  "run": {
    "kind": "plot", "model": "linear-vs-nonlinear", "xlim": [0.8, 7.2],
    "rows": [
      {"ylabel": "ext [mm]", "series": [{"signal": "Cup/ext", "label": "Cup/ext (nonlinear)", "scale": 1000}, {"signal": "CupL/ext", "label": "CupL/ext (linear)", "scale": 1000}], "legend": true},
      {"ylabel": "F_bot [N]", "series": [{"signal": "Cup/F_bot", "label": "Cup/F_bot"}, {"signal": "CupL/F_bot", "label": "CupL/F_bot"}], "legend": true},
      {"ylabel": "U [-]", "series": [{"signal": "Cup/U", "label": "Cup/U"}, {"signal": "CupL/U", "label": "CupL/U"}], "hlines": [{"y": 1.0, "label": "U = 1"}], "legend": true}
    ]
  },
  "fs": {
    "kind": "plot", "model": "linear-vs-nonlinear", "row_height": 3.2, "width": 800,
    "rows": [
      {"ylabel": "Fs [N]", "x": "Cup/ext", "x_scale": 1000, "xlabel": "ext [mm] (nonlinear)", "xlim": [-8, 8], "ylim": [-90, 35], "series": [{"signal": "Cup/Fs", "label": "Cup/Fs", "lw": 0.8}]},
      {"ylabel": "Fs [N]", "x": "CupL/ext", "x_scale": 1000, "xlabel": "ext [mm] (linear)", "xlim": [-8, 8], "ylim": [-90, 35], "series": [{"signal": "CupL/Fs", "label": "CupL/Fs", "lw": 0.8, "color": "#d95f02"}]}
    ]
  }
}
