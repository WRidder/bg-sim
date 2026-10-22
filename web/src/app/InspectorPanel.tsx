import { Inspector } from "../inspector/Inspector";

/**
 * The Inspector of plan 7.2: name, block, parameters (units, min/max,
 * description), ports, start values, "Open source" and "Copy to project
 * library" for the selected element.
 */
export function InspectorPanel() {
  return (
    <div className="inspector" data-testid="inspector-panel">
      <section className="panel-section" aria-labelledby="inspector-heading">
        <h2 className="panel-section__title" id="inspector-heading">
          Inspector
        </h2>
        <div className="panel-section__body">
          <Inspector />
        </div>
      </section>
    </div>
  );
}
