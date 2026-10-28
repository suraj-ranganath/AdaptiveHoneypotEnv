/**
 * Dev-only static SSE replayer. DEVELOPMENT DATA. Not an episode server.
 * Binds to loopback. Sets a provenance header so the UI will not label this LIVE.
 * Kill and reset return 501 and never report success.
 */
import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const file = process.argv[2];
if (!file) {
  console.error("usage: node scripts/sse-replayer.mjs <trace.jsonl>");
  process.exit(1);
}
const events = readFileSync(file, "utf8")
  .split("\n")
  .map((line) => line.trim())
  .filter(Boolean)
  .slice(1)
  .map((line) => JSON.parse(line));

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");
  if (req.method === "POST") {
    res.writeHead(501, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: false, error: "development replayer does not run an episode" }));
    return;
  }
  if (url.pathname === "/diagnostics") {
    res.writeHead(200, {
      "content-type": "application/json",
      "x-adaptivehoneypot-provenance": "development",
    });
    res.end(
      JSON.stringify({
        development_data: true,
        workflow_goal: "release",
        unavailable_to_defender: true,
      }),
    );
    return;
  }
  if (url.pathname !== "/events") {
    res.writeHead(404);
    res.end();
    return;
  }
  const last = req.headers["last-event-id"];
  const lastSequence = typeof last === "string" && last.includes(":") ? Number(last.split(":").at(-1)) : -1;
  res.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "x-adaptivehoneypot-provenance": "development",
  });
  for (const event of events) {
    if (event.sequence <= lastSequence) continue;
    res.write(`id: ${event.episode_id}:${event.sequence}\ndata: ${JSON.stringify(event)}\n\n`);
  }
  res.end();
});

server.listen(8788, "127.0.0.1", () => {
  console.log("development replayer http://127.0.0.1:8788  (not live)");
});
