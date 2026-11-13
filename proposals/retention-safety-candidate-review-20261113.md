# Code-only retention safety candidate

No scripts under `scripts/`, workflow, environment, keys, cloud snapshots or runtime service were changed. Public deployed Ops d6 remains frozen. Candidate builder `retention-safety-candidate.py` creates only a new disposable output directory and refuses missing/duplicate source anchors.

The candidate fixes explicit protected IDs being processed too late: native REMOVE entries move to KEEP **before** the real hourly derivation selects children. UNKNOWN/ASOF and transitive legacy/PITR parent holds still run, and the exact planner remains authoritative and `apply_ready:false`. A regression executes the actual patched `retention-audit.main`, actual `hourly_recovery.derive`, and separately actual planner build with a previously REMOVE-selected protected hourly point. That point is now classified, retained, and its parent protected.

Scoped daily rules express the approved 30 daily and 3 monthly points. Hourly and PITR retain their existing conservative 30d/daily30/monthly3 rule union. There is no approved 48-hour deletion horizon, and this candidate does not introduce one. The older three proposal files remain historical proposals, not active policy.

One-point, maximum19MiB immutable in-memory metadata cache avoids five repeated on-disk hash/JSON validations for one v3 point. Repository/scope/snapshot identity remains bound by the existing batch; returns are read-only bytes in a read-only mapping. Switching points evicts the old point. A new instance still revalidates private checkpoint data. This is CPU/local-IO improvement only; **it does not solve O(retained v3 × full outer manifest) network scaling or prove the180-second deadline**.

Eight bounded Linux synthetic tests pass (0.422s): protected actual-engine flow, actual planner closure, unapproved48h absence, missing-row no fabrication, duplicate rejection, source unchanged, exact patch anchors, immutable cache/eviction/deadline. No native/cloud subprocess is used by these tests. Fixtures contain synthetic identities only.

Remaining before activation: review the generated patch against the then-current reader-lock changes; preserve default native locks; choose/approve any shorter hourly/PITR horizon; complete authenticated native catalog/receipt design and actual performance trial at expected retained volume; re-run actual read-only external admission before any nonzero maintenance. Deletion authority and all concurrency/fence prerequisites remain unchanged.
