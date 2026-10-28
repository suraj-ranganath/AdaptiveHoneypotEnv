import type { Presentation } from "../state/presentation";

const LABEL: Record<Presentation["badge"], string> = {
  replay: "RECORDED REPLAY",
  live: "LIVE",
  connecting: "CONNECTING",
  unavailable: "LIVE UNAVAILABLE",
  "not-started": "NOT CONNECTED",
};

export function ModeBadge({ presentation }: { presentation: Presentation }) {
  return (
    <div className={`badge-wrap badge-${presentation.badge}`} data-testid="mode-badge">
      <div className={`badge badge-${presentation.badge}`} role="status" aria-live="polite">
        {LABEL[presentation.badge]}
      </div>
      {presentation.developmentData ? (
        <p className="dev-flag">Development data — not a real run</p>
      ) : (
        <p className="badge-detail">{presentation.detail}</p>
      )}
      {presentation.liveClaimBlocked ? (
        <p className="badge-detail">Shown as a recording because these events are development data.</p>
      ) : null}
    </div>
  );
}
