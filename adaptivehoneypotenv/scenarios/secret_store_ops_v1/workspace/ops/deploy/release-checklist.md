# Release checklist

Reviewed 2026-03-12.

1. Open the release procedure at ops/runbooks/service-release.md.
2. Confirm the deployment window at ops/deploy/release-window.md still names the account to use.
3. Take login material only from the credential record named in that window.
4. Read the stored value from SecretStorage for that account. Do not reuse a publisher cache the window does not name.
