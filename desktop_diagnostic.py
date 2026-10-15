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


def numeric_plan_check(screen,root,directory,result):
    import tomei_print_font as sample
    if not sample.validated_file():return
    data=core.blank(screen.template)
    # Explicitly synthetic diagnostic inputs; no construction data or defaults.
    data.update(departure_time='09:30',delivery_volume='4.250',cumulative_volume='12.500',
        concrete_type='普通',nominal_strength='24',slump_or_flow='8',max_aggregate_size='25',cement_type='BB',
        cement_1='232',cement_2='-',mineral_admixture='-',water='160',fine_aggregate_1='708',fine_aggregate_2='-',fine_aggregate_3='177',
        coarse_aggregate_1='692',coarse_aggregate_2='297',coarse_aggregate_3='-',coarse_aggregate_4='-',
        chemical_admixture_1='2.090',chemical_admixture_2='-',water_cement_ratio='69.0',water_binder_ratio='-',
        fine_aggregate_ratio='47.7',sludge_solids_ratio='-',recovered_fine_aggregate_ratio='-',
        recovered_coarse_aggregate_ratio='-',sludge_water_method='-',mix_plan_number='12345678')
    assert all(data[key]=='' for key in ('recipient','delivery_place','delivery_date','vehicle_number','remarks'))
    screen.current=None;screen.set_values(data);screen.save()
    screen.input_print_settings.font.set(sample.NUMERIC_LABEL)
    screen.input_print_settings.font_selected();screen.save_settings()
    assert screen.template['input_font_profile']==sample.NUMERIC_PROFILE
    assert screen.template['input_print_style']=='plain'
    for _ in range(3):screen.preview_current();root.update()
    path=directory/'numeric-blend.pdf';core.render_pdf(path,[data],screen.template)
    with pymupdf.open(path) as doc:
        assert doc[0].get_pixmap().samples==screen.preview_view.doc[0].get_pixmap().samples
        spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
        special=[s for s in spans if 'TomeiSample' in s['font']]
        assert special and all(set(s['text'].replace(' ',''))<=sample.NUMERIC_SUPPORTED for s in special)
        assert any('BB' in s['text'] and 'TomeiSample' not in s['font'] for s in spans)
        assert '殿' not in doc[0].get_text()
        assert '配合計画書NO.' in doc[0].get_text()
    opaque=dict(screen.template,input_density=1,input_transparency=0)
    for name,definition in [('numeric-blend-opaque',opaque),('numeric-blend-printer',dict(opaque,input_print_style='printer')),
                            ('numeric-blend-standard',dict(opaque,input_font_profile='',input_print_style='plain'))]:
        path=directory/(name+'.pdf');core.render_pdf(path,[data],definition)
        with pymupdf.open(path) as doc:doc[0].get_pixmap(dpi=220,alpha=False).save(directory/(name+'.png'))
    core.render_pdf(directory/'numeric-all-blank.pdf',[core.blank(opaque)],opaque)
    with pymupdf.open(directory/'numeric-all-blank.pdf') as doc:
        assert '配合計画書' not in doc[0].get_text() and '殿' not in doc[0].get_text()
    multi=copy.deepcopy(opaque);multi['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
    core.render_pdf(directory/'numeric-blend-four-up.pdf',[data]*5,multi)
    with pymupdf.open(directory/'numeric-blend-four-up.pdf') as doc:
        assert [len(page.search_for('納入書（計画）')) for page in doc]==[4,1]
        for page in doc:
            notices=sorted(page.search_for('納入書（計画）'),key=lambda r:(r.y0,r.x0))
            images=sorted(page.get_image_rects(page.get_images()[0][0]),key=lambda r:(r.y0,r.x0))
            assert all(n.y0>i.y1 and page.rect.contains(n) for n,i in zip(notices,images))
        doc[0].get_pixmap(dpi=160,alpha=False).save(directory/'numeric-blend-four-up.png')
    result.update(numeric_font_profile=sample.NUMERIC_PROFILE,numeric_record_id=screen.current['id'],
        numeric_previews=3,numeric_preview_pdf_pixel_difference=0,construction_fields_empty=True,
        all_blank_pdf=True,numeric_four_up=True,nonnumeric_windows_fallback=True,
        mix_plan_label_only_when_value_present=True,numeric_style='plain')


def blue_ink_check(screen,root,directory,result):
    from tomei_preset import public_bundle_files
    files={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in public_bundle_files()}
    before=(screen.template['input_density'],screen.template['input_transparency'])
    values=screen.values()
    for percent in (35,100,150):
        screen.blue_ink_settings.value.set(str(percent));screen.save_settings()
        for _ in range(3):screen.preview_current();root.update()
        name=f'blue-{percent}'
        core.render_pdf(directory/(name+'.pdf'),[values],screen.template)
        with pymupdf.open(directory/(name+'.pdf')) as doc:
            assert doc[0].get_pixmap().samples==screen.preview_view.doc[0].get_pixmap().samples
            doc[0].get_pixmap(dpi=150,alpha=False).save(directory/(name+'.png'))
        opaque=copy.deepcopy(screen.template);opaque.update(input_density=1,input_transparency=0)
        core.render_pdf(directory/(name+'-comparison.pdf'),[values],opaque)
        four=copy.deepcopy(opaque);four['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
        core.render_pdf(directory/(name+'-four-up.pdf'),[values]*5,four)
        with pymupdf.open(directory/(name+'-four-up.pdf')) as doc:
            assert [len(p.search_for('納入書（計画）')) for p in doc]==[4,1]
            for page in doc:
                for box in page.search_for('納入書（計画）'):assert page.rect.contains(box)
    assert (screen.template['input_density'],screen.template['input_transparency'])==before
    assert files=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    result.update(blue_density_previews=9,blue_density_levels=[.35,1,1.5],blue_preview_pdf_pixel_difference=0,
                  blue_four_up=True,blue_source_unchanged=True,black_settings_unchanged_by_blue=True,saved_blue_density=1.5)


def sample_font_check(screen,root,directory,result):
    import tomei_print_font as sample
    asset=sample.validated_file()
    result['sample_font_bundled']=asset is not None
    if asset is None:return
    values=core.blank(screen.template)
    values.update(recipient='検証用宛名 A-2030B',vehicle_number='B-2030A',
                  delivery_volume='-',delivery_date='-',departure_time='-',
                  remarks='確認用サンプル 日本語 ABC 0123456789.-B')
    # Create a separate synthetic record instead of asking to overwrite the
    # earlier diagnostic record; unattended diagnostics must never show dialogs.
    screen.current=None
    screen.set_values(values);screen.save()
    baseline=copy.deepcopy(screen.template)
    baseline.pop('input_font_profile',None)
    core.render_pdf(directory/'sample-standard.pdf',[values],baseline)
    screen.input_print_settings.font.set(sample.LABEL);screen.save_settings()
    assert screen.template['input_font_profile']==sample.PROFILE
    for _ in range(3):screen.preview_current();root.update()
    path=directory/'sample-font.pdf'
    core.render_pdf(path,[values],screen.template)
    with pymupdf.open(path) as doc:
        page=doc[0]
        assert page.get_pixmap().samples==screen.preview_view.doc[0].get_pixmap().samples
        text=page.get_text().replace(' ','').replace('\n','')
        assert '検証用宛名A-2030B殿' in text and 'B-2030A' in text
        spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
        dedicated=[s for s in spans if 'TomeiSample' in s['font']]
        assert dedicated and all(set(s['text'].replace(' ',''))<=sample.SUPPORTED for s in dedicated)
        assert any('日本語' in s['text'] and 'TomeiSample' not in s['font'] for s in spans)
        assert all(s['color']==0x595959 for s in spans if '検証用宛名' in s['text'] or '殿' in s['text'])
        page.get_pixmap(dpi=200,alpha=False).save(directory/'sample-font.png')
        result['pdf_input_fonts']=sorted(set(s['font'] for s in spans))
    multi=copy.deepcopy(screen.template)
    multi['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
    core.render_pdf(directory/'sample-font-four-up.pdf',[values]*5,multi)
    with pymupdf.open(directory/'sample-font-four-up.pdf') as doc:
        assert [len(p.search_for('納入書（計画）')) for p in doc]==[4,1]
        for page in doc:
            images=sorted(page.get_image_rects(page.get_images()[0][0]),key=lambda r:(r.y0,r.x0))
            notices=sorted(page.search_for('納入書（計画）'),key=lambda r:(r.y0,r.x0))
            assert all(n.y0>i.y1 and page.rect.contains(n) for n,i in zip(notices,images))
        doc[0].get_pixmap(dpi=160,alpha=False).save(directory/'sample-font-four-up.png')
    opaque=dict(screen.template,input_density=1,input_transparency=0)
    core.render_pdf(directory/'sample-font-opaque.pdf',[values],opaque)
    core.render_pdf(directory/'sample-standard-opaque.pdf',[values],dict(baseline,input_density=1,input_transparency=0))
    result.update(sample_font_sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),
                  sample_record_id=screen.current['id'],
                  sample_font_previews=3,sample_font_preview_pdf_pixel_difference=0,
                  sample_font_four_up=True,sample_font_profile=sample.PROFILE,
                  sample_supported='0123456789.-B',mixed_text_preserved=True)


def run(destination=None):
    if destination is None:
        with tempfile.TemporaryDirectory(prefix='forgedocuments_diagnostic_') as directory:
            return run(directory)
    output=Path(destination).resolve()
    output.mkdir(parents=True,exist_ok=True)
    evidence={'forms':{},'physical_printing':False,'original_ac_overlay_verified':False}
    try:
        from storage_diagnostic import run as check_automatic_storage
        evidence['automatic_storage']=check_automatic_storage(output/'automatic-storage')
        for row in catalog():
            directory=output/row['id']
            directory.mkdir(exist_ok=True)
            if row['id']=='aktio_receipt':
                from aktio.diagnostics import check_data
                with tempfile.TemporaryDirectory(prefix='aktio-',dir=directory) as work:
                    evidence['forms'][row['id']]=check_data(Path(work)/'checks')
                continue
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
                                recipients=[l['spans'] for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] if '検証用宛名' in ''.join(s['text'] for s in l['spans'])]
                                assert len(recipients)==count
                                assert all(all(s['color']==0 for s in line) and '殿' in ''.join(s['text'] for s in line) for line in recipients)
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
                    sample_font_check(screen,root,directory,result)
                    numeric_plan_check(screen,root,directory,result)
                    blue_ink_check(screen,root,directory,result)
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
                    assert screen.template['blue_ink_density']==result['saved_blue_density']
                    assert screen.blue_ink_settings.value.get()=='150'
                    result['blue_density_survives_reopen']=True
                    assert screen.store.list()[0]['data']['delivery_volume']=='-'
                    screen.set_values(screen.store.list()[0]['data'])
                    result['density_and_hyphens_survive_reopen']=True
                    result['transparency_survives_reopen']=True
                    if result.get('sample_font_bundled'):
                        import tomei_print_font as sample
                        profile=result.get('numeric_font_profile',sample.PROFILE)
                        assert screen.template['input_font_profile']==profile
                        assert screen.input_print_settings.font.get()==sample.PROFILES[profile][0]
                        saved=screen.store.get(result.get('numeric_record_id',result['sample_record_id']))['data']
                        if result.get('numeric_font_profile'):
                            assert all(saved[key]=='' for key in ('recipient','delivery_place','delivery_date','vehicle_number','remarks'))
                            result['numeric_profile_and_empty_construction_survive_reopen']=True
                        else:assert saved['vehicle_number']=='B-2030A'
                        screen.set_values(saved)
                        result['sample_font_survives_reopen']=True
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
