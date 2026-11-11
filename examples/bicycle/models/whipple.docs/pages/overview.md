# The hands-off bicycle in 3D

The benchmark bicycle as a nonlinear **3D bond graph**: rear frame with rider, fork, two wheels, three hinges and two rolling tyres. Nobody holds the handlebar. The run starts like the paper's figure 4: rolling straight at **4.6 m/s** when a sideways push gives it a lean rate of **0.5 rad/s**.

![The 3D view at 2 s, in the second weave swing: the bicycle leans 0.06 rad to the right and has steered 0.06 rad into the lean|800](assets/d8651e8230ca.png)

The bicycle leans to the right, the handlebar turns to the right on its own, the wheels run back under the rider and the bicycle comes upright after one and a half swings of the **weave** oscillation. At 4.6 m/s it is inside the self-stable band (4.29 to 6.02 m/s, see [the benchmark bicycle](project:benchmark)).

![Lean and steer rate and the forward speed (compare the paper's figure 4)|900](assets/61ef50e4b09b.png)

The forward speed is not held: the bicycle coasts, and the energy of the sideways motion is traded with the forward motion (the speed rises to 4.69 m/s while the lean is largest and settles at 4.62 m/s). It stays between 4.60 and 4.70 m/s, the range of the paper's figure.

## Run it

Press **Run** (5 s, about 15 s of solving). The **3D View** replays the run; the orange marker on each rim shows the wheels turning. Default plots: lean and steer angle ([Sense](block:Sense) `phi`, `delta`), their rates, the [forward speed](signal:Sense/v), the path, the tyre normal forces and the energy book.

The dashboard has two sliders, both **global parameters**: the forward speed `v` and the push `phid0` (the lean rate at the start). Things to try:

- **3 m/s**: below the weave speed the oscillation grows and the bicycle falls (after about 2 s with the default push; the model does not stop at the floor, so stop reading once the lean passes 1 rad).
- **5 m/s**: the weave dies out faster.
- **8 m/s** with a run of 12 s (Simulation settings): the weave dies out in a second, then the bicycle slowly capsizes, leaning and turning ever more to the right.
- **phid0 = 0**: nothing happens. The upright bicycle is an equilibrium at every speed.

Pages: [model and bond graph](page:model), [validation](page:validation).
