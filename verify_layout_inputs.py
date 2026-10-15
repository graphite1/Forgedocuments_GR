"""Shared imposition and per-form field settings regressions."""
import copy
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import pymupdf
import core
from ac_screen import App
from page_layout import defaults, placements
from settings_widgets import FieldDefaultsSettings


class LayoutAndInputs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.t=core.load_template()

    def tearDown(self):self.temp.cleanup()

    def imposed(self,**kwargs):
        t=copy.deepcopy(self.t);t['page_layout']=dict(defaults(t),rows=2,columns=2,scale='fit',margin_x_mm=5,margin_y_mm=5,gap_x_mm=3,gap_y_mm=4)
        t['page_layout'].update(kwargs);return t

    def rows(self,n):
        rows=[]
        for i in range(n):
            d=core.blank(self.t);d.update(number=f'{i+1:06d}',date='2026-10-14',quantity='1.50');rows.append(d)
        return rows

    def test_four_up_order_overflow_and_blank_final_slots(self):
        p=self.path/'four-up.pdf';t=self.imposed();core.render_pdf(p,self.rows(5),t)
        with pymupdf.open(p) as doc:
            self.assertEqual(len(doc),2)
            centers=[]
            for i in range(1,5):centers.append(doc[0].search_for(f'{i:06d}')[0].tl)
            self.assertLess(centers[0].x,centers[1].x);self.assertAlmostEqual(centers[0].y,centers[1].y,places=3)
            self.assertLess(centers[1].y,centers[2].y);self.assertLess(centers[2].x,centers[3].x)
            self.assertIn('000005',doc[1].get_text());self.assertNotIn('000004',doc[1].get_text())
            frames=[i for i in doc[1].get_drawings() if any(item[0]=='re' for item in i['items'])]
            self.assertEqual(len(frames),1)

    def test_actual_four_up_does_not_fit_a4_and_preserves_existing_file(self):
        t=self.imposed(scale='actual');p=self.path/'protected.pdf';p.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'原寸'):core.render_pdf(p,self.rows(4),t)
        self.assertEqual(p.read_bytes(),b'original')

    def test_fit_shrinks_without_upscaling_and_within_margins(self):
        t=self.imposed();paper,slots=placements(t);self.assertEqual(len(slots),4)
        for x,y,scale in slots:
            self.assertLess(scale,1);self.assertGreaterEqual(x,5*core.MM);self.assertGreaterEqual(y,5*core.MM)
            self.assertLessEqual(x+t['width_mm']*scale*core.MM,paper[0]-5*core.MM+.001)
            self.assertLessEqual(y+t['height_mm']*scale*core.MM,paper[1]-5*core.MM+.001)
        t=self.imposed(paper='A3',rows=1,columns=1);self.assertEqual(placements(t)[1][0][2],1)

    def test_landscape_custom_and_original_paper_with_actual_dimensions(self):
        t=self.imposed(paper='A3',orientation='landscape',scale='actual',rows=1);paper,slots=placements(t)
        self.assertEqual(paper,(420*core.MM,297*core.MM));self.assertEqual(slots[0][2],1)
        t=self.imposed(paper='custom',custom_width_mm=320,custom_height_mm=400,scale='actual');self.assertEqual(placements(t)[0],(320*core.MM,400*core.MM))
        t=self.imposed(paper='original',scale='actual');paper,_=placements(t)
        self.assertAlmostEqual(paper[0]/core.MM,2*t['width_mm']+3+10)
        self.assertAlmostEqual(paper[1]/core.MM,2*t['height_mm']+4+10)

    def test_layout_rejects_bad_rows_gaps_and_empty_slots(self):
        for opts in ({'rows':0},{'columns':True},{'rows':1.5},{'margin_x_mm':float('nan')},{'gap_y_mm':-1},{'margin_y_mm':200},{'paper':'bad'}):
            with self.assertRaises(ValueError):core.validate_template(self.imposed(**opts))

    def test_different_form_size_uses_same_imposition_without_ac_content(self):
        t=self.imposed(scale='actual');t.update(form_id='dummy',name='別帳票',width_mm=75,height_mm=95)
        t['fixed_texts']=[{'text':'別帳票','box':[10,10,900,60],'font':28}];p=self.path/'dummy.pdf';core.render_pdf(p,self.rows(4),t)
        with pymupdf.open(p) as doc:
            self.assertEqual(len(doc),1);self.assertNotIn('豊明市',doc[0].get_text())
            frames=[i['rect'] for i in doc[0].get_drawings() if any(item[0]=='re' for item in i['items'])]
            self.assertEqual(len(frames),4)
            for frame in frames:self.assertAlmostEqual(frame.width,75*core.MM,places=3);self.assertAlmostEqual(frame.height,95*core.MM,places=3)

    def test_imposed_random_preview_and_saved_output_are_identical(self):
        t=self.imposed();t.update(random_print_enabled=True,random_print_x_mm=.5,random_print_y_mm=.7)
        s=core.Store(self.path/'records');s.set_template(t);rows=self.rows(5)
        try:
            stored=[s.save(d,t) for d in rows];preview=self.path/'preview.pdf';saved=self.path/'saved.pdf'
            core.render_pdf(preview,rows,t);core.render_pdf(saved,stored,t)
            with pymupdf.open(preview) as a,pymupdf.open(saved) as b:
                for i in range(2):self.assertEqual(a[i].get_pixmap(dpi=100).samples,b[i].get_pixmap(dpi=100).samples)
                for page in a:
                    self.assertAlmostEqual(page.rect.width,210*core.MM,places=3)
        finally:s.close()

    def test_fixed_default_and_candidates_are_independent_per_form(self):
        t=copy.deepcopy(self.t);kind=next(f for f in t['fields'] if f['id']=='kind')
        kind.update(default='材料A',suggestions=['材料A','材料B'],fixed_value='材料B')
        core.validate_template(t);self.assertEqual(core.blank(t)['kind'],'材料B')
        kind.pop('fixed_value');self.assertEqual(core.blank(t)['kind'],'材料A')
        d=core.blank(t);d['kind']='確認済みの候補外';self.assertFalse(core.validate(d,t))
        other=copy.deepcopy(self.t);self.assertEqual(core.blank(other)['kind'],'')

    def test_field_settings_persist_and_existing_actual_records_are_not_rewritten(self):
        s=core.Store(self.path/'store');d=self.rows(1)[0];d['kind']='既存の実績表記';row=s.save(d,self.t)
        t=copy.deepcopy(self.t);kind=next(f for f in t['fields'] if f['id']=='kind');kind.update(default='開始値',fixed_value='新規固定値',suggestions=['開始値','候補'])
        s.set_template(t);s.close();s=core.Store(self.path/'store')
        try:
            self.assertEqual(s.template()['fields'],t['fields']);self.assertEqual(s.get(row['id']),row)
            self.assertEqual(core.blank(s.template())['kind'],'新規固定値')
            self.assertFalse(core.validate(row['data'],t))
        finally:s.close()

    def test_fixed_entry_readonly_but_loaded_historical_value_stays_visible(self):
        t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']=='kind')['fixed_value']='材料A'
        folder=self.path/'gui';s=core.Store(folder);s.set_template(t);s.close();root=tk.Tk();root.withdraw();app=App(root,folder)
        try:
            self.assertEqual(app.values()['kind'],'材料A');self.assertEqual(str(app.widgets['kind'].cget('state')),'readonly')
            actual=self.rows(1)[0];actual['kind']='過去の実績';app.set_values(actual);self.assertEqual(app.values()['kind'],'過去の実績')
        finally:app.store.close();root.destroy()

    def test_candidates_combobox_and_editor_apply_without_fabricating_mixes(self):
        t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']=='kind')['suggestions']=['確認済み材料A','確認済み材料B']
        folder=self.path/'choices';s=core.Store(folder);s.set_template(t);s.close();root=tk.Tk();root.withdraw();app=App(root,folder)
        try:
            self.assertEqual(app.widgets['kind'].winfo_class(),'TCombobox');self.assertEqual(str(app.widgets['kind'].cget('state')),'normal')
            editor=app.field_settings;editor.selected.set('種類 [kind]');editor.select();editor.default.set('確認済み材料B');editor.locked.set(True);editor.fixed.set('確認済み材料A');app.save_settings();app.new(check=False)
            self.assertEqual(app.values()['kind'],'確認済み材料A');self.assertEqual(str(app.widgets['kind'].cget('state')),'disabled')
            self.assertEqual(next(f for f in app.template['fields'] if f['id']=='kind')['suggestions'],['確認済み材料A','確認済み材料B'])
        finally:app.store.close();root.destroy()

    def test_invalid_defaults_fixed_values_and_variable_date_are_rejected(self):
        for fid,change in (('quantity',{'default':'NaN'}),('kind',{'suggestions':[10]}),('kind',{'fixed_value':1}),('date',{'fixed_value':'2026-10-14'})):
            t=copy.deepcopy(self.t);next(f for f in t['fields'] if f['id']==fid).update(change)
            with self.assertRaises(ValueError):core.validate_template(t)

    def test_exact_batch_import_is_atomic_and_unit_totals_are_separate(self):
        from record_batches import summary
        rows=self.rows(3);rows[0].update(quantity='1.50',quantity_unit='m³');rows[1].update(quantity='2.25',quantity_unit='m³');rows[2].update(quantity='2.00',quantity_unit='台')
        s=core.Store(self.path/'batch')
        try:
            stored=s.import_rows(rows,self.t,'実績CSV取込')
            self.assertEqual([r['data'] for r in stored],rows)
            totals=summary(stored,'number','quantity','quantity_unit')
            self.assertEqual(totals['count'],3);self.assertEqual(totals['numbers'],['000001','000002','000003'])
            self.assertEqual(totals['quantity_totals'],{'m³':'3.75','台':'2.00'})
            bad=copy.deepcopy(rows);bad[2]['date']='2026-02-30'
            with self.assertRaises(ValueError):s.import_rows(bad,self.t,'invalid')
            self.assertEqual(len(s.list()),3)
            self.assertTrue(all(len(s.history(r['id']))==1 for r in stored))
        finally:s.close()

    def test_batch_summary_preserves_missing_values_and_duplicate_numbers(self):
        from record_batches import summary
        rows=self.rows(3);rows[1].update(number='000001',quantity='');rows[2].update(quantity_unit='')
        result=summary(rows,'number','quantity','quantity_unit')
        self.assertEqual(result['duplicates'],['000001']);self.assertEqual(result['missing_quantity_count'],1)
        self.assertEqual(rows[1]['quantity'],'');self.assertEqual(result['quantity_totals'],{'':'3.00'})

    def test_dummy_method_and_receipt_ids_have_no_ac_specific_rendering(self):
        t=copy.deepcopy(self.t);t.update(form_id='dummy',name='別帳票')
        t['fixed_texts']=[]
        method=next(f for f in t['fields'] if f['id']=='method');method.pop('choice_marks',None);method.pop('mark_bounds',None);method.update(type='text',box=[100,100,700,60])
        receipt=next(f for f in t['fields'] if f['id']=='receipt_text');receipt.pop('suppressed_by',None)
        d=core.blank(t);d['method']='別帳票の値';p=self.path/'dummy-ids.pdf';core.render_pdf(p,[d],t)
        with pymupdf.open(p) as doc:self.assertIn('別帳票の値',doc[0].get_text())

    def test_linux_build_refuses_before_reading_signing_credentials(self):
        import tools.build_windows as builder
        with patch.object(builder.sys,'platform','linux'),patch.object(builder,'prepare_key') as prepare:
            with self.assertRaisesRegex(RuntimeError,'Windows'):builder.build(self.path/'build')
            prepare.assert_not_called();self.assertFalse((self.path/'build').exists())

    def test_new_dummy_store_uses_its_own_defaults_and_rejects_ac_settings(self):
        t=copy.deepcopy(self.t);t['form_id']='dummy';t['name']='別帳票';t['fixed_texts']=[{'text':'別帳票の原本固有文','box':[20,20,900,60],'font':28}]
        for k in ('company_name','company_address','company_contact','ac_defaults_version'):t.pop(k,None)
        with self.assertRaises(ValueError):core.Store(self.path/'missing',form_id='dummy')
        s=core.Store(self.path/'own',default_template=t,form_id='dummy')
        try:
            self.assertEqual(s.template(),t)
            with self.assertRaises(ValueError):s.set_template(self.t)
            self.assertNotIn('company_address',s.template())
        finally:s.close()

    def test_form_owned_colors_and_excluded_handwritten_fields_in_preview_and_saved(self):
        from PIL import Image
        t=copy.deepcopy(self.t);t.update(form_id='dummy',input_color=[0,0,0],input_print_style='smooth')
        t['fixed_texts']=[{'text':'固定文字','box':[20,20,900,60],'font':28}]
        for f in t['fields']:
            if f['id'] in ('arrival','receipt_image','receipt_text'):f['print']=False
        image=self.path/'handwritten.png';Image.new('RGB',(50,20),'black').save(image)
        d=core.blank(t);d.update(number='000001-A',arrival='09:45',receipt_text='手書き署名',receipt_image=core.image_encode(image))
        for name,rows in (('preview',[d]),('saved',[{'data':d}])):
            p=self.path/(name+'.pdf');core.render_pdf(p,rows,t)
            with pymupdf.open(p) as doc:
                text=doc[0].get_text();self.assertIn('000001-A',text);self.assertNotIn('09',text);self.assertNotIn('45',text);self.assertNotIn('手書き署名',text)
                self.assertEqual(doc[0].get_images(),[])
                spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for line in b['lines'] for s in line['spans']]
                self.assertEqual(next(s['color'] for s in spans if '000001-A' in s['text']),0)
                self.assertNotEqual(next(s['color'] for s in spans if '固定文字' in s['text']),0)


if __name__=='__main__':unittest.main(verbosity=2)
