/**
 * remark-math treats `$$...$$` on a single line as inline math; display math needs the
 * delimiters on lines of their own. People write `$$E=mc^2$$` as a paragraph of its own, so
 * such a line is rewritten to the block form before rendering (code fences are left alone).
 */
export function normalizeDisplayMath(text: string): string {
  let fence: string | null = null;
  return text
    .split("\n")
    .map((line) => {
      const marker = /^\s*(`{3,}|~{3,})/.exec(line)?.[1];
      if (marker !== undefined) {
        if (fence === null) {
          fence = marker[0] ?? null;
        } else if (marker[0] === fence) {
          fence = null;
        }
        return line;
      }
      if (fence !== null) {
        return line;
      }
      const single = /^(\s*)\$\$(?!\$)(.+?)\$\$\s*$/.exec(line);
      return single === null ? line : `${single[1]}$$\n${single[2]}\n${single[1]}$$`;
    })
    .join("\n");
}
