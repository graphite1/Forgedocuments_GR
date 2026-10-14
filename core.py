"""Form-specific metadata is in template.json; persistence and rendering are generic."""
from __future__ import annotations
import base64, copy, csv, hashlib, io, json, math, os, re, sqlite3, uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from page_layout import placements
from input_definitions import default_values,validate_definitions

BASE = Path(__file__).resolve().parent
MM = 72 / 25.4

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def load_template(path=None):
    return json.loads(Path(path or BASE/'template.json').read_text(encoding='utf-8-sig'))

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
    d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError('有限の数値を入力してください')
    return d

def validate(values, template):
    errors = []
    for f in template['fields']:
        value = values.get(f['id'], '')
        if not isinstance(value, str):
            errors.append(f"{f['label']}: 文字列として保存してください")
            continue
        if not value:
            if f.get('required'): errors.append(f"{f['label']}: 未入力です")
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
    for f in t['fields']:
        if f.get('font',28)<=0: raise ValueError('文字サイズは正数で設定')
        for box in [f['box']]+f.get('parts',[])+list(f.get('choice_marks',{}).values())+([f['mark_bounds']] if 'mark_bounds' in f else []):
            x,y,bw,bh=map(float,box)
            if x<0 or y<0 or bw<=0 or bh<=0 or x+bw>1000 or y+bh>1300: raise ValueError(f"{f['label']}: 印字領域が外周枠を超えています")
        if f.get('min') is not None and f.get('max') is not None and dec(f['min'])>dec(f['max']): raise ValueError(f"{f['label']}: 下限が上限を超えています")
    for item in t['fixed_texts']:
        x,y,bw,bh=map(float,item['box'])
        if x<0 or y<0 or bw<=0 or bh<=0 or x+bw>1000 or y+bh>1300: raise ValueError('固定文の印字領域が外周枠を超えています')
    if float(t.get('original_margin_mm',0.5))<0: raise ValueError('外側余白は0以上で設定')
    if type(t.get('random_print_enabled',False)) is not bool:raise ValueError('ランダム印字はON/OFFで指定')
    for key in ('random_print_x_mm','random_print_y_mm'):
        value=t.get(key,0.3)
        if isinstance(value,bool) or not math.isfinite(float(value)) or not 0<=float(value)<=2:
            raise ValueError('ランダム印字のずれ幅は0〜2mmで設定')
    placements(t)
    return t

class Store:
    def __init__(self, directory, default_template=None, form_id=None):
        self.default_template=default_template
        self.form_id=form_id
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
        return t

    def list(self, archived=False):
        return [dict(id=r[0],data=json.loads(r[1]),revision=r[2],created=r[3],updated=r[4],archived=bool(r[5])) for r in self.db.execute('SELECT id,data,revision,created,updated,archived FROM records WHERE archived=? ORDER BY rowid',(int(archived),))]

    def get(self,rid):
        r=self.db.execute('SELECT data,revision,created,updated,archived FROM records WHERE id=?',(rid,)).fetchone()
        if r is None: raise ValueError('記録が見つかりません')
        return dict(id=rid,data=json.loads(r[0]),revision=r[1],created=r[2],updated=r[3],archived=bool(r[4]))

    def save(self,data,template,rid=None,revision=None,reason='新規登録'):
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
            t=validate_template(self.check_form(json.loads(row[0])))
            if 'input_print_style' not in t:
                defaults=self.defaults()
                for key in ('input_print_style','impact_pitch','impact_dot_ratio','impact_stroke','input_stroke'):
                    t[key]=defaults.get(key)
                if t.get('input_color')==[0.13,0.38,0.57]:t['input_color']=defaults['input_color']
                self.set_template(t)
            return t
        path=self.directory/'template.json'
        t=load_template(path) if path.exists() else self.defaults()
        self.set_template(t)
        return t

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
        if '' in units: raise ValueError('数量単位を指定してください。kg等へ自動換算しません')
        updates=[]
        for r in records:
            data=copy.deepcopy(r['data'])
            if not data.get('quantity'): raise ValueError('正味重量が空欄です')
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
    fields=[f for f in t['fields'] if f['type']!='image']
    with open(path,'w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=[f['label'] for f in fields]); writer.writeheader()
        for r in records: writer.writerow({f['label']:r['data'].get(f['id'],'') for f in fields})

def csv_read(path,t):
    fields={f['label']:f for f in t['fields'] if f['type']!='image'}
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

def wrap_text(value,font,size,width):
    from reportlab.pdfbase import pdfmetrics
    lines=[]
    for para in value.split('\n'):
        line=''
        for ch in para:
            if line and pdfmetrics.stringWidth(line+ch,font,size)>width:
                lines.append(line); line=''
            line+=ch
        lines.append(line)
    return lines

def fit_text(value,font,size,w,h,wrap=False,min_font=14):
    from reportlab.pdfbase import pdfmetrics
    while size>=min_font:
        lines=wrap_text(value,font,size,w) if wrap else value.split('\n')
        if len(lines)*size*1.18<=h and all(pdfmetrics.stringWidth(s,font,size)<=w for s in lines): return size,lines
        size-=0.5
    raise ValueError('文字が欄内に収まりません。文字数を減らすか、設定の欄・文字サイズを調整してください')

def print_offset(values,t,occurrence=0):
    """Stable random-looking offset in form coordinates, independent of row IDs.

    Identical input previews and saved records have the same placement. Repeated
    identical pages get separate offsets, reproducible for the same page set.
    """
    if not t.get('random_print_enabled',False):return 0.0,0.0
    payload=json.dumps([values,occurrence],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    digest=hashlib.sha256(payload).digest()
    unit=lambda start: int.from_bytes(digest[start:start+8],'big')/(2**64-1)*2-1
    return (unit(0)*float(t.get('random_print_x_mm',.3))*1000/float(t['width_mm']),
            unit(8)*float(t.get('random_print_y_mm',.3))*1300/float(t['height_mm']))

def render_pdf(path,records,t,validate_records=True):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    validate_template(t)
    if not records: raise ValueError('出力対象がありません')
    font=font_name(t)
    impact_cache={}
    occurrences={}
    fw,fh=float(t['width_mm'])*MM,float(t['height_mm'])*MM
    page,slots=placements(t)
    destination=Path(path); temp=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        c=canvas.Canvas(str(temp),pagesize=page,pageCompression=1)
        c.setTitle(t['name'])
        for index,r in enumerate(records):
            if index and index%len(slots)==0:c.showPage()
            values=r.get('data',r)
            content=json.dumps(values,ensure_ascii=False,sort_keys=True)
            occurrence=occurrences.get(content,0);occurrences[content]=occurrence+1
            shift_x,shift_y=print_offset(values,t,occurrence)
            errs=validate(values,t) if validate_records else []
            if errs: raise ValueError('\n'.join(errs))
            ox,oy,scale=slots[index%len(slots)]
            c.saveState(); c.translate(ox,oy+fh*scale); c.scale(fw/1000*scale,-fh/1300*scale)
            c.setStrokeColorRGB(*t['line_color']); c.setFillColorRGB(*t['line_color']); c.setLineWidth(t['line_width'])
            c.rect(0,0,1000,1300,stroke=1,fill=0)
            for line in t['lines']:
                c.setDash(*line.get('dash',[])); c.line(*line['points'])
            c.setDash()
            def text(value,box,size=28,align='left',wrap=False,color=None,min_font=14):
                if not value: return
                x,y,w,h=box
                try: size,lines=fit_text(str(value),font,float(size),w,h,wrap,min_font)
                except ValueError as e: raise ValueError(f'{str(value)[:30]}: {e}')
                c.setFillColorRGB(*(color or t['line_color']))
                for i,s in enumerate(lines):
                    tx=x
                    from reportlab.pdfbase import pdfmetrics
                    width=pdfmetrics.stringWidth(s,font,size)
                    if align=='center': tx+=(w-width)/2
                    if align=='right': tx+=w-width
                    top=y+(h-len(lines)*size*1.18)/2+i*size*1.18
                    if color is not None:
                        tx=max(x,min(x+w-width,tx+shift_x))
                        # Shift all lines together, keeping their full line boxes
                        # inside the original field. Do not move the ruled form.
                        base=y+(h-len(lines)*size*1.18)/2
                        delta=max(y-base,min(y+h-len(lines)*size*1.18-base,shift_y))
                        top+=delta
                    c.saveState(); c.translate(tx,top+size*.91); c.scale(1,-1)
                    if color is not None and t.get('input_print_style','smooth')=='impact':
                        # A regular pin grid makes the input look like impact-printer ink.
                        # Render the glyph once to obtain coverage, then draw vector dots.
                        import pymupdf
                        key=(s,size,font)
                        if key not in impact_cache:
                            buffer=io.BytesIO()
                            mask=canvas.Canvas(buffer,pagesize=(width+size,size*1.6),pageCompression=1)
                            mask.setFillColorRGB(0,0,0);mask.setStrokeColorRGB(0,0,0)
                            mask.setLineWidth(float(t.get('impact_stroke',1.1)))
                            glyph=mask.beginText(size*.2,size*.3);glyph.setFont(font,size);glyph.setTextRenderMode(2);glyph.textOut(s);mask.drawText(glyph);mask.save()
                            with pymupdf.open(stream=buffer.getvalue(),filetype='pdf') as md:
                                pix=md[0].get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
                                raw=pix.samples;pitch=max(.75,float(t.get('impact_pitch',1.2)))
                                points=[]
                                # PDF baseline is 0.3em from the bottom; sample at pin centers.
                                yy=pitch/2
                                while yy<size*1.6:
                                    xx=pitch/2
                                    while xx<width+size:
                                        px=min(pix.width-1,int(xx*3));py=min(pix.height-1,int(yy*3))
                                        if raw[py*pix.stride+px]<170:points.append((xx-size*.2,size*1.3-yy))
                                        xx+=pitch
                                    yy+=pitch
                                impact_cache[key]=(points,pitch)
                        points,pitch=impact_cache[key]
                        radius=pitch*float(t.get('impact_dot_ratio',.46))
                        # Invisible glyphs preserve text search and copy in the PDF.
                        obj=c.beginText(0,0);obj.setFont(font,size);obj.setTextRenderMode(3);obj.textOut(s);c.drawText(obj)
                        for px,py in points:c.circle(px,py,radius,stroke=0,fill=1)
                    else:
                        c.setFont(font,size)
                        if color is not None:
                            c.setStrokeColorRGB(*color);c.setLineWidth(float(t.get('input_stroke',.5)))
                            obj=c.beginText(0,0);obj.setFont(font,size);obj.setTextRenderMode(2);obj.textOut(s);c.drawText(obj)
                        else:c.drawString(0,0,s)
                    c.restoreState()
            for item in t['fixed_texts']:
                if item.get('print',True): text(t.get(item['value_key'],'') if 'value_key' in item else item['text'],item['box'],item.get('font',28),item.get('align','left'),item.get('wrap',False),min_font=item.get('min_font',14))
            for f in t['fields']:
                if not f.get('print',True): continue
                value=values.get(f['id'],'')
                if not value: continue
                if value in f.get('choice_marks',{}):
                    c.setStrokeColorRGB(*t['input_color']);c.setLineWidth(1.5)
                    x,y,w,h=f['choice_marks'][value];bx,by,bw,bh=f.get('mark_bounds',[0,0,1000,1300])
                    dx=max(bx-x,min(bx+bw-x-w,shift_x));dy=max(by-y,min(by+bh-y-h,shift_y))
                    c.ellipse(x+dx,y+dy,x+w+dx,y+h+dy,stroke=1,fill=0)
                    c.setStrokeColorRGB(*t['line_color']);c.setLineWidth(t['line_width'])
                    continue
                if f['type']=='image':
                    x,y,w,h=f['box']
                    im=ImageReader(io.BytesIO(base64.b64decode(value)))
                    iw,ih=im.getSize(); scale=min(w/iw,h/ih); dw,dh=iw*scale,ih*scale
                    dx=max(-(w-dw)/2,min((w-dw)/2,shift_x));dy=max(-(h-dh)/2,min((h-dh)/2,shift_y))
                    c.saveState();c.translate(x+(w-dw)/2+dx,y+(h+dh)/2+dy);c.scale(1,-1);c.drawImage(im,0,0,dw,dh,mask='auto');c.restoreState()
                    continue
                if f.get('suppressed_by') and values.get(f['suppressed_by']): continue
                if f.get('parts'):
                    parts=value.split('-' if f['type']=='date' else ':')
                    for part,box in zip(parts,f['parts']): text(part,box,f.get('font',28),f.get('align','center'),color=t['input_color'],min_font=f.get('min_font',14))
                else:
                    text(value,f['box'],f.get('font',28),f.get('align','left'),f.get('wrap',False),t['input_color'],f.get('min_font',14))
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
