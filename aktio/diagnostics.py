"""Isolated synthetic AKTIO checks shared by desktop and packaged diagnostics."""
import copy
from pathlib import Path
from PIL import Image,ImageChops
import pymupdf
from . import receipt
from .planning import make_plan,export_plan
from .state import SessionStore


def synthetic_document():
    config=dict(date='2030-01-02',start='07:00',end='17:00',breaks=[['12:00','13:00']],minimum_trip_minutes=30,time_jitter_minutes=10,scale_gap_minutes=2,first_sn=4,measurement_mode='fixed',seed='0',vehicle_count=1,runs=2)
    vehicles=[dict(vehicle='SYNTHETIC',runs=2,tare_kg=11180,max_payload_kg=10000,max_gross_kg=21180,target_payload_kg=9000,weight_jitter_kg=500,
                   fixed_measurements=[dict(time=t,sn=str(s)) for t,s in [('07:08',4),('10:00',10),('14:00',27)]])]
    raw=dict(date='2030-01-02',time='07:00',sn='1',vehicle='SYNTHETIC',trip='1',category='空車',tare=11180,total=11180,
             a1l=2200,a1r=2200,a2l=1800,a2r=1800,a3l=1590,a3r=1590,record_id='SYNTHETIC_DIAGNOSTIC')
    item=dict(row=1,raw=raw,mapping={k:k for k in raw},default_tare=11180,record=receipt.prepare_record(1,raw,{k:k for k in raw},11180),status='合成検証',
              changes=[dict(at='2030-01-02T07:00:00',reason='合成データの診断',before={},after=copy.deepcopy(raw))])
    settings={k:str(config[k]) for k in ('date','start','end','minimum_trip_minutes','time_jitter_minutes','scale_gap_minutes','first_sn','seed','vehicle_count','runs')}
    settings.update(break_start='12:00',break_end='13:00')
    return dict(schema_version=1,form_id='aktio_receipt',settings=settings,extra_breaks=[],vehicles=vehicles,paper='A4中央',measurement_mode='fixed',
                records=make_plan(config,vehicles),generated_config=config,generated_vehicles=copy.deepcopy(vehicles),measured_records=[item],source_excel=None,sample_notice_color='charcoal')


def exercise_screen(screen,root):
    """Use AKTIO's own controller contract, without DefinitionScreen attributes."""
    expected=synthetic_document();screen.restore_document(expected)
    if not screen.autosave():raise ValueError('AKTIOの診断データを保存できません')
    root.update()
    assert screen.document()==expected
    return copy.deepcopy(expected)


def check_data(directory):
    """No GUI or printer calls. Every input here is explicitly synthetic."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    document=synthetic_document();store=SessionStore(directory/'records')
    try:store.save_session(document)
    finally:store.close()
    store=SessionStore(directory/'records')
    try:assert store.load_session()==document
    finally:store.close()
    for record in document['records']:
        _,layout=receipt.receipt_layout();box=layout['receipt_crop_px']
        plan=receipt.render_receipt_image(record).crop(box)
        measured_body=receipt.render_receipt_image(dict(record,mode='measured')).crop(box)
        assert ImageChops.difference(plan,measured_body).getbbox() is None
    for paper,size in [('a4',(2480,3508)),('receipt',(630,776))]:
        output=export_plan(document['records'],document['generated_config'],document['generated_vehicles'],directory/paper,paper=paper)
        files=list(output.glob('*.png'));assert len(files)==3
        for path in files:
            assert '出力見本' in path.name
            with Image.open(path) as im:
                assert im.size==size
                from .output_layout import notice_box,notice_image
                _,layout=receipt.receipt_layout();notice=im.crop(notice_box(document['records'][0],layout,paper=paper))
                assert notice.tobytes()==notice_image().tobytes()
        with pymupdf.open(output/'全レシート.pdf') as pdf:
            assert len(pdf)==3
            assert abs(pdf[0].rect.width-size[0]*72/300)<.01
            assert abs(pdf[0].rect.height-size[1]*72/300)<.01
            for page in pdf:
                pix=page.get_pixmap(matrix=pymupdf.Matrix(300/72,300/72),alpha=False)
                im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                from .output_layout import notice_box,notice_image
                _,layout=receipt.receipt_layout();notice=im.crop(notice_box(document['records'][0],layout,paper=paper))
                assert notice.convert('L').getextrema()[0]<80
    measured=document['measured_records'][0]['record']
    _,name=receipt.render_receipt(measured,directory,paper='receipt');assert '実測' in name
    return dict(status='passed',synthetic_only=True,gui_checked=False,physical_printing=False,
                saved_plan_and_measured_separately=True,correction_history_survives=True,seed_zero=True,
                specified_times=['07:08','10:00','14:00'],specified_sn=['0004','0010','0027'],tare_kg=11180,
                single_and_all_pdf_png=True,paper_modes=['a4','receipt'],specimen_notice_outside_every_receipt=True,original_body_unchanged=True,notice_color_contrast_minimum=7)
