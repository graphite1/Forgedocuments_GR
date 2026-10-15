"""Reviewed plan assets: approved public bundle and legacy private imports."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from blue_background import extract_background
from tomei_profiles import image_profile, CROP

CORRECTED_SHA256='a6bee70ebe7ca443b1b6e98b710b4df13c15098dbd1fc67ad69c4fb32127dafb'
ORIGINAL_SHA256='f88706b0614698490c7e360105e50410b0e7879bdd1af90ca7b848030c39d32c'
ORIGINAL_ISSUES=['郵便番号470-0163（正470-0162）','住所末尾127番地・配合種別5選択肢の訂正が必要']
PUBLIC_SHA256='e036d4f785c27270612c3242532e9ba31131465a14c8e54a5ac33709fea14f68'
PUBLIC_ASSETS=Path(__file__).resolve().parent/'assets'


def recognize(source):
    path=Path(source)
    if path.stat().st_size>20*1024*1024:return None
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest==PUBLIC_SHA256:return 'public_plan'
    if digest==CORRECTED_SHA256:return 'corrected'
    if digest==ORIGINAL_SHA256:return 'original_with_typos'
    return None


def public_bundle_files():
    """Validate the reviewed bitmap and its explicit public settings together."""
    config_path=PUBLIC_ASSETS/'tomei-plan-background.json'
    image_path=PUBLIC_ASSETS/'tomei-plan-background.png'
    if not config_path.is_file() or not image_path.is_file():
        raise ValueError('同梱の計画用背景と設定が不足しています。配布ZIPをすべて展開してください')
    config=json.loads(config_path.read_text(encoding='utf-8'))
    from tomei_profiles import PROFILE,COORDINATES
    expected={'schema_version':1,'image':image_path.name,'image_sha256':PUBLIC_SHA256,
              'public_distribution_approved':True,'document_purpose':'delivery_plan',
              'required_notice':'納入書（計画）','notice_in_image':True,
              'transaction_values_included':False,'handwriting_or_signatures_included':False,
              'layout_profile':PROFILE,'crop_pixels_after_rotation':CROP,
              'width_mm':118.3,'height_mm':1417*118.3/1018,
              'coordinate_width':1018,'coordinate_height':1417,
              'coordinate_definition':COORDINATES}
    if any(config.get(k)!=v for k,v in expected.items()) or recognize(image_path)!='public_plan':
        raise ValueError('同梱の計画用背景と専用設定の照合に失敗しました')
    return [config_path,image_path]


def bundled_source():
    if PUBLIC_ASSETS.is_dir():
        return public_bundle_files()[1]
    path=Path(__file__).resolve().parent/'private-assets'/'tomei-corrected-background.png'
    return path if path.is_file() and recognize(path)=='corrected' else None


def apply_preset(template,source,*,reviewed=False,errors=None):
    """Apply profile after explicit image selection or reviewed bundle loading."""
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
            original_sha256=ORIGINAL_SHA256,corrected_source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            original_pixel_fidelity=False,
            corrected_text=['470-0162','愛知県愛知郡東郷町大字春木字南切山127番地','配合の種別5選択肢'])
        if kind=='public_plan':
            config['processing'].update(public_distribution_approved=True,plan_notice_in_image=True,
                in_frame_notice_masked=True,recipient_honorific_masked=True,
                public_source_sha256=PUBLIC_SHA256,public_settings='assets/tomei-plan-background.json')
    config['unresolved_text_errors']=unresolved
    t['background']=config
    t['source_confirmation']['known_new_background_issues']=unresolved
    t['source_confirmation']['complete_blue_background_available']=reviewed and not unresolved
    return t


def with_bundled_preset(template):
    source=bundled_source()
    return apply_preset(template,source,reviewed=True) if source else template
