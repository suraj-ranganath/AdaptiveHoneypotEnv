# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, etc.) working in this repository. `CLAUDE.md` is a symlink to this file. Edit `AGENTS.md` only.

## Project

**AdaptiveHoneypotEnv** is an environment for training and evaluating AI models that create adaptive honeypots against AI agent swarms. Simulated software repositories hold attacking agents or swarms that pursue objectives. Defender models pick from preconfigured honeypot templates and adapt where they place them and what they contain, based on attacker capabilities, tool calls and observed behavior. See `README.md` for the motivation and abstract.

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

- Do not start implementation work until the execution plan is agreed with the user.
- Keep the environment simple and reproducible: seedable runs, deterministic where possible, logged trajectories.
- Keep all honeypot content synthetic. Never include real credentials, real third-party endpoints or working exploit payloads.
- Attacker agents run only against simulated, sandboxed targets.
- Commit or push only when the user asks.

## Status

Repository initialized. Implementation not yet started. Update this file as the stack, structure and commands are decided.
