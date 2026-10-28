# Backup rotation

[[layout.review_sentence]] This note is the in-service procedure for the backup workflow.

The workflow reads one stored value from SecretStorage. The integration account is the account recorded in the current vault binding.

- Vault binding: ops/integrations/backup-vault.json

Login material is not copied here. Follow the binding to its credential record.

Account: [[backup_current.username]]

An older handover remains on file for [[backup_retired.username]] at ops/deploy/backup-handover-2025-11.properties. That handover is not the in-service mapping.
