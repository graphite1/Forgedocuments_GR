"""Create private, importable settings from the explicitly corrected image."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import load_template, atomic_json
from tomei_screen import DEFINITION, validate_policy
from tomei_preset import apply_preset


def prepare(source, existing=None, reviewed=False):
    errors=[] if reviewed else ['修正画像の住所・5選択肢・罫線・空欄の確認が必要']
    t = apply_preset(load_template(existing or DEFINITION),source,reviewed=reviewed,errors=errors)
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
