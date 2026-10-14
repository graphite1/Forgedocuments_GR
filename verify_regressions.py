"""Cloud successor regressions. Isolated data only; no signing keys generated."""
import copy
import ctypes
import errno
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pymupdf
import tkinter as tk

import core
import main_app
import updates
from ac_defaults import ADDRESS, FORM_ID, migrate_template
from ac_screen import App
from pdf_view import PDFView
from preview_files import generated_pdf


class Regressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.t = core.load_template()
        self.roots = []

    def tearDown(self):
        for root in self.roots:
            try:
                if root.winfo_exists():root.destroy()
            except tk.TclError:pass
        self.temp.cleanup()

    def root(self):
        r=tk.Tk();r.withdraw();self.roots.append(r);return r

    def legacy(self):
        t=copy.deepcopy(self.t)
        for k in ('form_id','ac_defaults_version','ac_footer_revision','ac_footer_source','ac_previous_footer','company_name','company_address','company_contact','random_print_enabled','random_print_x_mm','random_print_y_mm'):
            t.pop(k,None)
        t['fixed_texts']=[i for i in t['fixed_texts'] if not i.get('id','').startswith('company_')]
        return t

    def sample(self):
        d=core.blank(self.t);d.update(date='2026-10-14',number='000012-A',recipient='動作確認用 株式会社',vehicle='0010',departure='09:05',arrival='09:45',quantity='1.00',method='2 P渡')
        return d

    def test_address_missing_or_blank_and_renamed_form(self):
        for name in ('GR 運搬明細書','独自の様式名'):
            for address in ('missing',None,''):
                t=self.legacy();t['name']=name;t['company_name']='エーシートヨアケ共同企業体'
                if address!='missing':t['company_address']=address
                original=copy.deepcopy(t);m=migrate_template(t,FORM_ID)
                self.assertEqual(t,original)
                self.assertEqual(m['company_address'],ADDRESS)
                self.assertEqual(m['company_name'],'エーシートヨアケ共同企業体')
                self.assertEqual(migrate_template(m,FORM_ID),m)

    def test_custom_company_address_contact_geometry_and_print_are_preserved(self):
        t=self.legacy();t.update(company_name='独自共同企業体',company_address='東京都千代田区丸の内1',company_contact='TEL 03-0000-0000',width_mm=116)
        slot={'id':'company_address','text':'東京都千代田区丸の内1','box':[70,1160,880,45],'font':24,'print':False}
        t['fixed_texts'].append(slot)
        m=migrate_template(t,FORM_ID)
        for key in ('company_name','company_address','company_contact','width_mm'):self.assertEqual(m[key],t[key])
        item=next(i for i in m['fixed_texts'] if i.get('id')=='company_address')
        for key in slot:self.assertEqual(item[key],slot[key])

    def test_legacy_untagged_address_is_not_duplicated_or_replaced(self):
        t=self.legacy();t['fixed_texts'].append({'text':'岐阜県岐阜市長良1','box':[62,1165,900,46],'font':28})
        m=migrate_template(t,FORM_ID)
        self.assertEqual(m['company_address'],'岐阜県岐阜市長良1')
        self.assertEqual(len([i for i in m['fixed_texts'] if i.get('value_key')=='company_address']),1)

    def test_conflicting_legacy_address_settings_preserve_printed_literal_and_scalar(self):
        t=self.legacy();t['company_address']='岐阜県岐阜市長良1'
        t['fixed_texts'].append({'id':'company_address','text':'東京都千代田区丸の内1','box':[62,1165,900,46],'font':28})
        m=migrate_template(t,FORM_ID)
        self.assertEqual(m['company_address'],'岐阜県岐阜市長良1')
        slot=next(i for i in m['fixed_texts'] if i.get('id')=='company_address')
        self.assertEqual(slot['text'],'東京都千代田区丸の内1');self.assertNotIn('value_key',slot)
        p=self.path/'conflicting.pdf';core.render_pdf(p,[core.blank(m)],m)
        with pymupdf.open(p) as doc:
            self.assertIn('東京都千代田区丸の内1',doc[0].get_text());self.assertNotIn('岐阜県',doc[0].get_text())

    def test_address_field_missing_default_is_filled_without_changing_other_fields(self):
        t=self.legacy();f=copy.deepcopy(t['fields'][1]);f.update(id='company_address',label='住所');f.pop('default');t['fields'].append(f)
        m=migrate_template(t,FORM_ID)
        self.assertEqual(m['fields'][-1]['default'],ADDRESS)
        self.assertEqual(m['fields'][:-1],t['fields'][:-1])
        self.assertFalse(any(i.get('id')=='company_address' for i in m['fixed_texts']))

    def test_explicit_clearing_after_migration_stays_cleared(self):
        t=migrate_template(self.legacy(),FORM_ID);t['company_address']=''
        self.assertEqual(migrate_template(t,FORM_ID)['company_address'],'')

    def test_dummy_form_has_no_ac_defaults_or_migration(self):
        t=self.legacy();t['form_id']='dummy';t['name']='エーシー帳票'
        t['fixed_texts']=[{'text':'別帳票の固定文','box':[20,20,900,50],'font':28}]
        self.assertEqual(migrate_template(t,'dummy'),t)
        self.assertEqual(migrate_template(t,FORM_ID),t)
        s=core.Store(self.path/'dummy');s.set_template(t)
        try:
            self.assertEqual(s.template(),t)
            p=self.path/'dummy.pdf';core.render_pdf(p,[core.blank(t)],t)
            with pymupdf.open(p) as doc:
                text=doc[0].get_text();self.assertIn('別帳票の固定文',text)
                self.assertNotIn(ADDRESS,text);self.assertNotIn('毎度',text);self.assertNotIn('エーシートヨアケ',text)
        finally:s.close()

    def test_sqlite_authoritative_settings_migrate_once_and_records_stay_unchanged(self):
        folder=self.path/'legacy';s=core.Store(folder);t=self.legacy();t['name']='変更した帳票名';s.set_template(t)
        row=s.save(self.sample(),t);original_history=s.history(row['id']);s.close()
        # A portable template must not supersede the saved SQLite settings.
        core.atomic_json(folder/'template.json',dict(t,name='古いファイル'))
        app=App(self.root(),folder)
        try:
            self.assertEqual(app.template['name'],'変更した帳票名')
            self.assertEqual(app.template['company_address'],ADDRESS)
            self.assertEqual(app.store.get(row['id']),row)
            self.assertEqual(app.store.history(row['id']),original_history)
            count=app.store.db.execute('SELECT count(*) FROM settings').fetchone()[0]
        finally:app.store.close();app.root.destroy()
        app=App(self.root(),folder)
        try:self.assertEqual(app.store.db.execute('SELECT count(*) FROM settings').fetchone()[0],count)
        finally:app.store.close();app.root.destroy()

    def test_initial_address_and_greeting_are_rendered(self):
        p=self.path/'blank.pdf';core.render_pdf(p,[core.blank(self.t)],self.t)
        with pymupdf.open(p) as doc:
            text=doc[0].get_text();compact=re.sub(r'\s+','',text)
            self.assertIn(ADDRESS,compact)
            self.assertIn('エーシートヨアケ',compact);self.assertIn('毎度 ありがとうございます',text)
            self.assertNotIn('ありがとうございます。',text)

    def test_unique_preview_paths_and_cleanup_on_failure_or_cancel(self):
        paths=[]
        for _ in range(12):
            with generated_pdf(self.path,'current') as p:
                p.write_bytes(b'test');paths.append(p)
            self.assertFalse(p.exists())
        self.assertEqual(len(set(paths)),12)
        with self.assertRaises(ValueError):
            with generated_pdf(self.path) as p:p.write_bytes(b'test');raise ValueError('render failed')
        self.assertFalse(p.exists())

    def test_locked_cleanup_does_not_mask_error_or_reuse_path(self):
        with generated_pdf(self.path) as old:
            old.write_bytes(b'locked')
            with patch.object(Path,'unlink',side_effect=PermissionError(errno.EACCES,'locked')):
                # Context exit must handle a reader still holding this file.
                pass
            with generated_pdf(self.path) as new:self.assertNotEqual(old,new)
        # Test cleanup's exception directly, including a simulated print cancel.
        with patch.object(Path,'unlink',side_effect=PermissionError(errno.EACCES,'locked')):
            with generated_pdf(self.path) as p:p.write_bytes(b'locked')
        self.assertTrue(p.exists());p.unlink()

    def test_twelve_changed_previews_while_previous_pdf_is_open(self):
        app=App(self.root(),self.path/'preview');held=[];paths=[]
        real_render=core.render_pdf
        def render(path,*args,**kwargs):
            paths.append(Path(path));real_render(path,*args,**kwargs)
            held.append(pymupdf.open(path))
        try:
            with patch('ac_screen.render_pdf',side_effect=render):
                for i in range(12):
                    app.vars['number'].set(f'{i:06d}-A');app.preview_current();app.root.update()
                    self.assertIn(f'{i:06d}-A',app.preview_view.doc[0].get_text())
            self.assertEqual(len(set(paths)),12)
            self.assertEqual(len(held),12)
            self.assertIn('000000-A',held[0][0].get_text())
        finally:
            for doc in held:doc.close()
            app.store.close();app.root.destroy()

    def test_pdf_view_owns_bytes_and_preserves_view_on_invalid_replacement(self):
        p=self.path/'source.pdf';core.render_pdf(p,[self.sample()],self.t)
        view=PDFView(self.root());view.pack();view.set_pdf(p);p.unlink()
        self.assertIn('000012-A',view.doc[0].get_text());old=view.doc
        p.write_bytes(b'broken')
        with self.assertRaises(Exception):view.set_pdf(p)
        self.assertIs(view.doc,old);self.assertFalse(old.is_closed)
        core.render_pdf(p,[core.blank(self.t)],self.t);view.set_pdf(p)
        self.assertTrue(old.is_closed);self.assertNotIn('000012-A',view.doc[0].get_text())

    def test_output_windows_print_cancel_and_save_cancel_then_preview(self):
        app=App(self.root(),self.path/'output');app.set_values(self.sample());app.save();app.preview_current();first=app.preview_view.doc
        try:
            for _ in range(3):app.output('all','preview');app.root.update()
            with patch('printing.print_pdf',return_value=False):app.output('all','print')
            app.vars['number'].set('9999')
            with patch('ac_screen.messagebox.askyesnocancel',return_value=None):app.output('all','pdf')
            self.assertIs(app.preview_view.doc,first)
            app.preview_current();self.assertIn('9999',app.preview_view.doc[0].get_text())
            self.assertFalse(list((app.store.directory/'preview').glob('*.pdf')))
        finally:app.store.close();app.root.destroy()

    def test_settings_validation_preview_can_repeat_and_preserve_input(self):
        app=App(self.root(),self.path/'settings');d=self.sample();app.set_values(d)
        try:
            app.preview_current()
            for _ in range(2):app.save_settings();app.preview_current()
            self.assertEqual(app.values(),d)
            self.assertFalse(list((app.store.directory/'preview').glob('*.pdf')))
        finally:app.store.close();app.root.destroy()

    def test_random_defaults_validation_and_zero_axes(self):
        self.assertFalse(self.t['random_print_enabled']);self.assertEqual(core.print_offset(self.sample(),self.t),(0,0))
        for key in ('random_print_x_mm','random_print_y_mm'):
            for value in (-1,3,float('nan'),float('inf'),True):
                t=copy.deepcopy(self.t);t[key]=value
                with self.assertRaises(ValueError):core.validate_template(t)
        t=dict(self.t,random_print_enabled=True,random_print_x_mm=0,random_print_y_mm=0)
        self.assertEqual(core.print_offset(self.sample(),t),(0,0))

    def test_random_preview_and_saved_output_match_exactly(self):
        t=dict(self.t,random_print_enabled=True,random_print_x_mm=.6,random_print_y_mm=.4)
        folder=self.path/'random';s=core.Store(folder);s.set_template(t);s.close()
        app=App(self.root(),folder);app.set_values(self.sample())
        try:
            app.preview_current();preview=app.preview_view.doc[0].get_pixmap(dpi=130).samples
            app.save();row=app.store.list()[0];p=self.path/'saved.pdf';core.render_pdf(p,[row],t)
            with pymupdf.open(p) as doc:self.assertEqual(doc[0].get_pixmap(dpi=130).samples,preview)
            self.assertEqual(row['data'],self.sample())
        finally:app.store.close();app.root.destroy()

    def test_random_offsets_reproducible_per_page_with_independent_axes(self):
        d=self.sample();t=dict(self.t,random_print_enabled=True,random_print_x_mm=.7,random_print_y_mm=.2)
        dx,dy=core.print_offset(d,t)
        self.assertLessEqual(abs(dx*self.t['width_mm']/1000),.7)
        self.assertLessEqual(abs(dy*self.t['height_mm']/1300),.2)
        self.assertNotEqual(core.print_offset(d,t,0),core.print_offset(d,t,1))
        a=self.path/'a.pdf';b=self.path/'b.pdf';original=copy.deepcopy(d)
        core.render_pdf(a,[d,d],t);core.render_pdf(b,[{'data':d,'id':'ignored'},d],t)
        with pymupdf.open(a) as first,pymupdf.open(b) as second:
            for i in range(2):self.assertEqual(first[i].get_pixmap(dpi=100).samples,second[i].get_pixmap(dpi=100).samples)
            self.assertNotEqual(first[0].get_pixmap(dpi=100).samples,first[1].get_pixmap(dpi=100).samples)
        self.assertEqual(d,original)

    def test_random_inputs_do_not_move_frame_or_date_content(self):
        off=dict(self.t,input_print_style='smooth');on=dict(off,random_print_enabled=True,random_print_x_mm=2,random_print_y_mm=2)
        paths=[]
        for name,t in (('off',off),('on',on)):
            p=self.path/f'{name}.pdf';core.render_pdf(p,[self.sample()],t);paths.append(p)
        with pymupdf.open(paths[0]) as a,pymupdf.open(paths[1]) as b:
            for token in ('2026','10','14','000012-A','0010'):self.assertIn(token,b[0].get_text())
            self.assertEqual(a[0].rect,b[0].rect)
            self.assertEqual(a[0].get_drawings()[0]['rect'],b[0].get_drawings()[0]['rect'])
            af=a[0].search_for('毎度')[0];bf=b[0].search_for('毎度')[0];self.assertEqual(af,bf)
            rect=a[0].get_drawings()[0]['rect']
            self.assertAlmostEqual(rect.width,off['width_mm']*core.MM,places=3)
            self.assertAlmostEqual(rect.x0,(a[0].rect.width-rect.width)/2,places=3)

    def test_random_glyphs_and_images_stay_inside_outer_frame(self):
        from PIL import Image
        p=self.path/'receipt.png';Image.new('RGB',(120,40),'red').save(p)
        d=self.sample();d['receipt_image']=core.image_encode(p);d['recipient']='長い宛先 株式会社土木施工管理';t=dict(self.t,input_print_style='smooth',random_print_enabled=True,random_print_x_mm=2,random_print_y_mm=2)
        out=self.path/'bounds.pdf';core.render_pdf(out,[d],t)
        with pymupdf.open(out) as doc:
            frame=doc[0].get_drawings()[0]['rect']
            for block in doc[0].get_text('dict')['blocks']:
                if block['type']==1:self.assertTrue(frame.contains(pymupdf.Rect(block['bbox'])))
                else:
                    for line in block['lines']:
                        for span in line['spans']:self.assertTrue(frame.contains(pymupdf.Rect(span['bbox'])),span['text'])

    def mutex_api(self,error,handle=123):
        api=SimpleNamespace(CreateMutexW=Mock(return_value=handle),CloseHandle=Mock())
        return api

    def test_duplicate_mutex_returns_normally_without_reading_lock_file(self):
        api=self.mutex_api(183)
        with patch.object(main_app.sys,'frozen',True,create=True),patch.object(main_app,'_instance_handle',None),patch.object(ctypes,'WinDLL',return_value=api,create=True),patch.object(ctypes,'get_last_error',return_value=183,create=True),patch('pathlib.Path.open',side_effect=PermissionError(errno.EACCES,'old running.lock')):
            self.assertFalse(main_app.acquire_instance());api.CloseHandle.assert_called_once_with(123)

    def test_primary_mutex_holds_until_release_and_uses_install_root(self):
        api=self.mutex_api(0)
        with patch.object(main_app.sys,'frozen',True,create=True),patch.object(main_app,'_instance_handle',None),patch.object(ctypes,'WinDLL',return_value=api,create=True),patch.object(ctypes,'get_last_error',return_value=0,create=True),patch('main_app.atexit.register') as register,patch('main_app.updates.install_root',return_value=self.path):
            self.assertTrue(main_app.acquire_instance());self.assertTrue(main_app.acquire_instance())
            self.assertEqual(api.CreateMutexW.call_count,1);register.assert_called_once()
            self.assertTrue(api.CreateMutexW.call_args.args[2].startswith('Local\\ForgedocumentsGR-'))
            main_app.release_instance();api.CloseHandle.assert_called_once_with(123)

    def test_mutex_access_failure_is_distinct_from_duplicate(self):
        api=self.mutex_api(5,None)
        with patch.object(main_app.sys,'frozen',True,create=True),patch.object(main_app,'_instance_handle',None),patch.object(ctypes,'WinDLL',return_value=api,create=True),patch.object(ctypes,'get_last_error',return_value=5,create=True):
            with self.assertRaises(OSError):main_app.acquire_instance()

    def test_duplicate_start_shows_info_and_does_not_create_home(self):
        with patch('main_app.acquire_instance',return_value=False),patch('main_app.updates.route_to_current',return_value=False),patch('main_app.messagebox.showinfo') as info,patch('main_app.Home') as home,patch.object(main_app.sys,'argv',['app']):
            self.assertIsNone(main_app.main());info.assert_called_once();home.assert_not_called()

    def test_existing_published_signature_and_tampering_without_private_keys(self):
        m=json.loads((Path(__file__).parent/'tests/fixtures/forgedocuments-gr-1.3.0.manifest.json').read_text())
        self.assertEqual(updates.validate_manifest(m),m)
        for field,value in (('release_notes','changed'),('sha256','0'*64),('app_id','other'),('download_url','https://other.test/file')):
            bad=dict(m);bad[field]=value
            with self.assertRaises(ValueError):updates.validate_manifest(bad)

    def test_archive_traversal_and_integrity_checks_without_signing(self):
        import zipfile
        for filename in ('../escape.exe','Forgedocuments GR.exe'):
            p=self.path/'update.zip'
            with zipfile.ZipFile(p,'w') as archive:
                files={filename:b'fake executable for ZIP validation only','version.json':b'{}'}
                for name,content in files.items():archive.writestr(name,content)
                archive.writestr('release_files.json',json.dumps({name:hashlib.sha256(content).hexdigest() for name,content in files.items()}))
            dest=self.path/('invalid' if filename.startswith('.') else 'valid')
            if filename.startswith('.'):
                with self.assertRaises(ValueError):updates.extract_archive(p,dest)
                self.assertFalse((self.path/'escape.exe').exists())
            else:updates.extract_archive(p,dest);self.assertEqual((dest/filename).read_bytes(),files[filename])
        p=self.path/'corrupt.zip'
        with zipfile.ZipFile(p,'w') as archive:
            archive.writestr(updates.EXE,b'fake');archive.writestr('version.json',b'{}')
            archive.writestr('release_files.json',json.dumps({updates.EXE:'0'*64,'version.json':'0'*64}))
        with self.assertRaises(ValueError):updates.extract_archive(p,self.path/'corrupt')
        self.assertFalse((self.path/'corrupt').exists())


if __name__=='__main__':unittest.main(verbosity=2)
