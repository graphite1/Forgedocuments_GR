"""Blue artwork density, independent input ink and persisted GUI previews."""
import copy,hashlib,tempfile,tkinter as tk,unittest
from pathlib import Path
from PIL import Image
import pymupdf
import blue_ink,core
from tomei_preset import with_bundled_preset,public_bundle_files
from tomei_screen import App,DEFINITION


class BlueInkChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=with_bundled_preset(core.load_template(DEFINITION))

    def tearDown(self):self.temp.cleanup()

    def test_density_validation_and_source_pixels_preserved(self):
        source=Image.new('RGB',(4,1));source.putdata([(0,128,255),(0,0,0),(160,160,160),(255,255,255)])
        original=source.tobytes();light=blue_ink.image(source,.35);dark=blue_ink.image(source,1.5)
        self.assertEqual(source.tobytes(),original);self.assertIs(blue_ink.image(source,1),source)
        self.assertGreater(light.getpixel((0,0))[0],source.getpixel((0,0))[0])
        self.assertLess(dark.getpixel((0,0))[1],source.getpixel((0,0))[1])
        for x in (1,2,3):self.assertEqual(light.getpixel((x,0)),source.getpixel((x,0)))
        for value in (0,.34,1.51,float('nan'),float('inf'),True):
            with self.subTest(value=value),self.assertRaises(ValueError):core.validate_template(dict(self.t,blue_ink_density=value))
        for value in (.35,1,1.5):core.validate_template(dict(self.t,blue_ink_density=value))

    def test_pdf_default_identity_black_independence_and_four_up_notice(self):
        sources={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in public_bundle_files()}
        values=core.blank(self.t);values.update(recipient='検証',vehicle_number='1234',delivery_volume='4.250')
        raster={};black={}
        for label,value in [('legacy',None),('normal',1),('light',.35),('dark',1.5)]:
            t=copy.deepcopy(self.t)
            if value is not None:t['blue_ink_density']=value
            path=self.path/(label+'.pdf');core.render_pdf(path,[values],t)
            with pymupdf.open(path) as doc:
                raster[label]=doc[0].get_pixmap().samples
                spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                black[label]=[(s['text'],s['bbox'],s['color']) for s in spans if s['color']==0]
                self.assertTrue(any('検証' in s[0] for s in black[label]))
                notice=[s for s in spans if '納入書' in s['text']]
                self.assertTrue(notice);self.assertNotEqual(notice[0]['color'],0xffffff)
            multi=copy.deepcopy(t);multi['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
            path=self.path/(label+'-four.pdf');core.render_pdf(path,[values]*5,multi)
            with pymupdf.open(path) as doc:
                self.assertEqual([len(p.search_for('納入書（計画）')) for p in doc],[4,1])
                for page in doc:
                    for box in page.search_for('納入書（計画）'):self.assertTrue(page.rect.contains(box))
        self.assertEqual(raster['legacy'],raster['normal']);self.assertNotEqual(raster['light'],raster['normal']);self.assertNotEqual(raster['dark'],raster['normal'])
        self.assertEqual(black['legacy'],black['light']);self.assertEqual(black['normal'],black['dark'])
        self.assertEqual({p:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},sources)
        notice_color=next(i.get('color',self.t['line_color']) for i in self.t['fixed_texts'] if i['id']=='copy_notice')
        self.assertEqual(blue_ink.color(notice_color,.35,notice=True),blue_ink.color(notice_color,.65))

    def test_gui_three_previews_pdf_match_and_saved_reopen(self):
        directory=self.path/'gui';root=tk.Tk();root.withdraw();app=App(root,directory)
        values=core.blank(app.template);values.update(recipient='検証',vehicle_number='1234')
        try:
            app.set_values(values);app.save();record=copy.deepcopy(app.current)
            old_black=(app.template.get('input_density',1),app.template.get('input_transparency',0))
            app.blue_ink_settings.value.set('72.5');app.save_settings()
            self.assertEqual(app.template['blue_ink_density'],.725)
            self.assertEqual((app.template.get('input_density',1),app.template.get('input_transparency',0)),old_black)
            for _ in range(3):app.preview_current();root.update()
            path=self.path/'gui.pdf';core.render_pdf(path,[values],app.template)
            with pymupdf.open(path) as doc:self.assertEqual(doc[0].get_pixmap().samples,app.preview_view.doc[0].get_pixmap().samples)
            self.assertEqual(app.store.get(record['id']),record)
        finally:app.store.close();root.destroy()
        root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            self.assertEqual(app.template['blue_ink_density'],.725);self.assertEqual(app.blue_ink_settings.value.get(),'72.5')
            self.assertEqual(app.store.list()[0]['data'],values);app.set_values(values);app.preview_current();root.update()
        finally:app.store.close();root.destroy()

if __name__=='__main__':unittest.main(verbosity=2)
