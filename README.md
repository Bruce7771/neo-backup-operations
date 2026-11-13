# Independent backup operations

This public repository contains operational code only. It contains no Neo application source, account data, database/media contents, backup inventories, real snapshot IDs, credentials or recovery passwords. Backups remain encrypted in the owner's private external storage. The application runs on Hostinger; neither application runtime nor backup operations require Replit.

## Current scope

The separate `backup-watchdog.yml` checks only the public aggregate backup-health endpoint once per hour, at minute17UTC, with no repository checkout or secrets. It preserves the existing zero-dollar paid-overage stop. It does not gain access to the maintenance environment or encrypted backups. A manual run is not evidence of a scheduled run; record the actual event and result separately.

The included workflow performs a **read-only retention audit**, manually or weekly, only when `NEO_BACKUP_AUDIT_ENABLED=true`. It uses the protected `NEO_BACKUP_MAINTENANCE` environment, default branch `main`, a checksum-pinned restic binary, a SHA-pinned checkout action and this exact workflow commit. No artifacts or package caches are uploaded. Job duration is bounded to five minutes. No job changes an account budget, purchases services or deletes backups.

The account-wide zero-dollar Actions hard stop must remain enabled. Check included quota before enabling automatic runs. Public standard Linux runner availability is not permission to add paid runner types or services. Environment deployment branches must allow only `main`; no per-run required reviewer is needed for unattended **read-only** weekly audits. Changes to workflow/policy code still require owner review. Review protection and contributor permissions before adding any secret.

## Private configuration, kept outside this repository

Environment secrets: `NEO_B2_AUDIT_KEY_ID`, `NEO_B2_AUDIT_KEY`, `NEO_RESTIC_PASSWORD`, `NEO_RESTIC_REPOSITORY`, `NEO_RETENTION_POLICY_JSON`, `NEO_RETENTION_PROTECTED_JSON`, `NEO_RETENTION_RESTORED_JSON`, `NEO_RETENTION_DEPENDENCIES_JSON`. The audit key must be a permanent bucket/prefix-restricted **read/list-only** key. It does not need final deletion, key administration or access to other buckets. Store real inventory/protected/restore/dependency/policy manifests only as protected environment secrets, never in public files, plaintext Actions variables or logs.

Nonprivate environment variable: `NEO_B2_REGION`. Repository kill switch: `NEO_BACKUP_AUDIT_ENABLED`, initially false. Runtime scope policy schema1 provides exactly three `scopes`, each with explicit `kind` (`daily`, `pitr`, `hourly`), `host`, `tag`, exact `paths`, plus `configuration_scopes` with `host`, `tag` and one exact path each. Protected/restored values are arrays of full IDs; dependencies are private child/parent mappings. Do not commit their values. Missing, changed or conflicting inventory fails closed.

The retention target is 30 daily and three monthly recovery points, with a 30-day recent window for configured scopes. Shared packs are protected by restic dependencies. Retained configuration children must retain their explicit full parent chain. Unrelated scopes are preserved. Synthetic planner tests use `/fixture/...` paths and repeated-character fake IDs only.

## Destructive maintenance is not activated

The audit returns a candidate with `apply_ready:false`; it is never authority to delete. Automatic expiration/prune needs a separately scoped maintenance key **outside the VPS**, a fresh complete writer inventory, and a reviewed forced-command fence transport. `scripts/fence-ssh-command.sh` is a prepared three-command entry point, not an installed root helper or provisioned identity. It must never grant a general shell or access to application data/secrets. The corresponding VPS helper/probe must be reviewed and installed privately.

Before enabling any mutation: fence backup starts only and let existing collectors finish their restart cleanup; keep Neo, PostgreSQL and WAL archiving running; replan exact IDs while fenced; preserve all protected points/parents; keep native repository locks; bound maintenance to the measured recovery objective; check the repository and restore retained databases/files on a separate target; release the matching lease and observe the next normal automatic backup. A disconnected runner or expired lease is not proof that prune stopped. Do not forcibly unlock an unknown writer.

Logical snapshot expiration, pack pruning and permanent deletion of hidden B2 versions are different operations. Never apply blanket age expiration to restic packs. Final version deletion requires an exact reviewed obsolete-version list, grace period and retention of all versions needed by current recovery points. No final-delete credential or apply workflow is included here.

Official references: [restic retention and locks](https://restic.readthedocs.io/en/stable/060_forget.html), [B2 application keys](https://www.backblaze.com/docs/cloud-storage-application-keys), [GitHub protected environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
