"""Source-pixel composition checks; all assets here are explicit test fixtures."""
import base64
import copy
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import tkinter as tk
from unittest.mock import patch
from PIL import Image,ImageDraw
import pymupdf
import core
from background_assets import load_background,encode_background
from background_test_support import synthetic_background
from blue_background import blue_pixels,estimate_rotation,extract_background
from input_coordinates import apply_coordinates
from tomei_defaults import migrate_background
from tomei_screen import App,DEFINITION,validate_policy


class BackgroundChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=core.load_template(DEFINITION)
        # Exercise legacy missing/draft behavior independently of the new bundle.
        self.bundle_patch=patch('tomei_preset.bundled_source',return_value=None);self.bundle_patch.start()

    def tearDown(self):self.bundle_patch.stop();self.temp.cleanup()

    def ready(self):
        t=copy.deepcopy(self.t);t['background']=synthetic_background(t);return t

    def test_missing_source_blocks_output_but_not_settings_csv_and_records(self):
        target=self.path/'existing.pdf';target.write_bytes(b'previous output')
        with self.assertRaisesRegex(ValueError,'背景画像が未準備'):core.render_pdf(target,[core.blank(self.t)],self.t)
        self.assertEqual(target.read_bytes(),b'previous output');self.assertFalse(list(self.path.glob('*.tmp')))
        s=core.Store(self.path/'store',default_template=self.t,form_id=self.t['form_id'],validate_definition=validate_policy)
        try:
            s.set_template(self.t);d=core.blank(self.t);d.update(delivery_volume='005.500')
            r=s.save(d,self.t);core.csv_export(self.path/'records.csv',[r],self.t)
            self.assertEqual(core.csv_read(self.path/'records.csv',self.t)[0],d)
            self.assertEqual(s.get(r['id'])['data'],d)
        finally:s.close()

    def test_blue_filter_retains_existing_hue_and_removes_black_red_and_grey(self):
        image=Image.new('RGB',(5,1));source=[(70,170,180),(225,240,243),(0,0,0),(220,20,30),(170,170,170)]
        image.putdata(source);pixels=list(blue_pixels(image).getdata())
        self.assertEqual(pixels[:2],source[:2]);self.assertEqual(pixels[2:],[(255,255,255)]*3)

    def test_saturated_source_blue_keeps_filled_glyphs_instead_of_only_edges(self):
        image=Image.new('RGB',(4,1))
        source=[(0,120,255),(0,70,230),(70,170,180),(220,20,220)]
        image.putdata(source)
        self.assertEqual(list(blue_pixels(image).getdata()),source[:3]+[(255,255,255)])

    def test_explicit_image_profile_preserves_legacy_and_protects_real_blank_cells(self):
        from tomei_profiles import image_profile
        before=copy.deepcopy(self.t)
        t=image_profile(self.t);validate_policy(t)
        self.assertEqual(self.t,before)
        self.assertEqual(core.blank(t),core.blank(before))
        self.assertAlmostEqual(t['coordinate_width']/t['coordinate_height'],t['width_mm']/t['height_mm'])
        t['background']=encode_background(Image.new('RGB',(1018,1417),(0,120,255)),t['width_mm'],t['height_mm'],source_sha256='0'*64,reviewed=True,kind='corrected_blue')
        loaded=load_background(t)
        for point in [(750-26,535-33),(960-26,535-33),(400-26,1370-33),(900-26,1370-33)]:
            self.assertEqual(loaded.getpixel(point),(255,255,255))
        for point in [(907-26,535-33),(1015-26,535-33),(80-26,1370-33)]:
            self.assertEqual(loaded.getpixel(point),(0,120,255))
        bad=copy.deepcopy(t);bad['background']['reviewed']=False
        with self.assertRaisesRegex(ValueError,'確認'):load_background(bad)
        bad=copy.deepcopy(t);bad['height_mm']+=1
        with self.assertRaisesRegex(ValueError,'縦横比'):validate_policy(bad)
        next(f for f in t['fields'] if f['id']=='vehicle_number')['box']=[300,1310,30,20]
        with self.assertRaisesRegex(ValueError,'空欄'):validate_policy(t)

    def test_crop_removes_annotation_and_does_not_fill_missing_blue_ink(self):
        image=Image.new('RGB',(1303,1805),'white');draw=ImageDraw.Draw(image)
        draw.line((30,30,1212,30),fill=(60,170,180),width=3)
        draw.text((1200,10),'ANNOTATION',fill='black');draw.rectangle((100,30,120,32),fill='white')
        path=self.path/'source.png';image.save(path)
        config=extract_background(path,[30,30,1213,1795],118.3,176.5,reviewed=False)
        t=copy.deepcopy(self.t);t['background']=config
        with self.assertRaisesRegex(ValueError,'確認'):load_background(t)
        raw=base64.b64decode(config['image_png_base64'])
        with Image.open(io.BytesIO(raw)) as result:
            self.assertEqual(result.size,(1183,1765));self.assertEqual(result.getpixel((80,0)),(255,255,255))
            self.assertEqual(result.getpixel((10,0)),(60,170,180))
        self.assertFalse(config['processing']['missing_ink_synthesized'])
        self.assertEqual(config['source_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_rotation_suggestion_is_never_applied_without_review(self):
        image=Image.new('RGB',(600,900),'white');draw=ImageDraw.Draw(image)
        for y in range(100,800,100):draw.line((20,y,580,y),fill=(70,180,185),width=3)
        rotated=image.rotate(1.2,resample=Image.Resampling.BICUBIC,fillcolor='white')
        result=estimate_rotation(rotated)
        self.assertAlmostEqual(result['suggested_degrees'],-1.2,delta=.25)
        self.assertFalse(result['automatic_application'])

    def test_corrupted_hash_unreviewed_source_and_bad_aspect_are_rejected(self):
        t=self.ready();t['background']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ハッシュ'):load_background(t)
        t=self.ready();t['background'].update(kind='original_blue',reviewed=False)
        with self.assertRaisesRegex(ValueError,'確認'):load_background(t)
        t=self.ready();t['background']=encode_background(Image.new('RGB',(300,300),'white'),118.3,176.5,source_sha256='0'*64,kind='synthetic_test',diagnostic_only=True)
        with self.assertRaisesRegex(ValueError,'縦横比'):load_background(t)

    def test_blue_marks_in_signature_and_arrival_value_areas_are_matted_each_render(self):
        image=Image.new('RGB',(1183,1765),(60,170,180))
        t=self.ready();t['background']=encode_background(image,118.3,176.5,source_sha256='0'*64,kind='synthetic_test',diagnostic_only=True)
        loaded=load_background(t)
        for x,y in ((80,65),(105,65),(45,174),(105,174)):
            self.assertEqual(loaded.getpixel((x*10,y*10)),(255,255,255))
        # Fixed blue unit slots and signature headings survive independently.
        self.assertEqual(loaded.getpixel((945,650)),(60,170,180))
        self.assertEqual(loaded.getpixel((100,1740)),(60,170,180))
        self.assertEqual(loaded.getpixel((0,1740)),(60,170,180))
        bad=copy.deepcopy(t);bad['background_blank_regions_mm']=[]
        with self.assertRaisesRegex(ValueError,'空欄'):validate_policy(bad)
        bad=copy.deepcopy(t);bad['overlay_fixed_text_ids'].append('original_title')
        with self.assertRaisesRegex(ValueError,'描き直'):validate_policy(bad)

    def test_coordinates_compile_mm_without_changing_values_or_fixed_fields(self):
        coord=json.loads((DEFINITION.parent/'tomei_taiheiyo.coordinates.json').read_text(encoding='utf-8'))
        raw=json.loads(DEFINITION.read_text(encoding='utf-8'));compiled=apply_coordinates(raw,coord)
        date=next(f for f in compiled['fields'] if f['id']=='delivery_date')
        self.assertEqual(len(date['parts']),3)
        self.assertAlmostEqual(date['parts'][0][0]*compiled['width_mm']/compiled['coordinate_width'],78)
        with self.assertRaises(ValueError):apply_coordinates(raw,{'schema_version':1,'unit':'mm','fields':[{'id':'arrival_time','box_mm':[1,1,2,2]}]})
        broken=copy.deepcopy(coord);broken['fields'][0]['input']=True
        with self.assertRaises(ValueError):apply_coordinates(raw,broken)
        self.assertEqual(core.blank(compiled),core.blank(raw))

    def test_legacy_upgrade_preserves_custom_geometry_values_and_record_history(self):
        old=copy.deepcopy(self.t)
        for key in ('background','render_mode','background_revision','overlay_fixed_text_ids','background_blank_regions_mm','document_purpose','plan_revision'):old.pop(key,None)
        next(i for i in old['fixed_texts'] if i.get('id')=='copy_notice')['text']='再生成'
        field=next(f for f in old['fields'] if f['id']=='delivery_place');field['default']='USER CUSTOM';field['box'][0]+=3;field['box'][2]-=3
        s=core.Store(self.path/'store',default_template=old);s.set_template(old)
        data=core.blank(old);data['delivery_volume']='007.250';record=s.save(data,old);history=s.history(record['id']);s.close()
        before=copy.deepcopy(old)
        s=core.Store(self.path/'store',default_template=self.t,form_id=self.t['form_id'],validate_definition=validate_policy,migrate_definition=lambda t:migrate_background(t,self.t))
        try:
            updated=s.template();self.assertEqual(updated['fields'],before['fields'])
            self.assertEqual(s.get(record['id'])['data'],data);self.assertEqual(s.history(record['id']),history)
            self.assertEqual(updated['background']['status'],'missing');self.assertEqual(updated['render_mode'],'background')
            self.assertEqual(updated['document_purpose'],'delivery_plan')
            self.assertEqual(updated['previous_identity_notice']['text'],'再生成')
            self.assertEqual(s.template(),updated)
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM settings').fetchone()[0],2)
            backup=self.path/'backup.sqlite3';s.backup(backup,updated)
            with closing(sqlite3.connect(backup)) as db:self.assertEqual(json.loads(db.execute('SELECT after_json FROM settings ORDER BY seq DESC LIMIT 1').fetchone()[0]),updated)
        finally:s.close()
        self.assertEqual(old,before)

    def test_gui_select_save_review_and_overlay_preserve_source_and_record_history(self):
        image=Image.new('RGB',(1183,1765),'white');draw=ImageDraw.Draw(image)
        draw.rectangle((0,0,1182,1764),outline=(60,170,180),width=2);draw.text((30,30),'TEST SOURCE',fill=(60,170,180))
        source=self.path/'test-background.png';image.save(source);before=source.read_bytes()
        root=tk.Tk();root.withdraw();app=App(root,self.path/'gui')
        try:
            data=core.blank(app.template);data.update(recipient='TEST PLAN ONLY',delivery_volume='005.500')
            app.set_values(data);app.save();history=app.store.history(app.current['id'])
            app.background_settings.select_source(source);app.save_settings()
            self.assertEqual(app.template['background']['status'],'draft');self.assertEqual(app.values(),data)
            with self.assertRaisesRegex(ValueError,'未確認'):app.preview_current()
            app.background_settings.reviewed.set(True)
            with self.assertRaisesRegex(ValueError,'未解決の誤字'):app.save_settings()
            # This test source is an artificial fixture and has no provided-image typos.
            app.background_settings.errors.delete('1.0','end');app.save_settings();app.preview_current()
            self.assertEqual(app.template['background']['status'],'ready')
            self.assertIn('納入書（計画）',app.preview_view.doc[0].get_text())
            self.assertIn('005.500',app.preview_view.doc[0].get_text());self.assertEqual(len(app.preview_view.doc[0].get_images()),1)
            self.assertEqual(app.store.history(app.current['id']),history)
            self.assertEqual(source.read_bytes(),before)
            backup=self.path/'with-asset.sqlite3';app.store.backup(backup,app.template)
            with closing(sqlite3.connect(backup)) as db:
                saved=json.loads(db.execute('SELECT after_json FROM settings ORDER BY seq DESC LIMIT 1').fetchone()[0])
                self.assertEqual(saved['background']['sha256'],app.template['background']['sha256'])
                self.assertEqual(saved['background']['image_png_base64'],app.template['background']['image_png_base64'])
        finally:app.store.close();root.destroy()

    def test_known_background_typos_block_confirmed_output_and_draft_is_storable(self):
        t=self.ready();t['background'].update(kind='original_blue',reviewed=False,status='draft',unresolved_text_errors=['470-0163 → 470-0162','配合種別の車体量'])
        core.validate_template(t)
        with self.assertRaisesRegex(ValueError,'未確認'):load_background(t)
        t['background'].update(reviewed=True,status='ready')
        with self.assertRaisesRegex(ValueError,'未解決の誤字'):load_background(t)
        t['background']['unresolved_text_errors']=[]
        self.assertIsNotNone(load_background(t))

    def test_recognized_image_selection_applies_profile_and_original_typos_stay_blocked(self):
        from tomei_preset import apply_preset,recognize
        source=self.path/'fixture.png';Image.new('RGB',(1070,1470),'white').save(source)
        digest=hashlib.sha256(source.read_bytes()).hexdigest();before=source.read_bytes()
        with patch('tomei_preset.CORRECTED_SHA256',digest):
            root=tk.Tk();root.withdraw();app=App(root,self.path/'preset-gui')
            try:
                app.background_settings.select_source(source);app.save_settings()
                self.assertEqual(app.template['layout_profile'],'generated-20261014')
                self.assertEqual(app.template['background']['status'],'draft')
                self.assertEqual(app.template['coordinate_width'],1018)
                app.background_settings.reviewed.set(True);app.save_settings();app.preview_current()
                self.assertEqual(app.template['background']['status'],'ready')
                self.assertEqual(app.template['background']['kind'],'corrected_blue')
            finally:app.store.close();root.destroy()
        with patch('tomei_preset.ORIGINAL_SHA256',digest):
            t=apply_preset(self.t,source,reviewed=True,errors=[])
            with self.assertRaisesRegex(ValueError,'未解決の誤字'):load_background(t)
        self.assertEqual(source.read_bytes(),before)
        self.assertIsNone(recognize(source))

    def test_private_bundle_initializes_new_store_but_preserves_existing_settings(self):
        source=self.path/'fixture.png';Image.new('RGB',(1070,1470),'white').save(source)
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        old=copy.deepcopy(self.t);next(f for f in old['fields'] if f['id']=='recipient')['default']='KEEP-CUSTOM'
        store=core.Store(self.path/'existing',default_template=old);store.set_template(old);store.close()
        with patch('tomei_preset.CORRECTED_SHA256',digest),patch('tomei_preset.bundled_source',return_value=source):
            for name in ('new','existing'):
                root=tk.Tk();root.withdraw();app=App(root,self.path/name)
                try:
                    if name=='new':
                        self.assertEqual(app.template['background']['status'],'ready');app.preview_current()
                    else:self.assertEqual(app.template,old)
                finally:app.store.close();root.destroy()

    def test_bitmap_and_notice_repeat_for_each_imposition_slot(self):
        t=self.ready();t['page_layout'].update(paper='A4',rows=2,columns=2,margin_x_mm=5,margin_y_mm=5,gap_x_mm=3,gap_y_mm=4,scale='fit')
        target=self.path/'many.pdf';data=core.blank(t);data['vehicle_number']='TEST_CAR'
        core.render_pdf(target,[data]*5,t)
        with pymupdf.open(target) as doc:
            self.assertEqual(len(doc),2)
            self.assertEqual(len(doc[0].get_image_rects(doc[0].get_images()[0][0])),4)
            self.assertEqual(len(doc[1].get_image_rects(doc[1].get_images()[0][0])),1)
            self.assertEqual(len(doc[0].search_for('納入書（計画）')),4)
            self.assertEqual(len(doc[1].search_for('納入書（計画）')),1)
            self.assertEqual(doc[0].get_drawings(),[])
