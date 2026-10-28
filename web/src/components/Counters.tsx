import { compromiseLabel, costLabel, detectionLabel, leadLabel, outcomeSentence, surrogateDisagreement } from "../events/metrics";
import type { Scene } from "../events/reduce";

export function Counters({ scene }: { scene: Scene }) {
  const detection = detectionLabel(scene);
  const compromise = compromiseLabel(scene);
  const cost = costLabel(scene);
  const exposed = scene.exposedEvents;
  const inspected = scene.inspectedEvents;
  const authenticated = scene.authenticatedEvents;
  const engaged = scene.engagements.length;
  const disagreement = surrogateDisagreement(scene);
  return (
    <section className="counters" aria-label="Outcomes">
      <div className="counter">
        <p className="counter-k">Exposed</p>
        <p className="counter-v">{exposed}</p>
        <p className="counter-s">events · id withheld</p>
      </div>
      <div className="counter">
        <p className="counter-k">Engaged</p>
        <p className="counter-v">{engaged}</p>
        <p className="counter-s">verified events</p>
      </div>
      <div className="counter">
        <p className="counter-k">Detection before compromise</p>
        <p className="counter-v">{detection.value}</p>
        <p className="counter-s">{detection.detail}</p>
      </div>
      <div className={`counter ${scene.compromise ? "is-compromise" : ""}`}>
        <p className="counter-k">Genuine compromise</p>
        <p className="counter-v">{compromise.value}</p>
        <p className="counter-s">{compromise.detail}</p>
      </div>
      <div className="counter separate">
        <p className="counter-k">Cost</p>
        <p className="counter-s strong">{cost.decoys}</p>
        <p className="counter-s">{cost.inference}</p>
      </div>
      <div className="counter separate">
        <p className="counter-k">Lead time</p>
        <p className="counter-s strong">{leadLabel(scene)}</p>
        <p className="counter-s">Rounds and attempts, separate from cost.</p>
      </div>
      <p className="funnel">
        Funnel · exposed events {exposed} · inspected events {inspected} · login events {authenticated} · engagement
        events {engaged}. Counts are events, because decoy id is not on the operator projection. A file read is not a
        catch. Login is not engagement.
      </p>
      <p className="outcome">{outcomeSentence(scene)}</p>
      {disagreement ? <p className="outcome">{disagreement}</p> : null}
    </section>
  );
}
