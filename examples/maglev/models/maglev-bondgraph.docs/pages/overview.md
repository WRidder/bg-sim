# Maglev as a bond graph

The current-driven model (`maglev-current-driven`) assumes an ideal current source. Here the coil is a real circuit: a voltage amplifier with a ±60 V rail, the coil resistance, and an inductance that changes with the gap. The magnet itself is the stdlib block `converters/Electromagnet`, a two-port field that stores magnetic energy and is the only link between the circuit and the ball. The position comes from an IR sensor with noise and a 16-bit ADC at 1 kHz, and a cascade controller closes the loop.

![The model canvas|900](assets/d4880814dfea.png)

| block | role |
| --- | --- |
| [Amp](block:Amp), [Sat](block:Sat) | modulated effort source: the amplifier voltage, clipped at ±60 V |
| [Jc](block:Jc), [Rc](block:Rc), [Imeas](block:Imeas) | electrical 1-junction (one current), coil resistance 2 Ω, flow detector for the current |
| [Jv](block:Jv), [Vcoil](block:Vcoil) | 0-junction at the field's coil port and its effort detector (the field voltage) |
| [EM](block:EM) | the electromagnet: an IC-field between the coil and the gap ([physics](page:physics)) |
| [Jb](block:Jb), [Ball](block:Ball), [Grav](block:Grav) | mechanical 1-junction (ball velocity, down positive), the 20 g mass, gravity |
| [Jf](block:Jf), [Fmag](block:Fmag), [Vball](block:Vball) | 0-junction at the field's gap port, force and velocity detectors |
| [BallPos](block:BallPos), [IR](block:IR) | gap, and the IR sensor subsystem (gain, noise, ADC) |
| [Pel](block:Pel), [Pmech](block:Pmech), [Eel](block:Eel), [Emech](block:Emech) | port powers of the field and their integrals |
| [Ref](block:Ref), [Pre](block:Pre), [Trim](block:Trim), [PID](block:PID), [Ipi](block:Ipi) | outer scheduled PID → current setpoint, inner PI → voltage ([controller](page:control)) |

## What to try

1. Open the **Dashboard** tab and move the setpoint slider: the model runs again, and the gauges show the gap and the coil current.
2. Plot [EM/W](signal:EM/W), [Eel/y](signal:Eel/y) and [Emech/y](signal:Emech/y): the stored energy is exactly what flowed in through the two ports.
3. Plot [Sat/y](signal:Sat/y): the noise keeps the amplifier busy (about 2 V rms), and the step drives it into the +60 V rail.
4. Set the `std` of `IR/Noise` to 0: the loop becomes quiet and matches the scipy design.

## 3D view

The same tabletop rig as the current-driven model. The gap follows [BallPos/y](signal:BallPos/y), the setpoint disc [Ref/y](signal:Ref/y) and the winding colour the field current [EM/i](signal:EM/i). Picture at 0.3 s:

![3D view at t = 0.3 s|500](assets/14d728b4e46b.png)
