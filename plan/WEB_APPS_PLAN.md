# Web games

The FMU-based desktop apps (`apps/f16-sim`, `cessna-sim`, `a109-sim`, `car-sim`) as browser games, in `apps/web`. They have nothing to do with the bg-sim editor: no backend, no Python, no Julia at run time. A static file server is enough, and each game also builds into one HTML file that opens from disk and can be mailed around.

## Decisions

| | Decision | Why |
|---|---|---|
| W1 | FMU compiled to WebAssembly with Zig (through `uv`) | The FMU's C sources need no change. Zero imports, 60 KB, about 2 µs per step for the F-16. A 30 s manoeuvre matched the native FMU to 6e-12 m. |
| W2 | three.js WebGLRenderer, TypeScript, Vite, no React | 156 KB gzipped against 635 KB for Babylon. The look comes from hand-written shaders either way. |
| W3 | The simulation runs on the main thread, in a fixed-step accumulator on `requestAnimationFrame` | SharedArrayBuffer needs COOP/COEP headers, which `file://` and a plain server do not give. A step costs microseconds, so no worker is needed. |
| W4 | The Wasm sits in a generated TypeScript module as base64 | The static site and the single file load it the same way, without a fetch. |
| W5 | Everything is procedural: meshes, textures, sound, the world | Keeps the single file small and means no asset pipeline and no licences. |
| W6 | Not bit-for-bit with the desktop apps | The user's call: the games are redesigned, only the flight and vehicle models carry over. |
| W7 | Terrain and shadows are computed in an inline worker | Two seconds of noise must not freeze the page, and an inline worker also works from `file://`. |

## Layout

```
apps/web/
  build_wasm.py        FMU to src/<game>/model.gen.ts (gitignored, regenerate after an FMU changes)
  shim/                the C glue between the FMU and JavaScript
  index.html           landing page
  f16/ cessna/ a109/ cars/   one folder per game, each an index.html
  src/engine/          shared by all: Stage, Sim, gates, camera, overlay, sound, input, effects
  src/island/          the island the aircraft share
  src/<game>/          what is the game's own
  tests/               Vitest (unit, scripted pilots) and Playwright scripts (real keys, screenshots)
```

## Rendering

World (sky, terrain, sea, ground objects) into a multisampled HDR target, half-resolution ray-marched clouds over it, then the near scene (the vehicle and its effects) so that it stays sharp in front of them, then bloom, ACES and a little grading. The sky panorama is shared by the dome, the water and aerial perspective. Quality drops by itself in four tiers when frames run long.

## Running

```
cd apps/web
npm ci
uv run build_wasm.py f16 ../f16-sim/build/f16_sim.fmu    # once per game, needs the FMU built
npm run dev                                              # or: npm run build, then serve dist/
GAME=f16 npm run build:single                            # dist-single/f16/index.html
npx vitest run
node tests/keys.mjs out.png                              # real key presses against the dev server
```

Port 8831 is the dev server the scripts expect (`GAMES_PORT` overrides it). Never 8765.

## Rules the games taught us

- Check every mesh with the signed volume test in `tests/aircraft.test.ts`. Three of the four games shipped inside-out parts from a first draft: a loft's winding depends on which way its sections run, and a mapping with a negative determinant mirrors what it moves.
- A float render target clamps nothing. With MSAA a varying is read outside its triangle where a triangle is edge-on or partly covered, so a value used in `exp`, or as a blend alpha, needs a `clamp` or `centroid`. The bloom now drops any pixel that is not finite and positive, but the source still shows as a wrong pixel.

## Not done

- No landing on the F-16: its FMU has no gear, and touching the ground is a crash.
- Touch controls.
- Device mapping beyond the standard gamepad layout: the desktop apps' per-device configuration did not carry over.
- Real frame rates on a discrete GPU. On the Arc integrated GPU at 1600x900 and top quality the flight games take about 21 ms of GPU time a frame and the cars 14 ms; the automatic quality step was not seen to react in a headless browser.
