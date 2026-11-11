# Sign changes (O18)

What may change sign in recorded results, per block whose convention changed, and per model that the
migration touched. Only port variables (`<path>/<port>.e`, `.f`, and a signal that is a port variable or the
integral of one) are allowed here. Golden files and `expected.json` entries are updated only for signals on this
list, by negation. A signal that changes sign and is not a port variable is listed as a deviation, with the reason.

## WP-O2: scalar and domain libraries

### Blocks

| block | change | what changes sign in a model |
| --- | --- | --- |
| `bondgraph/Sf` | law: `p.f ~ -f` (O15: at the tail of its bond the source delivers `+f`) | A migrated model keeps every signal, except: where the bond was at the head of a 1-junction and is reversed (the reversal cancels the law change, the value is kept), `<Sf>/p.e` and `<Sf>/p.f`. Where the value is negated instead (a conforming bond, a 0-junction, an element-to-element chain), nothing changes sign. |
| `bondgraph/MSf` | law: `p.f ~ -gain * u` | As `Sf`, with `gain` in place of `f`. |
| `bondgraph/Se`, `MSe` | declared `out`, law unchanged | Where a bond at the head of a 1-junction is reversed and the value negated: `<Se>/p.e`, `<Se>/p.f`. |
| `bondgraph/C`, `I`, `R` (and the other `in` one-ports) | declared `in`, law unchanged | Where a bond at the tail of a 1-junction is reversed and the junction keeps its sign: `<X>/p.e`, `<X>/p.f`, and the element's own integral of its port flow or effort (`C/q`, `I/P`). On a 0-junction or between two elements: nothing. |
| `TF`, `MTF`, `GY`, `MGY`, `PowerSensor` | `(p1, p2) => :through` (`(a, b)` for the sensor) | A reversed bond on a 0-junction or between two elements: nothing. `PowerSensor/y` (the power) never changes sign. |
| one-terminal sensors, `Volume`, `Accumulator`, `Brake`, `HeatCapacitor`, `TemperatureSensor`, `RS` | declared `in` (`RS.heat` `out`), law unchanged | Nothing: every existing bond already conformed. |

### Models

| model(s) | how | signals that change sign |
| --- | --- | --- |
| `quarter-car` | tool: `MSeGs`, `MSeGu` reversed, gains negated | `MSeGs/p.e`, `MSeGs/p.f`, `MSeGu/p.e`, `MSeGu/p.f` |
| `inverted-pendulum-cart` | tool: `IMx` reversed (0-junction, neutral); `MTFv.p2` reversed, the `VJ` junction renamed, `MSeG` gain negated | `IMv/p.e`, `IMv/p.f`, `IMv/P`, `MSeG/p.e`, `MSeG/p.f` |
| `planar-links`, `planar-links-payload` | tool: `MSf` gains negated (O15, element-to-element chain into a `TorqueSensor`) | none |
| `industrial-servo` (5 models) | tool: `IqSrc` gain negated (O15); two-mass and full: `Kc`, `Dc` reversed. By hand (review): `Bemf` reversed and its gain negated, `QJ -> MGY.p2` reversed and the MGY modulus `WeL.k` negated | `Bemf/p.e`, `Bemf/p.f`, `MGY/p2.e`, `MGY/p2.f`; two-mass and full: `Kc/p.e`, `Kc/p.f`, `Kc/q` (binding `joint:coupling_joint` gain negated), `Dc/p.e`, `Dc/p.f`. **Deviation:** `WeL/y` and `MGY/u` (the gyrator modulus `w_e L_q`, not a port variable): reversing one bond of a gyrator negates its modulus, and there is no other place for that sign. Referenced by no check, plot or binding. |
| `f16-sim` | build script: `Retract_*` reversed (0-junction), gains `-1` (O15) | none |
| `vdp-belt` | build script: `Belt` `f = v_b` (was `-v_b`, O15) | none |
| `ball-and-plate-swing` | build script: `Shaker` (MSf) driven by `ShakerRate` with amplitude `+A W` (was `-A W`, O15) | **Deviation:** `ShakerRate/y` (a Sine source output, not a port variable) changes sign; the MSf delivers the same flow. Referenced by no check, plot or binding. |
| `wind-turbine` (5 models) | build script: `Generator` reversed, gain `-1` | `Generator/p.e`, `Generator/p.f` |
| `hybrid-powersplit` (3 models) | build script: `EngineDrag`, `SpinLoss`, `Rolling` reversed, gains negated | `EngineDrag/p.e`, `EngineDrag/p.f`, `SpinLoss/p.e`, `SpinLoss/p.f`, `Rolling/p.e`, `Rolling/p.f` |
| `maglev-train` (3 models) | build script: `Weight`, `BodyWeight` (Se) and `Load` (MSe) reversed, values negated; `Rail` (MSf) reversed, value kept (O15 cancels) | `Weight/p.e`, `Weight/p.f`, `BodyWeight/p.e`, `BodyWeight/p.f`, `Load/p.e`, `Load/p.f`, `Rail/p.e`, `Rail/p.f` (vehicle: under `ModF/`, `ModR/`) |
| `cars` (9 models) | build script: the limited-slip damper bonds now arrive at the corner's `LsdTF` (element-to-element, notation only) | none |

No `expected.json` entry, golden file, plot or dashboard card of these examples names a signal on this list, so
none was edited.

### Julia tests and fixtures

| file | change | signals that change sign |
| --- | --- | --- |
| `test/fixtures/causality/two_c_series.json` | tool: both `C -> J0` bonds reversed (0-junction, neutral) | none; the stroke ends swap (`from`/`to`) with the bonds |
| `test/fixtures/causality/r_r_loop.json` | the `R -> R` bond (O4) replaced by a 1-junction with a bond to each R | none checked |
| `golden/bondgraph/test_MSf.jl` | the `gain = -1` workaround removed (`gain = 1`) | none: `MSf1/p.f = -u` as before |
| `golden/bondgraph/test_MGY.jl`, `test_MTF.jl`, `golden/converters/test_PowerSensor.jl` (model 1), `golden/rotation/test_GearBacklash.jl`, `test_GearWithBacklash.jl`, `test_components.jl` (four rigs), `test_simulate.jl` (start-survives rig) | the driving `Sf` value negated | none |
| `golden/contact/test_RollingSphere.jl`, `tyre_rig.jl` | the `-W` / `-w_rel` workaround removed | none |
| `test_multibond_slice.jl` (ScrewTF rig) | `T.b -> Sf` reversed (`Sf` is `out`), value negated | none |
| `test_export_scope.jl` (flipped bond) | stdlib `R` behind the reversed subsystem port is E114 now (asserted); the flipped case runs on an inline `R` without orientation | none: the flow is 1.5 as before |
| `golden/converters/test_PowerSensor.jl` (model 2) | the reversed placement `R -> sensor -> junction` is E114 now; asserted as a refusal | the -12 W reading is gone with the placement |
