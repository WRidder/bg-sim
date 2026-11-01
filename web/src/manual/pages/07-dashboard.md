# Dashboard

The **Dashboard** tab is a grid of cards that show results and set inputs for the next run. It is saved with the model.

## Edit the dashboard

1. Click **Edit dashboard**.
2. Click **+ Add card** and pick a card kind.
3. Use a card's **⚙** button for its settings (title, size, signal or parameter, ranges), drag its **⠿** grip or the arrow buttons to move it, and **×** to remove it.
4. Click **Done**.

You can also drag a signal from the **Signals** tab onto the dashboard: on empty space it makes a Value card, on a display card it adds the signal.

## Card kinds

| Group | Kinds |
| --- | --- |
| Display | Plot, Value, Gauge, Bar, Indicator, Text (Markdown) |
| Input (for the next run) | Number, Slider, Knob, Toggle, Select, Schedule |

A Plot card draws its signals against time, or against another signal (an XY plot, see below). Value, Gauge and Bar cards can have colour zones. An Indicator turns on above (or below) a threshold. A Select card picks one option of an enumeration parameter (an `Int` with named options, such as the load mode of example **cantilever-sections**, or the **Controller** of the cart models of example **quad-pendulum**, which switches between a full-travel and a short-travel swing-up controller at run time, without a recompile). The options are numbered from 0, as in the block's description (`0 constant, 1 sine, ...`), and the inspector shows the same numbers. A model can make other cards follow the choice: in **quad-pendulum** the cart plot's limit lines and the **Travel used** readout are signals computed from the selected controller's limit.

## XY plot cards

A Plot card can draw its signals against another signal instead of time: a phase portrait (x' against x), a force against a deflection, a torque–speed curve.

1. In **Edit dashboard**, open the Plot card's **⚙** settings.
2. Under **X axis**, set **Plot against** to a signal. A signal of the card moves to the x axis; the others are drawn against it, sample by sample. **Time (t)** switches back.
3. Check **Equal aspect** to make one unit as long on both axes, so a circle stays round.

The card follows the same run, time window and inspect time as the Plots tab: a ring marks the point at the inspect time, and the legend shows t, x and every y there. Drag a box to zoom, double-click to fit. In the model file the card has `"x": "<signal id>"` and `"equalAspect": true`, like a saved plot. Example **van-der-pol** (`vdp-tunnel-diode`) shows the phase portrait and the diode's current against its voltage.

## Inputs

An input card binds one block parameter and **overrides it for the next run**. The model itself does not change.

- The card footer shows the model value; **Use model value** removes the override.
- A block parameter whose value is an expression of [global parameters](page:parameters) (`final = h_step`) starts at the value the globals give it, and the footer says which globals drive it. The card overrides that one block parameter only. When the value is just a global's name, **Bind to global** moves the card to the global itself, so it changes every parameter that uses that global.
- The inspector marks an overridden parameter with a `dashboard:` tag.
- "applies at the next run" in the footer means the card's value differs from what the current run was started with. It clears when you press **Run**.
- The toolbar summarises what the next run uses, for example "Next run: 1 parameter override".
- If an input has a problem, the next run is refused until you fix it.

## Schedule table

A **Schedule** card changes parameters at given times during the run.

- The first column is the time `t [s]`. Add parameter columns with **+ Column…** and rows with **+ Row**.
- From each row's time on, the parameters take that row's values (step changes). Before the first row, the model values apply.

## Auto re-run

With **Auto re-run** checked, BG-Sim starts a new run once you have stopped changing inputs for 0.25 s and let go of the slider or knob you were dragging. It works only while the Dashboard tab is open, waits for an active run to finish, and does not run while an input has a problem.
