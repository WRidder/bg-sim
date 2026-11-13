// The games as single HTML files that open from disk: node build_single.mjs [f16|cessna|a109|cars ...]
// With no name, all four, into a fresh dist-single/: dist-single/<game>.html. The microduck demo has
// no single-file build (README.md, "Single file: not supported").
import { rmSync } from "node:fs";
import { resolve } from "node:path";
import { build } from "vite";

const GAMES = ["f16", "cessna", "a109", "cars"];
const asked = process.argv.slice(2);
const unknown = asked.filter((name) => !GAMES.includes(name));
if (unknown.length > 0) {
  console.error(`unknown game(s) ${unknown.join(", ")}: ${GAMES.join(", ")}`);
  process.exit(1);
}
if (asked.length === 0) {
  rmSync(resolve(import.meta.dirname, "dist-single"), { recursive: true, force: true });
}
for (const game of asked.length > 0 ? asked : GAMES) {
  process.env.GAME = game;
  await build({ root: import.meta.dirname, mode: "single" });
}
