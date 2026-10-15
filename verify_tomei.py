"""Concrete-form regressions with synthetic input only and no private keys."""
import copy
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import pymupdf
import core
from form_registry import catalog
from main_app import Home
from page_layout import placements
from tomei_screen import App,DEFINITION,EXCLUDED,FIXED,validate_policy
from background_test_support import synthetic_background


class TomeiChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.t=core.load_template(DEFINITION)
        self.t['background']=synthetic_background(self.t)

    def tearDown(self):self.temp.cleanup()

    def sample(self):
        d=core.blank(self.t)
        d.update(delivery_date='2030-01-02',recipient='動作確認用（実績ではありません）',delivery_place='TEST_SITE',vehicle_number='0012',cumulative_truck_count='0002',departure_time='09:21',delivery_volume='005.500',cumulative_volume='010.000',concrete_type='TEST_TYPE',nominal_strength='TEST_STRENGTH',slump_or_flow='TEST_FLOW',max_aggregate_size='TEST_SIZE',cement_type='TEST_CEMENT',water='0170.00',water_cement_ratio='050.00',mix_plan_number='TEST_PLAN_ONLY',remarks='動作確認用・実績ではありません',association_name='TEST_ASSOCIATION')
        return d

    def app(self):
        s=core.Store(self.path/'ui',default_template=self.t,form_id=self.t['form_id'],validate_definition=validate_policy)
        try:s.set_template(self.t)
        finally:s.close()
        root=tk.Tk();root.withdraw();return App(root,self.path/'ui')

    def finish(self,app):app.store.close();app.root.destroy()

    def test_42_source_fields_37_inputs_and_empty_black_defaults(self):
        self.assertEqual(len(self.t['fields']),42);self.assertEqual(len({f['id'] for f in self.t['fields']}),42)
        self.assertEqual(len([f for f in self.t['fields'] if f.get('input',True)]),37)
        self.assertTrue(all(value=='' for value in core.blank(self.t).values()))
        association=next(f for f in self.t['fields'] if f['id']=='association_name')
        self.assertEqual(association['source_bbox_mm'],[4,176.5,110,5])
        self.assertEqual(self.t['source_version'],'1.3');validate_policy(self.t)

    def test_blank_layout_and_blue_configuration_cannot_be_input_or_imported(self):
        s=core.Store(self.path/'data',default_template=self.t,form_id=self.t['form_id'],validate_definition=validate_policy)
        try:
            for key in (*EXCLUDED,*FIXED):
                d=self.sample();d[key]='禁止値'
                self.assertTrue(core.validate(d,self.t))
                with self.assertRaises(ValueError):s.save(d,self.t)
                with self.assertRaises(ValueError):s.import_rows([self.sample(),d],self.t,'invalid import')
                f=next(f for f in self.t['fields'] if f['id']==key);p=self.path/'forbidden.csv'
                with p.open('w',encoding='utf-8-sig',newline='') as file:
                    writer=csv.writer(file);writer.writerow([f['label']]);writer.writerow(['禁止値'])
                with self.assertRaises(ValueError):core.csv_read(p,self.t)
            self.assertEqual(s.list(),[])
        finally:s.close()

    def test_csv_exports_only_input_columns_and_preserves_decimal_strings(self):
        p=self.path/'records.csv';d=self.sample();core.csv_export(p,[{'data':d}],self.t)
        with p.open(encoding='utf-8-sig') as file:
            reader=csv.DictReader(file);headers=reader.fieldnames;self.assertEqual(len(headers),37)
            for key in (*EXCLUDED,*FIXED):self.assertNotIn(next(f['label'] for f in self.t['fields'] if f['id']==key),headers)
        rows=core.csv_read(p,self.t);self.assertEqual(rows[0],d)
        self.assertEqual(rows[0]['delivery_volume'],'005.500');self.assertEqual(rows[0]['vehicle_number'],'0012')

    def test_forbidden_handwriting_never_renders_even_with_record_validation_disabled(self):
        good=self.path/'good.pdf';bad=self.path/'bad.pdf';d=self.sample();core.render_pdf(good,[d],self.t)
        d.update(arrival_time='12:34',recipient_sign_status='FORBIDDEN_RECIPIENT_SIGNATURE',shipping_staff_status='FORBIDDEN_SHIPPING_SIGNATURE')
        with self.assertRaises(ValueError):core.render_pdf(bad,[d],self.t)
        core.render_pdf(bad,[d],self.t,validate_records=False)
        with pymupdf.open(good) as a,pymupdf.open(bad) as b:
            self.assertEqual(a[0].get_pixmap(dpi=100).samples,b[0].get_pixmap(dpi=100).samples)
            for value in ('12:34','FORBIDDEN_RECIPIENT_SIGNATURE','FORBIDDEN_SHIPPING_SIGNATURE'):self.assertNotIn(value,b[0].get_text())
            self.assertEqual(len(b[0].get_images()),1)

    def test_policy_rejects_enabling_excluded_fields_or_hiding_required_notice(self):
        for key in EXCLUDED:
            for change in ({'print':True},{'input':True},{'default':'12:34'},{'fixed_value':'bad'},{'type':'text'}):
                t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']==key).update(change)
                with self.assertRaises(ValueError):validate_policy(t)
        for change in ({'print':False},{'color':[1,1,1]},{'font':0.1},{'value_key':'empty_notice'},{'box':[0,0,1,1]}):
            t=copy.deepcopy(self.t);next(i for i in t['fixed_texts'] if i.get('id')=='copy_notice').update(change)
            with self.assertRaises(ValueError):validate_policy(t)
        t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']=='source_certification_text')['fixed_value']='BG0407016'
        with self.assertRaises(ValueError):validate_policy(t)

    def test_static_blue_input_black_title_and_source_certification_are_visible(self):
        p=self.path/'colors.pdf';core.render_pdf(p,[self.sample()],self.t)
        with pymupdf.open(p) as doc:
            text=doc[0].get_text()
            # Source-only blue typography is never redrawn from template strings.
            for value in ('レディーミクストコンクリート納入書','東名太平洋生コン株式会社','GB0407016','BG0407016'):
                self.assertNotIn(value,text)
            self.assertIn('合成基盤デモ・原票背景未取得',text)
            self.assertIn('納入書（計画）',text);self.assertNotIn('FAX',text)
            spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for line in b['lines'] for s in line['spans']]
            for value in ('TEST_SITE','0012','005.500','TEST_ASSOCIATION'):
                self.assertEqual(next(s['color'] for s in spans if value in s['text']),0)
            self.assertEqual(len(doc[0].get_images()),1)
            from background_assets import load_background
            self.assertIn((75,175,185),list(load_background(self.t).getdata()))

    def test_bad_input_or_fixed_colors_are_rejected(self):
        for key in ('issuer','delivery_volume'):
            t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']==key)['color']=[1,0,0]
            with self.assertRaises(ValueError):validate_policy(t)
        t=copy.deepcopy(self.t);t['line_color']=[0,0,0]
        with self.assertRaises(ValueError):validate_policy(t)

    def test_other_text_and_vectors_cannot_fill_excluded_layout_regions(self):
        for key in EXCLUDED:
            box=next(f for f in self.t['fields'] if f['id']==key)['box']
            t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']=='remarks')['box']=box
            with self.assertRaises(ValueError):validate_policy(t)
            t=copy.deepcopy(self.t);t['fixed_texts'].append({'text':'FORBIDDEN_CONTENT','box':box,'font':14,'print':True})
            with self.assertRaises(ValueError):validate_policy(t)
            x,y,w,h=box;t=copy.deepcopy(self.t);t['lines'].append({'points':[x+w*.2,y+h*.5,x+w*.8,y+h*.5]})
            with self.assertRaises(ValueError):validate_policy(t)
        t=copy.deepcopy(self.t);next(i for i in t['fixed_texts'] if i.get('id')=='recipient_sign_heading')['value_key']='hidden_signature';t['hidden_signature']='FORBIDDEN_CONTENT'
        with self.assertRaises(ValueError):validate_policy(t)

    def test_native_a5_frame_origin_and_external_association(self):
        p=self.path/'native.pdf';core.render_pdf(p,[self.sample()],self.t)
        with pymupdf.open(p) as doc:
            page=doc[0];self.assertAlmostEqual(page.rect.width/core.MM,148,places=3);self.assertAlmostEqual(page.rect.height/core.MM,210,places=3)
            frame=page.get_image_rects(page.get_images()[0][0])[0]
            for actual,expected in ((frame.x0/core.MM,14.4),(frame.y0/core.MM,13.3),(frame.width/core.MM,118.3),(frame.height/core.MM,176.5)):self.assertAlmostEqual(actual,expected,places=3)
            rect=page.search_for('TEST_ASSOCIATION')[0];self.assertGreater(rect.y0,frame.y1);self.assertTrue(page.rect.contains(rect))
            notice=page.search_for('納入書（計画）')[0];self.assertGreater(notice.y0,frame.y1);self.assertTrue(page.rect.contains(notice));self.assertFalse(notice.intersects(rect))

    def test_four_up_includes_footer_extents_and_ends_with_blank_slots(self):
        t=copy.deepcopy(self.t);t['page_layout'].update(paper='A4',rows=2,columns=2,margin_x_mm=5,margin_y_mm=5,gap_x_mm=3,gap_y_mm=4,scale='fit',align_x='center',align_y='center')
        rows=[]
        for i in range(5):d=self.sample();d.update(vehicle_number=f'TEST_CAR_{i}',association_name=f'TEST_ASSOC_{i}');rows.append(d)
        p=self.path/'four-up.pdf';core.render_pdf(p,rows,t)
        with pymupdf.open(p) as doc:
            self.assertEqual(len(doc),2)
            for i in range(4):self.assertIn(f'TEST_CAR_{i}',doc[0].get_text())
            self.assertIn('TEST_CAR_4',doc[1].get_text());self.assertNotIn('TEST_CAR_3',doc[1].get_text())
            for page in doc:
                for b in page.get_text('dict')['blocks']:
                    if b['type']==0:
                        for line in b['lines']:
                            for span in line['spans']:self.assertTrue(page.rect.contains(pymupdf.Rect(span['bbox'])))
            rects=doc[1].get_image_rects(doc[1].get_images()[0][0])
            self.assertEqual(len(rects),1)

    def test_source_choices_are_blue_unselected_and_black_when_checked(self):
        field=next(f for f in self.t['fields'] if f['id']=='mix_basis');key=field['options'][0]['key']
        none=self.path/'none.pdf';selected=self.path/'selected.pdf';d=core.blank(self.t);core.render_pdf(none,[d],self.t)
        d['mix_basis']=json.dumps([key]);core.render_pdf(selected,[d],self.t)
        with pymupdf.open(none) as a,pymupdf.open(selected) as b:
            for option in field['options']:self.assertNotIn(option['label'],a[0].get_text())
            self.assertNotIn(key,b[0].get_text());self.assertNotEqual(a[0].get_pixmap(dpi=100).samples,b[0].get_pixmap(dpi=100).samples)
            self.assertEqual(len([s for s in b[0].get_drawings() if s['color']==(0,0,0)]),2)
        for value in ('["unknown"]',json.dumps([key,key]),'{"standard_mix":true}'):
            d['mix_basis']=value;self.assertTrue(core.validate(d,self.t))

    def test_random_equivalent_choice_arrays_and_excluded_values_do_not_change_pixels(self):
        t=copy.deepcopy(self.t);t['random_print_enabled']=True
        keys=[o['key'] for o in next(f for f in t['fields'] if f['id']=='mix_basis')['options'][:2]]
        a=self.sample();a['mix_basis']=json.dumps(keys)
        b=copy.deepcopy(a);b['mix_basis']=json.dumps(list(reversed(keys)),separators=(',',':'));b['arrival_time']='12:34'
        first=self.path/'first.pdf';second=self.path/'second.pdf';core.render_pdf(first,[a],t);core.render_pdf(second,[b],t,validate_records=False)
        with pymupdf.open(first) as one,pymupdf.open(second) as two:self.assertEqual(one[0].get_pixmap(dpi=100).samples,two[0].get_pixmap(dpi=100).samples)

    def test_gui_has_no_excluded_or_fixed_input_widgets_and_rejects_transcription(self):
        app=self.app()
        try:
            for key in (*EXCLUDED,*FIXED):self.assertNotIn(key,app.vars);self.assertNotIn(key,app.widgets)
            bad=self.sample();bad['arrival_time']='12:34'
            with self.assertRaises(ValueError):app.set_values(bad)
            self.assertTrue(all(value=='' for value in app.values().values()))
        finally:self.finish(app)

    def test_twelve_changed_previews_old_view_open_cancel_and_saved_match(self):
        app=self.app();held=[]
        try:
            for i in range(12):
                d=self.sample();d['vehicle_number']=f'TEST_{i}';app.set_values(d);app.preview_current();app.root.update()
                held.append(app.preview_view.doc)
                self.assertIn(f'TEST_{i}',app.preview_view.doc[0].get_text())
            self.assertTrue(all(doc.is_closed for doc in held[:-1]))
            raster=app.preview_view.doc[0].get_pixmap(dpi=100).samples;app.save();p=self.path/'saved.pdf';core.render_pdf(p,app.store.list(),app.template)
            with pymupdf.open(p) as doc:self.assertEqual(raster,doc[0].get_pixmap(dpi=100).samples)
            with patch('printing.print_pdf',return_value=False):app.output('all','print')
            with patch('definition_screen.filedialog.asksaveasfilename',return_value=''):app.output('all','pdf')
            app.preview_current();self.assertFalse(list((app.store.directory/'preview').glob('*.pdf')))
        finally:self.finish(app)

    def test_settings_keep_custom_defaults_data_and_native_anchor(self):
        app=self.app();d=self.sample();app.set_values(d)
        try:
            app.field_settings.selected.set('コンクリートの種類による記号 [concrete_type]');app.field_settings.select()
            app.field_settings.default.set('TEST_CONFIRMED_TYPE');app.field_settings.suggestions.insert('1.0','TEST_CONFIRMED_TYPE\nTEST_OTHER_CONFIRMED_TYPE')
            app.save_settings();self.assertEqual(app.values(),d)
            self.assertEqual(app.template['page_layout']['align_x'],'start');self.assertEqual(app.template['page_layout']['align_y'],'start')
            app.new(check=False);self.assertEqual(app.values()['concrete_type'],'TEST_CONFIRMED_TYPE');self.assertEqual(app.values()['nominal_strength'],'')
            self.assertEqual(app.widgets['concrete_type'].winfo_class(),'TCombobox')
            t=json.loads(app.json_edit.get('1.0','end'));next(f for f in t['fields'] if f['id']=='arrival_time')['print']=True
            app.json_edit.delete('1.0','end');app.json_edit.insert('1.0',json.dumps(t))
            with self.assertRaises(ValueError):app.save_settings()
            self.assertFalse(next(f for f in app.store.template()['fields'] if f['id']=='arrival_time')['print'])
        finally:self.finish(app)

    def test_second_form_registered_and_ac_store_unchanged(self):
        rows=catalog();self.assertEqual([r['id'] for r in rows],['ac_toyoake','tomei_taiheiyo'])
        ac=self.path/'ac';s=core.Store(ac);s.set_template(core.load_template());s.close();before=(ac/'records.sqlite3').read_bytes()
        concrete=self.path/'concrete';concrete.mkdir();root=tk.Tk();root.withdraw();home=Home(root,{'ac_toyoake':str(ac),'tomei_taiheiyo':str(concrete)},storage_root=self.path/'automatic-install')
        try:
            home.open(rows[1]);root.update();screen=home.screens['tomei_taiheiyo']
            self.assertNotIn('company_address',screen.template);self.assertNotIn('エーシートヨアケ',json.dumps(screen.template,ensure_ascii=False))
            self.assertEqual(screen.template['background']['status'],'ready')
            screen.preview_current();self.assertIn('納入書（計画）',screen.preview_view.doc[0].get_text())
            self.assertEqual((ac/'records.sqlite3').read_bytes(),before)
        finally:home.close()

    def test_wrong_legacy_ac_folder_is_rejected_before_setting_migration(self):
        t=core.load_template();t.pop('form_id',None);t.pop('input_print_style');t['input_color']=[.13,.38,.57]
        s=core.Store(self.path/'legacy');s.set_template(t);s.close();root=tk.Tk();root.withdraw()
        try:
            with self.assertRaises(ValueError):App(root,self.path/'legacy')
        finally:root.destroy()
        with closing(sqlite3.connect(self.path/'legacy/records.sqlite3')) as db:
            rows=db.execute('SELECT after_json FROM settings').fetchall();self.assertEqual(len(rows),1);self.assertEqual(json.loads(rows[0][0]),t)

    def test_all_registered_forms_diagnostic(self):
        from main_app import diagnostic
        with patch('tkinter.simpledialog.askstring',side_effect=AssertionError('Unattended diagnostic must not request edit reasons')):
            diagnostic()


if __name__=='__main__':unittest.main(verbosity=2)
