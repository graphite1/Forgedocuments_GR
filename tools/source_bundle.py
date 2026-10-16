"""Committed source snapshot and third-party license texts for source BAT builds."""
import hashlib,importlib.metadata,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
LEGACY={'start.bat','setup.bat','start_auto.bat','check.bat','bootstrap.py'}
REQUIRED={'app.py','source_bootstrap.py','start_source.bat','setup_source.bat','SOURCE_README_JA.txt','requirements.txt','version.json','forms.json','template.json','update_config.json'}
GENERATED={'source-manifest.json','THIRD_PARTY_NOTICES.md'}


def digest(raw):return hashlib.sha256(raw).hexdigest()


def snapshot(source,repo=ROOT):
    if not re.fullmatch('[0-9a-f]{40}',source):raise ValueError('Source snapshot requires a full SHA')
    raw=subprocess.check_output(['git','ls-tree','-r','-z',source],cwd=repo)
    result={}
    for entry in raw.split(b'\0'):
        if not entry:continue
        meta,path=entry.split(b'\t',1);name=path.decode('utf-8');mode,kind,blob=meta.decode().split()
        if name.startswith('.github/') or name in LEGACY:continue
        if mode!='100644' and mode!='100755':raise ValueError('Source snapshot does not allow symlinks')
        p=Path(name)
        if any(part in {'.git','.venv','.source-venv','source-runtime','data','private','private-assets','build','dist','__pycache__','.dev-tools','test-results'} for part in p.parts):raise ValueError('Private/cache path in source snapshot')
        if p.suffix.lower() in {'.pdf','.xlsx','.db','.sqlite3','.pyc','.zip','.exe','.pem','.key'}:raise ValueError('Private/binary data in source snapshot: '+name)
        if p.suffix.lower() not in {'.py','.json','.txt','.md','.bat','.png','.ttf'} and name not in {'.gitignore','.gitattributes','LICENSE','COPYING','NOTICE'}:raise ValueError('Unreviewed source member: '+name)
        data=subprocess.check_output(['git','cat-file','blob',blob],cwd=repo)
        if p.suffix=='.bat':data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
        result[name]=data
    if not REQUIRED<=set(result):raise ValueError('Source launcher/files are missing: '+str(REQUIRED-set(result)))
    return result


def license_materials(require_build=True):
    roots=['reportlab','PyMuPDF','Pillow','charset-normalizer','cryptography']
    if require_build:roots+=['PyInstaller','pyinstaller-hooks-contrib']
    queue=list(roots);seen=set();files={};notes=[]
    while queue:
        name=queue.pop(0);key=re.sub('[-_.]+','-',name).lower()
        if key in seen:continue
        seen.add(key)
        try:dist=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            if name in roots:raise ValueError('Missing distribution/license metadata: '+name)
            continue
        copied=[]
        for index,file in enumerate(dist.files or []):
            text=str(file).lower();path=Path(dist.locate_file(file))
            if not any(part in text for part in ('license','copying','notice')) or (path.suffix.lower() not in ('','.txt','.md','.rst') and not path.name.upper().startswith(('LICENSE','COPYING','NOTICE'))) or not path.is_file():continue
            data=path.read_bytes()
            if len(data)>2*1024*1024:raise ValueError('Unexpected license text size')
            filename=key+'/'+str(index)+'-'+re.sub('[^A-Za-z0-9_.-]','_',path.name)+'.txt'
            files['third_party_licenses/'+filename]=data;copied.append(filename)
        if name in roots and not copied:raise ValueError('License text missing for '+name)
        label=dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See supplied license text'
        notes.append(f"- {dist.metadata['Name']} {dist.version}: {label}; copied {len(copied)} notice/license files.")
        for requirement in dist.requires or []:
            match=re.match(r'[A-Za-z0-9_.-]+',requirement)
            if match:queue.append(match[0])
    if require_build and sys.platform=='win32':
        runtime=Path(sys.base_prefix);license_=runtime/'LICENSE.txt'
        if not license_.is_file():raise ValueError('Python runtime license missing')
        files['third_party_licenses/python/LICENSE.txt']=license_.read_bytes()
        for name in ('tcl8.6','tk8.6'):
            terms=runtime/'tcl'/name/'license.terms'
            if terms.is_file():files['third_party_licenses/'+name+'/license.terms.txt']=terms.read_bytes()
        notes.append('- CPython runtime LICENSE.txt and installed Tcl/Tk license.terms files copied from the Windows Python distribution.')
    files['THIRD_PARTY_NOTICES.md']=('# Third-party notices\n\nApplication code is the identified repository snapshot; no new application license is granted here. Dependency metadata and original license/notice texts are included below. PyMuPDF distribution metadata states AGPL-3.0 or an Artifex commercial license; no commercial license is asserted by this package.\n\n'+'\n'.join(notes)+'\n').encode('utf-8')
    return files


def stage(directory,source,repo=ROOT,require_build=True):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    code=snapshot(source,repo);licenses=license_materials(require_build)
    overlap=set(code)&set(licenses)
    if overlap:raise ValueError('Source/license path collision')
    payload=dict(code,**licenses)
    for name,raw in payload.items():
        path=directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    manifest={'source_commit':source,'code_files':{name:digest(raw) for name,raw in code.items()},'license_files':{name:digest(raw) for name,raw in licenses.items()},'bat_line_endings':'CRLF; same committed implementation','private_data_included':False,'venv_included':False,'source_runtime_included':False}
    (directory/'source-manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return manifest


def audit(read,names,source,repo=ROOT):
    manifest=json.loads(read('source/source-manifest.json'))
    if manifest['source_commit']!=source or any(manifest[k] is not False for k in ('private_data_included','venv_included','source_runtime_included')):raise ValueError('Source identity/privacy manifest mismatch')
    expected=snapshot(source,repo)
    if manifest['code_files']!={name:digest(raw) for name,raw in expected.items()}:raise ValueError('Source file list differs from committed implementation')
    if set(manifest['code_files'])&set(manifest['license_files']):raise ValueError('Source/license path collision')
    if any(n!='THIRD_PARTY_NOTICES.md' and (not n.startswith('third_party_licenses/') or Path(n).suffix!='.txt' or '..' in Path(n).parts or ':' in n or '\\' in n) for n in manifest['license_files']):raise ValueError('Unexpected license path')
    wanted={'source/source-manifest.json'}|{'source/'+n for n in manifest['code_files']}|{'source/'+n for n in manifest['license_files']}
    if {n for n in names if n.startswith('source/')}!=wanted:raise ValueError('Unexpected source files or caches')
    if 'THIRD_PARTY_NOTICES.md' not in manifest['license_files'] or not any(n.startswith('third_party_licenses/') for n in manifest['license_files']):raise ValueError('Third-party notices missing')
    for name,hash_ in {**manifest['code_files'],**manifest['license_files']}.items():
        if digest(read('source/'+name))!=hash_:raise ValueError('Source/license file hash mismatch: '+name)
    return manifest
