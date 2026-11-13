#!/usr/bin/env python3
"""Validate an exact restic removal manifest. This program never deletes data.

Inputs are restic snapshots --json, three forget --dry-run --json plans,
and owner-controlled arrays of full protected/restore-verified snapshot IDs.
The result is a candidate manifest, not permission to execute it.
"""
import argparse
import hashlib
import json
import pathlib
import re
import unittest

HEX = re.compile(r"^[0-9a-f]{64}$")
SCOPES = {
    "fixture-daily": ("neo-daily", frozenset((
        "/fixture/daily",
        "/fixture/media"))),
    "fixture-pitr": ("neo-main-pitr", frozenset((
        "/fixture/pitr",))),
    "fixture-hourly": ("neo-hourly-files", frozenset((
        "/fixture/hourly",))),
}
CONFIG_SCOPES={
    ('fixture-ops','neo-ops-config'):'/fixture/ops',
    ('fixture-tls','neo-tls-config'):'/fixture/tls',
}
FULL_MAIN_HOST='fixture-daily'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def ids(values):
    require(isinstance(values, list), "ID inventory must be an array")
    require(all(isinstance(v, str) and HEX.fullmatch(v) for v in values),
            "Use full 64-character snapshot IDs")
    require(len(values) == len(set(values)), "Duplicate snapshot ID")
    return set(values)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def validate_hourly_recovery(retained, eligible, protected, restored, evidence, hourly_host, pitr_host):
    """Missing metadata never means legacy or self-contained PostgreSQL."""
    hourly={sid for sid in retained if eligible.get(sid)==hourly_host}
    require(isinstance(evidence,list), 'Hourly recovery evidence must be an explicit array')
    require(all(isinstance(e,dict) for e in evidence), 'Invalid hourly recovery record')
    children=[e.get('child_snapshot') for e in evidence]
    require(all(isinstance(child,str) for child in children), 'Invalid hourly child snapshot')
    require(len(children)==len(set(children)) and set(children)==hourly,
            'Every retained hourly point needs exact reviewed recovery metadata')
    for edge in evidence:
        require(isinstance(edge.get('evidence_sha256'),str) and HEX.fullmatch(edge['evidence_sha256']) and
                edge.get('verified') is True, 'Hourly metadata needs verified content hash')
        require(edge.get('source') in ('postgres-archive-delivery.json','reviewed-external-policy'),
                'Unknown hourly dependency evidence source')
        if edge.get('kind')=='sqlite-files-only':
            require(edge.get('postgres_recovery_included') is False and
                    not any(k in edge for k in ('wal_snapshot','restore_point','wal_segment')),
                    'SQLite-only evidence must not claim PostgreSQL recovery')
            continue
        require(edge.get('kind')=='pitr-named-point', 'Unknown hourly recovery format; refuse retention')
        parent=edge.get('wal_snapshot')
        require(isinstance(parent,str) and parent in retained and parent in protected and
                eligible.get(parent)==pitr_host,
                'Hourly PITR dependency is absent, unprotected or selected for removal')
        require(edge.get('delivery_verified') is True and
                isinstance(edge.get('restore_point'),str) and
                re.fullmatch(r'neo_hourly_[0-9]+_[0-9a-f]{8}',edge['restore_point']) and
                isinstance(edge.get('wal_segment'),str) and re.fullmatch(r'[0-9A-F]{24}',edge['wal_segment']),
                'Hourly named point needs verified delivery and exact recovery target')
    return evidence


def build(inventory, plans, protected, restored, dependencies=None, hourly_recovery=None):
    require(isinstance(inventory, list), "Invalid restic snapshot inventory")
    all_ids = ids([row["id"] for row in inventory])
    protected = ids(protected)
    restored = ids(restored)
    require(protected, "Explicit protected snapshot inventory is required")
    require(protected <= all_ids and restored <= all_ids,
            "Protected/restore evidence references an absent snapshot")
    rows = {row["id"]: row for row in inventory}
    eligible = {}
    for row in inventory:
        host = row.get("hostname")
        if host not in SCOPES:
            continue
        tag, paths = SCOPES[host]
        if tag not in row.get("tags", []):
            continue
        require(frozenset(row.get("paths", [])) == paths,
                "Unexpected paths for an authorized Neo backup scope")
        eligible[row["id"]] = host
    require(eligible, "No authorized Neo snapshots in inventory")
    keep, remove = set(), set()
    planned = set()
    for plan in plans:
        require(isinstance(plan, list), "Invalid forget JSON")
        for group in plan:
            for kind, target in (("keep", keep), ("remove", remove)):
                for row in group.get(kind) or []:
                    sid = row["id"]
                    require(HEX.fullmatch(sid) and sid in eligible,
                            "Plan contains absent/out-of-scope snapshot")
                    require(sid not in planned, "Snapshot appears twice in plan")
                    require(row.get("hostname") == rows[sid].get("hostname"),
                            "Plan/inventory owner mismatch")
                    require(frozenset(row.get("paths", [])) ==
                            frozenset(rows[sid].get("paths", [])),
                            "Plan/inventory path mismatch")
                    planned.add(sid)
                    target.add(sid)
    require(planned == set(eligible),
            "Plan is incomplete or inventory changed: regenerate while fenced")
    require(not protected & remove, "Removal intersects a protected snapshot")
    config_ids=set()
    for row in inventory:
        for (host,tag),path in CONFIG_SCOPES.items():
            if row.get('hostname')==host and tag in row.get('tags',[]):
                require(row.get('paths')==[path], 'Unexpected configuration-only dependency paths')
                config_ids.add(row['id'])
    dependencies=dependencies or []
    require(isinstance(dependencies,list), 'Invalid child-parent dependency inventory')
    children=[d['child_snapshot'] for d in dependencies]
    edges={(d['child_snapshot'],d['parent_snapshot']) for d in dependencies}
    require(len(edges)==len(dependencies) and set(children)==config_ids,
            'Every retained configuration delta needs its exact full-parent dependency')
    for dependency in dependencies:
        parent=dependency['parent_snapshot'];child=dependency['child_snapshot']
        require(parent in all_ids and parent in protected and parent not in remove,
                'Configuration delta parent is absent, unprotected or selected for removal')
        require(child in restored, 'Configuration delta needs explicit restore evidence')
    def verify_ancestry(child,stack):
        require(child not in stack,'Configuration dependency cycle')
        for _,parent in (edge for edge in edges if edge[0]==child):
            if parent in config_ids:
                verify_ancestry(parent,stack|{child})
            else:
                require(eligible.get(parent)==FULL_MAIN_HOST,
                        'Configuration ancestry must terminate at an authorized full main point')
    for child in config_ids:verify_ancestry(child,set())
    hourly_host=next(host for host,(tag,_) in SCOPES.items() if tag=='neo-hourly-files')
    pitr_host=next(host for host,(tag,_) in SCOPES.items() if tag=='neo-main-pitr')
    hourly_recovery=validate_hourly_recovery(all_ids-remove,eligible,protected,restored,
                                             hourly_recovery,hourly_host,pitr_host)
    for host in set(eligible.values()):
        host_kept = {sid for sid in keep if eligible[sid] == host}
        require(host_kept and host_kept & restored,
                "Each retained Neo scope needs an explicit restore-verified point")
    return {
        "schema": 1,
        "mode": "candidate-only-no-deletion",
        "inventory_sha256": hashlib.sha256(canonical(sorted(
            inventory, key=lambda r: r["id"]))).hexdigest(),
        "remove_snapshot_ids": sorted(remove),
        "protected_snapshot_ids": sorted(protected),
        "retained_snapshot_ids": sorted(all_ids - remove),
        "unrelated_snapshots_preserved": len(all_ids - set(eligible) - config_ids),
        "configuration_deltas_preserved":len(config_ids),
        "protected_child_parent_dependencies":dependencies,
        "hourly_recovery_dependencies":hourly_recovery,
        "requires_writer_fence_and_fresh_inventory": bool(remove),
        "apply_ready": False,
        "physical_b2_versions_selected": False,
    }


class PlannerTests(unittest.TestCase):
    def test_hourly_without_metadata_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'Hourly recovery evidence'):
            self.invoke(*self.data(),hourly_recovery=None)

    def test_hourly_missing_edge_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'Every retained hourly'):
            self.invoke(*self.data(),hourly_recovery=[])

    def hourly_pitr_fixture(self):
        inv,plans,protected,restored=self.data()
        hourly=next(r for r in inv if 'neo-hourly-files' in r['tags'])
        parent=next(r for r in inv if 'neo-main-pitr' in r['tags'])
        edge=dict(child_snapshot=hourly['id'],wal_snapshot=parent['id'],kind='pitr-named-point',
                  evidence_sha256='e'*64,source='postgres-archive-delivery.json',verified=True,
                  delivery_verified=True,restore_point='neo_hourly_1234567890_abcdef01',wal_segment='A'*24)
        return inv,plans,protected+[parent['id']],restored,[edge]

    def test_hourly_pitr_parent_preserved(self):
        inv,plans,protected,restored,edges=self.hourly_pitr_fixture()
        result=self.invoke(inv,plans,protected,restored,hourly_recovery=edges)
        self.assertIn(edges[0]['wal_snapshot'],result['retained_snapshot_ids'])
        self.assertEqual(result['hourly_recovery_dependencies'],edges)

    def test_hourly_shared_chain_needs_no_restore_for_every_point(self):
        inv,plans,protected,restored,edges=self.hourly_pitr_fixture()
        parent=next(r for r in inv if 'neo-main-pitr' in r['tags'])
        child=next(r for r in inv if 'neo-hourly-files' in r['tags'])
        # Existing per-scope restored chains remain verified. Newly checked
        # metadata/parent integrity must not force another full physical restore.
        new_parent=dict(parent,id='b'*64)
        new_child=dict(child,id='c'*64)
        inv.extend([new_parent,new_child])
        edges.append(dict(edges[0],child_snapshot=new_child['id'],wal_snapshot=new_parent['id']))
        result=self.invoke(inv,plans,protected+[new_parent['id']],restored,hourly_recovery=edges)
        self.assertIn(new_parent['id'],result['retained_snapshot_ids'])
        self.assertNotIn(new_parent['id'],restored)
        self.assertNotIn(new_child['id'],restored)
        self.assertEqual(len(result['hourly_recovery_dependencies']),2)

    def test_hourly_unprotected_parent_fails(self):
        inv,plans,protected,restored,edges=self.hourly_pitr_fixture()
        with self.assertRaisesRegex(ValueError,'Hourly PITR dependency'):
            self.invoke(inv,plans,protected[:1],restored,hourly_recovery=edges)

    def test_hourly_unverified_delivery_fails(self):
        inv,plans,protected,restored,edges=self.hourly_pitr_fixture()
        edges[0]['delivery_verified']=False
        with self.assertRaisesRegex(ValueError,'verified delivery'):
            self.invoke(inv,plans,protected,restored,hourly_recovery=edges)

    def test_hourly_sqlite_only_cannot_claim_pitr(self):
        inv,plans,protected,restored,edges=self.hourly_pitr_fixture()
        edges[0].update(kind='sqlite-files-only',postgres_recovery_included=False)
        with self.assertRaisesRegex(ValueError,'must not claim PostgreSQL'):
            self.invoke(inv,plans,protected,restored,hourly_recovery=edges)

    def test_hourly_duplicate_and_wrong_parent_fail(self):
        inv,plans,protected,restored,edges=self.hourly_pitr_fixture()
        with self.assertRaisesRegex(ValueError,'exact reviewed'):
            self.invoke(inv,plans,protected,restored,hourly_recovery=edges+edges)
        edges[0]['wal_snapshot']=inv[0]['id']
        with self.assertRaisesRegex(ValueError,'Hourly PITR dependency'):
            self.invoke(inv,plans,protected,restored,hourly_recovery=edges)

    def invoke(self,inventory,plans,protected,restored,dependencies=None,hourly_recovery='fixture'):
        if hourly_recovery=='fixture':
            removed={r['id'] for plan in plans for group in plan for r in group.get('remove',[])}
            hourly_recovery=[dict(child_snapshot=r['id'],kind='sqlite-files-only',verified=True,
                                  source='reviewed-external-policy',evidence_sha256='e'*64,postgres_recovery_included=False)
                             for r in inventory if 'neo-hourly-files' in r.get('tags',[]) and r['id'] not in removed]
        return build(inventory,plans,protected,restored,dependencies,hourly_recovery)

    def data(self):
        inv = []
        for i, (host, (tag, paths)) in enumerate(SCOPES.items(), 1):
            inv.append(dict(id=str(i)*64, hostname=host, tags=[tag], paths=sorted(paths)))
        return inv, [[{"keep": inv, "remove": []}]], [inv[0]["id"]], [r["id"] for r in inv]

    def test_read_only_no_expiry(self):
        result = self.invoke(*self.data())
        self.assertEqual(result["remove_snapshot_ids"], [])
        self.assertFalse(result["apply_ready"])

    def test_protected_not_removed(self):
        inv, _, protected, restored = self.data()
        with self.assertRaisesRegex(ValueError, "protected"):
            self.invoke(inv, [[dict(keep=inv[1:], remove=inv[:1])]], protected, restored)

    def test_changed_inventory_fails(self):
        inv, plans, protected, restored = self.data()
        extra = dict(inv[0], id="a"*64)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.invoke(inv + [extra], plans, protected, restored)

    def test_unrelated_cannot_be_deleted(self):
        inv, plans, protected, restored = self.data()
        extra = dict(id="a"*64, hostname="unrelated", tags=[], paths=["/unrelated"])
        inv.append(extra)
        plans.append([dict(keep=[], remove=[extra])])
        with self.assertRaisesRegex(ValueError, "out-of-scope"):
            self.invoke(inv, plans, protected, restored)

    def test_unrelated_retained(self):
        inv, plans, protected, restored = self.data()
        extra = dict(id="a"*64, hostname="unrelated", tags=[], paths=["/unrelated"])
        result = self.invoke(inv + [extra], plans, protected, restored)
        self.assertIn(extra["id"], result["retained_snapshot_ids"])

    def test_unknown_paths_fail(self):
        inv, plans, protected, restored = self.data()
        inv[0]["paths"] = ["/different"]
        with self.assertRaisesRegex(ValueError, "Unexpected paths"):
            self.invoke(inv, plans, protected, restored)

    def test_unverified_scope_fails(self):
        inv, plans, protected, restored = self.data()
        with self.assertRaisesRegex(ValueError, "restore-verified"):
            self.invoke(inv, plans, protected, restored[:1])

    def test_operations_delta_requires_parent_map(self):
        inv,plans,protected,restored=self.data()
        ops=dict(id='a'*64,hostname='fixture-ops',tags=['neo-ops-config'],paths=['/fixture/ops'])
        with self.assertRaisesRegex(ValueError,'full-parent'):
            self.invoke(inv+[ops],plans,protected,restored+[ops['id']])

    def test_operations_delta_preserves_parent(self):
        inv,plans,protected,restored=self.data()
        ops=dict(id='a'*64,hostname='fixture-ops',tags=['neo-ops-config'],paths=['/fixture/ops'])
        dependency=dict(child_snapshot=ops['id'],parent_snapshot=inv[0]['id'])
        result=self.invoke(inv+[ops],plans,protected,restored+[ops['id']],[dependency])
        self.assertEqual(result['configuration_deltas_preserved'],1)
        self.assertIn(dependency['parent_snapshot'],result['retained_snapshot_ids'])


def main():
    global SCOPES, CONFIG_SCOPES, FULL_MAIN_HOST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--inventory", type=pathlib.Path)
    parser.add_argument("--plan", action="append", type=pathlib.Path)
    parser.add_argument("--protected", type=pathlib.Path)
    parser.add_argument("--restore-evidence", type=pathlib.Path)
    parser.add_argument("--dependencies", type=pathlib.Path)
    parser.add_argument("--hourly-recovery", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--policy", type=pathlib.Path)
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PlannerTests)
        raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())
    if not all((args.inventory, args.plan, args.protected, args.restore_evidence, args.output, args.policy)):
        parser.error("all input files and --output are required")
    read = lambda p: json.loads(p.read_text())
    policy=read(args.policy)
    require(policy.get('schema')==1, 'Unsupported private scope policy')
    scope_rows=policy.get('scopes')
    config_rows=policy.get('configuration_scopes')
    require(isinstance(scope_rows,list) and len(scope_rows)==3, 'Exactly three authorized backup scopes required')
    require({r.get('kind') for r in scope_rows}=={'daily','pitr','hourly'}, 'Explicit daily, pitr and hourly kinds required')
    require(isinstance(config_rows,list), 'Configuration scope policy is required')
    require(all(isinstance(r.get('host'),str) and r['host'] and isinstance(r.get('tag'),str) and r['tag']
                and isinstance(r.get('paths'),list) and r['paths'] and all(isinstance(p,str) and p.startswith('/') for p in r['paths'])
                for r in scope_rows+config_rows), 'Invalid private host/tag/path policy')
    require(len({r['host'] for r in scope_rows})==3, 'Duplicate backup scope host')
    require(all(len(r['paths'])==1 for r in config_rows), 'Configuration scope must use one exact path')
    SCOPES={r['host']:(r['tag'],frozenset(r['paths'])) for r in scope_rows}
    CONFIG_SCOPES={(r['host'],r['tag']):r['paths'][0] for r in config_rows}
    require(len(CONFIG_SCOPES)==len(config_rows), 'Duplicate configuration scope')
    FULL_MAIN_HOST=next(r['host'] for r in scope_rows if r['kind']=='daily')
    result = build(read(args.inventory), [read(p) for p in args.plan],
                   read(args.protected), read(args.restore_evidence),
                   read(args.dependencies) if args.dependencies else [],
                   read(args.hourly_recovery) if args.hourly_recovery else None)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("Candidate validated; no deletion executed")


if __name__ == "__main__":
    main()
