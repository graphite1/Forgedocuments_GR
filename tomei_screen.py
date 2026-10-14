"""Concrete form policy and registration; source-specific data stays here."""
from pathlib import Path
from core import load_template,validate_template
from definition_screen import DefinitionScreen

FORM_ID='tomei_taiheiyo'
DEFINITION=Path(__file__).resolve().parent/'templates/tomei_taiheiyo.json'
EXCLUDED=('arrival_time','recipient_sign_status','shipping_staff_status')
FIXED=('issuer','source_certification_text')


def overlaps(a,b):
    x,y,w,h=a;bx,by,bw,bh=b
    return min(x+w,bx+bw)-max(x,bx)>1e-7 and min(y+h,by+bh)-max(y,by)>1e-7


def validate_blank_regions(t,default):
    fields={f['id']:f for f in default['fields']};regions=[fields[key]['box'] for key in EXCLUDED]
    heading_ids={'recipient_sign_heading':'荷受職員の署名又は記名','shipping_sign_heading':'出荷係の署名又は記名'}
    for key,label in heading_ids.items():
        items=[i for i in t['fixed_texts'] if i.get('id')==key]
        expected=next(i for i in default['fixed_texts'] if i.get('id')==key)
        if len(items)!=1 or items[0].get('text')!=label or not items[0].get('print',True) or 'value_key' in items[0] or items[0]['box']!=expected['box']:
            raise ValueError('署名欄の固定見出しと位置を保持してください')
    for f in t['fields']:
        if f['type']=='layout_only' or not f.get('print',True):continue
        boxes=[f['box']]+f.get('parts',[])+list(f.get('choice_marks',{}).values())
        boxes += [box for o in f.get('options',[]) for box in (o['box'],o['label_box'])]
        if any(overlaps(box,region) for box in boxes for region in regions):raise ValueError('着時刻・署名の空欄へ印字項目を配置できません')
    for item in t['fixed_texts']:
        if item.get('id') in heading_ids or not item.get('print',True):continue
        if any(overlaps(item['box'],region) for region in regions):raise ValueError('着時刻・署名の空欄へ固定文を追加できません')
    for line in t['lines']:
        x0,y0,x1,y1=line['points']
        for x,y,w,h in regions:
            if abs(y1-y0)<1e-7:
                enters=y+1e-7<y0<y+h-1e-7 and min(max(x0,x1),x+w)-max(min(x0,x1),x)>1e-7
            elif abs(x1-x0)<1e-7:
                enters=x+1e-7<x0<x+w-1e-7 and min(max(y0,y1),y+h)-max(min(y0,y1),y)>1e-7
            else:enters=overlaps([min(x0,x1),min(y0,y1),abs(x1-x0),abs(y1-y0)],[x,y,w,h])
            if enters:raise ValueError('着時刻・署名の空欄へ罫線以外の線を追加できません')


def validate_policy(t):
    default=load_template(DEFINITION)
    if t.get('form_id')!=FORM_ID:raise ValueError('別帳票の設定です')
    expected={f['id']:f for f in default['fields']};fields={f['id']:f for f in t['fields']}
    if set(fields)!=set(expected) or len(t['fields'])!=42:raise ValueError('生コンの42項目定義を保持してください')
    for key,f in fields.items():
        if f['type']!=expected[key]['type'] or f.get('input',True)!=expected[key].get('input',True):raise ValueError('項目の型・入力可否は変更できません')
    for key in EXCLUDED:
        f=fields[key]
        if f.get('print') or f.get('default') or f.get('fixed_value'):raise ValueError('着時刻・署名欄は空白で保持してください')
    for key in FIXED:
        if not fields[key].get('print',True):raise ValueError('発行元・原票認証文字列の固定表示を保持してください')
        if fields[key].get('color',t['line_color'])!=t['line_color']:raise ValueError('発行元・原票認証文字列は青い固定設定です')
    if fields['source_certification_text'].get('fixed_value')!='GB0407016':raise ValueError('原票記載文字列 GB0407016 を保持してください')
    notices=[i for i in t['fixed_texts'] if i.get('id')=='copy_notice']
    expected_notice=next(i for i in default['fixed_texts'] if i.get('id')=='copy_notice')
    if len(notices)!=1 or notices[0]!=expected_notice:raise ValueError('転記・再出力の識別表示と読み取れる色・大きさ・位置を保持してください')
    if t.get('input_color')!=[0,0,0]:raise ValueError('入力値は黒で出力してください')
    blue=t['line_color']
    if len(blue)!=3 or not 0<=min(blue)<=max(blue)<=1 or not blue[2]>max(blue[:2]):raise ValueError('固定罫線と固定文字は青で出力してください')
    for f in fields.values():
        if f.get('input',True) and f.get('color',t['input_color'])!=[0,0,0]:raise ValueError('入力項目の色は黒で保持してください')
    for item in t['fixed_texts']:
        if item.get('id')!='copy_notice' and item.get('color',blue)!=blue:raise ValueError('原票の固定文字は青で保持してください')
    title=next((i for i in t['fixed_texts'] if i.get('id')=='original_title'),None)
    if not title or not title.get('print',True) or title.get('value_key')!='original_title' or t.get('original_title')!=default['original_title']:raise ValueError('確認された原票表題を保持してください')
    if t.get('summary_config')!=default['summary_config']:raise ValueError('実績数量は納入容積をm³で集計してください')
    validate_blank_regions(t,default)
    validate_template(t)


class App(DefinitionScreen):
    def __init__(self,root,directory):
        t=load_template(DEFINITION);validate_policy(t)
        super().__init__(root,directory,t,validate_policy)
