/**
 * Models write math as `\(a\)` and `\[a\]` as readily as `$a$`; the Markdown stack knows only
 * the dollars. Code stays as it is, and so does math that is already in dollars.
 */

const PROTECTED = /(^|\n)(```|~~~)[\s\S]*?(?:\n\2[^\n]*|$)|\$\$[\s\S]*?\$\$|`[^`\n]*`/g;

function convert(text: string): string {
  return text
    .replace(/(?<!\\)\\\[([\s\S]+?)\\\]/g, (_, body: string) => `\n$$\n${body.trim()}\n$$\n`)
    .replace(/(?<!\\)\\\(([\s\S]+?)\\\)/g, (_, body: string) => `$${body.trim()}$`);
}

export function normalizeChatMath(text: string): string {
  let result = "";
  let last = 0;
  for (const match of text.matchAll(PROTECTED)) {
    result += convert(text.slice(last, match.index)) + match[0];
    last = match.index + match[0].length;
  }
  return result + convert(text.slice(last));
}
