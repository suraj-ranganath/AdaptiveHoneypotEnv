# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, etc.) working in this repository. `CLAUDE.md` is a symlink to this file. Edit `AGENTS.md` only.

## Project

**AdaptiveHoneypotEnv** is an environment for training and evaluating AI models that create adaptive honeypots against AI agent swarms. Simulated software repositories hold attacking agents or swarms that pursue objectives. Defender models pick from preconfigured honeypot templates and adapt where they place them and what they contain, based on attacker capabilities, tool calls and observed behavior. See `README.md` for the motivation and abstract.

## Implementation spec (source of truth)

**[`docs/IMPLEMENTATION_HANDOFF.md`](docs/IMPLEMENTATION_HANDOFF.md) (design v0.2) is the specification we implement against.** Read it before making design or implementation changes. Where it conflicts with anything else in this file or the README, the handoff wins. If an implementation needs to depart from it, raise that with the user first, then record the decision in the handoff.

Key points from the handoff:

- **MVP scope:** one task family (`secret_store_ops/v1`), two objective variants (release and backup), three templates, four placement slots, at most two decoys, and either one attacker or a scheduled team of three. The only defender actions are `deploy` and `wait`.
- **Real interactions, not simulation:** search, reads, HTTP requests and team messages all actually execute. The target is the real Honeyval `SecretStorage` app, pinned to a specific revision. Discovery is never a simulated probability.
- **Deterministic template compiler:** the defender proposes a decoy, and code creates and validates the real decoy account and the files that reference it. The LLM never picks credential values.
- **Gymnasium-style loop:** `reset(seed)` and `step(action)`. Each step advances the attackers by six tool attempts in round-robin order. A canary trigger does not end the episode; the first genuine compromise does.
- **Event-sourced:** an append-only JSONL log feeds both the scorer and the UI. The defender only sees redacted, schema-approved observations.
- **Observer UI:** React and PixiJS, driven by the server over SSE. Every visual element must link to a real event. The UI shows a `LIVE` or `RECORDED REPLAY` badge.
- **Build gates A–G (§12) and the regression tests (§13)** define what "done" means at each stage.

## Current phase

- **Immediate goal: a hackathon demo (started 2026-10-28).** Prioritize a compelling, working, visual demo over research completeness.
- **Long-term goal: a research environment** that is reproducible and supports both RL training and evaluation of defender models. Demo code should move toward this. Avoid shortcuts that would have to be thrown away entirely.
- The design is not final. The abstract and approach may change as research progresses.

## Key concepts

- **Attacker:** an agent or swarm with an objective, such as exfiltrating secrets or gaining access, that explores a repo through tool calls.
- **Defender:** a model that creates and places honeypots and adapts them to the attacker behavior it observes.
- **Honeypot template:** a preconfigured decoy type, such as fake credentials, a decoy config or a bait endpoint, that the defender instantiates and customizes.
- **Success metrics:** attacker discovery of and engagement with honeypots, catch rate, and low disruption to legitimate activity, such as false triggers by benign agents or developers.
- **Visual interface:** a live view of attacker and defender actions during runs.

## Working conventions

- Follow the handoff's build gates in order (A → G), and don't skip a gate's tests to reach the demo faster.
- Keep the code layout described in handoff §12, and avoid the components it explicitly rules out: Kubernetes, plugin ecosystems, multiple orchestration frameworks, shell tools for attackers.
- Keep the environment simple and reproducible: seedable runs, deterministic where possible, logged trajectories.
- Keep all honeypot content synthetic. Never include real credentials, real third-party endpoints or working exploit payloads.
- Attacker agents run only against simulated, sandboxed targets.
- Commit or push only when the user asks.

## Status

The implementation spec has been adopted, but no code exists yet. The next step is build gate A (fixture and integrity). Update this file as the stack, structure and commands are settled.
