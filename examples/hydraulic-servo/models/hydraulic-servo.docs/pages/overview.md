# Hydraulic position servo

A valve-controlled hydraulic servo (plan 9.6, milestone M2). A 100 bar supply and a 1 bar tank feed a 4/3 spool valve built from four variable orifices; the valve drives a single-rod [cylinder](block:Cyl) that moves a 50 kg mass with 500 N·s/m of damping. A 1 ms discrete [PID](block:PID1) turns the position error into the spool command. Everything except the position sensor and the sampled controller is a hydraulic/translation **bond graph** (D28).

![The model canvas|900](assets/e58355d76c0b.png)

Blocks of the loop:

| block | role |
| --- | --- |
| [PS](block:PS), [TK](block:TK) | pressure source (100 bar) and tank (1 bar); `One` drives the source input with a constant 1 |
| [Valve](block:Valve) | subsystem with four orifices in a Wheatstone bridge, ports P, T, A, B and one spool input |
| [Cyl](block:Cyl) | hydraulic cylinder, ports A, B and the rod |
| [Jrod](block:Jrod), [IM](block:IM), [RD](block:RD), [XS](block:XS) | translation 1-junction with the 50 kg mass, the 500 N·s/m damper and the position sensor |
| [XRef](block:XRef), [Err](block:Err), [PID1](block:PID1) | reference step, error node, discrete controller |
| [PSensA](block:PSensA), [PSensB](block:PSensB), [pAmin](block:pAmin), [pBmin](block:pBmin) | pressure taps and monitors of the checks |

## What to try

1. Press **Run** and plot [XS/y](signal:XS/y) together with [XRef/y](signal:XRef/y): the rod follows the 0.1 m step at 0.1 s.
2. Plot [Cyl/pA](signal:Cyl/pA) and [Cyl/pB](signal:Cyl/pB): the cap pressure dips to about 6 bar during the move and returns to the 33.7/67.3 bar trim.
3. Plot [PID1/y](signal:PID1/y): the spool is at -4.3e-5 before the step, saturates at +1 until about 0.166 s and then closes to the trim.
4. Raise `Kp` (for example to 25): the step saturates longer and the rod overshoots; lower it to 8 and the approach gets slower.
5. Set both cylinder start pressures back to 1e5 Pa and watch the W206 chatter described under [limitations](page:notes).

## 3D view

`scenes/hydraulic-servo.sdf` draws the translucent cylinder barrel, the piston with rod and the 50 kg load. The prismatic joint `stroke` follows [XS/y](signal:XS/y); the red tick marks the target position of the load. The picture is taken at 0.5 s, when the rod is at 0.0916 m.

![3D view at t = 0.5 s|500](assets/8f0ac9d8d53c.png)

Continue with [the plant](page:plant), [the controller](page:controller) and [the results](page:results).
