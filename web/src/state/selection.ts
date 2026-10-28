import type { AreaId } from "../events/areas";
import type { Scene } from "../events/reduce";
import type { ObserverEvent } from "../events/schema";

export type Selection =
  | { type: "event"; sequence: number }
  | { type: "attacker"; id: string }
  | { type: "deployment"; id: string }
  | { type: "post"; id: string }
  | { type: "area"; id: AreaId };

export function resolveSelection(scene: Scene, selection: Selection | null): ObserverEvent | null {
  if (!selection) return scene.events.at(-1) ?? null;
  if (selection.type === "event") {
    return scene.events.find((event) => event.sequence === selection.sequence) ?? null;
  }
  if (selection.type === "attacker") {
    const attacker = scene.attackers[selection.id];
    if (attacker && attacker.lastSequence !== null) {
      return scene.events.find((event) => event.sequence === attacker.lastSequence) ?? null;
    }
    return [...scene.events].reverse().find((event) => event.actorId === selection.id) ?? null;
  }
  if (selection.type === "deployment") {
    return (
      [...scene.events]
        .reverse()
        .find(
          (event) =>
            event.kind === "deployment_committed" ||
            event.kind === "deployment_rejected" ||
            event.kind === "deployment_started",
        ) ?? null
    );
  }
  if (selection.type === "post") {
    const postId = Number(selection.id);
    return (
      scene.events.find((event) => event.kind === "messageboard_posted" && event.postId === postId) ?? null
    );
  }
  if (selection.id === "service") {
    return [...scene.events].reverse().find((event) => event.toolName === "request_service") ?? null;
  }
  return null;
}
