from __future__ import annotations
import copy, json, os, sys, tempfile, traceback, uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from core import *

class App:
    def __init__(self,root,directory):
        self.root=root; self.store=Store(directory); self.template=self.store.template()
        self.current=None;self.loaded_values=None;self.suspend=False;self.changed=False;self.widgets={};self.vars={}
        root.title('GR｜運搬明細書');root.geometry('1220x840');root.minsize(880,640)
        style=ttk.Style();style.theme_use('clam');style.configure('TButton',padding=(9,5));style.configure('TNotebook.Tab',padding=(15,7))
        top=ttk.Frame(root,padding=10);top.pack(fill='x')
        ttk.Label(top,text='運搬明細書',font=('Yu Gothic UI',19,'bold')).pack(side='left')
        ttk.Button(top,text='保存先を切替',command=self.switch_folder).pack(side='right')
        ttk.Button(top,text='バックアップ',command=self.backup).pack(side='right',padx=6)
        self.notebook=ttk.Notebook(root);self.notebook.pack(fill='both',expand=True,padx=10,pady=4)
        self.entrytab=ttk.Frame(self.notebook);self.listtab=ttk.Frame(self.notebook);self.settingtab=ttk.Frame(self.notebook)
        for frame,name in [(self.entrytab,'入力'),(self.listtab,'一覧・出力'),(self.settingtab,'帳票設定')]:self.notebook.add(frame,text=name)
        self.status=tk.StringVar();ttk.Label(root,textvariable=self.status,padding=8).pack(fill='x')
        self.build_entry();self.build_list();self.build_settings();self.new(check=False);self.refresh()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.bind('<Control-s>',lambda e:self.guarded(self.save))

    def guarded(self,fn,*args):
        try:return fn(*args)
        except Exception as e:
            log=self.store.directory/'errors.log'
            with log.open('a',encoding='utf-8') as f:f.write(now()+'\n'+traceback.format_exc()+'\n')
            messagebox.showerror('処理を完了できません',str(e),parent=self.root)
            return False

    def dirty(self,*a):
        if not self.suspend:self.changed=True;self.status.set('未保存の入力があります')

    def may_leave(self):
        if not self.changed:return True
        r=messagebox.askyesnocancel('未保存の入力','入力内容を保存しますか？',parent=self.root)
        if r is None:return False
        if r:return bool(self.guarded(self.save))
        return True

    def build_entry(self):
        bar=ttk.Frame(self.entrytab,padding=8);bar.pack(fill='x')
        for label,cmd in [('新規',lambda:self.new()),('複製して新規',self.duplicate),('保存',lambda:self.guarded(self.save)),('プレビュー',lambda:self.guarded(self.preview_current))]:ttk.Button(bar,text=label,command=cmd).pack(side='left',padx=3)
        ttk.Label(bar,text='空欄可｜日付 YYYY-MM-DD｜時間 HH:MM｜番号は文字列として保存').pack(side='left',padx=12)
        pane=ttk.Panedwindow(self.entrytab,orient='horizontal');pane.pack(fill='both',expand=True)
        left=ttk.Frame(pane);right=ttk.Frame(pane);pane.add(left,weight=3);pane.add(right,weight=2)
        cv=tk.Canvas(left,highlightthickness=0);scroll=ttk.Scrollbar(left,orient='vertical',command=cv.yview);cv.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');cv.pack(side='left',fill='both',expand=True)
        form=ttk.Frame(cv,padding=12);win=cv.create_window((0,0),window=form,anchor='nw')
        form.bind('<Configure>',lambda e:cv.configure(scrollregion=cv.bbox('all')));cv.bind('<Configure>',lambda e:cv.itemconfigure(win,width=e.width))
        def wheel(e):
            cv.yview_scroll(int(-e.delta/120),'units')
        cv.bind('<Enter>',lambda e:cv.bind_all('<MouseWheel>',wheel));cv.bind('<Leave>',lambda e:cv.unbind_all('<MouseWheel>'))
        groups={}
        for f in self.template['fields']:
            if f['group'] not in groups:
                fr=ttk.LabelFrame(form,text=f['group'],padding=9);fr.pack(fill='x',pady=5);fr.columnconfigure(1,weight=1);groups[f['group']]=fr
            fr=groups[f['group']];row=len(fr.grid_slaves())//2
            ttk.Label(fr,text=f['label']).grid(row=row,column=0,sticky='nw',padx=(0,12),pady=5)
            if f['type']=='multiline':
                w=tk.Text(fr,height=3,width=30,undo=True,font=('Yu Gothic UI',10));w.grid(row=row,column=1,sticky='ew',pady=4)
                w.bind('<<Modified>>',lambda e:self.text_dirty(e));self.widgets[f['id']]=w
            elif f['type']=='image':
                holder=ttk.Frame(fr);holder.grid(row=row,column=1,sticky='ew');v=tk.StringVar();self.vars[f['id']]=v
                ttk.Button(holder,text='画像を選択',command=lambda fid=f['id']:self.guarded(self.pick_image,fid)).pack(side='left')
                ttk.Button(holder,text='解除',command=lambda fid=f['id']:self.vars[fid].set('')).pack(side='left',padx=4)
                self.image_status=tk.StringVar(value='なし');ttk.Label(holder,textvariable=self.image_status).pack(side='left')
                v.trace_add('write',lambda *a:(self.dirty(),self.image_status.set('登録済み' if self.vars['receipt_image'].get() else 'なし')))
            else:
                v=tk.StringVar();self.vars[f['id']]=v
                w=ttk.Combobox(fr,textvariable=v,values=f['choices'],state='readonly') if f['type']=='choice' else ttk.Entry(fr,textvariable=v)
                w.grid(row=row,column=1,sticky='ew',pady=4);v.trace_add('write',self.dirty)
        self.preview_label=ttk.Label(right,text='プレビューを押すと、保存前の内容も確認できます',anchor='center');self.preview_label.pack(fill='both',expand=True,padx=8,pady=8)
        ttk.Label(right,text='受領印は文字か画像のどちらかを使用。画像がある場合は画像を印字。\n数量単位は空欄から開始。記入例の「台」を自動設定しません。',wraplength=390,justify='left').pack(fill='x',padx=10,pady=12)

    def text_dirty(self,e):
        if e.widget.edit_modified():self.dirty();e.widget.edit_modified(False)

    def values(self):
        return {f['id']:(self.widgets[f['id']].get('1.0','end-1c') if f['type']=='multiline' else self.vars[f['id']].get()) for f in self.template['fields']}

    def set_values(self,data):
        self.suspend=True
        for f in self.template['fields']:
            value=data.get(f['id'],'')
            if f['type']=='multiline':
                w=self.widgets[f['id']];w.delete('1.0','end');w.insert('1.0',value);w.edit_modified(False)
            else:self.vars[f['id']].set(value)
        self.suspend=False;self.changed=False;self.loaded_values=copy.deepcopy(data)

    def new(self,check=True):
        if check and not self.may_leave():return
        self.current=None;self.set_values(blank(self.template));self.notebook.select(self.entrytab);self.status.set('新規入力｜保存先: '+str(self.store.directory))

    def duplicate(self):
        data=self.values()
        if not self.may_leave():return
        self.current=None;self.set_values(data);self.changed=True;self.vars['number'].set('');self.vars['receipt_text'].set('');self.vars['receipt_image'].set('')
        self.status.set('新規に複製しました。No.と受領印は空欄です')

    def save(self):
        data=self.values();errs=validate(data,self.template)
        if errs:raise ValueError('\n'.join(errs))
        if self.current and data==self.current['data']:
            self.changed=False;return True
        dup=[r for r in self.store.list() if data.get('number') and r['data'].get('number')==data['number'] and (not self.current or r['id']!=self.current['id'])]
        if dup and not messagebox.askyesno('No.の重複',f"同じNo.が{len(dup)}件あります。重複したまま保存しますか？",parent=self.root):return False
        reason='新規登録'
        if self.current:
            reason=simpledialog.askstring('訂正理由','変更理由を入力してください',parent=self.root)
            if reason is None:return False
        self.current=self.store.save(data,self.template,self.current['id'] if self.current else None,self.current['revision'] if self.current else None,reason)
        self.changed=False;self.loaded_values=copy.deepcopy(data);self.refresh();self.status.set('保存しました｜'+str(self.store.directory));return True

    def pick_image(self,fid):
        path=filedialog.askopenfilename(filetypes=[('画像','*.png *.jpg *.jpeg *.bmp'),('すべて','*.*')],parent=self.root)
        if path:self.vars[fid].set(image_encode(path))

    def build_list(self):
        bar=ttk.Frame(self.listtab,padding=8);bar.pack(fill='x')
        self.query=tk.StringVar();ttk.Label(bar,text='検索').pack(side='left');ttk.Entry(bar,textvariable=self.query,width=25).pack(side='left',padx=5);self.query.trace_add('write',lambda *a:self.refresh())
        self.archived=tk.BooleanVar();ttk.Checkbutton(bar,text='保管済みを表示',variable=self.archived,command=self.refresh).pack(side='left',padx=8)
        ttk.Button(bar,text='再読込',command=self.refresh).pack(side='left');ttk.Button(bar,text='開く',command=lambda:self.guarded(self.open_selected)).pack(side='left',padx=4)
        ttk.Button(bar,text='保管／復帰',command=lambda:self.guarded(self.archive_selected)).pack(side='left')
        ttk.Button(bar,text='訂正履歴',command=lambda:self.guarded(self.show_history)).pack(side='left',padx=4)
        cols=['date','number','recipient','site','kind','vehicle','quantity','quantity_unit','cumulative_quantity','cumulative_count']
        holder=ttk.Frame(self.listtab);holder.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(holder,columns=cols,show='headings',selectmode='extended')
        labels={f['id']:f['label'] for f in self.template['fields']}
        for col in cols:self.tree.heading(col,text=labels[col]);self.tree.column(col,width=115 if col not in ('recipient','kind') else 170,minwidth=70,stretch=False)
        sy=ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview);sx=ttk.Scrollbar(holder,orient='horizontal',command=self.tree.xview);self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.tree.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew');holder.rowconfigure(0,weight=1);holder.columnconfigure(0,weight=1)
        self.tree.bind('<Double-1>',lambda e:self.guarded(self.open_selected))
        for scope,title in [('selected','選択した行'),('all','全件（検索・表示条件に関係なく有効な記録すべて）')]:
            row=ttk.LabelFrame(self.listtab,text=title,padding=7);row.pack(fill='x',padx=8,pady=4)
            for label,fmt in [('PDF','pdf'),('PNG','png'),('プレビュー','preview'),('印刷','print'),('CSV','csv')]:
                ttk.Button(row,text=label,command=lambda s=scope,f=fmt:self.guarded(self.output,s,f)).pack(side='left',padx=4)
        row=ttk.Frame(self.listtab,padding=8);row.pack(fill='x')
        ttk.Button(row,text='CSV取込（列名で対応）',command=lambda:self.guarded(self.import_csv)).pack(side='left',padx=4)
        ttk.Button(row,text='選択行の累計を計算',command=lambda:self.guarded(self.cumulative)).pack(side='left',padx=4)
        ttk.Label(row,text='累計は登録順。計算対象と開始値を確認してから実行。').pack(side='left',padx=8)

    def refresh(self):
        if not hasattr(self,'tree'):return
        selected=set(self.tree.selection());self.tree.delete(*self.tree.get_children())
        q=self.query.get().casefold()
        for r in self.store.list(self.archived.get()):
            if q and q not in ' '.join(v for k,v in r['data'].items() if k!='receipt_image').casefold():continue
            self.tree.insert('', 'end',iid=r['id'],values=[r['data'].get(c,'') for c in self.tree['columns']])
            if r['id'] in selected:self.tree.selection_add(r['id'])

    def selected(self,one=False):
        ids=set(self.tree.selection());rows=[self.store.get(i) for i in self.tree.get_children() if i in ids]
        if not rows:raise ValueError('一覧で記録を選択してください')
        if one and len(rows)!=1:raise ValueError('1件だけ選択してください')
        return rows

    def open_selected(self):
        row=self.selected(one=True)[0]
        if not self.may_leave():return
        self.current=row;self.set_values(row['data']);self.notebook.select(self.entrytab);self.status.set('読込済み｜No. '+row['data'].get('number','')+'｜改訂 '+str(row['revision']))

    def archive_selected(self):
        if not self.may_leave():return
        rows=self.selected()
        for r in rows:self.store.archive(r['id'],not self.archived.get())
        if self.current and self.current['id'] in {r['id'] for r in rows}:self.new(check=False)
        self.refresh()

    def show_history(self):
        row=self.selected(one=True)[0];win=tk.Toplevel(self.root);win.title('訂正履歴');win.geometry('850x600')
        text=tk.Text(win,wrap='word');text.pack(fill='both',expand=True)
        labels={f['id']:f['label'] for f in self.template['fields']}
        for at,reason,before,after in self.store.history(row['id']):
            a=json.loads(before) if before else {};b=json.loads(after) if after else {}
            a=a.get('data',a);b=b.get('data',b)
            text.insert('end',f'{at}\n{reason}\n')
            for key in b.keys()|a.keys():
                if a.get(key,'')!=b.get(key,''):
                    av=a.get(key,'');bv=b.get(key,'')
                    if key=='receipt_image':av='画像あり' if av else 'なし';bv='画像あり' if bv else 'なし'
                    text.insert('end',f"  {labels.get(key,key)}: {av!r} → {bv!r}\n")
            text.insert('end','\n')
        text.configure(state='disabled')

    def preview_current(self):
        data=self.values();temp=self.store.directory/'preview';temp.mkdir(exist_ok=True);pdf=temp/'current.pdf';render_pdf(pdf,[data],self.template)
        import pymupdf as fitz
        from PIL import Image,ImageTk
        with fitz.open(pdf) as doc:
            pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples);im.thumbnail((440,610))
        self.preview_photo=ImageTk.PhotoImage(im);self.preview_label.configure(image=self.preview_photo,text='');self.status.set('保存前の内容をプレビューしました')

    def output(self,scope,fmt):
        if not self.may_leave():return
        rows=self.selected() if scope=='selected' else self.store.list()
        if not rows:raise ValueError('出力対象がありません')
        if fmt in ('preview','print'):
            directory=self.store.directory/'preview';directory.mkdir(exist_ok=True);path=directory/('selected.pdf' if scope=='selected' else 'all.pdf')
        elif fmt=='png':
            target=filedialog.askdirectory(title='PNGの保存先（専用サブフォルダを新規作成）',parent=self.root)
            if not target:return
            directory=Path(target)/('運搬明細書_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:4]);directory.mkdir();path=directory/'運搬明細書.pdf'
        else:
            target=filedialog.asksaveasfilename(title=f'{len(rows)}件を保存',defaultextension='.'+fmt,filetypes=[(fmt.upper(),'*.'+fmt)],initialfile='運搬明細書.'+fmt,parent=self.root)
            if not target:return
            path=Path(target)
        if fmt=='csv':csv_export(path,rows,self.template)
        else:render_pdf(path,rows,self.template)
        if fmt=='png':render_pngs(path,directory,dpi=200)
        if fmt=='preview':os.startfile(str(path))
        if fmt=='print':
            from printing import print_pdf
            if not print_pdf(path,self.root.winfo_id()):return
        self.store.export_log(fmt,path,rows,self.template);self.status.set(f'{len(rows)}件の{fmt.upper()}処理を完了｜{path}')

    def cumulative(self):
        if not self.may_leave():return
        rows=self.selected()
        quantity=simpledialog.askstring('開始累計量','選択行の直前までの累計量を入力',initialvalue='0',parent=self.root)
        if quantity is None:return
        count=simpledialog.askstring('開始累計台数','選択行の直前までの累計台数を入力',initialvalue='0',parent=self.root)
        if count is None:return
        numbers=' → '.join(r['data'].get('number','(No.空欄)') for r in rows)
        if not messagebox.askyesno('計算対象の確認',f'{len(rows)}件を登録順で計算します。\n{numbers}\n開始量 {quantity}、開始台数 {count}\n累計量・累計台数・累計量単位を訂正します。正味重量は保持します。',parent=self.root):return
        reason=simpledialog.askstring('訂正理由','累計を計算する理由',initialvalue='選択行の累計を計算',parent=self.root)
        if reason is None:return
        updates=self.store.apply_cumulative(rows,self.template,quantity,count,reason)
        if self.current and self.current['id'] in {r['id'] for r in updates}:
            self.current=self.store.get(self.current['id']);self.set_values(self.current['data'])
        self.refresh();self.status.set('累計を計算し、訂正履歴に記録しました')

    def import_csv(self):
        if not self.may_leave():return
        path=filedialog.askopenfilename(filetypes=[('CSV','*.csv')],parent=self.root)
        if not path:return
        data=csv_read(path,self.template)
        if not data:raise ValueError('CSVにデータ行がありません')
        existing={r['data'].get('number') for r in self.store.list() if r['data'].get('number')};seen=set();dups=[]
        for d in data:
            n=d.get('number')
            if n and (n in existing or n in seen):dups.append(n)
            seen.add(n)
        note='\nNo.重複: '+', '.join(dups[:15]) if dups else ''
        if not messagebox.askyesno('取込確認',f'{len(data)}件を新規追加します。既存記録と元CSVは変更しません。{note}\n続行しますか？',parent=self.root):return
        # Whole import is atomic; history is written alongside records.
        with self.store.db:
            self.store.db.execute('BEGIN IMMEDIATE')
            for d in data:
                rid=uuid.uuid4().hex;payload=json.dumps(d,ensure_ascii=False)
                self.store.db.execute('INSERT INTO records VALUES(?,?,1,?,?,0)',(rid,payload,now(),now()))
                self.store.db.execute('INSERT INTO history(record_id,at,reason,before_json,after_json) VALUES(?,?,?,?,?)',(rid,now(),'CSV取込: '+Path(path).name,None,payload))
        self.refresh();self.status.set(f'{len(data)}件を取り込みました')

    def build_settings(self):
        top=ttk.Frame(self.settingtab,padding=12);top.pack(fill='x')
        self.setting_vars={}
        options=[('width_mm','外周枠の幅 mm'),('height_mm','外周枠の高さ mm'),('original_margin_mm','原本寸法出力の外側余白 mm'),('font_path','日本語フォント TTF/TTC（空欄でWindows標準）')]
        for row,(key,label) in enumerate(options):
            ttk.Label(top,text=label).grid(row=row,column=0,sticky='w',pady=5)
            v=tk.StringVar(value=str(self.template.get(key,'')));self.setting_vars[key]=v;ttk.Entry(top,textvariable=v,width=55).grid(row=row,column=1,sticky='ew',pady=5)
        self.mode=tk.StringVar(value=self.template['page_mode']);ttk.Label(top,text='出力ページ').grid(row=4,column=0,sticky='w')
        modes=ttk.Frame(top);modes.grid(row=4,column=1,sticky='w')
        ttk.Radiobutton(modes,text='A4中央・実寸100%',variable=self.mode,value='A4').pack(side='left');ttk.Radiobutton(modes,text='原本寸法',variable=self.mode,value='original').pack(side='left',padx=8)
        self.ink_style=tk.StringVar(value=self.template.get('input_print_style','impact'))
        ttk.Label(top,text='青文字の印字').grid(row=5,column=0,sticky='w',pady=5)
        inks=ttk.Frame(top);inks.grid(row=5,column=1,sticky='w')
        ttk.Radiobutton(inks,text='ドット印字',variable=self.ink_style,value='impact').pack(side='left')
        ttk.Radiobutton(inks,text='通常の太字',variable=self.ink_style,value='smooth').pack(side='left',padx=8)
        ttk.Label(top,text='実寸はスキャン換算の暫定値。紙原本の実測値が分かれば修正してください。\n原本寸法ページは、枠線の欠けを防ぐため指定の外側余白を追加します。',wraplength=900).grid(row=6,column=0,columnspan=2,sticky='w',pady=8)
        bar=ttk.Frame(self.settingtab,padding=8);bar.pack(fill='x')
        ttk.Button(bar,text='設定を適用・保存',command=lambda:self.guarded(self.save_settings)).pack(side='left',padx=4)
        ttk.Button(bar,text='設定JSONを取込',command=lambda:self.guarded(self.import_template)).pack(side='left',padx=4)
        ttk.Button(bar,text='設定JSONを書出',command=lambda:self.guarded(self.export_template)).pack(side='left',padx=4)
        ttk.Label(self.settingtab,text='下のJSONで項目ごとの印字有無・文字サイズ・位置・必須・桁数・上限・固定文を変更できます。\n項目ID・型・追加削除を変更した場合は、別帳票用の画面改修も必要です。適用前にバックアップを推奨。',padding=8).pack(fill='x')
        box=ttk.Frame(self.settingtab);box.pack(fill='both',expand=True,padx=12,pady=8)
        self.json_edit=tk.Text(box,wrap='none',font=('Consolas',10));sy=ttk.Scrollbar(box,command=self.json_edit.yview);self.json_edit.configure(yscrollcommand=sy.set);sy.pack(side='right',fill='y');self.json_edit.pack(fill='both',expand=True)
        self.json_edit.insert('1.0',json.dumps(self.template,ensure_ascii=False,indent=2))

    def save_settings(self):
        if not self.may_leave():return
        t=json.loads(self.json_edit.get('1.0','end'))
        if [(f['id'],f['type']) for f in t['fields']]!=[(f['id'],f['type']) for f in self.template['fields']]:raise ValueError('画面と対応しない項目ID・型の変更です。項目定義の変更はコード側にも反映してください')
        for key,v in self.setting_vars.items():t[key]=v.get() if key=='font_path' else float(v.get())
        t['page_mode']=self.mode.get();t['input_print_style']=self.ink_style.get();validate_template(t)
        # Test rendering before saving malformed geometry/font settings.
        test=self.store.directory/'preview';test.mkdir(exist_ok=True);render_pdf(test/'settings_check.pdf',[blank(t)],t,validate_records=False)
        data=self.values()
        self.store.set_template(t);self.template=t
        for widget in self.entrytab.winfo_children():widget.destroy()
        self.vars={};self.widgets={};self.build_entry();self.set_values(data)
        labels={f['id']:f['label'] for f in t['fields']}
        for col in self.tree['columns']:self.tree.heading(col,text=labels[col])
        self.json_edit.delete('1.0','end');self.json_edit.insert('1.0',json.dumps(t,ensure_ascii=False,indent=2));self.status.set('帳票設定を保存しました。印字位置・文字・寸法に反映されます')

    def import_template(self):
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')],parent=self.root)
        if not path:return
        t=load_template(path);validate_template(t)
        self.json_edit.delete('1.0','end');self.json_edit.insert('1.0',json.dumps(t,ensure_ascii=False,indent=2))
        for k,v in self.setting_vars.items():v.set(str(t.get(k,'')))
        self.mode.set(t['page_mode']);self.ink_style.set(t.get('input_print_style','impact'));self.status.set('設定を読み込みました。「適用・保存」で確定します')

    def export_template(self):
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='template.json',parent=self.root)
        if path:atomic_json(path,self.template)

    def backup(self):
        def run():
            if not self.may_leave():return
            path=filedialog.asksaveasfilename(defaultextension='.sqlite3',initialfile='運搬明細書バックアップ_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sqlite3',parent=self.root)
            if path:
                if Path(path).resolve()==(self.store.directory/'records.sqlite3').resolve():raise ValueError('使用中のデータベースはバックアップ先に指定できません')
                self.store.backup(path,self.template);self.status.set('バックアップしました。SQLiteファイルと同名の設定JSONをセットで保管してください')
        self.guarded(run)

    def switch_folder(self):
        if not self.may_leave():return
        path=filedialog.askdirectory(title='別の保存先を選択（再起動します）',parent=self.root)
        if not path:return
        remember(path);self.store.close();self.root.destroy();main(path)

    def close(self):
        if self.may_leave():self.store.close();self.root.destroy()

def preferences():return Path(os.environ.get('APPDATA',str(Path.home())))/'AcToyoakeApp'/'preferences.json'

def remember(directory):
    p=preferences();p.parent.mkdir(parents=True,exist_ok=True);atomic_json(p,{'directory':str(directory)})

def main(directory=None,smoke=False):
    root=tk.Tk();root.withdraw()
    if directory is None:
        p=preferences()
        if p.exists():
            try:directory=json.loads(p.read_text(encoding='utf-8'))['directory']
            except (KeyError,ValueError):pass
        if not directory or not Path(directory).is_dir():
            directory=filedialog.askdirectory(title='伝票データの保存先フォルダを選んでください',parent=root)
            if not directory:root.destroy();return
        remember(directory)
    try:app=App(root,directory)
    except Exception as e:messagebox.showerror('起動エラー',str(e),parent=root);root.destroy();return
    if smoke:root.after(500,app.close)
    else:root.deiconify()
    root.mainloop()

if __name__=='__main__':
    if '--smoke-test' in sys.argv:
        with tempfile.TemporaryDirectory(prefix='ac_toyoake_launch_') as directory:main(directory,smoke=True)
    else:main(sys.argv[1] if len(sys.argv)>1 else None)
