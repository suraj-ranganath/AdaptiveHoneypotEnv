export type RequestedMode = "replay" | "live";
export type ConnectionState = "idle" | "connecting" | "open" | "closed" | "unreachable";

export type BadgeKind = "replay" | "live" | "connecting" | "unavailable" | "not-started";

export interface Presentation {
  badge: BadgeKind;
  developmentData: boolean;
  /** True when a live request was refused because the events are development data. */
  liveClaimBlocked: boolean;
  title: string;
  detail: string;
}

export function resolvePresentation(input: {
  screen: "intro" | "run";
  requested: RequestedMode;
  developmentData: boolean;
  connection: ConnectionState;
}): Presentation {
  if (input.screen === "intro") {
    if (input.requested === "live") {
      return {
        badge: "not-started",
        developmentData: false,
        liveClaimBlocked: false,
        title: "Not connected",
        detail: "Live starts only after the operator stream connects. The recording will not play in its place.",
      };
    }
    return {
      badge: "replay",
      developmentData: true,
      liveClaimBlocked: false,
      title: "Recorded replay",
      detail: "Development data — not a real run and not evidence.",
    };
  }

  if (input.requested === "replay" || input.developmentData) {
    return {
      badge: "replay",
      developmentData: input.developmentData,
      liveClaimBlocked: input.requested === "live" && input.developmentData,
      title: "Recorded replay",
      detail: input.developmentData
        ? "Development data — not a real run and not evidence."
        : "A recording of persisted events. This is not live.",
    };
  }

  if (input.connection === "open") {
    return {
      badge: "live",
      developmentData: false,
      liveClaimBlocked: false,
      title: "Live",
      detail: "Projecting the operator event stream.",
    };
  }
  if (input.connection === "connecting" || input.connection === "idle") {
    return {
      badge: "connecting",
      developmentData: false,
      liveClaimBlocked: false,
      title: "Connecting",
      detail: "Waiting for the operator stream. No activity is invented.",
    };
  }
  return {
    badge: "unavailable",
    developmentData: false,
    liveClaimBlocked: false,
    title: "Live unavailable",
    detail: "The operator stream is not connected. The recorded example has not been substituted.",
  };
}
