"""Actual desktop-shell checks, using only isolated synthetic records."""
import copy,hashlib,json,os,sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import pymupdf
import core
import updates
from form_registry import catalog,default_definition
from main_app import Home


def _values(template):
    values=core.blank(template)
    for key,value in [('number','1001'),('vehicle_number','1234'),('recipient','検証')]:
        if key in values:values[key]=value
    return values


def _exercise(root,home,directory):
    rows=catalog();saved={};colors={};previews={};theme=ttk.Style(root).theme_use()
    for row in rows:
        home.open(row);root.update()
        assert row['id'] in home.screens,row['id']
        screen=home.screens[row['id']];screen.root.withdraw()
        assert screen.store.directory==home.storage.root/'data'/row['id']
        if row['id']=='aktio_receipt':
            from aktio.diagnostics import exercise_screen
            saved[row['id']]=exercise_screen(screen,root);previews[row['id']]=0
            continue
        values=_values(screen.template);screen.set_values(values);screen.save()
        saved[row['id']]=copy.deepcopy(values)
        if row['id']=='ac_toyoake':
            t=copy.deepcopy(screen.template);t['line_color']=[.18,.28,.82]
            screen.json_edit.delete('1.0','end');screen.json_edit.insert('1.0',json.dumps(t,ensure_ascii=False));screen.save_settings()
        else:
            screen.blue_ink_settings.value.set('55');screen.save_settings()
        screen.set_values(values)
        for _ in range(3):screen.preview_current();root.update()
        previews[row['id']]=3
        single=directory/(row['id']+'-single.pdf');core.render_pdf(single,[values],screen.template)
        with pymupdf.open(single) as doc:
            assert doc[0].get_pixmap().samples==screen.preview_view.doc[0].get_pixmap().samples
            doc[0].get_pixmap(dpi=130,alpha=False).save(directory/(row['id']+'-single.png'))
        t=copy.deepcopy(screen.template);t['page_layout'].update(paper='A4',rows=2,columns=2,scale='fit')
        four=directory/(row['id']+'-four-up.pdf');core.render_pdf(four,[values]*5,t)
        with pymupdf.open(four) as doc:
            assert len(doc)==2
            if row['id']=='tomei_taiheiyo':
                assert [len(p.search_for('納入書（計画）')) for p in doc]==[4,1]
                for page in doc:
                    for box in page.search_for('納入書（計画）'):assert page.rect.contains(box)
        colors[row['id']]={k:copy.deepcopy(screen.template.get(k)) for k in ['line_color','input_color','blue_ink_density','input_density','input_transparency']}
        screen.new(check=False)
    assert ttk.Style(root).theme_use()==theme
    # Repeated round trips with both forms, never selecting a storage folder.
    for _ in range(2):
        for row in rows:
            screen=home.screens[row['id']];screen.close();home.open(row);root.update()
            screen=home.screens[row['id']];screen.root.withdraw()
            if row['id']=='aktio_receipt':
                assert screen.document()==saved[row['id']]
                continue
            records=screen.store.list()
            assert records[-1]['data']==saved[row['id']]
            assert {k:screen.template.get(k) for k in colors[row['id']]}==colors[row['id']]
            screen.set_values(saved[row['id']]);screen.preview_current();root.update()
            previews[row['id']]+=1;screen.new(check=False)
    return {'previews':previews,'round_trips':2,'saved_records_survive':True,'colors_independent':True,
            'colors':colors,'single_and_four_up':True,'preview_pdf_pixels_identical':True,
            'theme_stable':True,'directories':home.profiles}


def run(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    results={};errors=[]
    with patch('main_app.filedialog.askdirectory',side_effect=AssertionError('Storage picker is forbidden')),patch('main_app.messagebox.showerror',side_effect=lambda title,message,**kw:errors.append(str(message))):
        # In the packaged test, exercise the production default beside the actual
        # standalone EXE (or the updater's stable install root), not an injected
        # storage_root. Source-only checks keep their own isolated directory.
        fresh_root=updates.install_root() if getattr(sys,'frozen',False) else directory/'fresh-install'
        with patch.dict(os.environ,{'FORGEDOCUMENTS_INSTALL_ROOT':str(fresh_root)}):
            root=tk.Tk();root.withdraw();home=Home(root,{})
            try:results['fresh']=_exercise(root,home,directory)
            finally:home.dispose()
        results['production_install_root_default']=True
        assert not errors,errors
        # Reproduce the user's old layout: AC folder plus an extracted app folder
        # containing an AC template and an empty DB assigned to the Tomei profile.
        legacy=directory/'legacy-ac';wrong=directory/'legacy-extracted-app'
        ac=default_definition(catalog()[0]);store=core.Store(legacy,default_template=ac,form_id='ac_toyoake')
        try:store.set_template(ac);store.save(core.blank(ac),ac)
        finally:store.close()
        wrong.mkdir();core.atomic_json(wrong/'template.json',ac)
        store=core.Store(wrong,default_template=ac,form_id='ac_toyoake');store.close()
        profiles={'ac_toyoake':str(legacy),'tomei_taiheiyo':str(wrong)}
        files=[p for d in (legacy,wrong) for p in d.iterdir() if p.is_file()]
        hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        root=tk.Tk();root.withdraw();home=Home(root,profiles,storage_root=directory/'migrated-install')
        try:results['migrated']=_exercise(root,home,directory)
        finally:home.dispose()
        assert not errors,errors
        assert hashes=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        results['legacy_sources_unchanged']=True
        results['legacy_backups']=len(list((directory/'migrated-install/data/backups').glob('*/**/source.json')))
        # Actual path collision prevents writing, without changing ACLs/security.
        blocked=directory/'blocked-install';blocked.mkdir();(blocked/'data').write_text('occupied',encoding='ascii')
        root=tk.Tk();root.withdraw();home=Home(root,{},storage_root=blocked)
        try:
            for row in catalog():home.open(row)
            assert not home.screens
            assert len(errors)==len(catalog()) and all('書き込み可能' in e and '保存先の指定は不要' in e for e in errors)
            assert (blocked/'data').read_text()=='occupied'
        finally:home.dispose()
        results.update(no_storage_picker=True,blocked_write_clear_error=True,blocked_write_no_fallback=True)
    core.atomic_json(directory/'storage-diagnostic.json',dict(results,status='passed'))
    return dict(results,status='passed')
