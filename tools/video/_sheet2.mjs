// contact sheet of scan-*.jpg: node _sheet2.mjs <dir> [pattern]
import { chromium } from "./lib.mjs";
import { readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
const d = process.argv[2]; const re = new RegExp(process.argv[3] ?? "scan-");
const names = readdirSync(d).filter((n) => re.test(n));
writeFileSync(d + "/sheet.html", `<body style="margin:0;background:#222;color:#fff;display:grid;grid-template-columns:repeat(3,540px);gap:4px">${names.map((n) => `<div>${n}<img style="width:540px;height:450px;object-fit:contain" src="${pathToFileURL(path.join(d, n)).href}"></div>`).join("")}</body>`);
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1640, height: 470 * Math.ceil(names.length / 3) } });
await p.goto(pathToFileURL(d + "/sheet.html").href); await p.waitForTimeout(700);
await p.screenshot({ path: path.join(d, "..", "..", "_scan.png") }); await b.close();
