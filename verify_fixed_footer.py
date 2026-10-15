"""Fixed footer behavior and preservation; no claim of original-pixel alignment."""
import copy
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
import pymupdf
import core
from ac_defaults import FORM_ID, migrate_template
from ac_footer import ADDRESS, fixed_address, validate_fixed_footer
from ac_screen import App


class FixedFooterChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=core.load_template()

    def tearDown(self):self.temp.cleanup()

    def test_fixed_literal_above_company_with_matching_horizontal_extent(self):
        address=next(i for i in self.t['fixed_texts'] if i.get('id')=='company_address')
        company=next(i for i in self.t['fixed_texts'] if i.get('id')=='company_name')
        self.assertEqual(address,fixed_address());self.assertNotIn('value_key',address)
        self.assertLessEqual(address['box'][1]+address['box'][3],company['box'][1])
        self.assertEqual(address['box'][0],company['box'][0])
        self.assertLessEqual(abs(address['box'][2]-company['box'][2]),5)
        self.assertFalse(any(f['id']=='company_address' for f in self.t['fields']))
        self.assertFalse(self.t['ac_footer_source']['overlay_verified'])

    def test_random_offsets_leave_footer_pixels_identical_and_keep_one_line(self):
        off=copy.deepcopy(self.t);off['input_print_style']='plain'
        on=copy.deepcopy(off);on.update(random_print_enabled=True,random_print_x_mm=2,random_print_y_mm=2)
        values=core.blank(off);values.update(number='TEST-001',date='2026-10-14')
        paths=[self.path/'off.pdf',self.path/'on.pdf']
        for path,t in zip(paths,(off,on)):core.render_pdf(path,[values],t)
        with pymupdf.open(paths[0]) as a,pymupdf.open(paths[1]) as b:
            lines=[line for block in a[0].get_text('rawdict')['blocks'] if block['type']==0 for line in block['lines']]
            all_chars=[c for line in lines for s in line['spans'] for c in s['chars'] if not c['c'].isspace()]
            anchor=next(c for c in all_chars if c['c']=='愛')
            chars=sorted((c for c in all_chars if abs(c['origin'][1]-anchor['origin'][1])<.01),key=lambda c:c['origin'][0])
            self.assertEqual(len(chars),len(ADDRESS))
            self.assertEqual(''.join(c['c'] for c in chars),ADDRESS)
            self.assertGreater(chars[1]['origin'][0]-chars[0]['origin'][0],anchor['bbox'][2]-anchor['bbox'][0])
            clip=pymupdf.Rect(chars[0]['bbox'])
            for c in chars[1:]:clip|=pymupdf.Rect(c['bbox'])
            clip.y0-=3;clip.y1+=3
            self.assertEqual(a[0].get_pixmap(dpi=200,clip=clip).samples,b[0].get_pixmap(dpi=200,clip=clip).samples)
            self.assertEqual(a[0].get_drawings(),b[0].get_drawings())

    def test_old_generated_geometry_migrates_once_without_changing_records(self):
        old=copy.deepcopy(self.t)
        for key in ('ac_footer_revision','ac_footer_source','ac_previous_footer'):old.pop(key,None)
        address=next(i for i in old['fixed_texts'] if i.get('id')=='company_address')
        address.clear();address.update(id='company_address',value_key='company_address',text='',box=[62,1165,900,46],font=28,align='left',print=True)
        company=next(i for i in old['fixed_texts'] if i.get('id')=='company_name')
        company.update(box=[62,1100,900,60],font=40,align='left')
        s=core.Store(self.path/'records');s.set_template(old);data=core.blank(old);data['number']='KEEP-0001'
        record=s.save(data,old);history=s.history(record['id']);s.close()
        root=tk.Tk();root.withdraw();app=App(root,self.path/'records')
        try:
            self.assertEqual(next(i for i in app.template['fixed_texts'] if i.get('id')=='company_address'),fixed_address())
            self.assertEqual(app.store.get(record['id']),record);self.assertEqual(app.store.history(record['id']),history)
            self.assertEqual(migrate_template(app.template,FORM_ID),app.template)
            self.assertEqual(app.template['ac_previous_footer'][0],address)
        finally:app.store.close();root.destroy()

    def test_ui_has_no_editable_address_and_rejects_fixed_geometry_edits(self):
        root=tk.Tk();root.withdraw();app=App(root,self.path/'gui')
        try:
            self.assertNotIn('company_address',app.vars)
            self.assertNotIn('company_address',app.field_settings.fields)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child;yield from descendants(child)
            self.assertFalse(any(isinstance(w,ttk.Entry) and str(w.cget('textvariable'))==str(app.setting_vars['company_address']) for w in descendants(app.settingtab)))
            app.setting_vars['company_address'].set('MUST NOT APPLY');app.save_settings()
            self.assertEqual(app.setting_vars['company_address'].get(),ADDRESS)
            bad=copy.deepcopy(app.template);next(i for i in bad['fixed_texts'] if i.get('id')=='company_address')['box'][0]+=1
            app.json_edit.delete('1.0','end');app.json_edit.insert('1.0',json.dumps(bad))
            with self.assertRaisesRegex(ValueError,'固定テンプレート'):app.save_settings()
        finally:app.store.close();root.destroy()

    def test_custom_geometry_and_another_form_are_preserved(self):
        custom=copy.deepcopy(self.t)
        for key in ('ac_footer_revision','ac_footer_source','ac_previous_footer'):custom.pop(key,None)
        address=next(i for i in custom['fixed_texts'] if i.get('id')=='company_address')
        address.update(text='岐阜県岐阜市長良1',box=[70,1160,880,45],font=24,print=False)
        custom['company_address']=address['text']
        self.assertEqual(migrate_template(custom,FORM_ID),custom)
        other=copy.deepcopy(custom);other['form_id']='other'
        self.assertEqual(migrate_template(other,FORM_ID),other)
