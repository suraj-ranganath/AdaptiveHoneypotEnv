/**
 * The only event adapter in the observer.
 *
 * Wire format: `OperatorEventView` from
 * `adaptivehoneypotenv/contracts/events.py` (schema 1.0.0, extra forbidden).
 * Payload bytes, paths, hit lists, post text, deployment specs, and the
 * private workflow goal are not fields of this view. Unknown keys are rejected
 * so they cannot become a drawing.
 */

export const EVENT_SCHEMA_VERSION = "1.0.0" as const;

export const EVENT_KINDS = [
  "episode_started",
  "model_call_started",
  "model_call_finished",
  "tool_started",
  "tool_completed",
  "actor_turn_rejected",
  "messageboard_posted",
  "messageboard_read",
  "deployment_started",
  "deployment_committed",
  "deployment_rejected",
  "decoy_exposed",
  "decoy_inspected",
  "decoy_authenticated",
  "verified_engagement",
  "protected_value_exposed",
  "transition_completed",
  "episode_finished",
] as const;

export type EventKind = (typeof EVENT_KINDS)[number];

export const EVENT_STATUSES = ["ok", "error", "rejected", "invalid", "refused", "clipped"] as const;
export type EventStatus = (typeof EVENT_STATUSES)[number];

export const ACTOR_ROLES = ["operator", "controller", "defender", "attacker", "system"] as const;
export type ActorRole = (typeof ACTOR_ROLES)[number];

export const TOOL_NAMES = [
  "list_directory",
  "search_files",
  "read_file",
  "request_service",
  "post_to_messageboard",
  "read_messageboard",
  "finish",
] as const;
export type ToolName = (typeof TOOL_NAMES)[number];

const SCORING_KINDS = new Set<EventKind>([
  "decoy_exposed",
  "decoy_inspected",
  "decoy_authenticated",
  "verified_engagement",
  "protected_value_exposed",
]);

const FILE_TOOLS = new Set<ToolName>(["list_directory", "search_files", "read_file"]);

export const OPERATOR_EVENT_KEYS = [
  "schema_version",
  "kind",
  "episode_id",
  "sequence",
  "round_index",
  "attempt_index",
  "world_version",
  "actor_id",
  "actor_role",
  "status",
  "monotonic_duration_ns",
  "wall_time_unix_ns",
  "request_id",
  "payload_refs",
  "tool_name",
  "post_id",
  "char_count",
  "after_post_id",
  "returned_count",
  "clipped",
  "reward_components",
  "source_sequences",
  "deterministic_id",
] as const;

const KEY_SET = new Set<string>(OPERATOR_EVENT_KEYS);

export interface PayloadRef {
  refId: string;
  sha256: string;
  byteLength: number;
}

export interface RewardComponents {
  schemaVersion: "1.0.0";
  detectionBonus: 0 | 1;
  compromisePenalty: 0 | 1;
  decoyCostCents: number;
  newlyCommittedDecoys: 0 | 1 | 2;
}

/** One operator-projection event. Field names are the view, not the full journal. */
export interface ObserverEvent {
  schemaVersion: "1.0.0";
  kind: EventKind;
  episodeId: string;
  sequence: number;
  roundIndex: number;
  attemptIndex: number;
  worldVersion: number;
  actorId: string;
  actorRole: ActorRole;
  status: EventStatus;
  monotonicDurationNs: number;
  wallTimeUnixNs: number;
  requestId: string;
  payloadRefs: PayloadRef[];
  toolName: ToolName | null;
  postId: number | null;
  charCount: number | null;
  afterPostId: number | null;
  returnedCount: number | null;
  clipped: boolean | null;
  rewardComponents: RewardComponents | null;
  sourceSequences: number[];
  deterministicId: string | null;
}

export type ParseResult =
  | { ok: true; event: ObserverEvent }
  | { ok: false; error: string; sequence?: number; kind?: string };

export function isEventKind(value: string): value is EventKind {
  return (EVENT_KINDS as readonly string[]).includes(value);
}

export function isFileTool(tool: ToolName): boolean {
  return FILE_TOOLS.has(tool);
}

export function eventStreamId(episodeId: string, sequence: number): string {
  return `${episodeId}:${sequence}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeInt(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) return null;
  return value;
}

// Unix nanoseconds and long monotonic clocks sit above Number.MAX_SAFE_INTEGER.
// They remain integers; only the low bits are not exact in IEEE-754.
function clockInt(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  if (!Number.isInteger(value)) return null;
  return value;
}

function decimalCents(value: unknown): number | null {
  let text: string;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return null;
    text = value.toString();
    if (text.includes("e") || text.includes("E")) return null;
  } else if (typeof value === "string") {
    text = value.trim();
  } else {
    return null;
  }
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const [whole, frac = ""] = text.split(".");
  if (frac.length > 2 && !/^0+$/.test(frac.slice(2))) return null;
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  return Number.isSafeInteger(cents) ? cents : null;
}

function parseReward(value: unknown): RewardComponents | string | null {
  if (value == null) return null;
  if (!isRecord(value)) return "reward_components must be an object";
  const allowed = new Set([
    "schema_version",
    "detection_bonus",
    "compromise_penalty",
    "decoy_cost",
    "newly_committed_decoys",
  ]);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) return `reward_components.${key} is not on RewardComponents`;
  }
  if (value.schema_version !== "1.0.0") return "reward_components.schema_version must be 1.0.0";
  const detection = decimalCents(value.detection_bonus);
  const compromise = decimalCents(value.compromise_penalty);
  const cost = decimalCents(value.decoy_cost);
  const newly = safeInt(value.newly_committed_decoys);
  if (detection !== 0 && detection !== 100) return "detection_bonus is 0 or 1";
  if (compromise !== 0 && compromise !== 100) return "compromise_penalty is 0 or 1";
  if (newly === null || newly < 0 || newly > 2) return "newly_committed_decoys must be 0, 1, or 2";
  if (cost === null || cost !== 2 * newly) return "decoy_cost must be 0.02 per newly committed decoy";
  return {
    schemaVersion: "1.0.0",
    detectionBonus: detection === 100 ? 1 : 0,
    compromisePenalty: compromise === 100 ? 1 : 0,
    decoyCostCents: cost,
    newlyCommittedDecoys: newly as 0 | 1 | 2,
  };
}

function parseRefs(value: unknown): PayloadRef[] | string {
  if (value == null) return [];
  if (!Array.isArray(value)) return "payload_refs must be an array";
  const refs: PayloadRef[] = [];
  for (const item of value) {
    if (!isRecord(item)) return "payload ref must be an object";
    for (const key of Object.keys(item)) {
      if (key !== "ref_id" && key !== "sha256" && key !== "byte_length") {
        return `payload ref field ${key} is not on PayloadRef`;
      }
    }
    if (typeof item.ref_id !== "string" || !/^payload_[0-9a-f]{16,64}$/.test(item.ref_id)) {
      return "payload ref_id is invalid";
    }
    if (typeof item.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(item.sha256)) {
      return "payload sha256 is invalid";
    }
    const length = safeInt(item.byte_length);
    if (length === null || length < 0 || length > 1_048_576) return "payload byte_length is invalid";
    refs.push({ refId: item.ref_id, sha256: item.sha256, byteLength: length });
  }
  return refs;
}

function parseSources(value: unknown): number[] | string {
  if (value == null) return [];
  if (!Array.isArray(value)) return "source_sequences must be an array";
  const sources: number[] = [];
  for (const item of value) {
    const sequence = safeInt(item);
    if (sequence === null || sequence < 0) return "source_sequences must be non-negative integers";
    sources.push(sequence);
  }
  return sources;
}

function nullableInt(value: unknown, label: string): number | null | string {
  if (value == null) return null;
  const parsed = safeInt(value);
  if (parsed === null) return `${label} must be an integer`;
  return parsed;
}

function shapeError(event: ObserverEvent): string | null {
  const scoring = SCORING_KINDS.has(event.kind);
  const tool = event.kind === "tool_started" || event.kind === "tool_completed";
  const posted = event.kind === "messageboard_posted";
  const read = event.kind === "messageboard_read";
  const transition = event.kind === "transition_completed";

  if (tool) {
    if (!event.toolName) return `${event.kind} requires tool_name`;
    if (event.actorRole !== "attacker") return "tool events belong to an attacker";
    if (event.kind === "tool_started" && event.clipped !== null) return "tool_started has no clipped flag";
    if (event.kind === "tool_completed" && event.clipped === null) return "tool_completed requires clipped";
  } else if (event.toolName !== null) {
    return "tool_name is only present on tool events";
  }

  if (posted) {
    if (event.actorRole !== "attacker") return "a post belongs to an attacker";
    if (event.postId === null || event.postId < 1) return "messageboard_posted requires post_id ≥ 1";
    if (event.charCount === null || event.charCount < 1 || event.charCount > 2000) {
      return "messageboard_posted requires char_count from 1 to 2000";
    }
  } else if (event.postId !== null || event.charCount !== null) {
    return "post_id and char_count are only present on messageboard_posted";
  }

  if (read) {
    if (event.actorRole !== "attacker") return "a board read belongs to an attacker";
    if (event.afterPostId === null || event.afterPostId < 0) return "messageboard_read requires after_post_id ≥ 0";
    if (event.returnedCount === null || event.returnedCount < 0 || event.returnedCount > 20) {
      return "messageboard_read requires returned_count from 0 to 20";
    }
    if (event.clipped === null) return "messageboard_read requires clipped";
  } else if (!tool && (event.afterPostId !== null || event.returnedCount !== null)) {
    return "after_post_id and returned_count are only present on messageboard_read";
  } else if (!tool && event.clipped !== null) {
    return "clipped is only present on tool_completed and messageboard_read";
  }

  if (tool && (event.afterPostId !== null || event.returnedCount !== null)) {
    return "tool events do not carry board-read fields";
  }

  if (transition) {
    if (!event.rewardComponents) return "transition_completed requires reward_components";
  } else if (event.rewardComponents) {
    return "reward_components is only present on transition_completed";
  }

  if (scoring) {
    if (event.sourceSequences.length === 0) return `${event.kind} cites at least one source sequence`;
    if (!event.deterministicId || !/^[0-9a-f]{64}$/.test(event.deterministicId)) {
      return `${event.kind} requires a 64-hex deterministic_id`;
    }
  } else if (event.sourceSequences.length > 0 || event.deterministicId !== null) {
    return "source citations are only present on scoring events";
  }

  if (scoring || event.sourceSequences.length > 0) {
    const ordered = [...event.sourceSequences];
    if (new Set(ordered).size !== ordered.length) return "source sequences must be unique";
    if (ordered.some((source, index) => index > 0 && ordered[index - 1] >= source)) {
      return "source sequences must be strictly increasing";
    }
    if (ordered.some((source) => source >= event.sequence)) {
      return "source sequences must precede the derived event";
    }
  }
  return null;
}

export function parseObserverEvent(raw: unknown): ParseResult {
  if (!isRecord(raw)) return { ok: false, error: "event is not an object" };
  const extra = Object.keys(raw).filter((key) => !KEY_SET.has(key));
  const sequencePeek = safeInt(raw.sequence);
  const kindPeek = typeof raw.kind === "string" ? raw.kind : undefined;
  if (extra.length > 0) {
    return {
      ok: false,
      error: `Unknown field${extra.length === 1 ? "" : "s"}: ${extra.join(", ")}. The operator projection forbids them.`,
      sequence: sequencePeek ?? undefined,
      kind: kindPeek,
    };
  }
  if (raw.schema_version !== EVENT_SCHEMA_VERSION) {
    return {
      ok: false,
      error: "schema_version must be 1.0.0",
      sequence: sequencePeek ?? undefined,
      kind: kindPeek,
    };
  }
  if (!kindPeek || !isEventKind(kindPeek)) {
    return {
      ok: false,
      error: `Unrecognized event kind${kindPeek ? `: ${kindPeek}` : ""}. It is not drawn.`,
      sequence: sequencePeek ?? undefined,
      kind: kindPeek,
    };
  }
  const sequence = safeInt(raw.sequence);
  if (sequence === null || sequence < 0) {
    return { ok: false, error: "sequence must be an integer ≥ 0", kind: kindPeek };
  }
  const episodeId = raw.episode_id;
  if (typeof episodeId !== "string" || !/^ep_[A-Za-z0-9_-]{8,64}$/.test(episodeId)) {
    return { ok: false, error: "episode_id does not match the journal pattern", sequence, kind: kindPeek };
  }
  const roundIndex = safeInt(raw.round_index);
  const attemptIndex = safeInt(raw.attempt_index);
  const worldVersion = safeInt(raw.world_version);
  const duration = clockInt(raw.monotonic_duration_ns);
  const wall = clockInt(raw.wall_time_unix_ns);
  if (roundIndex === null || roundIndex < 0) return { ok: false, error: "round_index must be an integer ≥ 0", sequence, kind: kindPeek };
  if (attemptIndex === null || attemptIndex < 0) {
    return { ok: false, error: "attempt_index must be an integer ≥ 0", sequence, kind: kindPeek };
  }
  if (worldVersion === null || worldVersion < 0) {
    return { ok: false, error: "world_version must be an integer ≥ 0", sequence, kind: kindPeek };
  }
  if (duration === null || duration < 0) {
    return { ok: false, error: "monotonic_duration_ns must be an integer ≥ 0", sequence, kind: kindPeek };
  }
  if (wall === null || wall < 0) {
    return { ok: false, error: "wall_time_unix_ns must be an integer ≥ 0", sequence, kind: kindPeek };
  }
  if (typeof raw.actor_id !== "string" || !/^[a-z][a-z0-9_-]{0,63}$/.test(raw.actor_id)) {
    return { ok: false, error: "actor_id does not match the principal pattern", sequence, kind: kindPeek };
  }
  if (typeof raw.actor_role !== "string" || !(ACTOR_ROLES as readonly string[]).includes(raw.actor_role)) {
    return { ok: false, error: "actor_role is not a known principal role", sequence, kind: kindPeek };
  }
  if (typeof raw.status !== "string" || !(EVENT_STATUSES as readonly string[]).includes(raw.status)) {
    return { ok: false, error: "status is not a known event status", sequence, kind: kindPeek };
  }
  if (typeof raw.request_id !== "string" || !/^[A-Za-z0-9_.:-]{1,128}$/.test(raw.request_id)) {
    return { ok: false, error: "request_id does not match the journal pattern", sequence, kind: kindPeek };
  }

  const payloadRefs = parseRefs(raw.payload_refs);
  if (typeof payloadRefs === "string") return { ok: false, error: payloadRefs, sequence, kind: kindPeek };
  const toolRaw = raw.tool_name;
  let toolName: ToolName | null = null;
  if (toolRaw != null) {
    if (typeof toolRaw !== "string" || !(TOOL_NAMES as readonly string[]).includes(toolRaw)) {
      return { ok: false, error: "tool_name is not one of the seven attacker tools", sequence, kind: kindPeek };
    }
    toolName = toolRaw as ToolName;
  }
  const postId = nullableInt(raw.post_id, "post_id");
  const charCount = nullableInt(raw.char_count, "char_count");
  const afterPostId = nullableInt(raw.after_post_id, "after_post_id");
  const returnedCount = nullableInt(raw.returned_count, "returned_count");
  if (typeof postId === "string") return { ok: false, error: postId, sequence, kind: kindPeek };
  if (typeof charCount === "string") return { ok: false, error: charCount, sequence, kind: kindPeek };
  if (typeof afterPostId === "string") return { ok: false, error: afterPostId, sequence, kind: kindPeek };
  if (typeof returnedCount === "string") return { ok: false, error: returnedCount, sequence, kind: kindPeek };
  let clipped: boolean | null = null;
  if (raw.clipped != null) {
    if (typeof raw.clipped !== "boolean") return { ok: false, error: "clipped must be a boolean", sequence, kind: kindPeek };
    clipped = raw.clipped;
  }
  const reward = parseReward(raw.reward_components);
  if (typeof reward === "string") return { ok: false, error: reward, sequence, kind: kindPeek };
  const sources = parseSources(raw.source_sequences);
  if (typeof sources === "string") return { ok: false, error: sources, sequence, kind: kindPeek };
  let deterministicId: string | null = null;
  if (raw.deterministic_id != null) {
    if (typeof raw.deterministic_id !== "string") {
      return { ok: false, error: "deterministic_id must be a string", sequence, kind: kindPeek };
    }
    deterministicId = raw.deterministic_id;
  }

  const event: ObserverEvent = {
    schemaVersion: "1.0.0",
    kind: kindPeek,
    episodeId,
    sequence,
    roundIndex,
    attemptIndex,
    worldVersion,
    actorId: raw.actor_id,
    actorRole: raw.actor_role as ActorRole,
    status: raw.status as EventStatus,
    monotonicDurationNs: duration,
    wallTimeUnixNs: wall,
    requestId: raw.request_id,
    payloadRefs,
    toolName,
    postId,
    charCount,
    afterPostId,
    returnedCount,
    clipped,
    rewardComponents: reward,
    sourceSequences: sources,
    deterministicId,
  };
  const shape = shapeError(event);
  if (shape) return { ok: false, error: shape, sequence, kind: kindPeek };
  return { ok: true, event };
}
