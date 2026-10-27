/** The oscilloscope probe glyph: a tapered probe with a small ferrule. */
export function ProbeGlyph({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className="probe-glyph"
    >
      <path
        d="M13.8 2.8a2 2 0 0 1 2.8 0l4.6 4.6a2 2 0 0 1 0 2.8l-3.1 3.1-2.9-2.9-5.1 5.1-2.8-2.8 5.1-5.1-2.9-2.9 3.1-3.1Z"
        fill="currentColor"
      />
      <path d="M9.7 13.4 3.4 21.1a1 1 0 0 1-1.5-1.3l6.6-7.5 1.2 1.1Z" fill="currentColor" />
      <path
        d="M9.1 10.5 7 12.6l-1.1-1.1a1.3 1.3 0 0 1 0-1.8l.6-.6a1.3 1.3 0 0 1 1.8 0l.8.8Z"
        fill="currentColor"
      />
    </svg>
  );
}
