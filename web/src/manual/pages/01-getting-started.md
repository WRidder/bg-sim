# Getting started

BG-Sim is a modeling and simulation tool for **bond graphs**, **block diagrams** and **equation models**. All three use one modeling language and can be mixed in one model. A model is simulated by a Julia worker in the background.

## The screen

| Area | What it holds |
| --- | --- |
| Top bar | the project and model, **Run** / **Debug** / **Stop**, run settings, **Export FMU…**, background tasks, worker status, theme toggle and this manual |
| Left | the block **Library** and the **Model tree** |
| Centre | the tabs **Diagram**, **Code**, **Docs**, **Parameters** and **Dashboard** |
| Right | the **Inspector** of the selection |
| Bottom | **Plots**, **Auto Plot**, **3D View**, **Diagnostics**, **Debug**, **Signals** and **Log** |

You can resize every panel by dragging its border; the sizes are remembered.

## Your first model in five steps

1. On the start page, type a project name under **New project** and click **Create project**. Or click **Open sample** on an example to get an editable copy.
2. Drag blocks from the [library](page:projects-and-library) onto the canvas.
3. Connect ports by dragging from one port to another (see [Building models](page:building-models)).
4. Select a block and set its parameters in the inspector.
5. Click **Run** (`Ctrl+Enter`), then plot signals: right-click a bond and choose **Plot effort**, or double-click a signal in the **Signals** tab (see [Running and plotting](page:running-and-plotting)).

Problems in the model show up in the [Diagnostics](page:diagnostics) tab while you edit.

## Help in the app

- `F1` with a block selected opens the help of that block: ports, parameters, units and defaults. With nothing selected, `F1` opens this manual.
- `?` shows all [keyboard shortcuts](page:keyboard-shortcuts).
- Hover a button for its tooltip; most tooltips name the shortcut.
- The **Docs** tab of an example model often has a walkthrough.
