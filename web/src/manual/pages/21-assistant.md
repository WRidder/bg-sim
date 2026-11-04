# The assistant

The assistant is a chat panel that can explain, build and change models, run simulations and work out what the results mean. Open it with the **speech bubble** in the top bar, on any screen. Drag its left edge to resize it.

## On the home screen

Without a project open, the chat can answer questions about bg-sim, look through the example projects and create a new project for you. A new project is created straight away, because that changes nothing that exists. **Open project** takes you there, and the chat comes with you. Its first models are still a proposal, see below.

## In a project

Everything the chat changes goes to a **draft**. Your saved model stays as it is, and the canvas does not change, until you press **Apply**.

The **Proposed changes** box lists what changed, per file, with the problems found so far.

| Button | Does |
| --- | --- |
| **Apply** | writes the draft; the open model changes as one undo step, so Ctrl+Z takes it all back |
| **Discard** | drops the draft |
| **Apply automatically** | applies by itself when a run ends with a draft that passed its checks |
| **New chat** | starts over; it asks first if there are changes not applied |

After Apply the open model, the docs, the library and the 3D View show the changes without a page reload.

The chat can build a dashboard with its cards and inputs, and a 3D scene: it writes the scene file, points the model at it and binds links and joints to signals. A new scene is part of the draft like everything else.

The previous versions of the files go to the project's `logs/assistant` folder. If a file changed on disk since the chat read it, Apply refuses and says which one.

A draft that was not checked since its last edit can still be applied; the box says so. A draft that cannot be saved cannot be applied.

## What it can do

- **Models.** Read and edit diagrams, blocks and their parameters, globals and settings, library blocks and docs pages. It looks at the model's existing layout and keeps to it. A new diagram gets a tidy layout, and bond graph elements hang off their junctions.
- **Diagnostics.** See the model's errors and warnings, syntax errors in block code, and the worker log.
- **Debugger.** Start a debug run with breakpoints, step, run to a time, evaluate expressions at a pause and try parameter changes live, rewind and replay. You see the run in the **Debug** tab and can take over at any pause. It reports any breakpoint that could not bind. It can also look at a run you paused yourself. Live edits never change the model; a fix that works goes in the draft like any other change. Closing the chat stops a debug run the assistant left paused.
- **Simulations.** Start and stop runs, read signals and statistics, compare runs and sweep a parameter. A run of a draft shows in the run history like any other; the Plots dock follows it when no run of yours is going.
- **Other projects.** Read your other projects, the examples and their docs as a reference. It can only change the project that is open.
- **Questions.** When a choice is yours, it asks with radio buttons or checkboxes, and waits for your answer.

## Show it what you mean

Select something and the chat sees it: blocks and connections on the canvas, text in the Code tab, or text on a docs page. The selection appears as a **chip** above the message box and goes along with your next message. Click **×** on a chip to leave it out. Clicking in the chat box does not lose the selection.

## What appears in the chat

Answers can contain math, tables and diagrams. Figures appear in the conversation: plots of run signals (**Show in the Plots dock** moves them there), drawings of a diagram level, tables and heat maps. Move the pointer over a chart to read off the values.

## Code cells

For anything computed from results, the assistant runs a small code cell and shows it, with its output, in the chat. The cell has the run's time as `t` and its signals as `s"Load/w"`. A parameter is `s"Motor/R"`, and globals are available by name.

```julia
u = linspace(t[1], t[end], length(t))
y = interp(u, t, s"Load/w")
plot("Spectrum", fftfreq(length(y), samplerate(u)), abs(fft(y)))
table("Peak", maximum(y))
```

| Function | Shows |
| --- | --- |
| `plot`, `scatter`, `bar` | a chart; the title comes first and is optional |
| `table` | a table, one column per argument, named after the expression |
| `image` | a matrix as a heat map |
| `text`, `print` | a line of text |

These names also work capitalised, such as `Plot` and `Table`.

Cells look like Julia but are not run by Julia. bg-sim's own interpreter runs them, as it does for block equations, so a cell cannot reach files, the network or the system. It has statistics, integrals, FFTs, filters, peak finding, fits and linear algebra, and a cell can define its own functions. A cell stops at its work limit or after 30 seconds. Solver output is not evenly spaced in time, so resample with `linspace` and `interp` before an FFT.

## Choosing a model

The chat uses the profiles in `assistant.toml` in the bg-sim folder, or `assistant.example.toml` without one. When there is more than one, pick it at the top of the panel before the first message.

| Runner | Uses |
| --- | --- |
| `claude-cli` | the Claude Code command on your own subscription login, never an API key |
| `openai-compatible` | a local server (llama.cpp and the like), or a hosted service with an API key |

For a hosted service, `api_key_env` names the environment variable that holds the key. The key itself never goes in the file. The example file has two profiles through OpenCode Go, DeepSeek V4.1 Flash and GLM-5.3-Flash: set `OPENCODE_API_KEY` before you start the backend. DeepSeek also needs **Global** under Regions in the OpenCode console, under Settings > Privacy. With a hosted service, the chat, your models and their results go to that service.

A profile that cannot be used is marked **(not available)** in the list. Pick it to see why, then fix it and press **Check again**. On Windows a variable you set for your user is found without restarting BG-Sim.
