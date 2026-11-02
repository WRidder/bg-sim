# Cessna 172 simulator model

The flyable Cessna 172P, standing on runway 36 with the engine at idle and flaps 10. Pressing **Run** starts a scripted take-off ([Demo](block:Demo)):

1. full power, with the nose wheel holding the centre line;
2. rotation at 45 KCAS;
3. a climb at 75 KCAS, with the flaps up at 65 ft;
4. a turn to the east at 75 s.

The same model is the FMU of the flight simulator `apps/cessna-sim`.

![The model canvas|900](assets/150aecd1f731.png)

| block | role |
| --- | --- |
| [C172](block:C172) | the aircraft (a subsystem): the airframe, three landing-gear legs, the engine and propeller, the aerodynamics, the flaps |
| [Demo](block:Demo) | the scripted pilot; in the FMU the host's pilot replaces it |
| [AP](block:AP) | the autopilot: a wing leveller or heading hold, and altitude hold, adding to the yoke |
| [Status](block:Status) | what the instruments show: KIAS, vertical speed, slip, turn rate, the on-ground flag |

## What to try

1. Press **Run** and watch the [wheel loads](signal:C172/Contact_nose/fn): the nose wheel unloads at rotation, then the mains at lift-off.
2. Use the dashboard sliders to override the pilot: the yoke, pedals, throttle, mixture, flap detent, trim and toe brakes.
3. Switch the autopilot on with its sliders: the roll mode, the heading bug, altitude hold.

## 3D view

The airfield has runway 36, a taxiway, an apron, a hangar, a tower and a windsock. The control surfaces, the flaps, the steered nose wheel and the propeller move. Picture at 30 s, climbing out at 25 ft:

![3D view at t = 30 s|600](assets/d3e02e959295.png)

Continue with [the landing gear](page:gear), [the results](page:results) and [the FMU](page:fmu).
