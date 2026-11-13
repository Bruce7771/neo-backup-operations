# Reader admission before shared repository garbage collection

Status: local native fixture verified; **not installed and not deletion authority**.
No live key, workflow, service, timer, application or repository was changed.

## Observed native behavior

Pinned restic 0.16.4, fresh local repository and baseline zero locks:
active default `dump` holds one native lock; active explicit `--no-lock dump`
holds none. Removing `--no-lock` is not compatible with the current strictly
read-only B2 audit credential: writing/removing native locks needs additional
rights. Do not silently broaden that credential.

The native cooperative fixture actually ran `forget`, `prune`, `check` and
restored the retained synthetic payload, only in its own disposable LOCAL repo.
SH protected a live no-lock reader; maintenance EX refused in 0.000023 seconds
without interrupting the reader. A future producer waited behind EX and resumed.
The local native GC/check completed in 2.052647 seconds; SHA matched after prune.
Controller exit released its lock. This is not a measured production GC duration.

## Exact smallest deployment package requiring review

1. One root-owned repository-specific kernel-flock file on the VPS. Every
   supported VM restic invocation, including manual acceptance, restore, config,
   daily, PITR and hourly commands, holds SH for its entire native command. Parent
   selection/publication also remains protected where any external dependency
   can be chosen. Do not wrap the app, stop it, stop timers, or kill active readers.
2. Extend the EXISTING restricted maintenance forced-command with literal
   `reader-lease` and `gc-lease` operations, not arbitrary shell commands. The
   existing approved SSH credential is sufficient; no new key is required.
   Reader lease holds SH through the authenticated stream. GC obtains EX
   NONBLOCKING, returns busy immediately if any reader/producer is active, and
   caps the whole native-GC window at 90 seconds. Native exclusive restic locks
   remain necessary in addition. Lease EOF/controller death must release the FD.
3. Current GHA audit/read-only jobs must hold an authenticated SH lease while
   native commands run. This needs the existing SSH credential passed only to
   the protected job and exact forced-command permission; it changes the reviewed
   no-SSH audit contract, so is not silently enabled. Do not grant audit B2 key
   write/delete capabilities. Unknown/unwrapped readers mean GC stays blocked.
4. A fail-closed admission checks reviewed installed-script hashes, forced-command
   hash, declared command/alias roster, actual process census and fresh active
   lease inventory. The census alone cannot prove that a future unwrapped command
   will not start. Install/verify ALL supported entrypoints before admission.
   Root can intentionally bypass controls; no arbitrary-root-malicious claim.
5. Under EX, repeat inventory and dependency closure and validate the exact plan
   digest immediately before native operations. Retain fixed historical ASOF
   roots, all UNKNOWN13 and authenticated late-v2 parents plus fixed FA/65 config
   ancestors. Future accepted v3 has embedded PG; do not invent external parents.
   Timeout/exception releases the lease, records failure, leaves existing accepted
   restore receipts intact, and schedules no blind retry. No raw B2 version purge.

Native prune interruption safety and actual bounded production duration must be
validated before allowing nonzero GC. **The current unconditional NONZERO guard
remains.** This proposal is not an instruction to install a global restic wrapper.

## Separate remaining operational conditions

- Current accepted read-only plan selected zero removals; that is a legitimate
  no-op, not evidence that 30 daily / 3 monthly expiry is automated.
- Exact three late-v2 parents use the existing authenticated private closure;
  do not rescan all snapshots or infer parents from timestamps.
- Future weekly-base/config restore-evidence publication/refresh must work
  without the owner's computer. Static accepted-base lists fail closed for new
  unaccepted bases and are not a complete perpetual retention process.
- True backup-watchdog schedule was observed; retention weekly schedule is
  separately unconfirmed. The temporary audit cron was removed. No new scheduler,
  cron probe, external service or credential is part of this package.
