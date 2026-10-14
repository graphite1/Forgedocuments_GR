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
