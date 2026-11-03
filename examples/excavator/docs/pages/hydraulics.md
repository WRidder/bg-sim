# Hydraulics

![The load-sensing circuit|860](assets/512bc2471476.svg)

**Pump.** `LoadSensingPump` (stdlib, `converters`) is a variable-displacement pump of 220 cm³/rev at a constant
1800 rpm (396 l/min at full stroke). Its static regulator sets the displacement so that the outlet stays
`dp_ls` = 25 bar above the LS port (linear over a 2 bar regulation range), with a pressure cut-off at 320 bar and
a torque limiter at 530 N·m (100 kW of ideal pump power at 1800 rpm; the shaft power adds the friction loss
and peaks at 116 kW in the dig cycle). Volumetric and mechanical efficiencies 0.95 / 0.92. The
form follows the pressure-compensated pump of Simscape Fluids, with the LS pressure added to the set point.

**Sections.** Each of the three valve sections is a pre-compensator (`PressureCompensatedFlowControl`, 10 bar
across the spool) in front of a 4/3 spool (`DirectionalValve43`), whose opening follows the joystick through a
first-order spool lag (80 ms). The flow therefore depends on the joystick and not on the load: the boom passes
300 l/min at full stick, the arm 280, the bucket 200. A small **LS edge** on each spool (a second `DirectionalValve43`)
connects the LS gallery to the pressurised cylinder port. **Shuttle network:** a `CheckValve` from each gallery
to the common LS line picks the highest load pressure; a bleed orifice drains the line to tank when the sections
close. Make-up check valves on every cylinder port prevent cavitation.

**Volumes.** Every valve sits between two volumes (pump line, the volume between compensator and spool, the
cylinder chambers, the LS line), so the hydraulic connection sets have no algebraic loops.

**Relief.** A main `PressureReliefValve` at 343 bar. The LS pump never needs it: the cut-off destrokes the pump
first.

**No load sensing.** [excavator-no-ls](model:excavator-no-ls) ties the pump's LS port to the tank and sets the
margin to 280 bar, so the pump holds a constant 281 bar, and the sections throttle the difference to the load.
