# Van der Pol in mechanics: a block on a moving belt

A block on a spring rides a belt that runs at a constant speed $v_b$. Friction drags the block along until the spring holds it at $x_s = F_0/k$. With a friction force that **falls** as the slip velocity rises (the Stribeck effect), this equilibrium is unstable. When the block moves with the belt the slip drops and the friction rises, so the belt pushes harder. When it moves back, the friction falls. The contact acts as a negative damper and the block starts to oscillate. Squealing brakes, chattering machine slides and the bowed violin string work the same way.

![The model canvas|900](assets/b1f1266d4bdc.png)

The model has the same rig twice:

- the root diagram: the friction curve replaced by its third-order Taylor fit about the belt speed (block `BeltFriction` in [Fric](block:Fric)). This rig obeys Rayleigh's equation exactly, and its velocity obeys Van der Pol.
- [Stribeck](block:Stribeck): the full curve (block `StribeckFriction`), to show what the fit leaves out.
- [Ref](block:Ref): the textbook equation in the rig's seconds, and [RefV](block:RefV) $= V x$ in m/s.

Inside each rig: the belt is a flow source Sf on a 0-junction, whose effort is the friction force $F$. The slip $w = v_b - \dot x$ goes to the friction contact Fric, a nonlinear R in resistance causality (`@causality p => :effort_out`). The rest of the belt's flow is the block's 1-junction: mass, spring, a velocity detector and a position sensor.

## What to try

1. Plot [Vel/y](signal:Vel/y) and [RefV/y](signal:RefV/y): the same curve.
2. Plot [Fric/w](signal:Fric/w): the slip swings between 26.6 and 114.8 mm/s and never reaches 0, so the block never sticks.
3. Open the 3D view: the block (coloured by the slip) shakes by ±4.5 mm on the running belt, and the spring's rings follow.
4. Set the global `mu` to 2. The viscous coefficient $\sigma$ drops and the velocity swing exceeds the belt speed. The cubic fit then has no physical meaning: the real block would stick and slip.

Continue with [the physics and the scaling](page:physics) and [the results](page:results).

## 3D view

`scenes/vdp-belt.sdf` is the rig: a belt over two pulleys, a wall, the spring as eight rings and the block. The prismatic joint `block` follows [Pos/y](signal:Pos/y). The rings follow the same signal with gains $k/9$, and the belt's stripes move with the belt phase [BeltPhase/y](signal:BeltPhase/y), a sawtooth over one stripe pitch. The stripes tile the belt, so when the phase wraps only the end stripes change, under the guard hoods over the pulleys. Picture at 30 s:

![3D view at t = 30 s|500](assets/be5a8a1d4ffd.png)
