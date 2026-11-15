"""Parent-only built-in Actions token, exact reviewed GitHub READ endpoints."""
import json,re,ssl,urllib.error,urllib.parse,urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
class GitHubRead:
 def __init__(self,token,repositories,opener=None):
  if not isinstance(token,str) or not token or not token.isascii() or any(ord(c)<=32 or ord(c)==127 for c in token):raise ValueError('Invalid ephemeral GitHub read credential')
  if not isinstance(repositories,list) or not 1<=len(repositories)<=3 or len(set(repositories))!=len(repositories) or any(not isinstance(r,str) or re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+',r)is None or r.split('/')[1]in('.','..') for r in repositories):raise ValueError('Invalid reviewed public repository roster')
  if 'Bruce7771/neo-backup-operations'not in repositories:raise ValueError('Own operations repository required')
  self._token=token;self._repositories=set(repositories)
  self._opener=opener or urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
 def __repr__(self):return '<GitHubRead parent-only credential redacted>'
 def __call__(self,url):
  u=urllib.parse.urlsplit(url)
  if u.scheme!='https' or u.netloc!='api.github.com' or u.fragment or u.username or u.password:raise ValueError('Unreviewed GitHub read destination')
  allowed=False
  for repo in self._repositories:
   base='/repos/'+repo
   if u.path==base and not u.query:allowed=True
   if u.path==base+'/actions/runs' and u.query in ('status=in_progress&per_page=100&page='+str(n)for n in range(1,4)):allowed=True
  own='/repos/Bruce7771/neo-backup-operations/environments/NEO_BACKUP_MAINTENANCE'
  if u.path==own and not u.query:allowed=True
  if u.path==own+'/deployment-branch-policies' and u.query=='per_page=100':allowed=True
  if not allowed:raise ValueError('Unreviewed GitHub read endpoint')
  request=urllib.request.Request(url,headers={'Authorization':'Bearer '+self._token,'Accept':'application/vnd.github+json','User-Agent':'bounded-maintenance-parent-read','X-GitHub-Api-Version':'2022-11-28'},method='GET')
  try:
   with self._opener.open(request,timeout=10)as response:
    raw=response.read(2*1024*1024+1)
    if response.status!=200 or len(raw)>2*1024*1024:raise ValueError('Incomplete authenticated GitHub read')
    return json.loads(raw)
  except urllib.error.HTTPError as error:raise ValueError('Authenticated GitHub metadata HTTP '+str(error.code))from None
  except urllib.error.URLError:raise ValueError('Authenticated GitHub metadata transport failure')from None