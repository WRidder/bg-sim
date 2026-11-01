"""The Panda3D application: window, cameras, input polling, the frame loop, recording."""

from __future__ import annotations

import math
import subprocess
import time
from pathlib import Path

import numpy as np
from direct.showbase.ShowBase import ShowBase
from panda3d.core import ClockObject, Filename, KeyboardButton, PNMImage, Point2, Point3, Vec3

from .aircraft import Aircraft
from .core import Simulation
from .fmu import OUTPUTS, Settings, Start, body_to_ned
from .hud import Hud
from .inputs import Joysticks, Keyboard, load_config
from .scripts import SCRIPTS, wrap180
from .world import HORIZON, World

IX = {n: k for k, n in enumerate(OUTPUTS)}
CHASE_BACK, CHASE_UP, CHASE_TAU = 26.0, 6.0, 0.35
HELP = ("P pause   R reset   1-9 start   C view   G ring course   T turbulence   F1 help   Esc quit\n"
        "arrows or W/S, A/D stick   Q/E or Z/X pedals   PgUp/PgDn or +/- throttle\n"
        "L limiter, V velocity-vector roll, Y yaw damper: on/off (restarts the flight)")


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
        self.camLens.set_near_far(1.0, 100000.0)
        self.camLens.set_fov(65.0)
        starts = Start.load_all(args.starts)
        self.sim = Simulation(args.fmu, starts, Settings())
        self.sim.reset(args.start)
        self.world = World(self.render, self.camera)
        self.aircraft = Aircraft(self.render)
        self.hud = Hud(self.aspect2d, self.camLens.get_vfov(), line_scale=self.win.get_y_size() / 720.0)
        maps, kb = load_config(args.config)
        self.joy = Joysticks(maps, enabled=not (args.no_joystick or args.headless or args.record))
        self.kb = Keyboard(kb)
        self.kb.throttle = self.sim.start.thtl0
        self.view = "chase"
        self.cam_yaw = self.sim.model["psi_deg"]
        self.cam_pitch = 0.0
        self.caption = ""
        self.frames = 0
        self.fps = 0.0
        self.rt = 1.0
        self._rt_win = (time.perf_counter(), 0.0)
        self.recording = False
        if args.rings:
            self.sim.toggle_rings()
            self.world.set_rings(self.sim.rings)
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
        self.accept("g", self.toggle_rings)
        self.accept("t", self.toggle_turbulence)
        self.accept("l", self.toggle_switch, ["limiter"])
        self.accept("v", self.toggle_switch, ["vv_roll"])
        self.accept("y", self.toggle_switch, ["yaw_damper"])
        self.accept("f1", self.toggle_help)

    def toggle_help(self):
        self.hud.show_help = not self.hud.show_help

    def toggle_pause(self):
        self.sim.paused = not self.sim.paused

    def reset(self, index=None):
        if index is not None and index >= len(self.sim.starts):
            return
        self.sim.reset(index)
        self.kb.throttle = self.sim.start.thtl0
        self.cam_yaw = self.sim.model["psi_deg"]
        if self.sim.rings:
            self.world.set_rings(self.sim.rings)

    def toggle_view(self):
        self.set_view("cockpit" if self.view == "chase" else "chase")

    def set_view(self, view: str):
        self.view = view
        if view == "cockpit":
            self.camera.reparent_to(self.aircraft.eye)
            self.camera.set_pos_hpr(0, 0, 0, 0, 0, 0)
            self.camLens.set_fov(70.0)
            self.aircraft.root.hide()          # a clean HUD view: no fuselage in front of the eye
        else:
            self.aircraft.root.show()
            self.camera.reparent_to(self.render)
            self.camLens.set_fov(65.0)
        self.camLens.set_near_far(1.0, 100000.0)

    def toggle_rings(self):
        self.sim.toggle_rings()
        self.world.set_rings(self.sim.rings)

    def toggle_turbulence(self):
        self.sim.wind.intensity = 0.0 if self.sim.wind.intensity > 0 else 2.5

    def toggle_switch(self, name):
        sw = self.sim.settings.switches
        sw[name] = 0.0 if sw[name] > 0.5 else 1.0
        self.reset()   # the law switches are FMU parameters: set before initialisation

    def _held(self) -> dict[str, bool]:
        mw = self.mouseWatcherNode
        if mw is None:
            return {}
        down = mw.is_button_down
        a = KeyboardButton.ascii_key
        return {
            "pull": down(KeyboardButton.down()) or down(a("s")),
            "push": down(KeyboardButton.up()) or down(a("w")),
            "left": down(KeyboardButton.left()) or down(a("a")),
            "right": down(KeyboardButton.right()) or down(a("d")),
            "yaw_left": down(a("q")) or down(a("z")),
            "yaw_right": down(a("e")) or down(a("x")),
            "throttle_up": down(KeyboardButton.page_up()) or down(a("+")) or down(a("=")),
            "throttle_down": down(KeyboardButton.page_down()) or down(a("-")),
        }

    def _pilot(self, dt: float) -> None:
        self.kb.update(self._held(), dt)
        joy = self.joy.poll()
        self.sim.set_controls(joy.get("pitch", self.kb.pitch), joy.get("roll", self.kb.roll),
                              joy.get("yaw", self.kb.yaw), joy.get("throttle", self.kb.throttle))

    # ---- frame
    def frame(self, dt: float, script=None) -> None:
        sim = self.sim
        if script is None:
            self._pilot(dt)
            control = None
        else:
            thr0 = sim.start.thtl0

            def control(t):
                p, r, y, thr = script.controls(t, thr0, sim.model["phi_deg"])
                sim.set_controls(p, r, y, thr)
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
        a = sim.alpha()
        y0, y1 = sim.y_prev, m.y
        lerp = y0 + (y1 - y0) * a
        q = _nlerp(y0[[IX["q_w"], IX["q_x"], IX["q_y"], IX["q_z"]]], y1[[IX["q_w"], IX["q_x"], IX["q_y"], IX["q_z"]]], a)
        R = body_to_ned(*q)
        n, e, h = lerp[IX["north_m"]], lerp[IX["east_m"]], lerp[IX["alt_m"]]
        yd = {k: float(lerp[i]) for k, i in IX.items()}
        yd["psi_deg"] = float(y1[IX["psi_deg"]])
        yd["phi_deg"] = float(y1[IX["phi_deg"]])
        self.aircraft.update(R, n, e, h, yd)
        self.world.update(m.time, sim.rings)
        if self.view == "chase":
            self._chase(dt, n, e, h, R)
        y = m.snapshot()
        y["throttle"] = float(sim.u[3])
        y["agl"] = sim.agl()
        info = (f"{'REC' if self.recording else 'FPS'} {self.fps:3.0f}   RT {self.rt:4.2f}x   t {m.time:6.1f} s   "
                f"{self.view}   {sim.start.label}" + (f"   behind {sim.pacer.behind}" if sim.pacer.behind else "")
                + ("   turbulence" if sim.wind.intensity > 0 else ""))
        off = [k for k, v in sim.settings.switches.items() if v < 0.5]
        if off:
            info += "   OFF: " + ", ".join(off)
        self.hud.k = 1.0 / math.tan(math.radians(self.camLens.get_vfov()) / 2.0)
        self.hud.update(y, cockpit=self.view == "cockpit", info=info, ring=self._ring_text(), caption=self.caption,
                        t=m.time, crashed=sim.crashed, paused=sim.paused, help_text=self._help(),
                        ring_cue=self._ring_cue())

    def _chase(self, dt, n, e, h, R) -> None:
        psi = self.sim.model["psi_deg"]
        gamma = self.sim.model["gamma_deg"]
        k = 1.0 - math.exp(-max(dt, 0.0) / CHASE_TAU)
        self.cam_yaw += wrap180(psi - self.cam_yaw) * k
        self.cam_pitch += (0.6 * gamma - self.cam_pitch) * k
        yaw, pit = math.radians(self.cam_yaw), math.radians(self.cam_pitch)
        fwd = Vec3(math.sin(yaw) * math.cos(pit), math.cos(yaw) * math.cos(pit), math.sin(pit))
        target = Point3(e, n, h)
        pos = target - fwd * CHASE_BACK + Vec3(0, 0, CHASE_UP)
        from . import terrain
        ground = float(terrain.height(pos.y, pos.x)) + 3.0
        if pos.z < ground:
            pos.z = ground
        self.camera.set_pos(pos)
        self.camera.look_at(target + Vec3(0, 0, 2.0), Vec3(0, 0, 1))

    def _ring_text(self) -> str:
        sim = self.sim
        if not sim.rings:
            return ""
        hits = sum(r.hit for r in sim.rings)
        done = sum(r.passed for r in sim.rings)
        if sim.ring_done is not None:
            return f"COURSE DONE  {sim.ring_done:5.1f} s   {hits}/{len(sim.rings)} rings"
        return f"RING {done + 1}/{len(sim.rings)}   hits {hits}   {sim.ring_time:5.1f} s"

    def _ring_cue(self):
        r = self.sim.next_ring()
        if r is None:
            return None
        p = self.cam.get_relative_point(self.render, Point3(r.east, r.north, r.alt))
        p2 = Point2()
        ar = self.getAspectRatio()
        if p.y > 0 and self.camLens.project(p, p2):
            return (p2.x * ar, p2.y)
        # behind or off screen: on the edge, in its direction
        ang = math.atan2(p.z, p.x)
        return (0.85 * ar * math.cos(ang), 0.85 * math.sin(ang))

    def _help(self) -> str:
        starts = "\n".join(f"  {k + 1}: {s.label}" for k, s in enumerate(self.sim.starts))
        return "F1 help\n" + HELP + "\nstart conditions:\n" + starts

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

    def headless(self, seconds: float, script_name: str, fps: float) -> int:
        script = SCRIPTS[script_name]
        self.sim.pacer.max_steps = 1 << 30      # fixed frame steps: never drop sim time
        self.reset(script.start)
        n = int(round(seconds * fps))
        t0 = time.perf_counter()
        rendered = 0
        for _ in range(n):
            self.frame(1.0 / fps, script)
            self.graphicsEngine.render_frame()
            rendered += 1
            if self.sim.crashed:
                break
        wall = time.perf_counter() - t0
        m = self.sim.model
        ok = (not self.sim.crashed) and bool(np.all(np.isfinite(m.y))) and m.time >= seconds - 1e-6
        print(f"headless {script_name}: {m.time:.2f} s of sim time, {self.sim.steps} FMU steps, {rendered} frames "
              f"rendered offscreen ({self.win.get_x_size()}x{self.win.get_y_size()}) in {wall:.2f} s wall "
              f"({m.time / wall:.1f}x real time); alt {m['alt_m']:.0f} m, phi {m['phi_deg']:.1f} deg, "
              f"CAS {m['cas_mps'] / 0.514444:.0f} kt, crashed {self.sim.crashed}")
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1

    def record(self, out: Path, script_name: str, fps: float) -> int:
        script = SCRIPTS[script_name]
        self.sim.pacer.max_steps = 1 << 30
        self.recording = True
        self.reset(script.start)
        w, h = self.win.get_x_size(), self.win.get_y_size()
        n = int(round(script.duration * fps))
        out = Path(out)
        proc = None
        if out.suffix.lower() == ".mp4":
            cmd = [self.args.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                   "-r", f"{fps:g}", "-i", "-", "-vf", f"vflip,scale={self.args.out_size[0]}:{self.args.out_size[1]}:flags=area", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        else:
            out.mkdir(parents=True, exist_ok=True)
        self.graphicsEngine.render_frame()
        t0 = time.perf_counter()
        for i in range(n):
            self.frame(1.0 / fps, script)
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
        print(f"recorded {n} frames ({n / fps:.1f} s at {fps:g} fps) to {out} in {time.perf_counter() - t0:.1f} s; "
              f"crashed {self.sim.crashed}")
        return 0 if proc is None or proc.returncode == 0 else 1

    def close_game(self) -> None:
        try:
            self.sim.close()
        finally:
            self.destroy()
