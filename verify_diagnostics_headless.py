"""Exercise diagnostic dispatch and AKTIO's controller contract without Tk."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from verify_aktio import AktioScreenHeadlessChecks
from form_registry import catalog


class DiagnosticHeadlessChecks(unittest.TestCase):
    def test_packaged_entrypoint_uses_headless_path_and_checks_all_forms(self):
        from main_app import main
        with tempfile.TemporaryDirectory() as p,patch('sys.argv',['app.py','--headless-diagnostic','--diagnostic-output',p,'--cid-font']),patch('tkinter.Tk',side_effect=AssertionError('GUI forbidden')):
            main();report=json.loads((Path(p)/'headless-diagnostic.json').read_text())
            self.assertEqual(report['status'],'passed');self.assertFalse(report['gui_checked'])
            self.assertEqual(set(report['forms']),{'ac_toyoake','tomei_taiheiyo','aktio_receipt'})
            self.assertEqual(len(report['print_font_characters']),46)
            self.assertTrue(report['forms']['aktio_receipt']['plan_notice_inside_every_receipt'])

    def test_desktop_dispatch_does_not_use_generic_screen_attributes_for_aktio(self):
        import desktop_diagnostic
        row=next(r for r in catalog() if r['id']=='aktio_receipt')
        with tempfile.TemporaryDirectory() as p,patch('desktop_diagnostic.catalog',return_value=[row]),patch('storage_diagnostic.run',return_value={'status':'passed'}),patch('tkinter.Tk',side_effect=AssertionError('AKTIO data diagnostic is headless')):
            report=desktop_diagnostic.run(p)
            self.assertEqual(report['status'],'passed');self.assertEqual(report['forms']['aktio_receipt']['status'],'passed')


class AktioDiagnosticControllerChecks(unittest.TestCase):
    setUp=AktioScreenHeadlessChecks.setUp

    def test_storage_diagnostic_uses_aktio_contract_and_reopen_history(self):
        from aktio.diagnostics import exercise_screen
        from aktio.ui import Application
        document=exercise_screen(self.app,self.root)
        self.app.store.close();self.app=Application(self.root,self.folder)
        self.assertEqual(self.app.document(),document)

if __name__=='__main__':unittest.main(verbosity=2)
