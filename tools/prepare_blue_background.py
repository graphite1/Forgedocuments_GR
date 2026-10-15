"""Prepare an unreviewed blue asset from one explicitly selected local original."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from blue_background import extract_background


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('--crop',nargs=4,type=int,required=True,metavar=('LEFT','TOP','RIGHT','BOTTOM'),help='傾き補正後の外枠のピクセル座標')
    parser.add_argument('--angle',type=float,default=0,help='確認した傾き補正角度。自動適用しない')
    parser.add_argument('--pdf-page',type=int,default=0,help='0から数えるPDFページ')
    parser.add_argument('--width-mm',type=float,required=True)
    parser.add_argument('--height-mm',type=float,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError('既存の背景設定を上書きしません')
    config=extract_background(args.source,args.crop,args.width_mm,args.height_mm,deskew_degrees=args.angle,pdf_page=args.pdf_page)
    with args.output.open('x',encoding='utf-8') as file:json.dump(config,file,ensure_ascii=False,indent=2);file.write('\n')
    print('青印字背景候補を保存しました。未確認のため帳票出力には使用できません。元資料の欠け・手書き・切り出しを確認してください。')
