"""Build exe and GRHub signed ZIP. Private key stays in Windows Credential Vault."""
import argparse,base64,hashlib,json,subprocess,sys,zipfile
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def signing_key():
    from keyring.backends.Windows import WinVaultKeyring
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    vault=WinVaultKeyring();service='Forgedocuments_GR/release-signing';key_id='forgedocuments-gr-2026-01'
    stored=vault.get_password(service,key_id)
    if stored:key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(stored,validate=True))
    else:
        key=Ed25519PrivateKey.generate();raw=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
        vault.set_password(service,key_id,base64.b64encode(raw).decode('ascii'))
    public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode('ascii')
    return key,key_id,public

def prepare_key():
    key,key_id,public=signing_key()
    cfg={'app_id':'forgedocuments-gr','hub_url':'https://gr-release-hub.rinntyu2000.chatgpt.site','key_id':key_id,'public_key':public}
    (ROOT/'update_config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    return key,cfg

def build(output):
    key,cfg=prepare_key();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    v=json.loads((ROOT/'version.json').read_text(encoding='utf-8'))
    dest=output/f"Forgedocuments_GR-{v['version']}-windows-x64";dest.mkdir(exist_ok=False)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','Forgedocuments GR','--distpath',str(dest),'--workpath',str(output/'build'),'--specpath',str(output/'spec')]
    for name in ['template.json','forms.json','version.json','update_config.json']:args+=['--add-data',str(ROOT/name)+':.']
    args+=['--hidden-import','ac_screen','--hidden-import','reportlab.pdfbase._fontdata_enc_winansi','--hidden-import','reportlab.pdfbase._fontdata_enc_macroman',str(ROOT/'app.py')]
    subprocess.run(args,cwd=ROOT,check=True)
    for name in ['template.json','forms.json','version.json','update_config.json']:(dest/name).write_bytes((ROOT/name).read_bytes())
    (dest/'README.txt').write_text('Forgedocuments GR\n\n「Forgedocuments GR.exe」を開き、エーシー帳票を選択してください。\nPythonやbatの操作は不要です。\n右ドラッグでプレビュー移動、Ctrl＋ホイールで拡大・縮小。\n会社別のtemplate.jsonはエーシー帳票の帳票設定から取り込んでください。\n入力データは選択した保存先に置かれ、更新で上書きされません。\nアプリの更新からGR Release Hubの更新を取得できます。\n実機プリンターでの印刷は未検証。外周枠寸法は暫定値です。\n',encoding='utf-8-sig')
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}
    (dest/'release_files.json').write_text(json.dumps(files,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    archive=output/f"Forgedocuments_GR-{v['version']}-windows-x64.zip"
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(dest.iterdir()):z.write(p,p.name)
    manifest={'schema_version':1,'app_id':cfg['app_id'],'version':v['version'],'sequence':v['sequence'],'minimum_updater_version':'1.0.0','published_at':datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),'release_notes':'帳票選択画面にエーシー帳票を搭載。Python不要のexe起動、GRHubからの署名付きアプリ内更新、右ドラッグとCtrl＋ホイールによる共通PDFプレビュー。既存の伝票と会社別設定を保持。今後はアップデートで帳票画面を追加。','download_url':cfg['hub_url']+f"/api/apps/{cfg['app_id']}/releases/{v['sequence']}/download",'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'key_id':cfg['key_id']}
    from updates import canonical
    manifest['signature']=base64.b64encode(key.sign(canonical(manifest))).decode('ascii')
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps({'archive':str(archive),'exe':str(dest/'Forgedocuments GR.exe'),'sha256':manifest['sha256'],'size':archive.stat().st_size},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-key',action='store_true');parser.add_argument('--output',default=str(ROOT.parent/'release'))
    a=parser.parse_args()
    if a.prepare_key:prepare_key();print('Public key prepared; signing key is in Windows Credential Vault')
    else:build(a.output)
