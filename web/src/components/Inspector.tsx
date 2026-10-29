import { rationaleFor } from "../events/rationale";
import type { Scene } from "../events/reduce";
import { sanitizeText } from "../events/sanitize";
import type { ObserverEvent } from "../events/schema";

export function Inspector({
  event,
  scene,
  onSelectSequence,
}: {
  event: ObserverEvent | null;
  scene: Scene;
  focusDecoyId?: string | null;
  onSelectSequence(sequence: number): void;
}) {
  if (!event) {
    return (
      <section className="inspector" aria-label="Inspector">
        <h2>Inspector</h2>
        <p className="muted">Select an attacker, a message, or a timeline mark. Nothing here is inferred.</p>
      </section>
    );
  }

  return (
    <section className="inspector" aria-label="Inspector">
      <header className="inspector-head">
        <h2>Inspector</h2>
        <p className="mono">
          {event.kind} · seq {event.sequence} · round {event.roundIndex} · attempt {event.attemptIndex} · {event.status}
        </p>
      </header>
      <p className="rationale">{rationaleFor(event, scene)}</p>
      <p className="meta">
        Actor {event.actorId} · {event.actorRole} · request {sanitizeText(event.requestId, 128)}
      </p>
      {event.toolName ? <p className="meta">Tool {event.toolName}{event.clipped ? " · clipped" : ""}</p> : null}
      {event.kind === "messageboard_posted" ? (
        <p className="meta">
          Post {event.postId} · {event.charCount} characters. Text stays behind the payload ref.
        </p>
      ) : null}
      {event.kind === "messageboard_read" ? (
        <p className="meta">
          After post {event.afterPostId} · returned {event.returnedCount}
          {event.clipped ? " · clipped" : ""}
        </p>
      ) : null}
      {event.rewardComponents ? (
        <p className="meta">
          Surrogate on this event: detection_bonus {event.rewardComponents.detectionBonus} · compromise_penalty{" "}
          {event.rewardComponents.compromisePenalty} · newly_committed_decoys{" "}
          {event.rewardComponents.newlyCommittedDecoys} · decoy_cost{" "}
          {(event.rewardComponents.decoyCostCents / 100).toFixed(2)}. Not a counterfactual reward.
        </p>
      ) : null}
      {event.sourceSequences.length > 0 ? (
        <p className="sources">
          Source events{" "}
          {event.sourceSequences.map((sequence) => (
            <button key={sequence} type="button" className="link" onClick={() => onSelectSequence(sequence)}>
              seq {sequence}
            </button>
          ))}
        </p>
      ) : null}
      {event.deterministicId ? <p className="meta">Deterministic id {event.deterministicId}</p> : null}
      {event.payloadRefs.length > 0 ? (
        <ul className="meta">
          {event.payloadRefs.map((ref) => (
            <li key={ref.refId}>
              Payload {sanitizeText(ref.refId, 80)} · {ref.byteLength} bytes · sha256 {ref.sha256.slice(0, 12)}…
              Bytes are not on this event.
            </li>
          ))}
        </ul>
      ) : null}
      <p className="meta">
        Tool arguments, output, paths, hit lists, post text, deployment specs, and diffs stay behind payload refs.
      </p>
    </section>
  );
}
