"""The live telemetry panel: scrolling strip charts of the last seconds, F1 broadcast style.

A dark translucent panel on the left of the screen with one strip chart per channel group (speed,
pedals, steering, aero, g-forces, the drive, the tyre loads), thin bright traces and the current
values. T or the TELEMETRY button toggles it.

Cheap per frame: the samples go into one numpy ring buffer (a fixed sim-time rate, so the charts
scroll with the simulation and stop when it pauses); each chart is one Geom of line strips whose
vertex array is overwritten in one copy per frame (the x positions are fixed, the newest sample at
the right edge), and the value texts change at a few hertz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from direct.gui.DirectGui import DirectButton
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    CardMaker, Geom, GeomLinestrips, GeomNode, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, NodePath,
    TextNode,
    TransparencyAttrib,
)

WINDOW = 15.0          # s of sim time on the charts
RATE = 30.0            # samples per s of sim time
TEXT_RATE = 8.0        # value text updates per s of wall time

PANEL = (0.02, 0.03, 0.05, 0.80)
FRAME = (1.0, 1.0, 1.0, 0.10)
LABEL = (0.62, 0.66, 0.72, 1.0)
# trace colours, bright on the dark panel
C_SPEED = (0.95, 0.95, 0.98, 1.0)
C_THROTTLE = (0.20, 0.95, 0.35, 1.0)
C_BRAKE = (1.00, 0.22, 0.22, 1.0)
C_STEER = (0.30, 0.80, 1.00, 1.0)
C_DOWN = (0.75, 0.45, 1.00, 1.0)
C_DRAG = (1.00, 0.75, 0.20, 1.0)
C_LAT = (1.00, 0.35, 0.80, 1.0)
C_LON = (1.00, 0.85, 0.20, 1.0)
C_RPM = (0.95, 0.95, 0.98, 1.0)
C_POWER = (1.00, 0.60, 0.15, 1.0)
C_TYRE = ((0.30, 0.80, 1.00, 1.0), (1.00, 0.35, 0.80, 1.0), (0.20, 0.95, 0.35, 1.0), (1.00, 0.85, 0.20, 1.0))

Getter = Callable[[dict, dict], float]


@dataclass
class Trace:
    name: str            # short name in the readout
    color: tuple
    get: Getter          # (outputs, controls) -> value
    fmt: str             # readout format of the value


@dataclass
class Chart:
    title: str
    unit: str
    lo: float
    hi: float
    traces: list[Trace]
    auto: bool = False   # widen [lo, hi] to the data in the window (to a round number)
    zero: bool = False   # draw the zero line
    symmetric: bool = False   # auto range symmetric about zero
    lo_now: float = field(init=False, default=0.0)
    hi_now: float = field(init=False, default=0.0)

    def __post_init__(self):
        self.lo_now, self.hi_now = self.lo, self.hi


_FMT = None


def _format() -> GeomVertexFormat:
    """Position and colour as float32 (3 + 4 columns, 28 bytes a row): the layout `draw` writes."""
    global _FMT
    if _FMT is None:
        a = GeomVertexArrayFormat()
        a.add_column("vertex", 3, Geom.NT_float32, Geom.C_point)
        a.add_column("color", 4, Geom.NT_float32, Geom.C_color)
        _FMT = GeomVertexFormat.register_format(GeomVertexFormat(a))
    return _FMT


def nice_ceil(x: float) -> float:
    """The next round number (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 times a power of ten) at or above x."""
    if x <= 0:
        return 1.0
    e = 10.0 ** math.floor(math.log10(x))
    for m in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if m * e >= x - 1e-12:
            return m * e
    return 10.0 * e


def charts_for(outputs: set[str], motors: list[str]) -> list[Chart]:
    """The chart groups the vehicle's FMU outputs allow (aero and the motors only if present)."""
    g = lambda name: (lambda y, c: y.get(name, 0.0))          # noqa: E731
    charts = [
        Chart("SPEED", "km/h", 0.0, 100.0, [Trace("", C_SPEED, lambda y, c: abs(y.get("kmh", 0.0)), "{:4.0f}")], auto=True),
        Chart("THROTTLE / BRAKE", "%", 0.0, 100.0, [
            Trace("THR", C_THROTTLE, lambda y, c: 100.0 * c.get("throttle", 0.0), "{:3.0f}"),
            Trace("BRK", C_BRAKE, lambda y, c: 100.0 * c.get("brake", 0.0), "{:3.0f}")]),
        Chart("STEERING", "deg", -20.0, 20.0, [
            Trace("", C_STEER, lambda y, c: math.degrees(0.5 * (y.get("steer_fl", 0.0) + y.get("steer_fr", 0.0))),
                  "{:+5.1f}")], auto=True, zero=True, symmetric=True),
    ]
    if "downforce" in outputs:
        charts.append(Chart("AERO", "kN", 0.0, 1.0, [
            Trace("DOWN", C_DOWN, lambda y, c: y.get("downforce", 0.0) / 1000.0, "{:4.2f}"),
            Trace("DRAG", C_DRAG, lambda y, c: y.get("drag", 0.0) / 1000.0, "{:4.2f}")], auto=True))
    charts.append(Chart("G-FORCE", "g", -2.0, 2.0, [
        Trace("LAT", C_LAT, g("ay_g"), "{:+4.2f}"), Trace("LON", C_LON, g("ax_g"), "{:+4.2f}")], auto=True, zero=True,
        symmetric=True))
    if motors:
        m0 = motors[-1]
        charts.append(Chart("MOTOR", "krpm", 0.0, 10.0, [
            Trace("RPM", C_RPM, lambda y, c: y.get(f"motor_{m0}_rpm", 0.0) / 1000.0, "{:4.1f}")], auto=True))
        charts.append(Chart("POWER", "kW", -50.0, 100.0, [
            Trace("", C_POWER, lambda y, c: sum(y.get(f"motor_{a}_power", 0.0) for a in motors) / 1000.0, "{:+4.0f}")],
            auto=True, zero=True))
    tyres = [w for w in ("fl", "fr", "rl", "rr") if f"{w}_fz" in outputs]
    if tyres:
        charts.append(Chart("TYRE Fz", "kN", 0.0, 3.0, [
            Trace(w.upper(), C_TYRE[k], g_kn(f"{w}_fz"), "{:3.1f}") for k, w in enumerate(tyres)], auto=True))
    return charts


def g_kn(name: str) -> Getter:
    return lambda y, c: y.get(name, 0.0) / 1000.0


class History:
    """A ring buffer of `rows` channels, `n` samples at `rate` per second of sim time."""

    def __init__(self, rows: int, n: int, rate: float):
        self.n, self.dt = n, 1.0 / rate
        self.buf = np.full((rows, n), np.nan, dtype=np.float64)
        self.count = 0                 # samples taken since the last clear
        self.t_next = 0.0

    def clear(self) -> None:
        self.buf[:] = np.nan
        self.count = 0
        self.t_next = 0.0

    def sample(self, t: float, values: Callable[[], list[float]]) -> int:
        """Record `values()` at every sample instant up to t not yet recorded (the latest values, so
        called after every 5 ms FMU step they are at most a step old); returns the number recorded. A time
        before the last sample (a reset) clears the buffer first."""
        if t + 1e-9 < self.t_next - self.dt:
            self.clear()
        if t + 1e-9 < self.t_next:
            return 0
        vals = np.asarray(values(), dtype=np.float64)
        k = 0
        while self.t_next <= t + 1e-9 and k < self.n:
            self.buf[:, self.count % self.n] = vals
            self.count += 1
            self.t_next += self.dt
            k += 1
        if self.t_next <= t:                                 # a jump longer than the window
            self.t_next = t + self.dt
        return k

    def window(self) -> np.ndarray:
        """The samples in time order (oldest first, the newest last); NaN before the first."""
        h = self.count % self.n
        if self.count >= self.n:
            return np.concatenate([self.buf[:, h:], self.buf[:, :h]], axis=1)
        pad = np.full((self.buf.shape[0], self.n - self.count), np.nan)
        return np.concatenate([pad, self.buf[:, :self.count]], axis=1)


class Telemetry:
    """The panel. `sample` after every FMU step (Simulation.on_step), `draw` once per frame."""

    def __init__(self, aspect2d: NodePath, aspect: float, outputs: set[str], motors: list[str], line_scale: float = 1.0,
                 visible: bool = True):
        self.charts = charts_for(outputs, motors)
        self.n = int(round(WINDOW * RATE))
        self.traces = [t for ch in self.charts for t in ch.traces]
        self.history = History(len(self.traces), self.n, RATE)
        self.last_text = -1.0
        self.ar = aspect
        self.root = aspect2d.attach_new_node("telemetry")
        self.panel = self.root.attach_new_node("panel")
        # geometry of the panel (aspect2d units): left edge, width, top, chart pitch
        x0, w = -aspect + 0.03, 0.70
        top, bottom = 0.74, -0.62
        pitch = (top - bottom - 0.02) / len(self.charts)
        cm = CardMaker("bg")
        cm.set_frame(x0, x0 + w, bottom, top + 0.04)
        bg = self.panel.attach_new_node(cm.generate())
        bg.set_color(*PANEL)
        bg.set_transparency(TransparencyAttrib.M_alpha)
        self.boxes = []
        self.texts: list[OnscreenText] = []
        self.values: list[list[OnscreenText]] = []
        self.scale_texts: list[OnscreenText] = []
        self.geoms: list[GeomVertexData] = []
        self.thick = 1.6 * line_scale
        for k, ch in enumerate(self.charts):
            yt = top - k * pitch
            # plot box: below the title row
            bx0, bx1 = x0 + 0.015, x0 + w - 0.015
            by1, by0 = yt - 0.045, yt - pitch + 0.012
            self.boxes.append((bx0, bx1, by0, by1))
            self._frame(bx0, bx1, by0, by1)
            self.texts.append(self._text(ch.title, bx0, yt - 0.03, 0.03, LABEL, TextNode.A_left))
            row = []
            xr = bx1
            for tr in reversed(ch.traces):
                t = self._text("", xr, yt - 0.03, 0.032, tr.color, TextNode.A_right)
                row.insert(0, t)
                xr -= 0.0175 * (len(tr.name) + len(tr.fmt.format(-0.0)) + 2)        # the readout width
            self.values.append(row)
            self.scale_texts.append(self._text("", bx0 + 0.005, by1 - 0.022, 0.022, LABEL, TextNode.A_left))
            self.geoms.append(self._strips(f"chart{k}", ch, bx0, bx1))
        self.button = DirectButton(text="TELEMETRY  [T]", scale=0.032, pos=(x0 + w - 0.13, 0, top + 0.075),
                                   text_fg=(0.95, 0.95, 0.98, 1), frameColor=(0.10, 0.12, 0.16, 0.85),
                                   pad=(0.35, 0.25), relief=1, command=self.toggle, parent=self.root)
        self.visible = visible          # the user's choice (T, the button)
        self.suppressed = False         # hidden while the help text covers it
        self._apply()

    # ---- construction
    def _text(self, s, x, y, scale, color, align) -> OnscreenText:
        return OnscreenText(text=s, pos=(x, y), scale=scale, fg=color, align=align, parent=self.panel, mayChange=True)

    def _frame(self, x0, x1, y0, y1):
        from panda3d.core import LineSegs

        ls = LineSegs("frame")
        ls.set_thickness(1.0)
        ls.set_color(*FRAME)
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            ls.move_to(a[0], 0, a[1])
            ls.draw_to(b[0], 0, b[1])
        for q in (0.25, 0.5, 0.75):                            # time grid: 3.75 s apart for 15 s
            x = x0 + (x1 - x0) * q
            ls.move_to(x, 0, y0)
            ls.draw_to(x, 0, y1)
        np_ = self.panel.attach_new_node(ls.create())
        np_.set_transparency(TransparencyAttrib.M_alpha)

    def _strips(self, name, ch: Chart, x0, x1) -> GeomVertexData:
        """One vertex block of n points per trace (+ 2 for the zero line), as line strips."""
        nt = len(ch.traces)
        rows = nt * self.n + 2
        vdata = GeomVertexData(name, _format(), Geom.UH_dynamic)
        vdata.unclean_set_num_rows(rows)
        strips = GeomLinestrips(Geom.UH_static)
        for k in range(nt):
            strips.add_consecutive_vertices(k * self.n, self.n)
            strips.close_primitive()
        strips.add_consecutive_vertices(nt * self.n, 2)
        strips.close_primitive()
        geom = Geom(vdata)
        geom.add_primitive(strips)
        node = GeomNode(name)
        node.add_geom(geom)
        np_ = self.panel.attach_new_node(node)
        np_.set_render_mode_thickness(self.thick)
        np_.set_transparency(TransparencyAttrib.M_alpha)
        np_.set_antialias(0)
        # the fixed part of the array: x (oldest left), z = 0, colours; y written per frame
        arr = np.zeros((rows, 7), dtype=np.float32)
        xs = np.linspace(x0, x1, self.n, dtype=np.float32)
        for k, tr in enumerate(ch.traces):
            arr[k * self.n:(k + 1) * self.n, 0] = xs
            arr[k * self.n:(k + 1) * self.n, 3:7] = tr.color
        arr[-2:, 0] = (x0, x1)
        arr[-2:, 3:7] = (1.0, 1.0, 1.0, 0.25 if ch.zero else 0.0)
        ch._arr = arr                                         # noqa: SLF001 - the chart's vertex scratch
        return vdata

    # ---- runtime
    @property
    def shown(self) -> bool:
        return self.visible and not self.suppressed

    def _apply(self) -> None:
        if self.shown:
            self.panel.show()
        else:
            self.panel.hide()
        if self.suppressed:
            self.button.hide()
        else:
            self.button.show()

    def toggle(self) -> None:
        self.visible = not self.visible
        self._apply()

    def suppress(self, flag: bool) -> None:
        self.suppressed = flag
        self._apply()

    def clear(self) -> None:
        self.history.clear()

    def sample(self, t: float, y: dict, controls: dict) -> None:
        self.history.sample(t, lambda: [tr.get(y, controls) for tr in self.traces])

    def draw(self, t: float) -> None:
        """Redraw the traces; the value texts change at TEXT_RATE per second of `t`."""
        if not self.shown:
            return
        data = self.history.window()
        row = 0
        text_now = not (0.0 <= t - self.last_text < 1.0 / TEXT_RATE)       # also after a reset
        if text_now:
            self.last_text = t
        for k, ch in enumerate(self.charts):
            nt = len(ch.traces)
            d = data[row:row + nt]
            row += nt
            if ch.auto and np.isfinite(d).any():
                lo = min(ch.lo, float(np.nanmin(d)))
                hi = max(ch.hi, float(np.nanmax(d)))
                if ch.symmetric:
                    m = nice_ceil(max(-lo, hi))
                    lo, hi = -m, m
                else:
                    hi = nice_ceil(hi) if hi > 0 else hi
                    lo = -nice_ceil(-lo) if lo < 0 else lo
                ch.lo_now, ch.hi_now = lo, hi
            bx0, bx1, by0, by1 = self.boxes[k]
            span = max(ch.hi_now - ch.lo_now, 1e-9)
            last = np.nan_to_num(d[:, -1])
            # NaN (not yet sampled) sits at the oldest real value, so the trace starts flat
            filled = d.copy()
            for i in range(nt):
                r = filled[i]
                ok = np.isfinite(r)
                if ok.any():
                    r[~ok] = r[ok][0]
                else:
                    r[:] = 0.0
            z = by0 + (np.clip(filled, ch.lo_now, ch.hi_now) - ch.lo_now) / span * (by1 - by0)
            arr = ch._arr                                     # noqa: SLF001
            arr[:nt * self.n, 2] = z.reshape(-1)
            zero = by0 + (0.0 - ch.lo_now) / span * (by1 - by0)
            arr[-2:, 2] = min(max(zero, by0), by1)
            self.geoms[k].modify_array(0).modify_handle().copy_data_from(arr.tobytes())
            if text_now:
                for tr, txt, v in zip(ch.traces, self.values[k], last):
                    txt.setText((tr.name + " " if tr.name else "") + tr.fmt.format(v))
                self.scale_texts[k].setText(f"{fmt_scale(ch.hi_now)} {ch.unit}")


def fmt_scale(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 10 or v == int(v) else f"{v:g}"
