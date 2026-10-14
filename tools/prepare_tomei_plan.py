"""Create private, importable settings from the explicitly corrected image."""
import argparse
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import load_template, atomic_json
from tomei_screen import DEFINITION, validate_policy
from tomei_profiles import image_profile, CROP
from blue_background import extract_background


def prepare(source, existing=None, reviewed=False):
    from PIL import Image
    with Image.open(source) as image:
        if image.size != (1070, 1470):
            raise ValueError('この座標は1070×1470の修正背景専用です')
    t = image_profile(load_template(existing or DEFINITION))
    config = extract_background(source, CROP, t['width_mm'], t['height_mm'], reviewed=reviewed)
    config['kind'] = 'corrected_blue'
    config['processing'].update(
        imagegen_corrected=True, original_library_file_id='libfile_bec939d82fa48191940458f8cd81af4e',
        original_sha256='f88706b0614698490c7e360105e50410b0e7879bdd1af90ca7b848030c39d32c',
        corrected_source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        original_pixel_fidelity=False,
        corrected_text=['470-0162', '愛知県愛知郡東郷町大字春木字南切山127番地', '配合の種別5選択肢'])
    config['unresolved_text_errors'] = [] if reviewed else ['修正画像の住所・5選択肢・罫線・空欄の確認が必要']
    t['background'] = config
    t['source_confirmation']['corrected_original_issues'] = t['source_confirmation'].pop('known_new_background_issues', [])
    t['source_confirmation']['known_new_background_issues'] = [] if reviewed else config['unresolved_text_errors']
    t['source_confirmation']['complete_blue_background_available'] = reviewed
    validate_policy(t)
    return t


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--existing', type=Path, help='既存設定JSONの候補・既定値を保持')
    parser.add_argument('--reviewed', action='store_true', help='修正画像を目視確認した場合だけ指定')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('既存設定を上書きしません。別の出力先を指定してください')
    atomic_json(args.output, prepare(args.source, args.existing, args.reviewed))
    print(args.output)
