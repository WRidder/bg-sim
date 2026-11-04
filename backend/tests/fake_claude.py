"""A fake ``claude -p --input-format stream-json --output-format stream-json``, driven by
``FAKE_CLAUDE_MODE``.

It reads the --mcp-config the runner wrote (to find the backend URL and the session token, as the
relay would), emits ``system/init`` and performs a scripted run per user line. Modes:

  ok            init is right; calls add_block on the backend; text; result
  ask           calls ask_user; on the next user line reports what it was told
  math          read only; answers with math, a mermaid diagram and a table
  figure        runs the open model, shows a plot and a diagram
  debug         starts a debug run of the open model and inspects the pause
  home          on the home screen: creates a project, then a model in its draft
  extra_tool    init lists one more tool                 (the runner must abort)
  skill         init lists a skill
  slash         init lists a slash command
  extra_server  init lists a second MCP server
  api_key       init has apiKeySource "ANTHROPIC_API_KEY"
  slow          never answers; ends its turn when interrupted
  die           exits straight away with a message on stderr
  auto          the Playwright spec: a #ok, #ask, #math, #figure, #cell, #debug or #home in the message
                picks one of the above per message (#home <name> names the project)

FAKE_CLAUDE_TOOLS: the tool names, joined with commas; without it they are read from the backend,
as the relay would. FAKE_CLAUDE_ENVDUMP: file that receives
the environment. FAKE_CLAUDE_ARGV: file that receives argv and the working directory.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

ANSWER = r"""The motor's electrical time constant is $\tau = L/R$:

$$
\tau = \frac{L}{R} = 1\,\text{ms}
$$

```mermaid
graph LR
  V[Source] --> M[Motor] --> L[Load]
```

| quantity | value |
|---|---|
| speed | 42 rad/s |
"""


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def result(**extra) -> dict:
    return {
        "type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.001,
        "num_turns": 2, "duration_ms": 5, "result": "done", **extra,
    }


def say(text: str) -> None:
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


def main() -> None:
    mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
    argv = sys.argv[1:]
    if os.environ.get("FAKE_CLAUDE_ENVDUMP"):
        with open(os.environ["FAKE_CLAUDE_ENVDUMP"], "w", encoding="utf-8") as file:
            json.dump(dict(os.environ), file)
    if os.environ.get("FAKE_CLAUDE_ARGV"):
        with open(os.environ["FAKE_CLAUDE_ARGV"], "w", encoding="utf-8") as file:
            json.dump({"argv": argv, "cwd": os.getcwd(), "entries": sorted(os.listdir("."))}, file)
    if mode == "die":
        print("fake claude: not logged in", file=sys.stderr)
        sys.exit(3)
    with open(argv[argv.index("--mcp-config") + 1], encoding="utf-8") as file:
        env = json.load(file)["mcpServers"]["bgsim"]["env"]
    if "FAKE_CLAUDE_TOOLS" in os.environ:
        names = os.environ["FAKE_CLAUDE_TOOLS"].split(",")
    else:
        listing = urllib.request.Request(
            f"{env['BGSIM_ASSISTANT_URL']}/tools",
            headers={"Authorization": "Bearer " + env["BGSIM_ASSISTANT_TOKEN"]},
        )
        with urllib.request.urlopen(listing, timeout=30) as response:
            names = [tool["name"] for tool in json.loads(response.read())["tools"]]
    tools = ["mcp__bgsim__" + name for name in names]
    init = {
        "type": "system", "subtype": "init", "session_id": "fake", "tools": tools, "model": "fake",
        "mcp_servers": [{"name": "bgsim", "status": "connected"}], "skills": [],
        "slash_commands": [], "apiKeySource": "none", "permissionMode": "dontAsk",
    }
    if mode == "extra_tool":
        init["tools"] = [*tools, "Bash"]
    elif mode == "skill":
        init["skills"] = ["deep-research"]
    elif mode == "slash":
        init["slash_commands"] = ["compact"]
    elif mode == "extra_server":
        init["mcp_servers"].append({"name": "other", "status": "connected"})
    elif mode == "api_key":
        init["apiKeySource"] = "ANTHROPIC_API_KEY"

    def call(name: str, args: dict) -> dict:
        request = urllib.request.Request(
            f"{env['BGSIM_ASSISTANT_URL']}/tools/{name}",
            data=json.dumps(args).encode(),
            headers={
                "Authorization": "Bearer " + env["BGSIM_ASSISTANT_TOKEN"],
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())

    started = False
    asked = False
    scripted = mode == "auto"
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("type") == "control_request":
            emit(result(subtype="error_during_execution", is_error=True, result="interrupted"))
            continue
        if not started:
            emit(init)
            started = True
        if mode == "slow":
            continue
        text = str(message["message"]["content"])
        if scripted:
            tag = re.search(r"#(ok|ask|math|figure|cell|debug|home)\b", text)
            mode = tag.group(1) if tag else "ask" if "My answers" in text else "math"
        if mode not in ("ok", "ask", "math", "figure", "cell", "debug", "home"):
            time.sleep(1.5)  # a bad init must be caught before this "model" acts
        if mode == "ask":
            if asked:
                say("You said: " + text[-80:])
            else:
                asked = True
                call("ask_user", {"title": "Scope", "questions": [
                    {"id": "friction", "prompt": "Model friction?", "kind": "single", "options": [
                        {"value": "none", "label": "No friction"},
                        {"value": "viscous", "label": "Viscous", "description": "Adds a damper"},
                    ]},
                    {"id": "plots", "prompt": "Which plots?", "kind": "multiple", "allowOther": True,
                     "options": [{"value": "speed", "label": "Speed"}, {"value": "power", "label": "Power"}]},
                ]})
                say("Two questions first.")
            emit(result())
            continue
        if mode == "math":
            say(ANSWER)
            emit(result())
            continue
        if mode == "home":
            assert not call("add_block", {"name": "x", "ref": "stdlib:bondgraph/R"})["result"].get("added")
            named = re.search(r"#home (\S+)", text)
            call("create_project", {"name": named.group(1) if named else "pendulum"})
            call("create_model", {"name": "first"})
            say("Created.")
            emit(result())
            continue
        if mode == "debug":
            paused = call("debug_start", {})["result"]
            value = call("debug_evaluate", {"run_id": paused["runId"], "expr": "t"})
            say(f"Paused at t = {paused['t']}, {paused['reason']}: {value['isError']}")
            emit(result())
            continue
        if mode == "cell":
            run = call("run_simulation", {})["result"]
            call("run_code", {"title": "Spectrum", "run_id": run["runId"], "code": 'Plot(t, s"Synthetic/sine")'})
            say("Done, see the cell.")
            emit(result())
            continue
        if mode == "figure":
            run = call("run_simulation", {})["result"]
            call("plot_signals", {"title": "Sine", "run_id": run["runId"], "signals": ["Synthetic/sine"]})
            call("show_diagram", {})
            say("Done, see the figures.")
            emit(result())
            continue
        name = f"Damp{time.monotonic_ns() % 100000}"
        added = call("add_block", {"name": name, "ref": "stdlib:bondgraph/R"})
        say(f"Added {name}. You said: {text[-60:]}")
        emit(result(applied=not added["isError"]))


if __name__ == "__main__":
    main()
