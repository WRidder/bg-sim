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

Value, Gauge and Bar cards can have colour zones. An Indicator turns on above (or below) a threshold.

## Inputs

An input card binds one block parameter and **overrides it for the next run**. The model itself does not change.

- The card footer shows the model value; **Use model value** removes the override.
- A block parameter whose value is an expression of [global parameters](page:parameters) (`final = h_step`) starts at the value the globals give it, and the footer says which globals drive it. The card overrides that one block parameter only. When the value is just a global's name, **Bind to global** moves the card to the global itself, so it changes every parameter that uses that global.
- The inspector marks an overridden parameter with a `dashboard:` tag.
- The toolbar summarises what the next run uses, for example "Next run: 1 parameter override".
- If an input has a problem, the next run is refused until you fix it.

## Schedule table

A **Schedule** card changes parameters at given times during the run.

- The first column is the time `t [s]`. Add parameter columns with **+ Column…** and rows with **+ Row**.
- From each row's time on, the parameters take that row's values (step changes). Before the first row, the model values apply.

## Auto re-run

With **Auto re-run** checked, BG-Sim starts a new run shortly after you change an input. It works only while the Dashboard tab is open, waits for an active run to finish, and does not run while an input has a problem.
