# Current prepared AS-OF and native-lock maintenance stage

The registered read-only plan/check/component-restore workflow is separate from
this **unregistered** manual mutation proposal. Its zero-candidate result is a
real no-op, not proof of expiration. GitHub cron is still not proven; a Google
monitor is not a retention scheduler. No scheduler credentials/service are added.

## Tested code; deployment remains subject to review

- The original planner still produces `apply_ready:false`. The new coordinator
  does not flip it. It exports a private raw-input validation bundle, rebuilds
  the real planner, verifies protected/restored/configuration/UNKNOWN evidence,
  and issues a separate bounded admission for exact manually reviewed removals.
- The owner review digest binds removals, protected input/policy and executor
  commit. Concurrent new snapshot IDs do not by themselves change that decision;
  the actual current inventory/closure is separately rebound to each admission.
- A <=300-second **local logical write lease** is not a repository lock/fence.
  The proposed endpoint only reads source/unit/drop-in/cron/process metadata;
  it neither pauses backup starts nor reads environment/credential values.
  Fresh public external-job observations and zero native repository locks are
  also required. Busy or unknown sources refuse maintenance, not stop them.
- Every write uses native restic exclusive locks and `--retry-lock 0s`. Fresh
  timer deadlines must leave the requested bounded command/cleanup interval.
  Exact-ID forget is checked against the resulting inventory. New snapshots
  between forget and prune require a fresh GC replan. Native shared repository
  GC needs explicit policy review; it has no host/tag filter. No raw B2 version
  purge and no automatic unlock are present. Partial failures are not reported
  as zero deletions; read-only integrity/component checks are attempted.
- After writes, native no-lock metadata check and the bounded actual retained
  SQLite restore can coexist with working backups. They are not a full Neo/PG
  restoration. Local admission descriptors and secret files are temporary only.

## Historical UNKNOWN scope remains unknown

The active temporary policy conservatively holds all currently authorized roots.
It is deliberately **not** the permanent 30-daily/3-monthly policy: indefinitely
adding all future roots would defeat expiration.

The prepared schema2 AS-OF contract contains the full immutable inventory
projection and canonical hash/time, plus exact count13 and SHA256 of the sorted
existing UNKNOWN projection `(child_snapshot,evidence_sha256,restore_coverage)`.
The full thirteen protected UNKNOWN records stay unchanged in policy. This
removes a duplicated map without discarding evidence. All possible recovery
roots in that reviewed fixed historical index remain held; future bases are not
automatically added. Missing historical roots, changed metadata/digest/coverage,
duplicate/changed child count or a newly backdated root fail closed for review.
Known retained hourly/WAL/configuration dependencies are still held separately.

The schema2 metadata candidate is **not active merely because the code exists**.
It must fit existing secret limits and pass exact native validation before root
reviews/delivers it. No limit increase, lossy projection or invented compression.

## Actual versus proposal

The local synthetic encrypted repository rehearsal actually exercised native
restic0.16.4: a held backup lock refused forget with `--retry-lock 0s`; the backup
then completed, an exact fixture snapshot was forgotten, prune/check passed and
the retained synthetic SQLite was restored. It used no cloud/B2/SSH/Neo data.

The source inventory, external-job census, AS-OF and admission cases are isolated
logic tests. They do not prove the proposed Hostinger endpoint is installed, an
observation identity exists, a production nonzero plan was applied or a scheduler
ran. The new forced-command proposal permits **only `writer-status`**, root-owned
and not group/other-writable, with a separate read-only observation identity.
The existing legacy fence key/entry is unchanged. No new identity or runtime
endpoint has been created/installed by this stage.

`proposals/retention-manual.yml` remains outside `.github/workflows`. It calls
`proposals/retention-coordinator.py`, not the historical `retention-manual.py`
prototype. Activation requires review of the exact code, fixed AS-OF inputs,
source policy/read-only transport and shared GC choice. Current real removal
count zero does not justify deleting a point to manufacture a success.
