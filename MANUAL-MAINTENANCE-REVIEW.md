# Prepared manual maintenance, not activated

**Historical prototype notes below.** The current unregistered native-lock
coordinator and fixed AS-OF proposal are documented in
[ASOF-NATIVE-RETENTION-STAGE.md](ASOF-NATIVE-RETENTION-STAGE.md). They supersede
the old server-fence sequence and old candidate-only prototype entry; neither
proposal is a deployed mutation workflow.

The proposed workflow lives at `proposals/retention-manual.yml`, **outside**
`.github/workflows`, so GitHub does not register it at all. It is manual-only,
default `plan`, with an unset review kill switch. It adds no scheduled mutation, billing change, paid runner or external
service. Existing weekly audit and monitor cron events have not been proven to
execute; Google monitoring is not a retention scheduler.

The existing planner deliberately returns `apply_ready:false`. This draft does
**not** change or promote that flag. An apply request with nonzero removals stops
before acquiring a fence unless a separately reviewed admission validator has
produced an authoritative lease-bound manifest. No option or secret bypasses the
flag. Zero removal candidates produce an honest no-op: no lease, forget or prune;
that is not evidence that destructive maintenance was exercised.

## Explicit gates still missing

1. Permanent scoped audit/maintenance B2 credentials are now provisioned and
   independently verified by the read-only access job. Only the prefix-restricted maintenance
   credential may perform native restic mutations. No master key is accepted,
   copied or requested by this workflow.
2. The current restricted SSH status returns fence phase/unit names, but does not
   expose a fresh complete real-writer inventory. Acquire requires a privately
   generated inventory no older than sixty seconds, covering systemd, cron, manual
   sessions and external runners. There is no reviewed remote refresh/proof
   interface among the three current commands. A static secret or yesterday's
   receipt cannot satisfy this requirement. The draft therefore rejects current
   status rather than inventing completeness.
3. A reviewed admission validator must bind the repeated exact plan, repository,
   fresh writer evidence, current 300-second lease and complete retained
   configuration/full/PITR/WAL dependency closure. The read-only planner itself
   is not that authority. Its current `apply_ready:false` is a real blocked gate.
4. The private policy needs a protected retained SQLite-component postcheck
   contract grounded in an accepted manifest. It must identify exact snapshot,
   file, SHA and byte count, at most16MiB. Use a real working index/database, not
   an unused shadow artifact selected merely because it is small. This is a
   limited component restore, not recovery of all Neo databases or user files.
5. Restic `prune` is repository-wide garbage collection and has no host/tag scope
   filter. Exact authorized snapshot IDs can be bounded for `forget`, but calling
   prune scope-limited would be false. Repository-wide GC of unreachable packs,
   preservation of every retained/shared reference, and an adequate measured
   time budget require separate explicit review before its switch is enabled.

## Reviewed draft execution sequence

- Pinned checkout and checksum-pinned restic, standard public Linux runner, same
  maintenance concurrency group, protected environment, main branch only. Keep
  the existing account hard stop on paid overrun. No artifacts or caches.
- Generate a stable private read-only candidate using the unchanged planner and
  automatic hourly recovery derivation. Emit only digest/counts. Scope policy,
  IDs, target identity, lease token, recovery password and keys remain private.
- Nonzero mutation requires the exact reviewed digest and at most ten removals.
  Confirm fresh real writer evidence; call only pinned-host `acquire 300`, repeat
  the plan inside the lease, and reject any changed inventory/plan/closure.
- Retain all protected configuration children and full parents; retained hourly
  named targets retain their verified compatible PITR base/WAL snapshot. Unknown
  metadata, new unaccepted bases or missing restores fail closed.
- Validate the retained/protected component contract **before** the first write.
  Native-lock `forget` receives only exact approved IDs. Optional separately
  reviewed repository prune limits repacking to16MiB and each subprocess has a
  deadline. That bound limits repacking, not the volume of unreachable packs
  deleted or the total B2 traffic. No raw B2 version purge or broad age expiry.
- Run native restic metadata/reference check and actually restore the bounded
  retained SQLite component on the isolated runner. Compare exact SHA/bytes and
  native integrity. Do not claim a full Neo/PITR restore or prune savings from
  this limited verification.
- Finally release the matching private lease after native processes finish. On a
  timeout terminate the entire local process group first. Never unlock unknown
  repository locks or assume lease expiry means deletion ended.

The overall manual job is bounded to fifteen minutes, allowing pre-plan and
graceful acquisition before the maximum300-second held lease. Every operation
inside that lease reserves cleanup/release time and stops early if insufficient.
This is a safety deadline, not proof that a large repository can be replanned,
pruned, checked and restored within it; actual read-only timing is another
activation prerequisite.

## Failure boundaries

The current VPS watchdog keeps an expired/unknown fence held for reconciliation;
it does not silently resume backup writers during an uncertain external prune.
If acquisition fails before a token is returned, or the runner disappears, a
matching release cannot be fabricated. Inspect the actual runner/process/lock
state through the owner-supported path before resuming backup starts. Neo,
PostgreSQL and native WAL archiving must remain running throughout. This failure
can itself prevent future backups, so external detection of missing backups and
monitor/scheduler failure remains an explicit independent requirement. Do not
claim a failure email or autonomous weekly cleanup has been proven.

The current code is reviewable preparation. No Actions apply run, fence acquire,
forget, prune, B2 version deletion or post-maintenance production check was run
to prepare these files. Synthetic cases use fixture paths and fake IDs only.

## Verification of this draft

The existing seventeen planner tests and nine hourly recovery/DAG tests passed.
All eighteen affected manual-admission tests then passed on Linux. They exercise
read-only `apply_ready:false` rejection before SSH, zero-candidate no-op, exact
digest and protected-ID guards, missing/stale writer evidence, lease limits,
component boundaries, whole-process timeout, matching-lease release after a
simulated check failure, and the actual audit export's private-directory/mode
checks. SSH child processes receive no B2/recovery/policy environment and use no
user SSH configuration. Simulated `forget` is a mocked call: no real repository
mutation, cleanup or restoration is claimed.
