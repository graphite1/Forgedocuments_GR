"""Fail-closed preview packaging and download verification, without network writes."""
import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from tools import preview_release as preview


class PreviewReleaseChecks(unittest.TestCase):
    def package(self,path,extra=None):
        files={name:(b'MZsynthetic' if name.endswith('.exe') else b'{}') for name in preview.PACKAGE_NAMES-{'release_files.json'}}
        files['README.txt']=b'Unsigned prerelease for validation'
        for name in ('template.json','forms.json','version.json','update_config.json'):files[name]=(preview.ROOT/name).read_bytes()
        manifest={name:preview.sha256(raw) for name,raw in files.items()}
        files['release_files.json']=json.dumps(manifest).encode()
        if extra:files.update(extra)
        with zipfile.ZipFile(path,'w') as z:
            for name,raw in files.items():z.writestr(name,raw)
        return files

    def test_zip_allowlist_crc_and_payload_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'preview.zip';self.package(path)
            self.assertEqual(len(preview.audit_zip(path)),6)
            self.package(path,{'original.pdf':b'private'})
            with self.assertRaisesRegex(ValueError,'Unexpected'):preview.audit_zip(path)
            files=self.package(path)
            with zipfile.ZipFile(path,'w') as z:
                for name,raw in files.items():z.writestr(name,b'changed' if name=='template.json' else raw)
            with self.assertRaisesRegex(ValueError,'hash mismatch'):preview.audit_zip(path)

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
        source='1'*40;name=f"Forgedocuments_GR-{preview.version()['version']}-windows-x64.zip"
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
