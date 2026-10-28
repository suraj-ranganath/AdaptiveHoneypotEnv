import { useEffect, useRef, useState } from "react";
import { connectEventStream, createRenderQueue, type AppliedBatch } from "../events/stream";
import type { ObserverEvent } from "../events/schema";
import type { ConnectionState } from "./presentation";

export function useLiveStream(
  url: string | null,
  onBatch: (events: ObserverEvent[], errors: string[]) => void,
): { connection: ConnectionState; detail: string | null; provenance: "development" | null } {
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [detail, setDetail] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<"development" | null>(null);
  const onBatchRef = useRef(onBatch);
  const lastId = useRef<string | null>(null);
  onBatchRef.current = onBatch;

  useEffect(() => {
    if (!url) {
      setConnection("idle");
      setDetail(null);
      setProvenance(null);
      return;
    }
    setProvenance(null);
    const controller = new AbortController();
    const queue = createRenderQueue((batches: AppliedBatch[]) => {
      onBatchRef.current(
        batches.flatMap((batch) => batch.events),
        batches.flatMap((batch) => batch.errors),
      );
    });
    void connectEventStream({
      url,
      signal: controller.signal,
      getLastEventId: () => lastId.current,
      handlers: {
        enqueue(batch) {
          if (batch.lastEventId) lastId.current = batch.lastEventId;
          queue.push(batch);
        },
        onStatus(status, message) {
          setConnection(status);
          setDetail(message ?? null);
        },
        onProvenance(next) {
          setProvenance(next);
        },
      },
    });
    return () => {
      controller.abort();
      queue.cancel();
    };
  }, [url]);

  return { connection, detail, provenance };
}
