"""The public source must work without the developer's private workspace."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from PIL import Image
import pymupdf
import core
from background_assets import load_background
from tomei_preset import PUBLIC_ASSETS,PUBLIC_SHA256,public_bundle_files
from tomei_screen import App,DEFINITION


class PublicBackgroundChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def test_clean_first_open_displays_empty_plan_and_embeds_reviewed_pixels(self):
        root=tk.Tk();root.withdraw();app=App(root,self.path/'fresh')
        try:
            self.assertEqual(app.template['background']['status'],'ready')
            self.assertEqual(app.template['layout_profile'],'generated-20261014')
            self.assertTrue(app.template['background']['processing']['plan_notice_in_image'])
            self.assertTrue(all(value=='' for value in app.values().values()))
            self.assertEqual(app.notebook.select(),str(app.entrytab))
            page=app.preview_view.doc[0]
            self.assertEqual(len(page.search_for('納入書（計画）')),1)
            self.assertEqual(len(page.get_images()),1)
            image=Image.open(io.BytesIO(app.preview_view.doc.extract_image(page.get_images()[0][0])['image'])).convert('RGB')
            self.assertEqual(image.tobytes(),load_background(app.template).tobytes())
            for point in ((714,502),(934,502),(374,1337),(874,1337)):
                self.assertEqual(image.getpixel(point),(255,255,255))
            self.assertFalse(app.store.list())
        finally:app.store.close();root.destroy()

    def test_public_asset_and_windows_recipe_include_both_image_and_settings(self):
        files=public_bundle_files()
        self.assertEqual({p.name for p in files},{'tomei-plan-background.json','tomei-plan-background.png'})
        config=json.loads(files[0].read_text(encoding='utf-8'))
        self.assertTrue(config['public_distribution_approved']);self.assertTrue(config['notice_in_image'])
        self.assertFalse(config['transaction_values_included']);self.assertFalse(config['handwriting_or_signatures_included'])
        self.assertEqual(hashlib.sha256(files[1].read_bytes()).hexdigest(),PUBLIC_SHA256)
        from tools.build_windows import public_asset_args
        args=public_asset_args()
        for file in files:self.assertIn(str(file)+':assets',args)
        self.assertNotIn('private-assets',str(args))

    def test_corrupt_public_configuration_does_not_fall_back_to_an_unreviewed_image(self):
        for file in public_bundle_files():(self.path/file.name).write_bytes(file.read_bytes())
        config_path=self.path/'tomei-plan-background.json';config=json.loads(config_path.read_text())
        config['notice_in_image']=False;config_path.write_text(json.dumps(config))
        with patch('tomei_preset.PUBLIC_ASSETS',self.path):
            with self.assertRaisesRegex(ValueError,'照合'):public_bundle_files()

    def test_existing_records_history_and_custom_settings_are_not_replaced(self):
        old=core.load_template(DEFINITION)
        next(f for f in old['fields'] if f['id']=='recipient')['default']='KEEP-CUSTOM'
        store=core.Store(self.path/'old',default_template=old);store.set_template(old)
        data=core.blank(old);data['delivery_volume']='005.500';record=store.save(data,old)
        history=store.history(record['id']);store.close()
        root=tk.Tk();root.withdraw();app=App(root,self.path/'old')
        try:
            self.assertEqual(app.template,old)
            self.assertEqual(app.store.get(record['id']),record);self.assertEqual(app.store.history(record['id']),history)
        finally:app.store.close();root.destroy()

    def test_in_frame_notice_and_blue_honorific_are_masked_without_changing_other_ink(self):
        from tomei_preset import with_bundled_preset
        t=with_bundled_preset(core.load_template(DEFINITION))
        image=load_background(t)
        for rect in ((124,105,332,60),(232,166,46,42)):
            x,y,w,h=rect
            # Borders are intentionally excluded by the generic cell mask.
            self.assertEqual(image.crop((x-24,y-31,x+w-28,y+h-35)).getextrema(),((255,255),)*3)
        prior=copy.deepcopy(t);prior['background_blank_regions_mm']=prior['background_blank_regions_mm'][:-2]
        old=load_background(prior)
        from PIL import ImageChops,ImageDraw
        difference=ImageChops.difference(old,image)
        draw=ImageDraw.Draw(difference)
        for x,y,w,h in ((124,105,332,60),(232,166,46,42)):
            draw.rectangle((x-26,y-33,x+w-26,y+h-33),fill='black')
        self.assertIsNone(difference.getbbox())

    def test_recipient_and_honorific_black_notice_outside_each_frame_and_no_value_mutation(self):
        from tomei_preset import with_bundled_preset
        t=with_bundled_preset(core.load_template(DEFINITION))
        for value in ('確認用宛名','確認用宛名 殿'):
            data=core.blank(t);data['recipient']=value;before=copy.deepcopy(data)
            for count in (1,5):
                layout=copy.deepcopy(t)
                if count==5:layout['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
                path=self.path/f'check-{count}.pdf';core.render_pdf(path,[data]*count,layout)
                with pymupdf.open(path) as doc:
                    for page in doc:
                        images=sorted(page.get_image_rects(page.get_images()[0][0]),key=lambda r:(r.y0,r.x0))
                        notices=sorted(page.search_for('納入書（計画）'),key=lambda r:(r.y0,r.x0))
                        self.assertEqual(len(images),len(notices))
                        for image,notice in zip(images,notices):
                            self.assertGreater(notice.y0,image.y1);self.assertTrue(page.rect.contains(notice))
                        spans=[s for b in page.get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                        recipient=[s for s in spans if '確認用宛名' in s['text']]
                        self.assertEqual(len(recipient),len(images))
                        self.assertTrue(all(s['color']==0 and s['text'].count('殿')==1 for s in recipient))
                self.assertEqual(data,before)

    def test_old_profile_upgrades_once_and_preserves_custom_recipient_box_and_values(self):
        from tomei_preset import with_bundled_preset
        from tomei_defaults import migrate_background
        base=core.load_template(DEFINITION);old=with_bundled_preset(base)
        old.pop('plan_overlay_revision')
        old['background_blank_regions_mm']=old['background_blank_regions_mm'][:-2]
        recipient=next(f for f in old['fields'] if f['id']=='recipient')
        recipient.pop('display_suffix');recipient.update(box=[20,125,400,45],default='KEEP-CUSTOM',wrap=True)
        upgraded=migrate_background(old,base)
        actual=next(f for f in upgraded['fields'] if f['id']=='recipient')
        self.assertEqual(actual['box'],recipient['box']);self.assertEqual(actual['default'],'KEEP-CUSTOM')
        self.assertTrue(actual['wrap'])
        self.assertEqual(migrate_background(upgraded,base),upgraded)
        self.assertNotIn('plan_overlay_revision',old)

    def test_reselecting_same_background_keeps_new_masks_and_black_honorific(self):
        from tomei_preset import with_bundled_preset
        from tomei_profiles import image_profile
        t=with_bundled_preset(core.load_template(DEFINITION))
        self.assertEqual(image_profile(t)['background_blank_regions_mm'],t['background_blank_regions_mm'])
        self.assertEqual(image_profile(t)['fields'],t['fields'])
