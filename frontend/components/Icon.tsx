// Stroke icons on a 24 by 24 grid, keyed by agent, status, or feed marker.
const PATHS = {
  researcher: "M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 0 0 0-13zM15.5 15.5L21 21",
  analyst: "M5 20V11M12 20V4M19 20v-6",
  engineer: "M8 7l-5 5l5 5M16 7l5 5l-5 5",
  writer: "M4 20l1-5L16 4l4 4L9 19zM13.5 6.5l4 4",
  planner: "M3 12h5c5 0 3-6 8-6h5M8 12c5 0 3 6 8 6h5",
  synthesizer: "M3 6h5c5 0 3 6 8 6h5M3 18h5c5 0 3-6 8-6",
  critic: "M2 12s3.5-7 10-7s10 7 10 7s-3.5 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6a3 3 0 0 0 0-6z",
  pending: "M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18zM12 7.5V12l3 2",
  running: "M12 3a9 9 0 1 0 9 9",
  completed: "M5 12.5l4.5 4.5L19 7.5",
  failed: "M6 6l12 12M18 6L6 18",
  skipped: "M5 12h14",
  cancelled: "M7 7h10v10H7z",
  start: "M8 5l11 7l-11 7z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" data-icon={name} viewBox="0 0 24 24" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
