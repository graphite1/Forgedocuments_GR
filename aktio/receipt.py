#!/usr/bin/env python3
"""AKTIO XLSX -> receipts. Supports original and transport-ledger headers."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import argparse, json, re, sys, zipfile, xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RNS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ALIASES = {
    'date': ['日付', '計量日'], 'time': ['時刻', '計量時刻'],
    'sn': ['SN'], 'vehicle': ['車両', 'VEHICLE'],
    'trip': ['回数'], 'category': ['区分'],
    'a1l': ['1軸左'], 'a1r': ['1軸右'],
    'a2l': ['2軸左'], 'a2r': ['2軸右'],
    'a3l': ['3軸左'], 'a3r': ['3軸右'],
    'total': ['総重量'], 'tare': ['基準空車重量'], 'record_id': ['記録ID'],
}
AXLES = ['a1l', 'a1r', 'a2l', 'a2r', 'a3l', 'a3r']

def normalized(value):
    return re.sub(r'[\s\u3000]|[（(].*?[）)]', '', str(value)).upper()

def read_sheet(path):
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 100 * 1024 * 1024:
            raise ValueError('Excelの展開サイズが100MBを超えています')
        book = ET.fromstring(z.read('xl/workbook.xml'))
        sheets = book.findall('s:sheets/s:sheet', NS)
        if not sheets:
            raise ValueError('ワークシートがありません')
        selected = next((s for s in sheets if s.get('name') == '計量データ'), sheets[0])
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target = next((r.get('Target') for r in rels if r.get('Id') == selected.get('{'+RNS+'}id')), None)
        if not target:
            raise ValueError('計量シートの参照が見つかりません')
        sheet_path = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl') / target)
        # Workbook targets normally have no ..; resolve only within the ZIP namespace.
        parts = []
        for p in sheet_path.split('/'):
            if p == '..':
                if parts: parts.pop()
            elif p not in ('', '.'): parts.append(p)
        root = ET.fromstring(z.read('/'.join(parts)))
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in si.findall('.//s:t', NS))
                      for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', NS)]
        cells, rows = {}, {}
        for row in root.findall('s:sheetData/s:row', NS):
            row_number = int(row.get('r'))
            rows[row_number] = {}
            for cell in row.findall('s:c', NS):
                addr = cell.get('r'); col = re.match(r'[A-Z]+', addr).group()
                value_node = cell.find('s:v', NS); formula_node = cell.find('s:f', NS)
                raw = value_node.text if value_node is not None else None
                kind = cell.get('t')
                if kind == 's' and raw is not None: raw = shared[int(raw)]
                if kind == 'inlineStr': raw = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                item = {'value': raw, 'formula': formula_node.text if formula_node is not None else None,
                        'error': kind == 'e'}
                cells[addr] = item; rows[row_number][col] = addr
        def resolve(addr, seen=None):
            seen = set() if seen is None else set(seen)
            if addr in seen: raise ValueError('数式の循環参照: '+addr)
            seen.add(addr); item = cells.get(addr, {})
            if item.get('error'): raise ValueError('Excelのエラー値: '+addr+' '+str(item.get('value')))
            f = item.get('formula')
            # Follow simple source references before caches so current settings are reflected.
            if f:
                ref = re.fullmatch(r'\$?([A-Z]+)\$?([0-9]+)', f)
                if ref: return resolve(ref[1]+ref[2], seen)
                parts = re.split(r'(&)(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', f)
                if '&' in parts:
                    values = []
                    for part in parts:
                        if part == '&': continue
                        part = part.strip()
                        if re.fullmatch(r'"(?:[^"]|"")*"', part): values.append(part[1:-1].replace('""', '"'))
                        elif re.fullmatch(r'\$?[A-Z]+\$?[0-9]+', part): values.append(str(resolve(part.replace('$',''), seen) or ''))
                        else: break
                    else: return ''.join(values)
            return item.get('value')
        header_row = None; mapping = {}
        for number, row in rows.items():
            found = {}
            for col, addr in row.items():
                value = normalized(cells[addr].get('value') or '')
                for key, aliases in ALIASES.items():
                    if value in [normalized(a) for a in aliases]: found[key] = col
            if all(k in found for k in ['date', 'time', 'sn', *AXLES]):
                header_row, mapping = number, found; break
        if header_row is None:
            raise ValueError('対応する見出し行が見つかりません。日付・時刻・SN・6つの軸左右重量を確認してください')
        records = []
        for number, row in rows.items():
            if number <= header_row: continue
            data = {key: resolve(row.get(col, '')) for key, col in mapping.items()}
            # Ignore formula-only template rows and the summary blocks outside the data table.
            active = any(data.get(k) not in (None, '') for k in [*AXLES, 'total', 'time', 'sn'])
            if active: records.append((number, data))
        default_tare = None
        for number, row in rows.items():
            if number >= header_row: break
            if any(normalized(cells[addr].get('value') or '') == '管理用空車重量' for addr in row.values()):
                for col, addr in row.items():
                    v = resolve(addr)
                    try:
                        if v not in (None, '') and Decimal(str(v)) > 0:
                            default_tare = integer(v, '管理用空車重量'); break
                    except (ValueError, InvalidOperation): pass
                if default_tare is not None: break
        return records, mapping, default_tare

def integer(value, label):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n != n.to_integral_value(): raise ValueError()
        return int(n)
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError(label+'は0以上の整数kgで入力してください')

def date_text(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z','+00:00')).strftime('%d/%m/%Y')
    except ValueError: pass
    try:
        n = float(value)
        if not 1 <= n <= 2958465: raise ValueError()
        return (datetime(1899,12,30)+timedelta(days=n)).strftime('%d/%m/%Y')
    except (ValueError, TypeError, OverflowError): pass
    for fmt in ('%Y/%m/%d','%Y-%m-%d','%d/%m/%Y'):
        try: return datetime.strptime(str(value),fmt).strftime('%d/%m/%Y')
        except ValueError: pass
    raise ValueError('日付が不正です')

def time_text(value):
    if value in (None, ''): raise ValueError('時刻が未入力です')
    try:
        n = float(value)
        if n < 0 or n > 2958465: raise ValueError()
        minutes = int(round((n % 1) * 1440)) % 1440
        return f'{minutes//60:02d}:{minutes%60:02d}'
    except (ValueError, TypeError): pass
    m = re.fullmatch(r'(\d{1,2}):(\d{2})(?::\d{2})?', str(value).strip())
    if m and int(m[1]) < 24 and int(m[2]) < 60: return f'{int(m[1]):02d}:{int(m[2]):02d}'
    raise ValueError('時刻が不正です')

def prepare_record(number, data, mapping, default_tare):
    if data.get('date') in (None,''): raise ValueError('日付が未入力です')
    if data.get('sn') in (None,''): raise ValueError('SNが未入力です')
    date, time = date_text(data['date']), time_text(data.get('time'))
    sn = str(data['sn']).strip()
    if not re.fullmatch(r'[0-9]+(?:\.0+)?', sn): raise ValueError('SNは数字で入力してください')
    sn = str(int(Decimal(sn))).zfill(4)
    if len(sn)>4: raise ValueError('SNは0～9999で入力してください')
    vals = [integer(data.get(k), k) for k in AXLES]
    subtotals = [sum(vals[i:i+2]) for i in (0,2,4)]
    axes_total = sum(subtotals)
    transport = 'category' in mapping or 'trip' in mapping
    total = integer(data.get('total'), '総重量') if transport else axes_total
    if total <= 0: raise ValueError('総重量が0kgです')
    if total != axes_total: raise ValueError(f'軸合計{axes_total}kgと総重量{total}kgが不一致です')
    category = str(data.get('category') or '計量')
    if transport and category not in ('空車','積載'): raise ValueError('区分を空車／積載で指定してください')
    tare_raw = data.get('tare')
    tare = default_tare if tare_raw in (None,'') else integer(tare_raw,'基準空車重量')
    if category == '積載' and (tare is None or tare <= 0): raise ValueError('管理用空車重量が未入力です')
    payload = total-tare if category == '積載' else None
    if payload is not None and payload < 0: raise ValueError('積載時の総重量が管理用空車重量を下回っています')
    return {'mode': 'measured', 'excel_row': number, 'date': date, 'time': time, 'sn': sn,
            'vehicle': str(data.get('vehicle') or '').strip(),
            'trip': str(data.get('trip') or '0' if category == '空車' else data.get('trip') or ''),
            'category': category, 'axle_values_kg': vals, 'axle_totals_kg': subtotals,
            'total_kg': total, 'tare_kg': tare, 'payload_kg': payload,
            'record_id': str(data.get('record_id') or f'row{number}')}

def fonts():
    mono = next((p for p in [Path('C:/Windows/Fonts/consola.ttf'),Path('C:/Windows/Fonts/cour.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')] if p.exists()), None)
    if mono is None: raise ValueError('等幅フォントが見つかりません')
    return lambda size: ImageFont.truetype(str(mono),size)

def receipt_layout():
    from .asset_files import bundle_files
    root=bundle_files()[0].parent
    return root,json.loads((root/'layout.json').read_text(encoding='utf-8'))


def render_receipt_image(record, placement='center', notice_color='charcoal'):
    from .output_layout import checked_color,notice_image,notice_box,NOTICE_GAP
    checked_color(notice_color)
    if record.get('mode') not in ('simulation','measured'):
        raise ValueError('計画・実測の区分を確認できません')
    if date_text(record['date'])!=record['date'] or time_text(record['time'])!=record['time']:
        raise ValueError('日付・時刻の形式が不正です')
    if not re.fullmatch(r'[0-9]{4}',record['sn']):raise ValueError('SNは4桁の数字です')
    if type(record['excel_row']) is not int or record['excel_row']<1:raise ValueError('行番号が不正です')
    vals=record['axle_values_kg']
    if (len(vals)!=6 or any(type(v) is not int or v<0 for v in vals) or
        record['axle_totals_kg']!=[sum(vals[i:i+2]) for i in (0,2,4)] or record['total_kg']!=sum(vals)):
        raise ValueError('軸左右・軸計・TOTALが一致しません')
    root,layout=receipt_layout()
    image=Image.open(root/'a4_blank.png').convert('RGB')
    atlas=Image.open(root/'digits.png').convert('L')
    chars=layout['glyph_chars'];pitch=layout['character_pitch_px']
    vals=record['axle_values_kg'];sums=record['axle_totals_kg']
    fields={'date':record['date'],'time':record['time'],'sn':record['sn'],
            'a1l':vals[0],'a1r':vals[1],'a1sum':sums[0],
            'a2l':vals[2],'a2r':vals[3],'a2sum':sums[1],
            'a3l':vals[4],'a3r':vals[5],'a3sum':sums[2],'total':record['total_kg']}
    for key,value in fields.items():
        f=layout['fields'][key];value=str(value)
        if key in ('date','time','sn') and len(value)>f['slots']:
            raise ValueError(key+'の文字数が原本の印字欄を超えています')
        if key not in ('date','time','sn') and len(value)>f['slots']+1:
            raise ValueError(key+'の桁数が原本の印字欄を超えています')
        start=0 if key in ('date','time','sn') else f['slots']-len(value)
        for index,c in enumerate(value):
            if c not in chars: raise ValueError('表示できない文字: '+c)
            glyph=atlas.crop((chars.index(c)*24,0,chars.index(c)*24+24,36))
            x=round(f['x']+(start+index)*pitch)
            y=round(f['y']+layout['row_skew']*index*pitch)
            image.paste(glyph.convert('RGB'),(x,y))
    crop=layout.get('original_receipt_crop_px',[1320,580,1950,1260])
    if placement=='reference':
        if record['mode']=='simulation':
            label=notice_image(notice_color)
            image.paste(label,(crop[0]+(crop[2]-crop[0]-label.width)//2,crop[3]+NOTICE_GAP))
        return image
    receipt=image.crop(crop)
    page=Image.new('RGB',image.size,'white')
    at=((page.width-receipt.width)//2,(page.height-receipt.height)//2)
    page.paste(receipt,at)
    if record['mode']=='simulation':page.paste(notice_image(notice_color),notice_box(record,layout)[:2])
    return page


def output_image(record,paper='a4',notice_color='charcoal'):
    from .output_layout import output_box
    image=render_receipt_image(record,notice_color=notice_color)
    if paper=='receipt':
        _,layout=receipt_layout();return image.crop(output_box(record,layout))
    if paper!='a4':raise ValueError('出力用紙を確認してください')
    return image

def render_receipt(record, folder, paper='a4',notice_color='charcoal'):
    image=output_image(record,paper,notice_color)
    prefix='AKTIO_出力見本' if record['mode']=='simulation' else 'AKTIO_実測'
    name=f'{prefix}_{record["date"].replace("/","-")}_{record["time"].replace(":","-")}_SN{record["sn"]}_row{record["excel_row"]}'
    image.save(folder/(name+'.png'),dpi=(300,300))
    image.save(folder/(name+'.pdf'),resolution=300)
    return image,name

def main(argv=None):
    parser=argparse.ArgumentParser(description='AKTIO ExcelからPNG・PDFを一括作成')
    parser.add_argument('excel',type=Path); parser.add_argument('output',type=Path,nargs='?')
    args=parser.parse_args(argv)
    if not args.excel.is_file(): raise ValueError('Excelファイルが見つかりません: '+str(args.excel))
    folder=args.output or args.excel.parent/'AKTIO_レシート出力'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True,exist_ok=True)
    records,mapping,tare=read_sheet(args.excel)
    successes=[]; errors=[]; images=[]
    for number,data in records:
        try:
            record=prepare_record(number,data,mapping,tare)
            image,name=render_receipt(record,folder)
            images.append(folder/(name+'.png'));record['files']=[name+'.png',name+'.pdf'];successes.append(record)
            print(f'OK 行{number}: SN {record["sn"]} / 総重量 {record["total_kg"]:,} kg')
        except (ValueError, OverflowError) as e:
            errors.append({'excel_row':number,'message':str(e)});print(f'要確認 行{number}: {e}')
    if images:
        from .pdf_bundle import combine_png_pages
        combine_png_pages(images,folder/'全レシート.pdf')
    payloads=[r['payload_kg'] for r in successes if r['payload_kg'] is not None]
    summary={'source_excel':args.excel.name,'created_at':datetime.now().isoformat(timespec='seconds'),
             'success_count':len(successes),'error_count':len(errors),'management_tare_kg':tare,
             'loaded_receipt_count':len(payloads),'positive_payload_trip_count':sum(p>0 for p in payloads),
             'payload_total_kg':sum(payloads) if payloads else None,
             'records':successes,'errors':errors}
    (folder/'転記データ.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=[f'作成 {len(successes)}件 / 要確認 {len(errors)}件',
           f'管理用空車重量: {tare:,} kg' if tare is not None else '管理用空車重量: 指定なし',
           '全レシート.pdfは作成できた記録のみ収録。空車原記録は運搬重量の集計から除外。',
           '未計量の入力枠は出力しません。未入力の軸重量や時刻は補完しません。',
           *[f'行{e["excel_row"]}: {e["message"]}' for e in errors]]
    (folder/'実行結果.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    print(f'完了。出力先: {folder}')
    return 1 if errors else (0 if successes else 2)

if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,zipfile.BadZipFile,ET.ParseError) as exc:
        print('エラー: '+str(exc));raise SystemExit(2)
