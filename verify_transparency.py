"""Actual input alpha, distinguished from gray ink, with isolated GUI storage."""
import copy
import json
from pathlib import Path
import re
import tempfile
import tkinter as tk
import unittest

from PIL import Image
import pymupdf
import core
from background_assets import encode_background
from tomei_preset import with_bundled_preset
from tomei_screen import App,DEFINITION


class TransparencyChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=with_bundled_preset(core.load_template(DEFINITION))

    def tearDown(self):self.temp.cleanup()

    def raster(self,name,values,template):
        path=self.path/(name+'.pdf');core.render_pdf(path,[values],template)
        with pymupdf.open(path) as doc:return doc[0].get_pixmap(dpi=144,alpha=False).samples

    def test_real_alpha_over_blue_differs_from_gray_and_full_transparency_matches_blank(self):
        t=copy.deepcopy(self.t);t.update(input_print_style='printer',input_density=1)
        next(f for f in t['fields'] if f['id']=='recipient').update(box=[100,150,400,110],font=70,min_font=70)
        t['background']=encode_background(Image.new('RGB',(1018,1417),(0,120,255)),t['width_mm'],t['height_mm'],
            source_sha256='0'*64,kind='synthetic_test',diagnostic_only=True)
        values=core.blank(t);values['recipient']='TEST'
        blank=self.raster('blank',core.blank(t),t)
        opaque=self.raster('opaque',values,t)
        half=self.raster('alpha50',values,dict(t,input_transparency=.5))
        gray=self.raster('gray50',values,dict(t,input_density=.5))
        transparent=self.raster('alpha100',values,dict(t,input_transparency=1))
        self.assertEqual(transparent,blank)
        samples=[i for i in range(0,len(blank),3) if blank[i:i+3]==bytes((0,120,255)) and opaque[i:i+3]==bytes((0,0,0))]
        self.assertGreater(len(samples),20)
        for i in samples[::max(1,len(samples)//20)]:
            self.assertLess(half[i],3);self.assertLess(abs(half[i+1]-60),4);self.assertLess(abs(half[i+2]-127),4)
            self.assertLess(max(gray[i:i+3])-min(gray[i:i+3]),3)
            self.assertNotEqual(half[i:i+3],gray[i:i+3])
        pdf=(self.path/'alpha50.pdf').read_bytes()
        self.assertRegex(pdf,rb'/ca\s+(?:0?\.5)\b');self.assertRegex(pdf,rb'/CA\s+(?:0?\.5)\b')

    def test_alpha_applies_to_all_variable_ink_styles_and_marks_without_leaking_to_fixed_artwork(self):
        for style in ('plain','printer','smooth','impact'):
            t=dict(self.t,input_print_style=style,input_transparency=1)
            values=core.blank(t);values.update(recipient='TEST',delivery_date='-',delivery_volume='-')
            option=next(f for f in t['fields'] if f['id']=='mix_basis')['options'][0]['key']
            values['mix_basis']=json.dumps([option])
            self.assertEqual(self.raster(style+'-ink',values,t),self.raster(style+'-blank',core.blank(t),t))
        t=core.load_template();t.update(input_print_style='printer',input_transparency=1)
        values=core.blank(t);values.update(method='2 P渡',recipient='TEST')
        self.assertEqual(self.raster('ac-transparent',values,t),self.raster('ac-blank',core.blank(t),t))

    def test_gui_alpha_save_reload_and_preview_match_pdf_and_four_up(self):
        directory=self.path/'gui';root=tk.Tk();root.withdraw();app=App(root,directory)
        data=core.blank(app.template);data.update(recipient='サンプル宛名',delivery_volume='-')
        try:
            app.set_values(data);app.save();record=copy.deepcopy(app.current)
            app.input_print_settings.vars['input_transparency'].set('30');app.save_settings()
            self.assertEqual(app.template['input_transparency'],.3)
            for _ in range(3):app.preview_current();root.update()
            pdf=self.path/'saved.pdf';core.render_pdf(pdf,[data],app.template)
            with pymupdf.open(pdf) as doc:
                self.assertEqual(doc[0].get_pixmap().samples,app.preview_view.doc[0].get_pixmap().samples)
            multi=copy.deepcopy(app.template);multi['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
            pdf=self.path/'four-up.pdf';core.render_pdf(pdf,[data]*5,multi)
            with pymupdf.open(pdf) as doc:
                self.assertEqual([len(p.search_for('納入書（計画）')) for p in doc],[4,1])
                self.assertTrue(re.search(rb'/ca\s+(?:0?\.7)\b',pdf.read_bytes()))
            self.assertEqual(app.store.get(record['id']),record)
        finally:app.store.close();root.destroy()
        root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            self.assertEqual(app.template['input_transparency'],.3)
            self.assertEqual(app.input_print_settings.vars['input_transparency'].get(),'30')
            app.set_values(app.store.list()[0]['data']);app.preview_current();self.assertEqual(app.values(),data)
        finally:app.store.close();root.destroy()

    def test_missing_setting_is_opaque_and_existing_settings_are_not_rewritten(self):
        old=copy.deepcopy(self.t);old.pop('input_transparency')
        data=core.blank(old);data['recipient']='TEST'
        self.assertEqual(self.raster('old',data,old),self.raster('zero',data,dict(old,input_transparency=0)))
        store=core.Store(self.path/'legacy',default_template=old);store.set_template(old);store.close()
        root=tk.Tk();root.withdraw();app=App(root,self.path/'legacy')
        try:
            self.assertNotIn('input_transparency',app.template)
            self.assertEqual(app.input_print_settings.vars['input_transparency'].get(),'0')
        finally:app.store.close();root.destroy()

    def test_invalid_transparency_is_rejected(self):
        for value in (-.01,1.01,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):core.validate_template(dict(self.t,input_transparency=value))
