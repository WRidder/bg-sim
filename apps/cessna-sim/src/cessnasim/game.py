"""The Panda3D application: window, cameras, input polling, the frame loop, recording."""

from __future__ import annotations

import math
import subprocess
import time
from pathlib import Path

import numpy as np
from direct.showbase.ShowBase import ShowBase
from panda3d.core import ClockObject, Filename, KeyboardButton, PNMImage, Point3, Vec3

from .aircraft import Aircraft
from .core import FLAP_DETENTS, IDX, Simulation, wrap180
from .fmu import OUTPUTS, Start, body_to_world
from .inputs import Joysticks, Keyboard, Mixer, load_config
from .panel import Panel
from .pilot import SCRIPTS, Pilot, Script
from .world import HORIZON, TOWER, World

IX = {n: k for k, n in enumerate(OUTPUTS)}
CHASE_BACK, CHASE_UP, CHASE_TAU = 20.0, 4.0, 0.45
CHASE_AIM = -0.8     # m: the camera aims a little below the aircraft, which then sits above the panel
VIEWS = ("chase", "cockpit", "tower")
HELP = ("F1 help   P pause   R reset   1-9 start   C view (chase, cockpit, tower)   I panel   T turbulence\n"
        "Shift+W wind (off, 10 kt from the west, 15 kt from the north)   Esc quit\n"
        "arrows or W/S, A/D yoke   Q/E or Z/X pedals (nose wheel)   PgUp/PgDn or +/- throttle   M/N mixture\n"
        "F/V flaps down/up   Home/End or [ ] trim nose down/up   B brakes   , . left/right brake\n"
        "H autopilot roll (off, wing leveller, heading hold)   J altitude hold   K/L heading bug -/+ 5 deg")


def _nlerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    if float(np.dot(a, b)) < 0.0:
        b = -b
    q = a + (b - a) * t
    return q / np.linalg.norm(q)


class Game(ShowBase):
    def __init__(self, args):
        ShowBase.__init__(self)
        self.args = args
        self.disable_mouse()
        self.set_background_color(*HORIZON, 1)
        self.camLens.set_near_far(0.2, 60000.0)
        self.camLens.set_fov(65.0)
        starts = Start.load_all(args.starts)
        self.sim = Simulation(args.fmu, starts)
        self.world = World(self.render, self.camera)
        self.aircraft = Aircraft(self.render)
        self.panel = Panel(self.aspect2d, self.getAspectRatio(), line_scale=self.win.get_y_size() / 720.0)
        axes, buttons, kb = load_config(args.config)
        self.joy = Joysticks(axes, buttons, enabled=not (args.no_joystick or args.headless or args.record))
        self.kb = Keyboard(kb)
        self.mixer = Mixer()
        for line in self.joy.describe():
            print(line)
        self.view = "chase"
        self.cam_yaw = 0.0
        self.cam_pitch = 0.0
        self.caption = ""
        self.frames = 0
        self.fps = 0.0
        self.rt = 1.0
        self._rt_win = (time.perf_counter(), 0.0)
        self.recording = False
        self.wind_mode = 0
        self.reset(args.start)
        self._keys()
        self.set_view("chase")

    # ---- input
    def _keys(self):
        self.accept("escape", self.userExit)
        self.accept("p", self.toggle_pause)
        self.accept("r", self.reset)
        for k in range(1, 10):
            self.accept(str(k), self.reset, [k - 1])
        self.accept("c", self.cycle_view)
        self.accept("i", self.toggle_panel)
        self.accept("t", self.toggle_turbulence)
        self.accept("w-repeat", lambda: None)
        self.accept("shift-w", self.cycle_wind)
        self.accept("f", self.sim.flaps, [1])
        self.accept("v", self.sim.flaps, [-1])
        self.accept("h", self.sim.ap_roll_cycle)
        self.accept("j", self.sim.ap_alt_toggle)
        self.accept("k", self.sim.heading_bug, [-5.0])
        self.accept("l", self.sim.heading_bug, [5.0])
        self.accept("f1", self.toggle_help)

    def toggle_help(self):
        self.panel.show_help = not self.panel.show_help

    def toggle_panel(self):
        self.panel.show_panel = not self.panel.show_panel

    def toggle_pause(self):
        self.sim.paused = not self.sim.paused

    def reset(self, index=None):
        if index is not None and index >= len(self.sim.starts):
            return
        self.sim.reset(index)
        u = self.sim.u
        self.kb.throttle = float(u[IDX["throttle"]])
        self.kb.mixture = float(u[IDX["mixture"]])
        self.cam_yaw = self.sim.model["psi_deg"]
        self._apply_wind()

    def cycle_view(self):
        self.set_view(VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)])

    def set_view(self, view: str):
        self.view = view
        if view == "cockpit":
            self.camera.reparent_to(self.aircraft.eye)
            self.camera.set_pos_hpr(0, 0, 0, 0, -6.0, 0)
            self.camLens.set_fov(75.0)
            self.aircraft.root.hide()
        else:
            self.aircraft.root.show()
            self.camera.reparent_to(self.render)
            self.camLens.set_fov(60.0)
        self.camLens.set_near_far(0.2, 60000.0)

    def toggle_turbulence(self):
        self.sim.wind.intensity = 0.0 if self.sim.wind.intensity > 0 else 1.5

    def cycle_wind(self):
        self.wind_mode = (self.wind_mode + 1) % 3
        self._apply_wind()

    def _apply_wind(self):
        # (towards north, towards east, down): 10 kt from the west (a crosswind), 15 kt from the north (a headwind)
        self.sim.wind.steady = {0: (0.0, 0.0, 0.0), 1: (0.0, 5.14, 0.0), 2: (-7.72, 0.0, 0.0)}[self.wind_mode]

    def _held(self) -> dict[str, bool]:
        mw = self.mouseWatcherNode
        if mw is None:
            return {}
        down = mw.is_button_down
        a = KeyboardButton.ascii_key
        shift = down(KeyboardButton.shift())
        return {
            "pull": down(KeyboardButton.down()) or down(a("s")),
            "push": down(KeyboardButton.up()) or (down(a("w")) and not shift),
            "left": down(KeyboardButton.left()) or down(a("a")),
            "right": down(KeyboardButton.right()) or down(a("d")),
            "yaw_left": down(a("q")) or down(a("z")),
            "yaw_right": down(a("e")) or down(a("x")),
            "throttle_up": down(KeyboardButton.page_up()) or down(a("+")) or down(a("=")),
            "throttle_down": down(KeyboardButton.page_down()) or down(a("-")),
            "mixture_rich": down(a("m")),
            "mixture_lean": down(a("n")),
            "trim_down": down(KeyboardButton.home()) or down(a("[")),
            "trim_up": down(KeyboardButton.end()) or down(a("]")),
            "brakes": down(a("b")),
            "brake_l": down(a(",")),
            "brake_r": down(a(".")),
        }

    def _pilot(self, dt: float) -> None:
        held = self._held()
        self.kb.update(held, dt)
        joy, pressed = self.joy.poll()
        for name, act in (("flaps_down", lambda: self.sim.flaps(1)), ("flaps_up", lambda: self.sim.flaps(-1)),
                          ("ap_roll", self.sim.ap_roll_cycle), ("ap_alt", self.sim.ap_alt_toggle)):
            if name in pressed:
                act()
        rate = self.kb.cfg["trim_rate"] * dt
        if held.get("trim_up") or self.joy.held("trim_up"):
            self.sim.trim(rate)
        if held.get("trim_down") or self.joy.held("trim_down"):
            self.sim.trim(-rate)
        c = self.mixer.mix(joy, self.kb, held)
        both = 1.0 if self.joy.held("brakes") else 0.0
        self.sim.set_controls(yoke_pitch=c["pitch"], yoke_roll=c["roll"], pedals=c["yaw"], throttle=c["throttle"],
                              mixture=c["mixture"], brake_l=max(c["brake_l"], both), brake_r=max(c["brake_r"], both))

    # ---- frame
    def frame(self, dt: float, pilot=None, leg=None, t_leg: float = 0.0) -> None:
        sim = self.sim
        if pilot is None:
            self._pilot(dt)
        else:
            v = leg.views[0][1]
            for t0, name in leg.views:
                if t_leg >= t0:
                    v = name
            if v != self.view:
                self.set_view(v)
            self.caption = next((c for t0, t1, c in leg.captions if t0 <= t_leg < t1), "")
        before = sim.model.time
        sim.advance(dt, pilot)
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
        a = sim.alpha()
        y0, y1 = sim.y_prev, m.y
        lerp = y0 + (y1 - y0) * a
        qi = [IX["q_w"], IX["q_x"], IX["q_y"], IX["q_z"]]
        R = body_to_world(*_nlerp(y0[qi], y1[qi], a))
        n, e, h = lerp[IX["north_m"]], lerp[IX["east_m"]], lerp[IX["alt_m"]]
        yd = {k: float(lerp[i]) for k, i in IX.items()}
        for k in ("psi_deg", "phi_deg", "prop_angle"):
            yd[k] = float(y1[IX[k]])
        self.aircraft.update(R, n, e, h, yd, dt)
        w = sim.u[[IDX["wind_n"], IDX["wind_e"]]]
        self.world.update(m.time, (float(w[0]), float(w[1])))
        if self.view == "chase":
            self._chase(dt, n, e, h)
        elif self.view == "tower":
            self._tower(n, e, h)
        u = sim.u
        info = (f"{'REC' if self.recording else 'FPS'} {self.fps:3.0f}   RT {self.rt:4.2f}x   t {m.time:6.1f} s   "
                f"{self.view}   {sim.start.label}" + (f"   behind {sim.pacer.behind}" if sim.pacer.behind else "")
                + ("   turbulence" if sim.wind.intensity > 0 else "")
                + ({0: "", 1: "   wind 270/10", 2: "   wind 360/15"}[self.wind_mode]))
        flaps = int(round(u[IDX["flaps"]]))
        levers = {"flaps": flaps, "trim": float(u[IDX["trim"]]), "throttle": float(u[IDX["throttle"]]),
                  "mixture": float(u[IDX["mixture"]]),
                  "hdg_bug": float(u[IDX["ap_hdg_deg"]]) if round(u[IDX["ap_roll_mode"]]) == 2 else None,
                  "text": (f"FLAPS {FLAP_DETENTS[flaps]:2d} ({m['flap_deg']:4.1f})   TRIM {u[IDX['trim']]:+.2f}\n"
                           f"THR {u[IDX['throttle']] * 100:3.0f}%   MIX {u[IDX['mixture']] * 100:3.0f}%"
                           + ("   BRAKES" if max(u[IDX["brake_l"]], u[IDX["brake_r"]]) > 0.05 else ""))}
        rm, am = round(u[IDX["ap_roll_mode"]]), round(u[IDX["ap_alt_mode"]])
        ap = "AP " + ("OFF" if rm == 0 and am == 0 else
                      " ".join(s for s in ({1: "LVL", 2: f"HDG {u[IDX['ap_hdg_deg']]:03.0f}"}.get(rm, ""),
                                           f"ALT {u[IDX['ap_alt_m']] / 0.3048:5.0f} ft" if am else "") if s))
        warn = []
        if m["stall_flag"] > 0.5 or (m["alpha_deg"] > 15.5 and m["on_ground"] < 0.5):
            warn.append("STALL")
        agl = m["agl_ft"]
        if m["on_ground"] < 0.5 and agl < 400.0 and m["vs_fpm"] < -1500.0:
            warn.append("PULL UP")
        if m["on_ground"] > 0.5 and not sim.on_runway() and m["gs_mps"] > 1.0:
            warn.append("ON THE GRASS")
        if m["rpm"] > 2700.0:
            warn.append("OVERSPEED")
        touch = ""
        if sim.touchdowns:
            td = sim.touchdowns[-1]
            touch = (f"TOUCHDOWN {td.rating}: {-td.vs_fpm:3.0f} fpm, {td.kias:2.0f} KIAS\n"
                     f"{td.distance_m:4.0f} m past the threshold, {abs(td.offset_m):3.1f} m "
                     f"{'right' if td.offset_m > 0 else 'left'} of the centre line")
        self.panel.update(yd, info=info, caption=self.caption, t=m.time, crashed=sim.crash_reason if sim.crashed else "",
                          paused=sim.paused, help_text="F1 help\n" + HELP + "\nstarts:\n" + "\n".join(
                              f"  {k + 1}: {s.label}" for k, s in enumerate(sim.starts)),
                          touch=touch, warn=warn, ap=ap, levers=levers)

    def _chase(self, dt, n, e, h) -> None:
        m = self.sim.model
        psi = m["psi_deg"]
        k = 1.0 - math.exp(-max(dt, 0.0) / CHASE_TAU)
        self.cam_yaw += wrap180(psi - self.cam_yaw) * k
        gamma = math.degrees(math.atan2(m["vs_fpm"] * 0.3048 / 60.0, max(5.0, m["gs_mps"])))
        self.cam_pitch += (0.5 * gamma - self.cam_pitch) * k
        yaw, pit = math.radians(self.cam_yaw), math.radians(self.cam_pitch)
        fwd = Vec3(math.sin(yaw) * math.cos(pit), math.cos(yaw) * math.cos(pit), math.sin(pit))
        target = Point3(e, n, h)
        pos = target - fwd * CHASE_BACK + Vec3(0, 0, CHASE_UP)
        pos.z = max(pos.z, 1.5)
        self.camera.set_pos(pos)
        self.camera.look_at(target + Vec3(0, 0, CHASE_AIM), Vec3(0, 0, 1))

    def _tower(self, n, e, h) -> None:
        cam = Point3(*TOWER)
        target = Point3(e, n, h)
        dist = (target - cam).length()
        self.camera.set_pos(cam)
        self.camera.look_at(target, Vec3(0, 0, 1))
        # zoom: the aircraft about a fifth of the picture's height
        self.camLens.set_fov(max(3.0, min(60.0, math.degrees(2 * math.atan(30.0 / max(dist, 1.0))))))

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

    def _legs(self, script: Script, fps: float, each_frame=None):
        """Fly the script's legs at fixed frames of 1/fps; ``each_frame()`` after each rendered frame."""
        self.sim.pacer.max_steps = 1 << 30      # fixed frame steps: never drop sim time
        results = []
        for leg in script.legs:
            self.reset(leg.start)
            pilot = Pilot(**leg.pilot)
            n = int(round(leg.duration * fps))
            for i in range(n):
                self.frame(1.0 / fps, pilot, leg, self.sim.model.time)
                self.graphicsEngine.render_frame()
                if each_frame is not None:
                    each_frame()
                if self.sim.crashed and each_frame is None:
                    break
            results.append((leg, pilot, {**self.sim.model.snapshot(), "t": self.sim.model.time}, list(self.sim.touchdowns), self.sim.crashed,
                            self.sim.crash_reason))
        return results

    def headless(self, seconds: float | None, script_name: str, fps: float) -> int:
        script = SCRIPTS[script_name]
        if seconds is not None and len(script.legs) == 1:
            script = Script(script.name, [type(script.legs[0])(**{**vars(script.legs[0]), "duration": seconds})])
        t0 = time.perf_counter()
        results = self._legs(script, fps)
        wall = time.perf_counter() - t0
        ok = True
        sim_t = 0.0
        for leg, pilot, y, tds, crashed, reason in results:
            sim_t += y["t"]
            td = (f", touchdown {tds[-1].rating} {-tds[-1].vs_fpm:.0f} fpm at {tds[-1].distance_m:.0f} m"
                  if tds else "")
            print(f"leg from start {leg.start}: phases {pilot.log}; alt {y['alt_m']:.1f} m, KIAS {y['kias']:.0f}, "
                  f"heading {y['psi_deg']:.0f}, north {y['north_m']:.0f} m, east {y['east_m']:.1f} m{td}, "
                  f"crashed {crashed} {reason}")
            ok = ok and not crashed and bool(np.all(np.isfinite(list(y.values()))))
        print(f"headless {script_name}: {sim_t:.1f} s of sim time, {self.sim.steps} FMU steps, {self.frames} frames "
              f"rendered offscreen ({self.win.get_x_size()}x{self.win.get_y_size()}) in {wall:.2f} s wall "
              f"({sim_t / wall:.1f}x real time)")
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1

    def record(self, out: Path, script_name: str, fps: float) -> int:
        script = SCRIPTS[script_name]
        self.recording = True
        w, h = self.win.get_x_size(), self.win.get_y_size()
        out = Path(out)
        proc = None
        if out.suffix.lower() == ".mp4":
            cmd = [self.args.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                   "-r", f"{fps:g}", "-i", "-", "-vf",
                   f"vflip,scale={self.args.out_size[0]}:{self.args.out_size[1]}:flags=area", "-c:v", "libx264",
                   "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            out.mkdir(parents=True, exist_ok=True)
        frame_no = [0]

        def grab():
            if proc is not None:
                tex = self.win.get_screenshot()
                proc.stdin.write(bytes(tex.get_ram_image_as("RGB")))
            else:
                img = PNMImage()
                self.win.get_screenshot(img)
                img.write(Filename.from_os_specific(str(out / f"frame_{frame_no[0]:05d}.png")))
            frame_no[0] += 1

        self.graphicsEngine.render_frame()
        t0 = time.perf_counter()
        results = self._legs(script, fps, grab)
        if proc is not None:
            proc.stdin.close()
            proc.wait()
        for leg, pilot, y, tds, crashed, reason in results:
            print(f"leg from start {leg.start}: phases {pilot.log}; crashed {crashed} {reason}"
                  + (f"; touchdown {tds[-1].rating} {-tds[-1].vs_fpm:.0f} fpm" if tds else ""))
        print(f"recorded {frame_no[0]} frames ({frame_no[0] / fps:.1f} s at {fps:g} fps) to {out} in "
              f"{time.perf_counter() - t0:.1f} s")
        return 0 if proc is None or proc.returncode == 0 else 1

    def close_game(self) -> None:
        try:
            self.sim.close()
        finally:
            self.destroy()
