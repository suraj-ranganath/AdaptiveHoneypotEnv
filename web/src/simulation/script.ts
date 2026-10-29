import { parseObserverEvent, type ObserverEvent } from "../events/schema";

export const SIMULATION_BANNER = "Simulation: illustrative scripted episode, not a recorded run.";

export const SIMULATION_WHY =
  "Real episodes run attacker agents against a live, Docker-contained SecretStorage service with real decoy credentials. That trusted controller can't safely run on a public static host, so this page plays an illustrative scripted episode that follows the environment's design. Real runs are recorded and replayed separately.";

export interface SimulationScript {
  simulated: true;
  title: string;
  workflowGoal: "release" | "backup" | null;
  goalNote: string;
  events: ObserverEvent[];
}

export function parseSimulationScript(raw: string): SimulationScript {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  let header: Record<string, unknown>;
  try {
    header = JSON.parse(lines[0] ?? "{}") as Record<string, unknown>;
  } catch {
    throw new Error("Simulation header was not JSON.");
  }
  if (header.simulated !== true) {
    throw new Error("Refusing a file that is not marked simulated.");
  }
  if (header.development_data === true) {
    throw new Error("A simulation file cannot be labeled as development data.");
  }
  const events: ObserverEvent[] = [];
  for (const line of lines.slice(1)) {
    let rawEvent: unknown;
    try {
      rawEvent = JSON.parse(line);
    } catch {
      throw new Error("A simulation line was not JSON.");
    }
    const parsed = parseObserverEvent(rawEvent);
    if (!parsed.ok) throw new Error(parsed.error);
    events.push(parsed.event);
  }
  if (events.length === 0) throw new Error("Simulation file has no events.");
  const goal = header.workflow_goal === "release" || header.workflow_goal === "backup" ? header.workflow_goal : null;
  return {
    simulated: true,
    title: typeof header.title === "string" ? header.title : "Simulation",
    workflowGoal: goal,
    goalNote:
      typeof header.goal_note === "string"
        ? header.goal_note
        : "Script annotation, not an event. Unavailable to the defender.",
    events,
  };
}
