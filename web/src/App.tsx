import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Arcs } from "./components/Arcs";
import { Counters } from "./components/Counters";
import { Inspector } from "./components/Inspector";
import { Intro } from "./components/Intro";
import { MessageBoard } from "./components/MessageBoard";
import { ModeBadge } from "./components/ModeBadge";
import { Timeline } from "./components/Timeline";
import { DEMO_PROFILE, DEVELOPMENT_NOTICE, SCENARIO_SENTENCE } from "./copy";
import { DEV_TRACES, traceById } from "./dev/traces";
import { standLabel } from "./events/areas";
import { reduceEvents, type AttackerState } from "./events/reduce";
import { mergeEvents } from "./events/stream";
import type { ObserverEvent } from "./events/schema";
import { assertLoopback, createOperatorApi, DEFAULT_OPERATOR_BASE } from "./operator/api";
import { ATTACKER_HEX, attackerColor } from "./scene/palette";
import type { WorkspaceModel } from "./scene/model";
import { Workspace } from "./scene/Workspace";
import { SIMULATION_BANNER, SIMULATION_WHY, parseSimulationScript, type SimulationScript } from "./simulation/script";
import { delayFor } from "./state/playback";
import { resolvePresentation, type RequestedMode } from "./state/presentation";
import { resolveSelection, type Selection } from "./state/selection";
import { useLiveStream } from "./state/useLiveStream";

function defaultMode(params: URLSearchParams): RequestedMode {
  const raw = params.get("mode");
  if (raw === "live" || raw === "replay" || raw === "simulation") return raw;
  return import.meta.env.VITE_DEFAULT_MODE === "simulation" ? "simulation" : "replay";
}

function readOperatorBase(params: URLSearchParams): { base: string; error: string | null } {
  const raw = params.get("operator");
  if (!raw) return { base: DEFAULT_OPERATOR_BASE, error: null };
  try {
    assertLoopback(raw);
    return { base: raw, error: null };
  } catch (error) {
    return {
      base: DEFAULT_OPERATOR_BASE,
      error: error instanceof Error ? error.message : "Operator URL rejected.",
    };
  }
}

function rosterStatus(attacker: AttackerState): string {
  if (attacker.status === "waiting_model") return "Waiting on the model";
  if (attacker.note) return attacker.note;
  if (attacker.lastTool) return attacker.lastTool;
  return "Idle";
}

export function App() {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const operatorSetup = useMemo(() => readOperatorBase(params), [params]);
  const operator = useMemo(() => createOperatorApi(operatorSetup.base), [operatorSetup.base]);
  const stageRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(false);

  const atRaw = params.get("at");
  const atSequence = atRaw !== null && Number.isFinite(Number(atRaw)) ? Number(atRaw) : null;
  const initialMode = useMemo(() => defaultMode(params), [params]);
  const [traceId, setTraceId] = useState(params.get("trace") ?? DEV_TRACES[0].id);
  const [requested, setRequested] = useState<RequestedMode>(initialMode);
  const [screen, setScreen] = useState<"intro" | "run">(
    params.get("screen") === "intro"
      ? "intro"
      : params.get("screen") === "run" || atSequence !== null || initialMode === "simulation"
        ? "run"
        : "intro",
  );
  const [liveEvents, setLiveEvents] = useState<ObserverEvent[]>([]);
  const [liveErrors, setLiveErrors] = useState<string[]>([]);
  const [simulation, setSimulation] = useState<SimulationScript | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(() => {
    if (atSequence === null || initialMode === "simulation") return 0;
    return traceById(params.get("trace") ?? DEV_TRACES[0].id).events.filter((event) => event.sequence <= atSequence).length;
  });
  const [playing, setPlaying] = useState(initialMode === "simulation" && params.get("screen") !== "intro" && atSequence === null);
  const [follow, setFollow] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [pinned, setPinned] = useState(atSequence !== null);
  const [operatorNote, setOperatorNote] = useState<string | null>(operatorSetup.error);
  const [diagnosticsGoal, setDiagnosticsGoal] = useState<"release" | "backup" | null>(null);
  const [diagnosticsNote, setDiagnosticsNote] = useState<string | null>(null);
  const [diagnosticsDevelopment, setDiagnosticsDevelopment] = useState(false);
  const [mapAnchors, setMapAnchors] = useState<Record<string, { x: number; y: number }>>({});
  const [boardAnchors, setBoardAnchors] = useState<Record<string, { x: number; y: number }>>({});

  const trace = traceById(traceId);
  const simulationEvents = useMemo(() => simulation?.events ?? [], [simulation]);
  const events =
    requested === "live" ? liveEvents : requested === "simulation" ? simulationEvents : trace.events;
  const visibleCursor = screen === "intro" ? 0 : cursor;
  const scene = useMemo(() => reduceEvents(events.slice(0, visibleCursor)), [events, visibleCursor]);
  followRef.current = follow;

  const liveUrl = screen === "run" && requested === "live" ? operator.eventsUrl() : null;
  const live = useLiveStream(
    liveUrl,
    useCallback((incoming: ObserverEvent[], errors: string[]) => {
      if (errors.length > 0) setLiveErrors((prev) => [...prev, ...errors].slice(-6));
      if (incoming.length === 0) return;
      setLiveEvents((prev) => {
        const next = mergeEvents(prev, incoming);
        if (followRef.current) queueMicrotask(() => setCursor(next.length));
        return next;
      });
    }, []),
  );

  const developmentData =
    requested === "replay"
      ? trace.developmentData
      : requested === "live"
        ? live.provenance === "development" || diagnosticsDevelopment
        : false;

  useEffect(() => {
    let cancel = false;
    void fetch(`${import.meta.env.BASE_URL}simulation/demo.jsonl`)
      .then((response) => {
        if (!response.ok) throw new Error(`Simulation script HTTP ${response.status}.`);
        return response.text();
      })
      .then((text) => {
        if (!cancel) setSimulation(parseSimulationScript(text));
      })
      .catch((error: unknown) => {
        if (!cancel) setSimulationError(error instanceof Error ? error.message : "Simulation script failed to load.");
      });
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    if (requested !== "live" || screen !== "run") return;
    let cancel = false;
    void operator.diagnostics().then((result) => {
      if (cancel) return;
      setDiagnosticsGoal(result.goal);
      setDiagnosticsNote(result.message);
      setDiagnosticsDevelopment(result.developmentData);
    });
    return () => {
      cancel = true;
    };
  }, [requested, screen, operator]);

  const presentation = resolvePresentation({
    screen,
    requested,
    developmentData,
    connection: live.connection,
  });

  const atApplied = useRef(false);
  useEffect(() => {
    if (atApplied.current || requested !== "simulation" || atSequence === null || simulationEvents.length === 0) return;
    atApplied.current = true;
    const prefix = simulationEvents.filter((event) => event.sequence <= atSequence);
    setCursor(prefix.length);
    setPlaying(false);
    setPinned(true);
    const last = prefix.at(-1);
    if (last) setSelection({ type: "event", sequence: last.sequence });
  }, [requested, atSequence, simulationEvents]);

  useEffect(() => {
    if (screen !== "run" || !playing || requested === "live") return;
    const script = requested === "simulation" ? simulationEvents : trace.events;
    if (requested === "simulation" && script.length === 0) return;
    if (cursor >= script.length) {
      if (requested === "simulation") {
        const timer = window.setTimeout(() => setCursor(0), 900);
        return () => window.clearTimeout(timer);
      }
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => setCursor((current) => current + 1), delayFor(script[cursor]));
    return () => window.clearTimeout(timer);
  }, [screen, playing, requested, cursor, trace.events, simulationEvents]);

  useEffect(() => {
    if (pinned) return;
    const last = scene.events.at(-1);
    setSelection(last ? { type: "event", sequence: last.sequence } : null);
  }, [pinned, scene.events]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
        return;
      }
      if (screen !== "run" || (requested !== "replay" && requested !== "simulation")) return;
      if (event.key === " ") {
        event.preventDefault();
        setPlaying((value) => !value);
      } else if (event.key === "ArrowRight") {
        setPlaying(false);
        const limit = requested === "simulation" ? simulationEvents.length : trace.events.length;
        setCursor((value) => Math.min(limit, value + 1));
      } else if (event.key === "ArrowLeft") {
        setPlaying(false);
        setCursor((value) => Math.max(0, value - 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [screen, requested, trace.events.length, simulationEvents.length]);

  const workflowGoal =
    requested === "replay" ? trace.workflowGoal : requested === "simulation" ? (simulation?.workflowGoal ?? null) : diagnosticsGoal;
  const goalNote =
    requested === "replay"
      ? trace.goalNote
      : requested === "simulation"
        ? (simulation?.goalNote ?? "Script annotation, not an event. Unavailable to the defender.")
        : (diagnosticsNote ?? "The workflow goal is not an event. Live diagnostics load after Start.");

  function pin(next: Selection) {
    setPinned(true);
    setSelection(next);
    setFollow(false);
  }

  function start() {
    setScreen("run");
    setPinned(false);
    setSelection(null);
    setOperatorNote(operatorSetup.error);
    if (requested === "live") {
      setLiveEvents([]);
      setLiveErrors([]);
      setCursor(0);
      setPlaying(false);
      setFollow(true);
      return;
    }
    setCursor(0);
    setPlaying(true);
    setFollow(false);
  }

  function restartSimulation() {
    setPinned(false);
    setSelection(null);
    setFollow(false);
    setCursor(0);
    setPlaying(true);
  }

  async function kill() {
    if (requested === "simulation") {
      setPlaying(false);
      setOperatorNote("Simulation has no operator episode to kill.");
      return;
    }
    const episodeId = scene.episodeId;
    if (!episodeId) {
      setOperatorNote("No episode id in the applied events yet.");
      return;
    }
    if (requested === "replay") setPlaying(false);
    const result = await operator.kill(episodeId);
    setOperatorNote(result.message);
  }

  async function resetEpisode() {
    if (requested === "simulation") {
      restartSimulation();
      setOperatorNote("Simulation restarted from the script. No operator episode was reset.");
      return;
    }
    const episodeId = scene.episodeId ?? "none";
    const result = await operator.reset(episodeId);
    setPinned(false);
    setSelection(null);
    if (requested === "replay") {
      setPlaying(false);
      setCursor(0);
      setOperatorNote(`Recording rewound to the start. ${result.message}`);
      return;
    }
    setLiveEvents([]);
    setCursor(0);
    setFollow(true);
    setOperatorNote(result.message);
  }

  const model = useMemo<WorkspaceModel>(
    () => ({
      tokens: scene.attackerOrder.map((id, index) => {
        const attacker = scene.attackers[id];
        return {
          id,
          label: attacker.label,
          stand: attacker.stand,
          status: attacker.status,
          shape: attacker.shape,
          color: ATTACKER_HEX[index] ?? ATTACKER_HEX[0],
          selected: selection?.type === "attacker" && selection.id === id,
        };
      }),
      highlights: scene.highlights,
      deployments: scene.deployments.map((deployment) => ({
        ...deployment,
        selected: selection?.type === "deployment" && selection.id === deployment.id,
        engaged: false,
      })),
      engagement: scene.engagements.length > 0,
      compromise: scene.compromise !== null,
      defenderWaiting: scene.defenderWaiting,
      defenderSelected: false,
      motion: playing && requested !== "live" ? "play" : "snap",
      moveEpoch: scene.moveEpoch,
    }),
    [scene, selection, playing, requested],
  );

  const attackerIndex = Object.fromEntries(scene.attackerOrder.map((id, index) => [id, index]));
  const labels = Object.fromEntries(scene.attackerOrder.map((id) => [id, scene.attackers[id].label]));
  const waiting = scene.attackerOrder
    .filter((id) => scene.attackers[id].status === "waiting_model")
    .map((id) => scene.attackers[id].label);
  const selectedEvent = resolveSelection(scene, selection);
  const focusDecoyId = selection?.type === "deployment" ? selection.id : null;
  const anchors = { ...mapAnchors, ...boardAnchors };

  const onBoardLayout = useCallback(
    (layout: { board: { x: number; y: number } | null; posts: Record<string, { x: number; y: number }> }) => {
      const next: Record<string, { x: number; y: number }> = {};
      if (layout.board) next.board = layout.board;
      for (const [id, point] of Object.entries(layout.posts)) next[`post:${id}`] = point;
      setBoardAnchors(next);
    },
    [],
  );

  return (
    <div className="app">
      <div className="chrome">
      <header className="top">
        <div className="brand">
          <p className="word">AdaptiveHoneypotEnv</p>
          <p className="sub">Observer · {DEMO_PROFILE.scenarioId}</p>
        </div>
        <div className="top-actions">
          <button type="button" className="ghost" onClick={() => { setScreen("intro"); setPlaying(false); }}>
            Intro
          </button>
          {requested === "replay" && screen === "run" ? (
            <label className="trace-switch">
              Development trace
              <select
                value={traceId}
                onChange={(event) => {
                  setTraceId(event.target.value);
                  setCursor(0);
                  setPlaying(false);
                  setPinned(false);
                }}
              >
                {DEV_TRACES.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button type="button" className="ghost" onClick={() => void kill()}>
            Kill episode
          </button>
          <button type="button" className="ghost" onClick={() => void resetEpisode()}>
            Reset episode
          </button>
        </div>
        <ModeBadge presentation={presentation} />
      </header>
      {requested === "simulation" ? (
        <div className="sim-strip" role="note">
          <p className="sim-banner">{SIMULATION_BANNER}</p>
          <p className="sim-why">{SIMULATION_WHY}</p>
        </div>
      ) : null}
      {developmentData ? <p className="dev-strip">{trace.notice || DEVELOPMENT_NOTICE}</p> : null}
      {operatorNote ? <p className="op-note">{operatorNote}</p> : null}
      {live.detail && requested === "live" && presentation.badge !== "unavailable" ? (
        <p className="op-note">{live.detail}</p>
      ) : null}
      {liveErrors.length > 0 ? <p className="op-note">{liveErrors.at(-1)}</p> : null}
      {trace.errors.length > 0 && requested === "replay" ? <p className="op-note">{trace.errors.at(-1)}</p> : null}
      {simulationError && requested === "simulation" ? <p className="op-note">{simulationError}</p> : null}
      {scene.gaps.length > 0 ? <p className="op-note">Journal gap: {scene.gaps.at(-1)}. Missing events are not invented.</p> : null}
      <p className="goal-run">
        Observer only · workflow goal {workflowGoal ?? "unavailable"}. Unavailable to the defender. {goalNote}
      </p>
      </div>

      <div className="stage" ref={stageRef}>
        <div className="workspace-col">
          <div className="meter-row">
            <div className="round-chip">
              <span>Round</span>
              <strong>{scene.events.length === 0 ? "—" : scene.round}</strong>
            </div>
            {requested === "simulation" ? (
              <div className="round-chip">
                <span>Step</span>
                <strong>{scene.events.length === 0 ? "—" : scene.rewardTransitions}</strong>
              </div>
            ) : null}
          </div>
          {(scene.deploymentPhase !== "idle" ||
            scene.deploymentCommits > 0 ||
            scene.engagements.length > 0 ||
            scene.compromise) && (
            <div className="plates">
              {scene.deploymentPhase === "started" ? <p className="plate deploy">Deployment in progress</p> : null}
              {scene.deploymentCommits > 0 ? <p className="plate deploy">Deployment committed</p> : null}
              {scene.deploymentPhase === "rejected" ? <p className="plate rejected">Deployment rejected</p> : null}
              {scene.engagements.length > 0 ? <p className="plate alert">Verified engagement</p> : null}
              {scene.compromise ? <p className="plate compromise">Genuine compromise</p> : null}
            </div>
          )}
          <Workspace stageRef={stageRef} model={model} onSelect={pin} onAnchors={setMapAnchors} />
          <p className="projection-note">
            Service calls stand on Service. File tools stand together: the path is not on the operator projection, so
            no room is highlighted.
          </p>
          {waiting.length > 0 || scene.defenderWaiting ? (
            <p className="waiting-banner">
              Waiting on the model
              {waiting.length > 0 ? ` — ${waiting.join(", ")}` : ""}
              {scene.defenderWaiting ? " — defender" : ""}. No tool has been chosen for that call yet.
            </p>
          ) : null}
          <ul className="roster">
            {scene.attackerOrder.map((id, index) => {
              const attacker = scene.attackers[id];
              return (
                <li key={id}>
                  <button type="button" onClick={() => pin({ type: "attacker", id })}>
                    <i style={{ background: attackerColor(index) }} />
                    <strong>{attacker.label}</strong>
                    <span>{standLabel(attacker.stand)}</span>
                    <em>{rosterStatus(attacker)}</em>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
        <Arcs arcs={scene.arcs} anchors={anchors} attackerIndex={attackerIndex} />
        <div className="side">
          <MessageBoard
            posts={scene.posts}
            attackerIndex={attackerIndex}
            labels={labels}
            selectedPostId={selection?.type === "post" ? selection.id : null}
            onSelect={(id) => pin({ type: "post", id })}
            onLayout={onBoardLayout}
          />
          <Inspector
            event={selectedEvent}
            scene={scene}
            focusDecoyId={focusDecoyId}
            onSelectSequence={(sequence) => pin({ type: "event", sequence })}
          />
        </div>
        {screen === "intro" ? (
          <Intro
            traces={DEV_TRACES}
            traceId={trace.id}
            mode={requested}
            goal={requested === "replay" ? trace.workflowGoal : requested === "simulation" ? (simulation?.workflowGoal ?? null) : null}
            goalNote={
              requested === "replay"
                ? trace.goalNote
                : requested === "simulation"
                  ? (simulation?.goalNote ?? "Script annotation, not an event. Unavailable to the defender.")
                  : "The workflow goal is not an event. Live diagnostics load after Start."
            }
            scenario={DEMO_PROFILE.scenarioId}
            attackerModel={DEMO_PROFILE.attackerModel}
            defenderModel={DEMO_PROFILE.defenderModel}
            team={DEMO_PROFILE.team}
            awareness={DEMO_PROFILE.awareness}
            defenderPolicy={DEMO_PROFILE.defenderPolicy}
            defenderTrack={DEMO_PROFILE.defenderTrack}
            onTrace={setTraceId}
            onMode={setRequested}
            onStart={start}
          />
        ) : null}
      </div>

      <div className="foot">
      {screen === "run" ? <p className="sentence">{SCENARIO_SENTENCE}</p> : null}
      {screen === "run" ? <Counters scene={scene} /> : null}
      {screen === "run" ? (
      <Timeline
        events={events}
        cursor={visibleCursor}
        playing={playing}
        canScrub={(requested === "replay" || requested === "simulation") && screen === "run"}
        idleLabel={requested === "simulation" ? "Start of the simulation" : "Start of the recording"}
        onRestart={requested === "simulation" ? restartSimulation : undefined}
        onCursor={(next) => {
          setPlaying(false);
          setFollow(false);
          setCursor(next);
        }}
        onToggle={() => setPlaying((value) => !value)}
      />
      ) : null}
      {pinned && screen === "run" ? (
        <button
          type="button"
          className="follow"
          onClick={() => {
            setPinned(false);
            if (requested === "live") setFollow(true);
          }}
        >
          Follow latest event
        </button>
      ) : null}
      </div>
    </div>
  );
}
