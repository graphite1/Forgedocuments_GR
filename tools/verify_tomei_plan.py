"""Validate private real-background settings and render review artifacts (CID only)."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pymupdf
from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import core
from background_assets import load_background
from tomei_screen import App, validate_policy


def verify(settings, values, output):
    output.mkdir(parents=True, exist_ok=True)
    t=core.load_template(settings);validate_policy(t)
    data=json.loads(values.read_text(encoding='utf-8'))
    assert not core.validate(data,t)
    assert t['background']['kind']=='corrected_blue'
    expected=load_background(t)
    pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
    evidence={'font':'Japanese CID substitute; Windows unverified',
              'profile':t['layout_profile'], 'background_pixel_size':list(expected.size),
              'original_pixel_fidelity':False, 'provisional_width_mm':t['width_mm'],
              'files':{}, 'preview_iterations':12}
    with patch('core.font_name',return_value='HeiseiKakuGo-W5'):
        single=output/'tomei-plan-single.pdf';core.render_pdf(single,[data],t)
        multi=copy.deepcopy(t)
        multi['page_layout'].update(paper='A4',rows=2,columns=2,margin_x_mm=5,margin_y_mm=5,
                                    gap_x_mm=3,gap_y_mm=4,scale='fit')
        batch=output/'tomei-plan-a4-four-up.pdf';core.render_pdf(batch,[data]*5,multi)
        for path,counts in ((single,[1]),(batch,[4,1])):
            with pymupdf.open(path) as doc:
                assert len(doc)==len(counts)
                for index,(page,count) in enumerate(zip(doc,counts)):
                    assert len(page.search_for('納入書（計画）'))==count
                    assert '再生成' not in page.get_text()
                    assert page.get_text().count('005.500')==count
                    images=page.get_images();assert len(images)==1
                    assert len(page.get_image_rects(images[0][0]))==count
                    bitmap=Image.open(io.BytesIO(doc.extract_image(images[0][0])['image'])).convert('RGB')
                    assert bitmap.size==expected.size and bitmap.tobytes()==expected.tobytes()
                    # Values in the two signatures and arrival slots are blank even
                    # if a later source replacement contains blue handwriting.
                    for x,y in [(740,500),(940,500),(360,1335),(850,1335)]:
                        assert bitmap.getpixel((x,y))==(255,255,255)
                    page.get_pixmap(dpi=180,alpha=False).save(output/f'{path.stem}-{index+1}.png')
                evidence['files'][path.name]={'pages':len(doc),'notices_per_page':counts,
                     'embedded_background_pixel_difference':0,
                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        with tempfile.TemporaryDirectory() as temp:
            root=tk.Tk();root.withdraw();app=App(root,Path(temp))
            try:
                app.set_values(data);app.save()
                record=copy.deepcopy(app.current);history=app.store.history(record['id'])
                with patch('definition_screen.filedialog.askopenfilename',return_value=str(settings.resolve())):
                    app.import_template()
                app.save_settings()
                for i in range(12):
                    current=copy.deepcopy(data);current['vehicle_number']=f'{i:04}'
                    app.set_values(current);app.preview_current()
                    assert current['vehicle_number'] in app.preview_view.doc[0].get_text()
                saved=Path(temp)/'same-as-preview.pdf';core.render_pdf(saved,[app.values()],app.template)
                with pymupdf.open(saved) as doc:
                    assert doc[0].get_pixmap().samples==app.preview_view.doc[0].get_pixmap().samples
                assert app.store.get(record['id'])==record
                assert app.store.history(record['id'])==history
                assert not list((Path(temp)/'preview').glob('*.pdf'))
                evidence.update(preview_saved_pixel_difference=0,records_and_history_unchanged=True,
                                gui_settings_import=True,temporary_preview_files_remaining=0)
            finally:
                app.store.close();root.destroy()
    core.atomic_json(output/'verification.json',evidence)
    return evidence


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('settings',type=Path);parser.add_argument('values',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(args.settings,args.values,args.output),ensure_ascii=False,indent=2))
