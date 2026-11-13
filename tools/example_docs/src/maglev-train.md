@@ page @project overview - | Maglev train: what is modelled
# Maglev train

An **electromagnetic suspension (EMS)** train in the style of the Transrapid: magnets on the vehicle pull *up* towards a ferromagnetic rail on the underside of the guideway, and the gap between magnet and rail (about 10 mm) is kept by feedback, because the attraction grows when the gap shrinks: **a magnet alone is unstable**. A long stator (linear synchronous motor, LSM) in the guideway pushes the car forward.

| model | what it shows |
| --- | --- |
| [maglev-module](model:maglev-module) | One levitation module carrying a quarter of a car: lift-off from the skids, gap regulation at 10 mm, a guideway step and a payload step. The controller comes from an LQR design in `design/design.py`. |
| [maglev-module-open-loop](model:maglev-module-open-loop) | The same module without feedback, released 10 nm from its trim gap: the gap deviation grows with the unstable pole of the linearisation. |
| [maglev-vehicle](model:maglev-vehicle) | A 53 t car section on two such modules. The car body is a **3D rigid body** (floating base, spatial multibond) that heaves, pitches and travels; the LSM accelerates it to 430 km/h, it cruises and brakes on a guideway of sagging spans with one bump. |

Every plant is a **bond graph**. The coil and the magnet field are the stdlib `Electromagnet` (an energy-conserving IC-field with $L(h) = L_\infty + 2\alpha/h$ and $F = \alpha i^2/h^2$), the bogie, the secondary suspension and the skids are bond-graph elements, and the car body is the stdlib `RigidBody3D` on a `Free3D` joint. The scalar module graph is attached to the spatial body through the six drive ports of the joint: heave is `drive6`, pitch is `drive2` and the along-track motion is `drive4`.

## Where the numbers come from

See [parameters and sources](page:parameters). In short: the nominal gap (10 mm), the cruise speed (430 km/h), the acceleration (about 1 m/s²), the drag (Cd 0.26, 16 m²) and the car size and mass (27 m, 3.7 m, 53 t) are published Transrapid figures; the magnet constant, the coil, the chopper, the secondary suspension and the controller are **estimates** chosen here. The references of the checks are analytic (trim, weight balance, the open-loop pole) and independent nonlinear scipy simulations of the same equations (`design/design.py`). No published time series of a Transrapid levitation loop could be found, so there is no comparison with measured data.

@@ page @project parameters overview | Parameters and sources
# Parameters and sources

| quantity | value | status |
| --- | --- | --- |
| nominal gap $h_0$ | 10 mm | **published**: constant gap of about 10 mm (Transrapid; Wikipedia "Transrapid", Meisinger "40 years of Maglev") |
| cruise speed | 430 km/h | **published**: Shanghai Transrapid operating speed (not re-checked in this session) |
| acceleration | 1 m/s² | **published**: about 1 m/s² (Wikipedia "Transrapid") |
| drag | Cd 0.26, frontal area 16 m² | **published**: Wikipedia "Transrapid" (the area is marked "citation needed" there). The model's drag power at 400 km/h is 3.42 MW against the 3.53 MW quoted there. |
| car section | 27.0 m long, 3.7 m wide, 4.2 m high, 53 t empty | **published**: Transrapid vehicle brochure (end section; the 53 t is the passenger section, TR generation not named) |
| levitation chassis | four per section, 12-pole magnets | **published**: Schneider et al. 2022, coupled vehicle-guideway simulations of the TR08 (read through a search summary only) |
| span of the guideway | 24.768 m (double-span beam) | **recalled** from Transrapid guideway literature, not checked |
| chassis mass $m_b$ | 1.5 t per quarter | estimate (4 × 1.5 t = 6 t of the 53 t) |
| body mass $m_c$ | 11.75 t per quarter (47 t) | estimate (53 t minus the chassis) |
| magnet constant $\alpha$ | 5.777·10⁻⁴ H·m | estimate: $\alpha i_0^2/h_0^2 = (m_b + m_c) g$ at $i_0 = 150$ A (an equivalent magnet of N = 100 turns, 0.18 m² pole area, B = 0.94 T) |
| coil $R$, $L_\infty$ | 0.55 Ω, 30 mH | estimate ($R i_0^2$ = 12.4 kW per quarter = 0.93 kW/t, below the published 1.7 kW/t for levitation and guidance including the electronics) |
| chopper rail | ±800 V | estimate |
| secondary suspension | 1 Hz heave, ζ = 0.3 | estimate (typical air-spring ride) |
| skid gap, stop | 16 mm, 4 mm | estimate |
| guideway | sag 3 mm per span, one 2 mm × 12 m bump | estimate |
| LSM | 150 kN limit, 50 ms lag | estimate |
| guidance (lateral, roll, yaw) | stiff spring-dampers | estimate (the symmetric run never excites them) |

**Published validation data.** FRA/VNTSC measured TR08 vibrations at the Emsland test facility in 2001 (report DOT/FRA/ORD-02/06), but those are ground-vibration spectra and the report's data tables could not be read here. No levitation-gap, current or body-acceleration time series was found. The only published numbers used as a check are the cruise speed, the 1 m/s² acceleration and the drag power at 400 km/h.

@@ figures maglev-module
{
  "diagram": {"kind": "diagram", "model": "maglev-module"},
  "scene": {"kind": "scene", "model": "maglev-module", "t": 0.9},
  "run": {
    "kind": "plot", "model": "maglev-module", "xlim": [0, 8],
    "rows": [
      {"ylabel": "gap [mm]", "series": [{"signal": "Gap/y", "label": "Gap/y", "scale": 1000}, {"signal": "RefLag/y", "label": "RefLag/y (reference)", "scale": 1000, "style": "--"}], "legend": true},
      {"ylabel": "coil current [A]", "series": [{"signal": "EM/i", "label": "EM/i"}, {"signal": "Ctl/i_ff", "label": "Ctl/i_ff (trim current at the reference)", "style": "--"}], "legend": true},
      {"ylabel": "chopper voltage [V]", "series": [{"signal": "Ctl/v", "label": "Ctl/v"}], "hlines": [{"y": 800, "label": "rail"}]}
    ]
  },
  "disturb": {
    "kind": "plot", "model": "maglev-module", "xlim": [1.9, 8],
    "rows": [
      {"ylabel": "gap error [um]", "series": [{"signal": "Err/y", "label": "Err/y (gap - 10 mm)", "scale": 1000000}], "legend": true},
      {"ylabel": "coil current [A]", "series": [{"signal": "EM/i", "label": "EM/i"}], "hlines": [{"y": 150.0, "label": "trim at 13.25 t"}, {"y": 160.923, "label": "trim at 15.25 t"}], "legend": true}
    ]
  }
}
@@ page maglev-module overview - | Overview
# Levitation module

One EMS magnet module carries a quarter of a car section: a **levitation chassis** of 1.5 t under the rail and a **body share** of 11.75 t hanging from it on the secondary suspension (spring and damper, 1 Hz). Everything starts at rest on the **skids**, with the gap at 16.7 mm. The coil is energised from zero at the start. At 0.1 s the gap reference drops to 10 mm (through a 0.15 s lag), the magnet lifts the module off the skids at about 0.45 s and the controller holds 10 mm. At 2 s the guideway sinks by 1 mm (smoothed over about 10 ms), and at 4 s a payload of 2 t is added to the body share.

![The model canvas|900](@fig:diagram)

## What to try

- Open the **Dashboard**. Move **Guideway step** to −3 mm or +3 mm, or the **Payload step** to 4000 kg: the plots re-run. The gap returns to 10 mm in both cases because of the integral action; only the **current** changes with the weight, as $i = c_\mathrm{trim}\, h\,\sqrt{W'/W}$.
- Plot [EM/i](signal:EM/i) and [Ctl/v](signal:Ctl/v) during the lift-off: the chopper saturates at +800 V for about 25 ms while the coil is magnetised, the current overshoots to 241 A, and the module leaves the skids at 0.45 s.
- Open [maglev-module-open-loop](model:maglev-module-open-loop) to see the instability that the controller removes.

## 3D view

`scenes/maglev-module.sdf` is a side view: the rail on pillars, the magnet pad with its copper coil (coloured by [EM/i](signal:EM/i)) under it, and the body hanging on the secondary suspension. The gap deviation from 10 mm is drawn 20 times larger and the spring stretch 5 times larger than it is.

![3D view at t = 0.9 s|500](@fig:scene)

Continue with [the plant and the controller](page:design) and [the results](page:results).

@@ page maglev-module design overview | Plant and controller
# Plant and controller

## Bond graph

Velocities are positive **upward**; the gap is $h = z_\mathrm{rail} - z_\mathrm{bogie}$.

| part | bond graph |
| --- | --- |
| chopper | `MSe` [Amp](block:Amp) (voltage), limited to ±800 V by the controller |
| coil | 1-junction [Jc](block:Jc) (coil current) with the resistance [Rc](block:Rc), a current detector [Imeas](block:Imeas), and, through the 0-junction [Jv](block:Jv) with the voltage detector [Vcoil](block:Vcoil), the coil port of [EM](block:EM) |
| magnet | [EM](block:EM): `converters/Electromagnet`, co-energy $W' = L(h) i^2/2$, $L(h) = L_\infty + 2\alpha/h$. Its port $b$ is on the rail junction [Jr](block:Jr), its port $a$ on the bogie junction [Jb](block:Jb). |
| bogie | 1-junction [Jb](block:Jb) with the chassis mass [Chassis](block:Chassis) (`I`), its weight [Weight](block:Weight) (`Se`), the skid contact [Skid](block:Skid) (`HardStop`, 16 mm to 4 mm free travel) and the secondary suspension [Sus](block:Sus) (`SpringDamper`) |
| body | 1-junction [Jq](block:Jq) with the body mass [Body](block:Body), its weight [BodyWeight](block:BodyWeight) and the payload [Load](block:Load) |
| guideway | flow source [Rail](block:Rail) on [Jr](block:Jr): the rail velocity from a smoothed step |
| gap sensor | 0-junction [Jg](block:Jg) between rail and bogie; its flow is $\dot h$, and the integrator [Gap](block:Gap) gives the gap |

The coil carries $L(h)\,\dot i = v - R i + \dfrac{2\alpha i}{h^2}\,\dot h$ and the magnet pulls with $F = \alpha i^2/h^2$. The field stores exactly what flows in: the electrical port power $v\,i$ and the mechanical port power $F\,\dot h$ add up to $\mathrm{d}W/\mathrm{d}t$.

## Trim and the unstable pole

At the gap $h$ the magnet carries the weight $W = (m_b + m_c)\,g$ when the current is
$$ i_\mathrm{trim} = c_\mathrm{trim}\,h, \qquad c_\mathrm{trim} = \sqrt{W/\alpha} = 15000\ \mathrm{A/m}, $$
so 150 A at 10 mm. Linearised about this point (states $h$, $v_b$, spring stretch, $v_c$, $i$), the voltage-driven plant has the poles $+52.7$, $-67.1$, $-18.7$ and $-2.0 \pm 5.9\mathrm{j}$ 1/s: one **unstable real pole** at 52.7 1/s (8.4 Hz), the secondary-suspension mode at 1 Hz, and the coil/back-EMF modes.

## Controller

The block [Ctl](block:Ctl) (`GapController`, in `library/`) is full state feedback on the measured gap, its filtered rate (1 ms filter) and the coil current, with an integrator on the gap error and the trim feedforward:

$$ v = R\,i_\mathrm{ff} + a_1 (h - h_\mathrm{ref}) + a_2 \dot h_f + a_3 (i - i_\mathrm{ff}) + a_4 \!\int\!(h - h_\mathrm{ref}),\qquad i_\mathrm{ff} = c_\mathrm{trim}\,h_\mathrm{ref}, $$

limited to ±800 V with back-calculation anti-windup. The gains $a_k$ are the LQR solution on the bogie plant (`design/design.py`: weights 1 mm, 0.05 m/s, 20 A, and a small integral weight): $a_1 = 1.03\cdot10^6$ V/m, $a_2 = 7025$ V·s/m, $a_3 = -49$ V/A, $a_4 = 2\cdot10^6$ V/(m·s). With these gains the seven closed-loop poles (the five plant states, the derivative filter and the integrator) lie at $-1073$, $-126 \pm 176\mathrm{j}$, $-36$, $-8.6$ and $-1.8 \pm 6.1\mathrm{j}$ 1/s: stable, with the slow integral pole at $-8.6$ and the body mode left almost as it is.

Continue with [the results](page:results).

@@ page maglev-module results design | Results
# Results

![Gap, current and voltage|900](@fig:run)

- **Lift-off.** The coil is energised from zero; the chopper saturates at 800 V for 25 ms and the current reaches 241 A. The module sits on the skids (gap 16.0 mm, the contact compressed by 0.65 mm under the weight) until the force exceeds the weight at about 0.45 s, then follows the reference to 10 mm without undershooting it.
- **Steady state.** The current settles at the analytic trim 150.0 A, the magnet force equals the weight $(m_b + m_c)\,g = 129.98$ kN, and the gap error is below 3 µm before the guideway step.
- **Guideway step.** A 1 mm sink of the rail gives a peak gap deviation of 0.34 mm; the loop absorbs it within about 0.3 s.
- **Payload.** An extra 2 t gives a peak deviation of 1.25 mm and the integral action brings the gap back (1.2 µm left after 4 s). The trim current rises to 160.9 A, in step with the weight.

![Gap error and current after the steps|900](@fig:disturb)

The checks in `expected.json` compare these numbers with an independent scipy simulation of the same nonlinear equations and controller; bgsim and scipy agree within 15 µm in the gap over the 8 s.

@@ figures maglev-module-open-loop
{
  "diagram": {"kind": "diagram", "model": "maglev-module-open-loop"},
  "run": {
    "kind": "plot", "model": "maglev-module-open-loop", "xlim": [0, 0.3],
    "rows": [
      {"ylabel": "gap deviation [mm]", "series": [{"signal": "Err/y", "label": "Err/y", "scale": 1000}], "legend": true},
      {"ylabel": "growth rate [1/s]", "ylim": [0, 100], "series": [{"signal": "Growth/y", "label": "Growth/y"}], "hlines": [{"y": 52.6837, "label": "unstable pole 52.68 1/s"}], "legend": true}
    ]
  }
}
@@ page maglev-module-open-loop overview - | Overview
# Open-loop module

The module of [maglev-module](model:maglev-module) with **all feedback gains set to zero**: the chopper only holds the trim voltage $R\,i_\mathrm{trim}$. It starts exactly at its trim state with the gap **10 nm** too large. Because the magnet attracts more when the gap shrinks, the deviation grows exponentially, $\delta h \propto \mathrm{e}^{p t}$, with the unstable pole $p$ of the linearisation. The block [Growth](block:Growth) computes $\dot h / (h - h_0)$, which tends to $p$.

![The model canvas|900](@fig:diagram)

![Open-loop growth|900](@fig:run)

- The growth rate is 52.64 1/s at 0.15 s, against the unstable eigenvalue 52.68 1/s of the five-state linearisation (module, secondary suspension and coil), computed with scipy in `design/design.py`. It starts higher (the coil current responds first) and settles on the pole, until the deviation (about 0.06 mm at 0.2 s) leaves the linear range.
- This is the instability the gap controller has to remove: at 8.4 Hz the deviation doubles in 13 ms, so the control loop has to be fast, with a gap sensor and a chopper that react within about a millisecond.

@@ figures maglev-vehicle
{
  "diagram": {"kind": "diagram", "model": "maglev-vehicle"},
  "scene": {"kind": "scene", "model": "maglev-vehicle", "t": 135.5, "zoom": 4},
  "run": {
    "kind": "plot", "model": "maglev-vehicle", "xlim": [0, 276],
    "rows": [
      {"ylabel": "speed [m/s]", "series": [{"signal": "Speed/y", "label": "Speed/y"}, {"signal": "Profile/v", "label": "Profile/v", "style": "--"}], "hlines": [{"y": 119.44, "label": "430 km/h"}], "legend": true},
      {"ylabel": "force [kN]", "series": [{"signal": "Lsm/p.e", "label": "Lsm/p.e (LSM thrust)", "scale": 0.001}, {"signal": "Drag/p.e", "label": "Drag/p.e (aerodynamic drag)", "scale": 0.001, "style": "--"}], "legend": true},
      {"ylabel": "gap [mm]", "ylim": [9.0, 11.0], "series": [{"signal": "ModF/Gap/y", "label": "ModF/Gap/y", "scale": 1000}, {"signal": "ModR/Gap/y", "label": "ModR/Gap/y", "scale": 1000}], "legend": true}
    ]
  },
  "bump": {
    "kind": "plot", "model": "maglev-vehicle", "xlim": [134.0, 138.0],
    "rows": [
      {"ylabel": "guideway [mm]", "series": [{"signal": "GwF/z", "label": "GwF/z (front module)", "scale": 1000}, {"signal": "GwR/z", "label": "GwR/z (rear module)", "scale": 1000, "style": "--"}], "legend": true},
      {"ylabel": "gap error [um]", "series": [{"signal": "ModF/Err/y", "label": "ModF/Err/y", "scale": 1000000}, {"signal": "ModR/Err/y", "label": "ModR/Err/y", "scale": 1000000}], "legend": true},
      {"ylabel": "body", "series": [{"signal": "AccZ/y", "label": "AccZ/y [m/s^2]"}, {"signal": "PitchRate/y", "label": "PitchRate/y [rad/s]", "scale": 100}], "legend": true}
    ]
  },
  "lift": {
    "kind": "plot", "model": "maglev-vehicle", "xlim": [0, 3],
    "rows": [
      {"ylabel": "gap [mm]", "series": [{"signal": "ModF/Gap/y", "label": "ModF/Gap/y", "scale": 1000}], "legend": true},
      {"ylabel": "heave [mm]", "series": [{"signal": "Free/pz", "label": "Free/pz", "scale": 1000}], "legend": true},
      {"ylabel": "current [A]", "series": [{"signal": "ModF/EM/i", "label": "ModF/EM/i"}], "legend": true}
    ]
  }
}
@@ page maglev-vehicle overview - | Overview
# Maglev car on a guideway

A car section of 53 t on **two levitation modules**, each the module of [maglev-module](model:maglev-module) with the masses and the magnet doubled (two chassis pairs, half the car body each). The car body is a 3D rigid body. At 0.1 s the gap reference drops from the skid gap to 10 mm and the car lifts off (it rises 6.7 mm). At 4 s the long stator starts a speed profile: 1 m/s² up to **430 km/h** (119.4 s), 30 s of cruise, and the same deceleration. The guideway is a row of 24.768 m spans that **sag by 3 mm** at mid-span, with one smooth **2 mm bump** (a joint between two beams) at 8.5 km.

![The model canvas|900](@fig:diagram)

## What to try

- On the Dashboard, change the **cruise speed** (30 to 119.5 m/s), the **sag** and the **bump height**. A bump of 6 mm still keeps the gap above the 8 mm limit that the checks use; read the gap and the body acceleration cards.
- Plot [AccZ/y](signal:AccZ/y), the vertical acceleration of the body's centre of mass, and [PitchRate/y](signal:PitchRate/y): the sag excites the car at $v/L_\mathrm{span}$, up to 4.8 Hz at cruise, and the bump pitches it because the rear module reaches the bump 19 m later.
- Plot [Lsm/p.e](signal:Lsm/p.e) and [Drag/p.e](signal:Drag/p.e): at cruise they are equal (35.6 kN), during braking the LSM pushes back.

## 3D view

`scenes/maglev-train.sdf` shows the car on a T-shaped guideway. The pillars scroll under the car with the span phase ([GwF/ph](signal:GwF/ph)), so the car stays in view for the whole 17.8 km. The gap pads, the heave and the pitch are drawn **100 times larger** than they are (the nominal gap itself is true to scale); the copper coils are coloured by the coil current.

![3D view at t = 135.5 s|700](@fig:scene)

Continue with [the 3D body](page:body), [the guideway](page:track) and [the results](page:results).

@@ page maglev-vehicle body overview | The 3D car body
# The 3D car body

| part | element |
| --- | --- |
| [World](block:World) | `multibond/GroundSpatial` |
| [Free](block:Free) | `spatial/Free3D`: a floating base. Its pose is seven states (unit quaternion and the position of the body origin); its six **drive ports** carry the relative twist in the body frame: $\omega_x, \omega_y, \omega_z$ (rotation) and $v_x, v_y, v_z$ (translation). |
| [Body](block:Body) | `spatial/RigidBody3D`: spatial inertia, the Coriolis (Eulerian) term and gravity from the pose $g$. 47 t, $J = (1.2\cdot10^5,\ 2.9\cdot10^6,\ 2.9\cdot10^6)$ kg·m² (a homogeneous box of 27 × 3.7 × 4.2 m). |
| along the track | [Jx](block:Jx) on `drive4`: LSM thrust [Lsm](block:Lsm) (`MSe`, after a 50 ms lag), aerodynamic drag [Drag](block:Drag) (`MR` with $r = k_\mathrm{aero}\,\lvert v \rvert$, $k_\mathrm{aero} = \tfrac12\rho C_d A = 2.496$ N·s²/m²) and the speed detector [Speed](block:Speed) |
| heave and pitch | [Jz](block:Jz) on `drive6` and [Jt](block:Jt) on `drive2`; the levers below |
| guidance | [JLat](block:JLat), [JRoll](block:JRoll), [JYaw](block:JYaw) on `drive5`, `drive1`, `drive3`: stiff spring-dampers (guidance magnets) that hold the lateral, roll and yaw degrees of freedom |
| modules | [ModF](block:ModF) and [ModR](block:ModR) (front and rear, 9.5 m from the centre of mass), two instances of the library subsystem `LevitationModule` (`library/LevitationModule.bgsub.json`) |

**Levers.** The velocity of the module point at $x = \pm 9.5$ m, in the world's vertical direction, is
$$ v_\mathrm{pt} = v_z - x\,\omega_y + R_{31}\, v_x, \qquad R_{31} = -2\,q_y, $$
the heave, the pitch lever and the forward speed's vertical component when the car is pitched. Bond graph: a 0-junction ([ZF](block:ZF), [ZR](block:ZR)) adds the heave flow from [Jz](block:Jz), the pinion flow of the `RackAndPinion` [LeverF](block:LeverF) (radius 9.5 m, from the pitch rate) and the flow of the modulated transformer [ClimbF](block:ClimbF) (modulus $R_{31}$ from [R31](block:R31), on [Jx](block:Jx)). The same elements carry the forces back: the module force acts on heave, on pitch through the lever and, through $R_{31}$, on the along-track motion (a component of $-\theta F$). The $R_{31} v_x$ term matters at 430 km/h: a pitch of 0.1 mrad makes 12 mm/s of vertical velocity, as large as the heave velocity from a 3 mm sag. Without it the body heave drifts away from the integral of the gap loops.

## Why the module is a scalar graph

A levitation module is one-dimensional: the force acts along the guideway normal, the gap is a single coordinate. It is therefore the scalar module of [maglev-module](model:maglev-module) (one coil, one gap, one chassis), and only the car body, the part that heaves, pitches and travels, is a spatial body. The stdlib has no element that converts a spatial port to a scalar one, so the drive ports of `Free3D` are the interface.

Continue with [the guideway](page:track).

@@ page maglev-vehicle track body | The guideway and the speed profile
# The guideway and the speed profile

The block [GwF](block:GwF) (and [GwR](block:GwR)), `Guideway` in `library/`, gives the rail deflection under a module at the track coordinate $s$ (the body $x$ plus or minus 9.5 m):

$$ z(s) = A_\mathrm{sag}\sin^2\!\frac{\pi s}{L_\mathrm{span}} + \frac{A_b}{2}\Bigl(1 - \cos\frac{2\pi (s - s_b)}{\lambda_b}\Bigr)\ \ (s_b \le s \le s_b + \lambda_b), $$

positive towards the vehicle, and the rail velocity $-v\,\mathrm{d}z/\mathrm{d}s$ that drives the flow source `Rail` inside the module [ModF](block:ModF). A guideway with $z(s)$ at a joint is a lookup law, which is why this one block is a library block. The same function is in `design/design.py`.

The speed profile is the stdlib `TrapezoidalProfile` [Profile](block:Profile); the block [LsmCtl](block:LsmCtl) (`LsmController`) adds the acceleration and the drag as feedforward to a PI on the speed error and limits the thrust to 150 kN.

## Excitation

The sag has the wavelength $L_\mathrm{span} = 24.768$ m, so the excitation frequency is $v/L_\mathrm{span}$: 2.4 Hz at 215 km/h and 4.8 Hz at 430 km/h, close to the secondary suspension at 1 Hz and its harmonics only at low speed. The gap loop (poles around 130 to 1000 1/s) follows the rail; what reaches the body is the filtered remainder.

@@ page maglev-vehicle results track | Results
# Results

![Speed, thrust, drag and the gaps over the whole run|900](@fig:run)

![Lift-off|700](@fig:lift)

![The bump at 134.8 s|900](@fig:bump)

- **Levitation at rest.** After lift-off each module draws the trim current 150.0 A, carries $(m_b + m_c)g = 260$ kN (half the body and its chassis), and the body has risen by $h_\mathrm{rest} - h_0 = 6.7$ mm.
- **Speed.** $v = a(t - t_\mathrm{go})$ during the acceleration (56 m/s at 60 s), 119.44 m/s at cruise. The thrust is 35.6 kN at cruise and equals the aerodynamic drag $k_\mathrm{aero} v^2$. The aerodynamic power at 400 km/h is 3.42 MW; Wikipedia quotes 3.53 MW (with the same Cd and area, so this is a consistency check and not a validation).
- **Gaps.** Within 9.5 mm and 10.5 mm over the whole run, the skids carry nothing after the lift-off.
- **Ride.** The sag and the bump keep the body acceleration below 0.5 m/s² (peak, unweighted) and the pitch below 0.2 mrad. The bump is passed by the front module first and by the rear module 0.16 s later at cruise.
- **Reference.** A planar scipy simulation of the same car (heave, pitch, two modules, LSM, guideway; `design/design.py`) agrees with this model within 15 µm in the position of the body's centre and within about 70 µm in the gap during the bump, the checks give the tolerances.
