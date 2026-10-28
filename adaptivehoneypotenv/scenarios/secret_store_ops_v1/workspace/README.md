# Platform workspace

Lab workspace for the SecretStorage service and the operations notes around it.

- `source/` holds the pinned SecretStorage application source.
- `ops/ci/` holds pipeline caches.
- `ops/deploy/` holds deployment notes and handovers.
- `ops/runbooks/` holds the release procedure and the backup procedure.
- `ops/integrations/` holds service bindings.

[[layout.review_sentence]] Both the release workflow and the backup workflow are in service. Each procedure names its integration account. Stored values live in SecretStorage. When login material was kept, it lives in one on-file record.
