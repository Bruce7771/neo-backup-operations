# One external native-catalog trial: proposed execution and workflow diff

STATUS: prepared and synthetically tested only. No workflow file under `.github/` was changed, no merge/push/dispatch, no key/environment change and no cloud trial occurred. Existing default/cron audits remain the current engine.

## Least privilege and concurrency contract

Use the EXISTING permanent audit key, not the maintenance key. Confirmed key scopes in `neo-b2-permanent-access-complete-20261113.md`: audit=`listBuckets,listFiles,readFiles`; maintenance adds `writeFiles,deleteFiles`. Audit cannot create native shared locks. No extra B2 test is needed to pretend a read-only key has write permission. Do not use maintenance5 merely for the trial and never copy it to VPS.

Instead the proposed one-off EXTERNAL mode deliberately uses `--no-lock` only after validating its actual manual GitHub main job context and the exact reviewed workflow bytes. All outside GC/maintenance jobs must share `backup-repository-maintenance`, `cancel-in-progress:false`; no VM GC exists and nonzero maintenance must remain disabled with its hard block ON. Default local/native code still uses shared locks and its actual local CLI proof remains valid. This external mode makes no native-SH claim.

The pinned workflow declares `NEO_BACKUP_MAINTENANCE`, main-only/repository-only/manual-only job restrictions and that same concurrency group. Runtime guard verifies GitHub repo/ref/event/job/workflow-ref/run-ID context, exact40-character reviewed commit equal to `GITHUB_SHA`, and SHA-256 of the checked-out workflow file. It does NOT accept a JSON `verified:true` assertion. This does not defend against an already authorized malicious main writer; existing owner-only access, environment protection and reviewed exact commit remain part of the trust boundary.

The previously checked environment boundary is public `Bruce7771/neo-backup-operations`, default main, one custom deployment-branch policy `main` of type branch, `can_admins_bypass:false`. The existing owner API/sealed helper checked this before prior deliveries. Recheck these SAME read-only API fields with the approved owner helper immediately before merge/dispatch; this proposal does not claim a fresh API observation. Also confirm zero-dollar paid Actions stop and public standard `ubuntu-24.04`, without changing billing. No new subscription/runner/cache/artifact is introduced.

## Exact secret names, no values

The native trial step receives only:

- `NEO_B2_AUDIT_KEY_ID` → `AWS_ACCESS_KEY_ID`
- `NEO_B2_AUDIT_KEY` → `AWS_SECRET_ACCESS_KEY`
- `NEO_RESTIC_REPOSITORY` → `RESTIC_REPOSITORY`
- `NEO_RESTIC_PASSWORD`
- `NEO_RETENTION_POLICY_JSON` → `NEO_POLICY_JSON`
- `NEO_RETENTION_PROTECTED_JSON` → `NEO_PROTECTED_JSON`
- `NEO_RETENTION_RESTORED_JSON` → `NEO_RESTORED_JSON`
- `NEO_RETENTION_DEPENDENCIES_JSON` → `NEO_DEPENDENCIES_JSON`
- `NEO_RETENTION_HOURLY_RECOVERY_JSON` → `NEO_HOURLY_RECOVERY_JSON`

Existing nonsecret environment variable `NEO_B2_REGION` → `AWS_DEFAULT_REGION`.
Use CURRENT owner metadata44 and unchanged UNKNOWN13/ASOF roots, not a historical copied manifest. No maintenance/master/SSH secret is injected.

## Proposed workflow change and exact guards

`retention-readonly-native-trial.proposed.yml` is a replacement proposal for the EXISTING manual `.github/workflows/retention-readonly-check.yml`; it adds no cron. Native flag `native_trial` defaults false. With false the exact current audit-key checker remains selected. With true it runs integration tests and `run-native-external-trial.proposed.py`. Required native-only `reviewed_sha` is checked by the launcher against actual main SHA before any cloud access.

Reviewed workflow SHA-256 is `d14453c71b286190a7dc2438ae314552db9cd110bb1c283d8c84a7f565de1847`, pinned by `external-reader-contract.proposed.py`. Keep LF bytes; modifying even group/flags requires a new reviewed pin. Existing checkout action/restic checksum and10-minute job timeout remain. The workflow itself never provisions keys, uploads data, calls SSH, invokes prune/apply or uploads artifacts.

`build-native-external-engine.proposed.py` generates a NEW private RUNNER_TEMP copy of the already reviewed native engine. It adds the explicit external contract to native reader calls and extends ONLY the fixed numeric failure diagnostic allowlist for new statistics. Actual `scripts/` stay unchanged. `run-native-external-trial.proposed.py` verifies context, rejects elevated credential names, creates that private copy and runs the existing read-only checker from it. Password/inventory/checkpoints never leave ephemeral protected temp. The native engine's actual planner still returns `apply_ready:false`; the only forget calls are existing `--dry-run` plans. CLI guard rejects backup/prune/unlock/non-dry forget. The limited audit key independently prevents data deletion/writing.

## Root review and ONE actual execution sequence

1. Review proposal sources, workflow diff, hashes and tests; recheck current protected environment/free-account restrictions and current static metadata44; ensure no nonzero workflow/VM GC can overlap.
2. Only after Root GO, publish the reviewed proposal files and apply this workflow change to main. Verify remote commit and registered workflow; no dispatch merely because registration exists.
3. Review the exact resulting main commit and workflow-file hash. Dispatch the existing `retention-readonly-check.yml` once at main with `native_trial:true`, `reviewed_sha:<that exact approved commit>`, using the existing approved owner API helper. Plain `gh` is not required. No extra B2 credentials or environment writes.
4. Verify job actually entered `NEO_BACKUP_MAINTENANCE`, checkout SHA, native step selected, serialized group and runtime contract success. Require actual checker PASS with native integrity and existing limited SQLite restore, protections/UNKNOWN/ASOF unchanged and no deletion/fence. Preserve failure phase without blind redispatch.
5. Record current retained/v3 counts,4JSON bytes, seed full-outer fallbacks, unique authenticated trees/cache hits, CLI counts/bytes and elapsed derive time. It is a current-volume actual result, not720-point/180s proof. No automatic engine activation follows.

Eight synthetic workflow/guard tests pass: exact context; default native SH preserved; explicit external no-lock mode; wrong context/commit blocked; changed group/workflow hash blocked; mutation verbs blocked; workflow defaults/audit3/group restrictions; generated actual checker/audit source compile and diagnostic wiring. There was no GitHub/cloud action during these tests.
