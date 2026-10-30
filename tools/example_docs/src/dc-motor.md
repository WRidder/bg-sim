@@ figures iconic
{
  "diagram": {"kind": "diagram", "model": "iconic"},
  "scene": {"kind": "scene", "model": "iconic", "t": 0.2},
  "run": {
    "kind": "plot", "model": "iconic", "xlim": [0, 0.1],
    "rows": [
      {"ylabel": "rotor speed [rad/s]", "series": [{"signal": "Motor1/shaft.f", "label": "Motor1/shaft.f"}],
       "hlines": [{"y": 239.80815347721824, "label": "k V / (k² + R d) = 239.808 rad/s"}], "legend": true},
      {"ylabel": "winding current [A]", "series": [{"signal": "Motor1/i", "label": "Motor1/i", "color": "#d95f02"}]}
    ]
  }
}
@@ page iconic overview - | Overview
# DC motor, iconic model

The walking skeleton of bg-sim (plan 9.1, milestone M1): a permanent-magnet DC motor driven by a 12 V step, built **twice**. This model is the *iconic* version, made of ready-made components; the bond graph version is documented in the model `bondgraph` and must give the same rotor speed. A third variant, `speed-control`, closes a sampled PI loop around the same plant.

The diagram contains a [step source](block:Step1), a [voltage source](block:V1), the [DC motor](block:Motor1) with its housing fixed by [FixHousing](block:FixHousing), a [damper](block:Damp1) to a [fixed shaft](block:FixShaft) and the electrical [ground](block:Ground1).

![Diagram of the iconic model|800](@fig:diagram)

## Run it

1. Press **Run** (Ctrl+Enter) and plot [Motor1/shaft.f](signal:Motor1/shaft.f). The speed settles at $\omega_\infty = 239.808\ \mathrm{rad/s}$ (see [Results](page:results)).
2. Change `R` of `Motor1` and run again. A parameter-only re-run reuses the compiled system, so it takes a few tens of milliseconds: a good place to feel the edit/run loop.
3. Raise the damper's `d` and watch the steady speed drop.
4. Zoom the plot: the UI re-requests the data for the new window.

## 3D view

`scenes/dc-motor.sdf` shows the motor housing and a rotor disc with a stripe. The joint `shaft` follows the rotor angle `Motor1/rotor/phi`, so the stripe turns at the simulated speed (about 240 rad/s: use a slow playback speed).

![3D view at t = 0.2 s|500](@fig:scene)
@@ page iconic physics overview | Physics
# Physics of the DC motor

The `DCMotor` block couples the electrical winding to the shaft through the torque constant $k_t$. With winding current $i$, shaft speed $\omega$ and supply voltage $V$ the two energy storages (winding inductance and rotor inertia) give

$$L\,\frac{di}{dt} = V - R\,i - k_t\,\omega, \qquad J\,\frac{d\omega}{dt} = k_t\,i - d\,\omega .$$

The coupling is a gyrator: the same constant $k_t$ converts current to torque and speed to back-EMF, so no power is created or lost in the conversion. The viscous damping $d$ of the rotor is modelled in a separate `RotationalDamper` (`Damp1`), because the `DCMotor` of this model has `d = 0`.

## Parameters

| quantity | symbol | value | unit |
| --- | --- | --- | --- |
| winding resistance | $R$ | 2 | Ω |
| winding inductance | $L$ | 5e-4 (0.5 mH) | H |
| torque constant | $k_t$ | 0.05 | N·m/A |
| rotor inertia | $J$ | 1e-5 | kg·m² |
| damping in `DCMotor` | $d$ | 0 | N·m·s/rad |
| damper `Damp1` | $d$ | 1e-6 | N·m·s/rad |
| supply | $V$ | 12 V step at $t = 0.01$ s (Step1: 0 to 12) | V |
| `t_end` | | 1 | s |

## Steady state

Setting both derivatives to zero gives $i = (V - k_t \omega)/R$ and $k_t i = d\,\omega$, so

$$\omega_\infty = \frac{k_t V}{k_t^2 + R\,d} = \frac{0.05 \cdot 12}{0.05^2 + 2 \cdot 10^{-6}} = 239.808\ \mathrm{rad/s}, \qquad i_\infty = \frac{d\,\omega_\infty}{k_t} = 4.796\ \mathrm{mA}.$$

The electrical time constant $L/R = 0.25\ \mathrm{ms}$ is much faster than the mechanical one, about $J R/k_t^2 = 8\ \mathrm{ms}$ (the back-EMF acts as a damper of $k_t^2/R$), so the speed reaches 240 rad/s within about 40 ms of the step.
@@ page iconic results overview | Results
# Results

![Rotor speed and winding current after the step at 0.01 s|900](@fig:run)

At the start the winding current jumps to nearly $V/R = 6$ A (the back-EMF is still zero) and decays to the load current while the speed builds up.

## Acceptance checks (`expected.json`)

| check | expected | tolerance |
| --- | --- | --- |
| `Motor1/shaft.f` at $t = 1$ s | 239.80815347721824 rad/s | relative 1e-4 |
| `Motor1/shaft.f` at $t = 0.2$ s (the number the Playwright test reads) | 239.8 rad/s | 0.1 |
| `Motor1/i` at $t = 1$ s | 0.004796163069544365 A | relative 1e-4 |
| iconic vs bond graph, `Motor1/shaft.f` against `IJ/p.f`, from $t = 0.5$ s | difference | below 1e-6 rad/s |
| 3D bindings | scene file matches the bindings | |

The legend shows rotation speed in `1/s`; radians are dimensionless in the unit system, the plan quotes the same quantity as rad/s.

See also the [physics page](page:physics).
@@ figures bondgraph
{
  "diagram": {"kind": "diagram", "model": "bondgraph"},
  "scene": {"kind": "scene", "model": "bondgraph", "t": 0.5}
}
@@ page bondgraph overview - | Overview
# DC motor, bond graph model

The same motor as in `iconic`, written as a bond graph (plan 9.1). The chain is

$$S_e \to 1_{J1}\,(R,\ I) \to GY \to 1_{J2}\,(I,\ R)$$

- [Se1](block:Se1): constant effort source, $e = 12\ \mathrm{V}$ (no step, unlike the iconic model);
- [J1](block:J1): 1-junction, common current $i$, with [R1](block:R1) (`r` = 2 Ω) and [IL](block:IL) (`i` = 5e-4 H, the winding inductance);
- [GY1](block:GY1): gyrator with `r` = 0.05 (the torque constant $k_t$);
- [J2](block:J2): 1-junction, common speed $\omega$, with [IJ](block:IJ) (`i` = 1e-5 kg·m², the rotor inertia) and [Rd](block:Rd) (`r` = 1e-6, the viscous damping).

![Diagram of the bond graph model|800](@fig:diagram)

## Equations

On a 1-junction the flows are equal and the efforts sum to zero; the gyrator exchanges efforts and flows with the ratio $k_t$:

$$e_{GY,1} = k_t\,\omega, \qquad e_{GY,2} = k_t\,i .$$

$$L\,\dot i = 12 - R\,i - k_t\,\omega, \qquad J\,\dot\omega = k_t\,i - d\,\omega .$$

These are the equations of the `iconic` model with $d = 10^{-6}$ taken at the rotor junction. Both models therefore settle at the same $\omega_\infty = 239.808\ \mathrm{rad/s}$. The `Se` is a constant 12 V from $t = 0$, so only the settled part is comparable with the iconic run: from $t = 0.5$ s the two speeds (`IJ/p.f` and `Motor1/shaft.f`) agree to better than 1e-6 rad/s (the acceptance threshold in `expected.json`).

## Run it and the checks

Plot [IJ/p.f](signal:IJ/p.f) (the rotor speed) and [Rd/p.f](signal:Rd/p.f) (the same flow seen at the damper). The check `final_value` expects $\omega(1\,\mathrm{s}) = 239.80815347721824\ \mathrm{rad/s}$ within relative 1e-4.

## 3D view

The bond graph has no angle signal, so the rotor disc of the scene is coloured by the rotor speed [IJ/p.f](signal:IJ/p.f) (heat map from 0 to 240 rad/s).

![3D view at t = 0.5 s|500](@fig:scene)
@@ figures speed-control
{
  "diagram": {"kind": "diagram", "model": "speed-control"},
  "run": {
    "kind": "plot", "model": "speed-control", "xlim": [0, 0.3],
    "rows": [
      {"ylabel": "speed [rad/s]", "series": [{"signal": "WmSens/y", "label": "measured"}, {"signal": "Step1/y", "label": "reference", "style": "--"}], "legend": true},
      {"ylabel": "voltage [V]", "series": [{"signal": "PID1/y", "label": "PID1/y (command)"}], "hlines": [{"y": 24, "label": "limit 24 V"}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "Motor1/i", "label": "Motor1/i", "color": "#d95f02"}]}
    ]
  }
}
@@ page speed-control overview - | Overview
# DC motor with sampled speed control

The plant of the `iconic` model is closed with a 1 ms discrete PI controller (plan 9.1, milestone M2). The 12 V source is replaced by a [VoltageSource](block:V1) driven by a [DiscretePID](block:PID1); the reference is a 100 rad/s step at 0.01 s ([Step1](block:Step1)).

```
Step1 --> Err (u1 - u2) --> PID1 --> V1.u --> motor
  ^                                            |
  +-------- WmSens.y <-- SpeedSensor <---------+
```

![Diagram of the speed-control model|800](@fig:diagram)

- **Error node.** [Err](block:Err) is a two-input inline block `y = u1 - u2` (the stdlib `Sum` takes one vector input, which a JSON signal graph cannot assemble from scalars).
- **Sensor.** [WmSens](block:WmSens) is a zero-effort tap on the same wire node as the motor shaft and the damper, so it reads the rotor speed.
- **Supply limit.** The controller output is clamped to $\pm 24$ V; at 24 V the motor alone would settle at 479.6 rad/s, so the drive is voltage-limited, not speed-limited.

Plant parameters are those of the `iconic` model ($R = 2\ \Omega$, $L = 0.5$ mH, $k_t = 0.05$ N·m/A, $J = 10^{-5}$ kg·m², damper $10^{-6}$ N·m·s/rad); the run lasts 0.3 s with 3001 points and `reltol` 1e-8.
@@ page speed-control controller overview | Controller
# The discrete PID

[PID1](block:PID1) runs at the sample period $T_s = 1\ \mathrm{ms}$ (a constant of the block) with the parameters

| parameter | value |
| --- | --- |
| `method` | 1 (backward Euler for the integral) |
| `Kp` | 0.28 V/(rad/s) |
| `Ti` | 0.01 s (so $K_i = K_p/T_i = 28$ V/(rad/s·s)) |
| `Td` | 0 (a PI; differencing the 1 ms speed samples would be noisy) |
| `lower`, `upper` | -24 V, +24 V |

At every tick, with error $u_k$, the block updates

$$I_k = I_{k-1} + T_s\,u_k, \qquad v_k = K_p\,u_k + \frac{K_p}{T_i}\,I_k + K_p T_d\,\frac{u_k - u_{k-1}}{T_s}, \qquad y_k = \operatorname{clamp}(v_k, -24, 24).$$

**Anti-windup.** If $v_k$ would leave the limits, the increment of this tick is taken back out of the integral ($I_k \leftarrow I_k - T_s u_k$) and $v_k$ is recomputed, so the integral does not wind up while the voltage saturates.
@@ page speed-control results overview | Results
# Results

![Speed, voltage command and winding current|900](@fig:run)

From the README and `expected.json` (all verified by `uv run examples/run_checks.py`):

- the command is clamped to exactly 24.000 V for the first sample of the step (`max_abs` of [PID1/y](signal:PID1/y) = 24, abs 1e-6, and `max_abs_le` 24);
- the measured speed [WmSens/y](signal:WmSens/y) is 100 +- 1 rad/s at $t = 0.1$ s and 100 +- 0.05 at $t = 0.15$ s (measured 99.996 and 100.000), with no overshoot (peak 100.000 rad/s, abs 0.05);
- the winding current [Motor1/i](signal:Motor1/i) peaks at 11.03 A on the step (24 V / 2 Ω minus the back-EMF building up), stays below the 12 A bound and settles at the 2.0 mA load current;
- no diagnostics E901, E101, E102, E103, E106 or W206.

Other numbers quoted in the README: 91.9 rad/s at 0.015 s and 99.14 rad/s at 0.04 s.
