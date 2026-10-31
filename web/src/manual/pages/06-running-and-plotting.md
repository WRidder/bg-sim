# Running and plotting

## Run a simulation

Click **Run** in the top bar, or press `Ctrl+Enter`. **Stop** ends a run early.

Next to the buttons are the run settings. They are saved with the model. Press `Enter` to apply a value and `Esc` to undo it; an invalid value is marked and not applied.

| Field | Meaning |
| --- | --- |
| **t_end** | end time in seconds |
| **solver** | `auto`, `Rodas5P`, `Rodas5`, `Rosenbrock23`, `Tsit5` or `Vern7` |
| **tol** | relative tolerance |

- The status next to the settings shows the progress (`t / t_end`), then `done in …`, `cancelled` or `failed: …`.
- The **worker status** pill at the right shows whether the simulation worker is starting, warming up, ready or has crashed. Hover it for details. The first run after a start takes longer while the worker warms up.

## The bottom dock

The panel below the editor has the tabs **Plots**, **Auto Plot**, **3D View**, **Diagnostics**, **Debug**, **Signals** and **Log**.

## Plot signals

Every signal of a run is recorded, so you can plot any signal after the run, without adding sinks. There are several ways to add one:

- **From the canvas:** right-click a bond and choose **Plot effort**, **Plot flow** or **Plot power**, or right-click a block and choose **Plot all outputs**.
- **From the Signals tab:** search by name, path or unit. Double-click a signal or click its **+** to add it, or drag it onto a plot panel. **Add to** picks the target panel; **Plot all** adds every listed signal.
- **From the inspector:** right-click a signal in the block's signal list.

Signals go to the **Active** panel, which you choose in the plot toolbar.

### Work with plots

- **+ Panel** adds a panel. Type in a panel's title to rename it. A panel has at most two y axes; signals with a third unit go to a new panel.
- Drag horizontally to zoom in on a time range, use the mouse wheel to zoom at the pointer, and double-click (or **Reset zoom**) to show the whole run. The cursor and its values are shared by all panels.
- During a run the plots update live and follow the latest time. Zooming pauses the following; **Follow live** resumes it.
- **Pin run** keeps the current run. Start another run to compare: the pinned run shows as dashed lines.
- **CSV** downloads the plotted signals. The download runs as a [background task](page:background-tasks).
- **Detach** opens the plots in a separate browser window.

## Auto Plot

While the **Auto Plot** tab is open, it plots every recorded signal of the selected block, subsystem or connection. Choose a **Layout**: all signals in one panel, one signal per panel, or grouped by unit.

## 3D view

Models with a 3D scene show it in the **3D View** tab. The scene follows the run through bindings between scene objects and signals.

- Drag to orbit, right-drag to pan, scroll to zoom.
- The toolbar has **Isometric**, **Top**, **Front** and **Side** views, an **Orthographic projection** toggle, **Fit the scene in the view**, **Full screen** (with the playback bar; `Esc` exits) and **Detach** (a separate window).
- The playback bar replays the run: **Play**/**Pause** (`Space` when the 3D view has focus), **Rewind to start**, **Speed** (0.1× to 4×), **Loop** and a time slider.
- **Bindings** opens the bindings table. Each row binds a scene object's property (position, pose, scale, colour or visibility) to a signal, with a gain and an offset. **Add binding** adds a row.
