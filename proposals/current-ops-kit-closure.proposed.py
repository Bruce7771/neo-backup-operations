"""Exact owner-reviewed new Ops recovery-kit edges; inactive candidate only."""
import hashlib,json,re
HEX=re.compile('[0-9a-f]{64}')
def require(ok,msg):
 if not ok:raise ValueError(msg)
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def projection(row):return {k:row[k]for k in('id','hostname','tags','paths','time')}
def reviewed_kits(inventory,dependencies,configuration_scopes):
 rows={r['id']:r for r in inventory};approved={};roles={}
 for d in dependencies:
  if d.get('kind')!='reviewed-configuration-kit-v1':continue
  require(set(d)=={'child_snapshot','parent_snapshot','kind','child_inventory_sha256','parent_role'},'Unexpected kit authorization field')
  child=d['child_snapshot'];parent=d['parent_snapshot'];digest=d['child_inventory_sha256'];role=d['parent_role']
  require(all(isinstance(v,str)and HEX.fullmatch(v)for v in(child,parent,digest))and role in('full','hourly','config'),'Invalid exact kit authorization')
  require(child in rows,'Authorized kit absent from inventory');r=rows[child]
  require((r['hostname'],'neo-ops-config')in configuration_scopes and 'neo-ops-config'in r.get('tags',[])and len(r.get('paths',[]))==1,'Kit outside existing Main Ops host/tag')
  require(hashlib.sha256(canonical(projection(r))).hexdigest()==digest,'Exact kit inventory projection differs')
  require(child not in approved or approved[child]==digest,'Conflicting kit identity')
  require((child,parent)not in roles,'Duplicate kit edge');approved[child]=digest;roles[child,parent]=role
 return approved,roles

def patch_planner(source):
 def once(a,b):
  nonlocal source
  require(source.count(a)==1,'Planner source anchor changed');source=source.replace(a,b,1)
 once('import unittest','import unittest\nfrom current_ops_kit_closure import reviewed_kits')
 once('    config_ids=set()',"    dependencies=dependencies or []\n    require(isinstance(dependencies,list), 'Invalid child-parent dependency inventory')\n    reviewed,kit_roles=reviewed_kits(inventory,dependencies,CONFIG_SCOPES)\n    required_kit_hourlies=set()\n    config_ids=set()")
 once("require(row.get('paths')==[path], 'Unexpected configuration-only dependency paths')","require(row.get('paths')==[path]or row['id']in reviewed, 'Unexpected configuration-only dependency paths')")
 once("    dependencies=dependencies or []\n    require(isinstance(dependencies,list), 'Invalid child-parent dependency inventory')\n    children=",'    children=')
 old="""            if parent in config_ids:
                verify_ancestry(parent,stack|{child})
            else:
                require(eligible.get(parent)==FULL_MAIN_HOST,
                        'Configuration ancestry must terminate at an authorized full main point')"""
 new="""            role=kit_roles.get((child,parent))
            if parent in config_ids:
                require(child not in reviewed or role=='config','Kit parent role mismatch')
                verify_ancestry(parent,stack|{child})
            elif eligible.get(parent)==FULL_MAIN_HOST:
                require(child not in reviewed or role=='full','Kit parent role mismatch')
            else:
                expected_hourly=next(host for host,(tag,_)in SCOPES.items()if tag=='neo-hourly-files')
                require(child in reviewed and role=='hourly'and eligible.get(parent)==expected_hourly
                        and parent in restored,'Kit hourly parent needs actual restore evidence')
                required_kit_hourlies.add(parent)"""
 once(old,new)
 once('    for host in set(eligible.values()):',"    hourly_by={e['child_snapshot']:e for e in hourly_recovery}\n    require(all(hourly_by[sid].get('kind')=='selfcontained-pg-named-point'and hourly_by[sid].get('metadata_verified')is True for sid in required_kit_hourlies),'Kit hourly parent must be verified self-contained PostgreSQL')\n    for host in set(eligible.values()):")
 return source
