"""Automatic form routing, legacy backups, isolation and safe write failures."""
import copy,hashlib,json,sqlite3,tempfile,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch
from app_storage import AppStorage,StorageError,MARKER
from core import Store,blank,atomic_json
from form_registry import catalog,default_definition
from main_app import Home


class AppStorageChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name).resolve()
        self.rows=catalog();self.ac=default_definition(self.rows[0]);self.tomei=default_definition(self.rows[1])

    def tearDown(self):self.temp.cleanup()

    def legacy(self):
        folder=self.path/'legacy';t=copy.deepcopy(self.ac);t['line_color']=[.2,.3,.8]
        store=Store(folder,default_template=t,form_id=t['form_id']);store.set_template(t)
        data=blank(t);data['number']='1001';record=store.save(data,t);store.close()
        return folder,t,record

    def test_original_failure_fixture_is_imported_only_for_its_own_form(self):
        source,t,record=self.legacy();before={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in source.iterdir() if f.is_file()}
        manager=AppStorage(self.path/'app',dict(ac_toyoake=str(source),tomei_taiheiyo=str(source)))
        ac=manager.prepare(self.ac);tomei=manager.prepare(self.tomei)
        self.assertNotEqual(ac,tomei);self.assertEqual(ac,self.path/'app/data/ac_toyoake')
        store=Store(ac,default_template=self.ac,form_id='ac_toyoake')
        try:self.assertEqual(store.template()['line_color'],t['line_color']);self.assertEqual(store.get(record['id']),record)
        finally:store.close()
        self.assertFalse((tomei/'records.sqlite3').exists());self.assertIn('別帳票',manager.notices['tomei_taiheiyo'])
        self.assertEqual({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in source.iterdir() if f.is_file()},before)
        self.assertEqual(len(list((self.path/'app/data/backups').glob('*/ac_toyoake/records.sqlite3'))),1)
        self.assertEqual(len(list((self.path/'app/data/backups').glob('*/tomei_taiheiyo/records.sqlite3'))),1)

    def test_committed_wal_and_db_authority_are_preserved_in_backup(self):
        folder=self.path/'wal';store=Store(folder,default_template=self.ac,form_id='ac_toyoake')
        try:
            store.set_template(self.ac);record=store.save(blank(self.ac),self.ac)
            # A mismatched portable mirror must not override authoritative DB settings.
            atomic_json(folder/'template.json',self.tomei)
            manager=AppStorage(self.path/'wal-app',{'ac_toyoake':str(folder)})
            dest=manager.prepare(self.ac)
            other=Store(dest,default_template=self.ac,form_id='ac_toyoake')
            try:self.assertEqual(other.get(record['id']),record);self.assertEqual(other.template()['form_id'],'ac_toyoake')
            finally:other.close()
            backups=list((self.path/'wal-app/data/backups').glob('*/ac_toyoake/template.json'))
            self.assertEqual(json.loads(backups[0].read_text(encoding='utf8'))['form_id'],'tomei_taiheiyo')
            self.assertEqual(json.loads((dest/'template.json').read_text(encoding='utf8'))['form_id'],'ac_toyoake')
        finally:store.close()

    def test_existing_automatic_foreign_settings_and_marker_are_not_overwritten(self):
        manager=AppStorage(self.path/'guard');target=manager.path('tomei_taiheiyo');target.mkdir(parents=True)
        atomic_json(target/'template.json',self.ac);raw=(target/'template.json').read_bytes()
        with self.assertRaisesRegex(StorageError,'別の帳票'):manager.prepare(self.tomei)
        self.assertEqual((target/'template.json').read_bytes(),raw);self.assertFalse((target/'records.sqlite3').exists())
        (target/'template.json').unlink();atomic_json(target/MARKER,{'form_id':'ac_toyoake'})
        with self.assertRaisesRegex(StorageError,'別の帳票'):manager.prepare(self.tomei)

    def test_nonempty_unidentified_legacy_data_is_backed_up_and_not_silently_dropped(self):
        folder=self.path/'unidentified';folder.mkdir();con=sqlite3.connect(folder/'records.sqlite3')
        con.execute('create table records(id text)');con.execute("insert into records values('keep')");con.commit();con.close()
        before=(folder/'records.sqlite3').read_bytes()
        manager=AppStorage(self.path/'unknown-app',{'ac_toyoake':str(folder)})
        with self.assertRaisesRegex(StorageError,'帳票種別'):manager.prepare(self.ac)
        self.assertEqual((folder/'records.sqlite3').read_bytes(),before)
        self.assertFalse(manager.path('ac_toyoake').exists())
        self.assertTrue(list((self.path/'unknown-app/data/backups').glob('*/ac_toyoake/records.sqlite3')))

    def test_blocked_and_denied_storage_never_select_another_folder(self):
        root=self.path/'blocked';root.mkdir();(root/'data').write_text('occupied',encoding='ascii')
        manager=AppStorage(root)
        with self.assertRaisesRegex(StorageError,'書き込み可能'):manager.prepare(self.ac)
        self.assertEqual((root/'data').read_text(encoding='utf-8'),'occupied')
        with patch('app_storage._probe',side_effect=PermissionError('access denied')):
            with self.assertRaisesRegex(StorageError,'保存先の指定は不要'):AppStorage(self.path/'denied').prepare(self.ac)

    def test_shell_round_trips_two_forms_without_picker_or_color_mix(self):
        root=tk.Tk();root.withdraw();errors=[]
        with patch('main_app.filedialog.askdirectory',side_effect=AssertionError('Storage picker must never open')),patch('main_app.messagebox.showerror',side_effect=lambda *a,**k:errors.append(a)):
            home=Home(root,{},storage_root=self.path/'shell')
            try:
                for row in self.rows[:2]:home.open(row);root.update()
                self.assertFalse(errors);self.assertEqual(set(home.screens),{'ac_toyoake','tomei_taiheiyo'})
                ac=home.screens['ac_toyoake'];tomei=home.screens['tomei_taiheiyo']
                values={}
                for fid,screen in home.screens.items():
                    data=blank(screen.template);screen.set_values(data);screen.save();values[fid]=copy.deepcopy(data)
                ac_color=copy.deepcopy(ac.template['line_color']);tomei_color=copy.deepcopy(tomei.template['line_color'])
                tomei.blue_ink_settings.value.set('55');tomei.save_settings()
                self.assertEqual(ac.template['line_color'],ac_color);self.assertEqual(tomei.template['line_color'],tomei_color)
                for row in self.rows[:2]:
                    screen=home.screens[row['id']];screen.new(check=False);screen.close();home.open(row);root.update()
                    reopened=home.screens[row['id']]
                    self.assertEqual(reopened.store.list()[0]['data'],values[row['id']])
                self.assertEqual(home.screens['ac_toyoake'].template['line_color'],ac_color)
                self.assertEqual(home.screens['tomei_taiheiyo'].template['blue_ink_density'],.55)
                self.assertEqual(tk.ttk.Style(root).theme_use(),'vista' if 'vista' in tk.ttk.Style(root).theme_names() else 'default');self.assertFalse(errors)
            finally:home.dispose()

if __name__=='__main__':unittest.main(verbosity=2)
