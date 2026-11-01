# Notes and limitations

- **Arm.** The geometry is that of the LR Mate 200iD/7L, with the limits of the LR-10iA/10. Its acceleration and jerk limits are assumed (see Robot and trajectories). The arm is kinematic: the flange follows the plan exactly. A real controller adds servo lag and path deviation in blends that are not modelled here.
- **Cups and air.** The cups are lumped `SuctionCup` elements. There are no hose dynamics: the ejector acts directly on the cup chamber. The cylinders have no air dynamics either: the valve sets the force at once and the meter-out damper sets the speed.
- **Reduced model.** It holds the rods rigid, while bg-sim keeps them compliant (about 145 Hz laterally). The margins agree within a few hundredths (see Validation and checks).
- **Solver.** The models use `Rodas5P`. With FBDF the run stops when the cup lips land: the lip gap then falls through the `h_lost` level of the cup's `lost` latch, and FBDF forces its step below machine precision.
- **Contents.** The loose ball and bottle are rigid bodies with Hunt–Crossley wall contacts and regularised Coulomb friction. They have no rolling resistance, so the ball keeps rolling.
- **Regenerating.** See the README: `build_library.py`, `build_scene.py`, `optimize.py` (about 25 min on 20 cores), `build_models.py`, `reference.py` and `build_expected.py`.
