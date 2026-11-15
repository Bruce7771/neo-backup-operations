"""Exact two-point admission regression; no credentials or repository mutations."""
import ast, copy, importlib.util, json, tempfile, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
c=load('two_point',HERE/'reviewed-composed-control.proposed.py')
old=load('unchanged_one_point',HERE/'reviewed-composed-control.one-point-frozen.py')
tree=ast.parse((HERE/'complete-config-retention-engine-test.py').read_text())
fixture=json.loads(next(n.value.args[0].value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)and t.id=='FIXTURE'for t in n.targets)))
NEW={'id':c.NEW_CHILD,'hostname':'srv2140404-main-builder-config','tags':['neo-builder-preview-config'],'paths':['/var/lib/neo-builder-preview-config/capture'],'time':'2026-11-15T15:23:53.380760266Z'}
PARENT={'id':c.PARENT,'hostname':'srv2140404-main-daily-composed','tags':['neo-daily','neo-daily-composed-v1'],'paths':['/var/lib/neo-main-daily-online/capture','/srv/neo-recovery/object-storage/objects']}
OLD=next(r for r in fixture['rows']if r['id']==c.CHILD)
SCOPES={('srv2140404-main-builder-config','neo-builder-preview-config'):'/var/lib/neo-builder-preview-config/capture'}
class Tests(unittest.TestCase):
 def data(self):return copy.deepcopy([OLD,NEW,PARENT]),{c.CHILD,c.NEW_CHILD,c.PARENT}
 def test_both_exact_known_points(self):
  rows,protected=self.data();r=c.reviewed_composed_control(rows,protected,SCOPES)
  self.assertEqual(set(r),{c.CHILD,c.NEW_CHILD});self.assertEqual(r[c.CHILD],old.reviewed_composed_control(rows,protected,SCOPES)[c.CHILD])
  self.assertEqual(r[c.NEW_CHILD]['parent_snapshot'],c.PARENT);self.assertFalse(r[c.NEW_CHILD]['legacy_FULL_classification'])
  self.assertEqual(r[c.NEW_CHILD]['owner_compatible_data_snapshot'],'c559b4041887004930a071de4c1818a624223e97526d338f11eb3d9179a5f351')
 def test_each_unprotected_endpoint_fails(self):
  for sid in (c.CHILD,c.NEW_CHILD,c.PARENT):
   rows,p=self.data();p.remove(sid)
   with self.assertRaisesRegex(ValueError,'endpoints'):c.reviewed_composed_control(rows,p,SCOPES)
 def test_both_native_projections_fail_closed(self):
  for sid in (c.CHILD,c.NEW_CHILD):
   for field,value in [('paths',['/other']),('tags',['other']),('time','2026-11-15T00:00:00Z')]:
    rows,p=self.data();next(r for r in rows if r['id']==sid)[field]=value
    with self.assertRaisesRegex(ValueError,'projection'):c.reviewed_composed_control(rows,p,SCOPES)
 def test_parent_missing_or_wrong_type(self):
  rows,p=self.data()
  with self.assertRaisesRegex(ValueError,'parent absent'):c.reviewed_composed_control(rows[:-1],p,SCOPES)
  rows[-1]['hostname']='srv2140404-main-full'
  with self.assertRaisesRegex(ValueError,'exact composed daily'):c.reviewed_composed_control(rows,p,SCOPES)
 def test_unknown_child_not_granted_admission(self):
  rows,p=self.data();unknown=copy.deepcopy(NEW);unknown['id']='a'*64;rows.append(unknown);p.add(unknown['id'])
  self.assertNotIn(unknown['id'],c.reviewed_composed_control(rows,p,SCOPES))
 def test_actual_generated_planner_unknown_config_still_fails(self):
  # Build the existing engine unchanged, then substitute only this candidate.
  import sys
  with tempfile.TemporaryDirectory()as tmp:
   out=load('two_builder',HERE/'build-complete-config-retention-engine.proposed.py').build(HERE.parent/'scripts',Path(tmp)/'engine')
   sys.path.insert(0,str(out));previous=sys.modules.get('reviewed_composed_control');sys.modules['reviewed_composed_control']=c
   try:
    planner=load('two_actual_planner',out/'retention-plan.py');inv,plans,p,restored=planner.PlannerTests().data()
    planner.CONFIG_SCOPES={**planner.CONFIG_SCOPES,**SCOPES};inv=inv+copy.deepcopy([OLD,NEW,PARENT]);p=p+list({c.CHILD,c.NEW_CHILD,c.PARENT})
    r=planner.PlannerTests().invoke(inv,plans,p,restored);self.assertEqual(set(r['typed_composed_control_dependencies']),{c.CHILD,c.NEW_CHILD})
    unknown=copy.deepcopy(NEW);unknown['id']='a'*64;inv.append(unknown);p.append(unknown['id'])
    with self.assertRaises(ValueError):planner.PlannerTests().invoke(inv,plans,p,restored)
   finally:
    sys.path.pop(0)
    if previous is None:sys.modules.pop('reviewed_composed_control',None)
    else:sys.modules['reviewed_composed_control']=previous
if __name__=='__main__':unittest.main()
