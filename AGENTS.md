# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, etc.) working in this repository. `CLAUDE.md` is a symlink to this file. Edit `AGENTS.md` only.

## Project

**AdaptiveHoneypotEnv** is an environment for training and evaluating AI models that create adaptive honeypots against AI agent swarms. Simulated software repositories hold attacking agents or swarms that pursue objectives. Defender models pick from preconfigured honeypot templates and adapt where they place them and what they contain, based on attacker capabilities, tool calls and observed behavior. See `README.md` for the motivation and abstract.

## Specs (source of truth)

Read these before any design or implementation change, in this order of authority:

1. **[`docs/DESIGN.md`](docs/DESIGN.md) (design v1.0) — authoritative.** It locks the v1 decisions and refines the handoff with our research. Where anything conflicts, DESIGN.md wins.
2. **[`docs/IMPLEMENTATION_HANDOFF.md`](docs/IMPLEMENTATION_HANDOFF.md) (v0.2)** — long-form rationale behind the spec.
3. **[`docs/RESEARCH_FINDINGS.md`](docs/RESEARCH_FINDINGS.md)** — cited evidence behind the design choices.

If an implementation must depart from DESIGN.md, raise it with the user first, then record the decision there.

Decisions locked for v1 (see DESIGN.md §0 for the full table):

- **Adaptive defender only.** No static-vs-adaptive comparison. Evaluation arms: no-decoy control, random adaptive, heuristic adaptive, oracle-goal adaptive, and the showcased LLM adaptive defender.
- **Attacker conditions:** both naive and deception-aware (told traps may exist). Reported separately.
- **Model (default):** `z-ai/glm-5.3-flash` via OpenRouter (OpenAI-compatible) for both attacker and defender; `:free` / OpenCode Zen / OpenAI are config switches. The controller holds the provider key; actors/policies never see it.
- **Target:** Honeyval `SecretStorage` **sec** variant, pinned `google-research/honeyval@86272d8`. The genuine route is a **leaked service-account credential** in the ops files, not an app bug.
- **Isolation:** Docker. Target in a locked-down `internal`-network container with no published ports; the **host-side controller makes all model calls** so sandboxes need no outbound.
- **Portability:** `docker-compose` + `Makefile` one-command bringup **and** a `.devcontainer/`. Must come up on any Linux host with Docker + Python 3.11+ and in Codespaces, with no macOS-specific steps. Pin all deps and both upstream revisions.
- **Real interactions, not simulation:** search/reads/HTTP/messages all execute against the real app and workspace. Discovery is never a simulated probability.
- **Deterministic template compiler:** the defender proposes a decoy; code creates and validates the real decoy account and its files. The LLM never picks credential values.
- **Gymnasium loop:** `reset(seed)`/`step(action)`; each step advances the attackers 6 tool attempts round-robin. A canary trigger does not end the episode; the first genuine compromise does.
- **Event-sourced:** append-only JSONL feeds both scorer and UI; the defender sees only redacted, schema-approved observations.
- **Observer UI:** React + PixiJS over SSE; every visual element maps to a real event; `LIVE` / `RECORDED REPLAY` badge.
- **Build gates A–G (DESIGN.md §11) and the regression tests (§13)** define "done" at each stage. **Reward anchors to the counterfactual** (defender vs no-decoy control on matched seeds), never to "decoy touched" alone. **Refusals are their own outcome bucket, never a defender win.**

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

Design is solidified (DESIGN.md v1.0); no code exists yet. The next step is build gate A (fixture and integrity). This repo will be built out primarily by cloud orchestrator agents following DESIGN.md. Update this file as the stack, structure and commands are settled.
