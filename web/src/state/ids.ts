/**
 * Stable ids and unique instance names for the model document (plan 3.3).
 *
 * Ids are short and readable (`n1`, `c3`, `a1`) and never shown. Instance names
 * are path segments: they must stay identifiers because every signal id starts
 * with the instance path.
 */

/** The numeric suffix of `id` when it has `prefix`, else null. */
export function idNumber(id: string, prefix: string): number | null {
  if (!id.startsWith(prefix)) {
    return null;
  }
  const rest = id.slice(prefix.length);
  return /^\d+$/.test(rest) ? Number(rest) : null;
}

/** The next free `<prefix><number>` id, scanning the existing ids. */
export function nextId(prefix: string, existing: Iterable<string>): string {
  let highest = 0;
  for (const id of existing) {
    const value = idNumber(id, prefix);
    if (value !== null && value > highest) {
      highest = value;
    }
  }
  return `${prefix}${highest + 1}`;
}

/**
 * A unique instance name. A trailing number is incremented (`Motor1` ->
 * `Motor2`); otherwise the smallest free `2`, `3`, ... suffix is appended
 * (`Gain` -> `Gain2`). Names never collide, so copy/paste cannot produce two
 * nodes with the same path.
 */
export function uniqueName(base: string, existing: Iterable<string>): string {
  const taken = new Set(existing);
  if (!taken.has(base)) {
    return base;
  }
  const match = /^(.*?)(\d+)$/.exec(base);
  const stem = match?.[1] && match[1].length > 0 ? match[1] : base;
  let value = match ? Number(match[2]) + 1 : 2;
  let candidate = `${stem}${value}`;
  while (taken.has(candidate)) {
    value += 1;
    candidate = `${stem}${value}`;
  }
  return candidate;
}

/** Instance names already used by the diagram. */
export function usedNames(names: Iterable<string>): Set<string> {
  return new Set(names);
}
