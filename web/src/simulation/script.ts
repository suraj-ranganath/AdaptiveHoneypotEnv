import { isAreaId, type AreaId, type StandId } from "../events/areas";
import type { AttackerStatus, Arc } from "../events/reduce";
import { TOOL_NAMES, type ToolName } from "../events/schema";

export const SIMULATION_BANNER = "Simulation: illustrative scripted episode, not a recorded run.";

export const DEFAULT_SIMULATION_WHY =
  "Real episodes run attacker agents against a live, Docker-contained SecretStorage service with real decoy credentials, and that trusted controller cannot safely run on a public static host. This page plays an illustrative scripted episode that follows the environment design while real runs are recorded and replayed separately.";

export const SIMULATION_WHY = DEFAULT_SIMULATION_WHY;

export type SimulationMoment =
  | "setup"
  | "scan"
  | "coordination"
  | "defender"
  | "deploy"
  | "service"
  | "catch"
  | "aftermath"
  | "finish";

export type SimulationTool = ToolName | "none" | "thinking";

export interface SimulationHeader {
  simulated: true;
  scriptId: string;
  title: string;
  workflowGoal: "release" | "backup" | null;
  goalNote: string;
  why: string;
  teamAttemptBudget: number;
  attemptsPerDefenderDecision: number;
  maxDecoys: number;
  rewardFormula: string;
  baseline: { title: string; summary: string } | null;
}

export interface SimulationAttacker {
  id: string;
  label: string;
  stand: StandId;
  status: AttackerStatus;
  tool: SimulationTool;
  note: string;
}

export interface SimulationHighlight {
  area: AreaId;
  query: string;
  actorId: string | null;
  clipped: boolean;
}

export interface SimulationDeployment {
  id: string;
  templateId: string;
  slotId: string;
  contextId: "release" | "backup";
  area: AreaId;
  path: string;
  description: string;
  accountHint: string;
  engaged: boolean;
}

export interface SimulationPost {
  id: string;
  postId: number;
  authorId: string;
  round: number;
  text: string;
  seenBy: string[];
}

export interface SimulationDefenderView {
  observation: string[];
  inference: string;
  action: string;
}

export interface SimulationReward {
  detectionBonus: 0 | 1;
  compromisePenalty: 0 | 1;
  newlyCommittedDecoys: 0 | 1 | 2;
  decoyCost: number;
  cumulativeTotal: number;
}

export interface SimulationFrame {
  sequence: number;
  durationMs: number;
  round: number;
  kind: SimulationMoment;
  title: string;
  subtitle: string;
  attemptWindowUsed: number;
  teamAttemptsUsed: number;
  attackers: SimulationAttacker[];
  highlights: SimulationHighlight[];
  deployments: SimulationDeployment[];
  posts: SimulationPost[];
  arcs: Arc[];
  defender: SimulationDefenderView;
  toolLog: string[];
  serviceCall: string | null;
  reward: SimulationReward;
  engagement: boolean;
  compromise: boolean;
  outcomeNote: string | null;
}

export interface SimulationScript {
  header: SimulationHeader;
  frames: SimulationFrame[];
}

const STATUS_SET = new Set<AttackerStatus>(["idle", "waiting_model", "in_round", "finished", "refused"]);
const STAND_SET = new Set<StandId>(["bench", "ops", "withheld", "source", "ci", "deploy", "runbooks", "integrations", "service"]);
const MOMENT_SET = new Set<SimulationMoment>([
  "setup",
  "scan",
  "coordination",
  "defender",
  "deploy",
  "service",
  "catch",
  "aftermath",
  "finish",
]);
const SIM_TOOLS = new Set<SimulationTool>([...TOOL_NAMES, "none", "thinking"]);

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown, label: string): string {
  if (typeof value !== "string") throw new Error(`${label} must be a string.`);
  const text = value.trim();
  if (!text) throw new Error(`${label} cannot be empty.`);
  return text;
}

function asOptionalString(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function asInteger(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw new Error(`${label} must be an integer.`);
  }
  return value;
}

function asNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} must be a finite number.`);
  return value;
}

function asStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array.`);
  return value.map((item, index) => asString(item, `${label}[${index}]`));
}

function parseHeader(raw: Record<string, unknown>): SimulationHeader {
  if (raw.simulated !== true) throw new Error("Refusing a file that is not marked simulated: true.");
  const workflow =
    raw.workflow_goal === "release" || raw.workflow_goal === "backup" ? (raw.workflow_goal as "release" | "backup") : null;
  let baseline: SimulationHeader["baseline"] = null;
  if (raw.baseline !== undefined) {
    const base = asRecord(raw.baseline, "baseline");
    baseline = {
      title: asString(base.title, "baseline.title"),
      summary: asString(base.summary, "baseline.summary"),
    };
  }
  return {
    simulated: true,
    scriptId: asOptionalString(raw.script_id, "simulation-demo"),
    title: asOptionalString(raw.title, "Illustrative simulation"),
    workflowGoal: workflow,
    goalNote: asOptionalString(
      raw.goal_note,
      "Script annotation, not an event. Workflow goal is observer-only and unavailable to the defender.",
    ),
    why: asOptionalString(raw.why, DEFAULT_SIMULATION_WHY),
    teamAttemptBudget: raw.team_attempt_budget === undefined ? 90 : asInteger(raw.team_attempt_budget, "team_attempt_budget"),
    attemptsPerDefenderDecision:
      raw.attempts_per_defender_decision === undefined
        ? 6
        : asInteger(raw.attempts_per_defender_decision, "attempts_per_defender_decision"),
    maxDecoys: raw.max_decoys === undefined ? 2 : asInteger(raw.max_decoys, "max_decoys"),
    rewardFormula: asOptionalString(
      raw.reward_formula,
      "r_t = 1[verified engagement before compromise] - 1[genuine compromise] - 0.02[newly committed decoys]",
    ),
    baseline,
  };
}

function parseAttacker(raw: unknown, index: number): SimulationAttacker {
  const item = asRecord(raw, `attackers[${index}]`);
  const stand = asString(item.stand, `attackers[${index}].stand`) as StandId;
  if (!STAND_SET.has(stand)) throw new Error(`attackers[${index}].stand is not a known stand.`);
  const status = asString(item.status, `attackers[${index}].status`) as AttackerStatus;
  if (!STATUS_SET.has(status)) throw new Error(`attackers[${index}].status is not a known attacker status.`);
  const tool = asString(item.tool, `attackers[${index}].tool`) as SimulationTool;
  if (!SIM_TOOLS.has(tool)) throw new Error(`attackers[${index}].tool is not a simulation tool.`);
  return {
    id: asString(item.id, `attackers[${index}].id`),
    label: asString(item.label, `attackers[${index}].label`),
    stand,
    status,
    tool,
    note: asOptionalString(item.note, "—"),
  };
}

function parseHighlight(raw: unknown, index: number): SimulationHighlight {
  const item = asRecord(raw, `highlights[${index}]`);
  const areaText = asString(item.area, `highlights[${index}].area`);
  if (!isAreaId(areaText)) throw new Error(`highlights[${index}].area is not an area id.`);
  return {
    area: areaText,
    query: asString(item.query, `highlights[${index}].query`),
    actorId: typeof item.actor_id === "string" ? item.actor_id : null,
    clipped: item.clipped === true,
  };
}

function parseDeployment(raw: unknown, index: number): SimulationDeployment {
  const item = asRecord(raw, `deployments[${index}]`);
  const areaText = asString(item.area, `deployments[${index}].area`);
  if (!isAreaId(areaText)) throw new Error(`deployments[${index}].area is not an area id.`);
  const context = asString(item.context_id, `deployments[${index}].context_id`);
  if (context !== "release" && context !== "backup") {
    throw new Error(`deployments[${index}].context_id must be release or backup.`);
  }
  const description = asString(item.description, `deployments[${index}].description`);
  if (description.length > 240) throw new Error(`deployments[${index}].description exceeds 240 characters.`);
  return {
    id: asString(item.id, `deployments[${index}].id`),
    templateId: asString(item.template_id, `deployments[${index}].template_id`),
    slotId: asString(item.slot_id, `deployments[${index}].slot_id`),
    contextId: context,
    area: areaText,
    path: asString(item.path, `deployments[${index}].path`),
    description,
    accountHint: asString(item.account_hint, `deployments[${index}].account_hint`),
    engaged: item.engaged === true,
  };
}

function parsePost(raw: unknown, index: number): SimulationPost {
  const item = asRecord(raw, `posts[${index}]`);
  return {
    id: asString(item.id, `posts[${index}].id`),
    postId: asInteger(item.post_id, `posts[${index}].post_id`),
    authorId: asString(item.author_id, `posts[${index}].author_id`),
    round: asInteger(item.round, `posts[${index}].round`),
    text: asString(item.text, `posts[${index}].text`),
    seenBy: item.seen_by === undefined ? [] : asStringArray(item.seen_by, `posts[${index}].seen_by`),
  };
}

function parseArcs(raw: unknown, frame: { sequence: number; round: number }): Arc[] {
  if (raw === undefined) return [];
  if (!Array.isArray(raw)) throw new Error("arcs must be an array.");
  return raw.map((entry, index) => {
    const item = asRecord(entry, `arcs[${index}]`);
    const kind = asString(item.kind, `arcs[${index}].kind`);
    if (kind !== "post" && kind !== "read") throw new Error(`arcs[${index}].kind must be post or read.`);
    return {
      id: typeof item.id === "string" ? item.id : `${kind}-${frame.sequence}-${index}`,
      kind,
      actorId: asString(item.actor_id, `arcs[${index}].actor_id`),
      postId: typeof item.post_id === "string" ? item.post_id : null,
      sequence: frame.sequence,
      round: frame.round,
    };
  });
}

function parseDefender(raw: unknown): SimulationDefenderView {
  const item = asRecord(raw, "defender");
  return {
    observation: asStringArray(item.observation, "defender.observation"),
    inference: asString(item.inference, "defender.inference"),
    action: asString(item.action, "defender.action"),
  };
}

function parseReward(raw: unknown): SimulationReward {
  const item = asRecord(raw, "reward");
  const detection = asInteger(item.detection_bonus, "reward.detection_bonus");
  const compromise = asInteger(item.compromise_penalty, "reward.compromise_penalty");
  const newly = asInteger(item.newly_committed_decoys, "reward.newly_committed_decoys");
  if (detection !== 0 && detection !== 1) throw new Error("reward.detection_bonus must be 0 or 1.");
  if (compromise !== 0 && compromise !== 1) throw new Error("reward.compromise_penalty must be 0 or 1.");
  if (newly < 0 || newly > 2) throw new Error("reward.newly_committed_decoys must be 0, 1, or 2.");
  const decoyCost = asNumber(item.decoy_cost, "reward.decoy_cost");
  const rounded = Math.round(decoyCost * 100) / 100;
  if (Math.abs(rounded - 0.02 * newly) > 0.0001) {
    throw new Error("reward.decoy_cost must match 0.02 * newly_committed_decoys.");
  }
  return {
    detectionBonus: detection as 0 | 1,
    compromisePenalty: compromise as 0 | 1,
    newlyCommittedDecoys: newly as 0 | 1 | 2,
    decoyCost: rounded,
    cumulativeTotal: asNumber(item.cumulative_total, "reward.cumulative_total"),
  };
}

function parseFrame(raw: Record<string, unknown>): SimulationFrame {
  const sequence = asInteger(raw.sequence, "sequence");
  const round = asInteger(raw.round, "round");
  const kind = asString(raw.kind, "kind") as SimulationMoment;
  if (!MOMENT_SET.has(kind)) throw new Error(`kind ${kind} is not a known simulation moment.`);
  const attackersRaw = raw.attackers;
  if (!Array.isArray(attackersRaw) || attackersRaw.length === 0) throw new Error("attackers must be a non-empty array.");
  const attackers = attackersRaw.map((entry, index) => parseAttacker(entry, index));
  const highlightsRaw = Array.isArray(raw.highlights) ? raw.highlights : [];
  const deploymentsRaw = Array.isArray(raw.deployments) ? raw.deployments : [];
  const postsRaw = Array.isArray(raw.posts) ? raw.posts : [];

  return {
    sequence,
    durationMs: raw.duration_ms === undefined ? 950 : asInteger(raw.duration_ms, "duration_ms"),
    round,
    kind,
    title: asString(raw.title, "title"),
    subtitle: asOptionalString(raw.subtitle, ""),
    attemptWindowUsed: asInteger(raw.attempt_window_used, "attempt_window_used"),
    teamAttemptsUsed: asInteger(raw.team_attempts_used, "team_attempts_used"),
    attackers,
    highlights: highlightsRaw.map((entry, index) => parseHighlight(entry, index)),
    deployments: deploymentsRaw.map((entry, index) => parseDeployment(entry, index)),
    posts: postsRaw.map((entry, index) => parsePost(entry, index)),
    arcs: parseArcs(raw.arcs, { sequence, round }),
    defender: parseDefender(raw.defender),
    toolLog: asStringArray(raw.tool_log, "tool_log"),
    serviceCall: typeof raw.service_call === "string" && raw.service_call.trim() ? raw.service_call.trim() : null,
    reward: parseReward(raw.reward),
    engagement: raw.engagement === true,
    compromise: raw.compromise === true,
    outcomeNote: typeof raw.outcome_note === "string" ? raw.outcome_note.trim() || null : null,
  };
}

export function parseSimulationScript(raw: string): SimulationScript {
  const lines = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) throw new Error("Simulation script must include a header and at least one frame.");
  let headerRaw: Record<string, unknown>;
  try {
    headerRaw = asRecord(JSON.parse(lines[0] ?? "{}"), "header");
  } catch {
    throw new Error("Simulation header was not JSON.");
  }
  const header = parseHeader(headerRaw);
  const frames: SimulationFrame[] = [];
  for (const line of lines.slice(1)) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      throw new Error("A simulation frame line was not JSON.");
    }
    frames.push(parseFrame(asRecord(parsed, "frame")));
  }
  frames.sort((a, b) => a.sequence - b.sequence);
  const ids = new Set<string>();
  let previous = -1;
  for (const frame of frames) {
    if (frame.sequence <= previous) throw new Error("Frame sequence numbers must be strictly increasing.");
    previous = frame.sequence;
    if (frame.attemptWindowUsed < 0 || frame.attemptWindowUsed > header.attemptsPerDefenderDecision) {
      throw new Error("attempt_window_used exceeds attempts_per_defender_decision.");
    }
    if (frame.teamAttemptsUsed < 0 || frame.teamAttemptsUsed > header.teamAttemptBudget) {
      throw new Error("team_attempts_used exceeds team_attempt_budget.");
    }
    for (const deployment of frame.deployments) {
      ids.add(deployment.id);
      if (deployment.description.length > 240) {
        throw new Error(`Deployment ${deployment.id} exceeds the 240-character description limit.`);
      }
    }
  }
  if (ids.size > header.maxDecoys) {
    throw new Error(`Simulation shows ${ids.size} unique decoys, beyond max_decoys ${header.maxDecoys}.`);
  }
  return { header, frames };
}
