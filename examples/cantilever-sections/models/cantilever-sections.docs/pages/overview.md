# Three sections, one tip force

Three 2 m steel cantilevers of the **same mass per metre** (7.774 kg/m) are clamped to one wall: a solid round bar, a solid square bar and an **IPE 100** I-beam on its strong axis. One downward tip force loads all three. The shape alone decides how far each bends, how hard it is stressed and how fast it vibrates.

![The three beams at the first peak after the 250 N step (deflection drawn x10, colour: bending stress, grey 0, dark red at yield)|900](assets/d53c0cb458a7.png)

![Diagram: the load, three effort sources and the three beams|900](assets/f1215ac08b97.png)

[Load](block:Load) makes the tip force (positive down). Three effort sources [FRound](block:FRound), [FSquare](block:FSquare) and [FIPE](block:FIPE) apply it to the tip ports of [Round](block:Round), [Square](block:Square) and [IPE](block:IPE). Each beam is a `ModalCantilever`: three clamped-free assumed modes (see [the physics](page:physics)), its section given by global parameters.

## What it shows

- **Same mass, 21 times stiffer.** Under 250 N the bars deflect 40.7 and 38.8 mm, the I-beam 1.94 mm ([Round/w_mm](signal:Round/w_mm), [IPE/w_mm](signal:IPE/w_mm)). The I-beam puts its material far from the neutral axis: I = 163.3 cm⁴ against 7.8 cm⁴.
- **Stress.** The root moment is F L = 500 N m for all three; the stress M / W is 114, 96 and 15 MPa, a utilisation of 0.48, 0.41 and 0.065 ([Round/util](signal:Round/util)).
- **A sudden load more than doubles the stress.** The step swings the tips to 1.9 times their static deflection and the root moment to 2.21 F L: the round bar passes its yield stress for a moment ([Round/util](signal:Round/util) 1.07; the model stays elastic). A ramp of 1 s avoids it.
- **Resonance.** The bars' first modes are at 6.42 and 6.57 Hz, the I-beam's at 29.4 Hz. A 10 N sine at 6.42 Hz shakes the round bar to 39.5 mm and 130 MPa, more than the 250 N static load does.

## Try it

Open the **Dashboard** tab. Pick the **load** (constant, sine, constant + sine, sweep), set its force, ramp time, amplitude and frequency, press **Run**, and watch the **3D View**:

- a ramp time of 1 s: the overshoot of the step is gone;
- **sine** at 6.42 Hz, then 6.57 Hz (the square bar's f1), then 29.4 Hz with 100 N (the I-beam's);
- **sweep** (2 to 40 Hz in 10 s): each beam rings as the sweep passes its first mode;
- the own weight (g0 = 9.81) adds 9.3 mm to the bars' sag and 0.44 mm to the I-beam's.

The 3D view draws the deflection **x10, marked exaggerated**; pick x1 in its Deformation control for true scale. The colours always come from the true strain.
