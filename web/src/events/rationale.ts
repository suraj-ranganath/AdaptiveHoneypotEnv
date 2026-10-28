import type { Scene } from "./reduce";
import type { ObserverEvent } from "./schema";

function cite(sequence: number): string {
  return `seq ${sequence}`;
}

function cited(scene: Scene, sequences: number[]): string {
  if (sequences.length === 0) return "no source sequence on this event";
  return sequences
    .map((sequence) => {
      const source = scene.events.find((item) => item.sequence === sequence);
      if (!source) return `${cite(sequence)} (not in this prefix)`;
      const tool = source.toolName ? ` ${source.toolName}` : "";
      return `${cite(sequence)} (${source.actorId}${tool})`;
    })
    .join(", ");
}

/** Short, event-cited explanation. Never a chain of thought. */
export function rationaleFor(event: ObserverEvent, scene: Scene): string {
  const who = event.actorId;
  switch (event.kind) {
    case "episode_started":
      return `Episode ${event.episodeId} started (${cite(event.sequence)}). Scenario, team, and model are not fields of this projection.`;
    case "model_call_started":
      return `${who} model call started (${cite(event.sequence)}). No tool has been chosen for this call yet.`;
    case "model_call_finished":
      return event.status === "refused"
        ? `${who} model call finished with status refused (${cite(event.sequence)}). A provider refusal is not a defender outcome. Reasoning text is not on this projection.`
        : `${who} model call finished (${cite(event.sequence)}, status ${event.status}). Reasoning text is not on this projection.`;
    case "tool_started":
      return `${who} started ${event.toolName ?? "a tool"} (${cite(event.sequence)}). The result is not in yet.`;
    case "tool_completed": {
      const tool = event.toolName ?? "a tool";
      const parts = [`${who} completed ${tool} (${cite(event.sequence)}, status ${event.status}).`];
      if (tool === "search_files" || tool === "list_directory" || tool === "read_file") {
        parts.push("Path, query, and hit list are not on the operator projection, so this does not highlight a room.");
      }
      if (tool === "read_file") parts.push("A file read is not a catch unless a later decoy_inspected event says so.");
      if (tool === "finish") parts.push("The finish summary is not on this projection. It does not set compromise or engagement.");
      if (event.clipped) parts.push("The delivery was clipped. Omitted bytes are not shown.");
      return parts.join(" ");
    }
    case "actor_turn_rejected":
      return `${who} turn rejected (${cite(event.sequence)}, status ${event.status}). The reason category is not on the operator projection. Nothing was executed.`;
    case "messageboard_posted":
      return `${who} posted ${event.postId ?? "a message"} (${cite(event.sequence)}, ${event.charCount ?? 0} characters). Post text stays behind the payload ref. The defender does not receive this event.`;
    case "messageboard_read":
      return `${who} read the messageboard (${cite(event.sequence)}, ${event.returnedCount ?? 0} posts after ${event.afterPostId ?? 0}${event.clipped ? ", clipped" : ""}). Which posts came back is not on this projection. A board read is not a catch.`;
    case "deployment_started":
      return `Deployment started (${cite(event.sequence)}). No object is placed. Template, slot, and diff are not on the operator projection.`;
    case "deployment_rejected":
      return `Deployment rejected (${cite(event.sequence)}, status ${event.status}). No partial batch is placed. The reason category is not on the operator projection.`;
    case "deployment_committed":
      return `Deployment committed (${cite(event.sequence)}). The count of new decoys arrives on transition_completed, not on this event. Slot and diff are not on the operator projection.`;
    case "decoy_exposed":
      return `Decoy bytes were delivered (${cite(event.sequence)}, cites ${cited(scene, event.sourceSequences)}). Decoy id and recipient are not on the operator projection. Exposure is not a catch.`;
    case "decoy_inspected":
      return `Decoy content was inspected (${cite(event.sequence)}, cites ${cited(scene, event.sourceSequences)}). Inspection is not verified engagement.`;
    case "decoy_authenticated":
      return `Decoy login succeeded (${cite(event.sequence)}, cites ${cited(scene, event.sourceSequences)}). Login is not verified engagement.`;
    case "verified_engagement":
      return `Verified engagement (${cite(event.sequence)}, cites ${cited(scene, event.sourceSequences)}). The canary was delivered through an authenticated read. This does not stop the other sessions.`;
    case "protected_value_exposed":
      return `Genuine compromise (${cite(event.sequence)}, cites ${cited(scene, event.sourceSequences)}). The protected value was delivered. This is separate from verified engagement.`;
    case "transition_completed": {
      const reward = event.rewardComponents;
      const bits = reward
        ? `detection_bonus ${reward.detectionBonus}, compromise_penalty ${reward.compromisePenalty}, newly_committed_decoys ${reward.newlyCommittedDecoys}.`
        : "no reward components on this event.";
      return `Defender transition completed (${cite(event.sequence)}). Surrogate components: ${bits} This is not a counterfactual reward.`;
    }
    case "episode_finished":
      return `Episode finished (${cite(event.sequence)}). Termination reason is not on the operator projection. Detection and compromise on the counters come from verified_engagement and protected_value_exposed.`;
    default: {
      const neverKind: never = event.kind;
      return `Event ${cite(event.sequence)} (${String(neverKind)}).`;
    }
  }
}
