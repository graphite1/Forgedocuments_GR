"""Offline, isolated desktop/PDF checks for the actual packaged runtime."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import tkinter as tk

import pymupdf
from reportlab.pdfbase import pdfmetrics
import core
from form_registry import catalog, open_screen


def run(destination=None):
    if destination is None:
        with tempfile.TemporaryDirectory(prefix='forgedocuments_diagnostic_') as directory:
            return run(directory)
    output=Path(destination).resolve()
    output.mkdir(parents=True,exist_ok=True)
    evidence={'forms':{},'physical_printing':False,'original_ac_overlay_verified':False}
    try:
        for row in catalog():
            directory=output/row['id']
            directory.mkdir(exist_ok=True)
            root=tk.Tk();root.withdraw();screen=None
            try:
                screen=open_screen(row,root,directory/'records')
                t=screen.template
                font=core.font_name(t)
                face=pdfmetrics.getFont(font).face
                result={'font_file':str(face.filename),'ttc_face':0,'previews':0}
                values=core.blank(t)
                if row['id']=='tomei_taiheiyo':
                    values.update(recipient='検証用宛名',vehicle_number='TEST-001',
                                  delivery_date='-',departure_time='-',delivery_volume='-',
                                  remarks='検証用計画・実取引ではありません')
                screen.set_values(values)
                for _ in range(3):
                    screen.preview_current();root.update()
                    assert screen.preview_view.doc is not None
                    result['previews']+=1
                core.render_pdf(directory/'single.pdf',[values],t)
                multi=copy.deepcopy(t)
                multi.setdefault('page_layout',{}).update(paper='A4',rows=2,columns=2,
                    margin_x_mm=5,margin_y_mm=5,gap_x_mm=3,gap_y_mm=4,scale='fit')
                core.render_pdf(directory/'four-up.pdf',[values]*5,multi)
                for name,counts in [('single.pdf',[1]),('four-up.pdf',[4,1])]:
                    with pymupdf.open(directory/name) as doc:
                        assert len(doc)==len(counts)
                        for index,(page,count) in enumerate(zip(doc,counts)):
                            if row['id']=='tomei_taiheiyo':
                                notices=page.search_for('納入書（計画）')
                                assert len(notices)==count
                                images=page.get_image_rects(page.get_images()[0][0])
                                for notice,image in zip(sorted(notices,key=lambda r:(r.y0,r.x0)),sorted(images,key=lambda r:(r.y0,r.x0))):
                                    assert notice.y0>image.y1
                                    assert page.rect.contains(notice)
                                spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                                recipients=[s for s in spans if '検証用宛名' in s['text']]
                                assert len(recipients)==count
                                assert all(s['color']==0 and '殿' in s['text'] for s in recipients)
                            if index==0:page.get_pixmap(dpi=160,alpha=False).save(directory/(Path(name).stem+'.png'))
                    result[name]={'sha256':hashlib.sha256((directory/name).read_bytes()).hexdigest(),'pages':len(counts)}
                if row['id']=='ac_toyoake':
                    on=copy.deepcopy(t);on.update(random_print_enabled=True,random_print_x_mm=2,random_print_y_mm=2)
                    core.render_pdf(directory/'random.pdf',[values],on)
                    with pymupdf.open(directory/'single.pdf') as a,pymupdf.open(directory/'random.pdf') as b:
                        address='愛知県豊明市栄町神田182'
                        assert a[0].search_for(address)==b[0].search_for(address)
                        # Address is widely justified: compare the entire fixed footer.
                        page,slots=core.placements(t);ox,oy,scale=slots[0]
                        fh=t['height_mm']*core.MM
                        clip=pymupdf.Rect(ox,oy+fh*(1-1210/1300),ox+t['width_mm']*core.MM,oy+fh*(1-1080/1300))
                        assert a[0].get_pixmap(clip=clip).samples==b[0].get_pixmap(clip=clip).samples
                    result['fixed_footer_random_pixel_difference']=0
                else:
                    plain=copy.deepcopy(t);plain.update(input_print_style='plain',input_width_scale=1,input_tracking_em=0)
                    core.render_pdf(directory/'plain-reference.pdf',[values],plain)
                    screen.save()
                    record=copy.deepcopy(screen.current)
                    screen.input_print_settings.vars['input_density'].set('65')
                    screen.save_settings()
                    for _ in range(3):screen.preview_current();root.update()
                    result['density_previews']=3
                    core.render_pdf(directory/'density-65.pdf',[values],screen.template)
                    with pymupdf.open(directory/'density-65.pdf') as doc:
                        assert doc[0].get_pixmap().samples==screen.preview_view.doc[0].get_pixmap().samples
                        doc[0].get_pixmap(dpi=200,alpha=False).save(directory/'density-65.png')
                    assert screen.store.get(record['id'])==record
                    result.update(saved_density=.65,density_preview_pdf_pixel_difference=0,hyphens_preserved=True)
                    screen.input_print_settings.vars['input_transparency'].set('30')
                    screen.save_settings()
                    for _ in range(3):screen.preview_current();root.update()
                    core.render_pdf(directory/'transparency-30.pdf',[values],screen.template)
                    with pymupdf.open(directory/'transparency-30.pdf') as doc:
                        assert doc[0].get_pixmap().samples==screen.preview_view.doc[0].get_pixmap().samples
                        doc[0].get_pixmap(dpi=200,alpha=False).save(directory/'transparency-30.png')
                    four=copy.deepcopy(screen.template)
                    four['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
                    core.render_pdf(directory/'transparency-30-four-up.pdf',[values]*5,four)
                    with pymupdf.open(directory/'transparency-30-four-up.pdf') as doc:
                        assert [len(p.search_for('納入書（計画）')) for p in doc]==[4,1]
                    assert screen.store.get(record['id'])==record
                    result.update(saved_transparency=.3,transparency_previews=3,
                                  transparency_preview_pdf_pixel_difference=0,transparency_four_up=True)
                evidence['forms'][row['id']]=result
            finally:
                if screen:screen.store.close()
                root.destroy()
            root=tk.Tk();root.withdraw();screen=None
            try:
                screen=open_screen(row,root,directory/'records')
                if row['id']=='tomei_taiheiyo':
                    assert screen.template['input_density']==.65
                    assert screen.template['input_transparency']==.3
                    assert screen.store.list()[0]['data']['delivery_volume']=='-'
                    screen.set_values(screen.store.list()[0]['data'])
                    result['density_and_hyphens_survive_reopen']=True
                    result['transparency_survives_reopen']=True
                screen.preview_current();root.update()
                assert screen.preview_view.doc is not None
                result['close_and_reopen_preview']=True
            finally:
                if screen:screen.store.close()
                root.destroy()
        evidence['status']='passed'
    except Exception as error:
        evidence.update(status='failed',error=repr(error))
        raise
    finally:
        core.atomic_json(output/'diagnostic.json',evidence)
    return evidence
