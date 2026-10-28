/** Operator control interface. The real server.py is integration work; this client only calls it. */

export const DEFAULT_OPERATOR_BASE = "http://127.0.0.1:8787";

export interface OperatorCallResult {
  ok: boolean;
  status: number | null;
  message: string;
}

export interface DiagnosticsResult {
  goal: "release" | "backup" | null;
  developmentData: boolean;
  message: string;
}

export interface OperatorApi {
  baseUrl: string;
  eventsUrl(): string;
  diagnostics(): Promise<DiagnosticsResult>;
  kill(episodeId: string): Promise<OperatorCallResult>;
  reset(episodeId: string): Promise<OperatorCallResult>;
}

export function assertLoopback(baseUrl: string): URL {
  let url: URL;
  try {
    url = new URL(baseUrl);
  } catch {
    throw new Error("Operator URL is not valid.");
  }
  const host = url.hostname.replace(/^\[|\]$/g, "");
  if (host !== "127.0.0.1" && host !== "localhost" && host !== "::1") {
    throw new Error("Operator API binds to loopback by default. Refusing a non-loopback URL.");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("Operator URL must be http or https.");
  }
  return url;
}

export function createOperatorApi(baseUrl: string = DEFAULT_OPERATOR_BASE, fetchImpl: typeof fetch = fetch): OperatorApi {
  const url = assertLoopback(baseUrl);
  const base = url.toString().replace(/\/$/, "");
  async function post(path: string): Promise<OperatorCallResult> {
    try {
      const response = await fetchImpl(`${base}${path}`, { method: "POST" });
      const text = await response.text();
      let message = text.trim();
      if (message.startsWith("{")) {
        try {
          const body = JSON.parse(message) as { error?: string; message?: string; ok?: boolean };
          message = body.error ?? body.message ?? message;
        } catch {
          /* keep raw text */
        }
      }
      if (!message) message = response.ok ? "Operator accepted the call." : `HTTP ${response.status}`;
      return { ok: response.ok, status: response.status, message };
    } catch (error) {
      const detail = error instanceof Error ? error.message : "request failed";
      return {
        ok: false,
        status: null,
        message: `Operator API unreachable at ${url.host}. ${detail}. server.py is not part of this UI.`,
      };
    }
  }
  return {
    baseUrl: base,
    eventsUrl() {
      return `${base}/events`;
    },
    async diagnostics() {
      try {
        const response = await fetchImpl(`${base}/diagnostics`);
        const text = await response.text();
        if (!response.ok) {
          return {
            goal: null,
            developmentData: false,
            message: "Workflow goal is not an event. Operator diagnostics did not respond.",
          };
        }
        const body = JSON.parse(text) as {
          workflow_goal?: string;
          development_data?: boolean;
          unavailable_to_defender?: boolean;
        };
        const goal = body.workflow_goal === "release" || body.workflow_goal === "backup" ? body.workflow_goal : null;
        return {
          goal,
          developmentData: body.development_data === true,
          message: goal
            ? "Operator diagnostics. Not an event. Unavailable to the defender."
            : "Operator diagnostics responded without a release or backup goal.",
        };
      } catch {
        return {
          goal: null,
          developmentData: false,
          message: "Workflow goal is not an event. Operator diagnostics are unreachable.",
        };
      }
    },
    kill(episodeId) {
      return post(`/episodes/${encodeURIComponent(episodeId)}/kill`);
    },
    reset(episodeId) {
      return post(`/episodes/${encodeURIComponent(episodeId)}/reset`);
    },
  };
}
