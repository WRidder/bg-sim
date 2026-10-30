// Parse every math span of the example docs with the KaTeX of web/node_modules.
// stdin: JSON [{file, line, tex, display}]; stdout: JSON [{file, line, tex, error}] (empty = all fine).
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "../../web/package.json"));
const katex = require("katex");

const spans = JSON.parse(readFileSync(0, "utf8"));
const errors = [];
for (const span of spans) {
  try {
    katex.renderToString(span.tex, { displayMode: span.display, throwOnError: true });
  } catch (error) {
    errors.push({ file: span.file, line: span.line, tex: span.tex, error: String(error.message ?? error) });
  }
}
process.stdout.write(JSON.stringify(errors));
