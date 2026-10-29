import type { SimulationFrame } from "../simulation/script";

const FAMILY: Record<SimulationFrame["kind"], string> = {
  setup: "other",
  scan: "tool",
  coordination: "board",
  defender: "wait",
  deploy: "deploy",
  service: "tool",
  catch: "alert",
  aftermath: "board",
  finish: "end",
};

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.5, 2, 3] as const;

export function SimulationTimeline({
  frames,
  cursor,
  playing,
  speed,
  loop,
  onCursor,
  onToggle,
  onRestart,
  onSpeed,
  onLoop,
}: {
  frames: SimulationFrame[];
  cursor: number;
  playing: boolean;
  speed: number;
  loop: boolean;
  onCursor(next: number): void;
  onToggle(): void;
  onRestart(): void;
  onSpeed(next: number): void;
  onLoop(next: boolean): void;
}) {
  const current = cursor > 0 ? frames[Math.min(cursor, frames.length) - 1] : null;
  return (
    <div className="timeline sim-timeline">
      <div className="sim-controls">
        <button type="button" className="ghost" onClick={onToggle} aria-pressed={playing}>
          {playing ? "Pause" : "Play"}
        </button>
        <button type="button" className="ghost" onClick={onRestart}>
          Restart
        </button>
        <label className="speed-pick">
          Speed
          <select value={String(speed)} onChange={(event) => onSpeed(Number(event.target.value))}>
            {SPEED_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value}x
              </option>
            ))}
          </select>
        </label>
        <label className="loop-toggle">
          <input type="checkbox" checked={loop} onChange={(event) => onLoop(event.target.checked)} /> Loop
        </label>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(frames.length, 0)}
        value={Math.min(cursor, frames.length)}
        disabled={frames.length === 0}
        aria-label="Simulation position"
        onChange={(event) => onCursor(Number(event.target.value))}
      />
      <p className="timeline-now">
        {current ? (
          <>
            <i className={`tick tick-${FAMILY[current.kind] ?? "other"}`} />
            frame {current.sequence} · round {current.round} · {current.title}
          </>
        ) : (
          "Start of the simulation"
        )}
      </p>
      <div className="ticks" aria-hidden="true">
        {frames.map((frame, index) => (
          <button
            key={frame.sequence}
            type="button"
            className={`tick-btn tick-${FAMILY[frame.kind] ?? "other"}${index < cursor ? " seen" : ""}`}
            title={`frame ${frame.sequence} · ${frame.title}`}
            onClick={() => onCursor(index + 1)}
          />
        ))}
      </div>
    </div>
  );
}

