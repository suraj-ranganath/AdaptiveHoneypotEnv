import { SCENARIO_SENTENCE } from "../copy";
import type { DevTrace } from "../dev/traces";
import type { RequestedMode } from "../state/presentation";

interface Props {
  traces: DevTrace[];
  traceId: string;
  mode: RequestedMode;
  goal: string | null;
  goalNote: string;
  scenario: string;
  attackerModel: string;
  defenderModel: string;
  team: string;
  awareness: string;
  defenderPolicy: string;
  defenderTrack: string;
  onTrace(id: string): void;
  onMode(mode: RequestedMode): void;
  onStart(): void;
}

export function Intro({
  traces,
  traceId,
  mode,
  goal,
  goalNote,
  scenario,
  attackerModel,
  defenderModel,
  team,
  awareness,
  defenderPolicy,
  defenderTrack,
  onTrace,
  onMode,
  onStart,
}: Props) {
  return (
    <div className="intro">
      <div className="intro-card">
        <p className="kicker">AdaptiveHoneypotEnv · secret store ops</p>
        <h1>{SCENARIO_SENTENCE}</h1>
        <button type="button" className="start" onClick={onStart}>
          Start
        </button>
        <div className="summary">
          <p>
            <span>Scenario</span> {scenario}
          </p>
          <p className="profile-note">Demo profile from demo.yaml. Not an event field.</p>
          <p>
            <span>Attackers</span> {attackerModel} · {team} · {awareness}
          </p>
          <p>
            <span>Defender</span> {defenderPolicy} · {defenderTrack} · {defenderModel}
          </p>
        </div>
        <div className="goal">
          <p className="goal-kicker">Observer only · unavailable to the defender</p>
          <p className="goal-label">Workflow goal</p>
          <p className="goal-value">{goal ?? "Unavailable"}</p>
          <p className="goal-note">{goalNote}</p>
        </div>
        <fieldset className="mode-pick">
          <legend>Source</legend>
          <label>
            <input
              type="radio"
              name="mode"
              checked={mode === "replay"}
              onChange={() => onMode("replay")}
            />
            Recorded example
          </label>
          <label>
            <input type="radio" name="mode" checked={mode === "live"} onChange={() => onMode("live")} />
            Live operator stream
          </label>
          <label>
            <input
              type="radio"
              name="mode"
              checked={mode === "simulation"}
              onChange={() => onMode("simulation")}
            />
            Simulation
          </label>
        </fieldset>
        {mode === "replay" ? (
          <fieldset className="trace-pick">
            <legend>Development trace</legend>
            {traces.map((trace) => (
              <label key={trace.id}>
                <input
                  type="radio"
                  name="trace"
                  checked={trace.id === traceId}
                  onChange={() => onTrace(trace.id)}
                />
                {trace.title}
              </label>
            ))}
          </fieldset>
        ) : mode === "simulation" ? (
          <p className="live-note">
            Start plays the scripted simulation. It does not connect to an operator, and it is not a recorded run.
          </p>
        ) : (
          <p className="live-note">
            Start connects to the loopback operator stream. If it is down, nothing is played in its place.
          </p>
        )}
      </div>
    </div>
  );
}
