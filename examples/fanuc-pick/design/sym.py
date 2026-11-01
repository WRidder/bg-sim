"""Dual-mode scalar arithmetic: the same Python code evaluates numbers or writes bgsim discrete code.

The planner (`planner.py`) and the computed-torque servo (`servo.py`) are written once against
this module. With floats they are the Python reference that the optimizer and the validation
use; with `Sym` values they emit the statements of the generated `@discrete` blocks
(`build_library.py`), so the model and the reference compute the same formulas.

* `Sym(text)` is an expression; arithmetic and comparisons build new expressions.
* `Code.let(name, value)` emits `name = value` and returns `Sym(name)` (a float stays a float).
* `F.<fun>` dispatches `sqrt`, `sin`, `atan2`, `ifelse`, `min`, `max`, `clamp`, ... on the type.
"""

from __future__ import annotations

import math

import numpy as np


def _num(x: float) -> str:
    x = float(x)
    if x == 0.0:
        return "0.0"
    if x == int(x) and abs(x) < 1e15:
        return f"{x:.1f}"
    return repr(x)


def _wrap(x) -> str:
    if isinstance(x, Sym):
        return x.text
    if isinstance(x, bool):
        return "true" if x else "false"
    v = _num(x)
    return f"({v})" if v.startswith("-") else v


class Sym:
    __slots__ = ("text", "atom")

    def __init__(self, text: str, atom: bool = False) -> None:
        self.text = text if atom else f"({text})"
        self.atom = atom

    def __repr__(self) -> str:
        return f"Sym({self.text})"

    # arithmetic with zero / one folding
    def __add__(self, o):
        if not isinstance(o, Sym) and o == 0:
            return self
        return Sym(f"{self.text} + {_wrap(o)}")

    def __radd__(self, o):
        if not isinstance(o, Sym) and o == 0:
            return self
        return Sym(f"{_wrap(o)} + {self.text}")

    def __sub__(self, o):
        if not isinstance(o, Sym) and o == 0:
            return self
        return Sym(f"{self.text} - {_wrap(o)}")

    def __rsub__(self, o):
        if not isinstance(o, Sym) and o == 0:
            return -self
        return Sym(f"{_wrap(o)} - {self.text}")

    def __mul__(self, o):
        if not isinstance(o, Sym):
            if o == 0:
                return 0.0
            if o == 1:
                return self
            if o == -1:
                return -self
        return Sym(f"{self.text} * {_wrap(o)}")

    def __rmul__(self, o):
        return self.__mul__(o)

    def __truediv__(self, o):
        if not isinstance(o, Sym) and o == 1:
            return self
        return Sym(f"{self.text} / {_wrap(o)}")

    def __rtruediv__(self, o):
        return Sym(f"{_wrap(o)} / {self.text}")

    def __neg__(self):
        return Sym(f"-{self.text}")

    def __pow__(self, o):
        return Sym(f"{self.text}^{_wrap(o)}")

    def __lt__(self, o):
        return Sym(f"{self.text} < {_wrap(o)}")

    def __le__(self, o):
        return Sym(f"{self.text} <= {_wrap(o)}")

    def __gt__(self, o):
        return Sym(f"{self.text} > {_wrap(o)}")

    def __ge__(self, o):
        return Sym(f"{self.text} >= {_wrap(o)}")

    def __and__(self, o):
        return Sym(f"{self.text} && {_wrap(o)}")

    def __or__(self, o):
        return Sym(f"{self.text} || {_wrap(o)}")

    def __bool__(self):
        raise TypeError("a Sym has no truth value: use F.ifelse")


def is_sym(*xs) -> bool:
    return any(isinstance(x, Sym) for x in xs)


def _is_arr(*xs) -> bool:
    return any(isinstance(x, np.ndarray) for x in xs)


class F:
    """Functions that work on floats, numpy arrays (vectorised reference) and `Sym`."""

    @staticmethod
    def _f(name, fn, npfn, *xs):
        if is_sym(*xs):
            return Sym(f"{name}(" + ", ".join(_wrap(x) for x in xs) + ")", atom=True)
        if _is_arr(*xs):
            return npfn(*xs)
        return fn(*xs)

    sqrt = staticmethod(lambda x: F._f("sqrt", math.sqrt, np.sqrt, x))
    sin = staticmethod(lambda x: F._f("sin", math.sin, np.sin, x))
    cos = staticmethod(lambda x: F._f("cos", math.cos, np.cos, x))
    asin = staticmethod(lambda x: F._f("asin", math.asin, np.arcsin, x))
    acos = staticmethod(lambda x: F._f("acos", math.acos, np.arccos, x))
    atan2 = staticmethod(lambda y, x: F._f("atan", math.atan2, np.arctan2, y, x))
    abs = staticmethod(lambda x: F._f("abs", abs, np.abs, x))
    hypot = staticmethod(lambda x, y: F._f("hypot", math.hypot, np.hypot, x, y))
    tanh = staticmethod(lambda x: F._f("tanh", math.tanh, np.tanh, x))
    tan = staticmethod(lambda x: F._f("tan", math.tan, np.tan, x))

    @staticmethod
    def min(a, b):
        return F._f("min", min, np.minimum, a, b)

    @staticmethod
    def max(a, b):
        return F._f("max", max, np.maximum, a, b)

    @staticmethod
    def clamp(x, lo, hi):
        return F._f("clamp", lambda v, a, b: min(max(v, a), b), np.clip, x, lo, hi)

    @staticmethod
    def ifelse(c, a, b):
        if is_sym(c, a, b):
            return Sym(f"ifelse({_wrap(c)}, {_wrap(a)}, {_wrap(b)})", atom=True)
        if _is_arr(c, a, b):
            return np.where(c, a, b)
        return a if c else b

    @staticmethod
    def and_(a, b):
        if is_sym(a, b):
            return Sym(f"{_wrap(a)} && {_wrap(b)}")
        if _is_arr(a, b):
            return np.logical_and(a, b)
        return bool(a) and bool(b)

    @staticmethod
    def or_(a, b):
        if is_sym(a, b):
            return Sym(f"{_wrap(a)} || {_wrap(b)}")
        if _is_arr(a, b):
            return np.logical_or(a, b)
        return bool(a) or bool(b)

    @staticmethod
    def not_(a):
        if is_sym(a):
            return Sym(f"!{_wrap(a)}")
        if _is_arr(a):
            return np.logical_not(a)
        return not bool(a)

    @staticmethod
    def b2f(c):
        """1.0 / 0.0 of a condition."""
        return F.ifelse(c, 1.0, 0.0)


class Code:
    """Collects statements in Sym mode; passes values through in float mode."""

    def __init__(self, emit: bool) -> None:
        self.emit = emit
        self.lines: list[str] = []
        self.names: set[str] = set()

    def let(self, name: str, value):
        if not self.emit:
            return value
        self.lines.append(f"{name} = {_wrap(value) if not isinstance(value, Sym) else value.text}")
        self.names.add(name)
        return Sym(name, atom=True)

    def comment(self, text: str) -> None:
        if self.emit:
            self.lines.append(f"# {text}")

    def assign(self, target: str, value) -> None:
        """An output assignment (no Sym returned)."""
        if self.emit:
            self.lines.append(f"{target} = {_wrap(value) if not isinstance(value, Sym) else value.text}")

    def text(self, indent: int = 8) -> str:
        pad = " " * indent
        return "\n".join(pad + ln for ln in self.lines)
