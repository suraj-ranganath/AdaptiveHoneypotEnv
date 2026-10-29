import type { ObserverEvent } from "../events/schema";

const FAMILY: Record<string, string> = {
  model_call_started: "wait",
  model_call_finished: "wait",
  tool_started: "tool",
  tool_completed: "tool",
  actor_turn_rejected: "bad",
  messageboard_posted: "board",
  messageboard_read: "board",
  deployment_started: "deploy",
  deployment_committed: "deploy",
  deployment_rejected: "bad",
  decoy_exposed: "funnel",
  decoy_inspected: "funnel",
  decoy_authenticated: "funnel",
  verified_engagement: "alert",
  protected_value_exposed: "compromise",
  episode_finished: "end",
};

export function Timeline({
  events,
  cursor,
  playing,
  canScrub,
  onCursor,
  onToggle,
  onRestart,
  idleLabel = "Start of the recording",
}: {
  events: ObserverEvent[];
  cursor: number;
  playing: boolean;
  canScrub: boolean;
  onCursor(next: number): void;
  onToggle(): void;
  onRestart?: () => void;
  idleLabel?: string;
}) {
  const current = cursor > 0 ? events[cursor - 1] : null;
  return (
    <div className="timeline">
      {canScrub ? (
        <button type="button" className="ghost" onClick={onToggle} aria-pressed={playing}>
          {playing ? "Pause" : "Play"}
        </button>
      ) : (
        <span className="timeline-note">Live stream. Scrub is for a recording.</span>
      )}
      {onRestart ? (
        <button type="button" className="ghost" onClick={onRestart}>
          Restart
        </button>
      ) : null}
      <input
        type="range"
        min={0}
        max={Math.max(events.length, 0)}
        value={Math.min(cursor, events.length)}
        disabled={!canScrub || events.length === 0}
        aria-label="Replay position"
        onChange={(event) => onCursor(Number(event.target.value))}
      />
      <p className="timeline-now">
        {current ? (
          <>
            <i className={`tick tick-${FAMILY[current.kind] ?? "other"}`} />
            seq {current.sequence} · {current.kind} · {current.actorId}
          </>
        ) : (
          idleLabel
        )}
      </p>
      <div className="ticks" aria-hidden="true">
        {events.map((event, index) => (
          <button
            key={`${event.episodeId}:${event.sequence}`}
            type="button"
            className={`tick-btn tick-${FAMILY[event.kind] ?? "other"}${index < cursor ? " seen" : ""}`}
            title={`seq ${event.sequence} ${event.kind}`}
            disabled={!canScrub}
            onClick={() => onCursor(index + 1)}
          />
        ))}
      </div>
    </div>
  );
}
