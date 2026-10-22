/**
 * Starter sources for the two inline code nodes of plan 7.7. They are valid
 * blocks with one input and one output, so the node gets its first ports as
 * soon as the first `block.check` answers, and the user starts from working
 * code rather than an empty editor.
 */

export const EQUATION_TEMPLATE = `@block Equation begin
    @inputs u::Real
    @outputs y::Real
    @equations y ~ u
end
`;

export const DISCRETE_TEMPLATE = `@block DiscreteCode begin
    @inputs u::Real
    @outputs y::Real
    @variables y::Real
    @discrete Ts = 0.01 begin
        y = previous(y) + Ts * u
    end
end
`;

/** The block name declared on the first `@block` line, or null. */
export function blockNameOf(source: string): string | null {
  return /^[ \t]*@block[ \t]+([A-Za-z_][A-Za-z0-9_]*)/m.exec(source)?.[1] ?? null;
}
