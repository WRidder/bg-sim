# Control blocks

The signal and control blocks are in the **Continuous**, **Discrete and logic** and **Sources and sinks** categories of the library. Select a block and press `F1`, or click its help button in the library, for the full parameter list. All frequencies are angular, in **rad/s**. Every block here can be [exported](page:export) to C and FMU.

## Linear systems

| Block | What it does | Key parameters |
| --- | --- | --- |
| `TransferFunction` | `num(s)/den(s)`, coefficients in descending powers of s | `num` (m + 1 values), `den` (n + 1 values); constants `n` (the order) and `m` (the numerator degree, `n` by default) |
| `ZeroPole` | `gain·(s − z1)…(s − zm) / ((s − p1)…(s − pn))` | `gain`, `zero_re`, `zero_im`, `pole_re`, `pole_im`; constants `n` (poles), `m` (zeros) |
| `StateSpace` | `x' = A·x + B·u`, `y = C·x + D·u` | `A`, `B`, `C`; constants `N` (states) and `D` (the feedthrough, 0 by default) |

Notes:

- The transfer function must be proper: `den[1]` is not zero and the numerator degree `m` is at most `n`. `2/(s² + 3s + 2)` is `num = [2]` with `m = 0` and `den = [1, 3, 2]`; `num = [0, 0, 2]` with the default `m = n` gives the same response.
- **Linear blocks in a feedback loop.** A block whose output depends directly on its input (a direct feedthrough) closes an algebraic loop when it sits in a feedback loop. For the linear blocks the constants decide it, not the parameter values: `StateSpace` with `D = 0` (the default), `TransferFunction` with `m < n` and `ZeroPole` with `m < n` have no feedthrough and work in any loop. A `TransferFunction` whose numerator is padded with leading zeros to `n + 1` values (`m = n`) keeps the feedthrough path, even though its coefficient is 0: give it its `m + 1` values instead. When a loop cannot be solved because a feedthrough coefficient is zero in the run, the run fails, and an E903 next to the error names the blocks of the loop and the coefficient.
- In `ZeroPole`, the zeros and poles are given as real and imaginary parts. A complex pair starts at an odd position: position 1 and 2 hold `(re, im)` and `(re, −im)`, so set `pole_re = [-1, -1]`, `pole_im = [2, -2]` for `s = −1 ± 2j`. Only the first `m` zeros are used.

## Filters

| Block | What it does | Key parameters |
| --- | --- | --- |
| `LowPassButterworth` | maximally flat low-pass of order `n` (1 to 8) | `k` (DC gain), `wc` (−3 dB cutoff); constant `n` |
| `LowPassBessel` | low-pass with the flattest group delay (little overshoot), order `n` (1 to 8) | `k`, `wc` (−3 dB cutoff); constant `n` |
| `BandPass` | second-order band-pass, gain `k` at `w0` | `k`, `w0`, `bandwidth` (the −3 dB width) |
| `Notch` | second-order band-stop at `w0` | `k`, `w0`, `bandwidth`, `depth` (gain at `w0`: 0 removes it, 1 is no notch) |

The low-pass filters are built from second-order sections (plus one first-order section for an odd order). Both have the gain `k/√2` at `wc`.

## Routing

| Block | What it does |
| --- | --- |
| `Mux2`, `Mux3`, `Mux4` | combine 2, 3 or 4 scalar signals into one vector `y` |
| `Demux2`, `Demux3`, `Demux4` | split a vector of 2, 3 or 4 elements into scalar signals |
| `MultiportSwitch` | `y = u[index]`: picks one element of the vector input `u` |
| `Select` | one element of a vector of any size |

Notes:

- A vector port connects only to a vector of the same size. That is why each Mux and Demux has a fixed number of signals: pick the one you need, or chain them.
- `MultiportSwitch` rounds `index` to the nearest whole number (2.5 selects `u[3]`) and clamps it to 1..N. Feed its data input from a Mux. Each switch is an exact event.

## Nonlinearities

| Block | What it does | Key parameters |
| --- | --- | --- |
| `Backlash` | play: the output follows the input only when pushed from either end of a band of `width` | `width`, `initial`; constant `sample_period` |
| `VariableTransportDelay` | `y = u(t − d)`, the delay `d` is a second input | `initial`; constants `max_delay`, `sample_period` |
| `WrapToPi` | wraps an angle into (−π, π] | none |
| `Polynomial` | `p[1]·u^(N−1) + … + p[N]` | `p` (descending powers) |
| `Rounding` | floor, ceil, round (halves away from zero) or fix (towards zero) | `mode` |

Notes:

- `Backlash` updates its held position every `sample_period`. In between, the output follows the input exactly while it is pushed. A shorter `sample_period` follows a quick reversal more closely.
- `VariableTransportDelay` stores the input every `sample_period`. The delay is clamped to `[sample_period, max_delay]`, and a change of the delay takes effect over one sample period. Until the delay line has filled, the output is `initial`.

## Simulation control

| Block | What it does | Key parameters |
| --- | --- | --- |
| `StopSimulation` | ends the run when its input rises above `threshold` | `threshold` (default 0.5) |
| `Assertion` | fails the run when its input falls below `threshold` | `threshold` (default 0.5) |
| `HitCrossing` | flags the moment the input crosses `level` | `level`, `direction` (either, rising, falling) |

- `StopSimulation` stops the run at the exact moment of the crossing. The run ends normally, and a W217 warning in the [Diagnostics](page:diagnostics) panel names the block and the time.
- `Assertion` checks a condition that must hold during the whole run, for example the output of a `Compare` block. When it no longer holds, the run stops with an E902 error. The message names the block, so give the block a name that says what it checks, such as `PressureOk`.
- `HitCrossing` has two outputs: `y` is 0 until the first crossing and 1 from then on, and `n` counts the crossings. The crossing is located exactly. The block assumes that the input starts below `level`. If it starts above, set the start value of its variable `side` to 1; otherwise the first falling crossing is not counted.
- In an exported FMU, both blocks are checked after every step, so a stop can come up to one step late. After a `StopSimulation`, `fmi2DoStep` returns `fmi2Discard` and the FMU reports that it has terminated. After a failed `Assertion`, it logs the block and returns `fmi2Error`.

## Observers and discrete blocks

| Block | What it does | Key parameters |
| --- | --- | --- |
| `Luenberger` | estimates the state of `x' = A·x + B·u`, `y = C·x + D·u` from `u` and the measured `y` | `A`, `B`, `C`, `D`, observer gain `L` |
| `KalmanFilter` | discrete Kalman filter for `x[k+1] = A·x + B·u + w`, `y = C·x + D·u + v` | `A`, `B`, `C`, `D`, `Q` (process noise), `R` (measurement noise); constant `sample_period` |
| `Memory` | the input value of the previous tick | `initial`; constant `sample_period` |
| `DiscreteDerivative` | `gain·(u[k] − u[k−1]) / Ts` | `gain`, `initial`; constant `sample_period` |

Notes:

- Choose the `Luenberger` gain `L` so that the eigenvalues of `A − L·C` are faster than the plant. The default places them at −5 and −6.
- `KalmanFilter` updates its covariance at every tick, so its gain converges to the steady-state Kalman gain. Set the start value of the variable `P` to the initial uncertainty of the state.
- `Memory` gives the same values as `UnitDelay`, but it reads `previous(u)`. You can therefore use it to break a loop between discrete blocks (error E105).

## Gain scheduling

A gain that depends on the operating point is a lookup table whose output feeds a gain input of the control law. Use `Lookup1D` for one scheduling variable and `Lookup2D` for two:

- `Lookup2D` takes a square grid: `breaks` holds the x breakpoints in row 1 and the y breakpoints in row 2, and `table[i, j]` is the value at `x = breaks[1, j]`, `y = breaks[2, i]`. Between breakpoints it interpolates bilinearly. Outside the grid it holds the edge values.
- Write the control law so that it takes the gains as inputs and integrates `Ki·e` rather than multiplying `Ki` by the integral of `e`. Then a gain that changes with the flight condition does not make the output jump.

The **f16** example (in the Example gallery) schedules a pitch-rate law over dynamic pressure and Mach with three `Lookup2D` tables. It also shows a rate-limited actuator built from `Saturation`, `Gain` and `Integrator` blocks, a pilot model with a `TransportDelay`, and a phase-compensated rate limiter that removes a pilot-induced oscillation.

Its model **f16-sim** is a full three-axis fly-by-wire on the same airframe. Five more `Lookup2D` tables over dynamic pressure and Mach hold the roll and yaw gains, and a `Lookup1D` over alpha holds the aileron-rudder interconnect:

- Pitch: the stick commands a load factor. A turn compensation holds the altitude in a bank, and the alpha and g limiter stays in the loop.
- Roll: the stick commands a roll rate about the velocity vector. The rate limit falls with the load factor and at low dynamic pressure.
- Yaw: a yaw damper on the washed-out yaw rate, and the pedals command a sideslip.
- On the ground: a weight-on-wheels signal fades the three laws to direct commands, and a `Lookup1D` over the ground speed limits the nose-wheel steering. The landing gear is the Cessna's, with a retraction added.

The model's inputs and outputs are export markers, and its trim, CG, mass and law switches are globals. It exports as the FMU of a flight-simulator host (`apps/f16-sim`). The dashboard has sliders for the sticks, the pedals, the throttle and the law switches, and cards for the wheel loads and the gear position.

The **beaver** example (the DHC-2 Beaver of the TU Delft FDC toolbox) schedules its gains differently: the autopilot's gains are polynomials in the airspeed, written inside the control-law blocks. Its model **beaver-sim** flies that autopilot:

- Pitch: a pitch attitude hold, with an altitude hold as its outer loop.
- Roll: a roll attitude hold, with a heading hold as its outer loop, and a turn coordinator on the rudder.
- A mode input selects each loop: 0 off, 1 the attitude hold, 2 the outer loop. A loop that is off bleeds its integrator to zero, so engaging it later does not make the surface jump.
- A first-order servo with an airspeed-dependent gain drives each surface.

The default run is a climb, a turn to a heading and a level-off.
