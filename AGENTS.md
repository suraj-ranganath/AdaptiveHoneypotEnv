# AGENTS.md

Guidance for coding agents in this repository. `CLAUDE.md` is a relative symlink to this file. Edit `AGENTS.md` only.

## Project and priorities

**AdaptiveHoneypotEnv** is an environment for training and evaluating adaptive honeypot creation against AI agent swarms. See [README.md](README.md) for the motivation and original abstract.

- **Immediate goal:** a compelling, working hackathon demo, started 2026-10-28.
- **Long-term goal:** reproducible evaluation and RL support through the same environment dynamics.
- **Current authorization:** review and update planning documents. **Do not begin implementation until the user asks.** Documentation approval is not approval to build, deploy, or run model experiments.

## Specification authority

1. [docs/DESIGN.md](docs/DESIGN.md), v1.1, is authoritative.
2. [docs/IMPLEMENTATION_HANDOFF.md](docs/IMPLEMENTATION_HANDOFF.md), v0.3, expands the contracts and rationale.
3. [docs/RESEARCH_FINDINGS.md](docs/RESEARCH_FINDINGS.md) records evidence and limitations.

Read the design and handoff before changing architecture or implementation. Resolve routine engineering details within the approved scope. Raise substantive departures with the user and record approved decisions in the design. Explicit user instructions take precedence over these documents.

## Approved direction

- **AgentEnv around a shared custom core.** Use its protocol SDK first; task/artifact integration calls the same core. Do not adopt its default sandbox, triggers, or OpenEnv wrapper as our scoring or isolation semantics.
- **Detection first.** Verified engagement before genuine compromise is the primary outcome. Report warning lead time, attacker cost, compromise reduction, and benign disruption separately. A catch does not imply containment or prevention.
- **Workflow objectives:** release or backup; attackers discover the relevant account through repository evidence. Do not identify the exact target account in their initial prompt.
- **Real execution:** actual searches, reads, HTTP calls, and team messages against synthetic fixtures and the pinned Honeyval SecretStorage `sec` app.
- **Deterministic compiler:** defender chooses templates, placement, context, and bounded descriptions; code supplies credentials and canaries. At most two decoys; only `deploy` and `wait`.
- **One core loop:** `reset(seed)` / `step(action)`; up to six scheduled attacker attempts per defender transition; stop immediately at the first actual flag delivery. Canary delivery does not terminate the team.
- **Trusted controller:** holds provider credentials and actor identity; no shell or arbitrary network tools for actors. Target has no internet egress and no published ports. Operator interfaces remain private.
- **Event-sourced observer:** React + PixiJS over SSE, grounded in durable events; explicit `LIVE` / `RECORDED REPLAY` labels.
- **Evaluation:** no-decoy, random adaptive, heuristic adaptive, oracle-goal adaptive, and LLM adaptive arms; naive/deception-aware attackers; solo/trio. A matched deploy-at-reset ablation is approved for later research, not required for the demo.
- The per-transition reward is a provisional detection-oriented surrogate. Counterfactual protection is a separate paired evaluation; never describe the surrogate as a counterfactual reward.

## Working conventions

- No implementation yet. When authorized, follow gates A–G in [DESIGN.md §11](docs/DESIGN.md#11-code-layout-and-build-gates), without skipping prerequisite tests. Gates A–F establish the demo; G adds research exports and validation.
- Keep fixtures, credentials, secrets, and target endpoints synthetic and local. Model-provider endpoints are controller-only infrastructure.
- Keep it simple: one framework, one scenario family, explicit adapters. No Kubernetes, general plugin ecosystem, or general attacker-shell environment.
- Pin reused code, dependencies, images, prompts, and task versions before scored runs. Separate public layout randomness from private fixture secrets and policy randomness.
- Replays reproduce recorded events; seeds do not reproduce hosted-model decisions. Record failures, refusals, and invalid actions honestly.
- Use the source map for provenance, preserve upstream notices, and record local patches. Source review is not integration testing.
- Commit or push only when asked. Do not edit `CLAUDE.md` separately.

## Status

Planning documents are synchronized around the approved architecture. No environment code exists and no build gate has passed. Remaining demo logistics and engineering calibration items are tracked in [DESIGN.md §14](docs/DESIGN.md#14-decisions-and-outstanding-inputs).
