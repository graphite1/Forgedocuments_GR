"""Headless font-default, mixed-run and inferred-check evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf
import core
from input_fonts import InputFont
from tomei_defaults import migrate_background
from tomei_screen import DEFINITION,validate_policy
from tomei_preset import with_bundled_preset
from tomei_print_font import PROFILE,NUMERIC_PROFILE,input_font
from tomei_marks import draw_check,PROVENANCE


class TomeiFontMarkChecks(unittest.TestCase):
    def test_new_default_and_legacy_explicit_choices_and_values_are_preserved(self):
        t=core.load_template(DEFINITION);self.assertEqual(t['input_font_profile'],PROFILE)
        old=copy.deepcopy(t);old.pop('input_font_profile');old.pop('input_font_path',None);old['blue_ink_density']=.75
        migrated=migrate_background(old,t);self.assertEqual(migrated['input_font_profile'],PROFILE)
        for change in [dict(input_font_profile=NUMERIC_PROFILE),dict(input_font_path=''),dict(input_font_path='custom-font.ttf')]:
            explicit=dict(old,**change);self.assertEqual(migrate_background(explicit,t),explicit)
        self.assertEqual(migrate_background(migrated,t),migrated)
        with tempfile.TemporaryDirectory() as temp:
            store=core.Store(temp,default_template=t,form_id=t['form_id'],migrate_definition=lambda x:migrate_background(x,t))
            try:
                store.set_template(old);r=store.save(core.blank(t),t);before=store.get(r['id'])
                self.assertEqual(store.template()['input_font_profile'],PROFILE);self.assertEqual(store.get(r['id']),before)
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM settings').fetchone()[0],2)
            finally:store.close()

    def test_plan_number_uses_dedicated_digits_hyphens_and_preserves_japanese_fallback(self):
        t=with_bundled_preset(core.load_template(DEFINITION));font=input_font(t,'HeiseiKakuGo-W5')
        self.assertIsInstance(font,InputFont)
        self.assertEqual(font.runs('角文 殿 普通'),[(font.fallback,'角文 殿 普通')])
        with tempfile.TemporaryDirectory() as temp:
            t['input_print_style']='plain'
            values=core.blank(t);values['mix_plan_number']='12345678-90'
            path=Path(temp)/'synthetic.pdf';core.render_pdf(path,[values],t)
            with pymupdf.open(path) as doc:
                spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                dedicated=''.join(s['text'].replace(' ','') for s in spans if 'TomeiSample' in s['font'])
                self.assertIn('12345678-90',dedicated)
                self.assertIn('納入書（計画）',doc[0].get_text())

    def test_tomei_checks_use_connected_inferred_tick_in_existing_alpha_group(self):
        self.assertEqual(PROVENANCE['kind'],'inferred');self.assertFalse(PROVENANCE['source_pdf_verified'])
        t=with_bundled_preset(core.load_template(DEFINITION));field=next(f for f in t['fields'] if f['type']=='multi_choice')
        values=core.blank(t);values[field['id']]=json.dumps([field['options'][0]['key']])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'check.pdf'
            with patch('tomei_marks.draw_check',wraps=draw_check) as draw:core.render_pdf(path,[values],t);self.assertEqual(draw.call_count,1)
            with pymupdf.open(path) as doc:
                paths=[p for p in doc[0].get_drawings() if len(p['items'])==2 and all(i[0]=='l' for i in p['items'])]
                self.assertTrue(paths)
                a,b=paths[-1]['items'];self.assertEqual(a[2],b[1])
            for vals,name in [(values,'transparent'),(core.blank(t),'blank')]:
                core.render_pdf(Path(temp)/(name+'.pdf'),[vals],dict(t,input_transparency=1))
            with pymupdf.open(Path(temp)/'transparent.pdf') as a,pymupdf.open(Path(temp)/'blank.pdf') as b:
                self.assertEqual(a[0].get_pixmap().samples,b[0].get_pixmap().samples)
