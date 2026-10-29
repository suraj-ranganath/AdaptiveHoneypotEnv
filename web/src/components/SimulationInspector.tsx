import type { SimulationFrame, SimulationHeader } from "../simulation/script";

export function SimulationInspector({
  header,
  frame,
}: {
  header: SimulationHeader;
  frame: SimulationFrame | null;
}) {
  if (!frame) {
    return (
      <section className="inspector sim-inspector" aria-label="Simulation details">
        <h2>Simulation details</h2>
        <p className="muted">Press Play to step through the scripted episode.</p>
      </section>
    );
  }

  return (
    <section className="inspector sim-inspector" aria-label="Simulation details">
      <header className="inspector-head">
        <h2>Defender safe projection</h2>
        <p className="mono">
          frame {frame.sequence} · round {frame.round} · attempts {frame.attemptWindowUsed}/{header.attemptsPerDefenderDecision}
        </p>
      </header>
      <p className="sim-title">{frame.title}</p>
      {frame.subtitle ? <p className="sim-subtitle">{frame.subtitle}</p> : null}
      <h3>Observed telemetry (defender-visible)</h3>
      <ul className="meta">
        {frame.defender.observation.map((item, index) => (
          <li key={`${frame.sequence}-obs-${index}`}>{item}</li>
        ))}
      </ul>
      <h3>Inference</h3>
      <p className="rationale">{frame.defender.inference}</p>
      <h3>Action</h3>
      <p className="rationale">{frame.defender.action}</p>
      {frame.deployments.length > 0 ? (
        <>
          <h3>Committed decoy specs (scripted)</h3>
          <ul className="meta">
            {frame.deployments.map((deployment) => (
              <li key={deployment.id}>
                {deployment.templateId} · {deployment.slotId} · {deployment.contextId}
                <br />
                <strong>{deployment.path}</strong>
                <br />
                {deployment.description}
                <br />
                account hint: {deployment.accountHint}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {frame.serviceCall ? (
        <>
          <h3>Service step</h3>
          <p className="meta">{frame.serviceCall}</p>
        </>
      ) : null}
      <h3>Tool activity this frame</h3>
      <ul className="meta">
        {frame.toolLog.map((line, index) => (
          <li key={`${frame.sequence}-tool-${index}`}>{line}</li>
        ))}
      </ul>
      <p className="meta">
        Repo story: <strong>source/</strong>, <strong>deployment_notes</strong>, <strong>integration_records</strong>,{" "}
        <strong>ci_records</strong>, <strong>runbooks</strong>. Service route is behind a fixed-upstream bridge: POST
        /login, GET /get_secret?username=.
      </p>
      {header.baseline ? (
        <div className="sim-baseline">
          <h3>{header.baseline.title}</h3>
          <p>{header.baseline.summary}</p>
        </div>
      ) : null}
    </section>
  );
}

