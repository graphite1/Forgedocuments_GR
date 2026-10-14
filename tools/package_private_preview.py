"""Create a LOCAL-ONLY source preview with the reviewed private background."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from tomei_preset import recognize


def package(source_archive,background,output):
    if output.exists():raise FileExistsError(output)
    if recognize(background)!='corrected':raise ValueError('確認済み修正背景だけを同梱できます')
    with zipfile.ZipFile(source_archive) as src:
        if src.testzip() is not None:raise ValueError('ソースZIPが壊れています')
        entries=src.infolist()
        if any(not i.filename.startswith('Forgedocuments_GR/') or '..' in Path(i.filename).parts for i in entries):
            raise ValueError('指定されたソースZIPの構成が不正です')
        version=json.loads(src.read('Forgedocuments_GR/version.json'))
        commit=src.comment.decode('ascii')
        if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('ソースの対象コミットを確認できません')
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as dest:
            dest.comment=src.comment
            for entry in entries:dest.writestr(entry,src.read(entry.filename))
            dest.write(background,'Forgedocuments_GR/private-assets/tomei-corrected-background.png')
            dest.writestr('Forgedocuments_GR/PRIVATE-PREVIEW.txt',
                '本人の非公開試用専用。会社帳票の私有画像を含むため公開Git/Releaseへアップロードしないでください。\n'
                'ソース版です。Windows EXEは含みません。Python環境が別途必要です。\n'
                '生コンの新しい保存先では修正背景と専用位置を自動適用します。既存設定は保持します。\n'
                '既存保存先では帳票設定の「同梱の修正背景を選択」から明示的に適用できます。\n'
                'AC住所は固定・均等字間・変位対象外。ただし原本PDFのクラウド転送が未完で座標重ね合わせは未確認です。\n')
    metadata={'artifact_type':'private_source_preview','private_company_image_included':True,
              'public_release_asset':False,'source_commit':commit,'version':version['version'],
              'windows_exe_built':False,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix('.manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    return metadata


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source_archive',type=Path);p.add_argument('background',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(package(a.source_archive,a.background,a.output),ensure_ascii=False,indent=2))
