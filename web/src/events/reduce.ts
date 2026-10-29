/**
 * Project a prefix of operator events into scene state.
 * This is not an episode scheduler. It never creates a path, a hit, a decoy id,
 * a post body, or a deployment slot that the operator projection omitted.
 */

import type { AreaId, StandId } from "./areas";
import { isFileTool, type ObserverEvent, type ToolName } from "./schema";

export type { StandId };

const SHAPES = ["circle", "square", "diamond"] as const;
export type TokenShape = (typeof SHAPES)[number];

const BOUNDARY_KINDS = new Set<ObserverEvent["kind"]>([
  "deployment_started",
  "deployment_committed",
  "deployment_rejected",
  "transition_completed",
  "episode_finished",
]);

export type AttackerStatus = "idle" | "waiting_model" | "in_round" | "finished" | "refused";

export interface AttackerState {
  id: string;
  label: string;
  stand: StandId;
  intentStand: StandId;
  status: AttackerStatus;
  shape: TokenShape;
  lastTool: string | null;
  lastSequence: number | null;
  note: string | null;
}

export interface Highlight {
  area: AreaId;
  path: string;
  line: number;
  query: string;
  sequence: number;
  round: number;
  actorId: string | null;
  clipped: boolean;
}

export interface DeploymentView {
  id: string;
  templateId: string;
  slotId: string;
  contextId: string;
  description: string;
  area: AreaId | null;
  files: string[];
  accountStatus: string | null;
  diff: string | null;
  sequence: number;
  transactionId: string | null;
}

export interface BoardPost {
  id: string;
  postId: number;
  authorId: string;
  charCount: number;
  round: number;
  sequence: number;
}

export interface Arc {
  id: string;
  kind: "post" | "read";
  actorId: string;
  postId: string | null;
  sequence: number;
  round: number;
}

export interface EngagementRecord {
  sequence: number;
  round: number;
  attempt: number;
  actorId: string;
  sourceSequences: number[];
}

export interface CompromiseRecord {
  sequence: number;
  round: number;
  attempt: number;
  actorId: string;
  sourceSequences: number[];
}

export interface Scene {
  episodeId: string | null;
  events: ObserverEvent[];
  round: number;
  worldVersion: number;
  attackers: Record<string, AttackerState>;
  attackerOrder: string[];
  /** Always empty. Hit paths are not on the operator projection. */
  highlights: Highlight[];
  /** Always empty. Deployment specs and slots are not on the operator projection. */
  deployments: DeploymentView[];
  deploymentPhase: "idle" | "started" | "committed" | "rejected";
  deploymentCommits: number;
  deploymentRejections: number;
  posts: BoardPost[];
  arcs: Arc[];
  exposedEvents: number;
  inspectedEvents: number;
  authenticatedEvents: number;
  engagements: EngagementRecord[];
  compromise: CompromiseRecord | null;
  detectionBeforeCompromise: boolean;
  tie: boolean;
  leadRounds: number | null;
  leadAttempts: number | null;
  decoysCommitted: number;
  decoyCostCents: number;
  rewardTransitions: number;
  surrogateDetection: boolean;
  surrogateCompromise: boolean;
  defenderWaiting: boolean;
  finished: boolean;
  gaps: string[];
  moveEpoch: number;
  committedThrough: number;
}

export function emptyScene(): Scene {
  return {
    episodeId: null,
    events: [],
    round: 0,
    worldVersion: 0,
    attackers: {},
    attackerOrder: [],
    highlights: [],
    deployments: [],
    deploymentPhase: "idle",
    deploymentCommits: 0,
    deploymentRejections: 0,
    posts: [],
    arcs: [],
    exposedEvents: 0,
    inspectedEvents: 0,
    authenticatedEvents: 0,
    engagements: [],
    compromise: null,
    detectionBeforeCompromise: false,
    tie: false,
    leadRounds: null,
    leadAttempts: null,
    decoysCommitted: 0,
    decoyCostCents: 0,
    rewardTransitions: 0,
    surrogateDetection: false,
    surrogateCompromise: false,
    defenderWaiting: false,
    finished: false,
    gaps: [],
    moveEpoch: 0,
    committedThrough: -1,
  };
}

function ensureAttacker(scene: Scene, id: string, role: ObserverEvent["actorRole"]): AttackerState | null {
  if (role !== "attacker") return null;
  const existing = scene.attackers[id];
  if (existing) return existing;
  const shape = SHAPES[scene.attackerOrder.length] ?? "circle";
  const created: AttackerState = {
    id,
    label: id,
    stand: "bench",
    intentStand: "bench",
    status: "idle",
    shape,
    lastTool: null,
    lastSequence: null,
    note: null,
  };
  scene.attackers[id] = created;
  scene.attackerOrder.push(id);
  return created;
}

function commitThrough(scene: Scene, round: number): void {
  if (round <= scene.committedThrough) return;
  let moved = false;
  for (const attacker of Object.values(scene.attackers)) {
    if (attacker.intentStand !== attacker.stand) {
      attacker.stand = attacker.intentStand;
      moved = true;
    }
  }
  scene.committedThrough = round;
  if (moved) scene.moveEpoch += 1;
}

function intentForTool(tool: ToolName): StandId | null {
  if (tool === "request_service") return "service";
  if (isFileTool(tool)) return "withheld";
  return null;
}

function applyEvent(scene: Scene, event: ObserverEvent): void {
  if (scene.events.some((existing) => existing.episodeId === event.episodeId && existing.sequence === event.sequence)) {
    return;
  }
  const previous = scene.events[scene.events.length - 1];
  if (previous && previous.episodeId === event.episodeId) {
    if (event.sequence > previous.sequence + 1) {
      scene.gaps.push(`Sequence gap ${previous.sequence + 1}–${event.sequence - 1}`);
    }
    if (event.roundIndex < previous.roundIndex) scene.gaps.push(`Round index decreased at seq ${event.sequence}`);
    if (event.worldVersion < previous.worldVersion) scene.gaps.push(`World version decreased at seq ${event.sequence}`);
  }

  if (event.roundIndex > scene.round) {
    commitThrough(scene, scene.round);
    scene.round = event.roundIndex;
  } else {
    scene.round = Math.max(scene.round, event.roundIndex);
  }
  if (BOUNDARY_KINDS.has(event.kind)) commitThrough(scene, event.roundIndex);

  scene.worldVersion = Math.max(scene.worldVersion, event.worldVersion);
  if (!scene.episodeId) scene.episodeId = event.episodeId;
  scene.events.push(event);

  const attacker = ensureAttacker(scene, event.actorId, event.actorRole);
  const defenderCall = event.actorRole === "defender" || event.actorId === "defender";

  switch (event.kind) {
    case "episode_started":
      break;
    case "model_call_started": {
      if (defenderCall) {
        scene.defenderWaiting = true;
        break;
      }
      if (!attacker || attacker.status === "finished" || attacker.status === "refused") break;
      attacker.status = "waiting_model";
      attacker.lastSequence = event.sequence;
      attacker.note = null;
      break;
    }
    case "model_call_finished": {
      if (defenderCall) {
        scene.defenderWaiting = false;
        break;
      }
      if (!attacker || attacker.status === "finished") break;
      if (event.status === "refused") {
        attacker.status = "refused";
        attacker.note = "Provider refusal. This is not a defender outcome.";
      } else if (attacker.status === "waiting_model") {
        attacker.status = "in_round";
      }
      attacker.lastSequence = event.sequence;
      break;
    }
    case "tool_started": {
      if (!attacker || attacker.status === "finished" || attacker.status === "refused" || !event.toolName) break;
      attacker.status = "in_round";
      attacker.lastTool = event.toolName;
      attacker.lastSequence = event.sequence;
      break;
    }
    case "tool_completed": {
      if (!attacker || attacker.status === "refused" || !event.toolName) break;
      attacker.lastTool = event.toolName;
      attacker.lastSequence = event.sequence;
      if (event.toolName === "finish") {
        attacker.status = "finished";
        attacker.note = "Finished. The summary is not a catch or a compromise.";
        break;
      }
      attacker.status = "in_round";
      if (event.status === "error") attacker.note = "Tool returned an error. This is not a catch.";
      else if (event.clipped) attacker.note = "Delivery clipped. Omitted bytes are not shown.";
      else attacker.note = null;
      const stand = intentForTool(event.toolName);
      if (stand) attacker.intentStand = stand;
      break;
    }
    case "actor_turn_rejected": {
      if (!attacker || attacker.status === "finished" || attacker.status === "refused") break;
      attacker.status = "in_round";
      attacker.lastSequence = event.sequence;
      attacker.note = "Invalid turn. Nothing was executed.";
      break;
    }
    case "messageboard_posted": {
      if (event.postId === null || event.charCount === null) break;
      scene.posts.push({
        id: String(event.postId),
        postId: event.postId,
        authorId: event.actorId,
        charCount: event.charCount,
        round: event.roundIndex,
        sequence: event.sequence,
      });
      scene.arcs.push({
        id: `post-${event.sequence}`,
        kind: "post",
        actorId: event.actorId,
        postId: String(event.postId),
        sequence: event.sequence,
        round: event.roundIndex,
      });
      if (attacker && attacker.status !== "finished" && attacker.status !== "refused") {
        attacker.lastTool = "post_to_messageboard";
        attacker.lastSequence = event.sequence;
        attacker.status = "in_round";
      }
      break;
    }
    case "messageboard_read": {
      scene.arcs.push({
        id: `read-${event.sequence}`,
        kind: "read",
        actorId: event.actorId,
        postId: null,
        sequence: event.sequence,
        round: event.roundIndex,
      });
      if (attacker && attacker.status !== "finished" && attacker.status !== "refused") {
        attacker.lastTool = "read_messageboard";
        attacker.lastSequence = event.sequence;
        attacker.status = "in_round";
      }
      break;
    }
    case "deployment_started":
      scene.deploymentPhase = "started";
      break;
    case "deployment_rejected":
      scene.deploymentPhase = "rejected";
      scene.deploymentRejections += 1;
      break;
    case "deployment_committed":
      scene.deploymentPhase = "committed";
      scene.deploymentCommits += 1;
      break;
    case "decoy_exposed":
      scene.exposedEvents += 1;
      break;
    case "decoy_inspected":
      scene.inspectedEvents += 1;
      break;
    case "decoy_authenticated":
      scene.authenticatedEvents += 1;
      break;
    case "verified_engagement":
      if (scene.engagements.length === 0) {
        scene.engagements.push({
          sequence: event.sequence,
          round: event.roundIndex,
          attempt: event.attemptIndex,
          actorId: event.actorId,
          sourceSequences: event.sourceSequences,
        });
      }
      break;
    case "protected_value_exposed":
      if (!scene.compromise) {
        scene.compromise = {
          sequence: event.sequence,
          round: event.roundIndex,
          attempt: event.attemptIndex,
          actorId: event.actorId,
          sourceSequences: event.sourceSequences,
        };
      }
      break;
    case "transition_completed": {
      const reward = event.rewardComponents;
      if (!reward) break;
      scene.rewardTransitions += 1;
      scene.decoysCommitted += reward.newlyCommittedDecoys;
      scene.decoyCostCents += reward.decoyCostCents;
      if (reward.detectionBonus === 1) scene.surrogateDetection = true;
      if (reward.compromisePenalty === 1) scene.surrogateCompromise = true;
      break;
    }
    case "episode_finished":
      scene.finished = true;
      scene.defenderWaiting = false;
      break;
    default: {
      const neverEvent: never = event.kind;
      void neverEvent;
    }
  }
}

function finalize(scene: Scene): void {
  const engagement = scene.engagements[0] ?? null;
  const compromise = scene.compromise;
  scene.tie = Boolean(engagement && compromise && engagement.round === compromise.round);
  scene.detectionBeforeCompromise = Boolean(engagement && (!compromise || engagement.round < compromise.round));
  if (engagement && compromise && engagement.round <= compromise.round) {
    scene.leadRounds = compromise.round - engagement.round;
    scene.leadAttempts = compromise.attempt - engagement.attempt;
  } else {
    scene.leadRounds = null;
    scene.leadAttempts = null;
  }
}

export function reduceEvents(events: readonly ObserverEvent[]): Scene {
  const scene = emptyScene();
  const ordered = [...events].sort((a, b) => a.sequence - b.sequence || a.episodeId.localeCompare(b.episodeId));
  for (const event of ordered) applyEvent(scene, event);
  finalize(scene);
  return scene;
}
