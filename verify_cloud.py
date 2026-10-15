"""Run isolated cloud checks with existing dependencies and no private keys.

--cid-font explicitly uses ReportLab's existing Japanese CID font for this
Linux environment. It does not change production font selection or templates.
"""
import argparse
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import core
import updates
from verify import Verification
from verify_platform import PlatformChecks
from verify_regressions import Regressions
from verify_layout_inputs import LayoutAndInputs
from verify_tomei import TomeiChecks
from verify_background import BackgroundChecks
from verify_fixed_footer import FixedFooterChecks
from verify_public_background import PublicBackgroundChecks
from verify_input_print import InputPrintChecks
from verify_transparency import TransparencyChecks
from verify_sample_font import FontRunChecks,SampleFontChecks
from verify_numeric_plan import NumericPlanChecks
from verify_blue_ink import BlueInkChecks
from verify_app_storage import AppStorageChecks
from verify_theme_headless import ThemeHeadlessChecks
from verify_aktio import AktioChecks,AktioScreenHeadlessChecks
from verify_tomei_font_marks import TomeiFontMarkChecks
from verify_diagnostics_headless import DiagnosticHeadlessChecks,AktioDiagnosticControllerChecks
from verify_preview_release import PreviewReleaseChecks


class KeyFreePlatformChecks(PlatformChecks):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)

    def manifest(self):
        return {'sequence':updates.metadata()['sequence']+1,'version':'1.4.0'}

    @unittest.skip('Requires a new temporary signing key; use the existing published-manifest check instead')
    def test_signature_and_tampering(self):pass

    @unittest.skip('Signed EXE staging needs a genuine signed Windows ZIP; no new keys in this task')
    def test_zip_traversal_and_stage_integrity(self):pass


def suite():
    loader=unittest.defaultTestLoader
    return unittest.TestSuite(loader.loadTestsFromTestCase(c) for c in (Verification,KeyFreePlatformChecks,Regressions,LayoutAndInputs,TomeiChecks,BackgroundChecks,FixedFooterChecks,PublicBackgroundChecks,InputPrintChecks,TransparencyChecks,FontRunChecks,SampleFontChecks,NumericPlanChecks,BlueInkChecks,AppStorageChecks,ThemeHeadlessChecks,AktioChecks,AktioScreenHeadlessChecks,TomeiFontMarkChecks,DiagnosticHeadlessChecks,AktioDiagnosticControllerChecks,PreviewReleaseChecks))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cid-font',action='store_true');parser.add_argument('--headless',action='store_true',help='Never create a Tk window; GUI-dependent tests are explicitly skipped')
    parser.add_argument('--report',type=Path,help='Write public-safe aggregate test evidence')
    args=parser.parse_args()
    from contextlib import ExitStack
    stack=ExitStack()
    if args.headless:
        stack.enter_context(patch('tkinter.Tk',side_effect=unittest.SkipTest('GUI unavailable/prohibited: headless run')))
        stack.enter_context(patch('tkinter.Toplevel',side_effect=unittest.SkipTest('GUI unavailable/prohibited: headless run')))
    if args.cid_font:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
        pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))
        print('Cloud checks: Japanese CID substitute font; Windows MS Gothic appearance remains unverified.',flush=True)
        with patch('core.font_name',return_value='HeiseiKakuGo-W5'),patch('core.styled_font',side_effect=lambda t,style,default:'HeiseiMin-W3' if style=='serif' else default):
            result=unittest.TextTestRunner(verbosity=2).run(suite())
    else:result=unittest.TextTestRunner(verbosity=2).run(suite())
    stack.close()
    if args.report:
        core.atomic_json(args.report,{'status':'passed' if result.wasSuccessful() else 'failed','total':result.testsRun,'passed':result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),'skipped':len(result.skipped),'failures':len(result.failures),'errors':len(result.errors),'headless':args.headless,'cid_substitute':args.cid_font,'skip_reasons':sorted(set(reason for test,reason in result.skipped))})
    raise SystemExit(not result.wasSuccessful())
