"""Metrics and private sample-font integration; no scanned source fixtures."""
import copy
import io
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import pymupdf
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
import core
from input_fonts import InputFont,string_width,draw_text
import tomei_print_font as sample
from tomei_preset import with_bundled_preset
from tomei_screen import App,DEFINITION


class FontRunChecks(unittest.TestCase):
    def test_exact_coverage_and_tracking_across_boundaries(self):
        font=InputFont('Helvetica','Courier',frozenset('0123456789.-B'))
        value='A12B漢/ :9'
        self.assertEqual(font.runs(value),[('Helvetica','A'),('Courier','12B'),('Helvetica','漢/ :'),('Courier','9')])
        expected=sum(pdfmetrics.stringWidth(ch,'Courier' if ch in font.supported else 'Helvetica',20) for ch in value)
        self.assertAlmostEqual(string_width(value,font,20),expected)
        size,lines=core.fit_text('A12B',font,20,200,30,tracking_em=.02)
        self.assertEqual((size,lines),(20,['A12B']))
        data=io.BytesIO();c=canvas.Canvas(data)
        draw_text(c,font,'A12BA',20,tracking=2,x=10,y=100);c.save()
        with pymupdf.open(stream=data.getvalue(),filetype='pdf') as doc:
            chars=[ch for b in doc[0].get_text('rawdict')['blocks'] for l in b.get('lines',[]) for s in l['spans'] for ch in s['chars'] if ch['c']!=' ']
            self.assertEqual(''.join(ch['c'] for ch in chars),'A12BA')
            x=10
            for ch in chars:
                self.assertAlmostEqual(ch['origin'][0],x,places=3)
                x+=string_width(ch['c'],font,20)+2


@unittest.skipUnless(sample.font_file().is_file(),'Private font is deliberately absent from public source distributions')
class SampleFontChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=with_bundled_preset(core.load_template(DEFINITION))

    def tearDown(self):self.temp.cleanup()

    def test_supported_glyphs_and_explicit_missing_asset_error(self):
        fallback=core.font_name(self.t)
        font=sample.input_font(dict(self.t,input_font_profile=sample.PROFILE),fallback)
        self.assertEqual(font.supported,frozenset('0123456789.-B'))
        self.assertEqual(font.runs('A漢/ :'),[(fallback,'A漢/ :')])
        with patch('tomei_print_font.validated_file',return_value=None):
            with self.assertRaisesRegex(ValueError,'同梱'):sample.input_font(dict(self.t,input_font_profile=sample.PROFILE),fallback)
        self.assertEqual(sample.input_font(self.t,fallback),fallback)
        self.assertEqual(sample.input_font(dict(core.load_template(),input_font_profile=sample.PROFILE),fallback),fallback)

    def test_mixed_fonts_all_styles_preserve_alpha_and_fixed_artwork(self):
        values=core.blank(self.t);values.update(recipient='確認用 A-2030B',vehicle_number='B-2030A',delivery_volume='-',delivery_date='-')
        for style in ('plain','printer','smooth','impact'):
            t=dict(self.t,input_font_profile=sample.PROFILE,input_print_style=style)
            path=self.path/(style+'.pdf');core.render_pdf(path,[values],t)
            with pymupdf.open(path) as doc:
                text=doc[0].get_text().replace(' ','').replace('\n','')
                self.assertIn('確認用A-2030B殿',text)
                self.assertIn('B-2030A',text)
                fonts=[s['font'] for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                self.assertTrue(any('TomeiSample' in f for f in fonts))
                self.assertTrue(any('Gothic' in f or 'Meiryo' in f for f in fonts))
            transparent=self.path/(style+'-transparent.pdf');blank=self.path/(style+'-blank.pdf')
            core.render_pdf(transparent,[values],dict(t,input_transparency=1))
            core.render_pdf(blank,[core.blank(t)],t)
            with pymupdf.open(transparent) as a,pymupdf.open(blank) as b:
                self.assertEqual(a[0].get_pixmap().samples,b[0].get_pixmap().samples)

    def test_gui_selection_keeps_fallback_settings_and_survives_reopen(self):
        directory=self.path/'gui';root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            settings=app.input_print_settings
            old=copy.deepcopy(app.template)
            settings.font.set(sample.LABEL);app.save_settings()
            self.assertEqual(app.template['input_font_profile'],sample.PROFILE)
            self.assertEqual(app.template.get('input_font_path',''),old.get('input_font_path',''))
            data=core.blank(app.template);data.update(recipient='確認用 A-2030B',delivery_volume='-')
            app.set_values(data);app.save()
            for _ in range(3):app.preview_current();root.update()
        finally:app.store.close();root.destroy()
        root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            self.assertEqual(app.input_print_settings.font.get(),sample.LABEL)
            self.assertEqual(app.store.list()[0]['data'],data)
            app.set_values(data);app.preview_current()
            standard=next(label for label,value in app.input_print_settings.fonts.items() if value=='')
            app.input_print_settings.font.set(standard);app.save_settings()
            self.assertNotIn('input_font_profile',app.template)
            self.assertEqual(app.values(),data)
        finally:app.store.close();root.destroy()
