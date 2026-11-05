import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

/** Every folder with an index.html is one page: the landing page and one per game. */
const pages = (): Record<string, string> => {
  const root = import.meta.dirname;
  const found: Record<string, string> = { index: resolve(root, "index.html") };
  for (const name of readdirSync(root)) {
    const page = resolve(root, name, "index.html");
    if (statSync(resolve(root, name)).isDirectory() && !["node_modules", "dist", "dist-single", "lookdev"].includes(name)) {
      try {
        readFileSync(page);
        found[name] = page;
      } catch {
        // not a page
      }
    }
  }
  return found;
};

/** Puts the bundle inside the HTML: a page opened from file:// cannot load modules or fetch. */
const inlineEverything = (): Plugin => ({
  name: "bgsim-inline",
  enforce: "post",
  generateBundle(_, bundle) {
    for (const html of Object.values(bundle)) {
      if (html.type !== "asset" || !html.fileName.endsWith(".html")) {
        continue;
      }
      let text = String(html.source);
      for (const [name, chunk] of Object.entries(bundle)) {
        if (chunk.type === "chunk") {
          const code = chunk.code.replaceAll("</script", "<\\/script");
          text = text.replace(
            new RegExp(`<script[^>]*src="[^"]*${name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}"[^>]*></script>`),
            () => `<script type="module">${code}</script>`,
          );
          delete bundle[name];
        } else if (name.endsWith(".css")) {
          text = text.replace(
            new RegExp(`<link[^>]*href="[^"]*${name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}"[^>]*>`),
            () => `<style>${String(chunk.source)}</style>`,
          );
          delete bundle[name];
        }
      }
      html.source = text;
    }
  },
});

export default defineConfig(({ mode }) => {
  const single = mode === "single";
  return {
    base: "./",
    plugins: single ? [inlineEverything()] : [],
    build: {
      target: "es2022",
      chunkSizeWarningLimit: 4000,
      outDir: single ? "dist-single" : "dist",
      assetsInlineLimit: single ? 100_000_000 : 4096,
      cssCodeSplit: !single,
      rollupOptions: {
        input: single ? { [process.env.GAME ?? "f16"]: resolve(import.meta.dirname, process.env.GAME ?? "f16", "index.html") } : pages(),
        output: single ? { inlineDynamicImports: true } : {},
      },
    },
  };
});
