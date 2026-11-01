"""The Panda3D application: window, cameras, input polling, the frame loop, recording."""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np
from direct.showbase.ShowBase import ShowBase
from panda3d.core import ClockObject, Filename, KeyboardButton, PNMImage, Point3, Vec3

from .core import IDX as INPUT_IDX, Simulation
from .fmu import CORNERS, Start
from .hud import Hud, fmt_lap
from .inputs import Joysticks, Keyboard, Mixer, load_config
from .scripts import SCRIPTS, Driver, Path as DrivePath, hills_loop
from .telemetry import Telemetry
from .vehicle import Car
from .world import HORIZON, World

VIEWS = ("chase", "cockpit", "tv")
CHASE = {"racecar": (7.5, 2.4, 0.25), "buggy": (8.5, 3.2, 0.35)}     # back, up (m), yaw lag (s)
STEER = {"racecar": (2.80, math.radians(20.0)), "buggy": (2.70, math.radians(30.0))}   # wheelbase, full lock
HELP = ("P pause   R reset   1-9 start   C view (chase, cockpit, track side)   T telemetry   F1 help   Esc quit\n"
        "arrows or W/A/S/D: steer, accelerator, brake   space handbrake   V forward/reverse (at rest)")


def load_starts(path: Path, vehicle: str) -> list[Start]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Start(**rec) for rec in data[vehicle]]


def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class Game(ShowBase):
    def __init__(self, args):
        ShowBase.__init__(self)
        self.args = args
        self.vehicle = args.vehicle
        self.disable_mouse()
        self.set_background_color(*HORIZON, 1)
        self.camLens.set_near_far(0.1, 8000.0)
        self.camLens.set_fov(70.0)
        starts = load_starts(args.starts, self.vehicle)
        self.sim = Simulation(self.vehicle, args.fmu, starts)
        self.sim.reset(args.start)
        self.world = World(self.render, self.camera, self.vehicle)
        self.car = Car(self.render, self.vehicle, self.sim.model.index)
        self.hud = Hud(self.aspect2d, self.getAspectRatio(), line_scale=self.win.get_y_size() / 720.0)
        self.telemetry = Telemetry(self.aspect2d, self.getAspectRatio(), set(self.sim.model.outputs),
                                   self.sim.model.motors, line_scale=self.win.get_y_size() / 720.0,
                                   visible=not getattr(args, "no_telemetry", False))
        self.sim.on_step = self._telemetry_sample
        maps, buttons, kb = load_config(args.config)
        self.joy = Joysticks(maps, buttons, enabled=not (args.no_joystick or args.headless or args.record))
        self.kb = Keyboard(kb)
        self.mixer = Mixer()
        for line in self.joy.describe():
            print(line)
        self.controls = {"steer": 0.0, "throttle": 0.0, "brake": 0.0, "handbrake": 0.0}
        self._btn_prev: dict[str, bool] = {}
        self.view = "chase"
        self.cam_yaw = self.sim.start.yaw0
        self.tv = None
        self.caption = ""
        self.frames = 0
        self.fps = 0.0
        self.rt = 1.0
        self._rt_win = (time.perf_counter(), 0.0)
        self.recording = False
        self._keys()
        self.set_view("chase")

    # ---- input
    def _keys(self):
        self.accept("escape", self.userExit)
        self.accept("p", self.toggle_pause)
        self.accept("r", self.reset)
        for k in range(1, 10):
            self.accept(str(k), self.reset, [k - 1])
        self.accept("c", self.toggle_view)
        self.accept("v", self.toggle_reverse)
        self.accept("f1", self.toggle_help)
        self.accept("t", self.telemetry.toggle)

    def _telemetry_sample(self) -> None:
        """After each FMU step: the telemetry takes a sample when its next instant has come (the
        model's outputs and the pedal inputs of that step)."""
        u = self.sim.u
        self.telemetry.sample(self.sim.model.time, self.sim.model,
                              {"throttle": float(u[INPUT_IDX["throttle"]]), "brake": float(u[INPUT_IDX["brake"]])})

    def toggle_help(self):
        self.hud.show_help = not self.hud.show_help
        self.telemetry.suppress(self.hud.show_help)        # the help text runs down over the panel

    def toggle_pause(self):
        self.sim.paused = not self.sim.paused

    def toggle_reverse(self):
        self.sim.toggle_reverse()

    def reset(self, index=None):
        if index is not None and index >= len(self.sim.starts):
            return
        self.sim.reset(index)
        self.telemetry.clear()
        self.kb.steer = self.kb.throttle = self.kb.brake = 0.0
        self.cam_yaw = self.sim.start.yaw0

    def toggle_view(self):
        self.set_view(VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)])

    def set_view(self, view: str):
        self.view = view
        if view == "cockpit":
            self.camera.reparent_to(self.car.eye)
            self.camera.set_pos_hpr(0, 0, 0, 0, -4.0, 0)
            self.camLens.set_fov(80.0)
        else:
            self.camera.reparent_to(self.render)
            self.camLens.set_fov(70.0 if view == "chase" else 40.0)
        self.camLens.set_near_far(0.05 if view == "cockpit" else 0.2, 8000.0)

    def _held(self) -> dict[str, bool]:
        mw = self.mouseWatcherNode
        if mw is None:
            return {}
        down = mw.is_button_down
        a = KeyboardButton.ascii_key
        return {
            "left": down(KeyboardButton.left()) or down(a("a")),
            "right": down(KeyboardButton.right()) or down(a("d")),
            "accel": down(KeyboardButton.up()) or down(a("w")),
            "brake": down(KeyboardButton.down()) or down(a("s")),
            "handbrake": down(KeyboardButton.space()),
        }

    def _drive(self, dt: float) -> None:
        held = self._held()
        self.kb.update(held, dt)
        steer, throttle, brake = self.mixer.mix(self.joy.poll(), self.kb, held)
        buttons = self.joy.buttons()
        hand = 1.0 if (held.get("handbrake") or buttons.get("handbrake")) else 0.0
        rev = buttons.get("reverse", False)
        if rev and not self._btn_prev.get("reverse", False):
            self.sim.toggle_reverse()
        self._btn_prev["reverse"] = rev
        self.controls = {"steer": steer, "throttle": throttle, "brake": brake, "handbrake": hand}
        self.sim.set_controls(steer, throttle, brake, hand)

    # ---- frame
    def frame(self, dt: float, script=None, driver=None) -> None:
        sim = self.sim
        if script is None:
            self._drive(dt)
            control = None
        else:
            m = sim.model

            def control(t):
                if t < script.hold:
                    c = (0.0, 0.0, 1.0)
                else:
                    c = driver.controls(m["chassis_px"], m["chassis_py"], m["yaw"], m["speed"], m["ay_g"], m["beta"])
                self.controls = {"steer": c[0], "throttle": c[1], "brake": c[2], "handbrake": 0.0}
                sim.set_controls(*c)
            v = script.view(sim.model.time)
            if v != self.view:
                self.set_view(v)
            self.caption = script.caption(sim.model.time)
        before = sim.model.time
        sim.advance(dt, control)
        self._measure(dt, sim.model.time - before)
        self.draw(dt)

    def _measure(self, dt: float, sim_dt: float) -> None:
        self.frames += 1
        t0, acc = self._rt_win
        acc += sim_dt
        now = time.perf_counter()
        if self.recording:
            self.fps, self.rt = 1.0 / max(dt, 1e-9), 1.0
        elif now - t0 >= 1.0:
            self.rt = acc / (now - t0)
            self._rt_win = (now, 0.0)
            self.fps = ClockObject.get_global_clock().get_average_frame_rate()
            return
        self._rt_win = (t0, acc)

    def draw(self, dt: float) -> None:
        sim, m = self.sim, self.sim.model
        R, p = self.car.update(sim.y_prev, m.y, sim.alpha())
        if self.view == "chase":
            self._chase(dt, R, p)
        elif self.view == "tv":
            self._tv(p)
        y = m.snapshot()
        self.telemetry.draw(m.time)
        info = (f"{'REC' if self.recording else 'FPS'} {self.fps:3.0f}   RT {self.rt:4.2f}x   t {m.time:6.1f} s   "
                f"{self.vehicle}   {self.view}   {sim.start.label}" + (f"   behind {sim.pacer.behind}" if sim.pacer.behind else ""))
        lap = ""
        if sim.laps is not None:
            lt = sim.laps
            lap = (f"LAP {len(lt.laps) + 1}   {fmt_lap(lt.current(m.time))}\n"
                   f"last {fmt_lap(lt.last)}   best {fmt_lap(lt.best)}")
        surface = "  ".join(f"{c.upper()} {s}" for c, s in zip(CORNERS, sim.surfaces))
        self.hud.update(y, motors=m.motors, controls=self.controls, reverse=sim.reverse, info=info, lap=lap,
                        surface=surface, caption=self.caption, warning=sim.warning,
                        crashed=sim.crash_reason if sim.crashed else "", paused=sim.paused, help_text=self._help(),
                        t=m.time)

    def _ground(self, x: float, y: float) -> float:
        return float(self.world.hills.height(x, y)) if self.vehicle == "buggy" else 0.0

    def _chase(self, dt, R, p) -> None:
        back, up, tau = CHASE[self.vehicle]
        fwd = R[:, 0]
        yaw = math.atan2(fwd[1], fwd[0])
        k =1.0 - math.exp(-max(dt, 0.0) / tau)
        self.cam_yaw += wrap(yaw - self.cam_yaw) * k
        d = Vec3(math.cos(self.cam_yaw), math.sin(self.cam_yaw), 0.0)
        target = Point3(p[0], p[1], p[2])
        pos = target - d * back + Vec3(0, 0, up)
        ground = self._ground(pos.x, pos.y) + 0.8
        if pos.z < ground:
            pos.z = ground
        self.camera.set_pos(pos)
        self.camera.look_at(target + Vec3(0, 0, 0.6), Vec3(0, 0, 1))

    def _tv(self, p) -> None:
        pts = self.world.tv_points
        if self.tv is None or math.dist(self.tv[:2], p[:2]) > 140.0:
            self.tv = min(pts, key=lambda q: math.dist(q[:2], p[:2])) if pts else (p[0] + 30, p[1] + 30, p[2] + 6)
        self.camera.set_pos(*self.tv)
        self.camera.look_at(Point3(p[0], p[1], p[2] + 0.3), Vec3(0, 0, 1))
        dist = math.dist(self.tv, p)
        self.camLens.set_fov(max(12.0, min(55.0, math.degrees(2 * math.atan(7.0 / max(dist, 1.0))))))

    def _help(self) -> str:
        starts = "\n".join(f"  {k + 1}: {s.label}" for k, s in enumerate(self.sim.starts))
        return "F1 help\n" + HELP + "\nstarts:\n" + starts

    # ---- modes
    def run(self) -> None:
        def task(t):
            dt = ClockObject.get_global_clock().get_dt()
            self.frame(min(dt, 0.25))
            return t.cont

        self.taskMgr.add(task, "frame")
        t0 = time.perf_counter()

        def summary():
            wall = time.perf_counter() - t0
            m = self.sim.model
            print(f"interactive: {self.frames} frames in {wall:.1f} s ({self.frames / wall:.0f} fps), sim time "
                  f"{m.time:.2f} s ({m.time / wall:.3f}x real time), {self.sim.steps} FMU steps, catch-up drops "
                  f"{self.sim.pacer.behind}")

        self.exitFunc = summary
        if self.args.quit_after:
            self.taskMgr.doMethodLater(self.args.quit_after, lambda t: self.userExit(), "quit")
        ShowBase.run(self)

    def _driver(self, script) -> Driver:
        pts = self.world.track.p if self.vehicle == "racecar" else hills_loop()
        wb, lock = STEER[self.vehicle]
        return Driver(DrivePath(pts), script.v_max, script.ay_max, wheelbase=wb, steer_max=lock)

    def headless(self, seconds: float, script_name: str, fps: float) -> int:
        script = SCRIPTS[script_name]
        driver = self._driver(script)
        self.sim.pacer.max_steps = 1 << 30      # fixed frame steps: never drop sim time
        self.reset(script.start)
        n = int(round(seconds * fps))
        t0 = time.perf_counter()
        rendered = 0
        for _ in range(n):
            self.frame(1.0 / fps, script, driver)
            self.graphicsEngine.render_frame()
            rendered += 1
            if self.sim.crashed:
                break
        wall = time.perf_counter() - t0
        m = self.sim.model
        ok = (not self.sim.crashed) and bool(np.all(np.isfinite(m.y))) and m.time >= seconds - 1e-6
        laps = self.sim.laps.laps if self.sim.laps else []
        print(f"headless {script_name} ({self.vehicle}): {m.time:.2f} s of sim time, {self.sim.steps} FMU steps, "
              f"{rendered} frames rendered offscreen ({self.win.get_x_size()}x{self.win.get_y_size()}) in {wall:.2f} s "
              f"wall ({m.time / wall:.1f}x real time); {m['kmh']:.0f} km/h at ({m['chassis_px']:.0f}, "
              f"{m['chassis_py']:.0f}) m, SOC {m['soc'] * 100:.1f} %, laps {[round(x, 2) for x in laps]}, "
              f"crashed {self.sim.crashed}")
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1

    def record(self, out: Path, script_name: str, fps: float, seconds: float | None = None) -> int:
        script = SCRIPTS[script_name]
        driver = self._driver(script)
        self.sim.pacer.max_steps = 1 << 30
        self.recording = True
        self.reset(script.start)
        w, h = self.win.get_x_size(), self.win.get_y_size()
        n = int(round((seconds or script.duration) * fps))
        out = Path(out)
        proc = None
        if out.suffix.lower() == ".mp4":
            cmd = [self.args.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                   "-r", f"{fps:g}", "-i", "-", "-vf",
                   f"vflip,scale={self.args.out_size[0]}:{self.args.out_size[1]}:flags=area", "-c:v", "libx264",
                   "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            out.mkdir(parents=True, exist_ok=True)
        self.graphicsEngine.render_frame()
        t0 = time.perf_counter()
        for i in range(n):
            self.frame(1.0 / fps, script, driver)
            self.graphicsEngine.render_frame()
            if proc is not None:
                tex = self.win.get_screenshot()
                proc.stdin.write(bytes(tex.get_ram_image_as("RGB")))
            else:
                img = PNMImage()
                self.win.get_screenshot(img)
                img.write(Filename.from_os_specific(str(out / f"frame_{i:05d}.png")))
        if proc is not None:
            proc.stdin.close()
            proc.wait()
        laps = self.sim.laps.laps if self.sim.laps else []
        print(f"recorded {n} frames ({n / fps:.1f} s at {fps:g} fps) to {out} in {time.perf_counter() - t0:.1f} s; "
              f"laps {[round(x, 2) for x in laps]}, crashed {self.sim.crashed}")
        return 0 if proc is None or proc.returncode == 0 else 1

    def close_game(self) -> None:
        try:
            self.sim.close()
        finally:
            self.destroy()
