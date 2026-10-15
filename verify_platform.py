"""Platform regression checks with isolated records and temporary signing keys."""
import base64,copy,hashlib,json,os,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import tkinter as tk
from core import Store,load_template,blank,render_pdf
from pdf_view import PDFView
from form_registry import catalog
import updates
from main_app import Home,read_profiles

class PlatformChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.key=Ed25519PrivateKey.generate()
        self.cfg={'app_id':'forgedocuments-gr','key_id':'test','public_key':base64.b64encode(self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode(),'hub_url':'https://gr-release-hub.rinntyu2000.chatgpt.site'}

    def tearDown(self):self.temp.cleanup()

    def manifest(self):
        m={'app_id':self.cfg['app_id'],'version':'1.4.0','sequence':2,'schema_version':1,'minimum_updater_version':'1.0.0','published_at':'2026-10-14T00:00:00Z','release_notes':'test','download_url':self.cfg['hub_url']+'/api/apps/forgedocuments-gr/releases/2/download','sha256':'0'*64,'key_id':'test'}
        m['signature']=base64.b64encode(self.key.sign(updates.canonical(m))).decode();return m

    def test_signature_and_tampering(self):
        m=self.manifest();updates.validate_manifest(m,self.cfg)
        bad=copy.deepcopy(m);bad['release_notes']='modified'
        with self.assertRaises(ValueError):updates.validate_manifest(bad,self.cfg)
        for field,value in [('app_id','other'),('download_url','https://other.test/a'),('sequence',True),('minimum_updater_version','99.0.0')]:
            bad=copy.deepcopy(m);bad[field]=value
            with self.assertRaises(ValueError):updates.validate_manifest(bad,self.cfg)

    def test_version_and_catalog(self):
        self.assertTrue(updates.newer(self.manifest()))
        m=self.manifest();m['sequence']=1;self.assertFalse(updates.newer(m))
        rows=catalog();self.assertEqual(rows[0]['id'],'ac_toyoake')
        p=self.path/'catalog.json';p.write_text(json.dumps([rows[0],rows[0]]))
        with self.assertRaises(ValueError):catalog(p)

    def archive(self,filename='Forgedocuments GR.exe'):
        p=self.path/'update.zip';files={filename:b'fake exe','version.json':json.dumps({'app_id':'forgedocuments-gr','version':'1.4.0','sequence':2,'data_schema':1}).encode()}
        with zipfile.ZipFile(p,'w') as z:
            for name,raw in files.items():z.writestr(name,raw)
            z.writestr('release_files.json',json.dumps({name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}))
        return p

    def test_zip_traversal_and_stage_integrity(self):
        p=self.archive('../escape.exe')
        with self.assertRaises(ValueError):updates.extract_archive(p,self.path/'target')
        self.assertFalse((self.path/'escape.exe').exists())
        p=self.archive();m=self.manifest();m.pop('signature');m['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();m['signature']=base64.b64encode(self.key.sign(updates.canonical(m))).decode()
        with patch.object(updates,'config',return_value=self.cfg):
            stage=updates.stage_archive(p,m,self.path/'install');updates.verify_staged(stage)
            (stage/updates.EXE).write_bytes(b'changed')
            with self.assertRaises(ValueError):updates.verify_staged(stage)

    def test_backup_and_preserve_user_data(self):
        folder=self.path/'records';s=Store(folder);t=load_template();d=blank(t);d['number']='001A';r=s.save(d,t);s.set_template(t);s.close()
        original=(folder/'records.sqlite3').read_bytes()
        backup=updates.backup_data([folder],self.path/'app');self.assertEqual((folder/'records.sqlite3').read_bytes(),original)
        restored=Store(backup/'0');self.assertEqual(restored.get(r['id'])['data']['number'],'001A');restored.close()

    def test_pointer_zoom_and_right_drag(self):
        p=self.path/'preview.pdf';render_pdf(p,[blank(load_template()),blank(load_template())],load_template())
        root=tk.Tk();root.withdraw();view=PDFView(root);view.pack();view.set_pdf(p);root.update()
        point=(40,60);before=((point[0]-view.offset[0])/view.zoom,(point[1]-view.offset[1])/view.zoom)
        view.wheel(SimpleNamespace(state=4,delta=120,x=point[0],y=point[1]));root.update()
        after=((point[0]-view.offset[0])/view.zoom,(point[1]-view.offset[1])/view.zoom)
        self.assertAlmostEqual(before[0],after[0]);self.assertAlmostEqual(before[1],after[1])
        old=view.offset;view.pan_start(SimpleNamespace(x=10,y=10));view.pan_move(SimpleNamespace(x=30,y=45));view.pan_end(None)
        self.assertEqual(view.offset,(old[0]+20,old[1]+35));view.turn(1);self.assertEqual(view.page,1)
        view.actual();self.assertEqual(view.zoom,1);root.destroy()

    def test_shell_copies_ac_to_automatic_storage_and_preserves_old_folder(self):
        folder=self.path/'ac';folder.mkdir();root=tk.Tk();root.withdraw()
        home=Home(root,{'ac_toyoake':str(folder)},storage_root=self.path/'install');home.open(catalog()[0]);root.update()
        screen=home.screens['ac_toyoake'];self.assertEqual(screen.store.directory,self.path/'install/data/ac_toyoake');self.assertTrue(folder.is_dir());self.assertIn('エーシー帳票',screen.root.title());home.close()

    def test_legacy_profile_migration(self):
        p=self.path/'Roaming'/'ForgedocumentsGR'/'profiles.json';old=p.parent.parent/'AcToyoakeApp';old.mkdir(parents=True)
        (old/'preferences.json').write_text(json.dumps({'directory':str(self.path/'old-ac')}))
        with patch('main_app.profiles_path',return_value=p):self.assertEqual(read_profiles()['ac_toyoake'],str(self.path/'old-ac'))
        self.assertFalse(p.exists())

    def test_folder_button_opens_current_folder_without_selecting_storage(self):
        from ac_screen import App
        root=tk.Tk();root.withdraw();screen=App(root,self.path/'button-ac');calls=[]
        screen.folder_open_handler=lambda:calls.append('open')
        bar=root.winfo_children()[0]
        button=next(w for w in bar.winfo_children() if w.winfo_class()=='TButton' and w.cget('text')=='保存フォルダーを開く')
        button.invoke();self.assertEqual(calls,['open']);screen.store.close();root.destroy()

if __name__=='__main__':unittest.main(verbosity=2)
