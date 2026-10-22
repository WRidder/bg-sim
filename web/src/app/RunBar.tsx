/**
 * Run, Stop and the simulation settings of plan 7.2, mounted by `TopBar`.
 *
 * This file is owned by W1.4. The placeholder keeps the disabled controls of the
 * M0 shell; the real bar binds them to the model document's `settings`, starts
 * and cancels runs through the backend and shows `t / t_end` progress.
 */
const SIMULATION_SETTINGS = [
  { id: "t-end", label: "t_end", value: "1 s" },
  { id: "solver", label: "solver", value: "auto" },
  { id: "tol", label: "tol", value: "1e-6" },
] as const;

export function RunBar() {
  return (
    <>
      <div className="top-bar__run" role="group" aria-label="Simulation controls">
        <button
          type="button"
          className="button button--primary"
          disabled
          aria-label="Run simulation"
          title="Run (Ctrl+Enter) becomes available when a model is open"
        >
          <span className="button__glyph" aria-hidden="true">
            ▶
          </span>
          Run
        </button>
        <button
          type="button"
          className="button"
          disabled
          aria-label="Stop simulation"
          title="Stop becomes available while a simulation runs"
        >
          <span className="button__glyph" aria-hidden="true">
            ■
          </span>
          Stop
        </button>
      </div>

      <div className="top-bar__settings">
        {SIMULATION_SETTINGS.map((setting) => (
          <label className="setting" key={setting.id}>
            <span className="setting__label">{setting.label}</span>
            <input
              className="setting__value"
              type="text"
              value={setting.value}
              readOnly
              disabled
              aria-label={setting.label}
              title="Simulation settings become editable when a model is open"
            />
          </label>
        ))}
      </div>
    </>
  );
}
