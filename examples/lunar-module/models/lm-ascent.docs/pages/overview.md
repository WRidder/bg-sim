# Ascent to orbit

At 124:22:00 GET the ascent engine fired and the ascent stage left the descent stage on the surface. The model flies TN D-6846's ascent:

* a **vertical rise** until the radial rate reaches 40 ft/s (about 10 s), to clear the descent stage and the terrain;
* the **insertion phase** on Apollo's linear guidance: a radial acceleration that meets 60,000 ft and 32.2 ft/s radial rate when the downrange velocity reaches 5,534.9 ft/s; the ascent engine is not throttleable, so whatever thrust is left goes downrange;
* engine cutoff on the target velocity, anticipating the 0.2 s thrust tail-off.

![The model canvas|900](assets/ebe7d482b072.png)

| block | role |
| --- | --- |
| [Tank](block:Tank), [Engine](block:Engine) | the ascent stage's propellant and mass properties; the ascent engine (3,464 lbf, 309.4 s) |
| [Guid](block:Guid), [Att](block:Att) | the ascent guidance and the RCS attitude loop |
| [Orbit](block:Orbit) | apolune and perilune of the current state |
| [State](block:State), [Status](block:Status) | altitude, velocities, tilt; velocity gained |

Set `steer` and `gravity_scale` to 0 and the thrust stays vertical in empty space: the speed is then Tsiolkovsky's $c \ln(m_0/m)$.

![3D view at lift-off: the descent stage stays behind|600](assets/20ae4fae8967.png)

Continue with [the results](page:results).
