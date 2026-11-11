# The swinging plate: what the linear model leaves out

**Scenario.** An `MSf` drives the plate through a stiff lock spring
([Shaker](block:Shaker), [ShakerRate](block:ShakerRate)), so the plate angle swings as
α = −2° cos(2π · 2 Hz · t). The ball starts at rest **0.10 m** from the axis.

**The two answers.** The signal chain [LinX](block:LinX) integrates the textbook model
x'' = 5/7 g sin α of the same plate angle. Its mean is zero, so in that model the ball just jiggles
around 0.10 m. The bond graph contains the plate's rotation, and the ball drifts outwards by
**59 mm in 4 s** ([Drift/y](signal:Drift/y)). This is the centrifugal term x α̇² of the full
equation

ẍ = 5/7 (g sin α + x α̇² − (h + 2r/5) α̈),

which `design/design.py` integrates for the ball centre h = 15.7 mm above the axis. The drift
agrees with that equation to **0.1 %** at 1, 2, 3 and 4 s. The plate's angular acceleration also
modulates the normal force by ±0.05 N ([Contact/f_n](signal:Contact/f_n)).

![Plate angle, both positions and the normal force|900](assets/01fcdc811718.png)

The rig: [the ball-and-plate rig](project:rig).
