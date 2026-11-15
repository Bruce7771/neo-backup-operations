"""No network or service credentials; exact authenticated parent read contract."""
import importlib.util,io,json,pathlib,urllib.error,unittest
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('githubread',H/'publication-github-read.proposed.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
s=importlib.util.spec_from_file_location('coordinator',H/'publication-retention-coordinator.candidate.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
OWN='https://api.github.com/repos/Bruce7771/neo-backup-operations';TOKEN='SYNTHETIC-NOT-A-SERVICE-KEY'
class Response(io.BytesIO):status=200
class Opener:
 def __init__(self):self.requests=[]
 def open(self,r,timeout):
  self.requests.append(r)
  if r.get_header('Authorization')!='Bearer '+TOKEN:raise urllib.error.HTTPError(r.full_url,403,'rate limit exceeded',{},None)
  return Response(b'{"synthetic":true}')
class Tests(unittest.TestCase):
 def setUp(self):self.o=Opener();self.r=m.GitHubRead(TOKEN,['Bruce7771/neo-backup-operations'],self.o)
 def test_anon403_auth200_no_fallback(self):
  import urllib.request
  with self.assertRaises(urllib.error.HTTPError):self.o.open(urllib.request.Request(OWN),10)
  self.assertEqual(self.r(OWN),{'synthetic':True});self.assertEqual(len(self.o.requests),2)
 def test_exact_get_headers(self):
  self.r(OWN+'/environments/NEO_BACKUP_MAINTENANCE');q=self.o.requests[0];self.assertEqual(q.get_method(),'GET');self.assertEqual(q.get_header('Authorization'),'Bearer '+TOKEN)
 def test_other_destinations_and_mutations_refused_before_transport(self):
  for url in ['http://api.github.com/repos/Bruce7771/neo-backup-operations',OWN+'/actions/secrets',OWN+'?x=1',OWN+'#x','https://api.github.com.evil/repos/Bruce7771/neo-backup-operations','https://u@api.github.com/repos/Bruce7771/neo-backup-operations','https://api.github.com:443/repos/Bruce7771/neo-backup-operations','https://api.github.com/repos/foreign/project',OWN+'/actions/runs?status=in_progress&per_page=100&page=4']:
   with self.assertRaises(ValueError):self.r(url)
  self.assertEqual(self.o.requests,[])
 def test_redirect_never_forwarded(self):self.assertIsNone(m.NoRedirect().redirect_request(None,None,None,None,None,'https://evil/'))
 def test_exception_and_repr_redact_header(self):
  class Broken:
   def open(_,r,timeout):raise urllib.error.HTTPError(r.full_url,403,TOKEN,{'Authorization':TOKEN},None)
  r=m.GitHubRead(TOKEN,['Bruce7771/neo-backup-operations'],Broken())
  with self.assertRaisesRegex(ValueError,'^Authenticated GitHub metadata HTTP 403$'):r(OWN)
  self.assertNotIn(TOKEN,repr(r))
 def test_all_required_read_shapes(self):
  for url in [OWN,OWN+'/actions/runs?status=in_progress&per_page=100&page=1',OWN+'/environments/NEO_BACKUP_MAINTENANCE',OWN+'/environments/NEO_BACKUP_MAINTENANCE/deployment-branch-policies?per_page=100']:self.r(url)
  self.assertEqual(len(self.o.requests),4)
 def test_actual_policy_needs_no_invented_roster_field(self):
  self.assertEqual(c.CREDENTIAL_HOLDER_REPOSITORIES,['Bruce7771/neo-backup-operations'])
  source=(H/'publication-retention-coordinator.candidate.py').read_text()
  self.assertNotIn("policy['credential_holder_repositories']",source)
  self.assertIn('observer.observe(CREDENTIAL_HOLDER_REPOSITORIES,',source)
  self.assertIn("GitHubRead(env.pop('NEO_GITHUB_READ_TOKEN'), CREDENTIAL_HOLDER_REPOSITORIES)",source)
 def test_token_not_forwarded_and_all_parent_fetches_wired(self):
  e={'PATH':'/usr/bin:/bin','NEO_GITHUB_READ_TOKEN':TOKEN,'GITHUB_TOKEN':TOKEN,'RESTIC_REPOSITORY':'SYNTHETIC','AWS_ACCESS_KEY_ID':'SYNTHETIC','AWS_SECRET_ACCESS_KEY':'SYNTHETIC','RESTIC_PASSWORD_FILE':'SYNTHETIC','XDG_CACHE_HOME':'SYNTHETIC'}
  for native in (False,True):self.assertNotIn(TOKEN,c.subprocess_environment(e,native).values())
  source=(H/'publication-retention-coordinator.candidate.py').read_text();self.assertEqual(source.count('execution_contract(env, policy, static, fetch)'),3);self.assertIn('fetch=fetch)',source);self.assertIn("env.pop('NEO_GITHUB_READ_TOKEN')",source)
if __name__=='__main__':unittest.main()