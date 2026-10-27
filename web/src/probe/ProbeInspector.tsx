/**
 * Inspector for an oscilloscope probe. The probe itself is side-channel data:
 * its leads choose which signals are observed and a 3x3 block can group them
 * into user-defined plot panels.
 */

import type { Model, ModelProbe, ModelProbePanel } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { probeOptions, probeSignalOptions } from "./probeSignals";
import { useProbeUi } from "./probeUi";
import "./probe.css";

function toggle(list: readonly string[], id: string, checked: boolean): string[] {
  const next = new Set(list);
  if (checked) {
    next.add(id);
  } else {
    next.delete(id);
  }
  return [...next];
}

export function ProbeInspector({ model, probe }: { model: Model; probe: ModelProbe }) {
  const activeLinkId = useProbeUi((state) => state.activeLinkId);
  const setActiveLink = useProbeUi((state) => state.setActiveLink);
  const options = probeOptions(model, probe);
  const store = useDocumentStore.getState();
  const panels = probe.panels ?? [];

  const setPanels = (next: ModelProbePanel[]): void => {
    store.setProbePanels(probe.id, next);
  };
  const addPanel = (): void => {
    const used = new Set(panels.map((panel) => panel.id));
    let number = panels.length + 1;
    while (used.has(`panel${number}`)) {
      number += 1;
    }
    setPanels([
      ...panels,
      { id: `panel${number}`, title: `Panel ${number}`, signals: [] },
    ]);
  };
  const togglePanelSignal = (
    panel: ModelProbePanel,
    signal: string,
    checked: boolean,
  ): void => {
    setPanels(
      panels.map((entry) =>
        entry.id === panel.id
          ? { ...entry, signals: toggle(entry.signals, signal, checked) }
          : entry,
      ),
    );
  };

  return (
    <div className="inspector-body probe-inspector" data-testid="probe-inspector">
      <header className="inspector-header">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">
            {probe.kind === "block" ? "Probe block" : "Probe plot window"}
          </p>
          <h3 className="inspector-header__title">{probe.name}</h3>
          <p className="inspector-header__description">
            Probe leads observe connections without joining the circuit. Check the
            signals you want to plot.
          </p>
        </div>
      </header>

      <div className="probe-inspector__actions">
        <button
          type="button"
          className="button button--compact"
          data-testid="probe-toggle-open"
          onClick={() => store.setProbeOpen(probe.id, !(probe.open ?? true))}
        >
          {(probe.open ?? true) ? "Hide plot" : "Show plot"}
        </button>
        <button
          type="button"
          className="button button--compact"
          data-testid="probe-delete"
          onClick={() => store.deleteProbe(probe.id)}
        >
          Delete probe
        </button>
      </div>

      <section className="probe-inspector__section">
        <h4>Leads</h4>
        {probe.links.length === 0 ? (
          <p className="probe-inspector__hint">
            Right-click a connection and choose this probe, or drag from its handle.
          </p>
        ) : null}
        {probe.links.map((link) => {
          const connection = model.diagram.connections.find(
            (entry) => entry.id === link.connection,
          );
          const available =
            connection === undefined ? [] : probeSignalOptions(model.diagram, connection);
          const checked = link.signals;
          return (
            <div
              className={`probe-inspector__lead${activeLinkId === link.id ? " is-active" : ""}`}
              key={link.id}
              data-testid={`probe-link-${link.id}`}
              onClick={() => setActiveLink(link.id)}
            >
              <div className="probe-inspector__lead-head">
                <strong>{connection?.kind ?? "connection"} {link.connection}</strong>
                <button
                  type="button"
                  className="button button--compact"
                  data-testid={`probe-remove-link-${link.id}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    store.removeProbeLink(probe.id, link.id);
                  }}
                >
                  Remove
                </button>
              </div>
              {available.length === 0 ? (
                <p className="probe-inspector__hint">
                  This lead has no recorded signal (a pure junction connection).
                </p>
              ) : (
                available.map((option) => (
                  <label className="probe-inspector__check" key={option.id}>
                    <input
                      type="checkbox"
                      data-testid={`probe-signal-${link.id}-${option.id}`}
                      checked={checked.includes(option.id)}
                      onChange={(event) =>
                        store.setProbeLinkSignals(
                          probe.id,
                          link.id,
                          toggle(
                            checked,
                            option.id,
                            event.currentTarget.checked,
                          ),
                        )
                      }
                    />
                    <span>{option.label}</span>
                  </label>
                ))
              )}
            </div>
          );
        })}
      </section>

      {probe.kind === "block" ? (
        <section className="probe-inspector__section">
          <div className="probe-inspector__lead-head">
            <h4>Plot panels</h4>
            <button
              type="button"
              className="button button--compact"
              data-testid="probe-add-panel"
              onClick={addPanel}
            >
              Add panel
            </button>
          </div>
          {panels.length === 0 ? (
            <p className="probe-inspector__hint">
              No panels configured: all checked signals share one dedicated plot.
            </p>
          ) : null}
          {panels.map((panel) => (
            <div className="probe-inspector__panel" key={panel.id}>
              <div className="probe-inspector__lead-head">
                <input
                  className="probe-inspector__panel-title"
                  value={panel.title}
                  aria-label="Panel title"
                  data-testid={`probe-panel-title-${panel.id}`}
                  onChange={(event) =>
                    setPanels(
                      panels.map((entry) =>
                        entry.id === panel.id
                          ? { ...entry, title: event.currentTarget.value }
                          : entry,
                      ),
                    )
                  }
                />
                <button
                  type="button"
                  className="button button--compact"
                  data-testid={`probe-remove-panel-${panel.id}`}
                  onClick={() =>
                    setPanels(panels.filter((entry) => entry.id !== panel.id))
                  }
                >
                  Remove
                </button>
              </div>
              {options.map((option) => (
                <label className="probe-inspector__check" key={option.id}>
                  <input
                    type="checkbox"
                    data-testid={`probe-panel-${panel.id}-${option.id}`}
                    checked={panel.signals.includes(option.id)}
                    onChange={(event) =>
                      togglePanelSignal(
                        panel,
                        option.id,
                        event.currentTarget.checked,
                      )
                    }
                  />
                  <span>{option.label}</span>
                </label>
              ))}
            </div>
          ))}
        </section>
      ) : (
        <p className="probe-inspector__hint">
          This floating plot always shows all checked signals together.
        </p>
      )}
    </div>
  );
}
