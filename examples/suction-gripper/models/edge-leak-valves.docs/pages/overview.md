# One cup over the edge: per-cup flow valves

This is the same leaking cup 1 as in `edge-leak`, but every line has a flow-closing valve (`dp_close` = 8 kPa, 2 % bleed), like an SCR ball valve. Cup 1 sucks open air, the pressure drop over its line exceeds the closing pressure, and the valve shuts to the bleed. The manifold no longer sees the leak.

![Cup vacuum and line areas|900](assets/c8395916beb1.png)

Cup 1 stays at atmosphere and is lost. The five good cups reach [48.7 kPa](signal:Cup3/dp), slightly more than with six sealed cups because one cup less leaks into the manifold. Five cups carry the carton to the place position.

A fixed restrictor nozzle of 1 mm² per line has a similar effect (design.py): the good cups reach 40.9 kPa. The nozzle has no moving parts but slows the pick-up.
