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
    if not stored:raise RuntimeError('既存の署名鍵がWindows資格情報ストアにありません。新規鍵は作成しません。正規の署名環境で実行してください')
    key=Ed25519PrivateKey.from_private_bytes(base64.b64decode(stored,validate=True))
    public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode('ascii')
    return key,key_id,public

def prepare_key():
    key,key_id,public=signing_key()
    cfg=json.loads((ROOT/'update_config.json').read_text(encoding='utf-8'))
    if cfg['key_id']!=key_id or cfg['public_key']!=public:raise RuntimeError('既存署名鍵とアプリの公開鍵が一致しません。公開鍵は変更しません')
    return key,cfg


def public_asset_args():
    from tomei_preset import public_bundle_files
    args=[]
    for source in public_bundle_files():args+=['--add-data',str(source)+':assets']
    return args

def build(output,unsigned=False,private_background=None):
    if sys.platform!='win32':raise RuntimeError('Windows EXEはWindows環境でビルド・診断してください。Linux製の実行ファイルは配布しません')
    if unsigned:key=None;cfg=json.loads((ROOT/'update_config.json').read_text(encoding='utf-8'))
    else:key,cfg=prepare_key()
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    v=json.loads((ROOT/'version.json').read_text(encoding='utf-8'))
    dest=output/f"Forgedocuments_GR-{v['version']}-windows-x64";dest.mkdir(exist_ok=False)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--name','Forgedocuments GR','--distpath',str(dest),'--workpath',str(output/'build'),'--specpath',str(output/'spec')]
    args+=public_asset_args()
    if private_background:
        from tomei_preset import recognize
        source=Path(private_background).resolve()
        if recognize(source)!='corrected':raise ValueError('同梱は確認済み修正背景だけに対応します')
        if source.name!='tomei-corrected-background.png':raise ValueError('私有背景の同梱名はtomei-corrected-background.pngです')
        args+=['--add-data',str(source)+':private-assets']
    for name in ['template.json','forms.json','version.json','update_config.json']:args+=['--add-data',str(ROOT/name)+':.']
    from form_registry import catalog
    for row in catalog():
        args+=['--hidden-import',row['module']]
        definition=row.get('template')
        if definition and definition!='template.json':
            args+=['--add-data',str(ROOT/definition)+':'+str(Path(definition).parent)]
            metadata=json.loads((ROOT/definition).read_text(encoding='utf-8'))
            if metadata.get('coordinate_definition'):
                coordinate_path=(ROOT/definition).parent/metadata['coordinate_definition']
                if not coordinate_path.resolve().is_relative_to((ROOT/definition).parent.resolve()):raise ValueError('座標定義が帳票フォルダーを超えています')
                args+=['--add-data',str(coordinate_path)+':'+str(Path(definition).parent)]
            for profile in metadata.get('coordinate_profiles',[]):
                profile_path=(ROOT/definition).parent/profile
                if not profile_path.resolve().is_relative_to((ROOT/definition).parent.resolve()):raise ValueError('座標プロファイルが帳票フォルダーを超えています')
                args+=['--add-data',str(profile_path)+':'+str(Path(definition).parent)]
    args+=['--hidden-import','reportlab.pdfbase._fontdata_enc_winansi','--hidden-import','reportlab.pdfbase._fontdata_enc_macroman',str(ROOT/'app.py')]
    subprocess.run(args,cwd=ROOT,check=True)
    for name in ['template.json','forms.json','version.json','update_config.json']:(dest/name).write_bytes((ROOT/name).read_bytes())
    (dest/'README.txt').write_text('Forgedocuments GR\n\n「Forgedocuments GR.exe」を開き、エーシー帳票を選択してください。\nPythonやbatの操作は不要です。\n右ドラッグでプレビュー移動、Ctrl＋ホイールで拡大・縮小。\n会社別のtemplate.jsonはエーシー帳票の帳票設定から取り込んでください。\n入力データは選択した保存先に置かれ、更新で上書きされません。\nアプリの更新からGR Release Hubの更新を取得できます。\n実機プリンターでの印刷は未検証。外周枠寸法は暫定値です。\n',encoding='utf-8-sig')
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}
    (dest/'release_files.json').write_text(json.dumps(files,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    archive=output/f"Forgedocuments_GR-{v['version']}-windows-x64.zip"
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(dest.iterdir()):z.write(p,p.name)
    notes_path=ROOT/'docs'/f"RELEASE_NOTES_{v['version']}.txt"
    notes=notes_path.read_text(encoding='utf-8').strip() if notes_path.exists() else '帳票アプリの更新。既存の記録と独自設定を保持。'
    manifest={'schema_version':1,'app_id':cfg['app_id'],'version':v['version'],'sequence':v['sequence'],'minimum_updater_version':'1.0.0','published_at':datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),'release_notes':notes,'download_url':cfg['hub_url']+f"/api/apps/{cfg['app_id']}/releases/{v['sequence']}/download",'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'key_id':cfg['key_id']}
    from updates import canonical
    if key is not None:manifest['signature']=base64.b64encode(key.sign(canonical(manifest))).decode('ascii')
    (output/('manifest.unsigned.json' if unsigned else 'manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps({'archive':str(archive),'exe':str(dest/'Forgedocuments GR.exe'),'sha256':manifest['sha256'],'size':archive.stat().st_size,'signed':not unsigned},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-key',action='store_true',help='既存鍵と公開鍵の一致を確認（鍵の新規作成はしない）');parser.add_argument('--unsigned',action='store_true',help='Windowsビルドのみ。署名鍵を扱わず、公開不可の未署名候補を作成');parser.add_argument('--output',default=str(ROOT.parent/'release'))
    parser.add_argument('--private-background',type=Path,help='本人用の非公開ビルドだけに修正背景を同梱。公開資産へアップロードしない')
    a=parser.parse_args()
    if a.prepare_key:prepare_key();print('Existing signing key matches the unchanged public key')
    else:build(a.output,unsigned=a.unsigned,private_background=a.private_background)
