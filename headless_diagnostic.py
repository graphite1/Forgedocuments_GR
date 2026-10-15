"""Packaged-runtime validation with no Tk roots, user profiles or printer calls."""
import copy,hashlib,json,sys,tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import pymupdf
import core
from app_storage import AppStorage
from form_registry import catalog,default_definition


def run(destination,cid_font=False):
    output=Path(destination).resolve();output.mkdir(parents=True,exist_ok=True)
    evidence=dict(status='running',gui_checked=False,physical_printing=False,source_pdf_rechecked=False,
                  synthetic_only=True,windows_executable=sys.platform=='win32' and bool(getattr(sys,'frozen',False)),forms={})
    try:
        with ExitStack() as stack:
            stack.enter_context(patch('tkinter.Tk',side_effect=AssertionError('GUI forbidden in headless diagnostic')))
            stack.enter_context(patch('tkinter.Toplevel',side_effect=AssertionError('GUI forbidden in headless diagnostic')))
            if cid_font:
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.cidfonts import UnicodeCIDFont
                pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
                stack.enter_context(patch('core.font_name',return_value='HeiseiKakuGo-W5'))
            evidence['font_mode']='CID substitute; Windows fallback appearance unverified' if cid_font else 'existing Windows fonts'
            from tomei_print_font import bundle_files,OBSERVED_SUPPORTED,OBSERVED_SHA256
            assets=bundle_files();evidence['print_font_sha256']=OBSERVED_SHA256
            evidence['print_font_characters']=''.join(sorted(OBSERVED_SUPPORTED));assert len(OBSERVED_SUPPORTED)==46
            for p in assets:assert p.is_file()
            with tempfile.TemporaryDirectory(prefix='isolated-',dir=output) as work:
                work=Path(work);manager=AppStorage(work/'application');paths={r['id']:manager.prepare(default_definition(r)) for r in catalog()}
                assert len(set(paths.values()))==len(paths);evidence['storage_isolated']=True
                from aktio.diagnostics import check_data
                evidence['forms']['aktio_receipt']=check_data(work/'aktio')
                from tomei_screen import DEFINITION
                from tomei_preset import with_bundled_preset
                t=with_bundled_preset(core.load_template(DEFINITION));t['input_print_style']='plain'
                values=core.blank(t);values.update(recipient='角文',concrete_type='普通',mix_plan_number='20300102-1234')
                field=next(f for f in t['fields'] if f['type']=='multi_choice');values[field['id']]=json.dumps([field['options'][0]['key']])
                one=work/'tomei.pdf';core.render_pdf(one,[values],t)
                with pymupdf.open(one) as doc:
                    spans=[s for b in doc[0].get_text('dict')['blocks'] if b['type']==0 for l in b['lines'] for s in l['spans']]
                    printed=''.join(s['text'].replace(' ','') for s in spans if 'TomeiObservedPrint' in s['font'])
                    assert all(value in printed for value in ('角文','殿','普通','配合計画書NO.20300102-1234')),printed
                    assert '納入書（計画）' in doc[0].get_text()
                four=copy.deepcopy(t);four['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
                core.render_pdf(work/'four.pdf',[values]*5,four)
                with pymupdf.open(work/'four.pdf') as doc:assert [len(p.search_for('納入書（計画）')) for p in doc]==[4,1]
                store=core.Store(paths['tomei_taiheiyo'],default_template=t,form_id='tomei_taiheiyo')
                try:r=store.save(values,t);assert store.get(r['id'])['data']==values
                finally:store.close()
                evidence['forms']['tomei_taiheiyo']=dict(status='passed',observed_japanese_and_plan_number=True,four_up_notices=[4,1],inferred_check_separate=True)
                ac=default_definition(next(r for r in catalog() if r['id']=='ac_toyoake'));data=core.blank(ac);data['number']='SYNTHETIC-0001'
                store=core.Store(paths['ac_toyoake'],default_template=ac,form_id='ac_toyoake')
                try:r=store.save(data,ac);assert store.get(r['id'])['data']==data
                finally:store.close()
                core.render_pdf(work/'ac.pdf',[data],ac);evidence['forms']['ac_toyoake']=dict(status='passed',save_and_pdf=True)
        evidence['status']='passed'
    except Exception as error:
        evidence.update(status='failed',error=repr(error));raise
    finally:core.atomic_json(output/'headless-diagnostic.json',evidence)
    return evidence
