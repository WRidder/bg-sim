# Quadcopter with a cascaded flight controller

A 1.35 kg, 450 mm X quadcopter with a PX4-style cascaded flight controller, flown from the ground: take-off to 1 m, a 2 m x 2 m mission with a 90 degree yaw turn, a landing (X5.7). The airframe is a multibond floating body, every rotor is a motor plus propeller chain, the controller sees only sensors and a navigation filter, and the plant stands on four compliant contact legs. $z$ is up, units are SI.

| model | what it is |
| --- | --- |
| `quadcopter` (this model) | the 18 s mission, `reltol` 1e-4, `abstol` 1e-6, output every 10 ms (1801 points) |
| `quadcopter-repeat` | the same document stopped at 9 s on the same output grid: the determinism twin |

The model document and the 3D scene are **generated**: `uv run examples/quadcopter/design/build_model.py` writes `models/*.bgmodel.json` and `scenes/quadcopter.sdf` from the numbers of `design/design.py`; `uv run examples/quadcopter/design/design.py` prints the derivation of the gains and the loop margins.

![The model canvas|900](assets/b49a35a99f18.png)

## Run it

Press **Run**. The README measured 41 to 65 s of solve time on a loaded machine (51 800 solver steps, compile 1 to 3 s); every 2 ms discrete tick is recorded as a left/right event pair, so the run holds about 18 000 rows of 1559 signals (about 225 MB of data). Plot the mission ([Truth/x](signal:Truth/x), [Truth/y](signal:Truth/y), [Truth/z](signal:Truth/z) with [Mission/p_sp[1]](signal:Mission/p_sp[1])), the rotor speeds ([Rotor1/Drive/rotor/w](signal:Rotor1/Drive/rotor/w)), the battery ([Bat/V](signal:Bat/V), [Bat/I](signal:Bat/I)) and the estimator errors ([Err/pos](signal:Err/pos), [Err/att](signal:Err/att), [Err/vel](signal:Err/vel)).

## 3D view

`scenes/quadcopter.sdf` has the link `body` (pose binding `Truth/q[1..4]`, `Truth/x`, `y`, `z`), the joints `rotor_1..4` (position bindings `Rotor<k>/Drive/rotor/phi`, gain -1 for the clockwise rotors 3 and 4) and the ground link with the pads. Three moments of the mission: the climb, the first turn and the final descent.

![Climb: t = 3 s|420](assets/e91171ee4dc2.png)

![Yaw turn: t = 9.5 s|420](assets/d0085b3471aa.png)

![Descent: t = 16.8 s|420](assets/c51991be0d05.png)

Continue with [the architecture](page:architecture), [the flight controller](page:controller), [the estimator](page:estimator), [the results](page:results) and [the notes](page:notes).
