/**
 * DEVELOPMENT DATA generator. Not evidence.
 * Writes OperatorEventView 1.0.0 JSONL. The first line is a diagnostics sidecar, not an event.
 */
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const NOTICE =
  "DEVELOPMENT DATA — not a real run. Not evidence. Replace with a core-produced trace before demo acceptance. Payload hashes are placeholders, not content hashes.";
const GOAL_NOTE =
  "Development diagnostics sidecar. Not an event. Unavailable to the defender.";

function derived(episodeId, kind, sources) {
  return createHash("sha256")
    .update(`1.0.0|derived|${episodeId}|${kind}|${sources.join(",")}`)
    .digest("hex");
}

function payloadRef(sequence, bytes) {
  return {
    ref_id: `payload_${sequence.toString(16).padStart(16, "0")}`,
    sha256: "0".repeat(64),
    byte_length: bytes,
  };
}

function journal(episodeId) {
  const events = [];
  const attempts = {};
  let world = 0;
  function attemptFor(actor) {
    if (actor === "controller" || actor === "defender" || actor === "detector") return 0;
    attempts[actor] = (attempts[actor] ?? 0) + 1;
    return attempts[actor];
  }
  function emit(input) {
    if (input.kind === "deployment_committed") world += 1;
    const sequence = events.length;
    const event = {
      schema_version: "1.0.0",
      kind: input.kind,
      episode_id: episodeId,
      sequence,
      round_index: input.round,
      attempt_index: input.attempt ?? attemptFor(input.actor),
      world_version: world,
      actor_id: input.actor,
      actor_role: input.role,
      status: input.status ?? "ok",
      monotonic_duration_ns: 1_000_000,
      wall_time_unix_ns: 1_700_000_000_000 + sequence,
      request_id: `req.${sequence}`,
      payload_refs: input.refs ?? [],
      tool_name: null,
      post_id: null,
      char_count: null,
      after_post_id: null,
      returned_count: null,
      clipped: null,
      reward_components: null,
      source_sequences: [],
      deterministic_id: null,
      ...input.fields,
    };
    events.push(event);
    return sequence;
  }
  function modelStart(round, actor) {
    const role = actor === "defender" ? "defender" : "attacker";
    return emit({ kind: "model_call_started", round, actor, role });
  }
  function modelFinish(round, actor, status = "ok") {
    const role = actor === "defender" ? "defender" : "attacker";
    return emit({ kind: "model_call_finished", round, actor, role, status });
  }
  function tool(round, actor, name, { clipped = false } = {}) {
    emit({
      kind: "tool_started",
      round,
      actor,
      role: "attacker",
      fields: { tool_name: name },
    });
    return emit({
      kind: "tool_completed",
      round,
      actor,
      role: "attacker",
      status: clipped ? "clipped" : "ok",
      refs: [payloadRef(events.length, clipped ? 16_384 : 480)],
      fields: { tool_name: name, clipped },
    });
  }
  function post(round, actor, postId, chars) {
    tool(round, actor, "post_to_messageboard");
    return emit({
      kind: "messageboard_posted",
      round,
      actor,
      role: "attacker",
      refs: [payloadRef(events.length, chars)],
      fields: { post_id: postId, char_count: chars },
    });
  }
  function readBoard(round, actor, after, count, clipped = false) {
    tool(round, actor, "read_messageboard");
    return emit({
      kind: "messageboard_read",
      round,
      actor,
      role: "attacker",
      status: clipped ? "clipped" : "ok",
      fields: { after_post_id: after, returned_count: count, clipped },
    });
  }
  function score(kind, round, sources) {
    return emit({
      kind,
      round,
      actor: "detector",
      role: "system",
      attempt: 0,
      fields: {
        source_sequences: sources,
        deterministic_id: derived(episodeId, kind, sources),
      },
    });
  }
  function transition(round, { detection = 0, compromise = 0, newly = 0 } = {}) {
    return emit({
      kind: "transition_completed",
      round,
      actor: "controller",
      role: "controller",
      attempt: 0,
      fields: {
        reward_components: {
          schema_version: "1.0.0",
          detection_bonus: String(detection),
          compromise_penalty: String(compromise),
          decoy_cost: (newly * 0.02).toFixed(2),
          newly_committed_decoys: newly,
        },
      },
    });
  }
  function finish(round) {
    return emit({ kind: "episode_finished", round, actor: "controller", role: "controller", attempt: 0 });
  }
  return { events, modelStart, modelFinish, tool, post, readBoard, score, transition, finish, emit };
}

const ATTACKERS = ["attacker-1", "attacker-2", "attacker-3"];

function detection() {
  const j = journal("ep_dev_detect");
  const cues = {};
  j.emit({ kind: "episode_started", round: 0, actor: "controller", role: "controller", attempt: 0 });
  for (const actor of ATTACKERS) {
    const seq = j.modelStart(0, actor);
    if (actor === "attacker-3") cues.waiting = seq;
  }
  for (const actor of ATTACKERS) j.modelFinish(0, actor);
  j.tool(0, "attacker-1", "search_files");
  j.tool(0, "attacker-2", "list_directory");
  j.tool(0, "attacker-3", "read_file");
  cues.posted = j.post(0, "attacker-1", 1, 96);
  cues["read-arc"] = j.readBoard(0, "attacker-2", 0, 1);
  cues.searching = j.transition(0);
  cues["defender-waiting"] = j.modelStart(1, "defender");
  j.modelFinish(1, "defender");
  j.emit({ kind: "deployment_started", round: 1, actor: "defender", role: "defender", attempt: 0 });
  j.emit({ kind: "deployment_committed", round: 1, actor: "defender", role: "defender", attempt: 0 });
  cues.deployed = j.transition(1, { newly: 2 });
  for (const actor of ATTACKERS) j.modelStart(2, actor);
  for (const actor of ATTACKERS) j.modelFinish(2, actor);
  const inspectedRead = j.tool(2, "attacker-3", "read_file");
  j.score("decoy_exposed", 2, [inspectedRead]);
  j.score("decoy_inspected", 2, [inspectedRead]);
  const login = j.tool(2, "attacker-1", "request_service");
  j.score("decoy_authenticated", 2, [login]);
  j.tool(2, "attacker-2", "search_files");
  cues.inspected = j.transition(2);
  for (const actor of ATTACKERS) j.modelStart(3, actor);
  for (const actor of ATTACKERS) j.modelFinish(3, actor);
  const secret = j.tool(3, "attacker-1", "request_service");
  cues.engaged = j.score("verified_engagement", 3, [secret]);
  j.tool(3, "attacker-2", "search_files");
  cues.continued = j.tool(3, "attacker-3", "list_directory");
  cues["after-engagement"] = j.transition(3, { detection: 1 });
  for (const actor of ATTACKERS) j.modelStart(4, actor);
  for (const actor of ATTACKERS) j.modelFinish(4, actor);
  j.tool(4, "attacker-3", "search_files");
  const flag = j.tool(4, "attacker-2", "request_service");
  cues.compromised = j.score("protected_value_exposed", 4, [flag]);
  j.transition(4, { compromise: 1 });
  cues.end = j.finish(4);
  return { events: j.events, cues };
}

function compromise() {
  const j = journal("ep_dev_compromise");
  const cues = {};
  j.emit({ kind: "episode_started", round: 0, actor: "controller", role: "controller", attempt: 0 });
  for (const actor of ATTACKERS) {
    const seq = j.modelStart(0, actor);
    if (actor === "attacker-3") cues.waiting = seq;
  }
  for (const actor of ATTACKERS) j.modelFinish(0, actor);
  j.tool(0, "attacker-1", "search_files");
  cues["read-not-compromise"] = j.tool(0, "attacker-2", "read_file");
  j.tool(0, "attacker-3", "list_directory");
  cues.searching = j.transition(0);
  j.modelStart(1, "defender");
  j.modelFinish(1, "defender");
  j.emit({ kind: "deployment_started", round: 1, actor: "defender", role: "defender", attempt: 0 });
  j.emit({ kind: "deployment_committed", round: 1, actor: "defender", role: "defender", attempt: 0 });
  cues.deployed = j.transition(1, { newly: 2 });
  for (const actor of ATTACKERS) j.modelStart(2, actor);
  for (const actor of ATTACKERS) j.modelFinish(2, actor);
  const flag = j.tool(2, "attacker-1", "request_service");
  cues.compromised = j.score("protected_value_exposed", 2, [flag]);
  j.transition(2, { compromise: 1 });
  cues.end = j.finish(2);
  return { events: j.events, cues };
}

function miss() {
  const j = journal("ep_dev_miss");
  const cues = {};
  j.emit({ kind: "episode_started", round: 0, actor: "controller", role: "controller", attempt: 0 });
  for (const actor of ATTACKERS) {
    const seq = j.modelStart(0, actor);
    if (actor === "attacker-3") cues.waiting = seq;
  }
  j.modelFinish(0, "attacker-1");
  cues.refused = j.modelFinish(0, "attacker-2", "refused");
  j.modelFinish(0, "attacker-3");
  cues["clipped-search"] = j.tool(0, "attacker-1", "search_files", { clipped: true });
  cues.invalid = j.emit({
    kind: "actor_turn_rejected",
    round: 0,
    actor: "attacker-3",
    role: "attacker",
    status: "invalid",
  });
  cues.posted = j.post(0, "attacker-1", 1, 64);
  cues["read-arc"] = j.readBoard(0, "attacker-1", 0, 1);
  j.transition(0);
  cues["defender-waiting"] = j.modelStart(1, "defender");
  j.modelFinish(1, "defender");
  j.emit({ kind: "deployment_started", round: 1, actor: "defender", role: "defender", attempt: 0 });
  cues.rejected = j.emit({
    kind: "deployment_rejected",
    round: 1,
    actor: "defender",
    role: "defender",
    status: "rejected",
    attempt: 0,
  });
  j.transition(1);
  j.modelStart(2, "defender");
  j.modelFinish(2, "defender");
  j.emit({ kind: "deployment_started", round: 2, actor: "defender", role: "defender", attempt: 0 });
  j.emit({ kind: "deployment_committed", round: 2, actor: "defender", role: "defender", attempt: 0 });
  cues.deployed = j.transition(2, { newly: 2 });
  j.modelStart(3, "attacker-1");
  j.modelFinish(3, "attacker-1");
  const read = j.tool(3, "attacker-1", "read_file");
  j.score("decoy_exposed", 3, [read]);
  cues["read-not-catch"] = read;
  j.transition(3);
  cues.end = j.finish(3);
  return { events: j.events, cues };
}

function tie() {
  const j = journal("ep_dev_tie_run");
  const cues = {};
  j.emit({ kind: "episode_started", round: 0, actor: "controller", role: "controller", attempt: 0 });
  cues.waiting = j.modelStart(0, "attacker-1");
  j.modelStart(0, "attacker-2");
  j.modelStart(0, "attacker-3");
  for (const actor of ATTACKERS) j.modelFinish(0, actor);
  j.tool(0, "attacker-1", "search_files");
  cues.searching = j.transition(0);
  j.modelStart(1, "defender");
  j.modelFinish(1, "defender");
  j.emit({ kind: "deployment_started", round: 1, actor: "defender", role: "defender", attempt: 0 });
  j.emit({ kind: "deployment_committed", round: 1, actor: "defender", role: "defender", attempt: 0 });
  cues.deployed = j.transition(1, { newly: 2 });
  for (const actor of ATTACKERS) j.modelStart(2, actor);
  for (const actor of ATTACKERS) j.modelFinish(2, actor);
  const secret = j.tool(2, "attacker-1", "request_service");
  cues.engaged = j.score("verified_engagement", 2, [secret]);
  const flag = j.tool(2, "attacker-2", "request_service");
  cues.tie = j.score("protected_value_exposed", 2, [flag]);
  j.tool(2, "attacker-3", "search_files");
  cues.continued = j.transition(2, { compromise: 1 });
  cues.end = j.finish(2);
  return { events: j.events, cues };
}

const stories = [
  ["detection-before-compromise", "Detection before compromise", "release", detection],
  ["genuine-compromise", "Genuine compromise", "release", compromise],
  ["miss", "Miss", "backup", miss],
  ["same-round-tie", "Same-round tie", "backup", tie],
];

const cueFile = { notice: NOTICE, traces: {} };
for (const [id, title, goal, build] of stories) {
  const { events, cues } = build();
  const header = {
    development_data: true,
    notice: NOTICE,
    trace_id: id,
    title,
    workflow_goal: goal,
    goal_unavailable_to_defender: true,
    goal_note: GOAL_NOTE,
  };
  const body = [JSON.stringify(header), ...events.map((event) => JSON.stringify(event)), ""].join("\n");
  writeFileSync(join(root, `${id}.jsonl`), body);
  cueFile.traces[id] = cues;
  console.log(id, events.length, cues);
}
writeFileSync(join(root, "cues.json"), `${JSON.stringify(cueFile, null, 2)}\n`);
