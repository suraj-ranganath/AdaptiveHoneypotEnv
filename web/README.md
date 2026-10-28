# Observer

React + PixiJS projection of the operator event stream. This UI does not run an episode, score one, or invent activity.

It parses only `OperatorEventView` (`adaptivehoneypotenv/contracts/events.py`, schema `1.0.0`). Paths, hit lists, post text, deployment specs, and the private workflow goal are not on that view. The goal shown here comes from a diagnostics sidecar or `GET /diagnostics` on the loopback operator, and it is labeled as unavailable to the defender.

The badge reads **LIVE** only while a non-development operator stream is open. Recordings, including every file in `dev-traces/`, read **RECORDED REPLAY**. Connecting is not live. If the stream is down, the recording is not substituted.

## Run

```bash
cd web
npm ci
npm run dev
```

The dev server binds to `http://127.0.0.1:5173`. Kill and reset call `http://127.0.0.1:8787` (`POST /episodes/:id/kill` and `POST /episodes/:id/reset`). The event stream is `GET /events`. `server.py` does not serve that stream yet; an unreachable operator is reported as unreachable.

Replay a development trace:

```bash
npm run dev
# http://127.0.0.1:5173/?screen=run&trace=detection-before-compromise&at=49
```

`at` is an event sequence. The player pauses at that prefix. Traces are **DEVELOPMENT DATA**. They are not evidence. Replace them with core-produced journals before demo acceptance.

Regenerate the traces:

```bash
node dev-traces/build.mjs
```

A dev-only SSE replayer (loopback, provenance header `development`, kill returns 501):

```bash
node scripts/sse-replayer.mjs dev-traces/detection-before-compromise.jsonl
```

It listens on `http://127.0.0.1:8788`. Point the UI at it with `?mode=live&screen=run&operator=http://127.0.0.1:8788` only to exercise reconnect. The provenance header keeps the badge on **RECORDED REPLAY**.

## Checks

```bash
npm run typecheck
npm run lint
npm run build
```
