# Local cooperative publication barrier: tested prototype only

No runtime code, B2 object, service, timer, application or database was changed.
The production proposal's unconditional nonzero block remains in place.

`cooperative-publication-barrier-test.py` ran on Linux against a temporary local
lock file with independent processes: **7 tests passed in 0.421 seconds**.
It has no restic/backend/credential code. This is not a cross-host atomic lock.

## Exact cooperative protocol

1. Every producer takes SH **before reading or selecting any parent**, validates
   that parent's identity and availability, and keeps SH until its snapshot and
   delivery receipt are published. Local producer state that can become a
   future dependency is registered durably and is read under the same protocol.
2. Maintenance tries EX nonblocking. Any active SH producer makes it refuse
   immediately; that producer continues uninterrupted. There is no service or
   timer stop. Future SH producers wait briefly while EX is held.
3. Under EX, maintenance obtains a fresh complete inventory, authenticated
   dependency closure and current durable producer-parent roots. It reruns
   retention and accepts only the exact reviewed, still-eligible IDs. Native
   restic repository locking is still required; local EX does not replace it.
4. A future writer acquiring SH validates its parent again after acquisition.
   A disappeared parent causes refusal or an explicit validated rebase, never
   publication using a cached pre-lock parent ID.
5. EX lifetime must be bounded to **at most 90 seconds**, including enumeration,
   verification and exact forget. Insufficient remaining time aborts before
   mutation. Repository-wide prune is a separate reviewed operation, not hidden
   inside this short barrier. A dedicated controller must own EX through the
   remote operation and kill/join its own subprocess group before releasing it.
   SSH disconnect, timeout and process death must release ownership without
   leaving a detached forget running. A local shell timeout alone proves none
   of these remote lifecycle properties.

The fixture demonstrates active-writer noninterruption; nonblocking maintenance
refusal; next-writer wait/resume; the exact child-published-after-old-plan race
being caught by the EX replan; persistent producer-root protection before a
child exists; next-writer missing-parent refusal/explicit rebase; and crash/kill
release. The first fork-based test harness inherited the parent's lock file
descriptor, so the final harness uses independent spawned processes. Actual
wrappers must avoid inherited descriptor leaks and define intentional ownership
for children; blindly forking a controller is unsafe.

## Real migration surface observed read-only on 13 November

All enabled, manual, legacy and external repository writers must be inventoried,
not merely the most recent successful publisher. The following installed paths
were observed; this table does not claim they were modified or all are active.

| Source / unit | Required placement if this design were chosen |
| --- | --- |
| `neo-hourly-online-run.py` / `neo-main-hourly-files.service` | SH before `wait_marker_delivery` reads the cached PITR snapshot; retain through hourly backup and receipt. Native file capture and application write gate stay separate. |
| `neo-main-pitr-ship.sh` / `neo-main-pitr-ship.service` | SH before base/WAL state selection through self-contained restic publication; establish lock ordering against its existing `job.lock`. |
| `neo-main-pitr-rotate.sh` / `neo-main-pitr-rotate.service` | Wrap all parent/base selection; avoid recursively acquiring the common barrier through called ship scripts. Keep physical source-base identity pinned. |
| `neo-main-preview-collect.sh` / both preview backup unit names | Wrap before any parent/source selection through publication; aliases may not bypass the protocol. |
| `neo-builder-preview-config-collect.py` and `neo-builder-preview-config-backup.sh` | SH before fixed full-parent lookup through config-child publication. |
| `neo-main-ops-config-delta.sh` / matching service | SH before fixed full-parent lookup through publication. |
| `neo-main-ops-config-tls-delta.sh` / matching service | SH before fixed full and ops-parent lookup through publication. |
| `neo-hostinger-stage-collect.sh` / `neo-daily-backup.service` | Verify legacy unit state and scope; if it can write the shared repository, wrap or explicitly disable only with review. Do not silently omit it. |
| External workflows, ad-hoc shell/API clients and maintenance | Review the complete source roster and immutable hashes. All publishers need the same controller protocol; unwrapped or unknown writers fail closed. Read-only restore/check clients need native lock compatibility but must not publish. |

A new runtime controller, restricted remote entry point, ownership checks, all
producer wrappers and cross-host lifecycle tests would still be required. None
is installed. The existing read-only observation key must not gain mutation or
controller rights implicitly. Backup schedules must continue to work.

## Smaller alternative under investigation: self-contained future hourly points

Prefer removing the future dependency when the existing native PITR producer
contract permits it. A future hourly format can pin the current immutable
physical base, required WAL and receipt into its sealed tree with hardlinks
under the existing PITR `job.lock`, verify exact named marker and base manifest,
then release that source lock **before** its restic upload. The application write
pause must not include this operation. Restic deduplicates shared immutable bytes;
hardlinks alone do not prove base/WAL immutability or full recovery coverage.

This can eliminate the future `wal_snapshot` cloud-parent dependency, avoiding a
new cross-host publication barrier for those points. It still needs proof that
source files are never overwritten in place, exact base/WAL continuity checks,
bounded local capacity, schema/version and health updates, and an actual named
PG restore from the new hourly point. Old dependent points keep their historical
AS-OF roots; fixed full/ops configuration ancestry remains protected explicitly.
Do not broaden the current once-per-UTC-day full-restore/egress policy to a full
physical PG restore every hour. No install or live format change is authorized
by this prototype document.
