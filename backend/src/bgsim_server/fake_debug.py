"""Debug runs in the fake worker (plan 3.8, 5.13; WP P4.1).

The web lane (W4.1 to W4.3) develops and tests against this module, so it behaves like
the real worker at the protocol level -- the methods, the notifications, the manifest
and the diagnostics of plan 3.8 -- deterministically and fast. It simulates nothing: the
data of a debug run is the same synthetic table as every other fake run
(:func:`bgsim_server.worker._synthetic_columns`: 1001 rows, ``t`` = 0 .. 1 s in 1 ms
steps; signals ``Synthetic/sine``, ``/step``, ``/counter``, ``/flag``).

Time model
----------
* A **row** is one recorded sample (1 ms of simulated time). The fake treats each row as
  one *solver step*: ``solverStep`` stepping pauses after the next row, and watch, time
  and event conditions are checked after every row.
* A **fake tick** is :data:`TICK_ROWS` rows (10 ms of simulated time). Tick ``k`` is at
  ``t = 0.01 k`` (``k = 0 .. 100``, tick 0 at ``t0``). ``PausedInfo.tick`` is ``k`` at
  tick boundaries (statement pauses, ``tick`` steps) and ``null`` elsewhere.
* The run is paced in real time: :data:`TICK_WALL_S` = 10 ms of wall time per tick, so a
  complete run takes about one second, like a normal fake run (``BGSIM_FAKE_TICK_S``
  overrides the pace). A branch run fast-forwards to its branch time without pacing.
* While paused nothing is written: ``stream.f64`` ends with the pause row, so ``/data``
  ends exactly at the pause time. A pause flushes the stream, rewrites the manifest with
  status ``paused`` (``time.t1`` = pause time, ``debug.pauses`` appended) and then sends
  ``run.progress`` and ``debug.paused``; a resume rewrites the manifest as ``running``
  and then sends ``debug.resumed``.

Order inside one row (like the scheduler loop of plan 5.13): record the row; after-step
checks (watch crossing, event, time, ``runTo``, ``debug.pause``, ``solverStep`` and
``event`` stepping); then, on a tick boundary, the statement hooks of the tick (line
breakpoints, ``statement`` stepping) and the after-tick check (``tick`` stepping).

Breakpoints
-----------
* **Line** ``(ref, line, path)``: the block source is found from the model document
  (inline blocks), ``<projectDir>/library/<Name>.jl`` (``project:`` refs) or
  ``julia/BGSim/stdlib/<group>/<Name>.jl`` (``stdlib:`` refs). A *statement* is a
  non-blank, non-comment line inside an ``@discrete`` scope that is not ``end``,
  ``begin``, ``else`` or ``elseif`` (a heuristic scanner, not a parser). A statement
  line is verified (``resolved.hooks`` = matching instances); any other line gives
  **E401** with the D21 hint; a ref (or ``path``) the model does not use gives **W401**
  and ``verified = false``. When the source cannot be found the line is accepted as a
  statement. A verified line breakpoint pauses at *every* tick (reason ``breakpoint``,
  ``location`` with the statement range, a ``frame``). ``condition`` is evaluated in the
  frame; the locals are ``k`` (the tick number), ``v``, ``y`` (Real), ``on`` (Bool),
  ``xhat`` (a 2-vector, readable by ``evaluate`` only), the held outputs ``u`` and ``n``
  and ``t``. ``hitCount`` n pauses *only on the n-th hit* (a hit is a tick at which the
  condition holds, counted per breakpoint and per instance); counters reset when a
  breakpoint's definition changes.
* **Watch** ``s"id" > v`` (also ``<``, ``>=``, ``<=``, ``==``, ``!=``, arithmetic,
  ``&&``, ``||``, ``!``, a few functions, a comparison of two signals, ``t``): fires on
  the *upward crossing* (false to true) after a row, reason ``breakpoint``, ``frame``
  null, ``scope`` ``"watch"``. Adding or changing a watch re-arms it from the current
  row, so it never fires spuriously. At most 16 watches (:data:`MAX_WATCHES`); the 17th
  gets a status with an error diagnostic and ``verified = false``.
* **Time** ``t``: pauses at the first row with ``t_row >= t`` (reason ``time``), once.
* **Event**: the fake's events are the switching times of ``Synthetic/step`` and
  ``Synthetic/flag`` (0.25 s and 0.5 s). The pause (reason ``event``) is right after the
  switching row. ``event.path`` must be null or ``Synthetic`` (otherwise W401).
* **Exception**: accepted and verified, never fires (the fake has no solver failures).

Stepping (``debug.step``)
-------------------------
``statement`` pauses at the next statement hook of the tick (the hook table is every
statement of every instance of a block with ``@discrete`` code, in instance order then
line order) and wraps to the first hook of the next tick; without any hook it behaves
like ``tick``. ``tick`` pauses after the partitions of the current tick (the tick that
is running or about to run). ``solverStep`` pauses after the next row. ``event`` pauses
at the next event of the list above. All four give reason ``step``.

Other commands
--------------
``evaluate`` is a small safe expression evaluator (never Python ``eval``): numbers,
``s"id"``, ``t``, ``+ - * /``, comparisons, ``&&``, ``||``, ``!``, ``abs sqrt sin cos
min max``, and at a statement pause the frame names. Errors give a result with value
``0.0`` and an E001/E003/E004 diagnostic with ``scope = "watch"``. ``setParameter``
needs a path-qualified name (``Motor1/R``; otherwise E003), ``setState`` refuses ids that
end in ``/x_alg`` with **E402**; both record an ``Edit`` at the pause time in
``manifest.debug.edits`` and leave the synthetic data unchanged. A replay is a normal
fake run (no pauses) whose manifest records ``parentRun`` and the applied edits; a branch
is a debug run that pauses at ``t`` (reason ``time``) with ``parentRun``, ``branchAt``
and the parent's edits made before ``t``. Both read the parent's manifest next to the
new run directory. ``model.explain`` answers for any signal id.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import sys
import time
from collections.abc import Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .config import Settings
from .worker import _DEFAULT_RUN_SETTINGS, _SYNTHETIC_SIGNALS, _synthetic_columns, _utc_now

#: Rows per fake tick (10 ms of simulated time at the 1 ms row grid).
TICK_ROWS = 10
#: Wall time per fake tick; a whole run is about one second.
TICK_WALL_S = float(os.environ.get("BGSIM_FAKE_TICK_S", "0.01"))
#: The size of the watch pool (plan 5.13).
MAX_WATCHES = 16
#: Minimum wall time between two ``run.progress`` notifications of a running session.
PROGRESS_INTERVAL_S = 0.05

SIGNAL_IDS = [str(signal["id"]) for signal in _SYNTHETIC_SIGNALS]
_SIGNAL_UNITS = {str(signal["id"]): signal["unit"] for signal in _SYNTHETIC_SIGNALS}
_EVENT_SOURCE = {"path": "Synthetic", "ref": "inline:Synthetic"}

#: Methods this module answers for the fake worker.
METHODS = frozenset(
    {
        "debug.setBreakpoints",
        "debug.pause",
        "debug.continue",
        "debug.step",
        "debug.runTo",
        "debug.evaluate",
        "debug.values",
        "debug.setParameter",
        "debug.setState",
        "run.replay",
        "run.branch",
        "model.explain",
    }
)
_GRANULARITIES = ("statement", "tick", "solverStep", "event")
_SCOPE_MACROS = frozenset(
    {
        "constants", "parameters", "inputs", "outputs", "ports", "variables", "initial",
        "equations", "discrete", "events", "causality", "components", "connections",
        "observables",
    }
)  # fmt: skip


class DebugError(Exception):
    """A request the fake answers with an RPC error response."""


class _Cancelled(Exception):
    """The run was cancelled (``run.cancel``), possibly while paused."""


# --------------------------------------------------------------------------- diagnostics


def diagnostic(
    code: str,
    message: str,
    *,
    hint: str | None = None,
    path: str | None = None,
    block: str | None = None,
    scope: str | None = None,
    source: dict[str, Any] | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    """A plan 3.4 diagnostic with every key present.

    A path or block that is not a valid instance path or block reference is dropped, so the
    diagnostic always satisfies the contract.
    """
    path = path if path and _PATH.fullmatch(path) else None
    block = block if block and _valid_block(block) else None
    return {
        "code": code,
        "severity": severity or ("warning" if code.startswith("W") else "error"),
        "message": message,
        "hint": hint,
        "path": path,
        "block": block,
        "scope": scope,
        "source": source,
        "node": None,
        "connection": None,
    }


_PATH = re.compile(r"([A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*")
_BLOCK = re.compile(
    r"(stdlib:[A-Za-z0-9_]+(/[A-Za-z0-9_]+)*|project:[A-Za-z_][A-Za-z0-9_]*"
    r"|inline:[A-Za-z0-9_.-]+)"
)


def _valid_block(ref: str) -> bool:
    return _BLOCK.fullmatch(ref) is not None


def _source_kind(ref: str) -> str:
    return ref.split(":", 1)[0] if ":" in ref else "inline"


# --------------------------------------------------------------------------- expressions


class ExprError(Exception):
    """An expression error with a diagnostic code (E001 syntax, E003 name, E004 type)."""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.hint = hint

    def to_diagnostic(self) -> dict[str, Any]:
        return diagnostic(self.code, str(self), hint=self.hint, scope="watch")


_TOKEN = re.compile(
    r"""\s*(?:
        (?P<sig>s"[^"]*")
      | (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)
      | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>>=|<=|==|!=|&&|\|\||[-+*/()<>!,])
    )""",
    re.VERBOSE,
)
_COMPARE = {">", "<", ">=", "<=", "==", "!="}
_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "min": min,
    "max": max,
}

Node = tuple[Any, ...]


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(text):
        if text[position:].strip() == "":
            break
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            bad = text[position:].lstrip()[:1]
            raise ExprError(
                "E001",
                f"unexpected character {bad!r} in the expression",
                "write signals as s\"Motor1/i\" and use numbers, + - * /, comparisons and ( )",
            )
        position = match.end()
        kind = match.lastgroup or ""
        tokens.append((kind, match.group(kind)))
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.tokens = _tokenize(text)
        self.index = 0

    def parse(self) -> Node:
        if not self.tokens:
            raise ExprError("E001", "the expression is empty")
        node = self._or()
        if self.index != len(self.tokens):
            raise ExprError("E001", f"unexpected {self.tokens[self.index][1]!r} in the expression")
        return node

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _accept(self, *values: str) -> str | None:
        token = self._peek()
        if token is not None and token[0] == "op" and token[1] in values:
            self.index += 1
            return token[1]
        return None

    def _or(self) -> Node:
        node = self._and()
        while self._accept("||"):
            node = ("bin", "||", node, self._and())
        return node

    def _and(self) -> Node:
        node = self._compare()
        while self._accept("&&"):
            node = ("bin", "&&", node, self._compare())
        return node

    def _compare(self) -> Node:
        node = self._add()
        operator = self._accept(*_COMPARE)
        if operator is not None:
            node = ("bin", operator, node, self._add())
        return node

    def _add(self) -> Node:
        node = self._mul()
        while (operator := self._accept("+", "-")) is not None:
            node = ("bin", operator, node, self._mul())
        return node

    def _mul(self) -> Node:
        node = self._unary()
        while (operator := self._accept("*", "/")) is not None:
            node = ("bin", operator, node, self._unary())
        return node

    def _unary(self) -> Node:
        operator = self._accept("-", "+", "!")
        if operator is not None:
            return ("un", operator, self._unary())
        return self._primary()

    def _primary(self) -> Node:
        token = self._peek()
        if token is None:
            raise ExprError("E001", "the expression ends unexpectedly")
        kind, value = token
        self.index += 1
        if kind == "num":
            return ("num", float(value))
        if kind == "sig":
            return ("sig", value[2:-1])
        if kind == "name":
            if self._accept("("):
                if value not in _FUNCTIONS:
                    raise ExprError(
                        "E003",
                        f"unknown function {value!r}",
                        "the fake supports " + ", ".join(sorted(_FUNCTIONS)),
                    )
                arguments: list[Node] = []
                if not self._accept(")"):
                    arguments.append(self._or())
                    while self._accept(","):
                        arguments.append(self._or())
                    if not self._accept(")"):
                        raise ExprError("E001", "missing ) in the expression")
                return ("call", value, arguments)
            return ("name", value)
        if kind == "op" and value == "(":
            node = self._or()
            if not self._accept(")"):
                raise ExprError("E001", "missing ) in the expression")
            return node
        raise ExprError("E001", f"unexpected {value!r} in the expression")


def parse_expression(text: str) -> Node:
    """Parse a watch/evaluate/condition expression; raises :class:`ExprError`."""
    return _Parser(text).parse()


def _is_bool_node(node: Node) -> bool:
    if node[0] == "bin":
        return node[1] in _COMPARE or node[1] in ("&&", "||")
    return node[0] == "un" and node[1] == "!"


def _walk(node: Node) -> list[Node]:
    found = [node]
    if node[0] == "bin":
        found += _walk(node[2]) + _walk(node[3])
    elif node[0] == "un":
        found += _walk(node[2])
    elif node[0] == "call":
        for argument in node[2]:
            found += _walk(argument)
    return found


def _signal_id(name: str, context: str | None) -> str | None:
    """The synthetic signal id for ``name`` (absolute, or relative to ``context``)."""
    if name in _SIGNAL_UNITS:
        return name
    if context and f"{context}/{name}" in _SIGNAL_UNITS:
        return f"{context}/{name}"
    return None


class Env:
    """What an expression can read: the row's signals, ``t`` and the frame names."""

    def __init__(
        self,
        t: float,
        signals: dict[str, float],
        names: dict[str, float | bool] | None = None,
        context: str | None = None,
    ):
        self.t = t
        self.signals = signals
        self.names = names or {}
        self.context = context

    def name(self, name: str) -> float | bool:
        if name == "t":
            return self.t
        if name in self.names:
            return self.names[name]
        signal = _signal_id(name, self.context)
        if signal is not None:
            return self.signals[signal]
        raise ExprError(
            "E003",
            f"unknown name {name!r} in the expression",
            "use s\"Synthetic/sine\" for a signal, t for the time, "
            "or a local of the current statement pause",
        )

    def signal(self, signal_id: str) -> float:
        resolved = _signal_id(signal_id, self.context)
        if resolved is None:
            raise ExprError(
                "E003",
                f"unknown signal {signal_id!r}",
                "this run records " + ", ".join(SIGNAL_IDS),
            )
        return self.signals[resolved]


def evaluate_node(node: Node, env: Env) -> float | bool:
    """Evaluate a parsed expression; Bool only in conditions and logic (E004 otherwise)."""
    kind = node[0]
    if kind == "num":
        return float(node[1])
    if kind == "sig":
        return env.signal(node[1])
    if kind == "name":
        return env.name(node[1])
    if kind == "call":
        values = [_real(evaluate_node(argument, env), node[1]) for argument in node[2]]
        try:
            return float(_FUNCTIONS[node[1]](*values))
        except (ValueError, TypeError) as exc:
            raise ExprError("E004", f"{node[1]}() cannot be evaluated here: {exc}") from None
    if kind == "un":
        value = evaluate_node(node[2], env)
        if node[1] == "!":
            return not _boolean(value, "!")
        return -_real(value, node[1]) if node[1] == "-" else _real(value, node[1])
    operator = node[1]
    left = evaluate_node(node[2], env)
    if operator == "&&":
        return _boolean(left, operator) and _boolean(evaluate_node(node[3], env), operator)
    if operator == "||":
        return _boolean(left, operator) or _boolean(evaluate_node(node[3], env), operator)
    right = evaluate_node(node[3], env)
    if operator in _COMPARE:
        a, b = _real(left, operator), _real(right, operator)
        return {
            ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b, "==": a == b, "!=": a != b,
        }[operator]  # fmt: skip
    a, b = _real(left, operator), _real(right, operator)
    if operator == "+":
        return a + b
    if operator == "-":
        return a - b
    if operator == "*":
        return a * b
    if b == 0.0:
        raise ExprError("E004", "division by zero", "check the divisor of the expression")
    return a / b


def _real(value: float | bool, operator: str) -> float:
    if isinstance(value, bool):
        raise ExprError(
            "E004", f"a Bool cannot be used with {operator!r}", "Bool only works in && || and !"
        )
    return value


def _boolean(value: float | bool, operator: str) -> bool:
    if not isinstance(value, bool):
        raise ExprError(
            "E004", f"{operator!r} needs a Bool (a comparison)", "compare the value first"
        )
    return value


# --------------------------------------------------------------------------- block sources


@dataclass
class SourceInfo:
    """What the breakpoint resolver needs to know about one block source."""

    lines: list[str]
    scopes: dict[int, str]  #: line -> scope macro name (``@discrete``), for lines inside one
    statements: list[int]  #: 1-based lines of the ``@discrete`` statements

    def range_of(self, line: int) -> dict[str, int]:
        if not 1 <= line <= len(self.lines):
            return {"line": line, "col": 1, "endLine": line, "endCol": 2}
        code = _strip_comment(self.lines[line - 1]).rstrip()
        col = len(code) - len(code.lstrip()) + 1
        return {"line": line, "col": col, "endLine": line, "endCol": max(len(code) + 1, col + 1)}


_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_BRACKETS = re.compile(r"\[[^\[\]]*\]")
_OPENERS = re.compile(r"\b(?:begin|if|for|while|function|let|do|try|struct|quote|macro|module)\b")
_CLOSERS = re.compile(r"\bend\b")
_MACRO = re.compile(r"^@([A-Za-z_][A-Za-z0-9_]*)\b(.*)$")
_NON_STATEMENT = ("end", "begin", "else", "elseif")


def _strip_comment(line: str) -> str:
    in_string = False
    for index, char in enumerate(line):
        if char == '"' and (index == 0 or line[index - 1] != "\\"):
            in_string = not in_string
        elif char == "#" and not in_string:
            return line[:index]
    return line


def _code_for_counting(line: str) -> str:
    code = _STRING.sub('""', _strip_comment(line))
    previous = None
    while previous != code:  # nested index brackets, e.g. x[y[1]]
        previous, code = code, _BRACKETS.sub("", code)
    return code


def analyse_source(text: str) -> SourceInfo:
    """Find the ``@discrete`` statement lines of a block source (a heuristic scanner)."""
    lines = text.splitlines()
    scopes: dict[int, str] = {}
    statements: list[int] = []
    depth = 0
    scope: str | None = None
    scope_depth = 0
    for number, raw in enumerate(lines, 1):
        code = _code_for_counting(raw)
        stripped = code.strip()
        opens = len(_OPENERS.findall(code))
        closes = len(_CLOSERS.findall(code))
        first = stripped.split(None, 1)[0] if stripped else ""
        if scope is None:
            match = _MACRO.match(stripped)
            if match and depth == 1 and match.group(1) in _SCOPE_MACROS:
                name = "@" + match.group(1)
                scopes[number] = name
                if opens > closes:
                    scope, scope_depth = name, depth
                elif name == "@discrete" and match.group(2).strip():
                    statements.append(number)  # a one-line scope holds its statement
        else:
            scopes[number] = scope
            if stripped and first not in _NON_STATEMENT and scope == "@discrete":
                statements.append(number)
        depth += opens - closes
        if scope is not None and depth <= scope_depth:
            scope = None
    return SourceInfo(lines, scopes, statements)


@dataclass(frozen=True)
class Instance:
    """One block instance of the model: the path, the block reference and its source text."""

    path: str
    ref: str
    source: str | None


def model_instances(model: dict[str, Any] | None) -> list[Instance]:
    """Every block instance of a model document, subsystems included, in document order."""
    found: list[Instance] = []

    def walk(diagram: dict[str, Any], prefix: str) -> None:
        for node in diagram.get("nodes") or []:
            block = node.get("block") or {}
            path = f"{prefix}{node.get('name')}"
            if "ref" in block:
                found.append(Instance(path, str(block["ref"]), None))
            elif "inline" in block:
                source = (block["inline"] or {}).get("source")
                found.append(Instance(path, f"inline:{node.get('id')}", source))
            elif "subsystem" in block:
                walk((block["subsystem"] or {}).get("diagram") or {}, path + "/")

    if isinstance(model, dict):
        walk(model.get("diagram") or {}, "")
    return found


def source_path(settings: Settings, project_dir: Path | None, ref: str) -> Path | None:
    """The file that holds a ``stdlib:`` or ``project:`` block, or ``None``."""
    kind, _, name = ref.partition(":")
    if not name or ".." in name:
        return None
    if kind == "stdlib":
        return settings.repo_root / "julia" / "BGSim" / "stdlib" / f"{name}.jl"
    if kind == "project" and project_dir is not None:
        return project_dir / "library" / f"{name}.jl"
    return None


def load_source(
    settings: Settings, project_dir: Path | None, instance: Instance
) -> SourceInfo | None:
    """The analysed source of an instance's block, or ``None`` when it cannot be found."""
    text = instance.source
    if text is None:
        path = source_path(settings, project_dir, instance.ref)
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = None
    return analyse_source(text) if text is not None else None


# --------------------------------------------------------------------------- the data


@dataclass
class Hook:
    """One statement hook of the tick: instance path, block reference and source line."""

    path: str
    ref: str
    line: int
    range: dict[str, int]


@dataclass
class _Line:
    bp: dict[str, Any]
    hooks: list[Hook]
    condition: Node | None
    status: dict[str, Any]


@dataclass
class _Watch:
    bp: dict[str, Any]
    ast: Node | None
    status: dict[str, Any]
    definition: str = ""
    previous: bool = False


_FRAME_NAMES = ("k", "v", "y", "on", "u", "n")


def _scalar(name: str, kind: str, value: float | bool) -> dict[str, Any]:
    return {"name": name, "type": kind, "size": [], "value": value}


@dataclass
class _Table:
    """The synthetic run: 5 x 1001 float64 (time first) and the derived event times."""

    data: np.ndarray = field(default_factory=_synthetic_columns)

    def __post_init__(self) -> None:
        self.n = int(self.data.shape[1])
        t = self.data[0]
        switching = np.nonzero(np.diff(self.data[2]) != 0.0)[0] + 1
        switching = np.union1d(switching, np.nonzero(np.diff(self.data[4]) != 0.0)[0] + 1)
        self.event_times = [float(t[i]) for i in switching]

    def t(self, row: int) -> float:
        return float(self.data[0, row])

    def signals(self, row: int) -> dict[str, float]:
        return {sid: float(self.data[1 + i, row]) for i, sid in enumerate(SIGNAL_IDS)}

    def row_at_or_after(self, t: float) -> int:
        return min(int(np.searchsorted(self.data[0], t - 1e-12, side="left")), self.n - 1)


def frame_for(table: _Table, row: int, tick: int) -> dict[str, Any]:
    """The fake frame at a statement pause: locals, held outputs and previous-tick values."""
    sine = float(table.data[1, row])
    t = table.t(row)
    prior = max(row - TICK_ROWS, 0)
    return {
        "locals": [
            _scalar("k", "Int", tick),
            _scalar("v", "Real", sine),
            _scalar("y", "Real", math.cos(2.0 * math.pi * t)),
            _scalar("on", "Bool", bool(table.data[4, row] >= 0.5)),
            {"name": "xhat", "type": "Real", "size": [2], "value": [sine, 0.5 * sine]},
        ],
        "held": [
            _scalar("u", "Real", float(table.data[2, row])),
            _scalar("n", "Int", int(table.data[3, row])),
        ],
        "previous": [
            _scalar("v", "Real", float(table.data[1, prior])),
            _scalar("u", "Real", float(table.data[2, prior])),
        ],
    }


def frame_env(table: _Table, row: int, tick: int) -> dict[str, float | bool]:
    """The scalar frame names as an expression environment."""
    frame = frame_for(table, row, tick)
    names: dict[str, float | bool] = {}
    for entry in [*frame["locals"], *frame["held"]]:
        if entry["size"] == []:
            names[entry["name"]] = entry["value"]
    return names


# --------------------------------------------------------------------------- the session


class Session:
    """One fake run: a debug run, a branch, or a plain (replay) run, as one task."""

    def __init__(
        self,
        host: FakeDebugger,
        run_id: str,
        run_dir: Path,
        *,
        model: dict[str, Any] | None,
        project_dir: str | None,
        manifest_base: dict[str, Any],
        debug: dict[str, Any] | None,
        parent: str | None = None,
        branch_at: float | None = None,
        edits: list[dict[str, Any]] | None = None,
        record_debug: bool = False,
        fast_until: float = -1.0,
        run_to: float | None = None,
    ):
        self.host = host
        self.run_id = run_id
        self.run_dir = run_dir
        self.model = model
        self.project_dir = Path(project_dir) if project_dir else None
        self.manifest_base = manifest_base
        self.debug_enabled = debug is not None
        self.record_debug = record_debug or self.debug_enabled
        self.parent = parent
        self.branch_at = branch_at
        self.edits: list[dict[str, Any]] = list(edits or [])
        self.pauses: list[dict[str, Any]] = []
        self.breakpoints: list[dict[str, Any]] = list((debug or {}).get("breakpoints") or [])
        self.pause_on_entry = bool((debug or {}).get("pauseOnEntry"))
        self.fast_until = fast_until
        self.table = _Table()
        self.instances = model_instances(model)
        self._sources: dict[str, SourceInfo | None] = {}
        self.base_hooks: list[Hook] = self._build_hooks()
        self.hooks: list[Hook] = list(self.base_hooks)
        self.lines: list[_Line] = []
        self.watches: list[_Watch] = []
        self.statuses: list[dict[str, Any]] = []
        self._counters: dict[str, tuple[str, int]] = {}
        self._fired_times: set[str] = set()
        self._definitions: dict[str, str] = {}
        self.state = "running"
        self.row = -1
        self.flushed = 0
        self.paused_info: dict[str, Any] | None = None
        self._resume: asyncio.Future | None = None
        self._pause_flag = False
        self._cancel = False
        self._step: str | None = None
        self._run_to = run_to
        self._manifest_lock = asyncio.Lock()
        self._stream: Any = None
        self._clock0 = 0.0
        self._last_progress = 0.0
        self._started = time.perf_counter()
        self._resolve_breakpoints()

    # ------------------------------------------------------------ sources and hooks

    def source(self, instance: Instance) -> SourceInfo | None:
        """The analysed source of an instance's block, or ``None`` when it cannot be found."""
        if instance.ref not in self._sources:
            self._sources[instance.ref] = load_source(
                self.host.settings, self.project_dir, instance
            )
        return self._sources[instance.ref]

    def _build_hooks(self) -> list[Hook]:
        hooks: list[Hook] = []
        for instance in self.instances:
            info = self.source(instance)
            if info is None:
                continue
            for line in info.statements:
                hooks.append(Hook(instance.path, instance.ref, line, info.range_of(line)))
        return hooks

    # ------------------------------------------------------------ breakpoints

    def set_breakpoints(self, breakpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace the full set; returns the status of every breakpoint, in order."""
        self.breakpoints = list(breakpoints)
        self._resolve_breakpoints()
        return [status for status in self.statuses]

    def _resolve_breakpoints(self) -> None:
        previous_watch = {w.bp["id"]: w for w in self.watches}
        self.lines, self.watches, self.statuses = [], [], []
        extra: list[Hook] = []
        watch_count = 0
        row = max(self.row, 0)
        for bp in self.breakpoints:
            kind = bp.get("kind")
            definition = json.dumps({k: v for k, v in bp.items() if k != "enabled"}, sort_keys=True)
            if self._definitions.get(bp["id"]) != definition:
                self._counters.pop(bp["id"], None)
                self._fired_times.discard(bp["id"])
            self._definitions[bp["id"]] = definition
            if kind == "line":
                entry = self._resolve_line(bp, extra)
                self.lines.append(entry)
                self.statuses.append(entry.status)
            elif kind == "watch":
                watch_count += 1
                watch = self._resolve_watch(bp, watch_count)
                watch.definition = definition
                before = previous_watch.get(bp["id"])
                if before is not None and before.definition == definition:
                    watch.previous = before.previous
                else:  # a new or changed watch is armed from the current row: no spurious pause
                    watch.previous = self._watch_truth(watch, row)
                self.watches.append(watch)
                self.statuses.append(watch.status)
            elif kind == "event":
                path = (bp.get("event") or {}).get("path")
                if path in (None, "Synthetic"):
                    self.statuses.append(_status(bp["id"], True, 1, ["Synthetic"]))
                else:
                    self.statuses.append(
                        _status(
                            bp["id"],
                            False,
                            0,
                            [],
                            [
                                diagnostic(
                                    "W401",
                                    f"no event source at path {path!r}: the fake's events "
                                    "come from Synthetic",
                                    hint="use the path Synthetic or leave the path empty",
                                    path=None,
                                )
                            ],
                        )
                    )
            else:  # time, exception
                self.statuses.append(_status(bp["id"], True, 1, []))
        self.hooks = sorted(
            [*self.base_hooks, *extra],
            key=lambda h: (self._instance_index(h.path, h.ref), h.line),
        )

    def _instance_index(self, path: str, ref: str) -> int:
        for index, instance in enumerate(self.instances):
            if instance.path == path and instance.ref == ref:
                return index
        return len(self.instances)

    def _resolve_line(self, bp: dict[str, Any], extra: list[Hook]) -> _Line:
        target = bp["line"]
        ref, line, path = str(target["ref"]), int(target["line"]), target.get("path")
        diagnostics: list[dict[str, Any]] = []
        used = [i for i in self.instances if i.ref == ref]
        matching = [i for i in used if path is None or i.path == path]
        condition: Node | None = None
        if not matching:
            where = f" at {path}" if path else ""
            diagnostics.append(
                diagnostic(
                    "W401",
                    f"the breakpoint's block {ref}{where} is not used in this model, "
                    "so it stays unverified",
                    hint=f"instantiate {ref} in the model or remove the breakpoint",
                    path=path,
                    block=ref,
                )
            )
            return _Line(bp, [], None, _status(bp["id"], False, 0, [], diagnostics))
        info = self.source(matching[0])
        hooks: list[Hook] = []
        if info is not None and line not in info.statements:
            scope = info.scopes.get(line)
            diagnostics.append(
                diagnostic(
                    "E401",
                    f"no statement on line {line} of {ref}",
                    hint="equations do not execute in order; "
                    "add a watch breakpoint on a signal instead",
                    path=path or matching[0].path,
                    block=ref,
                    scope=scope,
                    source={
                        "kind": _source_kind(ref),
                        "ref": ref,
                        "range": info.range_of(line),
                    },
                )
            )
            return _Line(bp, [], None, _status(bp["id"], False, 0, [], diagnostics))
        for instance in matching:
            known = next(
                (h for h in self.base_hooks if h.path == instance.path and h.line == line), None
            )
            if known is None:  # the source was not found: accept the line as a statement
                known = Hook(
                    instance.path,
                    instance.ref,
                    line,
                    {"line": line, "col": 1, "endLine": line, "endCol": 2},
                )
                extra.append(known)
            hooks.append(known)
        text = bp.get("condition")
        if text:
            try:
                condition = parse_expression(str(text))
                unknown = [
                    n[1]
                    for n in _walk(condition)
                    if n[0] == "name" and n[1] != "t" and n[1] not in _FRAME_NAMES
                ]
                if unknown:
                    raise ExprError(
                        "E003",
                        f"unknown name {unknown[0]!r} in the condition",
                        "the frame holds " + ", ".join(_FRAME_NAMES) + " and t",
                    )
            except ExprError as exc:
                condition = None
                diag = exc.to_diagnostic()
                diag["scope"] = "@discrete"
                return _Line(
                    bp, [], None, _status(bp["id"], False, len(hooks), [], [diag])
                )
        return _Line(
            bp,
            hooks,
            condition,
            _status(bp["id"], True, len(hooks), [h.path for h in hooks], diagnostics),
        )

    def _resolve_watch(self, bp: dict[str, Any], ordinal: int) -> _Watch:
        spec = bp["watch"]
        context = spec.get("context")
        if ordinal > MAX_WATCHES:
            diag = diagnostic(
                "E001",
                f"at most {MAX_WATCHES} watch breakpoints",
                hint="remove or disable another watch breakpoint first",
                scope="watch",
            )
            return _Watch(bp, None, _status(bp["id"], False, 0, [], [diag]))
        try:
            ast = parse_expression(str(spec["expr"]))
            for node in _walk(ast):
                if node[0] == "sig":
                    Env(0.0, {s: 0.0 for s in SIGNAL_IDS}, context=context).signal(node[1])
                elif node[0] == "name" and node[1] != "t":
                    Env(0.0, {s: 0.0 for s in SIGNAL_IDS}, context=context).name(node[1])
            if not _is_bool_node(ast):
                raise ExprError(
                    "E004",
                    "a watch expression must be a comparison",
                    'write for example s"Synthetic/sine" > 0.5',
                )
        except ExprError as exc:
            return _Watch(bp, None, _status(bp["id"], False, 0, [], [exc.to_diagnostic()]))
        paths = [context] if context else ["Synthetic"]
        return _Watch(bp, ast, _status(bp["id"], True, 1, paths))

    def _watch_truth(self, watch: _Watch, row: int) -> bool:
        if watch.ast is None:
            return False
        env = Env(
            self.table.t(row),
            self.table.signals(row),
            context=(watch.bp["watch"] or {}).get("context"),
        )
        try:
            return bool(evaluate_node(watch.ast, env))
        except ExprError:
            return False

    # ------------------------------------------------------------ commands from the worker

    @property
    def paused(self) -> bool:
        return self.state == "paused"

    def request_pause(self) -> None:
        if self.state == "running":
            self._pause_flag = True

    def request_cancel(self) -> None:
        self._cancel = True
        if self._resume is not None and not self._resume.done():
            self._resume.set_result(("cancel", None))

    def resume(self, command: str, argument: Any = None) -> None:
        assert self._resume is not None and not self._resume.done()
        self._resume.set_result((command, argument))

    def run_to_check(self, t: float) -> None:
        if t <= self.table.t(self.row) + 1e-12:
            raise DebugError(f"runTo needs a time after the pause time {self.table.t(self.row):g}")
        if t > self.table.t(self.table.n - 1) + 1e-12:
            raise DebugError(f"runTo time {t:g} is after the end of the run")

    def evaluate(self, expr: str, context: str | None) -> dict[str, Any]:
        row = self.row
        names: dict[str, float | bool] = {}
        vector: dict[str, dict[str, Any]] = {}
        if self.paused_info is not None and self.paused_info.get("frame") is not None:
            names = frame_env(self.table, row, row // TICK_ROWS)
            for entry in self.paused_info["frame"]["locals"]:
                if entry["size"]:
                    vector[entry["name"]] = entry
        env = Env(self.table.t(row), self.table.signals(row), names, context)
        try:
            node = parse_expression(expr)
            if node[0] == "name" and node[1] in vector:
                entry = vector[node[1]]
                return {
                    "value": entry["value"],
                    "type": entry["type"],
                    "size": entry["size"],
                    "unit": None,
                    "diagnostics": [],
                }
            value = evaluate_node(node, env)
        except ExprError as exc:
            return {
                "value": 0.0,
                "type": "Real",
                "size": [],
                "unit": None,
                "diagnostics": [exc.to_diagnostic()],
            }
        unit = None
        if node[0] == "sig":
            resolved = _signal_id(node[1], context)
            unit = _SIGNAL_UNITS.get(resolved) if resolved else None
        return {
            "value": value,
            "type": "Bool" if isinstance(value, bool) else "Real",
            "size": [],
            "unit": unit,
            "diagnostics": [],
        }

    def values(self, ids: list[str]) -> dict[str, Any]:
        signals = self.table.signals(self.row)
        return {
            "t": self.table.t(self.row),
            "values": {sid: signals[sid] for sid in ids if sid in signals},
        }

    async def edit(self, kind: str, target: str, value: float) -> dict[str, Any]:
        if kind == "parameter" and "/" not in target:
            return {
                "ok": False,
                "edit": None,
                "diagnostics": [
                    diagnostic(
                        "E003",
                        f"unknown parameter {target!r}",
                        hint="write the instance path and the parameter, for example Motor1/R",
                        scope="watch",
                    )
                ],
            }
        if kind == "state" and target.endswith("/x_alg"):
            return {
                "ok": False,
                "edit": None,
                "diagnostics": [
                    diagnostic(
                        "E402",
                        f"state change refused: {target} is determined by an algebraic "
                        "equation, not a differential state",
                        hint="change a differential state or a parameter instead; "
                        "algebraic variables follow from the equations (DAE)",
                        path=target.rsplit("/", 1)[0] or None,
                    )
                ],
            }
        edit = {"t": self.table.t(self.row), "kind": kind, "target": target, "value": float(value)}
        self.edits.append(edit)
        await self.write_manifest()
        return {"ok": True, "edit": edit, "diagnostics": []}

    # ------------------------------------------------------------ files

    def _manifest(self, status: str, stats: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = self.flushed
        t0 = float(self.table.data[0, 0])
        manifest: dict[str, Any] = {
            **self.manifest_base,
            "status": status,
            "signals": _SYNTHETIC_SIGNALS,
            "time": {
                "n": rows,
                "t0": t0,
                "t1": float(self.table.data[0, rows - 1]) if rows else t0,
            },
            "diagnostics": [],
            "layout": "columnar-f64-v1",
        }
        if stats is not None:
            manifest["stats"] = stats
        if self.parent is not None:
            manifest["parentRun"] = self.parent
        if self.branch_at is not None:
            manifest["branchAt"] = self.branch_at
        if self.record_debug:
            manifest["debug"] = {
                "breakpoints": self.breakpoints,
                "edits": self.edits,
                "pauses": self.pauses,
            }
        return manifest

    async def write_manifest(self, status: str | None = None, stats: dict | None = None) -> None:
        """Rewrite ``manifest.json`` atomically (retrying a Windows sharing violation)."""
        async with self._manifest_lock:
            document = self._manifest(status or self._file_status(), stats)
            text = json.dumps(document, indent=2) + "\n"
            temp = self.run_dir / "manifest.json.tmp"
            for attempt in range(100):
                try:
                    temp.write_text(text, encoding="utf-8")
                    os.replace(temp, self.run_dir / "manifest.json")
                    return
                except PermissionError:
                    if attempt == 99:
                        raise
                    await asyncio.sleep(0.005)

    def _file_status(self) -> str:
        return "paused" if self.state == "paused" else "running"

    def _flush(self) -> None:
        end = self.row + 1
        if end > self.flushed and self._stream is not None:
            np.ascontiguousarray(self.table.data[:, self.flushed : end].T).tofile(self._stream)
            self._stream.flush()
            self.flushed = end

    async def _progress(self) -> None:
        now = time.perf_counter()
        if now - self._last_progress < PROGRESS_INTERVAL_S:
            return
        self._last_progress = now
        self._flush()
        await self.host.notify(
            "run.progress",
            {"runId": self.run_id, "t": self.table.t(self.row), "rows": self.flushed},
        )

    # ------------------------------------------------------------ pausing

    def _paused_info(
        self,
        reason: str,
        *,
        breakpoint_id: str | None = None,
        location: dict[str, Any] | None = None,
        frame: dict[str, Any] | None = None,
        tick: int | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "t": self.table.t(self.row),
            "tick": tick,
            "reason": reason,
            "breakpointId": breakpoint_id,
            "location": location,
            "frame": frame,
            "diagnostics": diagnostics or [],
        }

    async def _pause(self, info: dict[str, Any]) -> None:
        """Flush, publish ``paused``, block until a resume command, publish ``resumed``."""
        self._step = None
        self._pause_flag = False
        self._flush()
        self.state = "paused"
        self.paused_info = info
        self.pauses.append({"t": info["t"], "reason": info["reason"]})
        await self.write_manifest()
        await self.host.notify(
            "run.progress", {"runId": self.run_id, "t": info["t"], "rows": self.flushed}
        )
        await self.host.notify("debug.paused", info)
        if self._cancel:
            self._resume = None
            raise _Cancelled
        self._resume = asyncio.get_running_loop().create_future()
        paused_at = time.perf_counter()
        command, argument = await self._resume
        self._resume = None
        self._clock0 += time.perf_counter() - paused_at
        if command == "cancel":
            raise _Cancelled
        self.state = "running"
        self.paused_info = None
        if command == "step":
            self._step = str(argument)
        elif command == "runTo":
            self._run_to = float(argument)
        await self.write_manifest()
        await self.host.notify("debug.resumed", {"runId": self.run_id})

    def _event_location(self) -> dict[str, Any]:
        return {
            **_EVENT_SOURCE,
            "scope": "@events",
            "range": {"line": 1, "col": 1, "endLine": 1, "endCol": 2},
        }

    def _watch_location(self, watch: _Watch) -> dict[str, Any]:
        spec = watch.bp["watch"]
        context = spec.get("context") or "Synthetic"
        return {
            "path": context,
            "ref": "inline:Synthetic",
            "scope": "watch",
            "range": {"line": 1, "col": 1, "endLine": 1, "endCol": max(len(spec["expr"]), 1) + 1},
        }

    # ------------------------------------------------------------ the run

    async def run(self) -> None:
        status = "done"
        stats: dict[str, Any] = {}
        self.run_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._stream = (self.run_dir / "stream.f64").open("wb")
            self._clock0 = time.perf_counter()
            await self.host.notify(
                "run.phase", {"runId": self.run_id, "phase": "simulate", "t_s": 0.0}
            )
            await self.write_manifest("running")
            try:
                await self._loop()
            except _Cancelled:
                status = "cancelled"
            rows = max(self.row + 1, 1) if status == "cancelled" else self.table.n
            self.row = rows - 1
            self._flush()
            self._stream.close()
            self._stream = None
            np.ascontiguousarray(self.table.data[:, :rows]).tofile(self.run_dir / "columns.f64")
            await self.host.notify(
                "run.phase",
                {"runId": self.run_id, "phase": "write", "t_s": self.table.t(rows - 1)},
            )
            stats = {
                "compile_s": 0.0,
                "sim_s": round(time.perf_counter() - self._started, 3),
                "steps": max(rows - 1, 0),
                "events": len(self.table.event_times),
                "states": 2,
                "equations": 7,
            }
            self.state = "done"
            await self.write_manifest(status, stats)
        except Exception as exc:  # noqa: BLE001 - keep the fake alive; report like the worker
            status = "failed"
            print(f"[fake-worker] debug run {self.run_id} failed: {exc!r}", file=sys.stderr)
            stats = {
                "compile_s": 0.0,
                "sim_s": round(time.perf_counter() - self._started, 3),
                "steps": 0,
                "events": 0,
                "states": 0,
                "equations": 0,
            }
            with suppress(Exception):
                await self.write_manifest("failed", stats)
        finally:
            self.state = "done"
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            self.host.finished(self.run_id)
        await self.host.notify(
            "run.done",
            {"runId": self.run_id, "status": status, "stats": stats, "diagnostics": []},
        )

    async def _loop(self) -> None:
        table = self.table
        for row in range(table.n):
            previous_t = table.t(row - 1) if row else -math.inf
            self.row = row
            t = table.t(row)
            if self._cancel:
                self.row = row - 1
                raise _Cancelled
            if row == 0 and self.pause_on_entry:
                await self._pause(self._paused_info("entry"))
            await self._after_step(row, previous_t, t)
            if row % TICK_ROWS == 0:
                await self._tick(row, row // TICK_ROWS)
        self._flush()

    async def _after_step(self, row: int, previous_t: float, t: float) -> None:
        candidate: dict[str, Any] | None = None
        crossed = False
        for watch in self.watches:
            truth = self._watch_truth(watch, row)
            fires = truth and not watch.previous and watch.bp.get("enabled", True)
            watch.previous = truth
            if fires and candidate is None:
                count = self._count_hit(watch.bp)
                wanted = watch.bp.get("hitCount")
                if wanted is None or count == wanted:
                    candidate = self._paused_info(
                        "breakpoint",
                        breakpoint_id=watch.bp["id"],
                        location=self._watch_location(watch),
                    )
        for time_t in self.table.event_times:
            if previous_t < time_t <= t + 1e-12:
                crossed = True
                break
        if candidate is None and crossed:
            for bp in self.breakpoints:
                if bp.get("kind") == "event" and bp.get("enabled", True):
                    status = next(s for s in self.statuses if s["id"] == bp["id"])
                    if status["verified"]:
                        candidate = self._paused_info(
                            "event", breakpoint_id=bp["id"], location=self._event_location()
                        )
                        break
        if candidate is None:
            for bp in self.breakpoints:
                if (
                    bp.get("kind") == "time"
                    and bp.get("enabled", True)
                    and bp["id"] not in self._fired_times
                    and (bp.get("time") or {}).get("t", math.inf) <= t + 1e-12
                ):
                    self._fired_times.add(bp["id"])
                    candidate = self._paused_info("time", breakpoint_id=bp["id"])
                    break
        if candidate is None and self._run_to is not None and self._run_to <= t + 1e-12:
            self._run_to = None
            candidate = self._paused_info("time")
        if candidate is None and self._pause_flag:
            candidate = self._paused_info("pause")
        if candidate is None and self._step == "solverStep":
            candidate = self._paused_info("step")
        if candidate is None and self._step == "event" and crossed:
            candidate = self._paused_info("step", location=self._event_location())
        if candidate is not None:
            if row % TICK_ROWS == 0 and candidate["reason"] == "step":
                candidate["tick"] = row // TICK_ROWS
            await self._pause(candidate)

    def _count_hit(self, bp: dict[str, Any], instance: str = "") -> int:
        key = bp["id"]
        definition = self._definitions.get(key, "")
        stored = self._counters.get(f"{key}|{instance}")
        count = (stored[1] if stored and stored[0] == definition else 0) + 1
        self._counters[f"{key}|{instance}"] = (definition, count)
        return count

    async def _tick(self, row: int, tick: int) -> None:
        for hook in list(self.hooks):
            reason: str | None = None
            breakpoint_id: str | None = None
            for entry in self.lines:
                if not entry.status["verified"] or not entry.bp.get("enabled", True):
                    continue
                if hook not in entry.hooks:
                    continue
                if entry.condition is not None:
                    env = Env(
                        self.table.t(row),
                        self.table.signals(row),
                        frame_env(self.table, row, tick),
                    )
                    try:
                        if evaluate_node(entry.condition, env) is not True:
                            continue
                    except ExprError:
                        continue
                count = self._count_hit(entry.bp, f"{hook.path}")
                wanted = entry.bp.get("hitCount")
                if wanted is None or count == wanted:
                    reason, breakpoint_id = "breakpoint", entry.bp["id"]
                    break
            if reason is None and self._step == "statement":
                reason = "step"
            if reason is not None:
                await self._pause(
                    self._paused_info(
                        reason,
                        breakpoint_id=breakpoint_id,
                        location={
                            "path": hook.path,
                            "ref": hook.ref,
                            "scope": "@discrete",
                            "range": hook.range,
                        },
                        frame=frame_for(self.table, row, tick),
                        tick=tick,
                    )
                )
        if self._step == "tick" or (self._step == "statement" and not self.hooks):
            await self._pause(self._paused_info("step", tick=tick))
        await self._progress()
        await self._pace(tick)

    async def _pace(self, tick: int) -> None:
        now = time.perf_counter()
        if self.table.t(self.row) < self.fast_until:
            self._clock0 = now - tick * TICK_WALL_S
            await asyncio.sleep(0)
            return
        delay = self._clock0 + tick * TICK_WALL_S - now
        await asyncio.sleep(max(0, delay))



def _status(
    bp_id: str,
    verified: bool,
    hooks: int,
    paths: list[str],
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": bp_id,
        "verified": verified,
        "resolved": {"hooks": hooks, "paths": paths},
        "diagnostics": diagnostics or [],
    }


# --------------------------------------------------------------------------- explain


def explain(
    settings: Settings,
    model: dict[str, Any] | None,
    project_dir: str | None,
    signal: str,
) -> dict[str, Any]:
    """A plausible ``ExplainResult`` for any signal id (see the module docstring)."""
    instances = model_instances(model)
    head = signal.split("/", 1)[0]
    owner = next((i for i in instances if i.path.split("/")[-1] == head or i.path == head), None)
    ref = owner.ref if owner is not None else "inline:Synthetic"
    line = 1
    if owner is not None:
        info = load_source(settings, Path(project_dir) if project_dir else None, owner)
        if info is not None:
            equations = [n for n, scope in sorted(info.scopes.items()) if scope == "@equations"]
            line = equations[1] if len(equations) > 1 else (equations[0] if equations else 1)
    name = signal.rsplit("/", 1)[-1]
    origin = {
        "path": owner.path if owner is not None else "Synthetic",
        "ref": ref,
        "range": {"line": line, "col": 5, "endLine": line, "endCol": 24},
    }
    unit = _SIGNAL_UNITS.get(signal)
    kind, expression, alias_of = "observed", f'2 * s"{SIGNAL_IDS[0]}"', None
    text = f"{name} ~ 2 * sine"
    if signal == "Synthetic/sine":
        expression, text = "sin(2 * pi * t)", "sine ~ sin(2 * pi * t)"
    elif signal == "Synthetic/step":
        kind, expression, alias_of = "alias", None, "Synthetic/step_cmd"
        text = "step ~ step_cmd"
    elif signal == "Synthetic/counter":
        kind, expression, text = "state", None, "ddt(counter) ~ 10"
    elif signal == "Synthetic/flag":
        kind, expression, text = "algebraic", None, "flag ~ ifelse(t >= 0.5, 1, 0)"
    elif signal.startswith("Motor1/i") or signal == "Motor1/i":
        expression = '(s"Motor1/V" - s"Motor1/E") / s"Motor1/R"'
        text = "i ~ (V - E) / R"
    return {
        "signal": signal,
        "kind": kind,
        "unit": unit,
        "expression": expression,
        "aliasOf": alias_of,
        "equations": [{"text": text, "origin": origin}],
        "diagnostics": [],
    }


# --------------------------------------------------------------------------- the host


class FakeDebugger:
    """The debug part of the fake worker: sessions, dispatch and the replay/branch runs."""

    METHODS = METHODS
    DebugError = DebugError

    def __init__(
        self,
        settings: Settings,
        notify: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]],
        spawn: Callable[[str, Coroutine[Any, Any, None]], None],
    ):
        self.settings = settings
        self.notify = notify
        self._spawn = spawn
        self.sessions: dict[str, Session] = {}
        self._models: dict[str, tuple[dict[str, Any], str | None]] = {}

    def remember(self, run_id: str, model: Any, project_dir: Any) -> None:
        """Keep the model of a started run so a replay or branch can resolve block sources."""
        if isinstance(model, dict):
            self._models[run_id] = (model, str(project_dir) if project_dir else None)

    def finished(self, run_id: str) -> None:
        self.sessions.pop(run_id, None)

    def cancel(self, run_id: str) -> bool:
        session = self.sessions.get(run_id)
        if session is None:
            return False
        session.request_cancel()
        return True

    # ------------------------------------------------------------ starting runs

    @staticmethod
    def _base(run_id: str, model: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": run_id,
            "model": str(model.get("name") or "SyntheticSignals"),
            "modelHash": hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest(),
            "created": _utc_now(),
            "settings": model.get("settings") or _DEFAULT_RUN_SETTINGS,
        }

    def start_debug(self, run_id: str, params: dict[str, Any]) -> None:
        """``run.start`` with ``debug``: a debug session."""
        model = params.get("model") if isinstance(params.get("model"), dict) else {}
        session = Session(
            self,
            run_id,
            Path(params["runDir"]),
            model=model,
            project_dir=params.get("projectDir"),
            manifest_base=self._base(run_id, model),
            debug=params["debug"],
        )
        self._launch(session)

    def _launch(self, session: Session) -> None:
        self.sessions[session.run_id] = session
        self._spawn(session.run_id, session.run())

    def _parent(self, params: dict[str, Any]) -> tuple[dict[str, Any], Path]:
        run_dir = Path(params["runDir"])
        parent_manifest = run_dir.parent / str(params["runId"]) / "manifest.json"
        try:
            document = json.loads(parent_manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise DebugError(f"unknown run {params['runId']!r}") from None
        return document, run_dir

    def _derived(
        self,
        params: dict[str, Any],
        *,
        debug: dict[str, Any] | None,
        branch_at: float | None,
    ) -> Session:
        parent, run_dir = self._parent(params)
        new_id = str(params["newRunId"])
        known = self._models.get(str(params["runId"]))
        if known is not None:
            self._models[new_id] = known
        edits = list(((parent.get("debug") or {}).get("edits")) or [])
        if branch_at is not None:
            edits = [e for e in edits if e["t"] < branch_at]
        base = {
            "id": new_id,
            "model": parent["model"],
            "modelHash": parent["modelHash"],
            "created": _utc_now(),
            "settings": parent["settings"],
        }
        return Session(
            self,
            new_id,
            run_dir,
            model=known[0] if known else None,
            project_dir=known[1] if known else None,
            manifest_base=base,
            debug=debug,
            parent=str(params["runId"]),
            branch_at=branch_at,
            edits=edits,
            record_debug=True,
            fast_until=branch_at if branch_at is not None else -1.0,
            run_to=branch_at,
        )

    # ------------------------------------------------------------ dispatch

    def _session(self, run_id: Any, *, need_paused: bool, message: str) -> Session:
        session = self.sessions.get(str(run_id))
        if session is None or not session.debug_enabled:
            raise DebugError(message)
        if need_paused and not session.paused:
            raise DebugError("run is not paused")
        return session

    async def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        """Answer one of :data:`METHODS`; raises :class:`DebugError` for an RPC error."""
        if method == "model.explain":
            known = params.get("model") if isinstance(params.get("model"), dict) else None
            return explain(self.settings, known, params.get("projectDir"), str(params["signal"]))
        if method == "run.replay":
            session = self._derived(params, debug=None, branch_at=None)
            self._launch(session)
            return {"accepted": True}
        if method == "run.branch":
            at = float(params["t"])
            session = self._derived(
                params, debug={"breakpoints": [], "pauseOnEntry": False}, branch_at=at
            )
            end = session.table.t(session.table.n - 1)
            if not 0.0 <= at <= end:
                raise DebugError(f"the branch time {at:g} is outside the run [0, {end:g}]")
            self._launch(session)
            return {"accepted": True}
        run_id = params.get("runId")
        not_debug = "run is not a debug run"
        if method == "debug.setBreakpoints":
            session = self._session(run_id, need_paused=False, message=not_debug)
            statuses = session.set_breakpoints(list(params.get("breakpoints") or []))
            await session.write_manifest()  # debug.breakpoints follows the full set
            return {"breakpoints": statuses}
        if method == "debug.pause":
            session = self._session(run_id, need_paused=False, message=not_debug)
            session.request_pause()
            return {"ok": True}
        session = self._session(run_id, need_paused=True, message="run is not paused")
        if method == "debug.continue":
            session.resume("continue")
            return {"ok": True}
        if method == "debug.step":
            granularity = params.get("granularity")
            if granularity not in _GRANULARITIES:
                raise DebugError(f"unknown step granularity {granularity!r}")
            session.resume("step", granularity)
            return {"ok": True}
        if method == "debug.runTo":
            at = float(params["t"])
            session.run_to_check(at)
            session.resume("runTo", at)
            return {"ok": True}
        if method == "debug.evaluate":
            return session.evaluate(str(params["expr"]), params.get("context"))
        if method == "debug.values":
            return session.values([str(i) for i in params.get("ids") or []])
        if method == "debug.setParameter":
            return await session.edit("parameter", str(params["name"]), float(params["value"]))
        if method == "debug.setState":
            return await session.edit("state", str(params["id"]), float(params["value"]))
        raise DebugError(f"method {method!r} is not implemented by the fake worker")
