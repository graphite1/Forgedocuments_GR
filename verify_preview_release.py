"""Fail-closed preview packaging and download verification, without network writes."""
import hashlib,io,json,tempfile,unittest,zipfile,subprocess
from pathlib import Path
from unittest.mock import patch
from tools import preview_release as preview


class PreviewReleaseChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.source_bundle import stage
        cls.source=subprocess.check_output(['git','write-tree'],cwd=preview.ROOT,text=True).strip()
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'source';stage(folder,cls.source,require_build=False)
            cls.source_files={'source/'+p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}

    def package(self,path,extra=None):
        files={name:(b'MZsynthetic' if name.endswith('.exe') else b'{}') for name in preview.PACKAGE_NAMES-{'release_files.json'}}
        files['README.txt']=b'Unsigned prerelease for validation'
        for name in ('template.json','forms.json','version.json','update_config.json'):files[name]=(preview.ROOT/name).read_bytes()
        files.update(self.source_files);files['examples/AKTIO-output-sample.png']=b'SYNTHETIC TEST PNG'
        manifest={name:preview.sha256(raw) for name,raw in files.items()}
        files['release_files.json']=json.dumps(manifest).encode()
        if extra:files.update(extra)
        with zipfile.ZipFile(path,'w') as z:
            for name,raw in files.items():z.writestr(name,raw)
        return files

    def test_zip_allowlist_crc_and_payload_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'preview.zip';self.package(path)
            self.assertEqual(len(preview.audit_zip(path)),len(self.source_files)+7)
            self.package(path,{'original.pdf':b'private'})
            with self.assertRaisesRegex(ValueError,'Unexpected'):preview.audit_zip(path)
            files=self.package(path)
            with zipfile.ZipFile(path,'w') as z:
                for name,raw in files.items():z.writestr(name,b'changed' if name=='template.json' else raw)
            with self.assertRaisesRegex(ValueError,'hash mismatch'):preview.audit_zip(path)

    def test_source_snapshot_rejects_changes_caches_missing_notices_and_wrong_commit(self):
        from tools.source_bundle import audit
        files=dict(self.source_files)
        self.assertEqual(audit(files.__getitem__,files,self.source)['source_commit'],self.source)
        with self.assertRaisesRegex(ValueError,'identity'):audit(files.__getitem__,files,'2'*40)
        files['source/source-runtime/data/aktio_receipt/records.sqlite3']=b'PRIVATE'
        with self.assertRaisesRegex(ValueError,'Unexpected'):audit(files.__getitem__,files,self.source)
        del files['source/source-runtime/data/aktio_receipt/records.sqlite3']
        files['source/app.py']+=b'CHANGED'
        with self.assertRaisesRegex(ValueError,'hash mismatch'):audit(files.__getitem__,files,self.source)
        self.assertNotIn('source/start_auto.bat',self.source_files)
        self.assertNotIn('source/.source-venv',self.source_files)
        bat=self.source_files['source/start_source.bat'];self.assertIn(b'\r\n',bat);self.assertNotIn(b'\n',bat.replace(b'\r\n',b''))

    def test_source_launcher_uses_only_venv_and_isolated_application_storage(self):
        import source_bootstrap as launcher
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);env=launcher.environment(root)
            self.assertEqual(Path(env['FORGEDOCUMENTS_INSTALL_ROOT']),root/'source-runtime')
            self.assertEqual(Path(env['APPDATA']),root/'source-runtime/profile')
            self.assertEqual(env.get('PATH'),__import__('os').environ.get('PATH'))
            python=root/'.source-venv/Scripts/python.exe'
            with patch.object(launcher,'BASE',root),patch.object(launcher,'verify_venv',return_value=python),patch.object(launcher.subprocess,'run',return_value=Mock(returncode=0)) as run:
                self.assertEqual(launcher.run(['--headless-diagnostic']),0)
                self.assertEqual(run.call_args.args[0],[str(python),'-B',str(root/'app.py'),'--headless-diagnostic'])
                self.assertEqual(run.call_args.kwargs['cwd'],root)
        with patch.object(launcher.sys,'version_info',(3,13)),self.assertRaisesRegex(RuntimeError,'3.14'):launcher.check_python()

    def test_guard_rejects_existing_tag_and_private_repository(self):
        class Client:
            def api(self,path):
                if path.endswith(preview.REPOSITORY):return {'visibility':'public'}
                return {'id':1} if '/releases/tags/' in path else None
        with patch('tools.preview_release.source_check'):
            with self.assertRaisesRegex(ValueError,'already exists'):preview.guard(Client(),'1'*40,'v'+preview.version()['version']+'-preview.1')
        client=Client();client.api=lambda path:{'visibility':'private'}
        with self.assertRaisesRegex(ValueError,'public'):preview.release_context(client,'1'*40,'v'+preview.version()['version']+'-preview.1')

    def test_redirect_removes_token_for_another_host(self):
        import urllib.request
        req=urllib.request.Request('https://api.github.com/asset',headers={'Authorization':'Bearer SYNTHETIC','Accept':'application/octet-stream'})
        target=preview.SafeRedirect().redirect_request(req,None,302,'Found',{},'https://release-assets.githubusercontent.com/synthetic')
        self.assertIsNone(target.get_header('Authorization'))
        target=preview.SafeRedirect().redirect_request(req,None,302,'Found',{},'https://api.github.com/another')
        self.assertEqual(target.get_header('Authorization'),'Bearer SYNTHETIC')

    def test_public_downloads_resolve_tag_and_verify_every_byte(self):
        source=self.source;name=f"Forgedocuments_GR-{preview.version()['version']}-windows-x64.zip"
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'preview.zip';self.package(archive);zip_bytes=archive.read_bytes()
        report=dict(source_commit=source,signed=False,archive=name,sha256=preview.sha256(zip_bytes),packaged_diagnostic={'status':'passed'})
        data={name:zip_bytes,'preview-validation.json':json.dumps(report).encode()}
        data['SHA256SUMS.txt']=''.join(f'{preview.sha256(raw)}  {n}\n' for n,raw in data.items()).encode()
        release=dict(tag_name='v'+preview.version()['version']+'-preview.1',prerelease=True,draft=False,html_url='https://github.com/synthetic',
                     assets=[dict(name=n,browser_download_url='https://github.com/'+n,digest='sha256:'+preview.sha256(raw)) for n,raw in data.items()])
        class Client:
            def api(self,path):return {'object':{'type':'commit','sha':source}}
            def request(self,url,authenticated=True):
                if authenticated:raise AssertionError('Public download must not send a token')
                return data[url.split('/')[-1]]
        client=Client();result=preview.verify_assets(client,release,source,expected=data,public=True)
        self.assertTrue(result['public_download_verified']);self.assertEqual(result['sha256'],report['sha256'])
        tampered=dict(data,**{name:b'CHANGED'})
        with self.assertRaisesRegex(ValueError,'differ'):preview.verify_assets(client,release,source,expected=tampered,public=True)
        with self.assertRaisesRegex(ValueError,'tag'):preview.verify_assets(client,release,'2'*40,expected=data,public=True)
        with self.assertRaisesRegex(ValueError,'prerelease'):preview.verify_assets(client,dict(release,prerelease=False),source,expected=data,public=True)

    def test_embedded_assets_are_exact_and_original_pdf_is_rejected(self):
        from types import ModuleType
        from tomei_preset import public_bundle_files
        from tomei_print_font import bundle_files
        from aktio.asset_files import bundle_files as aktio_files
        payload={p.relative_to(preview.ROOT).as_posix():p.read_bytes() for p in [*public_bundle_files(),*bundle_files(),*aktio_files()]}
        for n in ('forms.json','template.json','version.json','update_config.json','templates/tomei_taiheiyo.json','templates/aktio_receipt.json'):payload[n]=(preview.ROOT/n).read_bytes()
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('encodings/ascii.pyc',b'SYNTHETIC BYTECODE')
        payload['base_library.zip']=stream.getvalue()
        class Reader:
            def __init__(self,path):self.toc=payload
            def extract(self,name):return payload[name]
        module=ModuleType('PyInstaller.archive.readers');module.CArchiveReader=Reader
        with patch.dict('sys.modules',{'PyInstaller':ModuleType('PyInstaller'),'PyInstaller.archive':ModuleType('PyInstaller.archive'),'PyInstaller.archive.readers':module}):
            self.assertFalse(preview.audit_embedded('synthetic.exe')['forbidden_embedded_files'])
            payload['original.pdf']=b'not a real PDF'
            with self.assertRaisesRegex(ValueError,'Forbidden'):preview.audit_embedded('synthetic.exe')
            del payload['original.pdf']
            payload['user-source.zip']=b'forbidden source archive'
            with self.assertRaisesRegex(ValueError,'Forbidden'):preview.audit_embedded('synthetic.exe')
            del payload['user-source.zip'];payload['assets/tomei-observed-46-v2.ttf']=b'changed'
            with self.assertRaisesRegex(ValueError,'mismatch'):preview.audit_embedded('synthetic.exe')

    def test_japanese_result_can_be_printed_to_a_windows_cp1252_pipe(self):
        from contextlib import redirect_stdout
        raw=io.BytesIO();stream=io.TextIOWrapper(raw,encoding='cp1252',write_through=True)
        result={'characters':'角文殿普通配合計画書NO.0123456789-','status':'passed'}
        with redirect_stdout(stream):preview.print_result(result)
        self.assertEqual(json.loads(raw.getvalue().decode('cp1252')),result)
        stream.detach()

    def test_no_token_creation_and_no_non_github_endpoints(self):
        with self.assertRaisesRegex(ValueError,'existing'):preview.GitHub().api('repos/'+preview.REPOSITORY)
        with self.assertRaisesRegex(ValueError,'endpoint'):preview.GitHub('SYNTHETIC').request('https://example.com/no')
        with patch('tools.preview_release.sys.platform','linux'),self.assertRaisesRegex(ValueError,'Windows'):preview.verify_build('unused','1'*40,'unused')

if __name__=='__main__':unittest.main(verbosity=2)
