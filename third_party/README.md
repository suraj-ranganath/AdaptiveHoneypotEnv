# Third-party sources

Phase 0 vendors no upstream code. Reviewed pins, recorded in DESIGN.md §9.3 and copied into `adaptivehoneypotenv/scenarios/secret_store_ops_v1/provenance.json`, are references only:

- Honeyval `86272d8d1fb4b3090037561cc31b28dc8a8350f8`
- AgentEnv `666c26a586c9118599352c7caa52f53d2e89fb62` (framework `0.9.1375`, protocol `0.1.390`)
- ExploitGym `a8029e47135a29f1c1a6e79109bf86fba379b3f3` (architectural reference, not a runtime dependency)

WS1 adds notices, the pinned SecretStorage source, and a patch ledger when code is actually reused.
