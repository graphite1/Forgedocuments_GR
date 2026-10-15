"""Only reviewed blank derivatives enter public source and Windows packages."""
import hashlib,json
from pathlib import Path

ASSETS=('a4_blank.png','digits.png','layout.json','manifest.json')


def bundle_files():
    root=Path(__file__).resolve().parent/'assets'
    paths=[root/name for name in ASSETS]
    if not all(p.is_file() for p in paths):raise ValueError('AKTIOの印字素材が不足しています')
    manifest=json.loads(paths[-1].read_text(encoding='utf-8'))
    if manifest.get('original_pdf_included') is not False or manifest.get('transaction_data_included') is not False:
        raise ValueError('AKTIO同梱素材の用途を確認できません')
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=manifest['files'].get(p.name) for p in paths[:-1]):
        raise ValueError('AKTIO印字素材のハッシュが一致しません')
    return paths
