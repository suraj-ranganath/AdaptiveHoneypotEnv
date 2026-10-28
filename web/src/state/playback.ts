import type { ObserverEvent } from "../events/schema";

export function delayFor(event: ObserverEvent | undefined): number {
  if (!event) return 560;
  switch (event.kind) {
    case "model_call_started":
      return 1100;
    case "verified_engagement":
      return 1500;
    case "protected_value_exposed":
      return 1600;
    case "deployment_committed":
      return 1300;
    case "decoy_inspected":
    case "decoy_authenticated":
      return 1000;
    case "messageboard_posted":
    case "messageboard_read":
      return 900;
    case "tool_completed":
      return 820;
    default:
      return 480;
  }
}
