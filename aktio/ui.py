"""Tkinter front end: measured receipt output and a separate simulation planner."""
from pathlib import Path
from datetime import datetime
import copy,json,os,threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
from . import receipt
from .planning import make_plan,export_plan
from .state import SessionStore,checked_document
from desktop_theme import configure_theme
from core import atomic_json

class Application:
    def __init__(self,root,directory):
        configure_theme(root)
        self.directory=Path(directory);self.store=SessionStore(directory)
        try:saved=self.store.load_session()
        except Exception:self.store.close();raise
        self._autosave_id=None;self._restoring=True;self._state_safe=True;self.folder_open_handler=None
        self.root=root;root.title('Forgedocuments GR｜AKTIO 計量・運搬');root.geometry('1220x900');root.minsize(1100,780)
        self.records=[];self.plan=[];self.vehicles=[];self.output_folder=None;self.source=None
        self.settings={};self.photo=None;self.busy=False
        header=tk.Frame(root,bg='#18324B');header.pack(fill='x')
        tk.Label(header,text='AKTIO  計量・運搬計画',bg='#18324B',fg='white',font=('Yu Gothic UI',18,'bold')).pack(side='left',padx=20,pady=15)
        tk.Label(header,text='計量入力  /  運搬予定',bg='#18324B',fg='#BED3E7',font=('Yu Gothic UI',11)).pack(side='right',padx=20)
        output_bar=ttk.Frame(root);output_bar.pack(fill='x',padx=12,pady=7)
        self.paper=tk.StringVar(value='A4中央')
        ttk.Label(output_bar,text='出力・印刷用紙：').pack(side='left')
        ttk.Combobox(output_bar,textvariable=self.paper,values=['A4中央','レシート実寸'],state='readonly',width=16).pack(side='left',padx=6)
        ttk.Label(output_bar,text='1ページ1枚・実寸100%｜乱数予定には必ず「計画」を印字').pack(side='left',padx=8)
        ttk.Button(output_bar,text='選択1枚をPDF出力',command=self.export_selected).pack(side='left',padx=6)
        ttk.Button(output_bar,text='選択1枚を印刷',command=lambda:self.direct_print(True)).pack(side='left',padx=6)
        ttk.Button(output_bar,text='全件を連番印刷',command=lambda:self.direct_print(False)).pack(side='left',padx=6)
        self.tabs=ttk.Notebook(root);self.tabs.pack(fill='both',expand=True,padx=12,pady=12)
        self.actual_tab=ttk.Frame(self.tabs);self.plan_tab=ttk.Frame(self.tabs)
        self.tabs.add(self.plan_tab,text='運搬予定');self.tabs.add(self.actual_tab,text='計量入力')
        self.actual_ui();self.plan_ui()
        self.status=tk.StringVar(value='Excelを選択するか、運搬予定の条件を設定してください。')
        ttk.Label(root,textvariable=self.status,anchor='w').pack(fill='x',padx=16,pady=(0,10))
        self.set_vehicle_count()
        if saved:
            try:self.restore_document(saved)
            except Exception:self.store.close();raise
        self._restoring=False
        for var in [*self.settings.values(),self.paper,self.plan_mode]:
            var.trace_add('write',self.schedule_save)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def schedule_save(self,*args):
        if self._restoring:return
        if self._autosave_id:self.root.after_cancel(self._autosave_id)
        self._autosave_id=self.root.after(600,self.autosave)

    def autosave(self):
        if not self._state_safe:return False
        if self._restoring:return True
        if self._autosave_id:self.root.after_cancel(self._autosave_id)
        self._autosave_id=None
        try:self.store.save_session(self.document());return True
        except Exception as error:
            self.status.set('自動保存できません。入力を保持したまま停止しています：'+str(error))
            return False

    def may_leave(self):
        if self.busy:
            messagebox.showinfo('処理中','処理が完了してから閉じてください',parent=self.root);return False
        if self.autosave():return True
        messagebox.showerror('保存できません','保存先の書き込みを確認してください。保存できるまで画面を閉じません。',parent=self.root)
        return False

    def close(self):
        if self.may_leave():
            if self._autosave_id:self.root.after_cancel(self._autosave_id)
            self.store.close();self.root.destroy()

    def tree(self,parent,columns,height=9):
        box=ttk.Frame(parent);box.pack(fill='both',expand=True,pady=7)
        tree=ttk.Treeview(box,columns=[x[0] for x in columns],show='headings',height=height)
        for key,label,width in columns:tree.heading(key,text=label);tree.column(key,width=width,minwidth=50,anchor='center')
        scroll=ttk.Scrollbar(box,orient='vertical',command=tree.yview);tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        return tree

    def actual_ui(self):
        bar=ttk.Frame(self.actual_tab);bar.pack(fill='x',padx=12,pady=10)
        ttk.Button(bar,text='Excelを読み込む',command=self.import_excel).pack(side='left')
        ttk.Button(bar,text='計量行を追加',command=self.add_actual).pack(side='left',padx=5)
        ttk.Button(bar,text='選択行の入力・訂正',command=self.edit_actual).pack(side='left',padx=8)
        ttk.Button(bar,text='選択行をプレビュー',command=lambda:self.preview(self.records,self.actual_tree)).pack(side='left')
        ttk.Button(bar,text='全件PDF・PNGを出力',command=self.export_actual).pack(side='right')
        self.source_label=tk.StringVar(value='未選択')
        ttk.Label(self.actual_tab,textvariable=self.source_label).pack(anchor='w',padx=14)
        self.actual_tree=self.tree(self.actual_tab,[('row','Excel行',70),('vehicle','車両',170),('trip','回数',60),('time','時刻',70),('sn','SN',65),('total','総重量kg',100),('tare','空車基準kg',110),('payload','積載kg',90),('status','確認',270)])
        self.actual_note=tk.StringVar(value='各車・各日の初回は空車計量。軸左右からTOTALを計算します。訂正理由を記録し、読込元のExcelは上書きしません。')
        ttk.Label(self.actual_tab,textvariable=self.actual_note,wraplength=1120).pack(fill='x',padx=14,pady=10)

    def field(self,parent,row,col,label,key,value,width=12):
        ttk.Label(parent,text=label).grid(row=row,column=col*2,sticky='w',padx=(8,6),pady=5)
        v=tk.StringVar(value=str(value));self.settings[key]=v
        ttk.Entry(parent,textvariable=v,width=width).grid(row=row,column=col*2+1,sticky='w',padx=(0,14),pady=5)

    def plan_ui(self):
        mode_bar=ttk.Frame(self.plan_tab);mode_bar.pack(fill='x',padx=12,pady=(8,0))
        ttk.Label(mode_bar,text='予定の作成方法：').pack(side='left')
        self.plan_mode=tk.StringVar(value='指定時刻・SN（3枚）')
        mode=ttk.Combobox(mode_bar,textvariable=self.plan_mode,values=['指定時刻・SN（3枚）','運搬回数で作成'],state='readonly',width=24)
        mode.pack(side='left',padx=6);mode.bind('<<ComboboxSelected>>',lambda e:(self.refresh_vehicles(),self.invalidate()))
        ttk.Label(mode_bar,text='3枚：空車 → 積載 → 積載。時刻・SNを各車で指定します。').pack(side='left',padx=8)
        top=ttk.LabelFrame(self.plan_tab,text='稼働条件');top.pack(fill='x',padx=12,pady=10)
        fields=[('日付','date',datetime.now().strftime('%Y-%m-%d')),('開始','start','07:00'),('終了','end','17:00'),('台数','vehicle_count',1),
                ('休憩開始','break_start','12:00'),('休憩終了','break_end','13:00'),('各車の運搬回数','runs',10),('SN開始値','first_sn',4),
                ('最短運搬間隔(分)','minimum_trip_minutes',30),('時刻の振幅(分)','time_jitter_minutes',10),('計量間隔(分)','scale_gap_minutes',2),('乱数シード(任意)','seed','')]
        for i,(label,key,value) in enumerate(fields): self.field(top,i//4,i%4,label,key,value)
        ttk.Label(top,text='各車の第1回は必ず空車計量。運搬10回なら空車1回＋積載10回。休憩欄を両方空欄にすると休憩なし。').grid(row=3,column=0,columnspan=8,sticky='w',padx=8,pady=5)
        ttk.Label(top,text='指定時刻・SNでは各車3枚を作成し、回数・SN開始値・時刻の振幅は使用しません。').grid(row=4,column=0,columnspan=8,sticky='w',padx=8,pady=(0,5))
        self.extra_breaks=[]
        tools=ttk.Frame(self.plan_tab);tools.pack(fill='x',padx=12)
        ttk.Button(tools,text='台数・回数を車両表へ反映',command=self.set_vehicle_count).pack(side='left')
        ttk.Button(tools,text='車両の重量条件を編集',command=self.edit_vehicle).pack(side='left',padx=8)
        ttk.Button(tools,text='3回の時刻・SNを指定',command=self.edit_measurements).pack(side='left')
        ttk.Button(tools,text='休憩を追加',command=self.add_break).pack(side='left')
        ttk.Button(tools,text='休憩一覧',command=self.show_breaks).pack(side='left',padx=8)
        ttk.Button(tools,text='設定・計画を読み込む',command=self.load_document).pack(side='right')
        self.vehicle_tree=self.tree(self.plan_tab,[('vehicle','車両',105),('runs','運搬回数',80),('tare_kg','空車kg',85),('max_payload_kg','積載上限kg',105),('max_gross_kg','総重量上限kg',110),('target_payload_kg','中心積載kg',105),('weight_jitter_kg','重量振幅kg',100),('fixed','指定時刻 / SN',280)],height=3)
        self.vehicle_tree.bind('<Double-1>',lambda e:self.edit_vehicle())
        actions=ttk.Frame(self.plan_tab);actions.pack(fill='x',padx=12,pady=5)
        ttk.Button(actions,text='計量予定を生成',command=self.generate).pack(side='left')
        ttk.Button(actions,text='選択予定をプレビュー',command=lambda:self.preview(self.plan,self.plan_tree)).pack(side='left',padx=8)
        ttk.Button(actions,text='設定・計画を保存',command=self.save_document).pack(side='left')
        ttk.Button(actions,text='全件PDF・PNGを出力',command=self.export_simulation).pack(side='right')
        self.plan_summary=tk.StringVar(value='重量の中心値と上限を設定し、10kg刻みで予定を作成します。')
        ttk.Label(self.plan_tab,textvariable=self.plan_summary).pack(anchor='w',padx=14,pady=3)
        self.plan_tree=self.tree(self.plan_tab,[('vehicle','車両',130),('trip','計量回数',80),('time','計量予定',90),('sn','SN',65),('total','総重量kg',115),('payload','積載kg',115),('interval','同車の間隔(分)',125),('kind','区分',110)],height=6)

    def config(self):
        result={k:v.get().strip() for k,v in self.settings.items()}
        for k in ('vehicle_count','runs','first_sn','minimum_trip_minutes','time_jitter_minutes','scale_gap_minutes'):
            try: result[k]=int(result[k])
            except ValueError: raise ValueError(k+'は整数で指定してください')
        a,b=result.pop('break_start'),result.pop('break_end')
        if bool(a)!=bool(b): raise ValueError('休憩開始・終了は両方入力、または両方空欄にしてください')
        result['breaks']=([[a,b]] if a else [])+[list(p) for p in self.extra_breaks]
        result['measurement_mode']='fixed' if self.plan_mode.get()=='指定時刻・SN（3枚）' else 'count'
        return result

    def invalidate(self):
        self.plan=[];self.plan_tree.delete(*self.plan_tree.get_children())
        self.plan_summary.set('条件を変更しました。「計量予定を生成」を実行してください。')
        self.schedule_save()

    def set_vehicle_count(self):
        try:
            n=int(self.settings['vehicle_count'].get());runs=int(self.settings['runs'].get())
            if not 1<=n<=50 or not 1<=runs<=100: raise ValueError('台数は1～50、各車の回数は1～100です')
            old=self.vehicles;self.vehicles=[]
            for i in range(n):
                v=dict(old[i]) if i<len(old) else {'vehicle':f'車両{i+1}','tare_kg':11180,'max_payload_kg':10000,'max_gross_kg':21180,'target_payload_kg':9000,'weight_jitter_kg':500}
                v['runs']=runs;self.vehicles.append(v)
                if 'fixed_measurements' not in v:
                    from .planning import hhmm,minute
                    first=int(self.settings['first_sn'].get())+i*3
                    v['fixed_measurements']=[{'time':hhmm(minute(t)+i*2),'sn':str(first+j).zfill(4)} for j,t in enumerate(('07:08','10:00','14:00'))]
            self.refresh_vehicles();self.invalidate()
        except ValueError as e: messagebox.showerror('設定を確認',str(e))

    def refresh_vehicles(self):
        self.vehicle_tree.delete(*self.vehicle_tree.get_children())
        keys=self.vehicle_tree['columns']
        for i,v in enumerate(self.vehicles):
            values=[]
            for k in keys:
                if k=='fixed':values.append(' / '.join(f'{s["time"]} #{s["sn"]}' for s in v.get('fixed_measurements',[])))
                elif k=='runs' and self.plan_mode.get()=='指定時刻・SN（3枚）':values.append(2)
                else:values.append(v[k])
            self.vehicle_tree.insert('', 'end',iid=str(i),values=values)

    def form_dialog(self,title,fields,callback):
        win=tk.Toplevel(self.root);win.title(title);win.transient(self.root);win.grab_set()
        variables={}
        for i,(key,label,value) in enumerate(fields):
            ttk.Label(win,text=label).grid(row=i,column=0,sticky='w',padx=15,pady=5)
            variables[key]=tk.StringVar(value=str(value));ttk.Entry(win,textvariable=variables[key],width=32).grid(row=i,column=1,padx=15,pady=5)
        def apply():
            try: callback({k:v.get().strip() for k,v in variables.items()});win.destroy()
            except (ValueError,TypeError) as e:messagebox.showerror('入力を確認',str(e),parent=win)
        ttk.Button(win,text='保存',command=apply).grid(row=len(fields),column=0,columnspan=2,pady=12)

    def edit_vehicle(self):
        selection=self.vehicle_tree.selection()
        if not selection:messagebox.showinfo('車両を選択','編集する車両を選択してください');return
        index=int(selection[0]);v=self.vehicles[index]
        labels=['車両名','運搬回数（空車計量は別に1回）','空車重量kg','積載重量上限kg','総重量上限kg','想定積載重量（中心）kg','重量の振幅kg（10kg刻み）']
        keys=['vehicle','runs','tare_kg','max_payload_kg','max_gross_kg','target_payload_kg','weight_jitter_kg']
        def apply(data):
            for k in keys[1:]:data[k]=int(data[k])
            self.vehicles[index]={**v,**data};self.refresh_vehicles();self.invalidate()
        self.form_dialog('車両条件',[(k,l,v[k]) for k,l in zip(keys,labels)],apply)

    def edit_measurements(self):
        selection=self.vehicle_tree.selection()
        if not selection:messagebox.showinfo('車両を選択','時刻・SNを指定する車両を選択してください');return
        index=int(selection[0]);v=self.vehicles[index]
        specified=v.get('fixed_measurements') or [{'time':t,'sn':str(i+1).zfill(4)} for i,t in enumerate(('07:08','10:00','14:00'))]
        fields=[]
        for i,label in enumerate(('第1回 空車','第2回 積載（午前）','第3回 積載（午後）')):
            fields.extend([(f't{i}',label+' 時刻 HH:MM',specified[i]['time']),(f's{i}',label+' SN',specified[i]['sn'])])
        def apply(data):
            from .planning import minute,hhmm,periods,active_minute_of
            settings=self.config();slots=periods(settings);previous=None;sn=set();result=[]
            for i in range(3):
                time=hhmm(minute(data[f't{i}']));active=active_minute_of(time,slots)
                number=data[f's{i}']
                if not number.isascii() or not number.isdigit() or len(number)>4:raise ValueError('SNは0～9999の数字で指定してください')
                number=number.zfill(4)
                if number in sn:raise ValueError('3回のSNは別々の番号にしてください')
                sn.add(number)
                if previous is not None and active-previous<settings['minimum_trip_minutes']:raise ValueError('空車→積載→積載の順で、最短運搬間隔を空けて指定してください')
                previous=active;result.append({'time':time,'sn':number})
            v['fixed_measurements']=result;self.plan_mode.set('指定時刻・SN（3枚）');self.refresh_vehicles();self.invalidate()
        self.form_dialog(v['vehicle']+'：3回の時刻・SN',fields,apply)

    def add_break(self):
        def apply(data):
            from .planning import minute
            if minute(data['a'])>=minute(data['b']):raise ValueError('終了は開始より後にしてください')
            self.extra_breaks.append((data['a'],data['b']));self.invalidate()
        self.form_dialog('追加休憩',[('a','開始','10:00'),('b','終了','10:15')],apply)

    def show_breaks(self):
        win=tk.Toplevel(self.root);win.title('追加休憩');win.transient(self.root)
        box=tk.Listbox(win,width=35,height=8);box.pack(padx=15,pady=10)
        for a,b in self.extra_breaks:box.insert('end',f'{a} ～ {b}')
        def remove():
            if box.curselection():
                index=box.curselection()[0];del self.extra_breaks[index];box.delete(index);self.invalidate()
        ttk.Button(win,text='選択した追加休憩を削除',command=remove).pack(pady=10)

    def background(self,work,done):
        if self.busy: return
        self.busy=True;self.status.set('処理中です…')
        def run():
            try:result=work();self.root.after(0,lambda:self.complete(done,result))
            except Exception as exc:
                message=str(exc);self.root.after(0,lambda:self.failed(message))
        threading.Thread(target=run,daemon=True).start()

    def complete(self,done,result):
        self.busy=False;done(result);self.autosave()

    def failed(self,message):
        self.busy=False;self.status.set('処理できませんでした。条件を確認してください。');messagebox.showerror('確認',message)

    def import_excel(self):
        if self.busy:return
        name=filedialog.askopenfilename(filetypes=[('Excel','*.xlsx')],initialdir=self.directory)
        if not name:return
        try:
            rows,mapping,tare=receipt.read_sheet(name)
            if self.records and not messagebox.askyesno('計量データの入替','現在の計量入力を履歴ごと保存してから、新しいExcelへ入れ替えますか？',parent=self.root):return
            if self.records:
                backup=self.directory/('計量入力バックアップ_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json')
                atomic_json(backup,self.document())
            self.records=[]
            for row,data in rows:
                item={'row':row,'raw':data,'mapping':mapping,'default_tare':tare,'record':None,'status':'OK'}
                try:item['record']=receipt.prepare_record(row,data,mapping,tare)
                except ValueError as e:item['status']=str(e)
                self.records.append(item)
            self.source=Path(name);self.source_label.set(name);self.refresh_actual()
            self.status.set(f'読込 {len(self.records)}件。選択行を編集・確認してからPDFを作成できます。');self.autosave()
        except Exception as e:messagebox.showerror('Excel読込',str(e))

    def refresh_actual(self):
        self.actual_tree.delete(*self.actual_tree.get_children())
        for index,item in enumerate(self.records):
            r=item['record'];d=item['raw']
            self.actual_tree.insert('','end',iid=str(index),values=[item['row'],d.get('vehicle') or '',d.get('trip') or '',r['time'] if r else d.get('time') or '',r['sn'] if r else d.get('sn') or '',r['total_kg'] if r else d.get('total') or '',r['tare_kg'] if r else item['default_tare'] or '',r['payload_kg'] if r and r['payload_kg'] is not None else '',item['status']])

    def add_actual(self):
        if self.busy:return
        number=max([i['row'] for i in self.records]+[0])+1
        day=datetime.now().strftime('%Y-%m-%d')
        name=next((i['raw'].get('vehicle') for i in reversed(self.records) if i['raw'].get('vehicle')),'車両1')
        same=[i['record'] for i in self.records if i['record'] and i['record']['vehicle']==name and i['record']['date']==datetime.strptime(day,'%Y-%m-%d').strftime('%d/%m/%Y')]
        data={'date':day,'time':'','sn':'','vehicle':name,
              'trip':str(len(same)+1),'category':'積載' if same else '空車',
              'tare':11180,'record_id':f'MANUAL_{datetime.now().strftime("%Y%m%d%H%M%S%f")}',
              **{k:None for k in receipt.AXLES}}
        self.records.append({'row':number,'raw':data,'mapping':dict(receipt.ALIASES),
                             'default_tare':11180,'record':None,'status':'新規入力待ち','new':True})
        self.refresh_actual();self.autosave();self.actual_tree.selection_set(str(len(self.records)-1));self.edit_actual()

    def edit_actual(self):
        if self.busy:return
        sel=self.actual_tree.selection()
        if not sel:messagebox.showinfo('行を選択','編集する計量行を選択してください');return
        index=int(sel[0]);item=self.records[index];d=item['raw'];r=item['record']
        fields=[('date','日付 YYYY-MM-DD',datetime.strptime(r['date'],'%d/%m/%Y').strftime('%Y-%m-%d') if r else datetime.now().strftime('%Y-%m-%d')),
                ('time','時刻 HH:MM',r['time'] if r else ''),('sn','SN',r['sn'] if r else d.get('sn') or ''),
                ('vehicle','車両',d.get('vehicle') or ''),('category','区分 空車／積載',d.get('category') or '積載'),
                ('tare','空車基準kg',r['tare_kg'] if r and r['tare_kg'] else item['default_tare'] or 11180)]
        labels=['1軸左kg','1軸右kg','2軸左kg','2軸右kg','3軸左kg','3軸右kg']
        fields.extend((k,l,d.get(k) if d.get(k) is not None else '') for k,l in zip(receipt.AXLES,labels));fields.append(('reason','入力・訂正理由','計量値の新規入力' if item.get('new') else ''))
        def apply(values):
            reason=values.pop('reason')
            if not reason:raise ValueError('訂正理由を入力してください')
            values['total']=str(sum(receipt.integer(values[k],k) for k in receipt.AXLES));values['trip']=d.get('trip') or '';values['record_id']=d.get('record_id') or ''
            mapping=dict(item['mapping'],category='C',trip='B',total='P',tare='Q')
            record=receipt.prepare_record(item['row'],values,mapping,item['default_tare'])
            same=[i['record'] for i in self.records if i is not item and i['record'] and i['record']['vehicle']==record['vehicle'] and i['record']['date']==record['date']]
            first=min(same+[record],key=lambda r:r['time'])
            if first['category']!='空車':raise ValueError('この車両・日付の最初の計量は空車にしてください。空車を先に入力してください')
            if item.get('new'):
                values['trip']=str(len(same)+1)
                record['trip']=values['trip']
            item.setdefault('changes',[]).append({'at':datetime.now().isoformat(timespec='seconds'),'reason':reason,'before':dict(item['raw']),'after':dict(values)})
            item.update(raw=values,mapping=mapping,record=record,status='訂正済み',new=False);self.refresh_actual();self.autosave()
        self.form_dialog('計量入力・訂正（TOTALは軸左右から計算）',fields,apply)

    def generate(self):
        if self.busy:return
        try:
            config=self.config()
            if config['vehicle_count']!=len(self.vehicles):raise ValueError('変更した台数を車両表へ反映してください')
            vehicles=copy.deepcopy(self.vehicles)
        except ValueError as e:messagebox.showerror('設定',str(e));return
        def done(records):
            self.plan=records;self.generated_config=config;self.generated_vehicles=vehicles
            self.refresh_plan();self.status.set('予定を生成しました。時刻・回数・重量を確認してください。')
        self.background(lambda:make_plan(config,vehicles),done)

    def refresh_plan(self):
        from .planning import minute
        self.plan_tree.delete(*self.plan_tree.get_children());previous={}
        for i,r in enumerate(self.plan):
            interval=minute(r['time'])-previous[r['vehicle']] if r['vehicle'] in previous else ''
            previous[r['vehicle']]=minute(r['time'])
            self.plan_tree.insert('','end',iid=str(i),values=[r['vehicle'],r['trip'],r['time'],r['sn'],r['total_kg'],r['payload_kg'],interval,r['category']])
        empty=sum(r['category']=='空車' for r in self.plan);loaded=len(self.plan)-empty
        self.plan_summary.set(f'台数 {len(self.vehicles)} / 空車 {empty}回＋運搬 {loaded}回＝計量 {len(self.plan)}回 / 想定積載重量 {sum(r["payload_kg"] for r in self.plan):,}kg')

    def preview(self,items,tree):
        sel=tree.selection()
        if not sel:messagebox.showinfo('行を選択','プレビューする行を選択してください');return
        item=items[int(sel[0])];r=item.get('record') if 'record' in item else item
        if r is None:messagebox.showerror('プレビュー','入力不足・不一致のある行はプレビューできません');return
        image=receipt.render_receipt_image(r);_,layout=receipt.receipt_layout();crop=image.crop(layout['receipt_crop_px'])
        win=tk.Toplevel(self.root);win.title('レシート プレビュー（実寸・A4中央）')
        bar=ttk.Frame(win);bar.pack(fill='x',padx=10,pady=5)
        label=ttk.Label(win);label.pack(padx=10,pady=10)
        def show(full=False):
            p=image.copy() if full else crop.copy();p.thumbnail((650,700));label.photo=ImageTk.PhotoImage(p);label.configure(image=label.photo)
        ttk.Button(bar,text='印字部分を拡大',command=lambda:show(False)).pack(side='left')
        ttk.Button(bar,text='A4全体の配置',command=lambda:show(True)).pack(side='left',padx=8)
        show(False)

    def choose_output(self,prefix):
        base=filedialog.askdirectory(title='出力先の親フォルダ',initialdir=self.directory)
        return Path(base)/(prefix+'_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')) if base else None

    def paper_kind(self):return 'a4' if self.paper.get()=='A4中央' else 'receipt'

    def current_records(self,single):
        is_plan=self.tabs.select()==str(self.plan_tab)
        items,tree=(self.plan,self.plan_tree) if is_plan else (self.records,self.actual_tree)
        if is_plan:
            if not self.plan:raise ValueError('先に計量予定を生成してください')
            if self.config()!=self.generated_config or self.vehicles!=self.generated_vehicles:raise ValueError('条件を変更したため、計量予定を再生成してください')
            from .planning import validate_plan
            validate_plan(self.plan,self.generated_config,self.generated_vehicles)
        if single:
            selected=tree.selection()
            if not selected:raise ValueError('対象の1枚を表から選択してください')
            items=[items[int(selected[0])]]
        records=[i if is_plan else i['record'] for i in items]
        bad=sum(r is None for r in records);records=[r for r in records if r is not None]
        if bad and not single and not messagebox.askyesno('未入力の行',f'{bad}件は入力不足です。内容が揃った{len(records)}件だけ処理しますか？'):return []
        if not records:raise ValueError('出力できる内容がありません。入力を確認してください')
        return copy.deepcopy(records)

    def export_selected(self):
        if self.busy:return
        try:records=self.current_records(True);paper=self.paper_kind()
        except ValueError as e:messagebox.showerror('1枚出力',str(e));return
        folder=self.choose_output('AKTIO_1枚')
        if not folder:return
        def work():
            folder.mkdir(parents=True,exist_ok=False);receipt.render_receipt(records[0],folder,paper=paper)
            (folder/'入力内容.json').write_text(json.dumps(records[0],ensure_ascii=False,indent=2),encoding='utf-8')
            return folder
        self.background(work,self.output_done)

    def direct_print(self,single):
        if self.busy:return
        try:
            records=self.current_records(single)
            if not records:return
            paper=self.paper_kind();self.busy=True;self.status.set('印刷用紙・プリンターを確認してください。');self.root.update_idletasks()
            from .printing import print_records
            printed=print_records(records,owner=self.root.winfo_id(),paper=paper)
            self.status.set(f'{len(records)}枚を連番で印刷ジョブへ送りました。' if printed else '印刷をキャンセルしました。')
        except (ValueError,OSError) as e:messagebox.showerror('印刷',str(e));self.status.set('印刷できませんでした。表示された理由を確認してください。')
        finally:self.busy=False

    def output_done(self,folder):
        self.output_folder=folder;self.status.set('出力先：'+str(folder))
        if messagebox.askyesno('出力完了','PDF・PNGを作成しました。出力フォルダを開きますか？'):
            if hasattr(os,'startfile'):os.startfile(folder)

    def export_simulation(self):
        if self.busy:return
        if not self.plan:messagebox.showinfo('予定生成','先に計量予定を生成してください');return
        try:
            if self.config()!=self.generated_config or self.vehicles!=self.generated_vehicles:raise ValueError('条件が変更されています。計量予定を再生成してください')
        except ValueError as e:messagebox.showerror('予定生成',str(e));return
        folder=self.choose_output('AKTIO_出力');paper=self.paper_kind()
        records=copy.deepcopy(self.plan);config=copy.deepcopy(self.generated_config);vehicles=copy.deepcopy(self.generated_vehicles)
        if folder:self.background(lambda:export_plan(records,config,vehicles,folder,paper=paper),self.output_done)

    def export_actual(self):
        if self.busy:return
        good=copy.deepcopy([i for i in self.records if i['record'] is not None]);bad=[i for i in self.records if i['record'] is None]
        if not good:messagebox.showinfo('出力','出力できる実測記録がありません');return
        if bad and not messagebox.askyesno('未完成の記録',f'{len(bad)}件に不足があります。入力が揃った{len(good)}件だけ出力しますか？'):return
        folder=self.choose_output('AKTIO_出力');paper=self.paper_kind()
        if not folder:return
        def work():
            folder.mkdir(parents=True,exist_ok=False);images=[]
            for item in good:image,name=receipt.render_receipt(item['record'],folder,paper=paper);images.append(folder/(name+'.png'))
            from .pdf_bundle import combine_png_pages
            combine_png_pages(images,folder/'全実測レシート.pdf')
            (folder/'実測_転記と訂正履歴.json').write_text(json.dumps({'mode':'measured','source_excel':str(self.source),'records':self.records},ensure_ascii=False,indent=2),encoding='utf-8')
            return folder
        self.background(work,self.output_done)

    def document(self):
        return {'schema_version':1,'form_id':'aktio_receipt','measured_records':copy.deepcopy(self.records),
                'source_excel':str(self.source) if self.source else None,'settings':{k:v.get() for k,v in self.settings.items()},'extra_breaks':self.extra_breaks,'vehicles':self.vehicles,
                'paper':self.paper.get(),'measurement_mode':'fixed' if self.plan_mode.get()=='指定時刻・SN（3枚）' else 'count',
                'records':self.plan,'generated_config':getattr(self,'generated_config',None),'generated_vehicles':getattr(self,'generated_vehicles',None)}

    def save_document(self):
        name=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('AKTIO保存JSON','*.json')],initialfile='AKTIO_記録と計画.json',initialdir=self.directory)
        if name:
            try:
                atomic_json(name,self.document());self.autosave();self.status.set('設定・計画・計量入力と訂正履歴を保存しました。')
            except Exception as error:messagebox.showerror('保存',str(error),parent=self.root)

    def restore_document(self,data):
        data=checked_document(data)
        saved_mode=data.get('measurement_mode') or (data.get('generated_config') or data.get('config') or {}).get('measurement_mode','count')
        self.plan_mode.set('指定時刻・SN（3枚）' if saved_mode=='fixed' else '運搬回数で作成')
        if data.get('paper') in ('A4中央','レシート実寸'):self.paper.set(data['paper'])
        if 'config' in data and 'settings' not in data:
            cfg=data['config'];settings={k:cfg[k] for k in self.settings if k in cfg}
            breaks=cfg.get('breaks',[]);settings['break_start']=breaks[0][0] if breaks else '';settings['break_end']=breaks[0][1] if breaks else ''
            settings['vehicle_count']=len(data.get('vehicles',[]));settings['runs']=data.get('vehicles',[{'runs':10}])[0]['runs']
            data={**data,'settings':settings,'extra_breaks':breaks[1:]}
        for k,v in data.get('settings',{}).items():
            if k in self.settings:self.settings[k].set('' if v is None else v)
        self.vehicles=data.get('vehicles') or self.vehicles;self.extra_breaks=data.get('extra_breaks',[])
        self.plan=data.get('records',[])
        if any(r.get('mode')!='simulation' for r in self.plan):raise ValueError('計画ファイルに試算以外の記録が含まれています')
        self.generated_config=data.get('generated_config') or (self.config() if self.plan else None)
        self.generated_vehicles=data.get('generated_vehicles') or ([dict(v) for v in self.vehicles] if self.plan else None)
        if self.plan:
            from .planning import validate_plan
            # Older saved plans did not include the initial tare. Keep their settings,
            # but require regeneration instead of inserting a fabricated measured record.
            first_by_vehicle={}
            for r in sorted(self.plan,key=lambda r:r['time']):first_by_vehicle.setdefault(r['vehicle'],r)
            if any(r.get('category')!='空車' or 'haul_trip' not in r for r in first_by_vehicle.values()):
                self.plan=[];self.generated_config=None;self.generated_vehicles=None
            else:validate_plan(self.plan,self.generated_config,self.generated_vehicles)
        self.records=data.get('measured_records',[]);self.source=data.get('source_excel')
        self.source_label.set(self.source or '未選択');self.refresh_actual()
        self.refresh_vehicles();self.refresh_plan()
        if not self.plan:self.plan_summary.set('設定を読み込みました。第1回を空車計量として予定を再生成してください。')

    def load_document(self):
        if self.busy:return
        name=filedialog.askopenfilename(filetypes=[('AKTIO保存JSON','*.json')],initialdir=self.directory)
        if name:
            old=copy.deepcopy(self.document());self._restoring=True
            try:
                data=checked_document(json.loads(Path(name).read_text(encoding='utf-8-sig')))
                atomic_json(self.directory/('読込前バックアップ_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json'),old)
                self.restore_document(data);self.status.set('設定・計画・計量入力と訂正履歴を読み込みました。')
            except Exception as e:
                try:self.restore_document(old)
                except Exception as rollback_error:
                    self._state_safe=False
                    self.status.set('読込を取り消せません。保存済みデータは変更していません：'+str(rollback_error))
                    messagebox.showerror('読込中止',str(rollback_error),parent=self.root);return
                messagebox.showerror('設定読込',str(e),parent=self.root)
            finally:self._restoring=False
            self.autosave()
