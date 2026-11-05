/**
 * The buggy's ground: the sum of cosines compiled into its FMU (examples/cars/design/hills.json).
 * What the tyres roll on cannot change, so the world is built on this function, not the reverse.
 */

const A = [2.2, 1.4, 0.9, 0.45, 0.25, 0.12];
const KX = [0.04487989505128276, 0.041887902047863905, -0.07180783208205242, 0.13962634015954636, 0.057119866428905326, 0.25132741228718347];
const KY = [0.019634954084936207, 0.05585053606381855, 0.053855874061539306, -0.11423973285781065, 0.18087957702486687, 0.15707963267948966];
const PH = [0.3, 1.9, 4.0, 2.6, 0.7, 5.1];

export function hills(x: number, y: number): number {
  let h = 0;
  for (let i = 0; i < 6; i += 1) {
    h += A[i] * Math.cos(KX[i] * x + KY[i] * y + PH[i]);
  }
  return h;
}

/** The same function for a shader, where `p` is (x, y) in the FMU's frame. */
export const HILLS_GLSL = /* glsl */ `
float hills(vec2 p) {
  float h = 0.0;
${A.map((a, i) => `  h += ${a.toFixed(4)} * cos(${KX[i].toFixed(9)} * p.x + ${KY[i].toFixed(9)} * p.y + ${PH[i].toFixed(4)});`).join("\n")}
  return h;
}
`;
