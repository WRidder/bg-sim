/**
 * Per-component units of a multibond port (plan 5.3, J-MB2, D-MB10).
 *
 * A Planar port is `[N*m, N, N]` effort and `[rad/s, m/s, m/s]` flow; a Spatial
 * port is the angular triad followed by the linear triad. The catalog domain
 * carries these arrays (`components`), and a subsystem power port may carry the
 * same arrays through its boundary. A scalar port has no component array and
 * keeps its single domain effort/flow unit.
 */

import type { CatalogDomain } from "../contracts/catalog";
import type { PortSpec } from "../editor/nodeInterface";
import type { CatalogIndex } from "../library/catalogIndex";

export interface ComponentUnits {
  effort: readonly string[];
  flow: readonly string[];
}

/** The domain's authoritative per-component arrays, or null for a scalar domain. */
export function domainComponentUnits(
  domain: CatalogDomain | undefined,
): ComponentUnits | null {
  if (domain === undefined || !("components" in domain)) {
    return null;
  }
  return { effort: domain.components.effort, flow: domain.components.flow };
}

/**
 * The units to show for one power port: the subsystem boundary arrays when
 * present, otherwise the catalog domain's arrays. Signal ports and scalar power
 * ports return null and keep the single-unit presentation.
 */
export function portComponentUnits(
  port: PortSpec,
  index: CatalogIndex,
): ComponentUnits | null {
  if (port.kind !== "power") {
    return null;
  }
  if (
    port.effortUnits !== undefined &&
    port.flowUnits !== undefined &&
    port.effortUnits.length === port.flowUnits.length &&
    port.effortUnits.length > 1
  ) {
    return { effort: port.effortUnits, flow: port.flowUnits };
  }
  return domainComponentUnits(index.domains.get(port.domain));
}

/** `[N*m, N, N]`, one bracket for a units line. */
export function unitArrayText(units: readonly string[]): string {
  return `[${units.join(", ")}]`;
}
