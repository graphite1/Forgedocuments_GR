"""Integration checks. Test records are isolated; never writes to live user data."""
import copy, json, os, tempfile, unittest
from pathlib import Path
from core import *
import pymupdf as fitz

class Verification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=os.environ.get('AC_TEST_TEMP'));cls.path=Path(cls.temp.name);cls.t=load_template()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def sample(self):
        d=blank(self.t);d.update(date='2026-10-14',number='000012-A',recipient='動作確認用 株式会社',site='動作確認用現場',kind='入力例（実データではありません）',vehicle='0010',departure='09:05',arrival='09:45',quantity='1.00',quantity_unit='台',cumulative_unit='台',shipping_temperature='150',arrival_temperature='140',shipping_clerk='確認用',notes='動作確認用。\n入力内容を変更して使用。',method='2 P渡')
        return d

    def test_01_blank_and_pdf_sizes(self):
        self.assertFalse(validate(blank(self.t),self.t))
        p=self.path/'blank.pdf';render_pdf(p,[blank(self.t)],self.t)
        with fitz.open(p) as d:
            self.assertEqual(len(d),1);self.assertAlmostEqual(d[0].rect.width,210*MM,places=3)
            self.assertAlmostEqual(d[0].rect.height,297*MM,places=3)
            text=d[0].get_text();self.assertIn('運',text);self.assertIn('毎度',text);self.assertNotIn('原本の記入例会社名',text)
        t=copy.deepcopy(self.t);t['page_mode']='original';render_pdf(p,[self.sample()],t)
        with fitz.open(p) as d:self.assertAlmostEqual(d[0].rect.width,(t['width_mm']+1)*MM,places=3)

    def test_02_storage_revision_history_reopen(self):
        directory=self.path/'store';s=Store(directory);d=self.sample();r=s.save(d,self.t);rid=r['id']
        d['notes']='訂正内容';u=s.save(d,self.t,rid,r['revision'],'備考訂正')
        with self.assertRaises(ValueError):s.save(d,self.t,rid,r['revision'],'古い改訂')
        self.assertEqual(len(s.history(rid)),2);s.close();s=Store(directory)
        self.assertEqual(s.get(rid)['data']['number'],'000012-A');self.assertEqual(s.get(rid)['data']['vehicle'],'0010')
        self.assertEqual(s.get(rid)['data']['notes'],'訂正内容')
        s.archive(rid);self.assertEqual(len(s.list()),0);s.archive(rid,False);self.assertEqual(len(s.list()),1)
        s.set_template(self.t);s.backup(self.path/'backup.sqlite3',self.t);s.close()

    def test_03_validation_explicit_limits(self):
        d=self.sample();d['quantity']='1.1';t=copy.deepcopy(self.t);f=next(f for f in t['fields'] if f['id']=='quantity');f.update(max='10',min='0',decimals=2)
        self.assertFalse(validate(d,t));d['quantity']='10';self.assertFalse(validate(d,t));d['quantity']='10.01';self.assertTrue(validate(d,t))
        for value in ['NaN','Infinity','abc']:
            d['quantity']=value;self.assertTrue(validate(d,t))
        d=self.sample();d['date']='2026-02-30';self.assertTrue(validate(d,t));d['date']='2026-2-1';self.assertTrue(validate(d,t))
        d=self.sample();d['departure']='24:00';self.assertTrue(validate(d,t));d=self.sample();d['cumulative_count']='2.1';self.assertTrue(validate(d,t))

    def test_04_cumulative_atomic_and_units(self):
        s=Store(self.path/'calc');rows=[]
        for i in range(3):
            d=self.sample();d['number']=str(i).zfill(5);rows.append(s.save(d,self.t))
        updated=s.apply_cumulative(rows,self.t,'5.50','10')
        self.assertEqual(updated[-1]['data']['cumulative_quantity'],'8.50');self.assertEqual(updated[-1]['data']['cumulative_count'],'13');self.assertEqual(updated[-1]['data']['cumulative_unit'],'台')
        self.assertTrue(all(r['data']['quantity']=='1.00' for r in updated))
        with self.assertRaises(ValueError):s.apply_cumulative(rows,self.t)
        self.assertEqual(s.get(rows[0]['id'])['data']['cumulative_quantity'],'6.50')
        d=self.sample();d['quantity_unit']='kg';other=s.save(d,self.t)
        with self.assertRaises(ValueError):s.apply_cumulative([updated[0],other],self.t)
        s.close()

    def test_05_csv_roundtrip_header_matching(self):
        d=self.sample();p=self.path/'sample.csv';csv_export(p,[{'data':d}],self.t);read=csv_read(p,self.t)
        self.assertEqual(read[0]['number'],'000012-A');self.assertEqual(read[0]['notes'],d['notes'])
        p.write_text('No.,車両番号,年月日\n0001,0012,2026-10-14\n',encoding='utf-8-sig');self.assertEqual(csv_read(p,self.t)[0]['vehicle'],'0012')
        p.write_text('不明列\n1\n',encoding='utf-8-sig')
        with self.assertRaises(ValueError):csv_read(p,self.t)

    def test_06_multipage_png_long_text(self):
        d=self.sample();d['recipient']='長い宛先を確認するための名称 株式会社土木施工管理';d['notes']='長い文字列と折り返しを確認。'*5
        p=self.path/'multi.pdf';render_pdf(p,[d,blank(self.t),self.sample()],self.t)
        with fitz.open(p) as doc:self.assertEqual(len(doc),3)
        files=render_pngs(p,self.path/'png',dpi=100);self.assertEqual(len(files),3)
        d['recipient']='あ'*300
        with self.assertRaises(ValueError):render_pdf(p,[d],self.t)
        with fitz.open(p) as doc:self.assertEqual(len(doc),3) # failed output keeps previous file intact

    def test_07_signature_and_no_copy(self):
        from PIL import Image
        p=self.path/'signature.png';Image.new('RGBA',(100,50),(220,0,0,100)).save(p)
        d=self.sample();d['receipt_image']=image_encode(p);d['receipt_text']='非表示の文字';out=self.path/'signature.pdf';render_pdf(out,[d],self.t)
        with fitz.open(out) as doc:
            self.assertEqual(len(doc[0].get_images()),1);self.assertNotIn('非表示の文字',doc[0].get_text())
        self.assertTrue(all(v=='' for v in blank(self.t).values()))

    def test_08_template_state(self):
        s=Store(self.path/'settings');t=copy.deepcopy(self.t);t['width_mm']=116;s.set_template(t);self.assertEqual(s.template()['width_mm'],116);s.close()
        t['width_mm']=300
        with self.assertRaises(ValueError):validate_template(t)

    def test_09_tkinter_hidden_smoke(self):
        import tkinter as tk
        from app import App
        root=tk.Tk();root.withdraw();app=App(root,self.path/'gui');root.update()
        d=self.sample();app.set_values(d);root.update();self.assertEqual(app.values(),d)
        self.assertTrue(app.save());self.assertEqual(len(app.store.list()),1)
        app.preview_current();root.update();self.assertTrue(hasattr(app,'preview_photo'))
        t=copy.deepcopy(app.template);next(f for f in t['fields'] if f['id']=='number')['required']=True
        app.json_edit.delete('1.0','end');app.json_edit.insert('1.0',json.dumps(t,ensure_ascii=False));app.save_settings();root.update()
        self.assertEqual(app.values(),d);self.assertTrue(next(f for f in app.template['fields'] if f['id']=='number')['required'])
        app.store.close();root.destroy()

    def test_10_print_style_migration(self):
        old=copy.deepcopy(self.t)
        for key in ('input_print_style','impact_pitch','impact_dot_ratio','impact_stroke','input_stroke'):old.pop(key,None)
        old['input_color']=[.13,.38,.57]
        s=Store(self.path/'migration');s.set_template(old);row=s.save(self.sample(),old)
        current=s.template();self.assertEqual(current['input_print_style'],'impact');self.assertEqual(current['input_color'],self.t['input_color'])
        self.assertEqual(s.get(row['id'])['data'],row['data']);self.assertEqual(len(s.history(row['id'])),1)
        p=self.path/'impact.pdf';render_pdf(p,[row],current)
        with fitz.open(p) as d:
            self.assertIn('000012-A',d[0].get_text());self.assertGreater(len(d[0].get_drawings()),300)
        s.close()

if __name__=='__main__':unittest.main(verbosity=2)
