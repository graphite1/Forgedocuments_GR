"""Headless, synthetic tests for AKTIO integration; no source transaction fixtures."""
import copy,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import pymupdf
from PIL import Image,ImageChops
from aktio import receipt
from aktio.planning import make_plan,validate_plan,export_plan
from aktio.state import SessionStore,checked_document
from aktio.printing import print_rectangle,print_records
from app_storage import AppStorage,StorageError
from form_registry import catalog,default_definition


def fixture(mode='fixed',seed=0):
    config=dict(date='2030-01-02',start='07:00',end='17:00',breaks=[['12:00','13:00']],minimum_trip_minutes=30,time_jitter_minutes=10,scale_gap_minutes=2,first_sn=4,measurement_mode=mode,seed=seed)
    vehicle=dict(vehicle='SYNTHETIC',runs=10,tare_kg=11180,max_payload_kg=10000,max_gross_kg=21180,target_payload_kg=9000,weight_jitter_kg=500,
                 fixed_measurements=[dict(time=t,sn=str(s)) for t,s in [('07:08',4),('10:00',10),('14:00',27)]])
    return config,[vehicle]


def actual_item():
    raw=dict(date='2030-01-02',time='07:00',sn='1',vehicle='SYNTHETIC',trip='1',category='空車',tare=11180,total=11180,
             a1l=2200,a1r=2200,a2l=1800,a2r=1800,a3l=1590,a3r=1590,record_id='SYNTHETIC')
    mapping={k:k for k in raw}
    return dict(row=1,raw=raw,mapping=mapping,default_tare=11180,record=receipt.prepare_record(1,raw,mapping,11180),status='OK',
                changes=[dict(at='2030-01-02T07:00:00',reason='合成テスト',before={},after=copy.deepcopy(raw))])


def document():
    c,v=fixture()
    return dict(form_id='aktio_receipt',schema_version=1,settings={},vehicles=v,records=make_plan(c,v),generated_config=c,generated_vehicles=v,
                measured_records=[actual_item()],paper='A4中央',measurement_mode='fixed')


class AktioChecks(unittest.TestCase):
    def test_fixed_three_records_exact_time_sn_tare_and_seed_zero(self):
        c,v=fixture();a=make_plan(c,v);b=make_plan(c,v)
        self.assertEqual(a,b);self.assertEqual([r['time'] for r in a],['07:08','10:00','14:00'])
        self.assertEqual([r['sn'] for r in a],['0004','0010','0027'])
        self.assertEqual([r['category'] for r in a],['空車','積載','積載'])
        self.assertEqual(a[0]['total_kg'],11180);self.assertEqual(a[0]['payload_kg'],0)
        for r in a:
            self.assertEqual(r['mode'],'simulation');self.assertEqual(r['total_kg'],sum(r['axle_values_kg']))
            self.assertLessEqual(r['total_kg'],21180);self.assertLessEqual(r['payload_kg'],10000)
            self.assertTrue(all(w%10==0 for w in r['axle_values_kg']))

    def test_count_multi_vehicle_breaks_intervals_limits_and_sn(self):
        for seed in range(20):
            c,v=fixture('count',seed);v.append(dict(v[0],vehicle='SYNTHETIC2'))
            records=make_plan(c,v);self.assertEqual(len(records),22);self.assertTrue(validate_plan(records,c,v))
            self.assertEqual([r['sn'] for r in records],[str(i).zfill(4) for i in range(4,26)])

    def test_impossible_break_gap_duplicate_sn_and_weight_are_rejected(self):
        c,v=fixture()
        for index,change in [(1,dict(time='12:10')),(1,dict(time='07:20')),(2,dict(sn='4'))]:
            bad=copy.deepcopy(v);bad[0]['fixed_measurements'][index].update(change)
            with self.assertRaises(ValueError):make_plan(c,bad)
        bad=copy.deepcopy(v);bad[0]['max_gross_kg']=11100
        with self.assertRaises(ValueError):make_plan(c,bad)
        records=make_plan(c,v);records[1]['axle_values_kg'][0]+=1
        with self.assertRaises(ValueError):validate_plan(records,c,v)
        bad=copy.deepcopy(v);bad.append(dict(v[0],vehicle='OTHER'))
        with self.assertRaises(ValueError):make_plan(c,bad)

    def test_every_plan_path_has_notice_inside_receipt_and_actual_remains_distinct(self):
        c,v=fixture();r=make_plan(c,v)[1];actual=dict(r,mode='measured')
        plan=receipt.render_receipt_image(r);measured=receipt.render_receipt_image(actual)
        _,layout=receipt.receipt_layout();box=layout['receipt_crop_px']
        self.assertIsNotNone(ImageChops.difference(plan.crop(box),measured.crop(box)).getbbox())
        self.assertIsNone(ImageChops.difference(plan,measured).crop((0,0,900,3508)).getbbox())
        # Direct printing calls the same marked renderer; record order is untouched.
        import inspect,aktio.printing
        self.assertIn('render_receipt_image(record)',inspect.getsource(aktio.printing.print_records))
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for paper,size in [('a4',(2480,3508)),('receipt',(630,680))]:
                image,name=receipt.render_receipt(r,folder,paper)
                self.assertIn('計画',name);self.assertEqual(image.size,size)
                expected=plan if paper=='a4' else plan.crop(box)
                with Image.open(folder/(name+'.png')) as saved:self.assertEqual(saved.tobytes(),expected.tobytes())
                with pymupdf.open(folder/(name+'.pdf')) as pdf:
                    self.assertAlmostEqual(pdf[0].rect.width,size[0]*72/300,places=2)
                    self.assertAlmostEqual(pdf[0].rect.height,size[1]*72/300,places=2)
                    pix=pdf[0].get_pixmap(matrix=pymupdf.Matrix(300/72,300/72))
                    rendered=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                    if paper=='a4':rendered=rendered.crop(box)
                    # The notice is in the last 100 px of the real-size receipt.
                    self.assertLess(rendered.crop((400,580,600,650)).convert('L').getextrema()[0],100)
            unknown=dict(r);unknown.pop('mode')
            with self.assertRaisesRegex(ValueError,'区分'):receipt.render_receipt_image(unknown)

    def test_all_plan_pdf_png_pages_and_print_geometry(self):
        c,v=fixture();records=make_plan(c,v)
        with tempfile.TemporaryDirectory() as temp:
            path=export_plan(records,c,v,Path(temp)/'export',paper='receipt')
            self.assertEqual(len(list(path.glob('*.png'))),3)
            with pymupdf.open(path/'全レシート.pdf') as pdf:
                self.assertEqual(len(pdf),3)
                self.assertAlmostEqual(pdf[0].rect.width,53.34*72/25.4,places=2)
            saved=json.loads((path/'運搬記録.json').read_text(encoding='utf-8'));self.assertEqual(saved['records'],records)
        self.assertEqual(print_rectangle(53.34,57.5733333333,300,300,2480,3508,0,0),(925,1414,1555,2094))
        with patch('aktio.printing.os.name','posix'):
            with self.assertRaises(OSError):print_records(records)

    def test_session_reopen_keeps_measured_plan_and_correction_history_separate(self):
        data=document()
        with tempfile.TemporaryDirectory() as temp:
            manager=AppStorage(Path(temp));row=next(r for r in catalog() if r['id']=='aktio_receipt')
            folder=manager.prepare(default_definition(row));self.assertEqual(folder,Path(temp).resolve()/'data/aktio_receipt')
            store=SessionStore(folder);store.save_session(data);store.close()
            store=SessionStore(folder)
            try:self.assertEqual(store.load_session(),data)
            finally:store.close()
            other=default_definition(catalog()[0])
            with self.assertRaises(ValueError):
                bad=SessionStore(folder);bad.check_form(other)
            bad.close()

    def test_foreign_corrupt_and_mixed_session_never_overwrite_saved_state(self):
        data=document()
        with tempfile.TemporaryDirectory() as temp:
            store=SessionStore(temp);store.save_session(data)
            try:
                for change in [dict(form_id='ac_toyoake'),dict(records=[actual_item()['record']]),dict(measured_records=[dict(actual_item(),record=data['records'][0])])]:
                    with self.assertRaises(ValueError):store.save_session(dict(data,**change))
                    self.assertEqual(store.load_session(),data)
                store.db.execute("UPDATE aktio_session SET document='broken'");store.db.commit()
                with self.assertRaises(json.JSONDecodeError):store.load_session()
                self.assertEqual(store.db.execute('SELECT document FROM aktio_session').fetchone()[0],'broken')
            finally:store.close()

    def test_excel_synthetic_formula_import_no_execution_and_no_source_changes(self):
        # Minimal OOXML with a deliberately stale formula cache: simple references win.
        headers=['日付','時刻','SN','車両','回数','区分','1軸左','1軸右','2軸左','2軸右','3軸左','3軸右','総重量','基準空車重量']
        values=['2030-01-02','07:00','0001','SYNTHETIC','1','空車',2200,2200,1800,1800,1590,1590,11180,11180]
        import xml.sax.saxutils as x
        ns=receipt.NS['s'];cells=[]
        for row,items in [(1,headers),(2,values)]:
            part=[]
            for i,value in enumerate(items):
                col=chr(65+i);addr=f'{col}{row}'
                if addr=='N2':part.append(f'<c r="{addr}"><f>M2</f><v>1</v></c>')
                else:part.append(f'<c r="{addr}" t="inlineStr"><is><t>{x.escape(str(value))}</t></is></c>')
            cells.append(f'<row r="{row}">'+''.join(part)+'</row>')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'synthetic.xlsx'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="{receipt.RNS}"><sheets><sheet name="計量データ" r:id="r1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData>'+''.join(cells)+'</sheetData></worksheet>')
            before=p.read_bytes();rows,mapping,tare=receipt.read_sheet(p)
            record=receipt.prepare_record(rows[0][0],rows[0][1],mapping,tare)
            self.assertEqual(record['tare_kg'],11180);self.assertEqual(record['mode'],'measured');self.assertEqual(p.read_bytes(),before)




class FakeVar:
    def __init__(self,*args,value='',**kwargs):self.value=str(value);self.callbacks=[]
    def get(self):return self.value
    def set(self,value):
        self.value=str(value)
        for callback in self.callbacks:callback()
    def trace_add(self,mode,callback):self.callbacks.append(callback)


class FakeTree:
    def __init__(self,columns):self.columns=[c[0] for c in columns];self.rows={};self.selected=()
    def __getitem__(self,key):return self.columns
    def get_children(self):return tuple(self.rows)
    def delete(self,*keys):
        for key in keys:self.rows.pop(key,None)
    def insert(self,parent,index,iid,values):self.rows[iid]=values
    def selection(self):return self.selected
    def selection_set(self,value):self.selected=(value,)
    def bind(self,*args):pass


class AktioScreenHeadlessChecks(unittest.TestCase):
    def setUp(self):
        from contextlib import ExitStack
        from unittest.mock import MagicMock
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)/'data/aktio_receipt';self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ['tk.Frame','tk.Label','ttk.Frame','ttk.Label','ttk.Button','ttk.Combobox','ttk.Notebook','ttk.LabelFrame','ttk.Entry']:
            self.stack.enter_context(patch('aktio.ui.'+name,MagicMock()))
        self.stack.enter_context(patch('aktio.ui.tk.StringVar',FakeVar))
        self.stack.enter_context(patch('aktio.ui.configure_theme'))
        from aktio.ui import Application
        self.stack.enter_context(patch.object(Application,'tree',lambda self,parent,columns,height=9:FakeTree(columns)))
        self.root=MagicMock();self.root.after.return_value='pending';self.root.winfo_id.return_value=123
        self.app=Application(self.root,self.folder)
        self.addCleanup(lambda:self.app.store.close())

    def test_real_controller_generates_saves_reopens_and_keeps_manual_corrections(self):
        from aktio.ui import Application
        app=self.app;app.settings['date'].set('2030-01-02');app.settings['seed'].set('0')
        with patch.object(app,'background',lambda work,done:done(work())):app.generate()
        self.assertEqual([r['sn'] for r in app.plan],['0004','0005','0006'])
        def enter(title,fields,callback):
            values={key:str(value) for key,label,value in fields}
            values.update(date='2030-01-02',time='07:00',sn='1',reason='合成テストの入力')
            values.update({k:str(v) for k,v in zip(receipt.AXLES,[2200,2200,1800,1800,1590,1590])})
            callback(values)
        with patch.object(app,'form_dialog',enter):app.add_actual();app.edit_actual()
        self.assertEqual(len(app.records[0]['changes']),2);self.assertFalse(app.records[0]['new'])
        self.assertEqual(app.records[0]['record']['mode'],'measured');self.assertTrue(app.autosave())
        expected=copy.deepcopy(app.document());app.store.close()
        app=Application(self.root,self.folder);self.app=app
        self.assertEqual(app.document(),expected);self.assertEqual(app.paper_kind(),'a4')
        app.tabs.select.return_value=str(app.plan_tab);app.plan_tree.selection_set('1')
        sent=[]
        with patch('aktio.printing.print_records',side_effect=lambda records,**kw:sent.extend(records) or True):app.direct_print(True)
        self.assertEqual(len(sent),1);self.assertEqual(sent[0]['mode'],'simulation')
        self.assertEqual(sent[0]['sn'],'0005')

    def test_invalid_import_preserves_live_state_and_database(self):
        app=self.app;self.assertTrue(app.autosave());before=copy.deepcopy(app.document())
        path=Path(self.temp.name)/'foreign.json';path.write_text(json.dumps(dict(before,form_id='ac_toyoake')))
        with patch('aktio.ui.filedialog.askopenfilename',return_value=str(path)),patch('aktio.ui.messagebox.showerror') as error:
            app.load_document();error.assert_called_once()
        self.assertEqual(app.document(),before);self.assertEqual(app.store.load_session(),before)

    def test_concurrent_writes_and_write_failure_keep_screen_open(self):
        app=self.app;self.assertTrue(app.autosave());other=SessionStore(self.folder);other.load_session()
        changed=app.document();changed['paper']='レシート実寸';other.save_session(changed);other.close()
        with patch('aktio.ui.messagebox.showerror'):
            self.assertFalse(app.may_leave())
        self.root.destroy.assert_not_called()
        with SessionStoreForTest(self.folder) as saved:self.assertEqual(saved.load_session()['paper'],'レシート実寸')


class SessionStoreForTest(SessionStore):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


if __name__=='__main__':unittest.main(verbosity=2)
