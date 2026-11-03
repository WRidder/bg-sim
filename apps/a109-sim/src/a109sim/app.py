"""a109sim: fly the bg-sim A109 helicopter FMU in real time.

    uv run a109sim [--start N] [--config config/devices.toml] [--fmu build/a109_sim.fmu]
    uv run a109sim --list-devices
    uv run a109sim --headless --script smoke         # smoke test: offscreen, the scripted pilot
    uv run a109sim --record out.mp4 --script demo    # deterministic video (or a folder: PNG frames)

One thread. Each frame: read the controls, let the pacer turn the frame time into whole 5 ms FMU
steps (bounded catch-up), interpolate the drawn state between the last two steps, draw.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="a109sim", description="Fly the bg-sim A109 helicopter FMU in real time.")
    p.add_argument("--fmu", type=Path, default=APP / "build" / "a109_sim.fmu")
    p.add_argument("--starts", type=Path, default=APP / "build" / "starts.json")
    p.add_argument("--config", type=Path, default=APP / "config" / "devices.toml")
    p.add_argument("--start", type=int, default=0, help="index of the start condition (0-based)")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--no-joystick", action="store_true")
    p.add_argument("--headless", action="store_true", help="offscreen, the scripted pilot, fixed frames")
    p.add_argument("--seconds", type=float, default=None, help="--headless: sim time of a one-leg script")
    p.add_argument("--record", type=Path, help="render the --script offscreen: an .mp4 (ffmpeg) or a folder of PNGs")
    p.add_argument("--script", default=None, help="the scripted pilot: smoke, circuit, landing, demo")
    p.add_argument("--fps", type=float, default=30.0, help="frame rate of --record / --headless")
    p.add_argument("--size", default="1280x720")
    p.add_argument("--supersample", type=int, default=2, help="--record to .mp4: render this many times larger, then downscale")
    p.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    p.add_argument("--msaa", type=int, default=4, help="multisamples of the window (0: off)")
    p.add_argument("--vsync", type=int, default=1, help="interactive: 1 waits for the display refresh")
    p.add_argument("--quit-after", type=float, default=None, help="interactive: quit after this many seconds (a check)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list_devices:
        from .inputs import list_devices

        return list_devices()
    from panda3d.core import loadPrcFileData

    w, h = (int(v) for v in args.size.lower().split("x"))
    offscreen = args.headless or args.record is not None
    args.out_size = (w, h)
    if args.record is not None and args.record.suffix.lower() == ".mp4":
        w, h = w * args.supersample, h * args.supersample
    loadPrcFileData("", "\n".join([
        f"win-size {w} {h}",
        "window-title a109-sim",
        "window-type offscreen" if offscreen else "window-type onscreen",
        f"framebuffer-multisample {1 if args.msaa else 0}", f"multisamples {args.msaa}",
        "sync-video 0" if offscreen or not args.vsync else "sync-video 1",
        "audio-library-name null",
        "notify-level-gltf error", "notify-level-glgsg warning",
        "show-frame-rate-meter 0",
        "texture-anisotropic-degree 8",
    ]))
    from .game import Game

    game = Game(args)
    try:
        if args.record is not None:
            return game.record(args.record, args.script or "demo", args.fps)
        if args.headless:
            return game.headless(args.seconds, args.script or "smoke", args.fps)
        game.run()
        return 0
    finally:
        game.close_game()


if __name__ == "__main__":
    sys.exit(main())
