/**
 * Parser for the binary `/api/runs/{id}/data` frame (plan 3.7).
 *
 * Layout, all little-endian:
 *
 *     u32 n_signals | u32 n_points | n_points × f64 time | n_signals × n_points × f64
 *
 * The two `u32` counts are followed by the time column and then one Float64
 * column per requested signal, in request order. The response is binary by
 * design (plan 3.7), so it is read with `DataView`/`Float64Array` — never JSON.
 *
 * On a little-endian host (every browser on the target platforms) the columns
 * are exposed as zero-copy views over the response buffer; a big-endian host
 * falls back to `DataView` and copies. The length is checked exactly, so a
 * truncated or padded answer is reported instead of drawing garbage.
 */

/** Byte size of `u32 n_signals` + `u32 n_points`. */
export const RUN_DATA_HEADER_BYTES = 8;
/** Byte size of one Float64 value. */
export const RUN_DATA_VALUE_BYTES = 8;

const LITTLE_ENDIAN_PROBE = new Uint16Array([1]);
/** True when the host stores multi-byte values little-endian (all browsers). */
export const IS_LITTLE_ENDIAN =
  new Uint8Array(LITTLE_ENDIAN_PROBE.buffer)[0] === 1;

/** A decoded frame; every column has `nPoints` values. */
export interface RunDataFrame {
  /** Number of signal columns (the requested `ids`). */
  nSignals: number;
  /** Number of rows in every column. */
  nPoints: number;
  /** Time values in seconds. */
  time: Float64Array;
  /** One value column per signal, in request order. */
  values: Float64Array[];
}

/** A malformed `/data` answer; the message is meant for the user. */
export class RunDataError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RunDataError";
  }
}

/** A frame with the given number of empty columns. */
export function emptyRunDataFrame(nSignals = 0): RunDataFrame {
  return {
    nSignals,
    nPoints: 0,
    time: new Float64Array(0),
    values: Array.from({ length: nSignals }, () => new Float64Array(0)),
  };
}

/**
 * Decode one binary `/data` response.
 *
 * @throws {RunDataError} when the buffer is shorter than the header, when its
 *   length does not match the stated counts, or when the counts cannot
 *   describe a frame.
 */
export function parseRunData(buffer: ArrayBuffer): RunDataFrame {
  if (buffer.byteLength < RUN_DATA_HEADER_BYTES) {
    throw new RunDataError(
      `The run data answer is ${buffer.byteLength} bytes, which is too short ` +
        "to hold the two-column-count header. Is the backend a bg-sim release?",
    );
  }

  const view = new DataView(buffer);
  const nSignals = view.getUint32(0, true);
  const nPoints = view.getUint32(4, true);
  const expected =
    RUN_DATA_HEADER_BYTES +
    (nSignals + 1) * nPoints * RUN_DATA_VALUE_BYTES;

  if (buffer.byteLength !== expected) {
    throw new RunDataError(
      `The run data answer declares ${nSignals} signal(s) × ${nPoints} point(s) ` +
        `and should be ${expected} bytes, but the backend sent ${buffer.byteLength} bytes. ` +
        "Reload the run and try again.",
    );
  }

  if (nPoints === 0) {
    return emptyRunDataFrame(nSignals);
  }

  if (IS_LITTLE_ENDIAN) {
    const time = new Float64Array(buffer, RUN_DATA_HEADER_BYTES, nPoints);
    const values = Array.from({ length: nSignals }, (_, index) => {
      const offset =
        RUN_DATA_HEADER_BYTES + (index + 1) * nPoints * RUN_DATA_VALUE_BYTES;
      return new Float64Array(buffer, offset, nPoints);
    });
    return { nSignals, nPoints, time, values };
  }

  const time = new Float64Array(nPoints);
  for (let index = 0; index < nPoints; index += 1) {
    time[index] = view.getFloat64(
      RUN_DATA_HEADER_BYTES + index * RUN_DATA_VALUE_BYTES,
      true,
    );
  }
  const values = Array.from({ length: nSignals }, (_, signal) => {
    const column = new Float64Array(nPoints);
    const start =
      RUN_DATA_HEADER_BYTES +
      (signal + 1) * nPoints * RUN_DATA_VALUE_BYTES;
    for (let index = 0; index < nPoints; index += 1) {
      column[index] = view.getFloat64(
        start + index * RUN_DATA_VALUE_BYTES,
        true,
      );
    }
    return column;
  });
  return { nSignals, nPoints, time, values };
}
