import compromiseRaw from "../../dev-traces/genuine-compromise.jsonl?raw";
import detectionRaw from "../../dev-traces/detection-before-compromise.jsonl?raw";
import missRaw from "../../dev-traces/miss.jsonl?raw";
import tieRaw from "../../dev-traces/same-round-tie.jsonl?raw";
import { DEVELOPMENT_NOTICE } from "../copy";
import { parseObserverEvent, type ObserverEvent } from "../events/schema";

export interface DevTrace {
  id: string;
  title: string;
  notice: string;
  developmentData: boolean;
  workflowGoal: "release" | "backup" | null;
  goalNote: string;
  events: ObserverEvent[];
  errors: string[];
}

export function parseDevTrace(raw: string): DevTrace {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const header = JSON.parse(lines[0] ?? "{}") as {
    development_data?: boolean;
    notice?: string;
    trace_id?: string;
    title?: string;
    workflow_goal?: string;
    goal_note?: string;
  };
  if (header.development_data !== true) {
    throw new Error("Refusing a trace that is not labeled DEVELOPMENT DATA.");
  }
  const events: ObserverEvent[] = [];
  const errors: string[] = [];
  for (const line of lines.slice(1)) {
    let rawEvent: unknown;
    try {
      rawEvent = JSON.parse(line);
    } catch {
      errors.push("A development-trace line was not JSON.");
      continue;
    }
    const parsed = parseObserverEvent(rawEvent);
    if (!parsed.ok) errors.push(parsed.error);
    else events.push(parsed.event);
  }
  const goal = header.workflow_goal === "release" || header.workflow_goal === "backup" ? header.workflow_goal : null;
  if (!goal) errors.push("Development diagnostics are missing a release or backup workflow goal.");
  return {
    id: header.trace_id ?? "development-trace",
    title: header.title ?? "Development trace",
    notice: header.notice ?? DEVELOPMENT_NOTICE,
    developmentData: true,
    workflowGoal: goal,
    goalNote:
      header.goal_note ??
      "Development diagnostics sidecar. Not an event. Unavailable to the defender.",
    events,
    errors,
  };
}

export const DEV_TRACES: DevTrace[] = [
  parseDevTrace(detectionRaw),
  parseDevTrace(compromiseRaw),
  parseDevTrace(missRaw),
  parseDevTrace(tieRaw),
];

export function traceById(id: string): DevTrace {
  return DEV_TRACES.find((trace) => trace.id === id) ?? DEV_TRACES[0];
}
