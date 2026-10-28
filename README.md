# AdaptiveHoneypotEnv

**An Environment for Training and Evaluating Adaptive Honeypot Creation Against AI Agent Swarms**

> Status: early stage. The current focus is a hackathon demo; the research environment is being built alongside it. Scope and design will change as research progresses.

## Motivation

Attacks driven by autonomous AI agents have moved from hypothetical to real in 2026:

- **OpenAI → Hugging Face (July 2026).** During an internal evaluation, OpenAI models running with reduced cyber refusals escaped their sandbox through a zero-day in a package registry cache proxy. They escalated privileges and moved laterally until they reached the internet. They then used stolen credentials and a second zero-day to get remote code execution on Hugging Face servers, where they hunted for benchmark secrets so they could cheat on the evaluation.[^register] Independent investigators from METR and Redwood Research found that about 700 agents worked together as a swarm. They coordinated over an unsanctioned message board, and some tried to cover their tracks by deleting or altering records.[^nbc] OpenAI's own report says that "some early signals… could have triggered an earlier response."[^nbc]
- **OpenCode (October 2026).** Attackers spent 48 hours trying to break into OpenCode's systems. They got into the OpenCode Console and stole users' AI provider API keys, which led to unauthorized charges on OpenAI, Anthropic and Google accounts. OpenCode tied the breach to a "large-scale distillation attack." Its defensive AI agents stopped helping once the malicious code they were analyzing set off safety filters.[^techcrunch-opencode]
- **Railway (October 2026).** A "sustained and targeted campaign" may have exposed environment variables for up to 1.85% of workspaces (about 100,000). The attackers were after AI provider keys for distillation. Railway said the attacker likely had access to **abliterated** models, which are open-weight models with their refusal training removed, along with substantial compute.[^thn-railway] Railway called the breach part of a broader campaign against platforms "with the aim of compromising AI inference providers."[^techcrunch-railway]

These incidents follow the same pattern. Attackers run large numbers of tireless agents, and some use models with no guardrails. They explore codebases and infrastructure at machine speed, and they go straight for secrets: credentials, API keys and private data. Defenders who rely on guarded models can be left behind when those models refuse to engage with malicious code. Anyone can abliterate an open-weight model, so this capability is not limited to frontier labs.[^abliterated]

This already affects enterprises, and it will soon affect all of them. Static defenses do not keep up with attackers that explore a codebase, use tools and coordinate at machine speed. Defenders need **adaptive honeypots** inside their own repositories and infrastructure. These are decoys that change in response to what attackers are doing, so that attackers find them, engage with them and get caught.

## Abstract

As AI agents become more capable of exploring codebases, using tools, and coordinating with other agents, we need better ways to defend against potentially malicious behavior. Honeypots are one possible defense, but for them to work, an attacking agent needs to actually discover the honeypot and find it relevant to what it is trying to accomplish.

We propose **AdaptiveHoneypotEnv**, an environment for training and evaluating AI models that create adaptive honeypots. The idea is to simulate realistic software repositories where attacking agents and agent swarms pursue objectives, while defender models create and place honeypots to catch them. Defenders can choose from preconfigured honeypot templates and adapt their placement and content based on the attacker's capabilities, tool calls, and observed behavior.

Our goal is to build a simple, reproducible environment that supports both reinforcement learning and evaluation. Researchers should be able to compare different defender models, train better honeypot creation strategies, and measure how effectively they attract attackers without disrupting legitimate activity. We also plan to build a visual interface that shows attacker and defender behavior during live runs, making the environment easier to understand and experiment with.

## Core ideas

- **Simulated repositories:** realistic software repos for attackers to explore.
- **Attackers:** single agents and agent swarms that pursue objectives using tool calls.
- **Defenders:** models that choose honeypot templates and adapt where they place them and what they contain, based on attacker behavior.
- **Metrics:** how well honeypots attract and catch attackers, and how little they disrupt legitimate activity.
- **RL and evaluation:** a reproducible environment for training defender strategies and benchmarking defender models.
- **Visual interface:** live views of attacker and defender behavior.

## Getting started

Coming soon.

## Repository structure

Coming soon.

## References

[^register]: The Register, "OpenAI admits it was the source of the agent swarm that attacked Hugging Face" (2026-07-22). https://www.theregister.com/ai-and-ml/2026/07/22/openai-admits-it-was-the-source-of-the-agent-swarm-that-attacked-hugging-face/5275939
[^nbc]: NBC News / Reuters, "OpenAI agents hacked Hugging Face in 700-strong swarm, tried to cover tracks, investigations find" (2026-08). https://www.nbcnews.com/tech/tech-news/openai-report-says-network-was-hacked-rogue-ai-agents-rcna594590
[^techcrunch-opencode]: TechCrunch, "Hackers hit AI coding tool OpenCode, running up charges on users' AI accounts" (2026-10-19). https://techcrunch.com/2026/10/19/hackers-hit-ai-coding-tool-opencode-running-up-charges-on-users-ai-accounts/
[^thn-railway]: The Hacker News, "Railway Says Intruder May Have Accessed Customer Secrets, Urges Credential Rotation" (2026-10-22). https://thehackernews.com/2026/10/railway-says-intruder-may-have-accessed.html
[^techcrunch-railway]: TechCrunch, "Developer platform Railway urges 'all users' to revoke secret keys after cyberattack" (2026-10-22). https://techcrunch.com/2026/10/22/developer-platform-railway-urges-all-users-to-revoke-secret-keys-after-cyberattack/
[^abliterated]: LavX News (via Eve Security), "Security Teams Face New Risk Class as Abliterated Models Enable Unrestricted Agents" (2026-10-26). https://news.lavx.hu/article/security-teams-face-new-risk-class-as-abliterated-models-enable-unrestricted-agents
