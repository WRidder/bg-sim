# Motion profiles and drive electronics

These blocks are in the **Motion and drive electronics** category of the library. The profiles generate setpoints for a point-to-point move; the drive electronics sit between a controller and a motor. Select a block and press `F1`, or click its help button in the library, for the full parameter list.

## Motion profiles

Every profile moves from `q_start` to `q_end`, starting at `t_start`, and is at rest at both ends. Before `t_start` the position output is `q_start`; once the move has ended it is exactly `q_end`. A move with `q_end < q_start` runs backwards. Positions have no unit, so the same profile drives a slide in m or a joint in rad; velocities are in position units per second.

| Block | Outputs | Key parameters | Acceleration |
| --- | --- | --- | --- |
| `TrapezoidalProfile` | `q`, `v`, `a` | `v_max`, `a_max` | jumps (±`a_max`, 0) |
| `SCurveProfile` | `q`, `v`, `a`, `jerk` | `v_max`, `a_max`, `j_max` | continuous; the jerk is ±`j_max` or 0 |
| `CycloidalProfile` | `q`, `v`, `a`, `jerk` | `duration` | continuous, zero at both ends |
| `PolynomialProfile` | `q`, `v`, `a`, `jerk` | `duration` | continuous (3-4-5 quintic polynomial) |
| `HarmonicProfile` | `q`, `v`, `a` | `duration` | jumps at both ends |

Notes:

- `TrapezoidalProfile` accelerates with `a_max` up to `v_max`, cruises, and brakes with `a_max`. When the move is too short to reach `v_max`, the velocity is a triangle and the peak speed is `√(a_max·|q_end − q_start|)`.
- `SCurveProfile` is the jerk-limited seven-segment profile. It reaches `a_max` and `v_max` when the distance allows; a shorter move skips the cruise and lowers the peaks, so the move still ends exactly at `q_end`.
- The duration-based profiles (`CycloidalProfile`, `PolynomialProfile`, `HarmonicProfile`) end at `t_start + duration`. The peak velocity is `2h/duration` (cycloidal), `1.875h/duration` (quintic) and `πh/(2·duration)` (harmonic), with `h = q_end − q_start`.
- Every segment switch is an exact event, so a switch on an output time never stops the run with W206.
- To drive a mechanism, feed `q` (or `v`) to a position or velocity controller, or `v` straight into a `VelocitySource` / `SpeedSource`.

## Drive electronics

| Block | What it does | Key parameters |
| --- | --- | --- |
| `PWM` | switched output: `high` for the duty fraction of every carrier period, then `low` | `frequency` (Hz), `high`, `low`, `t_start`; input `u` = duty 0..1 |
| `PWMAverage` | the mean of the PWM output over a period, `low + (high − low)·duty` | `high`, `low` |
| `PowerAmplifier` | a voltage source for a motor: `gain·u`, clamped to ±`V_max`, minus `R_out·i`, with an optional current limit | `gain`, `V_max`, `R_out`, `I_max`, `R_limit` |
| `HBridge` | averaged H-bridge between a DC bus (`dc_p`, `dc_n`) and a load (`out_p`, `out_n`): `v_out = duty·v_bus`, `i_bus = duty·i` | `R_on`, `I_max`, `R_limit`; input `duty` −1..1 |
| `Encoder` | the shaft angle as whole counts, the quantized angle and the index pulse | `cpr` (counts per revolution), `sample_period` |
| `ADC` | samples, clips and quantizes a signal; outputs the level and the integer code | `bits`, `u_min`, `u_max`, `sample_period` |
| `DAC` | quantizes a value (or takes a code) and holds it until the next sample | `bits`, `y_min`, `y_max`, `input` (value or code), `sample_period` |

Notes:

- **Switched or averaged.** Every PWM edge is an event of the solver, and each event counts towards the run's event limit (W206). A 20 kHz carrier over one second is 40 000 edges, so model a fast drive with `PWMAverage` (or feed the duty straight into `HBridge`), and use `PWM` to look at the ripple of a short run or a slow carrier. For a bipolar switched H-bridge, set the PWM's `low = −1` and `high = 1` and wire it to the bridge's `duty`.
- **Current limit.** In `PowerAmplifier` and `HBridge`, above `I_max` the output voltage drops by `R_limit` volts per ampere of excess current. The limit is steep but finite, so the stage stays a voltage source for a motor winding. The default `I_max = 1e12` A means no limit.
- **Supply limit.** The amplifier clamps its command to ±`V_max`. The H-bridge cannot exceed its bus voltage, and it draws the load power from the bus (`i_dc` output), so a battery or a supply model on the bus side sees the drive.
- **Encoder.** `counts = floor(angle·cpr/2π)`, so angle 0 is count 0 and negative angles give negative counts. `cpr` is the count after decoding, four times the line count of a quadrature encoder. `index` is true during the first count of each revolution.
- **ADC and DAC.** The `2^bits` levels run from the lower to the upper end of the range, both included. Values round half away from zero and clip at the range. Wire an ADC's `code` to a DAC with `input = 1` for a code round trip.
- `Encoder`, `ADC` and `DAC` sample on their own clock (`sample_period`, set in the block's code, 1 ms by default) and hold their outputs in between, like the blocks in **Discrete and logic** (see [Signal sources](page:signal-sources) for `ZOH` and the delays).
- All these blocks export to C and FMU (see [Export](page:export)). The exported code evaluates every switch at the step instants instead of locating it, so a PWM edge or a profile switch inside a step shows up at the next step.
