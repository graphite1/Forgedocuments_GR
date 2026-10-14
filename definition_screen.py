"""Shared exact-record input/batch output screen driven by a form definition."""
import copy
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog

from core import Store,blank,validate,validate_template,render_pdf,render_pngs,csv_read,csv_export,atomic_json
from pdf_view import PDFView,preview_window
from preview_files import generated_pdf
from record_batches import summary
from settings_widgets import LayoutSettings,FieldDefaultsSettings


class DefinitionScreen:
    def __init__(self,root,directory,default_template,validate_policy,migrate_definition=None):
        self.root=root;self.default_template=copy.deepcopy(default_template);self.validate_policy=validate_policy
        self.store=Store(directory,default_template=default_template,form_id=default_template['form_id'],validate_definition=validate_policy,migrate_definition=migrate_definition)
        try:
            self.template=self.store.template();self.validate_policy(self.template)
        except Exception:self.store.close();raise
        self.current=None;self.changed=False;self.suspend=False;self.loaded_values=None
        self.vars={};self.widgets={};self.choice_vars={};self.folder_switch_handler=None
        root.title('Forgedocuments GR｜'+self.template['name']);root.geometry('1250x850');root.minsize(950,650)
        bar=ttk.Frame(root,padding=8);bar.pack(fill='x')
        ttk.Label(bar,text=self.template['name'],font=('Yu Gothic UI',16,'bold')).pack(side='left')
        ttk.Button(bar,text='保存先を切替',command=self.switch_folder).pack(side='right')
        ttk.Button(bar,text='バックアップ',command=lambda:self.guarded(self.backup)).pack(side='right',padx=5)
        self.notebook=ttk.Notebook(root);self.notebook.pack(fill='both',expand=True)
        self.listtab=ttk.Frame(self.notebook);self.entrytab=ttk.Frame(self.notebook);self.settingtab=ttk.Frame(self.notebook)
        for tab,title in ((self.listtab,'一覧・一括出力'),(self.entrytab,'単票入力'),(self.settingtab,'帳票設定')):self.notebook.add(tab,text=title)
        self.status=tk.StringVar();ttk.Label(root,textvariable=self.status,padding=8).pack(fill='x')
        self.build_list();self.build_entry();self.build_settings();self.new(check=False);self.refresh();self.notebook.select(self.listtab)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def input_fields(self):
        return [f for f in self.template['fields'] if f.get('input',True) and f['type']!='layout_only']

    def guarded(self,fn,*args):
        try:return fn(*args)
        except Exception as error:messagebox.showerror('処理を完了できません',str(error),parent=self.root);return False

    def dirty(self,*args):
        if not self.suspend:self.changed=True;self.status.set('未保存の入力があります')

    def may_leave(self):
        if not self.changed:return True
        result=messagebox.askyesnocancel('未保存の入力','入力内容を保存しますか？',parent=self.root)
        return False if result is None else bool(self.guarded(self.save)) if result else True

    def build_entry(self):
        bar=ttk.Frame(self.entrytab,padding=8);bar.pack(fill='x')
        for label,fn in (('新規',self.new),('保存',self.save),('プレビュー',self.preview_current)):
            ttk.Button(bar,text=label,command=lambda f=fn:self.guarded(f)).pack(side='left',padx=4)
        ttk.Label(bar,text=self.template.get('entry_value_label','実際の記録を入力｜日付 YYYY-MM-DD｜時刻 HH:MM｜未記載は空欄')).pack(side='left',padx=10)
        pane=ttk.Panedwindow(self.entrytab,orient='horizontal');pane.pack(fill='both',expand=True)
        left=ttk.Frame(pane);right=ttk.Frame(pane);pane.add(left,weight=3);pane.add(right,weight=2)
        canvas=tk.Canvas(left,highlightthickness=0);scroll=ttk.Scrollbar(left,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        body=ttk.Frame(canvas,padding=8);win=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda event:canvas.itemconfigure(win,width=event.width))
        groups={}
        for f in self.input_fields():
            if f['group'] not in groups:
                frame=ttk.LabelFrame(body,text=f['group'],padding=8);frame.pack(fill='x',pady=4);frame.columnconfigure(1,weight=1);groups[f['group']]=frame
            frame=groups[f['group']];row=len(frame.grid_slaves())//2
            ttk.Label(frame,text=f['label']+('（固定）' if f.get('fixed_value') is not None else ''),wraplength=180).grid(row=row,column=0,sticky='nw',padx=4,pady=4)
            if f['type']=='multi_choice':
                holder=ttk.Frame(frame);holder.grid(row=row,column=1,sticky='ew');self.choice_vars[f['id']]={}
                for option in f['options']:
                    v=tk.BooleanVar();self.choice_vars[f['id']][option['key']]=v
                    ttk.Checkbutton(holder,text=option['label'],variable=v,command=self.dirty).pack(anchor='w')
            elif f['type']=='multiline':
                w=tk.Text(frame,height=4,width=32);w.grid(row=row,column=1,sticky='ew');w.bind('<<Modified>>',self.text_dirty);self.widgets[f['id']]=w
            else:
                v=tk.StringVar();self.vars[f['id']]=v;fixed=f.get('fixed_value') is not None
                if f.get('suggestions'):w=ttk.Combobox(frame,textvariable=v,values=f['suggestions'],state='disabled' if fixed else 'normal')
                elif f['type']=='choice':w=ttk.Combobox(frame,textvariable=v,values=f['choices'],state='disabled' if fixed else 'readonly')
                else:w=ttk.Entry(frame,textvariable=v,state='readonly' if fixed else 'normal')
                w.grid(row=row,column=1,sticky='ew',pady=4);self.widgets[f['id']]=w;v.trace_add('write',self.dirty)
        self.preview_view=PDFView(right);self.preview_view.pack(fill='both',expand=True)
        ttk.Label(right,text=self.template.get('entry_notice','未記載の実績は空欄で保持します。'),wraplength=420,padding=8).pack(fill='x')

    def text_dirty(self,event):
        if event.widget.edit_modified():self.dirty();event.widget.edit_modified(False)

    def values(self):
        data=blank(self.template)
        for f in self.input_fields():
            fid=f['id']
            if f['type']=='multi_choice':
                keys=[key for key,value in self.choice_vars[fid].items() if value.get()]
                data[fid]=json.dumps(keys,separators=(',',':')) if keys else ''
            elif f['type']=='multiline':data[fid]=self.widgets[fid].get('1.0','end-1c')
            else:data[fid]=self.vars[fid].get()
        return data

    def set_values(self,data):
        for f in self.template['fields']:
            if (f['type']=='layout_only' or not f.get('input',True)) and data.get(f['id'],'') not in ('',None):raise ValueError(f"{f['label']}: 入力・転記できない欄です")
        errors=validate(data,self.template)
        if errors:raise ValueError('\n'.join(errors))
        self.suspend=True
        try:
            for f in self.input_fields():
                fid=f['id'];value=data.get(fid,'')
                if f['type']=='multi_choice':
                    keys=json.loads(value) if value else []
                    for key,v in self.choice_vars[fid].items():v.set(key in keys)
                elif f['type']=='multiline':
                    w=self.widgets[fid];w.delete('1.0','end');w.insert('1.0',value);w.edit_modified(False)
                else:self.vars[fid].set(value)
        finally:self.suspend=False
        self.loaded_values=copy.deepcopy(data);self.changed=False

    def new(self,check=True):
        if check and not self.may_leave():return
        self.current=None;self.set_values(blank(self.template));self.notebook.select(self.entrytab);self.status.set('新規入力')

    def save(self):
        data=self.values()
        if self.current and data==self.current['data']:self.changed=False;return True
        reason='新規登録'
        if self.current:
            reason=simpledialog.askstring('訂正理由','変更理由を入力してください',parent=self.root)
            if reason is None:return False
        self.current=self.store.save(data,self.template,self.current['id'] if self.current else None,self.current['revision'] if self.current else None,reason)
        self.loaded_values=copy.deepcopy(data);self.changed=False;self.refresh();self.status.set('保存しました');return True

    def build_list(self):
        bar=ttk.Frame(self.listtab,padding=8);bar.pack(fill='x')
        for label,fn in (('単票を手入力',self.new),('選択行を開く',self.open_selected),('CSV一括取込',self.import_csv),('集計確認',self.batch_summary)):
            ttk.Button(bar,text=label,command=lambda f=fn:self.guarded(f)).pack(side='left',padx=4)
        columns=self.template['list_fields'];self.tree=ttk.Treeview(self.listtab,columns=columns,show='headings',selectmode='extended')
        labels={f['id']:f['label'] for f in self.template['fields']}
        for key in columns:self.tree.heading(key,text=labels[key]);self.tree.column(key,width=150,stretch=True)
        self.tree.pack(fill='both',expand=True);self.tree.bind('<Double-1>',lambda event:self.guarded(self.open_selected))
        for scope,label in (('selected','選択した記録（単票も選択可）'),('all','全記録')):
            row=ttk.LabelFrame(self.listtab,text=label,padding=6);row.pack(fill='x',padx=8,pady=4)
            for fmt,title in (('preview','プレビュー'),('pdf','PDF'),('png','PNG'),('print','印刷'),('csv','CSV')):
                ttk.Button(row,text=title,command=lambda s=scope,f=fmt:self.guarded(self.output,s,f)).pack(side='left',padx=4)

    def refresh(self):
        selected=set(self.tree.selection());self.tree.delete(*self.tree.get_children())
        for row in self.store.list():
            self.tree.insert('','end',iid=row['id'],values=[row['data'].get(key,'') for key in self.tree['columns']])
            if row['id'] in selected:self.tree.selection_add(row['id'])

    def selected(self):
        selected=set(self.tree.selection());rows=[self.store.get(key) for key in self.tree.get_children() if key in selected]
        if not rows:raise ValueError('一覧で記録を選択してください')
        return rows

    def open_selected(self):
        if not self.may_leave():return
        rows=self.selected()
        if len(rows)!=1:raise ValueError('1件だけ選択してください')
        self.set_values(rows[0]['data']);self.current=rows[0];self.notebook.select(self.entrytab)

    def preview_current(self):
        with generated_pdf(self.store.directory/'preview') as path:
            render_pdf(path,[self.values()],self.template);self.preview_view.set_pdf(path)
        self.status.set('保存前の内容をプレビューしました')

    def output(self,scope,fmt):
        if not self.may_leave():return
        rows=self.selected() if scope=='selected' else self.store.list()
        if not rows:raise ValueError('出力対象がありません')
        if fmt in ('preview','print'):
            with generated_pdf(self.store.directory/'preview',scope) as path:
                render_pdf(path,rows,self.template)
                if fmt=='preview':preview_window(self.root,path)
                else:
                    from printing import print_pdf
                    if not print_pdf(path,self.root.winfo_id()):return
                self.store.export_log(fmt,path,rows,self.template)
        elif fmt=='png':
            target=filedialog.askdirectory(title='PNGの保存先',parent=self.root)
            if not target:return
            from uuid import uuid4
            folder=Path(target)/(self.template['form_id']+'-'+uuid4().hex[:8]);folder.mkdir()
            path=folder/'records.pdf';render_pdf(path,rows,self.template);render_pngs(path,folder);self.store.export_log(fmt,path,rows,self.template)
        else:
            target=filedialog.asksaveasfilename(defaultextension='.'+fmt,filetypes=[(fmt.upper(),'*.'+fmt)],parent=self.root)
            if not target:return
            path=Path(target)
            if fmt=='csv':csv_export(path,rows,self.template)
            else:render_pdf(path,rows,self.template)
            self.store.export_log(fmt,path,rows,self.template)
        self.status.set(f'{len(rows)}件の{fmt.upper()}処理を完了')

    def import_csv(self):
        if not self.may_leave():return
        path=filedialog.askopenfilename(filetypes=[('CSV','*.csv')],parent=self.root)
        if not path:return
        rows=csv_read(path,self.template)
        if not rows:raise ValueError('CSVにデータ行がありません')
        if not messagebox.askyesno('取込確認',f'{len(rows)}件の実績を新規追加します。続行しますか？',parent=self.root):return
        self.store.import_rows(rows,self.template,'CSV取込: '+Path(path).name);self.refresh()

    def batch_summary(self):
        cfg=self.template['summary_config'];rows=self.selected()
        result=summary(rows,cfg.get('number_field'),cfg['quantity_field'],cfg.get('unit_field'))
        totals='\n'.join(f"{value} {unit or cfg.get('unit','')}" for unit,value in result['quantity_totals'].items()) or '0'
        messagebox.showinfo(self.template.get('quantity_summary_title','選択した記録の集計'),f"件数: {result['count']}\n数量合計:\n{totals}\n数量未記載: {result['missing_quantity_count']}件",parent=self.root)

    def build_settings(self):
        bar=ttk.Frame(self.settingtab,padding=8);bar.pack(side='bottom',fill='x')
        for label,fn in (('設定を適用・保存',self.save_settings),('設定JSONを取込',self.import_template),('設定JSONを書出',self.export_template)):
            ttk.Button(bar,text=label,command=lambda f=fn:self.guarded(f)).pack(side='left',padx=4)
        canvas=tk.Canvas(self.settingtab,highlightthickness=0);scroll=ttk.Scrollbar(self.settingtab,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        body=ttk.Frame(canvas,padding=8);win=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        self.layout_settings=LayoutSettings(body,self.template);self.layout_settings.pack(fill='x',pady=5)
        self.background_settings=None
        if self.template.get('render_mode')=='background':
            from background_settings import BackgroundSettings
            self.background_settings=BackgroundSettings(body,self.template);self.background_settings.pack(fill='x',pady=5)
        self.field_settings=FieldDefaultsSettings(body,self.template);self.field_settings.pack(fill='x',pady=5)
        random=ttk.LabelFrame(body,text='入力文字の位置だけをずらす（内容は変えません）',padding=6);random.pack(fill='x')
        self.random_enabled=tk.BooleanVar(value=self.template.get('random_print_enabled',False));ttk.Checkbutton(random,text='ランダム印字',variable=self.random_enabled).grid(row=0,column=0)
        self.random_axes={}
        for col,key in enumerate(('random_print_x_mm','random_print_y_mm'),1):
            ttk.Label(random,text=('横' if col==1 else '縦')+' ±mm').grid(row=0,column=col*2-1);v=tk.StringVar(value=str(self.template.get(key,.3)));self.random_axes[key]=v;ttk.Entry(random,textvariable=v,width=8).grid(row=0,column=col*2)
        ttk.Label(body,text=self.template.get('settings_notice','既存の記録は設定変更で書き換えません。'),wraplength=1000,padding=8).pack(fill='x')
        self.json_edit=tk.Text(body,height=18,wrap='none');self.json_edit.pack(fill='both',expand=True);self.json_edit.insert('1.0',json.dumps(self.template,ensure_ascii=False,indent=2))

    def save_settings(self):
        if not self.may_leave():return
        t=json.loads(self.json_edit.get('1.0','end'));self.layout_settings.apply(t);self.field_settings.apply(t)
        if self.background_settings:self.background_settings.apply(t)
        t['random_print_enabled']=self.random_enabled.get()
        for key,v in self.random_axes.items():t[key]=float(v.get())
        self.validate_policy(t);validate_template(t)
        if t.get('render_mode')!='background' or t.get('background',{}).get('status')=='ready':
            with generated_pdf(self.store.directory/'preview','settings') as path:render_pdf(path,[blank(t)],t)
        data=self.values();self.store.set_template(t);self.template=t
        if self.background_settings:self.background_settings.saved(t)
        for child in self.entrytab.winfo_children():child.destroy()
        self.vars={};self.widgets={};self.choice_vars={};self.build_entry();self.set_values(data)
        self.json_edit.delete('1.0','end');self.json_edit.insert('1.0',json.dumps(t,ensure_ascii=False,indent=2));self.status.set('設定を保存しました。既存記録は保持しています')

    def import_template(self):
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')],parent=self.root)
        if not path:return
        from core import load_template
        t=self.store.prepare_definition(load_template(path));self.validate_policy(t);validate_template(t)
        self.layout_settings.load(t);self.field_settings.load(t);self.random_enabled.set(t.get('random_print_enabled',False))
        if self.background_settings:self.background_settings.load(t)
        for key,v in self.random_axes.items():v.set(str(t.get(key,.3)))
        self.json_edit.delete('1.0','end');self.json_edit.insert('1.0',json.dumps(t,ensure_ascii=False,indent=2));self.status.set('設定を読み込みました。適用・保存で確定します')

    def export_template(self):
        path=filedialog.asksaveasfilename(defaultextension='.json',parent=self.root)
        if path:atomic_json(path,self.template)

    def backup(self):
        path=filedialog.asksaveasfilename(defaultextension='.sqlite3',parent=self.root)
        if not path:return
        if Path(path).resolve()==(self.store.directory/'records.sqlite3').resolve():raise ValueError('使用中のDBはバックアップ先に指定できません')
        self.store.backup(path,self.template)

    def switch_folder(self):
        if self.folder_switch_handler:return self.folder_switch_handler()
        raise ValueError('保存先の切替は帳票選択画面から開いて実行してください')

    def close(self):
        if self.may_leave():self.store.close();self.root.destroy()
