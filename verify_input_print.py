"""Variable printer ink and missing-value markers, using synthetic plan data."""
import copy
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import pymupdf
import core
from record_batches import summary
from tomei_preset import with_bundled_preset
from tomei_screen import App,DEFINITION


class InputPrintChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.t=with_bundled_preset(core.load_template(DEFINITION))

    def tearDown(self):self.temp.cleanup()

    def test_hyphens_roundtrip_store_csv_scalar_types_and_print_date_time_without_splitting(self):
        for name,t in [('ac',core.load_template()),('tomei',self.t)]:
            data=core.blank(t)
            ids=[f['id'] for f in t['fields'] if f.get('input',True) and f['type'] not in ('layout_only','multi_choice','image')]
            data.update({key:'-' for key in ids})
            self.assertFalse(core.validate(data,t))
            store=core.Store(self.path/name,default_template=t)
            try:
                record=store.save(data,t);self.assertEqual(store.get(record['id'])['data'],data)
                core.csv_export(self.path/(name+'.csv'),[record],t)
                self.assertEqual(core.csv_read(self.path/(name+'.csv'),t),[data])
            finally:store.close()
            store=core.Store(self.path/name,default_template=t)
            try:self.assertEqual(store.get(record['id'])['data'],data)
            finally:store.close()
            pdf=self.path/(name+'.pdf');core.render_pdf(pdf,[data]*2,t)
            with pymupdf.open(pdf) as doc:
                for page in doc:
                    self.assertEqual(page.get_text().count('-'),len(ids))

    def test_markers_are_missing_in_totals_and_cumulative_rejects_them_atomically(self):
        rows=[{'quantity':'-','quantity_unit':'m³'},{'quantity':'','quantity_unit':'m³'},{'quantity':'2.50','quantity_unit':'m³'}]
        result=summary(rows,None,'quantity','quantity_unit')
        self.assertEqual(result['quantity_totals'],{'m³':'2.50'});self.assertEqual(result['missing_quantity_count'],2)
        self.assertEqual(summary(rows[:2],None,'quantity','quantity_unit')['quantity_totals'],{})
        t=core.load_template();data=core.blank(t);data.update(quantity='-',quantity_unit='m³')
        store=core.Store(self.path/'calculation',default_template=t)
        try:
            record=store.save(data,t)
            with self.assertRaisesRegex(ValueError,'数値'):store.apply_cumulative([record],t)
            self.assertEqual(store.get(record['id']),record)
        finally:store.close()
        f=copy.deepcopy(next(f for f in t['fields'] if f['id']=='quantity'));f['min']='0'
        self.assertTrue(core.validate({'quantity':'-1'},{'fields':[f]}))
        f['numeric_required_for_calculation']=True
        self.assertIn('計算に必要',core.validate({'quantity':'-'},{'fields':[f]})[0])

    def test_density_gui_save_reopen_preview_and_four_up_keep_fixed_blue_pixels(self):
        directory=self.path/'gui';root=tk.Tk();root.withdraw();app=App(root,directory)
        data=core.blank(app.template);data.update(recipient='検証用宛名',delivery_date='-',delivery_volume='-')
        try:
            app.set_values(data)
            app.widgets['delivery_volume'].delete(0,'end');app.widgets['delivery_volume'].insert(0,'-')
            self.assertEqual(app.values()['delivery_volume'],'-')
            app.save();record=copy.deepcopy(app.current)
            app.tree.selection_set(record['id'])
            with patch('definition_screen.messagebox.showinfo') as info:
                app.batch_summary()
                self.assertIn('集計できる数値なし',info.call_args.args[1])
            old=copy.deepcopy(app.template)
            app.input_print_settings.vars['input_density'].set('65')
            app.input_print_settings.vars['input_width_scale'].set('96')
            app.input_print_settings.vars['input_tracking_em'].set('2')
            app.input_print_settings.vars['input_weight_em'].set('1.8')
            app.save_settings();self.assertEqual(app.values(),data)
            self.assertEqual(app.template['input_density'],.65)
            for _ in range(3):app.preview_current();root.update()
            saved=self.path/'density.pdf';core.render_pdf(saved,[data],app.template)
            with pymupdf.open(saved) as doc:
                self.assertEqual(doc[0].get_pixmap().samples,app.preview_view.doc[0].get_pixmap().samples)
                spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                self.assertTrue(all(s['color']==0x595959 for s in spans if '検証用宛名' in s['text']))
            before=self.path/'before.pdf';core.render_pdf(before,[data],old)
            with pymupdf.open(before) as a,pymupdf.open(saved) as b:
                notice=a[0].search_for('納入書（計画）')[0]
                self.assertEqual(a[0].get_pixmap(clip=notice,dpi=200).samples,b[0].get_pixmap(clip=notice,dpi=200).samples)
                image=a[0].get_images()[0][0];other=b[0].get_images()[0][0]
                self.assertEqual(a.extract_image(image)['image'],b.extract_image(other)['image'])
            multi=copy.deepcopy(app.template);multi['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
            core.render_pdf(self.path/'multi.pdf',[data]*5,multi)
            with pymupdf.open(self.path/'multi.pdf') as doc:
                self.assertEqual([len(p.search_for('納入書（計画）')) for p in doc],[4,1])
            self.assertEqual(app.store.get(record['id']),record)
        finally:app.store.close();root.destroy()
        root=tk.Tk();root.withdraw();app=App(root,directory)
        try:
            self.assertEqual(app.template['input_density'],.65)
            self.assertEqual(app.input_print_settings.vars['input_density'].get(),'65')
            app.set_values(app.store.list()[0]['data']);app.preview_current()
            self.assertEqual(app.values(),data)
        finally:app.store.close();root.destroy()

    def test_density_and_tracking_reject_invalid_settings(self):
        for key,value in [('input_density',0),('input_density',1.1),('input_density',float('nan')),
                          ('input_width_scale',True),('input_tracking_em',-.1),('input_weight_em',.2)]:
            bad=copy.deepcopy(self.t);bad[key]=value
            with self.assertRaises(ValueError):core.validate_template(bad)

    def test_choice_dropdown_selects_and_saves_the_marker(self):
        from ac_screen import App as AcApp
        root=tk.Tk();root.withdraw();app=AcApp(root,self.path/'ac-gui')
        try:
            choices=list(app.widgets['method']['values']);self.assertIn('-',choices)
            app.widgets['method'].current(choices.index('-'));app.save()
            self.assertEqual(app.store.list()[0]['data']['method'],'-')
            app.tree.selection_set(app.current['id'])
            with patch('ac_screen.messagebox.showinfo') as info:
                app.batch_summary()
                self.assertIn('集計できる数値なし',info.call_args.args[1])
            app.preview_current();self.assertIn('-',app.preview_view.doc[0].get_text())
        finally:app.store.close();root.destroy()

    def test_input_font_width_tracking_weight_and_density_leave_fixed_ac_footer_unchanged(self):
        import os
        t=core.load_template();t.update(input_color=[0,0,0],input_print_style='printer')
        values=core.blank(t);values['recipient']='検証用宛名'
        altered=copy.deepcopy(t)
        font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/meiryo.ttc'
        if font.is_file():altered['input_font_path']=str(font)
        altered.update(input_width_scale=.9,input_tracking_em=.08,input_weight_em=.03,input_density=.8,
                       random_print_enabled=True,random_print_x_mm=2,random_print_y_mm=2)
        a_path=self.path/'font-a.pdf';b_path=self.path/'font-b.pdf'
        core.render_pdf(a_path,[values],t);core.render_pdf(b_path,[values],altered)
        with pymupdf.open(a_path) as a,pymupdf.open(b_path) as b:
            _,slots=core.placements(t);ox,oy,_=slots[0];fh=t['height_mm']*core.MM
            clip=pymupdf.Rect(ox,oy+fh*(1-1210/1300),ox+t['width_mm']*core.MM,oy+fh*(1-1080/1300))
            self.assertEqual(a[0].get_pixmap(clip=clip).samples,b[0].get_pixmap(clip=clip).samples)
            self.assertNotEqual(a[0].get_pixmap().samples,b[0].get_pixmap().samples)
            if font.is_file():
                def recipient_font(page):
                    return next(s['font'] for block in page.get_text('dict')['blocks'] if block['type']==0 for l in block['lines'] for s in l['spans'] if '検証用宛名' in s['text'])
                self.assertNotEqual(recipient_font(a[0]),recipient_font(b[0]))
