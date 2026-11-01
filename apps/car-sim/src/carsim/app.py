"""carsim: drive the bg-sim race car or buggy FMU in real time.

    uv run carsim [--vehicle racecar|buggy] [--start N] [--config config/devices.toml]
    uv run carsim --list-devices
    uv run carsim --headless --script smoke --seconds 10      # smoke test: offscreen, scripted driver
    uv run carsim --record out.mp4 --script demo              # deterministic video (or a folder: PNG frames)

One thread. Each frame: read the controls, let the pacer turn the frame time into whole 5 ms FMU
steps (bounded catch-up), set the friction under each wheel before each step, interpolate the
drawn state between the last two steps, draw.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="carsim", description="Drive the bg-sim race car or buggy FMU in real time.")
    p.add_argument("--vehicle", choices=("racecar", "buggy"), default=None,
                   help="racecar (the race track) or buggy (the hills); default: the script's, else racecar")
    p.add_argument("--fmu", type=Path, default=None, help="default build/<vehicle>_sim.fmu")
    p.add_argument("--starts", type=Path, default=APP / "build" / "starts.json")
    p.add_argument("--config", type=Path, default=APP / "config" / "devices.toml")
    p.add_argument("--start", type=int, default=0, help="index of the start (0-based)")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--no-joystick", action="store_true")
    p.add_argument("--headless", action="store_true", help="offscreen, scripted, as fast as possible")
    p.add_argument("--seconds", type=float, default=None, help="sim time of --headless (default the script's) "
                   "or of --record (default the script's duration)")
    p.add_argument("--record", type=Path, help="render the --script offscreen: an .mp4 (ffmpeg) or a folder of PNGs")
    p.add_argument("--script", default=None, help="scripted driver: smoke, smoke-buggy, demo, demo-buggy")
    p.add_argument("--fps", type=float, default=60.0, help="frame rate of --record / --headless")
    p.add_argument("--size", default="1280x720")
    p.add_argument("--supersample", type=int, default=2, help="--record to .mp4: render this many times larger, then downscale")
    p.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    p.add_argument("--msaa", type=int, default=4, help="multisamples of the window (0: off)")
    p.add_argument("--vsync", type=int, default=1, help="interactive: 1 waits for the display refresh")
    p.add_argument("--quit-after", type=float, default=None, help="interactive: quit after this many seconds (a check)")
    args = p.parse_args(argv)
    from .scripts import SCRIPTS

    if args.script is not None and args.script not in SCRIPTS:
        p.error(f"unknown script {args.script!r}: {', '.join(SCRIPTS)}")
    if args.vehicle is None:
        args.vehicle = SCRIPTS[args.script].vehicle if args.script else "racecar"
    if args.script is not None and SCRIPTS[args.script].vehicle != args.vehicle:
        p.error(f"the script {args.script!r} drives the {SCRIPTS[args.script].vehicle}")
    if args.fmu is None:
        args.fmu = APP / "build" / f"{args.vehicle}_sim.fmu"
    return args


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
        "window-title car-sim",
        "window-type offscreen" if offscreen else "window-type onscreen",
        f"framebuffer-multisample {1 if args.msaa else 0}", f"multisamples {args.msaa}",
        "sync-video 0" if offscreen or not args.vsync else "sync-video 1",
        "audio-library-name null",
        "notify-level-gltf error", "notify-level-glgsg warning",
        "show-frame-rate-meter 0",
        "texture-anisotropic-degree 8",
    ]))
    from .game import Game
    from .scripts import SCRIPTS

    game = Game(args)
    try:
        default = "smoke" if args.vehicle == "racecar" else "smoke-buggy"
        if args.record is not None:
            return game.record(args.record, args.script or ("demo" if args.vehicle == "racecar" else "demo-buggy"),
                               args.fps, args.seconds)
        if args.headless:
            name = args.script or default
            return game.headless(args.seconds or SCRIPTS[name].duration, name, args.fps)
        game.run()
        return 0
    finally:
        game.close_game()


if __name__ == "__main__":
    sys.exit(main())
