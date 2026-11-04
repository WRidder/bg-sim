# Modelling assistant

A chat panel that creates and changes models, drives the simulation and assesses results. The
pattern comes from `D:\CtrlX Agentic Machine Control\planner-playground`. The user manual page is
`web/src/manual/pages/21-assistant.md`.

## Decisions

| Decision | Why |
|---|---|
| The backend owns a draft; nothing is saved until Apply | A chat can run for many turns and go wrong; the saved project stays the reference |
| One tool registry, two runners | `claude-cli` and `openai-compatible` must offer the same abilities and the same limits |
| `claude-cli` runs on the subscription login, never an API key | Key variables are stripped from the child and the runner aborts unless `system/init` reports `apiKeySource: "none"` |
| `system/init` self-check | The CLI must report exactly our MCP tools, no skills, no slash commands, no other server |
| Edit tools have no `project` argument | Other projects are read-only by construction, enforced by a test |
| `ask_user` does not block | The tool stores the question and the run ends; the answers start the next run, so no process waits on a person |
| The transcript is a fold over the events | A reloaded page replays from seq 0; there is no second record that could disagree |
| `valid` blocks Apply, `checked` blocks only auto-apply | A half-built model can be saved and fixed by hand; only an unattended Apply needs the stronger guarantee |
| `create_project` writes at once | It is additive; `Session.bind_project` then rebinds the draft, and opening the project finds the chat |
| Code cells use the language's own interpreter, not Julia `eval` | Spec principle "Julia syntax, not Julia semantics"; no approval step, no file, network or system access |
| Layout: new nodes only, unless `whole: true` | A user's existing arrangement is theirs; new diagrams get a layered layout |

## Debugger

The `debug_*` tools call what the Debug tab calls (`debug.COMMANDS`, `_derive_run`), so a run has one
state whoever drives it. A tool waits for the next `debug.paused`, by the identity of the notification
held in `_RunState.last_paused`, or for the end of the run. Control is limited to runs of the open
project. A followed debug run keeps its own breakpoints (`keepRunBreakpoints`): the editor's first-pause
resync would otherwise replace them with the user's. Live edits touch only the run, not the draft.

`debug_start` always starts paused at entry and sends the breakpoints then: only the answer to
`debug.setBreakpoints` says whether one bound, and the worker can only answer once the run is built.
An unbound breakpoint leaves the run at entry; a run that ends without a pause says so.

Known limit of the debugger itself: a watch is a continuous callback, and a signal of `@discrete` code
jumps at a tick, so such a watch is verified and never fires (`debug-tour`, `s"Ctrl/z" > 0.1`). The tool
descriptions send the agent to a line breakpoint with a condition instead.

## Layout

- `backend/src/bgsim_server/assistant/`: `tools.py` (registry), `draft.py`, `session.py`, `manager.py`,
  `api.py`, `runner_claude.py` + `mcp_relay.py`, `runner_openai.py`, `modelops.py`, `analysis.py`,
  `reference.py`, `selection.py`, `profiles.py`, `prompts/`.
- `julia/BGSim/src/sim/cells.jl`, `cell_library.jl`: worker RPC `code.run`. The backend extracts the
  `s"..."` ids with a regex and sends only those series.
- `web/src/assistant/`: `assistantStore.ts` (session, SSE, Apply), `transcript.ts` (the fold),
  `selectionStore.ts`, `panelStore.ts` (loaded on every page; the rest is a lazy chunk), and the cards.
- `contracts/schemas/assistant.schema.json`; `code.run` is in `worker-rpc.schema.json`. The TypeScript
  generator emits every `$defs` entry of this schema, since its root only points at the event.

## Security

- UI routes answer on the loopback interface only: the subscription login is for the user alone.
- The relay endpoints need a per-session bearer token, which never reaches the audit log.
- A hosted profile names an environment variable (`api_key_env`), never the key itself, and
  `Profile.public()` shows only the variable's name.
- Tool calls are read from structured `tool_calls` only, never parsed out of text.

## Hosted endpoints

`openai-compatible` also serves hosted services. OpenCode Go (the `deepseek-v4.1-flash` and
`glm-5.3-flash` profiles in `assistant.example.toml`) showed what a local server does not need: an `Authorization` header, a
named client (`User-Agent`, `x-opencode-session`), no `/models` listing (404, so only `auto` depends
on it) and `reasoning_content` kept in the history. The 404 and the base URL were checked without a
key; the endpoint has not been called with one yet.

## Verified

- Backend tests on the fake worker with `backend/tests/fake_claude.py`, the Julia cell tests, vitest
  and `web/tests/e2e/assistant.spec.ts` (real KaTeX and Mermaid, scripted `claude`).
- By hand on 2026-11-04, with Claude Code 2.1.318 and the real Julia worker: `system/init` accepted,
  run, FFT and table cells, recovery from cell errors, `add_block` with `near`, a proposal with
  diagnostics.

## Open

- A `copy_library_block` tool: `create_model` copies blocks and `write_library_block` adapts them.
- A project deleted during a chat ends only the audit log, not the session.
