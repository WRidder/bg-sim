# The flapping drive and the aeroelastic wing

## Drive

```
 Drv (ElectricDrive: R = 0.15 Ohm, k_t = 0.0125 N m/A, J = 4e-06 kg m^2) -- Gear (IdealGear, N = 28) -- Crank -- ShaftL (ElasticShaft) -- JL1.drive
                                                                         \-- ShaftR (ElasticShaft) -- JR1.drive
```

[Drv](block:Drv) is the stdlib bond-graph DC motor, [Gear](block:Gear) an ideal gear of ratio 28, and [Crank](block:Crank) a power-conserving **modulated transformer with three rotation ports**
for the crank-rocker linkage of the thesis' actuation (a four-bar linkage in the real bird, reduced here to its kinematic map with a second harmonic for the asymmetric up/down stroke):

$$\varphi(\psi) = \Phi\,[\sin\psi + h_2\sin(2\psi + \varphi_2)], \qquad \dot\varphi_{L,R} = a_{L,R}\,\varphi'(\psi)\,\dot\psi, \qquad \tau_{crank} = -\varphi'(\psi)\,(a_L\tau_L + a_R\tau_R),$$

$\Phi$ = 0.5 rad, $h_2$ = 0.06. The factors $a_L, a_R$ (nominally 1) scale the stroke amplitude of each wing: **asymmetric flapping amplitude**, the roll input of the flight controller next to the tail.
Each wing hangs on the crank through an `ElasticShaft` (120 N m/rad): a rigid coupling of the motor inertia to the multibond joint rate is derivative-causal (W201), the shaft keeps every storage element integral and models the compliance of the real linkage.
[FlapCtl](block:FlapCtl) is the analogue speed regulator of the motor (PI plus the motor model as feed-forward, back-calculation anti-windup, voltage limit $0.98\,V_{bat}$ = 21.8 V of the 6S pack) that makes the crank turn at the commanded flapping frequency $f$: measured within-stroke speed ripple
10.6 rad/s RMS on the motor, i.e. 1.5 % of the mean speed. The measured flapping frequency of the full run is 3.69 to 4.50 Hz (thesis: 2 to 4 Hz).

The **rear rod** of the thesis' actuator ("the rear rod has a phase lag with respect to the front rod. This creates a changing angle of attack for the up and down-stroke of the wing") is the kinematic rest angle of the torsion spring of the root joint,
$\theta_{rest} = \Theta\sin(\psi + \psi_s) - \theta_{inc}$ ($\Theta$ = 0.3 rad, $\psi_s$ = 0.8 rad, rigging incidence $\theta_{inc}$ = 0.12 rad): like the thesis, both rods are velocity-controlled inputs (`Crank.pitL`, `pitR`).

## Aeroelastic wing

[JL1](block:JL1) and [JL2](block:JL2) are `WingJoint`s: the joint coordinate $q$ (flap, resp. bend) is exact; the other held directions are springs with dampers.

| joint | spring | value | thesis source |
| --- | --- | --- | --- |
| flap, root | drive through the crank | - | actuation rods |
| torsion about the span axis | $k_{r,p}$ on $d\theta_x - \theta_{rest}$ | 0.6 (root), 0.5 (outer) N m/rad, damping 0.01, 0.008 | $K_o$, $R$ of the 6D connector (eq. 4-7, 15, 17), values assumed |
| bend, outer against inner | $k$, $b$ on $q$ | 12.0 N m/rad ($E I / L$, $E I$ = 2.4 N m$^2$ of two carbon rods), 0.06 N m s/rad | $E_f I_x + E_r I_r$ (eq. 15), assumed moduli |
| sweep | held rotation | 40.0 N m/rad | $K_o$ |
| pivot translations | held, three directions | 2e+04 N/m, damping 25.0 N s/m | $K_t$ (eq. 16) |

Measured in the full run (after 8 s): flap stroke $\pm 0.51$ rad, root torsion up to 0.17 rad, bend up to 0.07 rad.

![Flapping: stroke, bend and torsion over 1.5 s, flapping frequency over the run|900](assets/22b04ef3f129.png)
