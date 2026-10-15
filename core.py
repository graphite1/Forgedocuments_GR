"""Form-specific metadata is in template.json; persistence and rendering are generic."""
from __future__ import annotations
import base64, copy, csv, hashlib, io, json, math, os, re, sqlite3, uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from itertools import count
from page_layout import placements
from input_definitions import default_values,validate_definitions

BASE = Path(__file__).resolve().parent
MM = 72 / 25.4

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def load_template(path=None):
    path=Path(path or BASE/'template.json')
    template=json.loads(path.read_text(encoding='utf-8-sig'))
    definition=template.pop('coordinate_definition',None)
    if definition:
        from input_coordinates import apply_coordinates
        coordinate_path=(path.parent/definition).resolve()
        if not coordinate_path.is_relative_to(path.parent.resolve()):raise ValueError('座標定義は帳票定義のフォルダー内で指定してください')
        template=apply_coordinates(template,json.loads(coordinate_path.read_text(encoding='utf-8-sig')))
        template['coordinate_source']=definition
    return template

def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def blank(template):
    return default_values(template)

def dec(value):
    if value=='-':raise ValueError('「-」は未記載の記号です。計算には数値を入力してください')
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError('有限の数値を入力してください')
    return d

def validate(values, template):
    errors = []
    for f in template['fields']:
        value = values.get(f['id'], '')
        if f['type']=='layout_only' or f.get('input',True) is False:
            if value not in ('',None):errors.append(f"{f['label']}: 入力・転記できない欄です")
            continue
        if not isinstance(value, str):
            errors.append(f"{f['label']}: 文字列として保存してください")
            continue
        if not value:
            if f.get('required'): errors.append(f"{f['label']}: 未入力です")
            continue
        if value=='-' and f['type'] in ('text','date','time','decimal','integer','choice'):
            if f.get('numeric_required_for_calculation'):
                errors.append(f"{f['label']}: 計算に必要な数値を入力してください（-は未記載）")
            continue
        try:
            typ = f['type']
            if typ == 'date':
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): raise ValueError('YYYY-MM-DDで入力')
                datetime.strptime(value,'%Y-%m-%d')
            elif typ == 'time':
                if not re.fullmatch(r'\d{2}:\d{2}',value): raise ValueError('HH:MMで入力')
                datetime.strptime(value,'%H:%M')
            elif typ in ('decimal','integer'):
                if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',value): raise ValueError('数値で入力')
                d=dec(value)
                if typ=='integer' and d!=d.to_integral_value(): raise ValueError('整数で入力')
                if f.get('min') is not None and d<dec(f['min']): raise ValueError(f"下限 {f['min']} 未満")
                if f.get('max') is not None and d>dec(f['max']): raise ValueError(f"上限 {f['max']} 超過")
                if f.get('decimals') is not None and max(0,-d.as_tuple().exponent)>f['decimals']:
                    raise ValueError(f"小数 {f['decimals']} 桁以内で入力")
            elif typ=='choice' and value not in f['choices']: raise ValueError('選択肢にない値')
            elif typ=='multi_choice':
                selected=json.loads(value)
                allowed={o['key'] for o in f['options']}
                if not isinstance(selected,list) or not all(isinstance(k,str) and k in allowed for k in selected) or len(selected)!=len(set(selected)):
                    raise ValueError('選択肢にない値または重複した選択です')
            elif typ=='image':
                from PIL import Image
                Image.open(io.BytesIO(base64.b64decode(value,validate=True))).verify()
            if f.get('max_length') is not None and len(value)>f['max_length']: raise ValueError(f"{f['max_length']} 文字以内で入力")
            if '\x00' in value: raise ValueError('使用できない制御文字')
        except (ValueError, InvalidOperation, OverflowError, OSError) as e:
            errors.append(f"{f['label']}: {e}")
    return errors

def validate_template(t):
    if t.get('schema_version')!=1: raise ValueError('未対応の帳票設定バージョン')
    w,h=float(t['width_mm']),float(t['height_mm'])
    if not (10<=w<=1000 and 10<=h<=1000): raise ValueError('寸法は10〜1000mmで設定')
    if t['page_mode'] not in ('A4','original'): raise ValueError('出力モードが不正')
    if 'page_layout' not in t and t['page_mode']=='A4' and (w>210 or h>297): raise ValueError('A4縦の枠内に実寸で収まりません')
    ids=[f['id'] for f in t['fields']]
    if len(ids)!=len(set(ids)): raise ValueError('項目IDが重複しています')
    validate_definitions(t['fields'],validate)
    if t.get('render_mode','vector') not in ('vector','background'):raise ValueError('帳票の合成方式が不正です')
    if t.get('render_mode')=='background':
        from background_assets import validate_background
        validate_background(t)
    coord_w,coord_h=float(t.get('coordinate_width',1000)),float(t.get('coordinate_height',1300))
    if not all(math.isfinite(v) and 10<=v<=10000 for v in (coord_w,coord_h)):raise ValueError('帳票座標の範囲が不正です')
    max_y=coord_h*float(t.get('content_height_mm',h))/h
    for f in t['fields']:
        if f.get('font',28)<=0: raise ValueError('文字サイズは正数で設定')
        option_boxes=[box for option in f.get('options',[]) for box in (option['box'],option['label_box'])]
        for box in [f['box']]+f.get('parts',[])+list(f.get('choice_marks',{}).values())+([f['mark_bounds']] if 'mark_bounds' in f else [])+option_boxes:
            x,y,bw,bh=map(float,box)
            if not all(math.isfinite(v) for v in (x,y,bw,bh)) or x<0 or y<0 or bw<=0 or bh<=0 or x+bw>coord_w+1e-7 or y+bh>max_y+1e-7: raise ValueError(f"{f['label']}: 印字領域が出力範囲を超えています")
        if f['type']=='multi_choice':
            keys=[o['key'] for o in f['options']]
            if len(keys)!=len(set(keys)):raise ValueError('選択肢IDが重複しています')
        if f.get('min') is not None and f.get('max') is not None and dec(f['min'])>dec(f['max']): raise ValueError(f"{f['label']}: 下限が上限を超えています")
    for item in t['fixed_texts']:
        x,y,bw,bh=map(float,item['box'])
        if not all(math.isfinite(v) for v in (x,y,bw,bh)) or x<0 or y<0 or bw<=0 or bh<=0 or x+bw>coord_w+1e-7 or y+bh>max_y+1e-7: raise ValueError('固定文の印字領域が出力範囲を超えています')
    if float(t.get('original_margin_mm',0.5))<0: raise ValueError('外側余白は0以上で設定')
    if type(t.get('random_print_enabled',False)) is not bool:raise ValueError('ランダム印字はON/OFFで指定')
    for key in ('random_print_x_mm','random_print_y_mm'):
        value=t.get(key,0.3)
        if isinstance(value,bool) or not math.isfinite(float(value)) or not 0<=float(value)<=2:
            raise ValueError('ランダム印字のずれ幅は0〜2mmで設定')
    for key,lower,upper,default in (('input_density',.35,1,1),('input_transparency',0,1,0),('input_width_scale',.8,1.2,1),
                                  ('input_tracking_em',0,.2,0),('input_weight_em',0,.06,.018)):
        value=t.get(key,default)
        if isinstance(value,bool) or not math.isfinite(float(value)) or not lower<=float(value)<=upper:
            raise ValueError(f'入力文字の{key}は{lower:g}〜{upper:g}で指定してください')
    from blue_ink import density as validate_blue_density
    validate_blue_density(t)
    placements(t)
    return t

class Store:
    def __init__(self, directory, default_template=None, form_id=None, validate_definition=None, migrate_definition=None):
        self.default_template=default_template
        self.form_id=form_id
        self.validate_definition=validate_definition
        self.migrate_definition=migrate_definition
        if form_id and default_template is None:
            raise ValueError('帳票専用の既定設定を指定してください')
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.directory/'records.sqlite3',timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, data TEXT NOT NULL, revision INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS history(seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, at TEXT NOT NULL, reason TEXT NOT NULL, before_json TEXT, after_json TEXT);
        CREATE TABLE IF NOT EXISTS exports(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, format TEXT, path TEXT, snapshot TEXT NOT NULL, template TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL);
        ''')
        self.db.commit()

    def close(self): self.db.close()

    def defaults(self):
        return copy.deepcopy(self.default_template) if isinstance(self.default_template,dict) else load_template(self.default_template)

    def check_form(self,t):
        if self.form_id and t.get('form_id',self.form_id)!=self.form_id:
            raise ValueError('別の帳票の保存先・設定は使用できません')
        if self.form_id and 'form_id' not in t:
            expected={f['id'] for f in self.defaults()['fields']};actual={f['id'] for f in t['fields']}
            if not expected<=actual:raise ValueError('この保存先の項目は選択した帳票に対応していません')
        if self.validate_definition:self.validate_definition(t)
        return t

    def list(self, archived=False):
        return [dict(id=r[0],data=json.loads(r[1]),revision=r[2],created=r[3],updated=r[4],archived=bool(r[5])) for r in self.db.execute('SELECT id,data,revision,created,updated,archived FROM records WHERE archived=? ORDER BY rowid',(int(archived),))]

    def get(self,rid):
        r=self.db.execute('SELECT data,revision,created,updated,archived FROM records WHERE id=?',(rid,)).fetchone()
        if r is None: raise ValueError('記録が見つかりません')
        return dict(id=rid,data=json.loads(r[0]),revision=r[1],created=r[2],updated=r[3],archived=bool(r[4]))

    def save(self,data,template,rid=None,revision=None,reason='新規登録'):
        self.check_form(template)
        errors=validate(data,template)
        if errors: raise ValueError('\n'.join(errors))
        rid=rid or uuid.uuid4().hex
        payload=json.dumps(data,ensure_ascii=False)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT data,revision FROM records WHERE id=?',(rid,)).fetchone()
            if old:
                if revision!=old[1]: raise ValueError('別の画面で更新されています。一覧から再読込してください')
                if not reason.strip(): raise ValueError('訂正理由を入力してください')
                self.db.execute('UPDATE records SET data=?,revision=revision+1,updated=? WHERE id=?',(payload,now(),rid))
            else:
                if revision is not None: raise ValueError('記録が見つかりません')
                self.db.execute('INSERT INTO records VALUES(?,?,1,?,?,0)',(rid,payload,now(),now()))
            self.db.execute('INSERT INTO history(record_id,at,reason,before_json,after_json) VALUES(?,?,?,?,?)',(rid,now(),reason,old[0] if old else None,payload))
        return self.get(rid)

    def archive(self,rid,archive=True):
        with self.db:
            old=self.get(rid)
            self.db.execute('UPDATE records SET archived=?,revision=revision+1,updated=? WHERE id=?',(int(archive),now(),rid))
            self.db.execute('INSERT INTO history(record_id,at,reason,before_json,after_json) VALUES(?,?,?,?,?)',(rid,now(),'保管' if archive else '復帰',json.dumps(old,ensure_ascii=False),json.dumps(self.get(rid),ensure_ascii=False)))

    def import_rows(self,rows,template,reason):
        self.check_form(template)
        for data in rows:
            errors=validate(data,template)
            if errors:raise ValueError('\n'.join(errors))
        ids=[]
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for data in rows:
                rid=uuid.uuid4().hex;ids.append(rid);payload=json.dumps(data,ensure_ascii=False);at=now()
                self.db.execute('INSERT INTO records VALUES(?,?,1,?,?,0)',(rid,payload,at,at))
                self.db.execute('INSERT INTO history(record_id,at,reason,before_json,after_json) VALUES(?,?,?,?,?)',(rid,at,reason,None,payload))
        return [self.get(rid) for rid in ids]

    def history(self,rid):
        return self.db.execute('SELECT at,reason,before_json,after_json FROM history WHERE record_id=? ORDER BY seq DESC',(rid,)).fetchall()

    def export_log(self,fmt,path,records,template):
        with self.db:
            self.db.execute('INSERT INTO exports(at,format,path,snapshot,template) VALUES(?,?,?,?,?)',(now(),fmt,str(path),json.dumps(records,ensure_ascii=False),json.dumps(template,ensure_ascii=False)))

    def set_template(self,t):
        self.check_form(t);validate_template(t)
        path=self.directory/'template.json'
        old=path.read_text(encoding='utf-8') if path.exists() else None
        # JSON lives in SQLite as the authoritative settings history, file is a portable copy.
        with self.db:
            self.db.execute('INSERT INTO settings(at,before_json,after_json) VALUES(?,?,?)',(now(),old,json.dumps(t,ensure_ascii=False)))
        atomic_json(path,t)

    def template(self):
        row=self.db.execute('SELECT after_json FROM settings ORDER BY seq DESC LIMIT 1').fetchone()
        if row:
            stored=json.loads(row[0])
            t=self.prepare_definition(stored)
            t=validate_template(self.check_form(t))
            if t!=stored:self.set_template(t)
            if 'input_print_style' not in t:
                defaults=self.defaults()
                for key in ('input_print_style','impact_pitch','impact_dot_ratio','impact_stroke','input_stroke'):
                    t[key]=defaults.get(key)
                if t.get('input_color')==[0.13,0.38,0.57]:t['input_color']=defaults['input_color']
                self.set_template(t)
            return t
        path=self.directory/'template.json'
        t=self.prepare_definition(load_template(path) if path.exists() else self.defaults())
        self.set_template(t)
        return t

    def prepare_definition(self,t):
        # A form-specific migration must not touch another form's settings.
        if self.form_id and t.get('form_id',self.form_id)!=self.form_id:raise ValueError('別の帳票の保存先・設定は使用できません')
        return self.migrate_definition(t) if self.migrate_definition else t

    def backup(self,path,t):
        other=sqlite3.connect(path)
        try:self.db.backup(other)
        finally:other.close()
        atomic_json(Path(path).with_suffix('.template.json'),t)

    def apply_cumulative(self,records,template,start_qty='0',start_count='0',reason='累計を計算'):
        if not reason.strip(): raise ValueError('訂正理由を入力してください')
        total=dec(start_qty); count=dec(start_count)
        if count!=count.to_integral_value(): raise ValueError('開始台数は整数で指定')
        groups={(r['data'].get('date',''),r['data'].get('recipient',''),r['data'].get('site',''),r['data'].get('kind',''),r['data'].get('quantity_unit','')) for r in records}
        if len(groups)!=1: raise ValueError('同じ年月日・宛先・現場名・種類・単位の記録だけを選択してください')
        units={r['data'].get('quantity_unit','') for r in records}
        if '' in units or '-' in units: raise ValueError('数量単位を指定してください。kg等へ自動換算しません')
        updates=[]
        for r in records:
            data=copy.deepcopy(r['data'])
            if data.get('quantity') in ('',None,'-'): raise ValueError('正味重量が未記載です（空欄・-）。累計計算には数値を入力してください')
            total+=dec(data['quantity']); count+=1
            data['cumulative_quantity']=format(total,'f'); data['cumulative_count']=format(count,'f'); data['cumulative_unit']=data['quantity_unit']
            errs=validate(data,template)
            if errs: raise ValueError('\n'.join(errs))
            updates.append((r,data))
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for r,data in updates:
                current=self.get(r['id'])
                if current['revision']!=r['revision']: raise ValueError('更新競合。再読込してください')
                payload=json.dumps(data,ensure_ascii=False)
                self.db.execute('UPDATE records SET data=?,revision=revision+1,updated=? WHERE id=?',(payload,now(),r['id']))
                self.db.execute('INSERT INTO history(record_id,at,reason,before_json,after_json) VALUES(?,?,?,?,?)',(r['id'],now(),reason,json.dumps(r['data'],ensure_ascii=False),payload))
        return [self.get(r['id']) for r,_ in updates]

def csv_export(path,records,t):
    fields=[f for f in t['fields'] if f['type'] not in ('image','layout_only') and f.get('input',True)]
    with open(path,'w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=[f['label'] for f in fields]); writer.writeheader()
        for r in records: writer.writerow({f['label']:r['data'].get(f['id'],'') for f in fields})

def csv_read(path,t):
    fields={f['label']:f for f in t['fields'] if f['type'] not in ('image','layout_only') and f.get('input',True)}
    with open(path,encoding='utf-8-sig',newline='') as src:
        reader=csv.DictReader(src)
        headers=reader.fieldnames or []
        if len(set(headers))!=len(headers): raise ValueError('CSVの列名が重複しています')
        unknown=set(headers)-set(fields)
        if unknown: raise ValueError('対応する列名がありません: '+', '.join(sorted(unknown)))
        if not headers: raise ValueError('CSVのヘッダーがありません')
        records=[]
        for i,row in enumerate(reader,2):
            if None in row: raise ValueError(f'{i}行目: 列数がヘッダーより多い')
            data=blank(t)
            for name,value in row.items(): data[fields[name]['id']]=value or ''
            errs=validate(data,t)
            if errs: raise ValueError(f'{i}行目: '+' / '.join(errs))
            records.append(data)
        return records

def image_encode(path):
    from PIL import Image, ImageOps
    with Image.open(path) as src:
        im=ImageOps.exif_transpose(src).convert('RGBA'); im.thumbnail((1200,1200))
        out=io.BytesIO(); im.save(out,format='PNG')
    return base64.b64encode(out.getvalue()).decode('ascii')

def font_name(t):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    p=t.get('font_path','')
    candidates=([Path(p)] if p else [])+[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msgothic.ttc',Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/meiryo.ttc',BASE/'assets/font.ttf']
    for candidate in candidates:
        if candidate.is_file():
            name='JP_'+hashlib.sha256(str(candidate).encode()).hexdigest()[:12]
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name,str(candidate),subfontIndex=0))
            return name
    raise ValueError('日本語フォントが見つかりません。帳票設定でTTFまたはTTCを指定してください')

def styled_font(t,style,default):
    if style!='serif':return default
    candidate=Path(t.get('serif_font_path') or Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/msmincho.ttc')
    return font_name(dict(t,font_path=str(candidate))) if candidate.is_file() else default

def wrap_text(value,font,size,width,width_scale=1,tracking_em=0):
    from input_fonts import string_width
    lines=[]
    for para in value.split('\n'):
        line=''
        for ch in para:
            if line and string_width(line+ch,font,size)*width_scale+len(line)*size*tracking_em>width:
                lines.append(line); line=''
            line+=ch
        lines.append(line)
    return lines

def fit_text(value,font,size,w,h,wrap=False,min_font=14,width_scale=1,tracking_em=0):
    from input_fonts import string_width
    while size>=min_font:
        lines=wrap_text(value,font,size,w,width_scale,tracking_em) if wrap else value.split('\n')
        if len(lines)*size*1.18<=h and all(string_width(s,font,size)*width_scale+max(0,len(s)-1)*size*tracking_em<=w for s in lines): return size,lines
        size-=0.5
    raise ValueError('文字が欄内に収まりません。文字数を減らすか、設定の欄・文字サイズを調整してください')

def print_content(values,t):
    data={}
    for f in t['fields']:
        if f['type']=='layout_only' or not f.get('input',True) or not f.get('print',True):continue
        if f.get('suppressed_by') and values.get(f['suppressed_by']):continue
        value=values.get(f['id'],'')
        if f['type']=='multi_choice':
            try:
                selected=json.loads(value) if value else []
                if isinstance(selected,list) and all(isinstance(key,str) for key in selected):value=sorted(selected)
            except (ValueError,TypeError):pass
        data[f['id']]=value
    return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def print_offset(values,t,occurrence=0):
    """Stable random-looking offset in form coordinates, independent of row IDs.

    Identical input previews and saved records have the same placement. Repeated
    identical pages get separate offsets, reproducible for the same page set.
    """
    if not t.get('random_print_enabled',False):return 0.0,0.0
    payload=json.dumps([print_content(values,t),occurrence],ensure_ascii=False,separators=(',',':')).encode('utf-8')
    digest=hashlib.sha256(payload).digest()
    unit=lambda start: int.from_bytes(digest[start:start+8],'big')/(2**64-1)*2-1
    return (unit(0)*float(t.get('random_print_x_mm',.3))*float(t.get('coordinate_width',1000))/float(t['width_mm']),
            unit(8)*float(t.get('random_print_y_mm',.3))*float(t.get('coordinate_height',1300))/float(t['height_mm']))

def render_pdf(path,records,t,validate_records=True):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    validate_template(t)
    if not records: raise ValueError('出力対象がありません')
    background=None
    if t.get('render_mode')=='background':
        from background_assets import load_background
        background=load_background(t)
    font=font_name(t)
    base_font=font;style_fonts={}
    input_font=font_name(dict(t,font_path=t['input_font_path'])) if t.get('input_font_path') else base_font
    from tomei_print_font import input_font as selected_input_font
    from input_fonts import string_width,draw_text
    input_font=selected_input_font(t,input_font)
    from blue_ink import density as blue_density,color as blue_color,image as blue_image
    artwork_density=blue_density(t)
    if background is not None:background=blue_image(background,artwork_density)
    density=float(t.get('input_density',1))
    input_alpha=1-float(t.get('input_transparency',0))
    from pdf_input_alpha import begin_ink,end_ink
    ink_serial=count()
    input_ink=[1-density+channel*density for channel in t['input_color']]
    impact_cache={}
    occurrences={}
    fw,fh=float(t['width_mm'])*MM,float(t['height_mm'])*MM
    coord_w,coord_h=float(t.get('coordinate_width',1000)),float(t.get('coordinate_height',1300))
    page,slots=placements(t)
    destination=Path(path); temp=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        c=canvas.Canvas(str(temp),pagesize=page,pageCompression=1)
        c.setTitle(t['name'])
        for index,r in enumerate(records):
            if index and index%len(slots)==0:c.showPage()
            values=r.get('data',r)
            content=print_content(values,t)
            occurrence=occurrences.get(content,0);occurrences[content]=occurrence+1
            shift_x,shift_y=print_offset(values,t,occurrence)
            errs=validate(values,t) if validate_records else []
            if errs: raise ValueError('\n'.join(errs))
            ox,oy,scale=slots[index%len(slots)]
            c.saveState(); c.translate(ox,oy+fh*scale); c.scale(fw/coord_w*scale,-fh/coord_h*scale)
            fixed_blue=blue_color(t['line_color'],artwork_density)
            c.setStrokeColorRGB(*fixed_blue); c.setFillColorRGB(*fixed_blue); c.setLineWidth(t['line_width'])
            if background is not None:
                from background_compositor import draw_background
                draw_background(c,background,coord_w,coord_h)
            else:
                c.rect(0,0,coord_w,coord_h,stroke=1,fill=0)
                for line in t['lines']:
                    c.setDash(*line.get('dash',[])); c.line(*line['points'])
            c.setDash()
            def text(value,box,size=28,align='left',wrap=False,color=None,min_font=14,is_input=None,font_override=None,notice=False):
                if not value: return
                if is_input is None:is_input=color is not None
                font=font_override or (input_font if is_input else base_font)
                shaped=is_input
                width_scale=float(t.get('input_width_scale',1)) if shaped else 1
                tracking_em=float(t.get('input_tracking_em',0)) if shaped else 0
                x,y,w,h=box
                try: size,lines=fit_text(str(value),font,float(size),w,h,wrap,min_font,width_scale,tracking_em)
                except ValueError as e: raise ValueError(f'{str(value)[:30]}: {e}')
                ink=[1-density+channel*density for channel in (color or t['input_color'])] if is_input else blue_color(color or t['line_color'],artwork_density,notice=notice)
                c.setFillColorRGB(*ink)
                for i,s in enumerate(lines):
                    tx=x
                    width=string_width(s,font,size)*width_scale+max(0,len(s)-1)*size*tracking_em
                    if align=='center': tx+=(w-width)/2
                    if align=='right': tx+=w-width
                    top=y+(h-len(lines)*size*1.18)/2+i*size*1.18
                    if is_input:
                        tx=max(x,min(x+w-width,tx+shift_x))
                        # Shift all lines together, keeping their full line boxes
                        # inside the original field. Do not move the ruled form.
                        base=y+(h-len(lines)*size*1.18)/2
                        delta=max(y-base,min(y+h-len(lines)*size*1.18-base,shift_y))
                        top+=delta
                    c.saveState(); c.translate(tx,top+size*.91); c.scale(1,-1)
                    if is_input:
                        ink_group=begin_ink(c,input_alpha,(-size,-size,width+size,size*1.5),f'input_ink_{next(ink_serial)}')
                        c.setFillColorRGB(*ink)
                    if is_input and t.get('input_print_style','smooth')=='impact':
                        # A regular pin grid makes the input look like impact-printer ink.
                        # Render the glyph once to obtain coverage, then draw vector dots.
                        import pymupdf
                        mask_width=width/width_scale
                        key=(s,size,font,width_scale,tracking_em)
                        if key not in impact_cache:
                            buffer=io.BytesIO()
                            mask=canvas.Canvas(buffer,pagesize=(mask_width+size,size*1.6),pageCompression=1)
                            mask.setFillColorRGB(0,0,0);mask.setStrokeColorRGB(0,0,0)
                            mask.setLineWidth(float(t.get('impact_stroke',1.1)))
                            draw_text(mask,font,s,size,size*tracking_em/width_scale,2,size*.2,size*.3);mask.save()
                            with pymupdf.open(stream=buffer.getvalue(),filetype='pdf') as md:
                                pix=md[0].get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
                                raw=pix.samples;pitch=max(.75,float(t.get('impact_pitch',1.2)))
                                points=[]
                                # PDF baseline is 0.3em from the bottom; sample at pin centers.
                                yy=pitch/2
                                while yy<size*1.6:
                                    xx=pitch/2
                                    while xx<mask_width+size:
                                        px=min(pix.width-1,int(xx*3));py=min(pix.height-1,int(yy*3))
                                        if raw[py*pix.stride+px]<170:points.append((xx-size*.2,size*1.3-yy))
                                        xx+=pitch
                                    yy+=pitch
                                impact_cache[key]=(points,pitch)
                        points,pitch=impact_cache[key]
                        radius=pitch*float(t.get('impact_dot_ratio',.46))
                        # Invisible glyphs preserve text search and copy in the PDF.
                        c.scale(width_scale,1)
                        draw_text(c,font,s,size,size*tracking_em/width_scale,3)
                        for px,py in points:c.circle(px,py,radius,stroke=0,fill=1)
                    else:
                        if is_input:
                            c.scale(width_scale,1)
                        if is_input and t.get('input_print_style','smooth')!='plain':
                            c.setStrokeColorRGB(*ink)
                            c.setLineWidth(size*float(t.get('input_weight_em',.018)) if t.get('input_print_style')=='printer' else float(t.get('input_stroke',.5)))
                            draw_text(c,font,s,size,size*tracking_em/width_scale,2)
                        elif is_input and tracking_em:
                            draw_text(c,font,s,size,size*tracking_em/width_scale)
                        elif align=='justify' and len(s)>1:
                            obj=c.beginText(0,0);obj.setFont(font,size)
                            obj.setCharSpace((w-width)/(len(s)-1));obj.textOut(s);c.drawText(obj)
                        else:draw_text(c,font,s,size)
                    if is_input:end_ink(c,ink_group)
                    c.restoreState()
            for item in t['fixed_texts']:
                if background is not None and item.get('id') not in t.get('overlay_fixed_text_ids',[]):continue
                style=item.get('font_style')
                if style not in style_fonts:style_fonts[style]=styled_font(t,style,base_font)
                if item.get('print',True): text(t.get(item['value_key'],'') if 'value_key' in item else item['text'],item['box'],item.get('font',28),item.get('align','left'),item.get('wrap',False),color=item.get('color'),min_font=item.get('min_font',14),is_input=False,font_override=style_fonts[style],notice=item.get('id')=='copy_notice')
            if background is not None and t['background'].get('kind')=='synthetic_test':
                # Synthetic assets demonstrate the pipeline, never original fidelity.
                text('合成基盤デモ・原票背景未取得',[coord_w*.03,coord_h*.04,coord_w*.94,coord_h*.035],size=coord_w*.018,min_font=coord_w*.012,color=[.4,.4,.4],is_input=False)
            for f in t['fields']:
                if f['type']=='layout_only':continue
                if not f.get('print',True): continue
                is_input=f.get('input',True)
                if background is not None and not is_input:continue
                value=values.get(f['id'],'') if is_input else f.get('fixed_value','')
                if f['type']=='multi_choice':
                    selected=json.loads(value) if value else []
                    for option in f['options']:
                        x,y,w,h=option['box']
                        if background is None:
                            c.setStrokeColorRGB(*fixed_blue);c.setLineWidth(t['line_width']);c.rect(x,y,w,h,stroke=1,fill=0)
                            text(option['label'],option['label_box'],option.get('font',16),min_font=option.get('min_font',10),is_input=False)
                        if option['key'] in selected:
                            c.saveState()
                            if is_input:
                                ink_group=begin_ink(c,input_alpha,(0,0,coord_w,coord_h),f'input_ink_{next(ink_serial)}')
                            c.setStrokeColorRGB(*input_ink);c.setLineWidth(t.get('input_stroke',.5))
                            dx=max(-w*.2,min(w*.2,shift_x));dy=max(-h*.2,min(h*.2,shift_y))
                            c.line(x+w*.2+dx,y+h*.2+dy,x+w*.8+dx,y+h*.8+dy);c.line(x+w*.2+dx,y+h*.8+dy,x+w*.8+dx,y+h*.2+dy)
                            if is_input:end_ink(c,ink_group)
                            c.restoreState()
                    continue
                if not value: continue
                prefix=f.get('display_prefix','')
                if prefix and value!='-':
                    import unicodedata
                    normalized=lambda text:unicodedata.normalize('NFKC',str(text)).strip().casefold()
                    if not normalized(value).startswith(normalized(prefix)):
                        value=prefix+str(value)
                suffix=f.get('display_suffix','')
                if suffix and value!='-' and not str(value).rstrip().endswith(suffix.strip()):
                    value=str(value)+suffix
                if value in f.get('choice_marks',{}):
                    c.saveState()
                    if is_input:
                        ink_group=begin_ink(c,input_alpha,(0,0,coord_w,coord_h),f'input_ink_{next(ink_serial)}')
                    c.setStrokeColorRGB(*input_ink);c.setLineWidth(1.5)
                    x,y,w,h=f['choice_marks'][value];bx,by,bw,bh=f.get('mark_bounds',[0,0,coord_w,coord_h])
                    dx=max(bx-x,min(bx+bw-x-w,shift_x));dy=max(by-y,min(by+bh-y-h,shift_y))
                    c.ellipse(x+dx,y+dy,x+w+dx,y+h+dy,stroke=1,fill=0)
                    if is_input:end_ink(c,ink_group)
                    c.restoreState()
                    continue
                if f['type']=='image':
                    x,y,w,h=f['box']
                    im=ImageReader(io.BytesIO(base64.b64decode(value)))
                    iw,ih=im.getSize(); scale=min(w/iw,h/ih); dw,dh=iw*scale,ih*scale
                    dx=max(-(w-dw)/2,min((w-dw)/2,shift_x));dy=max(-(h-dh)/2,min((h-dh)/2,shift_y))
                    c.saveState();c.translate(x+(w-dw)/2+dx,y+(h+dh)/2+dy);c.scale(1,-1);c.drawImage(im,0,0,dw,dh,mask='auto');c.restoreState()
                    continue
                if f.get('suppressed_by') and values.get(f['suppressed_by']): continue
                if f.get('parts') and value!='-':
                    parts=value.split('-' if f['type']=='date' else ':')
                    for part,box in zip(parts,f['parts']): text(part,box,f.get('font',28),f.get('align','center'),color=t['input_color'],min_font=f.get('min_font',14))
                else:
                    text(value,f['box'],f.get('font',28),f.get('align','left'),f.get('wrap',False),f.get('color',t['input_color'] if is_input else t['line_color']),f.get('min_font',14),is_input=is_input)
            c.restoreState()
        c.showPage();c.save();os.replace(temp,destination)
    finally: temp.unlink(missing_ok=True)
    return page

def render_pngs(pdf_path,directory,dpi=200):
    import pymupdf as fitz
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    with fitz.open(pdf_path) as doc:
        for i,page in enumerate(doc):
            p=directory/f'{Path(pdf_path).stem}_{i+1:04}.png'
            page.get_pixmap(dpi=dpi,alpha=False).save(p);paths.append(p)
    return paths
