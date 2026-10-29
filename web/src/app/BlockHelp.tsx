import { useRef } from "react";

import type { CatalogBlock, CatalogDomain, DomainName } from "../contracts/catalog";
import { BlockIcon, JunctionGlyph } from "../editor/icons";
import { PortGlyph } from "../library/PortGlyph";
import { useCatalogStore } from "../library/catalogStore";
import type { CatalogIndex } from "../library/catalogIndex";
import { useHelpStore } from "./helpStore";
import { useDialogFocus } from "./useDialogFocus";

const DOMAIN_LETTER: Record<DomainName, string> = {
  Electrical: "E",
  Translation: "T",
  Rotation: "R",
  Hydraulic: "H",
  Generic: "G",
  Planar: "P",
  Spatial: "S",
};

function unitText(unit: string | null | undefined): string {
  return unit === null || unit === undefined || unit.length === 0 ? "dimensionless" : unit;
}

function sizeText(size: readonly number[]): string {
  return size.length === 0 ? "scalar" : size.join(" × ");
}

function variableText(domain: CatalogDomain | undefined): string {
  if (domain === undefined) {
    return "";
  }
  return `effort ${domain.effort.name} [${unitText(domain.effort.unit)}], flow ${domain.flow.name} [${unitText(domain.flow.unit)}]`;
}

function JunctionHelp({ kind }: { kind: "0" | "1" }) {
  return (
    <>
      <p className="help-dialog__description">
        {kind === "0"
          ? "A 0 junction is a common-effort point: every attached bond carries the same effort and the flows sum to zero (Kirchhoff current law, a shared node)."
          : "A 1 junction is a common-flow point: every attached bond carries the same flow and the efforts sum to zero (Kirchhoff voltage law, a shared velocity)."}
      </p>
      <p className="help-dialog__note">
        Junctions have no parameters. Attach bonds to the circle edge; the arrow of each bond shows the
        positive power direction.
      </p>
    </>
  );
}

function BlockSections({ block, index }: { block: CatalogBlock; index: CatalogIndex }) {
  return (
    <>
      <p className="help-dialog__description" data-testid="block-help-description">
        {block.description}
      </p>

      <section aria-labelledby="help-ports">
        <h3 className="open-dialog__heading" id="help-ports">
          Ports
        </h3>
        {block.ports.length + block.inputs.length + block.outputs.length === 0 ? (
          <p className="help-dialog__note">This block has no ports; it only holds parameters.</p>
        ) : (
          <table className="help-table" data-testid="block-help-ports">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Kind</th>
                <th scope="col">Domain / type</th>
                <th scope="col">Units</th>
              </tr>
            </thead>
            <tbody>
              {block.ports.map((port) => (
                <tr key={`p-${port.name}`}>
                  <th scope="row">
                    <PortGlyph domain={port.domain} name={port.name} frame={port.frame} />
                    {port.name}
                  </th>
                  <td>power{port.size.length > 0 ? ` · ${sizeText(port.size)}` : ""}</td>
                  <td>
                    <span className="help-table__letter" aria-hidden="true">
                      {DOMAIN_LETTER[port.domain]}
                    </span>{" "}
                    {port.domain}
                  </td>
                  <td>{variableText(index.domains.get(port.domain))}</td>
                </tr>
              ))}
              {block.inputs.map((input) => (
                <tr key={`i-${input.name}`}>
                  <th scope="row">{input.name}</th>
                  <td>input signal{input.size.length > 0 ? ` · ${sizeText(input.size)}` : ""}</td>
                  <td>{input.type}</td>
                  <td>{unitText(input.unit)}</td>
                </tr>
              ))}
              {block.outputs.map((output) => (
                <tr key={`o-${output.name}`}>
                  <th scope="row">{output.name}</th>
                  <td>output signal{output.size.length > 0 ? ` · ${sizeText(output.size)}` : ""}</td>
                  <td>{output.type}</td>
                  <td>{unitText(output.unit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="help-params">
        <h3 className="open-dialog__heading" id="help-params">
          Parameters
        </h3>
        {block.parameters.length === 0 ? (
          <p className="help-dialog__note">No parameters: this block works as it is.</p>
        ) : (
          <table className="help-table" data-testid="block-help-params">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Unit</th>
                <th scope="col">Default</th>
                <th scope="col">Min</th>
                <th scope="col">Max</th>
                <th scope="col">Description</th>
              </tr>
            </thead>
            <tbody>
              {block.parameters.map((parameter) => (
                <tr key={parameter.name}>
                  <th scope="row">
                    {parameter.name}
                    {parameter.tunable ? <span className="inspector-tag">tunable</span> : null}
                  </th>
                  <td>{unitText(parameter.unit)}</td>
                  <td>
                    <code>{parameter.default}</code>
                  </td>
                  <td>{parameter.min ?? "—"}</td>
                  <td>{parameter.max ?? "—"}</td>
                  <td>
                    {parameter.description}
                    {parameter.options !== null ? ` Options: ${parameter.options.join(", ")}.` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {block.constants.length > 0 ? (
        <section aria-labelledby="help-constants">
          <h3 className="open-dialog__heading" id="help-constants">
            Constants
          </h3>
          <ul className="help-dialog__list">
            {block.constants.map((constant) => (
              <li key={constant.name}>
                <code>{constant.name}</code> = <code>{JSON.stringify(constant.default)}</code>
                {constant.structural ? " · changes the block structure" : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

/**
 * Help for one block from its catalog entry: description, ports with domain
 * and units, and parameters with unit, default, bounds and description. Opened
 * from the library (the help button of an expanded item), the inspector and F1.
 */
export function BlockHelp() {
  const ref = useHelpStore((state) => state.blockRef);
  const close = useHelpStore((state) => state.closeBlockHelp);
  const index = useCatalogStore((state) => state.index);
  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(ref !== null, dialog, close);

  if (ref === null) {
    return null;
  }
  const junctionKind = ref === "junction:0" ? "0" : ref === "junction:1" ? "1" : null;
  const block = index?.blocksByRef.get(ref);
  const title = junctionKind !== null ? `Junction ${junctionKind}` : (block?.name ?? ref);

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          close();
        }
      }}
    >
      <div
        className="help-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="block-help-title"
        data-testid="block-help"
        data-ref={ref}
        ref={dialog}
        tabIndex={-1}
      >
        <header className="open-dialog__header">
          <span aria-hidden="true" className="help-dialog__icon">
            {junctionKind !== null ? (
              <JunctionGlyph kind={junctionKind} size={26} />
            ) : block !== undefined ? (
              <BlockIcon icon={block.icon} name={block.name} size={26} />
            ) : null}
          </span>
          <div className="help-dialog__heading">
            <h2 className="open-dialog__title" id="block-help-title">
              {title}
            </h2>
            <p className="help-dialog__ref">
              {ref}
              {block !== undefined ? ` · ${block.group}` : ""}
            </p>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close the block help"
            title="Close (Esc)"
            data-testid="block-help-close"
            onClick={close}
          >
            <span aria-hidden="true">✕</span>
          </button>
        </header>
        <div className="help-dialog__body">
          {junctionKind !== null ? (
            <JunctionHelp kind={junctionKind} />
          ) : block !== undefined && index !== null ? (
            <BlockSections block={block} index={index} />
          ) : (
            <p className="help-dialog__note" role="status">
              {index === null
                ? "The library is still loading; reopen the help in a moment."
                : `The block ${ref} is not in the current catalog. Check the project library or pick the block again from the library.`}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** A small "?" button that opens the help of `blockRef`. */
export function BlockHelpButton({ blockRef, label }: { blockRef: string; label: string }) {
  const open = useHelpStore((state) => state.openBlockHelp);
  return (
    <button
      type="button"
      className="icon-button block-help-button"
      data-testid="block-help-button"
      aria-label={`Help for ${label}`}
      title={`Help for ${label} (F1)`}
      onClick={() => open(blockRef)}
    >
      <span aria-hidden="true">?</span>
    </button>
  );
}
