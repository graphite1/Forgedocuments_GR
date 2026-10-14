"""Recognize reviewed private assets without placing company images in Git."""
import hashlib
from pathlib import Path
from PIL import Image
from blue_background import extract_background
from tomei_profiles import image_profile, CROP

CORRECTED_SHA256='a6bee70ebe7ca443b1b6e98b710b4df13c15098dbd1fc67ad69c4fb32127dafb'
ORIGINAL_SHA256='f88706b0614698490c7e360105e50410b0e7879bdd1af90ca7b848030c39d32c'
ORIGINAL_ISSUES=['郵便番号470-0163（正470-0162）','住所末尾127番地・配合種別5選択肢の訂正が必要']


def recognize(source):
    path=Path(source)
    if path.stat().st_size>20*1024*1024:return None
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest==CORRECTED_SHA256:return 'corrected'
    if digest==ORIGINAL_SHA256:return 'original_with_typos'
    return None


def bundled_source():
    path=Path(__file__).resolve().parent/'private-assets'/'tomei-corrected-background.png'
    return path if path.is_file() and recognize(path)=='corrected' else None


def apply_preset(template,source,*,reviewed=False,errors=None):
    """Apply profile only after explicit image selection or private bundle use."""
    kind=recognize(source)
    if kind is None:raise ValueError('このプリセットは確認済み修正画像と元画像だけに対応します')
    with Image.open(source) as image:
        if image.size!=(1070,1470):raise ValueError('画像プリセットの寸法が一致しません')
    t=image_profile(template)
    config=extract_background(source,CROP,t['width_mm'],t['height_mm'],reviewed=reviewed)
    unresolved=list(errors or [])
    if kind=='original_with_typos':
        unresolved=list(dict.fromkeys(ORIGINAL_ISSUES+unresolved))
    else:
        config['kind']='corrected_blue'
        config['processing'].update(imagegen_corrected=True,
            original_library_file_id='libfile_bec939d82fa48191940458f8cd81af4e',
            original_sha256=ORIGINAL_SHA256,corrected_source_sha256=CORRECTED_SHA256,
            original_pixel_fidelity=False,
            corrected_text=['470-0162','愛知県愛知郡東郷町大字春木字南切山127番地','配合の種別5選択肢'])
    config['unresolved_text_errors']=unresolved
    t['background']=config
    t['source_confirmation']['known_new_background_issues']=unresolved
    t['source_confirmation']['complete_blue_background_available']=reviewed and not unresolved
    return t


def with_bundled_preset(template):
    source=bundled_source()
    return apply_preset(template,source,reviewed=True) if source else template
