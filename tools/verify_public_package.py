"""Extract only a source ZIP and prove the bundled plan opens on first use."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


CHILD = '''
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import patch
import copy,hashlib,io,json,sys,tempfile,tkinter as tk
import pymupdf
from PIL import Image
import core
from background_assets import load_background
from form_registry import catalog,open_screen
from tomei_preset import PUBLIC_SHA256,public_bundle_files
assert core.BASE.resolve()==Path.cwd().resolve()
assert not (Path.cwd()/'private').exists()
assert not (Path.cwd()/'private-assets').exists()
if sys.argv[1]=='1':
 from reportlab.pdfbase import pdfmetrics
 from reportlab.pdfbase.cidfonts import UnicodeCIDFont
 pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
font=patch('core.font_name',return_value='HeiseiKakuGo-W5') if sys.argv[1]=='1' else nullcontext()
with font,tempfile.TemporaryDirectory() as data:
 root=tk.Tk();root.withdraw()
 app=open_screen(next(r for r in catalog() if r['id']=='tomei_taiheiyo'),root,Path(data)/'fresh')
 try:
  assert app.template['background']['status']=='ready'
  assert app.template['layout_profile']=='generated-20261014'
  assert app.notebook.select()==str(app.entrytab)
  assert all(v=='' for v in app.values().values())
  assert not app.store.list()
  assert app.preview_view.doc is not None
  expected=load_background(app.template)
  page=app.preview_view.doc[0]
  assert len(page.search_for('納入書（計画）'))==1
  assert len(page.get_images())==1
  bitmap=Image.open(io.BytesIO(app.preview_view.doc.extract_image(page.get_images()[0][0])['image'])).convert('RGB')
  assert bitmap.tobytes()==expected.tobytes()
  for point in ((714,502),(934,502),(374,1337),(874,1337)):
   assert bitmap.getpixel(point)==(255,255,255)
  t=copy.deepcopy(app.template)
  t['page_layout'].update(paper='A4',rows=2,columns=2,margin_x_mm=5,margin_y_mm=5,gap_x_mm=3,gap_y_mm=4,scale='fit')
  target=Path(data)/'four-up.pdf';core.render_pdf(target,[core.blank(t)]*5,t)
  with pymupdf.open(target) as doc:
   counts=[len(page.search_for('納入書（計画）')) for page in doc]
   assert counts==[4,1]
  files=public_bundle_files()
  from tools.build_windows import public_asset_args
  args=public_asset_args()
  assert all(str(file)+':assets' in args for file in files)
  result={'isolated_source_imports':True,'private_workspace_needed':False,
   'clean_first_open_preview':True,'inputs_blank':True,'database_records':0,
   'background_status':'ready','layout_profile':t['layout_profile'],
   'embedded_background_pixel_difference':0,'signature_and_arrival_empty':True,
   'four_up_notices_per_page':counts,'windows_recipe_includes_public_assets':True,
   'public_image_sha256':PUBLIC_SHA256,'windows_exe_generated':False,
   'font':'Japanese CID substitute' if sys.argv[1]=='1' else 'configured runtime font'}
  print(json.dumps(result,ensure_ascii=False))
 finally:app.store.close();root.destroy()
'''


CHILD_HEADLESS = r'''
from pathlib import Path
from unittest.mock import patch
import copy,json,tempfile
import pymupdf
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import core
from app_storage import AppStorage
from form_registry import catalog,default_definition
from tomei_preset import with_bundled_preset,public_bundle_files
from tomei_screen import DEFINITION
from tomei_print_font import validated_file,validated_observed_file
from aktio.asset_files import bundle_files
from aktio.state import SessionStore
from aktio.receipt import render_receipt
from aktio.planning import make_plan
assert core.BASE.resolve()==Path.cwd().resolve()
assert validated_file() is not None and validated_observed_file() is not None
assert len(bundle_files())==4
assert len(public_bundle_files())==2
pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
with tempfile.TemporaryDirectory() as data,patch('tkinter.Tk',side_effect=AssertionError('GUI forbidden')),patch('tkinter.Toplevel',side_effect=AssertionError('GUI forbidden')),patch('core.font_name',return_value='HeiseiKakuGo-W5'):
 manager=AppStorage(data);rows=catalog();paths=[manager.prepare(default_definition(r)) for r in rows]
 assert len(set(paths))==3
 store=SessionStore(paths[2]);assert store.load_session() is None;store.close()
 t=with_bundled_preset(core.load_template(DEFINITION));values=core.blank(t);values['mix_plan_number']='12345678-90'
 t['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
 pdf=Path(data)/'tomei.pdf';core.render_pdf(pdf,[values]*5,t)
 with pymupdf.open(pdf) as doc:assert [len(p.search_for('納入書（計画）')) for p in doc]==[4,1]
 c=dict(date='2030-01-02',start='07:00',end='17:00',breaks=[['12:00','13:00']],measurement_mode='count',first_sn=1,seed=0)
 v=dict(vehicle='SYNTHETIC',runs=2,tare_kg=11180,max_payload_kg=10000,max_gross_kg=21180,target_payload_kg=9000,weight_jitter_kg=500)
 records=make_plan(c,[v]);image,name=render_receipt(records[0],Path(data),paper='receipt')
 assert '計画' in name and image.size==(630,680)
 print(json.dumps({'isolated_source_imports':True,'gui_executed':False,'private_workspace_needed':False,'form_storage_isolated':True,'approved_numeric_font_validated':True,'aktio_blank_assets_validated':True,'four_up_notices_per_page':[4,1],'aktio_receipt_pixels':[630,680],'windows_exe_generated':False,'windows_gui_and_printing_verified':False,'font':'Japanese CID substitute'}))
'''


def verify(archive,output,cid_font=False,headless=False):
    with tempfile.TemporaryDirectory(prefix='gr_public_source_') as temp:
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC failed')
            names=[n for n in z.namelist() if not n.endswith('/')]
            prefix=names[0].split('/')[0]
            if any(not n.startswith(prefix+'/') or '..' in Path(n).parts for n in z.namelist()):raise ValueError('Unsafe archive path')
            relative=[n.split('/',1)[1] for n in names]
            forbidden=[n for n in relative if Path(n).suffix.lower() in ('.pdf','.sqlite3','.db','.key','.pem','.exe','.xlsx','.zip') or 'private' in Path(n).parts or 'private-assets' in Path(n).parts]
            images=[n for n in relative if Path(n).suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
            if forbidden or set(images)!={'assets/tomei-plan-background.png','aktio/assets/a4_blank.png','aktio/assets/digits.png'}:raise ValueError('Unexpected public assets: '+str(forbidden+images))
            commit=z.comment.decode('ascii')
            z.extractall(temp)
        root=Path(temp)/prefix
        child=subprocess.run([sys.executable,'-B','-c',CHILD_HEADLESS if headless else CHILD,'1' if cid_font else '0'],cwd=root,capture_output=True,text=True)
        if child.returncode:raise RuntimeError(child.stderr)
        result=json.loads(child.stdout)
        result.update(source_commit=commit,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                      archive_file_count=len(names),only_approved_public_image=True,crc_verified=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cid-font',action='store_true',help='Cloud-only Japanese CID font, not Windows validation')
    parser.add_argument('--headless',action='store_true',help='Verify source imports, storage and renderers without creating GUI windows')
    args=parser.parse_args();print(json.dumps(verify(args.archive,args.output,args.cid_font,args.headless),ensure_ascii=False,indent=2))
