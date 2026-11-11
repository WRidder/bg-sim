# Landing by hand

The landing phase (P66, "rate of descent") was flown by hand: each click of the commander's switch changed the descent rate by 1 ft/s, and the hand controller tilted the LM to move it. This model starts in a hover with the usable propellant Eagle had at P66 entry (about 960 kg, from the descent model) and lets you fly it from the dashboard:

* the **descent rate** above 100 ft, and the rate at touchdown (the command ramps between them below 100 ft);
* a **forward translation** at a set speed for a set time, then the forward speed is nulled;
* the **hover time left**: how long the usable propellant would hold the LM in a hover.

The guidance is the descent model's P66 loop: the throttle holds the commanded descent rate, and the attitude tilts the thrust to reach the commanded forward speed. The engine stops at touchdown or when the usable propellant is gone.

![The model canvas|900](assets/d43abd91e45b.png)

| block | role |
| --- | --- |
| [RateCmd](block:RateCmd), [FwdCmd](block:FwdCmd) | the pilot's commands from the dashboard |
| [Guid](block:Guid), [Throttle](block:Throttle), [Att](block:Att) | the P66 loops, the engine and the RCS |
| [Pad1](block:Pad1)..[Pad4](block:Pad4) | the footpads |
| [Status](block:Status) | hover time left, thrust-to-weight ratio |

![3D view after the landing|600](assets/94c1bf2ce5fe.png)

Continue with [the results](page:results).
