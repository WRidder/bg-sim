"""The telemetry panel's data side: the ring buffer, the scales and the chart groups."""

from __future__ import annotations

import numpy as np
import pytest

from carsim.telemetry import History, charts_for, nice_ceil


def test_history_samples_at_a_fixed_sim_time_rate():
    h = History(2, 5, rate=10.0)
    v = [0.0]
    t = 0.0
    for _ in range(3):                       # frames of 0.25 s: 2 or 3 samples each
        h.sample(t, lambda: [v[0], -v[0]])
        v[0] += 1.0
        t += 0.25
    w = h.window()
    assert w.shape == (2, 5)
    assert h.count == 6                      # t = 0, 0.1, 0.2 | 0.3, 0.4, 0.5 (held at the frame's value)
    assert w[0].tolist() == [1.0, 1.0, 2.0, 2.0, 2.0]     # the last 5 of 0 | 1 1 | 2 2 2
    assert np.allclose(w[1], -w[0])


def test_history_window_is_oldest_first_and_padded():
    h = History(1, 4, rate=1.0)
    h.sample(0.0, lambda: [7.0])
    w = h.window()[0]
    assert np.isnan(w[:3]).all() and w[3] == 7.0
    for k in range(1, 6):
        h.sample(float(k), lambda k=k: [float(k)])
    assert h.window()[0].tolist() == [2.0, 3.0, 4.0, 5.0]


def test_history_clears_when_time_goes_back():
    h = History(1, 4, rate=1.0)
    for k in range(4):
        h.sample(float(k), lambda k=k: [float(k)])
    h.sample(0.0, lambda: [9.0])             # a reset: sim time starts again
    w = h.window()[0]
    assert h.count == 1 and w[-1] == 9.0 and np.isnan(w[:3]).all()


def test_history_pause_adds_nothing():
    h = History(1, 4, rate=1.0)
    h.sample(2.0, lambda: [1.0])
    n = h.count
    assert h.sample(2.0, lambda: [5.0]) == 0 and h.count == n


@pytest.mark.parametrize(("x", "y"), [(0.7, 0.8), (1.0, 1.0), (1.2, 1.5), (260.0, 300.0), (9.1, 10.0), (0.0, 1.0)])
def test_nice_ceil(x, y):
    assert nice_ceil(x) == pytest.approx(y)


def test_chart_groups_follow_the_outputs():
    base = {"kmh", "ax_g", "ay_g", "steer_fl", "steer_fr", "fl_fz", "fr_fz", "rl_fz", "rr_fz"}
    titles = [c.title for c in charts_for(base | {"downforce", "drag", "motor_r_rpm"}, ["r"])]
    assert titles == ["SPEED", "THROTTLE / BRAKE", "STEERING", "AERO", "G-FORCE", "MOTOR", "POWER", "TYRE Fz"]
    assert "AERO" not in [c.title for c in charts_for(base, ["r"])]       # an FMU without the aero outputs
    aero = next(c for c in charts_for(base | {"downforce", "drag"}, ["r"]) if c.title == "AERO")
    y = {"downforce": 4200.0, "drag": 1500.0}
    assert [t.get(y, {}) for t in aero.traces] == [pytest.approx(4.2), pytest.approx(1.5)]
    power = next(c for c in charts_for(base, ["f", "r"]) if c.title == "POWER")
    assert power.traces[0].get({"motor_f_power": 2.0e4, "motor_r_power": 3.0e4}, {}) == pytest.approx(50.0)
