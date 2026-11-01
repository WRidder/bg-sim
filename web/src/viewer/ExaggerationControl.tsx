import type { ReactElement } from "react";

import { EXAGGERATION_STEPS, formatFactor } from "./exaggeration";

export interface ExaggerationControlProps {
  readonly factor: number;
  readonly onChange: (factor: number) => void;
}

/**
 * The deformation exaggeration, shown in the 3D view itself (so it is in every screenshot, the detached
 * window and full screen): a chip with the factor, marked "exaggerated" above ×1, that is also the picker.
 */
export function ExaggerationControl({ factor, onChange }: ExaggerationControlProps): ReactElement {
  const exaggerated = factor !== 1;
  return (
    <div className="viewer__badge" data-testid="deformation-badge" data-factor={factor} data-exaggerated={exaggerated ? "true" : "false"}>
      <label className="viewer__badge-label">
        <span>Deformation</span>
        <select
          className="viewer__badge-select"
          aria-label="Deformation exaggeration"
          data-testid="deformation-exaggeration"
          value={factor}
          title={exaggerated ? `Deformations (beams and mode shapes) are drawn ${formatFactor(factor)} larger than computed` : "Deformations (beams and mode shapes) are drawn at true scale"}
          onChange={(e) => {
            onChange(Number(e.target.value));
          }}
        >
          {EXAGGERATION_STEPS.map((f) => (
            <option key={f} value={f}>
              {formatFactor(f)}
            </option>
          ))}
        </select>
      </label>
      <span className="viewer__badge-note">{exaggerated ? "exaggerated" : "true scale"}</span>
    </div>
  );
}
