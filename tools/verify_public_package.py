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


def verify(archive,output,cid_font=False):
    with tempfile.TemporaryDirectory(prefix='gr_public_source_') as temp:
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:raise ValueError('ZIP CRC failed')
            names=[n for n in z.namelist() if not n.endswith('/')]
            prefix=names[0].split('/')[0]
            if any(not n.startswith(prefix+'/') or '..' in Path(n).parts for n in z.namelist()):raise ValueError('Unsafe archive path')
            relative=[n.split('/',1)[1] for n in names]
            forbidden=[n for n in relative if Path(n).suffix.lower() in ('.pdf','.sqlite3','.db','.key','.pem','.exe') or 'private' in Path(n).parts or 'private-assets' in Path(n).parts]
            images=[n for n in relative if Path(n).suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
            if forbidden or images!=['assets/tomei-plan-background.png']:raise ValueError('Unexpected public assets: '+str(forbidden+images))
            commit=z.comment.decode('ascii')
            z.extractall(temp)
        root=Path(temp)/prefix
        child=subprocess.run([sys.executable,'-B','-c',CHILD,'1' if cid_font else '0'],cwd=root,capture_output=True,text=True)
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
    args=parser.parse_args();print(json.dumps(verify(args.archive,args.output,args.cid_font),ensure_ascii=False,indent=2))
