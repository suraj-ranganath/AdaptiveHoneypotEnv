import type { SimulationFrame, SimulationHeader } from "../simulation/script";

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

export function SimulationCounters({
  header,
  frame,
}: {
  header: SimulationHeader;
  frame: SimulationFrame | null;
}) {
  if (!frame) {
    return (
      <section className="counters sim-counters" aria-label="Simulation outcomes">
        <p className="outcome">Script not started.</p>
      </section>
    );
  }

  const remaining = Math.max(0, header.teamAttemptBudget - frame.teamAttemptsUsed);
  const detectionBeforeCompromise = frame.reward.detectionBonus === 1 && frame.reward.compromisePenalty === 0;

  return (
    <section className="counters sim-counters" aria-label="Simulation outcomes">
      <div className="counter">
        <p className="counter-k">Detection before compromise</p>
        <p className="counter-v">{yesNo(detectionBeforeCompromise)}</p>
        <p className="counter-s">verified engagement before any genuine compromise</p>
      </div>
      <div className={`counter ${frame.compromise ? "is-compromise" : ""}`}>
        <p className="counter-k">Genuine compromise</p>
        <p className="counter-v">{frame.compromise ? "Observed" : "Not observed"}</p>
        <p className="counter-s">scripted outcome for this episode</p>
      </div>
      <div className="counter">
        <p className="counter-k">Attempt window</p>
        <p className="counter-v">
          {frame.attemptWindowUsed}/{header.attemptsPerDefenderDecision}
        </p>
        <p className="counter-s">6 attacker attempts per defender decision</p>
      </div>
      <div className="counter">
        <p className="counter-k">Team attempt budget</p>
        <p className="counter-v">
          {frame.teamAttemptsUsed}/{header.teamAttemptBudget}
        </p>
        <p className="counter-s">{remaining} attempts remaining</p>
      </div>
      <div className="counter separate">
        <p className="counter-k">Decoys committed</p>
        <p className="counter-s strong">{frame.deployments.length}</p>
        <p className="counter-s">maximum {header.maxDecoys}</p>
      </div>
      <div className="counter separate">
        <p className="counter-k">Scripted reward total</p>
        <p className="counter-s strong">{frame.reward.cumulativeTotal.toFixed(2)}</p>
        <p className="counter-s">illustrative, from this script (not live scoring)</p>
      </div>
      <p className="funnel sim-formula">{header.rewardFormula}</p>
      <p className="outcome">
        Components now: detection_bonus {frame.reward.detectionBonus} · compromise_penalty{" "}
        {frame.reward.compromisePenalty} · newly_committed_decoys {frame.reward.newlyCommittedDecoys} · decoy_cost{" "}
        {frame.reward.decoyCost.toFixed(2)}.
      </p>
      {frame.outcomeNote ? <p className="outcome">{frame.outcomeNote}</p> : null}
    </section>
  );
}

