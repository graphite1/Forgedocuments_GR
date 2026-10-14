import queue,threading
import tkinter as tk
from tkinter import ttk,messagebox
import updates

class UpdateWindow(tk.Toplevel):
    def __init__(self,parent,on_apply):
        super().__init__(parent);self.title('Forgedocuments GR｜アプリの更新');self.geometry('650x430')
        self.on_apply=on_apply;self.manifest=None;self.staged=None;self.running=False;self.results=queue.Queue()
        self.status=tk.StringVar(value='現在版 '+updates.metadata()['version'])
        ttk.Label(self,textvariable=self.status,padding=12).pack(fill='x')
        self.notes=tk.Text(self,wrap='word',height=13);self.notes.pack(fill='both',expand=True,padx=12)
        self.notes.insert('1.0','更新を確認すると最新版と変更内容を表示します。\n保存した伝票と会社別設定は保持します。');self.notes.configure(state='disabled')
        bar=ttk.Frame(self,padding=12);bar.pack(fill='x')
        self.check=ttk.Button(bar,text='更新を確認',command=lambda:self.work('check',updates.fetch_latest));self.check.pack(side='left')
        self.fetch=ttk.Button(bar,text='ダウンロード',state='disabled',command=lambda:self.work('download',lambda:updates.download(self.manifest)));self.fetch.pack(side='left',padx=8)
        self.apply=ttk.Button(bar,text='更新して再起動',state='disabled',command=self.apply_update);self.apply.pack(side='left')
        self.protocol('WM_DELETE_WINDOW',self.leave);self.after(100,self.poll)

    def leave(self):
        if self.running:messagebox.showinfo('処理中','更新処理が終了するまでお待ちください',parent=self)
        else:self.destroy()

    def work(self,kind,fn):
        if self.running:return
        self.running=True;self.check.configure(state='disabled');self.fetch.configure(state='disabled');self.apply.configure(state='disabled');self.status.set('更新情報を確認中…' if kind=='check' else 'ダウンロード・署名・整合性を確認中…')
        def run():
            try:self.results.put((kind,fn(),None))
            except Exception as e:self.results.put((kind,None,str(e)))
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        if not self.winfo_exists():return
        try:
            kind,value,error=self.results.get_nowait();self.running=False;self.check.configure(state='normal')
            if error:self.status.set('更新処理を完了できません');messagebox.showerror('更新',error,parent=self)
            elif kind=='check':
                self.manifest=value;self.staged=None;is_new=updates.newer(value)
                self.status.set(f"現在版 {updates.metadata()['version']} ／ 最新版 {value['version']}"+('' if is_new else '（更新なし）'))
                self.notes.configure(state='normal');self.notes.delete('1.0','end');self.notes.insert('1.0',value['release_notes']);self.notes.configure(state='disabled')
                self.fetch.configure(state='normal' if is_new else 'disabled')
            else:self.staged=value;self.status.set('更新ファイルの準備が完了しました');self.apply.configure(state='normal')
        except queue.Empty:pass
        self.after(100,self.poll)

    def apply_update(self):
        if self.staged and not self.running:
            try:self.on_apply(self.staged)
            except Exception as e:messagebox.showerror('更新',str(e),parent=self)
