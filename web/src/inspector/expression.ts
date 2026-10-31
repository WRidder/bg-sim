/**
 * Constant-expression syntax for the inspector (plan 3.3 `params`/`starts`,
 * plan 5.2.4).
 *
 * Values are expression strings, not numbers: they may refer to constants,
 * other parameters and whitelisted pure functions. The worker is authoritative
 * about names and types (E001–E003); this small parser exists so the inspector
 * can catch syntax errors while the user types and can evaluate a
 * pure-literal expression to check the catalog's min/max bounds. It never
 * guesses a value for an expression that mentions a name.
 */

export interface NumberLiteral {
  kind: "number";
  value: number;
}

export interface IdentifierExpression {
  kind: "identifier";
  name: string;
}

export interface CallExpression {
  kind: "call";
  name: string;
  args: ExpressionNode[];
}

export interface UnaryExpression {
  kind: "unary";
  operator: "+" | "-" | "!";
  operand: ExpressionNode;
}

export type BinaryOperator =
  | "+"
  | "-"
  | "*"
  | "/"
  | "^"
  | "<"
  | ">"
  | "<="
  | ">="
  | "=="
  | "!="
  | "&&"
  | "||";

export interface BinaryExpression {
  kind: "binary";
  operator: BinaryOperator;
  left: ExpressionNode;
  right: ExpressionNode;
}

export type ExpressionNode =
  | NumberLiteral
  | IdentifierExpression
  | CallExpression
  | UnaryExpression
  | BinaryExpression;

export type ParseResult =
  | { ok: true; ast: ExpressionNode }
  | { ok: false; message: string };

class ExpressionSyntaxError extends Error {}

type TokenKind = "number" | "identifier" | "operator" | "lparen" | "rparen" | "comma" | "end";

interface Token {
  kind: TokenKind;
  text: string;
  value?: number;
}

const NUMBER = /^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/;
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*/;

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;
  while (index < source.length) {
    const char = source[index] ?? "";
    if (/\s/.test(char)) {
      index += 1;
      continue;
    }
    if (char === "=") {
      // `==` is an operator; a single `=` is an equation, not an expression.
      if (source[index + 1] === "=") {
        tokens.push({ kind: "operator", text: "==" });
        index += 2;
        continue;
      }
      throw new ExpressionSyntaxError("Use an expression, not an equation (remove '=').");
    }
    if (char === "~") {
      throw new ExpressionSyntaxError("Use an expression, not an equation (remove '~').");
    }
    if (char === "(" || char === ")" || char === ",") {
      tokens.push({
        kind: char === "(" ? "lparen" : char === ")" ? "rparen" : "comma",
        text: char,
      });
      index += 1;
      continue;
    }
    const pair = source.slice(index, index + 2);
    if (["<=", ">=", "==", "!=", "&&", "||"].includes(pair)) {
      tokens.push({ kind: "operator", text: pair });
      index += 2;
      continue;
    }
    if ("+-*/^<>!".includes(char)) {
      tokens.push({ kind: "operator", text: char });
      index += 1;
      continue;
    }
    const rest = source.slice(index);
    const numberMatch = NUMBER.exec(rest);
    if (numberMatch !== null) {
      const text = numberMatch[0];
      tokens.push({ kind: "number", text, value: Number(text) });
      index += text.length;
      continue;
    }
    const identifierMatch = IDENTIFIER.exec(rest);
    if (identifierMatch !== null) {
      const text = identifierMatch[0];
      tokens.push({ kind: "identifier", text });
      index += text.length;
      continue;
    }
    throw new ExpressionSyntaxError(`Unexpected character "${char}".`);
  }
  tokens.push({ kind: "end", text: "the end of the expression" });
  return tokens;
}

class Parser {
  private index = 0;

  constructor(private readonly tokens: readonly Token[]) {}

  parse(): ExpressionNode {
    const expression = this.or();
    const next = this.peek();
    if (next.kind !== "end") {
      throw new ExpressionSyntaxError(`Unexpected "${next.text}" after the expression.`);
    }
    return expression;
  }

  private or(): ExpressionNode {
    let left = this.and();
    for (;;) {
      const token = this.peek();
      if (token.kind === "operator" && token.text === "||") {
        this.take();
        left = { kind: "binary", operator: "||", left, right: this.and() };
      } else {
        return left;
      }
    }
  }

  private and(): ExpressionNode {
    let left = this.comparison();
    for (;;) {
      const token = this.peek();
      if (token.kind === "operator" && token.text === "&&") {
        this.take();
        left = { kind: "binary", operator: "&&", left, right: this.comparison() };
      } else {
        return left;
      }
    }
  }

  private comparison(): ExpressionNode {
    let left = this.additive();
    for (;;) {
      const token = this.peek();
      if (
        token.kind === "operator" &&
        (token.text === "<" ||
          token.text === ">" ||
          token.text === "<=" ||
          token.text === ">=" ||
          token.text === "==" ||
          token.text === "!=")
      ) {
        this.take();
        left = {
          kind: "binary",
          operator: token.text as BinaryOperator,
          left,
          right: this.additive(),
        };
      } else {
        return left;
      }
    }
  }

  private peek(): Token {
    return this.tokens[this.index] ?? { kind: "end", text: "the end of the expression" };
  }

  private take(): Token {
    const token = this.peek();
    this.index += 1;
    return token;
  }

  private additive(): ExpressionNode {
    let left = this.multiplicative();
    for (;;) {
      const token = this.peek();
      if (token.kind === "operator" && (token.text === "+" || token.text === "-")) {
        this.take();
        const right = this.multiplicative();
        left = { kind: "binary", operator: token.text, left, right };
      } else {
        return left;
      }
    }
  }

  private multiplicative(): ExpressionNode {
    let left = this.unary();
    for (;;) {
      const token = this.peek();
      if (token.kind === "operator" && (token.text === "*" || token.text === "/")) {
        this.take();
        const right = this.unary();
        left = { kind: "binary", operator: token.text, left, right };
      } else {
        return left;
      }
    }
  }

  private unary(): ExpressionNode {
    const token = this.peek();
    if (
      token.kind === "operator" &&
      (token.text === "+" || token.text === "-" || token.text === "!")
    ) {
      this.take();
      return {
        kind: "unary",
        operator: token.text as UnaryExpression["operator"],
        operand: this.unary(),
      };
    }
    return this.power();
  }

  private power(): ExpressionNode {
    const base = this.primary();
    const token = this.peek();
    if (token.kind === "operator" && token.text === "^") {
      this.take();
      // The exponent may carry a sign (`2^-3`) and is right-associative.
      return { kind: "binary", operator: "^", left: base, right: this.unary() };
    }
    return base;
  }

  private primary(): ExpressionNode {
    const token = this.take();
    if (token.kind === "number") {
      return { kind: "number", value: token.value ?? Number.NaN };
    }
    if (token.kind === "identifier") {
      if (this.peek().kind !== "lparen") {
        return { kind: "identifier", name: token.text };
      }
      this.take();
      const args: ExpressionNode[] = [];
      if (this.peek().kind === "rparen") {
        this.take();
        return { kind: "call", name: token.text, args };
      }
      for (;;) {
        args.push(this.or());
        const next = this.peek();
        if (next.kind === "comma") {
          this.take();
          continue;
        }
        if (next.kind === "rparen") {
          this.take();
          return { kind: "call", name: token.text, args };
        }
        throw new ExpressionSyntaxError(
          next.kind === "end"
            ? `The call to ${token.text} is missing its closing ")".`
            : `Expected "," or ")" in the call to ${token.text}, but found "${next.text}".`,
        );
      }
    }
    if (token.kind === "lparen") {
      const expression = this.or();
      const next = this.take();
      if (next.kind !== "rparen") {
        throw new ExpressionSyntaxError(
          next.kind === "end"
            ? 'The group is missing its closing ")".'
            : `Expected ")" to close the group, but found "${next.text}".`,
        );
      }
      return expression;
    }
    if (token.kind === "end") {
      throw new ExpressionSyntaxError("The expression is incomplete.");
    }
    throw new ExpressionSyntaxError(
      `Expected a number, a name or "(", but found "${token.text}".`,
    );
  }
}

/** Parse one constant expression; the message is ready to show in the UI. */
export function parseExpression(source: string): ParseResult {
  if (source.trim().length === 0) {
    return { ok: false, message: "Enter a value." };
  }
  try {
    return { ok: true, ast: new Parser(tokenize(source)).parse() };
  } catch (error) {
    if (error instanceof ExpressionSyntaxError) {
      return { ok: false, message: error.message };
    }
    throw error;
  }
}

/**
 * The numeric value of a pure-literal expression, or null when the expression
 * names anything (a constant, parameter, `t`, a function) and only the worker
 * can resolve it. `pi` is the one name that has a fixed numeric meaning.
 */
export function evaluateLiteral(node: ExpressionNode): number | null {
  switch (node.kind) {
    case "number":
      return node.value;
    case "identifier":
      return node.name === "pi" ? Math.PI : null;
    case "call":
      return null;
    case "unary": {
      if (node.operator === "!") {
        return null;
      }
      const value = evaluateLiteral(node.operand);
      if (value === null) {
        return null;
      }
      return node.operator === "-" ? -value : value;
    }
    case "binary": {
      const left = evaluateLiteral(node.left);
      const right = evaluateLiteral(node.right);
      if (left === null || right === null) {
        return null;
      }
      switch (node.operator) {
        case "+":
          return left + right;
        case "-":
          return left - right;
        case "*":
          return left * right;
        case "/":
          return left / right;
        case "^":
          return left ** right;
        default:
          return null;
      }
    }
    default:
      return null;
  }
}

/** Convenience for callers that only have the text. */
export function literalValue(source: string): number | null {
  const parsed = parseExpression(source);
  return parsed.ok ? evaluateLiteral(parsed.ast) : null;
}

// ---------------------------------------------------------------------------
// Global parameters (spec "Global parameters"): evaluation with named values,
// the names an expression reads, and whole-identifier renaming.
// ---------------------------------------------------------------------------

export type ExpressionValue = number | boolean;

export type EvaluationResult =
  | { ok: true; value: ExpressionValue }
  | { ok: false; message: string; name?: string };

class EvaluationError extends Error {
  constructor(
    message: string,
    readonly name_: string | undefined = undefined,
  ) {
    super(message);
  }
}

function num(value: ExpressionValue, what: string): number {
  if (typeof value !== "number") {
    throw new EvaluationError(`${what} needs a number, not a Bool.`);
  }
  return value;
}

/**
 * The pure functions of the constant folder (Julia `_fold_call`), so the
 * browser computes exactly what the compiler will. Anything else (`ddt`,
 * `previous`, vectors) is not a constant.
 */
const PURE_FUNCTIONS: Record<string, (args: number[]) => number> = {
  abs: ([a = Number.NaN]) => Math.abs(a),
  sign: ([a = Number.NaN]) => Math.sign(a),
  min: (args) => Math.min(...args),
  max: (args) => Math.max(...args),
  clamp: ([x = Number.NaN, lo = Number.NaN, hi = Number.NaN]) => Math.min(Math.max(x, lo), hi),
  floor: ([a = Number.NaN]) => Math.floor(a),
  ceil: ([a = Number.NaN]) => Math.ceil(a),
  // Julia rounds half to even.
  round: ([a = Number.NaN]) => {
    const r = Math.round(a);
    return Math.abs(a % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
  },
  sqrt: ([a = Number.NaN]) => {
    if (a < 0) {
      throw new EvaluationError(`sqrt of a negative number (${a}).`);
    }
    return Math.sqrt(a);
  },
  exp: ([a = Number.NaN]) => Math.exp(a),
  log: ([a = Number.NaN]) => {
    if (a < 0) {
      throw new EvaluationError(`log of a negative number (${a}).`);
    }
    return Math.log(a);
  },
  log10: ([a = Number.NaN]) => {
    if (a < 0) {
      throw new EvaluationError(`log10 of a negative number (${a}).`);
    }
    return Math.log10(a);
  },
  sin: ([a = Number.NaN]) => Math.sin(a),
  cos: ([a = Number.NaN]) => Math.cos(a),
  tan: ([a = Number.NaN]) => Math.tan(a),
  asin: ([a = Number.NaN]) => Math.asin(a),
  acos: ([a = Number.NaN]) => Math.acos(a),
  atan: (args) => (args.length === 2 ? Math.atan2(args[0] ?? 0, args[1] ?? 0) : Math.atan(args[0] ?? 0)),
  sinh: ([a = Number.NaN]) => Math.sinh(a),
  cosh: ([a = Number.NaN]) => Math.cosh(a),
  tanh: ([a = Number.NaN]) => Math.tanh(a),
  mod: ([a = Number.NaN, b = Number.NaN]) => {
    if (b === 0) {
      throw new EvaluationError("Division by zero in mod.");
    }
    return a - b * Math.floor(a / b);
  },
  rem: ([a = Number.NaN, b = Number.NaN]) => {
    if (b === 0) {
      throw new EvaluationError("Division by zero in rem.");
    }
    return a % b;
  },
  hypot: ([a = Number.NaN, b = Number.NaN]) => Math.hypot(a, b),
};

function evaluateNode(node: ExpressionNode, env: ReadonlyMap<string, number>): ExpressionValue {
  switch (node.kind) {
    case "number":
      return node.value;
    case "identifier": {
      const value = env.get(node.name);
      if (value !== undefined) {
        return value;
      }
      if (node.name === "true" || node.name === "false") {
        return node.name === "true";
      }
      if (node.name === "pi") {
        return Math.PI;
      }
      throw new EvaluationError(`"${node.name}" is not a global parameter.`, node.name);
    }
    case "call": {
      if (node.name === "ifelse") {
        if (node.args.length !== 3) {
          throw new EvaluationError("ifelse takes three arguments.");
        }
        const [cond, a, b] = node.args as [ExpressionNode, ExpressionNode, ExpressionNode];
        const c = evaluateNode(cond, env);
        if (typeof c !== "boolean") {
          throw new EvaluationError("The ifelse condition must be a comparison.");
        }
        return evaluateNode(c ? a : b, env);
      }
      const fn = PURE_FUNCTIONS[node.name];
      if (fn === undefined) {
        throw new EvaluationError(`${node.name} is not a pure built-in function.`);
      }
      return fn(node.args.map((arg) => num(evaluateNode(arg, env), node.name)));
    }
    case "unary": {
      const value = evaluateNode(node.operand, env);
      if (node.operator === "!") {
        if (typeof value !== "boolean") {
          throw new EvaluationError("! needs a Bool.");
        }
        return !value;
      }
      const n = num(value, node.operator);
      return node.operator === "-" ? -n : n;
    }
    case "binary": {
      const left = evaluateNode(node.left, env);
      const right = evaluateNode(node.right, env);
      if (node.operator === "&&" || node.operator === "||") {
        if (typeof left !== "boolean" || typeof right !== "boolean") {
          throw new EvaluationError(`${node.operator} needs two Bools.`);
        }
        return node.operator === "&&" ? left && right : left || right;
      }
      if (node.operator === "==") {
        return left === right;
      }
      if (node.operator === "!=") {
        return left !== right;
      }
      const a = num(left, node.operator);
      const b = num(right, node.operator);
      switch (node.operator) {
        case "+":
          return a + b;
        case "-":
          return a - b;
        case "*":
          return a * b;
        case "/":
          if (b === 0) {
            throw new EvaluationError("Division by zero.");
          }
          return a / b;
        case "^":
          return a ** b;
        case "<":
          return a < b;
        case ">":
          return a > b;
        case "<=":
          return a <= b;
        case ">=":
          return a >= b;
      }
    }
  }
  throw new EvaluationError("Not a constant expression.");
}

/**
 * Evaluate an expression whose names are global parameters (`env`). This is
 * the browser's mirror of the compiler's constant folder; the worker stays
 * authoritative.
 */
export function evaluateExpression(
  node: ExpressionNode,
  env: ReadonlyMap<string, number>,
): EvaluationResult {
  try {
    return { ok: true, value: evaluateNode(node, env) };
  } catch (error) {
    if (error instanceof EvaluationError) {
      return error.name_ === undefined
        ? { ok: false, message: error.message }
        : { ok: false, message: error.message, name: error.name_ };
    }
    throw error;
  }
}

/** Every name an expression reads (not the called function names), first use first. */
export function expressionNames(node: ExpressionNode, out: string[] = []): string[] {
  switch (node.kind) {
    case "identifier":
      if (!out.includes(node.name)) {
        out.push(node.name);
      }
      break;
    case "call":
      node.args.forEach((arg) => expressionNames(arg, out));
      break;
    case "unary":
      expressionNames(node.operand, out);
      break;
    case "binary":
      expressionNames(node.left, out);
      expressionNames(node.right, out);
      break;
    default:
      break;
  }
  return out;
}

export interface IdentifierSpan {
  name: string;
  start: number;
  end: number;
  /** The identifier is called (`sqrt(`), so it names a function, not a value. */
  call: boolean;
}

/**
 * The plain identifiers of an expression string with their positions, scanned
 * with the tokenizer's own number and identifier rules: the `e` of `1e-3` is
 * part of a number, and a dotted name (`a.b`) is one token that is never
 * split. Text the tokenizer would reject is skipped, so renaming works on
 * every stored value.
 */
export function identifierSpans(source: string): IdentifierSpan[] {
  const spans: IdentifierSpan[] = [];
  let index = 0;
  while (index < source.length) {
    const rest = source.slice(index);
    const numberMatch = NUMBER.exec(rest);
    if (numberMatch !== null && /[0-9.]/.test(rest[0] ?? "")) {
      index += numberMatch[0].length;
      // A number glued to letters (`2x`) is not an identifier start either.
      const glued = /^[A-Za-z0-9_]*/.exec(source.slice(index));
      index += glued?.[0].length ?? 0;
      continue;
    }
    const identifierMatch = IDENTIFIER.exec(rest);
    if (identifierMatch !== null) {
      const text = identifierMatch[0];
      if (!text.includes(".")) {
        const after = source.slice(index + text.length).trimStart();
        spans.push({ name: text, start: index, end: index + text.length, call: after.startsWith("(") });
      }
      index += text.length;
      continue;
    }
    index += 1;
  }
  return spans;
}

/** `source` with every whole-identifier use of `from` replaced by `to`. */
export function renameIdentifier(source: string, from: string, to: string): string {
  const spans = identifierSpans(source).filter((span) => span.name === from && !span.call);
  let out = source;
  for (const span of spans.reverse()) {
    out = out.slice(0, span.start) + to + out.slice(span.end);
  }
  return out;
}

/**
 * A plain value, not an equation: a number with an optional sign, or a Bool.
 * Anything else (a name, arithmetic, a function) is "driven" and gets the Σ
 * marker of the inspector, as in SolidWorks.
 */
export function isPlainLiteral(source: string): boolean {
  return /^\s*[+-]?\s*(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\s*$/.test(source) ||
    /^\s*(?:true|false)\s*$/.test(source);
}

/** The SolidWorks-style equation prefix: a leading `=` is accepted and dropped. */
export function stripEquationPrefix(source: string): string {
  const trimmed = source.trim();
  return trimmed.startsWith("=") && !trimmed.startsWith("==") ? trimmed.slice(1).trim() : trimmed;
}
