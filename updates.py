"""GRHub signed Windows updates. User data is never in the application archive."""
import base64,hashlib,json,os,re,shutil,sqlite3,subprocess,sys,time,uuid,zipfile
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from datetime import datetime
from contextlib import closing
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from core import atomic_json

BASE=Path(__file__).resolve().parent
EXE='Forgedocuments GR.exe'
MAX_ZIP=180*1024*1024

def metadata():return json.loads((BASE/'version.json').read_text(encoding='utf-8'))
def config():return json.loads((BASE/'update_config.json').read_text(encoding='utf-8'))
def install_root():return Path(os.environ.get('FORGEDOCUMENTS_INSTALL_ROOT',str(Path(sys.executable).parent if getattr(sys,'frozen',False) else BASE))).resolve()
def canonical(m):return json.dumps(m,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')

def validate_manifest(m,cfg=None):
    cfg=cfg or config()
    if set(m)!={'app_id','version','sequence','schema_version','minimum_updater_version','published_at','release_notes','download_url','sha256','key_id','signature'}:raise ValueError('更新情報の形式が不正です')
    if m['app_id']!=cfg['app_id'] or m['schema_version']!=1 or m['key_id']!=cfg['key_id']:raise ValueError('別アプリまたは未対応の更新情報です')
    if type(m['sequence']) is not int or m['sequence']<1 or not re.fullmatch(r'\d+\.\d+\.\d+',m['version']):raise ValueError('更新版番号が不正です')
    if tuple(map(int,m['minimum_updater_version'].split('.')))>tuple(map(int,metadata()['updater_version'].split('.'))):raise ValueError('更新機能の互換性がありません。新規配布版を使用してください')
    if not re.fullmatch('[0-9a-f]{64}',m['sha256']):raise ValueError('SHA256が不正です')
    expected=cfg['hub_url'].rstrip('/')+f"/api/apps/{cfg['app_id']}/releases/{m['sequence']}/download"
    if m['download_url']!=expected:raise ValueError('更新ファイルの配布先が一致しません')
    unsigned={k:v for k,v in m.items() if k!='signature'}
    try:Ed25519PublicKey.from_public_bytes(base64.b64decode(cfg['public_key'],validate=True)).verify(base64.b64decode(m['signature'],validate=True),canonical(unsigned))
    except Exception as e:raise ValueError('更新情報の署名を確認できません') from e
    return m

def fetch_latest():
    cfg=config();url=cfg['hub_url'].rstrip('/')+f"/api/apps/{cfg['app_id']}/releases/latest"
    with urlopen(Request(url,headers={'User-Agent':'Forgedocuments-GR/'+metadata()['version']}),timeout=20) as r:
        raw=r.read(65537)
    if len(raw)>65536:raise ValueError('更新情報が大きすぎます')
    return validate_manifest(json.loads(raw))

def newer(m,current=None):
    current=current or metadata()
    return m['sequence']>current['sequence'] and tuple(map(int,m['version'].split('.')))>tuple(map(int,current['version'].split('.')))

def extract_archive(archive,target):
    target=Path(target)
    if target.exists():raise ValueError('更新展開先が既に存在します')
    with zipfile.ZipFile(archive) as z:
        seen=set();total=0
        for item in z.infolist():
            name=item.filename
            if not name or '\\' in name or name.startswith('/') or ':' in name:raise ValueError('更新ZIPのパスが不正です')
            parts=Path(name).parts
            if '..' in parts or '.' in parts or name.casefold() in seen or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('更新ZIPのパスが不正です')
            seen.add(name.casefold());total+=item.file_size
            if item.file_size>MAX_ZIP or total>MAX_ZIP*2:raise ValueError('更新ZIPが大きすぎます')
            if not (name in {EXE,'version.json','forms.json','template.json','update_config.json','README.txt','release_files.json'} or name.startswith('docs/')):raise ValueError('更新ZIPに対象外ファイルがあります: '+name)
        if not {EXE.casefold(),'version.json','release_files.json'}<=seen:raise ValueError('更新ファイルが不足しています')
        target.mkdir(parents=True)
        try:
            z.extractall(target)
            files=json.loads((target/'release_files.json').read_text(encoding='utf-8'))
            expected={x.filename for x in z.infolist()}-{'release_files.json'}
            if set(files)!=expected:raise ValueError('配布ファイル一覧が一致しません')
            for name,digest in files.items():
                if hashlib.sha256((target/name).read_bytes()).hexdigest()!=digest:raise ValueError('展開後のファイルが一致しません')
        except Exception:
            shutil.rmtree(target);raise

def stage_archive(archive,m,root=None):
    validate_manifest(m)
    if not newer(m):raise ValueError('現在版より新しい更新ではありません')
    archive=Path(archive);root=Path(root or install_root())
    if archive.stat().st_size>MAX_ZIP or hashlib.sha256(archive.read_bytes()).hexdigest()!=m['sha256']:raise ValueError('更新ZIPのSHA256が一致しません')
    directory=root/'.updates'/'releases'/f"{m['sequence']}-{m['version']}-{uuid.uuid4().hex[:8]}"
    extract_archive(archive,directory)
    v=json.loads((directory/'version.json').read_text(encoding='utf-8'))
    if v['app_id']!=m['app_id'] or v['version']!=m['version'] or v['sequence']!=m['sequence'] or v['data_schema']!=metadata()['data_schema']:raise ValueError('データ形式または版番号の互換性がありません')
    atomic_json(directory/'signed_manifest.json',m)
    shutil.copy2(archive,directory/'_signed_archive.zip')
    return directory

def download(m,root=None):
    validate_manifest(m);root=Path(root or install_root());staging=root/'.updates';staging.mkdir(parents=True,exist_ok=True)
    archive=staging/('download-'+uuid.uuid4().hex+'.zip')
    try:
        with urlopen(Request(m['download_url'],headers={'User-Agent':'Forgedocuments-GR'}),timeout=30) as response,archive.open('wb') as out:
            if urlparse(response.url).netloc!=urlparse(config()['hub_url']).netloc:raise ValueError('別の配布先へ転送されました')
            total=0
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>MAX_ZIP:raise ValueError('更新ZIPが大きすぎます')
                out.write(chunk)
        return stage_archive(archive,m,root)
    finally:archive.unlink(missing_ok=True)

def verify_staged(directory):
    directory=Path(directory);m=validate_manifest(json.loads((directory/'signed_manifest.json').read_text(encoding='utf-8')))
    archive=directory/'_signed_archive.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=m['sha256']:raise ValueError('準備済みZIPが署名情報と一致しません')
    with zipfile.ZipFile(archive) as z:files=json.loads(z.read('release_files.json'))
    for name,digest in files.items():
        path=(directory/name).resolve()
        if not path.is_relative_to(directory.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('準備済み更新ファイルが変更されています')
    return m

def backup_data(directories,root):
    target=Path(root)/'.updates'/'backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');target.mkdir(parents=True)
    inventory=[]
    for i,path in enumerate(dict.fromkeys(str(Path(p).resolve()) for p in directories)):
        source=Path(path);db=source/'records.sqlite3';dest=target/str(i);dest.mkdir()
        if db.exists():
            with closing(sqlite3.connect('file:'+db.as_posix()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(dest/'records.sqlite3')) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('バックアップの整合性確認に失敗しました')
        if (source/'template.json').exists():shutil.copy2(source/'template.json',dest/'template.json')
        inventory.append({'source':path,'backup':str(dest)})
    atomic_json(target/'inventory.json',inventory);return target

def child_env(root):
    env=os.environ.copy();env['FORGEDOCUMENTS_INSTALL_ROOT']=str(root);env['FORGEDOCUMENTS_SKIP_ROUTE']='1';return env

def run_diagnostic(exe,root):
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    result=subprocess.run([str(exe),'--diagnostic'],env=child_env(root),timeout=45,creationflags=flags)
    if result.returncode:raise ValueError('更新版の起動診断に失敗しました')

def request_apply(directory,directories):
    if not getattr(sys,'frozen',False):raise ValueError('開発用ソースの更新はGitを使用してください。exe配布版ではアプリ内更新を利用できます')
    root=install_root();directory=Path(directory);verify_staged(directory)
    run_diagnostic(directory/EXE,root)
    transaction=root/'.updates'/('apply-'+uuid.uuid4().hex+'.json')
    atomic_json(transaction,{'directory':str(directory),'directories':directories,'parent_pid':os.getpid(),'old_exe':sys.executable,'root':str(root)})
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    subprocess.Popen([str(directory/EXE),'--apply-update',str(transaction)],env=child_env(root),creationflags=flags)

def wait_parent(pid):
    import ctypes
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.restype=ctypes.c_void_p;k.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32];k.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=k.OpenProcess(0x100000,False,int(pid))
    if handle:
        try:
            # A slow close is bounded. Never terminate a user application.
            if k.WaitForSingleObject(handle,120000)!=0:raise ValueError('アプリ終了待ちがタイムアウトしました')
        finally:k.CloseHandle(handle)

def apply_transaction(path):
    t=json.loads(Path(path).read_text(encoding='utf-8'));root=Path(t['root']).resolve();directory=Path(t['directory']).resolve()
    if not directory.is_relative_to(root/'.updates'/'releases'):raise ValueError('更新保存先が不正です')
    wait_parent(t['parent_pid']);m=verify_staged(directory)
    backup=backup_data(t['directories'],root)
    ready=root/'.updates'/('ready-'+uuid.uuid4().hex)
    atomic_json(root/'.updates'/'journal.json',{'status':'starting','candidate':str(directory),'previous':t['old_exe'],'backup':str(backup)})
    env=child_env(root);env['FORGEDOCUMENTS_READY_FILE']=str(ready)
    child=subprocess.Popen([str(directory/EXE)],env=env)
    for _ in range(300):
        if ready.exists():
            atomic_json(root/'.updates'/'current.json',{'relative_exe':str((directory/EXE).relative_to(root)),'sequence':m['sequence']})
            atomic_json(root/'.updates'/'journal.json',{'status':'confirmed','candidate':str(directory),'backup':str(backup),'process_pid':child.pid})
            ready.unlink(missing_ok=True);Path(path).unlink(missing_ok=True);return
        if child.poll() is not None:break
        time.sleep(.1)
    if child.poll() is None:child.terminate();child.wait(timeout=10)
    atomic_json(root/'.updates'/'journal.json',{'status':'failed','candidate':str(directory),'previous':t['old_exe'],'backup':str(backup)})
    subprocess.Popen([t['old_exe']],env=child_env(root))
    raise ValueError('更新版の起動確認に失敗しました。以前の版へ戻しました')

def route_to_current():
    if not getattr(sys,'frozen',False) or os.environ.get('FORGEDOCUMENTS_SKIP_ROUTE')=='1':return False
    root=install_root();p=root/'.updates'/'current.json'
    if not p.exists():return False
    state=json.loads(p.read_text(encoding='utf-8'));target=(root/state['relative_exe']).resolve()
    if not target.is_relative_to(root/'.updates'/'releases'):raise ValueError('更新起動先が不正です')
    if target==Path(sys.executable).resolve():return False
    verify_staged(target.parent)
    subprocess.Popen([str(target),*sys.argv[1:]],env=child_env(root));return True
