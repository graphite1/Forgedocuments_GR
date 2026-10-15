"""Unsigned preview audit and release. No GRHub, signing vault or new credentials."""
import argparse,hashlib,io,json,os,re,subprocess,sys,tempfile,urllib.error,urllib.parse,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
REPOSITORY='graphite1/Forgedocuments_GR'
PACKAGE_NAMES={'Forgedocuments GR.exe','template.json','forms.json','version.json','update_config.json','README.txt','release_files.json'}
PUBLIC_NAMES={'SHA256SUMS.txt','preview-validation.json'}


def sha256(raw):return hashlib.sha256(raw).hexdigest()


def version():return json.loads((ROOT/'version.json').read_text(encoding='utf-8'))


def source_check(source):
    if not re.fullmatch('[0-9a-f]{40}',source):raise ValueError('Expected a full source commit SHA')
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if actual!=source:raise ValueError('Checkout does not match the audited source commit')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise ValueError('Source checkout is not clean')


def audit_zip(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP CRC failed')
        names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=PACKAGE_NAMES:raise ValueError('Unexpected package members')
        manifest=json.loads(archive.read('release_files.json'))
        if set(manifest)!=PACKAGE_NAMES-{'release_files.json'}:raise ValueError('Unexpected release file manifest')
        for name,digest in manifest.items():
            if sha256(archive.read(name))!=digest:raise ValueError('Package hash mismatch: '+name)
        for name in ('template.json','forms.json','version.json','update_config.json'):
            if archive.read(name)!=(ROOT/name).read_bytes():raise ValueError('Package definition differs from source: '+name)
        bundled=json.loads(archive.read('version.json'))
        if bundled!=version():raise ValueError('Package version differs from source')
        if 'Unsigned prerelease for validation' not in archive.read('README.txt').decode('utf-8-sig'):
            raise ValueError('Unsigned preview notice missing')
    return manifest


def audit_embedded(exe):
    from PyInstaller.archive.readers import CArchiveReader
    from tomei_preset import public_bundle_files
    from tomei_print_font import bundle_files as font_files
    from aktio.asset_files import bundle_files as aktio_files
    reader=CArchiveReader(str(exe));names={str(n).replace('\\','/'):n for n in reader.toc}
    forbidden=[n for n in names if (Path(n).suffix.lower() in ('.pdf','.db','.sqlite3','.xlsx','.key','.pem','.zip') and n!='base_library.zip') or
               n.startswith(('data/','private/','private-assets/','test-results/')) or Path(n).name in ('ui_settings.json','records.sqlite3')]
    if forbidden:raise ValueError('Forbidden embedded files: '+repr(forbidden))
    if 'base_library.zip' in names:
        # PyInstaller's standard-library bytecode container is expected runtime data.
        with zipfile.ZipFile(io.BytesIO(reader.extract(names['base_library.zip']))) as standard:
            if standard.testzip() is not None or any(Path(n).suffix!='.pyc' or '..' in Path(n).parts or n.startswith('/') for n in standard.namelist()):
                raise ValueError('Unexpected content in the standard-library archive')
    expected={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()) for p in [*public_bundle_files(),*font_files(),*aktio_files()]}
    for name,digest in expected.items():
        if name not in names or sha256(reader.extract(names[name]))!=digest:raise ValueError('Embedded asset mismatch: '+name)
    for name in ('forms.json','template.json','version.json','update_config.json','templates/tomei_taiheiyo.json','templates/aktio_receipt.json'):
        if name not in names or reader.extract(names[name])!=(ROOT/name).read_bytes():raise ValueError('Embedded definition mismatch: '+name)
    return dict(embedded_asset_sha256=expected,forbidden_embedded_files=[])


def verify_build(output,source,test_report):
    if sys.platform!='win32':raise ValueError('Packaged EXE validation requires Windows')
    source_check(source);output=Path(output);v=version()
    archive=output/f"Forgedocuments_GR-{v['version']}-windows-x64.zip"
    audit_zip(archive)
    exe=output/f"Forgedocuments_GR-{v['version']}-windows-x64"/'Forgedocuments GR.exe'
    embedded=audit_embedded(exe)
    tests=json.loads(Path(test_report).read_text(encoding='utf-8'))
    if tests.get('status')!='passed' or tests.get('failures')!=0 or tests.get('errors')!=0 or tests.get('headless') is not True:
        raise ValueError('Headless source test evidence did not pass')
    # Use a fresh extraction, never the source tree, install folder or a user profile.
    with tempfile.TemporaryDirectory(prefix='forge-exe-') as temp:
        temp=Path(temp);app=temp/'app';app.mkdir()
        with zipfile.ZipFile(archive) as package:package.extractall(app)
        environment=dict(os.environ,APPDATA=str(temp/'profile'),LOCALAPPDATA=str(temp/'local'),FORGEDOCUMENTS_INSTALL_ROOT=str(app),FORGEDOCUMENTS_SKIP_ROUTE='1')
        fonts=Path(environment.get('WINDIR','C:/Windows'))/'Fonts'
        cid=not any((fonts/n).is_file() for n in ('msgothic.ttc','meiryo.ttc'))
        args=[str(app/'Forgedocuments GR.exe'),'--headless-diagnostic','--diagnostic-output',str(temp/'diagnostic')]
        if cid:args.append('--cid-font')
        subprocess.run(args,env=environment,cwd=app,check=True,timeout=180,capture_output=True)
        diagnostic=json.loads((temp/'diagnostic/headless-diagnostic.json').read_text(encoding='utf-8'))
        if diagnostic.get('status')!='passed' or diagnostic.get('windows_executable') is not True or diagnostic.get('gui_checked') is not False:
            raise ValueError('Packaged headless diagnostic did not pass')
        if set(diagnostic.get('forms',{}))!={'ac_toyoake','tomei_taiheiyo','aktio_receipt'}:raise ValueError('A form was not checked')
        audit_zip(archive)  # Diagnostic writes must never enter the distributable.
    report=dict(artifact_type='unsigned_windows_prerelease',source_commit=source,version=v['version'],sequence=v['sequence'],
                archive=archive.name,sha256=sha256(archive.read_bytes()),size_bytes=archive.stat().st_size,
                signed=False,grhub_update=False,tests=tests,packaged_diagnostic=diagnostic,**embedded,
                unverified=['Windows desktop GUI','physical printer and paper','source-PDF pixel overlay'],
                validation_host='GitHub-hosted Windows Server; Windows 10/11 desktop UI not exercised')
    (output/'preview-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checks=[f"{sha256(p.read_bytes())}  {p.name}" for p in (archive,output/'preview-validation.json')]
    (output/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n',encoding='ascii')
    return report


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=super().redirect_request(req,fp,code,msg,headers,newurl)
        if target and urllib.parse.urlsplit(req.full_url).netloc!=urllib.parse.urlsplit(newurl).netloc:
            target.remove_header('Authorization')
        return target


class GitHub:
    def __init__(self,token=None):self.token=token;self.opener=urllib.request.build_opener(SafeRedirect())
    def request(self,url,method='GET',data=None,content_type='application/json',authenticated=True):
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in ('api.github.com','uploads.github.com','github.com','release-assets.githubusercontent.com'):
            raise ValueError('Unexpected GitHub endpoint')
        headers={'User-Agent':'ForgeDocuments-preview','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'}
        if authenticated:
            if not self.token:raise ValueError('Use the existing Actions GITHUB_TOKEN; no credentials are created')
            headers['Authorization']='Bearer '+self.token
        if data is not None:headers['Content-Type']=content_type
        request=urllib.request.Request(url,data=data,headers=headers,method=method)
        try:
            with self.opener.open(request,timeout=120) as response:return response.read()
        except urllib.error.HTTPError as error:
            if error.code==404:return None
            raise RuntimeError(f'GitHub {method} failed with HTTP {error.code}') from None
    def api(self,path,method='GET',data=None):
        raw=self.request('https://api.github.com/'+path,method,json.dumps(data).encode('utf-8') if data is not None else None)
        return json.loads(raw) if raw is not None else None


def release_context(client,source,tag):
    if not re.fullmatch('[0-9a-f]{40}',source):raise ValueError('Expected a full source commit SHA')
    expected='v'+version()['version']+'-preview.1'
    if tag!=expected:raise ValueError('Preview tag differs from source version')
    repo=client.api('repos/'+REPOSITORY)
    if not repo or repo.get('visibility')!='public':raise ValueError('Only the approved public repository is allowed')
    return 'repos/'+REPOSITORY


def guard(client,source,tag):
    source_check(source);base=release_context(client,source,tag)
    if client.api(base+'/releases/tags/'+tag) is not None or client.api(base+'/git/ref/tags/'+tag) is not None:
        raise ValueError('This preview tag/release already exists; refusing a duplicate build or overwrite')
    return {'status':'ready','source_commit':source,'tag':tag,'public_standard_runner_only':True}


def verify_assets(client,release,source,expected=None,public=False):
    if release.get('prerelease') is not True or (public and release.get('draft')):raise ValueError('Expected a published prerelease')
    # Resolve the actual tag, rather than trusting target_commitish text.
    if public:
        ref=client.api('repos/'+REPOSITORY+'/git/ref/tags/'+release['tag_name'])
        if not ref or ref['object']['type']!='commit' or ref['object']['sha']!=source:raise ValueError('Release tag does not point to the audited source commit')
    names=PUBLIC_NAMES|{f"Forgedocuments_GR-{version()['version']}-windows-x64.zip"}
    assets=release.get('assets',[])
    if len(assets)!=len(names) or {a['name'] for a in assets}!=names:raise ValueError('Unexpected release assets')
    downloaded={}
    for asset in assets:
        url=asset['browser_download_url'] if public else asset['url']
        if public:raw=client.request(url,authenticated=False)
        else:
            # The API media type is required for draft asset downloads.
            raw=download_draft(client,url)
        if raw is None:raise ValueError('Release asset cannot be downloaded')
        downloaded[asset['name']]=raw
        if expected and raw!=expected[asset['name']]:raise ValueError('Downloaded release bytes differ: '+asset['name'])
        if asset.get('digest') and asset['digest']!='sha256:'+sha256(raw):raise ValueError('GitHub asset digest mismatch')
    report=json.loads(downloaded['preview-validation.json'])
    if report.get('source_commit')!=source or report.get('signed') is not False or report.get('packaged_diagnostic',{}).get('status')!='passed':
        raise ValueError('Release evidence does not match source and validation')
    checksum_names=set()
    for line in downloaded['SHA256SUMS.txt'].decode('ascii').splitlines():
        digest,name=line.split('  ',1)
        checksum_names.add(name)
        if name not in downloaded or sha256(downloaded[name])!=digest:raise ValueError('Release checksum mismatch')
    if len(downloaded['SHA256SUMS.txt'].decode('ascii').splitlines())!=2:raise ValueError('Unexpected checksum file')
    archive=report['archive']
    if checksum_names!={archive,'preview-validation.json'}:raise ValueError('Checksum coverage mismatch')
    if sha256(downloaded[archive])!=report['sha256']:raise ValueError('Release ZIP differs from evidence')
    audit_zip(io.BytesIO(downloaded[archive]))
    return dict(status='passed',source_commit=source,tag=release['tag_name'],prerelease=True,public_download_verified=public,
                release_url=release['html_url'],sha256=report['sha256'],size_bytes=len(downloaded[archive]),asset_sha256={n:sha256(b) for n,b in downloaded.items()})


def download_draft(client,url):
    # GitHub API returns asset bytes with this Accept header; redirects strip auth.
    request=urllib.request.Request(url,headers={'User-Agent':'ForgeDocuments-preview','Accept':'application/octet-stream','Authorization':'Bearer '+client.token})
    with client.opener.open(request,timeout=120) as response:return response.read()


def publish(output,source,tag,client):
    source_check(source);base=release_context(client,source,tag);output=Path(output)
    report=json.loads((output/'preview-validation.json').read_text(encoding='utf-8'))
    if report['source_commit']!=source or report['artifact_type']!='unsigned_windows_prerelease':raise ValueError('Unaudited source')
    archive=output/report['archive'];audit_zip(archive)
    if sha256(archive.read_bytes())!=report['sha256']:raise ValueError('ZIP changed after validation')
    paths=[archive,output/'SHA256SUMS.txt',output/'preview-validation.json'];expected={p.name:p.read_bytes() for p in paths}
    if client.api(base+'/releases/tags/'+tag) is not None or client.api(base+'/git/ref/tags/'+tag) is not None:
        raise ValueError('Release/tag already exists; no replacement is allowed')
    notes=(ROOT/'docs'/('RELEASE_NOTES_'+version()['version']+'.txt')).read_text(encoding='utf-8')
    notes+='\n\nSource commit: '+source+'\nZIP SHA256: '+report['sha256']+'\nHeadless source tests: '+str(report['tests']['passed'])+' passed, '+str(report['tests']['skipped'])+' skipped.\nPackaged Windows headless diagnostic: passed. Desktop GUI and physical printing: unverified.\n'
    release=client.api(base+'/releases','POST',dict(tag_name=tag,target_commitish=source,name=version()['version']+' unsigned Windows preview',body=notes,draft=True,prerelease=True,make_latest='false'))
    upload=release['upload_url'].split('{',1)[0]
    if urllib.parse.urlsplit(upload).hostname!='uploads.github.com':raise ValueError('Unexpected upload host')
    for path in paths:
        raw=client.request(upload+'?'+urllib.parse.urlencode({'name':path.name}),'POST',expected[path.name],content_type='application/zip' if path.suffix=='.zip' else 'application/octet-stream')
        if raw is None:raise ValueError('Release upload failed')
    release=client.api(base+'/releases/'+str(release['id']))
    verify_assets(client,release,source,expected=expected,public=False)
    release=client.api(base+'/releases/'+str(release['id']),'PATCH',dict(draft=False,prerelease=True,make_latest='false'))
    release=client.api(base+'/releases/'+str(release['id']))
    result=verify_assets(client,release,source,expected=expected,public=True)
    (output/'download-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['guard','audit','publish'])
    parser.add_argument('--source',required=True);parser.add_argument('--tag');parser.add_argument('--output',type=Path);parser.add_argument('--tests',type=Path)
    args=parser.parse_args();client=GitHub(os.environ.get('GH_TOKEN'))
    if args.operation=='guard':result=guard(client,args.source,args.tag)
    elif args.operation=='audit':result=verify_build(args.output,args.source,args.tests)
    else:result=publish(args.output,args.source,args.tag,client)
    print(json.dumps(result,ensure_ascii=False,indent=2))
