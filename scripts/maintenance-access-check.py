#!/usr/bin/env python3
"""Read-only independent scoped-key and encrypted repository access proof.

No SSH/fence, canary, backup, key creation, deletion, purge or artifact operation.
Private authorization/configuration/inventory responses never reach stdout.
"""
import base64
import json
import os
from pathlib import Path
import re
import resource
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

AUDIT=frozenset(('listBuckets','listFiles','readFiles'))
MAINTENANCE=AUDIT|frozenset(('writeFiles','deleteFiles'))
AUTHORIZE='https://api.backblazeb2.com/b2api/v4/b2_authorize_account'


class CheckFailed(Exception):pass


def require(ok):
    if not ok:raise CheckFailed('read-only-access-boundary-failed')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def safe_api(url):
    value=urllib.parse.urlsplit(url)
    require(value.scheme=='https'and value.hostname is not None
            and(value.hostname=='backblazeb2.com'or value.hostname.endswith('.backblazeb2.com'))
            and value.port in(None,443)and not(value.username or value.password or value.query or value.fragment))
    return value


def repository_target(repository):
    require(isinstance(repository,str)and repository.startswith('s3:https://'))
    parsed=safe_api(repository[3:]);parts=parsed.path.strip('/').split('/')
    require(len(parts)==2 and re.fullmatch('[A-Za-z0-9-]{6,63}',parts[0])is not None and parts[1]=='restic')
    return parts[0],parsed.hostname,'restic/'


def api_json(url,authorization,body=None):
    safe_api(url)
    require(isinstance(authorization,str)and authorization and all(32<=ord(c)<127 for c in authorization))
    payload=None if body is None else json.dumps(body).encode()
    request=urllib.request.Request(url,data=payload,headers={'Authorization':authorization,
        'Content-Type':'application/json'},method='GET'if body is None else'POST')
    opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),NoRedirect())
    with opener.open(request,timeout=30)as response:
        require(response.status==200)
        data=response.read(1024*1024+1);require(len(data)<=1024*1024)
    return json.loads(data)


def verify_authorization(auth,expected,bucket,endpoint,prefix):
    storage=auth['apiInfo']['storageApi'];allowed=storage['allowed']
    capabilities=allowed.get('capabilities');buckets=allowed.get('buckets')
    require(isinstance(capabilities,list)and len(capabilities)==len(expected)and frozenset(capabilities)==expected)
    require(isinstance(buckets,list)and len(buckets)==1 and isinstance(buckets[0].get('id'),str)and buckets[0]['id'])
    require(buckets[0].get('name')in(None,bucket)and allowed.get('namePrefix')==prefix)
    require('applicationKeyExpirationTimestamp'in auth and auth['applicationKeyExpirationTimestamp']is None)
    api=safe_api(storage['apiUrl']);s3=safe_api(storage['s3ApiUrl'])
    require(api.path in('','/')and s3.path in('','/')and s3.hostname==endpoint)
    require(isinstance(auth.get('authorizationToken'),str)and auth['authorizationToken'])
    return buckets[0]['id']


def authorize_pair(key_id,key,expected,bucket,endpoint,prefix,call=api_json):
    require(isinstance(key_id,str)and key_id and isinstance(key,str)and key)
    basic=base64.b64encode((key_id+':'+key).encode()).decode()
    auth=call(AUTHORIZE,'Basic '+basic)
    bucket_id=verify_authorization(auth,expected,bucket,endpoint,prefix)
    # Read-only listBuckets resolves the restricted ID to the exact private
    # repository bucket name even if authorize returned a null bucket name.
    response=call(auth['apiInfo']['storageApi']['apiUrl'].rstrip('/')+'/b2api/v4/b2_list_buckets',
        auth['authorizationToken'],{'accountId':auth['accountId'],'bucketId':bucket_id})
    rows=response.get('buckets')
    require(isinstance(rows,list)and len(rows)==1 and rows[0].get('bucketId')==bucket_id
            and rows[0].get('bucketName')==bucket and rows[0].get('bucketType')=='allPrivate')
    return bucket_id,{'authorized':True,'exact_capabilities':True,'one_expected_private_bucket':True,
                      'exact_prefix':True,'permanent':True,'matching_s3_endpoint':True}


def restic_output(arguments,env,work,maximum=32*1024*1024,timeout=90):
    def restrict():resource.setrlimit(resource.RLIMIT_FSIZE,(maximum,maximum))
    with tempfile.TemporaryFile(dir=work)as out,tempfile.TemporaryFile(dir=work)as errors:
        result=subprocess.run(['restic']+arguments,env=env,stdin=subprocess.DEVNULL,
            stdout=out,stderr=errors,timeout=timeout,preexec_fn=restrict)
        require(result.returncode==0 and out.tell()<=maximum)
        out.seek(0);return out.read(maximum+1)


def verify_repository(key_id,key,repository,password_file,region,work,call=restic_output):
    env={k:v for k,v in os.environ.items()if not k.startswith(('NEO_','AWS_','RESTIC_'))}
    env.update(RESTIC_REPOSITORY=repository,RESTIC_PASSWORD_FILE=str(password_file),
               AWS_ACCESS_KEY_ID=key_id,AWS_SECRET_ACCESS_KEY=key)
    if region:env['AWS_DEFAULT_REGION']=region
    version=call(['version'],env,work,maximum=4096,timeout=10).decode()
    require(version.startswith('restic 0.16.4 '))
    rows=json.loads(call(['--no-cache','--no-lock','snapshots','--json'],env,work))
    require(isinstance(rows,list)and rows and all(isinstance(r,dict)
        and re.fullmatch('[0-9a-f]{64}',r.get('id',''))is not None for r in rows))
    config=json.loads(call(['--no-cache','--no-lock','cat','config'],env,work,maximum=64*1024))
    require(config.get('version')in(1,2)and re.fullmatch('[0-9a-f]{64}',config.get('id',''))is not None)
    return len(rows),config['id']


def main():
    os.umask(0o077)
    env=os.environ
    required=('NEO_B2_AUDIT_KEY_ID','NEO_B2_AUDIT_KEY','NEO_B2_MAINTENANCE_KEY_ID',
              'NEO_B2_MAINTENANCE_KEY','NEO_RESTIC_REPOSITORY','NEO_RESTIC_PASSWORD','RUNNER_TEMP')
    require(all(env.get(name)for name in required))
    # The workflow supplies only the two scoped pairs. Do not consume any
    # administrative/master variable even if accidentally present in the job.
    require(not any(value for name,value in env.items()if 'MASTER'in name.upper()))
    repository=env['NEO_RESTIC_REPOSITORY'];bucket,endpoint,prefix=repository_target(repository)
    scopes=[];results={};configs=[]
    with tempfile.TemporaryDirectory(prefix='neo-maintenance-access-',dir=env['RUNNER_TEMP'])as tmp:
        work=Path(tmp);work.chmod(0o700);password=work/'password'
        password.write_text(env['NEO_RESTIC_PASSWORD']);password.chmod(0o600)
        for label,expected in(('AUDIT',AUDIT),('MAINTENANCE',MAINTENANCE)):
            key_id=env['NEO_B2_'+label+'_KEY_ID'];key=env['NEO_B2_'+label+'_KEY']
            identity,checks=authorize_pair(key_id,key,expected,bucket,endpoint,prefix)
            count,config_id=verify_repository(key_id,key,repository,password,env.get('NEO_B2_REGION'),work)
            scopes.append(identity);configs.append(config_id)
            results[label.lower()]=dict(checks,repository_config_decrypted=True,snapshot_count=count)
        require(scopes[0]==scopes[1]and configs[0]==configs[1])
    print(json.dumps({'scope':'independent-maintenance-access-readonly',**results,
        'same_restricted_bucket':True,'same_encrypted_repository':True,
        'fence_acquired':False,'repository_write_performed':False,'deletion_performed':False,
        'retention_completed':False}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        # No exception values, HTTP response bodies, subprocess stderr or tokens.
        print('::error::Read-only maintenance access check failed ('+type(error).__name__+')',file=sys.stderr)
        raise SystemExit(1)
