"""Numeric-first private printing and optional construction information."""
import copy
from pathlib import Path
import tempfile
import tkinter as tk
import unicodedata
import unittest

import pymupdf
import core
from tomei_preset import with_bundled_preset
from tomei_screen import App,DEFINITION
import tomei_print_font as sample


def blend_values(template):
    values=core.blank(template)
    values.update(departure_time='09:30',delivery_volume='4.250',cumulative_volume='12.500',
        concrete_type='普通',nominal_strength='24',slump_or_flow='8',max_aggregate_size='25',cement_type='BB',
        cement_1='232',cement_2='-',mineral_admixture='-',water='160',fine_aggregate_1='708',fine_aggregate_2='-',fine_aggregate_3='177',
        coarse_aggregate_1='692',coarse_aggregate_2='297',coarse_aggregate_3='-',coarse_aggregate_4='-',
        chemical_admixture_1='2.090',chemical_admixture_2='-',water_cement_ratio='69.0',water_binder_ratio='-',
        fine_aggregate_ratio='47.7',sludge_solids_ratio='-',recovered_fine_aggregate_ratio='-',
        recovered_coarse_aggregate_ratio='-',sludge_water_method='-',mix_plan_number='12345678')
    return values


class NumericPlanChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=with_bundled_preset(core.load_template(DEFINITION))

    def tearDown(self):self.temp.cleanup()

    def test_all_blank_and_blend_only_output_preserve_empty_construction(self):
        values=blend_values(self.t)
        for key in ('recipient','delivery_place','delivery_date','vehicle_number','remarks'):
            self.assertEqual(values[key],'')
        self.assertFalse(core.validate(values,self.t));self.assertFalse(core.validate(core.blank(self.t),self.t))
        store=core.Store(self.path/'store',default_template=self.t)
        try:
            record=store.save(values,self.t);self.assertEqual(store.get(record['id'])['data'],values)
        finally:store.close()
        for data,name in [(values,'blend'),(core.blank(self.t),'blank')]:
            path=self.path/(name+'.pdf');core.render_pdf(path,[data],self.t)
            with pymupdf.open(path) as doc:
                text=doc[0].get_text()
                self.assertIn('納入書（計画）',text)
                self.assertNotIn('殿',text)
                if name=='blend':self.assertIn('配合計画書NO. 12345678',text)
                else:self.assertNotIn('配合計画書',text)
        multi=copy.deepcopy(self.t);multi['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
        path=self.path/'four.pdf';core.render_pdf(path,[values]*5,multi)
        with pymupdf.open(path) as doc:self.assertEqual([len(p.search_for('納入書（計画）')) for p in doc],[4,1])

    def test_plan_prefix_only_for_nonempty_values_and_never_duplicated(self):
        for value in ('','-','12345678','配合計画書NO. 12345678','配合計画書ＮＯ．12345678'):
            data=core.blank(self.t);data['mix_plan_number']=value
            path=self.path/(str(len(value))+'.pdf');core.render_pdf(path,[data],self.t)
            with pymupdf.open(path) as doc:
                text=unicodedata.normalize('NFKC',doc[0].get_text()).casefold()
                self.assertEqual(text.count('配合計画書no.'),0 if value in ('','-') else 1)
            self.assertEqual(data['mix_plan_number'],value)

    @unittest.skipUnless(sample.font_file().is_file(),'Private font deliberately not distributed with public source')
    def test_numeric_profile_gui_plain_default_fallback_preview_and_reopen(self):
        directory=self.path/'gui';root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            values=blend_values(app.template);app.set_values(values);app.save();record=copy.deepcopy(app.current)
            app.input_print_settings.font.set(sample.NUMERIC_LABEL)
            app.input_print_settings.font_selected();app.save_settings()
            self.assertEqual(app.template['input_font_profile'],sample.NUMERIC_PROFILE)
            self.assertEqual(app.template['input_print_style'],'plain')
            font=sample.input_font(app.template,core.font_name(app.template))
            self.assertEqual(font.supported,frozenset('0123456789.-'))
            self.assertTrue(all(name==font.fallback for name,text in font.runs('BB配合計画書NO:')))
            for _ in range(3):app.preview_current();root.update()
            path=self.path/'numeric.pdf';core.render_pdf(path,[values],app.template)
            with pymupdf.open(path) as doc:
                self.assertEqual(doc[0].get_pixmap().samples,app.preview_view.doc[0].get_pixmap().samples)
                spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                dedicated=[s for s in spans if 'TomeiSample' in s['font']]
                self.assertTrue(dedicated)
                self.assertTrue(all(set(s['text'].replace(' ',''))<=sample.NUMERIC_SUPPORTED for s in dedicated))
                self.assertTrue(any('BB' in s['text'] and 'TomeiSample' not in s['font'] for s in spans))
            self.assertEqual(app.store.get(record['id']),record)
        finally:app.store.close();root.destroy()
        root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            self.assertEqual(app.template['input_font_profile'],sample.NUMERIC_PROFILE)
            self.assertEqual(app.input_print_settings.font.get(),sample.NUMERIC_LABEL)
            data=app.store.list()[0]['data'];self.assertEqual(data,values)
            app.set_values(data);app.preview_current()
        finally:app.store.close();root.destroy()
