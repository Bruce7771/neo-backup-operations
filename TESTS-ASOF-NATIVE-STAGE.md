# Frozen AS-OF/native-admission stage verification

All checks below used isolated Linux temporary files or a tiny **local synthetic**
encrypted repository. No production B2 mutation, key creation, endpoint install,
service/schedule change or DNS action occurred.

| Test group | Passed |
| --- | ---: |
| Actual retention planner/dependency guard | 19 |
| Hourly metadata/WAL and conservative UNKNOWN derivation | 12 |
| AS-OF schema2: future roots, historical-root loss, fingerprint, exact13 child/count/coverage/order | 9 |
| Read-only writer source/process census and forced-command restrictions | 9 |
| Public external-run observation | 3 |
| Actual planner-bundle rebuild and separate bounded admission | 10 |
| Exact native post-forget inventory transition / no service-fence commands | 5 |
| **Total isolated cases** | **67** |

The final forced-command test initially lacked its `.sh` fixture in the remote
temporary test harness. The missing fixture was included and all four affected
groups passed; no application/source logic was changed to bypass a failure.

Native rehearsal also completed with exit0 on restic0.16.4:

- actual held synthetic backup lock caused `--retry-lock 0s forget` to refuse;
- the held backup completed and released its native lock;
- exact fixture snapshot forget, native prune/check and actual retained SQLite
  restoration passed;
- no cloud repository/configuration/credential was loaded.

The new admission creates separate authority after rebuilding a readonly plan;
the original planner's `apply_ready:false` is not flipped. Busy backups, unknown
clients, stale evidence, unreviewed shared GC and insufficient timer/lease budget
refuse writes without pausing services or starts. New observation forced-command
proposal permits only `writer-status`, never legacy acquire/release or shell.

Runtime observation transport, fixed AS-OF protected-environment metadata and
real nonzero cleanup are not proven by these tests. The previously successful
external zero-candidate check remains a no-op; a new AS-OF external read-only run
must supply its own result after root reviews/delivers metadata and code. No
automatic retention scheduler is claimed.
