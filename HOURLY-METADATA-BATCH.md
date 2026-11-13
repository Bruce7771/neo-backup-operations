# Bounded hourly metadata fetch

The read-only audit now selects hourly JSON metadata with one native
`restic --no-lock restore --verify` per previously uncached point. Its fixed
include allowlist contains only manifest, capture result, PostgreSQL marker,
delivery metadata and the v3 sealed-PG metadata. A v2 point materializes four
files; its v3-only include matches nothing. V3 requires exactly five. Historical
UNKNOWN formats may have fewer available metadata files; their existing exact
reviewed manifest fingerprint is still required by the unchanged derivation.

No directory-wide include selects SQLite, media, WAL or physical base payload.
The existing separate, bounded exact marker-WAL read and physical base-manifest
authentication remain unchanged. Every selected JSON still obeys the caller's
size limit and is authenticated against the outer manifest; v3 seal identity
also matches delivery metadata. Native restore output is discarded, and no
private snapshot IDs, paths or content are printed.

Checkpoints are private 0700 directories under RUNNER_TEMP, bound to repository,
scope, exact root and full snapshot ID. Individual 0600 files and their record
are fsynced before atomic publication. A completed point survives a later failed
point/audit subprocess in the same runner job; malformed or cross-point cache
records fail closed. They are revalidated on use. There is no cache/artifact
upload and no assumption that ephemeral hosted-runner files survive a new job.

The original **180-second** shared derivation deadline is unchanged. Native
batch restore is bounded to 40 seconds or the smaller remaining budget, with an
8MiB per-file output resource limit plus strict per-name and total-selection
postchecks. Metadata source mutation, backup writers and repository maintenance
are never paused. Safe aggregate output reports native batch/checkpoint counts
and selected JSON bytes, not private metadata.

Thirteen synthetic cases passed on Linux in 0.251 seconds: v2/v3 selection,
same-job checkpoint reuse, scope/root/snapshot/path allowlists, oversize restored
and cached files, traversal, individual hashes, cross-point contamination,
independent point directories, cached read limits/deadline, completed-point
preservation after later failure and exclusion of payload paths. No cloud call
or production mutation was performed by those cases. Actual external audit
duration remains to be measured after review/delivery; batching is not claimed
as a completed production performance result merely from these fixtures.

The NONZERO-maintenance hard block remains unchanged. A successful metadata
batch does not establish full PostgreSQL replay, finite historical closure,
writer-roster enforcement, automatic expiry or a working external cron.
