/**
 * SSE projection client.
 * Parsing and dedup are synchronous. The reader never awaits the React render.
 */

import { eventStreamId, parseObserverEvent, type ObserverEvent, type ParseResult } from "./schema";

export interface SseFrame {
  id: string | null;
  event: string | null;
  data: string;
}

export function parseSseBuffer(buffer: string): { frames: SseFrame[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  const frames: SseFrame[] = [];
  for (const part of parts) {
    if (!part.trim()) continue;
    let id: string | null = null;
    let event: string | null = null;
    const dataLines: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith(":")) continue;
      if (line.startsWith("id:")) id = line.slice(3).trimStart();
      else if (line.startsWith("event:")) event = line.slice(6).trimStart();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    if (dataLines.length > 0) frames.push({ id, event, data: dataLines.join("\n") });
  }
  return { frames, rest };
}

export interface DedupLog {
  ingest(episodeId: string, sequence: number): { accepted: boolean; lastEventId: string };
  lastEventId(): string | null;
  size(): number;
}

export function createDedupLog(): DedupLog {
  const seen = new Set<string>();
  let last: string | null = null;
  return {
    ingest(episodeId, sequence) {
      const id = eventStreamId(episodeId, sequence);
      if (seen.has(id)) return { accepted: false, lastEventId: last ?? id };
      seen.add(id);
      last = id;
      return { accepted: true, lastEventId: id };
    },
    lastEventId: () => last,
    size: () => seen.size,
  };
}

export function mergeEvents(prev: readonly ObserverEvent[], incoming: readonly ObserverEvent[]): ObserverEvent[] {
  if (incoming.length === 0) return [...prev];
  const map = new Map<string, ObserverEvent>();
  for (const event of prev) map.set(eventStreamId(event.episodeId, event.sequence), event);
  for (const event of incoming) map.set(eventStreamId(event.episodeId, event.sequence), event);
  return [...map.values()].sort((a, b) => a.sequence - b.sequence);
}

export function buildSseHeaders(lastEventId: string | null): Record<string, string> {
  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (lastEventId) headers["Last-Event-ID"] = lastEventId;
  return headers;
}

export interface AppliedBatch {
  events: ObserverEvent[];
  errors: string[];
  lastEventId: string | null;
}

/** Apply frames through the adapter and dedup. Synchronous; safe to call from a read loop. */
export function ingestFrames(frames: readonly SseFrame[], log: DedupLog): AppliedBatch {
  const events: ObserverEvent[] = [];
  const errors: string[] = [];
  for (const frame of frames) {
    let raw: unknown;
    try {
      raw = JSON.parse(frame.data);
    } catch {
      errors.push(`SSE data was not JSON${frame.id ? ` (${frame.id})` : ""}.`);
      continue;
    }
    const parsed: ParseResult = parseObserverEvent(raw);
    if (!parsed.ok) {
      errors.push(parsed.sequence ? `seq ${parsed.sequence}: ${parsed.error}` : parsed.error);
      continue;
    }
    const { accepted } = log.ingest(parsed.event.episodeId, parsed.event.sequence);
    if (!accepted) continue;
    events.push(parsed.event);
  }
  return { events, errors, lastEventId: log.lastEventId() };
}

export interface StreamHandlers {
  /** Must not return a promise the reader depends on. Called synchronously per chunk. */
  enqueue: (batch: AppliedBatch) => void;
  onStatus: (status: "connecting" | "open" | "closed" | "unreachable", detail?: string) => void;
  onProvenance?: (provenance: "development") => void;
}

export interface StreamConnectOptions {
  url: string;
  signal: AbortSignal;
  getLastEventId: () => string | null;
  fetchImpl?: typeof fetch;
  handlers: StreamHandlers;
  /** Test hook. Production reconnects back off from 400ms. */
  reconnectDelayMs?: number;
}

/**
 * Read an SSE response body. `enqueue` is invoked synchronously as frames complete.
 * The function does not await `enqueue`, so a slow render cannot stall the socket read
 * beyond the time spent inside that synchronous call. Callers should only push onto a queue.
 */
export async function connectEventStream(options: StreamConnectOptions): Promise<void> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const log = createDedupLog();
  const firstDelay = options.reconnectDelayMs ?? 400;
  let backoff = firstDelay;
  while (!options.signal.aborted) {
    options.handlers.onStatus("connecting");
    let response: Response;
    try {
      response = await fetchImpl(options.url, {
        headers: buildSseHeaders(options.getLastEventId() ?? log.lastEventId()),
        signal: options.signal,
      });
    } catch (error) {
      if (options.signal.aborted) return;
      const message = error instanceof Error ? error.message : "connection failed";
      options.handlers.onStatus("unreachable", message);
      await sleep(backoff, options.signal);
      backoff = Math.min(backoff * 2, 5_000);
      continue;
    }
    if (!response.ok || !response.body) {
      options.handlers.onStatus("unreachable", `HTTP ${response.status}`);
      await sleep(backoff, options.signal);
      backoff = Math.min(backoff * 2, 5_000);
      continue;
    }
    if (response.headers.get("x-adaptivehoneypot-provenance") === "development") {
      options.handlers.onProvenance?.("development");
    }
    options.handlers.onStatus("open");
    backoff = firstDelay;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (!options.signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseBuffer(buffer);
        buffer = parsed.rest;
        if (parsed.frames.length > 0) {
          options.handlers.enqueue(ingestFrames(parsed.frames, log));
        }
      }
    } catch (error) {
      if (options.signal.aborted) return;
      const message = error instanceof Error ? error.message : "stream failed";
      options.handlers.onStatus("unreachable", message);
      await sleep(backoff, options.signal);
      continue;
    }
    if (options.signal.aborted) return;
    options.handlers.onStatus("closed", "The stream ended.");
    await sleep(backoff, options.signal);
  }
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/** Schedule a flush without the SSE reader awaiting React. */
export function createRenderQueue(flush: (batches: AppliedBatch[]) => void, schedule: (cb: () => void) => void = defaultSchedule): {
  push: (batch: AppliedBatch) => void;
  cancel: () => void;
} {
  let queued: AppliedBatch[] = [];
  let scheduled = false;
  return {
    push(batch) {
      queued.push(batch);
      if (scheduled) return;
      scheduled = true;
      schedule(() => {
        scheduled = false;
        const ready = queued;
        queued = [];
        flush(ready);
      });
    },
    cancel() {
      queued = [];
      scheduled = false;
    },
  };
}

function defaultSchedule(callback: () => void): void {
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => callback());
  else setTimeout(callback, 0);
}
