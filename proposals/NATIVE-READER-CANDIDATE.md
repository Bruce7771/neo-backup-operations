# Bounded native reader contract candidate (not installed)

This candidate changes four SUPPORTED timer-path sources, eight explicit no-lock
flags, and the required legacy compatibility delegate pin. It does not change
applications, roles, keys, timers, callbacks, repository data, or NONZERO guard.

`native-reader-four-source-candidate.py::prepare` accepts exactly five byte strings
with actual installed LF SHA256s. It returns candidates and byte-exact originals
for rollback IN MEMORY. No runtime-install function exists. Local Windows source
copies of two shell files contain CRLF; the fixture explicitly converts their LF
representation and must then match the installed SHA, never silently accepts a
new hash. Frozen migration files were not edited.

Candidate v3 SHA256:
`96b95a419894b030fce5e126b0e744e8bade1f977de08a4987886761fb676c5d`.
The paired legacy delegate now pins exactly that SHA and fails changed-target
execution. Old runner SHA03099... and old delegate SHA3d78... are retained in the
rollback map. There is no old-v2 publication fallback.

Five native/Linux tests passed using reviewed source bytes: eight flag removal,
matched delegate pin, exact rollback preservation, changed/incomplete source
refusal, shell syntax and actual descriptor hash guard after candidate mutation.
Twelve pure admission tests passed, including rejection of default `ls`: restic
0.16.4 `ls` does NOT acquire a native lock. This candidate uses only dump/stats.

## Actual supported entrypoint census

Four enabled active timers: neo-main-hourly-files (v3-run+capture),
neo-main-pitr-ship, neo-main-pitr-rotate, neo-main-preview-backup (scheduled
service→main-preview-collect). At observation all four services were idle.
Old neo-daily-backup.timer is disabled/inactive and points to old stage collector.
No Neo/restic cron.d entries or root crontab were found. A literal recursive
reference traversal from these roots examined22files and found the eight flags
only in the four candidate files. This literal traversal is NOT proof of dynamic
exec aliases; review must bind actual unit/collector/helper paths and hashes.
Old stage/manual media/one-shot source-artifact tools remain stored, but are
explicitly OUTSIDE the future supported-reader contract and cannot be run during
maintenance without a new reviewed admission. Preserve, do not delete, them.

Three actual B2-credential workflows (maintenance-access-check, retention-audit,
retention-readonly-check) already share exact concurrency group
`backup-repository-maintenance`, cancel-in-progress:false. The proposed mutator
must use the SAME repo/group. Transport-check uses another group but has no B2
credentials or content reads; watchdog only checks HTTP. No SSH-reader lease,
new key, or expanded audit-key rights are needed by this simpler candidate.

## Review/install boundary and acceptance still required

- Recheck exact installed source hashes and no active backup/restore/check jobs.
  A selected multi-command reader's snapshots must remain explicitly protected;
  per-command native SH alone does not protect a gap between commands.
- Install all five files in a serialized idle window, preserve protected exact
  originals, verify source/delegate hashes and read-only native lock behavior.
  Partial installation must roll back the WHOLE five-file map, never old runner
  paired with the new pin or vice versa. No broad source substitution.
- Changed runner fingerprint forces the next actual v3 full restore, including
  named-target PostgreSQL and6SQLite/media. Do not rewrite old successful proofs.
  Following success, capture all changed controls in ONE small config child,
  restore it, append exact child→FA protection/evidence, then read-only audit.
  Existing protected config children remain held.
- No cloud GC is allowed yet. Quiet-window proposal requires no active jobs,
  native locks0, next PITR/hourly/daily >120seconds, bounded GC90seconds, repeat
  inventory/closure and exact authenticated three late-v2 parent holds. Existing
  UNKNOWN13/fixed-ASOF/FA+65 holds remain. No raw B2 version purge.
- Reader SIGINT cleanup was measured0.470476sec; SIGKILL left a verified own
  lock, and local native unlock cleaned it only after reap/strict single-own-lock
  census. This is NOT mid-prune interruption proof. Actual delayed mid-REPACK
  cleanup proof is a separate root-assigned fixture. Never remove unknown locks
  or invoke remove-all; a live child can never be unlocked early.
- Weekly scheduled retention and future restore-evidence publication/refresh
  remain separate incomplete conditions. An accepted zero-removal read-only plan
  does not establish automatic30daily/3monthly expiry.

## Coherent eight-source superseding installer

The separately reviewed `native-reader-eight-source-{candidate,install}.py`
package supersedes a bare five-source deployment. It adds BOTH config collector
mirrors and the config coverage validator, preserves ALL8installed originals,
and includes the8rollback paths plus the new root-private enrollment receipt.
The config validator now requires34sources, with all enrollment paths explicit.
New code49,913B plus original rollback44,764B remains below the existing2MB
configuration budget (existing protected payload340,371B; full actual next
collector measurement/restore remains required). No extra raw data is included.

The installer is root-only, default PLAN, exact8before/after SHA-pinned bytes.
It uses existing collector/hourly/PITR/config/application-capture nonblocking
locks, refuses active backup/restore units and next4timer events within120sec.
It records PUBLISHING before replacement, preserves originals root0700, publishes
new controls root0700 and verifies bytes. Exceptions roll back all replaced files
and modes. Seven installer tests passed including failure after3writes, post-rename directory
fsync failure with all8original bytes/modes restored, FD mode set before payload
fsync, all8exact originals,
mode preservation, expired deadline/no candidate write, symlink refusal.

A SIGKILL/power loss can interrupt any multi-file replacement. The persistent
PUBLISHING receipt and protected exact originals permit explicit recovery; this
is not filesystem-wide atomicity. NONZERO GC remains blocked throughout, so an
interrupted enrollment cannot authorize unsafe pruning. No services or timers
are stopped. Complete pair/fullbyte verification is required before acceptance.

Actual read-only PLAN against all8CURRENTinstalled files passed; it read the
sources and generated candidates in memory, tested prospective collector coverage,
and invoked default PLAN. It did NOT acquire runtime job locks, check an upcoming
idle window, install files, invoke a backup, or alter receipts. A fresh idle/window
check occurs only at the separately approved actual publication boundary.
