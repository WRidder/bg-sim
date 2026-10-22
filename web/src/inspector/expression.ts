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
