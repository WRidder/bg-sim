# Browser games

Island Sortie (F-16), Short Final (Cessna), Island Lift (A109) and Apex & Dust (race car and buggy).

The bg-sim FMU apps as web games: the flight or vehicle model compiled to WebAssembly, the world drawn with three.js, no backend. A static file server is enough, and each game also builds into one HTML file that opens from disk.

```
npm ci
uv run build_wasm.py f16 ../f16-sim/build/f16_sim.fmu
uv run build_wasm.py cessna ../cessna-sim/build/cessna_sim.fmu
uv run build_wasm.py a109 ../a109-sim/build/a109_sim.fmu
uv run build_wasm.py cars ../car-sim/build/racecar_sim.fmu racecar.gen.ts
uv run build_wasm.py cars ../car-sim/build/buggy_sim.fmu buggy.gen.ts
npm run dev -- --host 127.0.0.1 --port 8831
```

Then open http://127.0.0.1:8831/.

- `npm run build` writes a static site to `dist/`.
- `GAME=f16 npm run build:single` writes one self-contained file to `dist-single/f16/index.html`. Also for `cessna`, `a109` and `cars`.
- `npx vitest run` runs the unit tests and the scripted pilots.
- `node tests/keys.mjs out.png` flies with real key presses against the dev server.
- `node tests/cessna-keys.mjs`, `tests/a109-keys.mjs` and `tests/cars-keys.mjs` do the same for the other games.

The design and its reasons are in `plan/WEB_APPS_PLAN.md`.
