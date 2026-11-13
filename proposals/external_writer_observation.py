#!/usr/bin/env python3
"""Public GitHub-run observation; no token, secrets, mutations or scheduler."""
import hashlib
import json
import re
import ssl
import time
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def get(url):
    if not url.startswith('https://api.github.com/repos/'):raise ValueError('Unexpected public API destination')
    request=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'bounded-backup-writer-observation'})
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
    with opener.open(request,timeout=10)as response:
        raw=response.read(2*1024*1024+1)
        if response.status!=200 or len(raw)>2*1024*1024:raise ValueError('Incomplete public writer observation')
        return json.loads(raw)


def observe(repositories,current_repository,current_run_id,fetch=get,now=time.time):
    if not isinstance(repositories,list)or not 1<=len(repositories)<=3 or len(set(repositories))!=len(repositories):
        raise ValueError('Explicit repository credential-holder roster required')
    other=[];observed=[]
    for repository in repositories:
        if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository)is None or any(p in('.', '..')for p in repository.split('/')):
            raise ValueError('Invalid public repository identity')
        base='https://api.github.com/repos/'+repository
        meta=fetch(base)
        if meta.get('private')is not False or meta.get('full_name')!=repository:
            raise ValueError('Only the reviewed public credential-holder repository is observable without tokens')
        count=0;seen=set()
        for page in range(1,4):
            body=fetch(base+'/actions/runs?status=in_progress&per_page=100&page='+str(page))
            rows=body.get('workflow_runs');total=body.get('total_count')
            if not isinstance(rows,list)or type(total)is not int or not 0<=total<=300:
                raise ValueError('Incomplete writer-run pagination')
            for row in rows:
                identity=row.get('id')
                if type(identity)is not int or identity in seen or row.get('status')!='in_progress':
                    raise ValueError('Run set changed or returned unexpected state')
                seen.add(identity);count+=1;observed.append([repository,identity,row.get('head_sha')])
                if repository!=current_repository or str(identity)!=str(current_run_id):other.append(identity)
            if count==total:break
            if page==3 or not rows:raise ValueError('Incomplete writer-run inventory')
    return {'schema':1,'complete':True,'observed_epoch':int(now()),'repositories':repositories,
            'other_running_jobs':len(other),'read_only_or_unknown_jobs_treated_conservatively_as_busy':True,
            'observation_sha256':hashlib.sha256(json.dumps(observed,sort_keys=True).encode()).hexdigest(),
            'token_used':False,'service_or_schedule_changes':False}
