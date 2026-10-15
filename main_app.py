"""Desktop shell. Future forms are shipped as additional catalog screen modules."""
import atexit,hashlib,json,os,sys,tempfile,traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from core import atomic_json
from form_registry import catalog,open_screen,default_definition
from app_storage import AppStorage,open_folder
import updates
from desktop_theme import configure_theme

def profiles_path():return Path(os.environ.get('APPDATA',str(Path.home())))/'ForgedocumentsGR'/'profiles.json'

def read_profiles():
    p=profiles_path()
    data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    # Keep the exact legacy AC storage folder, do not move existing files.
    legacy=p.parent.parent/'AcToyoakeApp'/'preferences.json'
    if 'ac_toyoake' not in data and legacy.exists():
        old=json.loads(legacy.read_text(encoding='utf-8'));data['ac_toyoake']=old['directory']
    return data

class Home:
    def __init__(self,root,profiles=None,storage_root=None):
        configure_theme(root)
        self.root=root;self.screens={};self.update_dialog=None
        self.storage=AppStorage(storage_root or updates.install_root(),read_profiles() if profiles is None else profiles,profiles_path())
        self.profiles={row['id']:str(self.storage.path(row['id'])) for row in catalog()}
        root.title('Forgedocuments GR｜帳票選択');root.geometry('820x560');root.minsize(650,420)
        ttk.Label(root,text='Forgedocuments GR',font=('Yu Gothic UI',24,'bold'),padding=20).pack(anchor='w')
        ttk.Label(root,text='使用する帳票を選択してください',padding=(20,0,20,16)).pack(anchor='w')
        ttk.Label(root,text='保存先はアプリ内で帳票ごとに自動設定します。フォルダーの指定は不要です。',padding=(20,0,20,8)).pack(anchor='w')
        for row in catalog():
            frame=ttk.LabelFrame(root,text=row['title'],padding=16);frame.pack(fill='x',padx=20,pady=8)
            ttk.Label(frame,text=row['description']).pack(side='left')
            ttk.Button(frame,text='開く',command=lambda r=row:self.open(r)).pack(side='right')
        footer=ttk.Frame(root,padding=20);footer.pack(side='bottom',fill='x')
        ttk.Label(footer,text='v'+updates.metadata()['version']).pack(side='left')
        ttk.Button(footer,text='アプリの更新',command=self.show_updates).pack(side='right')
        root.protocol('WM_DELETE_WINDOW',self.close)

    def open(self,row):
        try:
            if row['id'] in self.screens and self.screens[row['id']].root.winfo_exists():
                self.screens[row['id']].root.lift();return
            directory=self.storage.prepare(default_definition(row))
            win=tk.Toplevel(self.root)
            try:screen=open_screen(row,win,directory)
            except Exception:win.destroy();raise
            self.screens[row['id']]=screen
            screen.folder_open_handler=lambda:open_folder(directory)
            if row['id'] in self.storage.notices:screen.status.set(self.storage.notices.pop(row['id']))
        except Exception as e:messagebox.showerror('帳票を開けません',str(e),parent=self.root)

    def living(self):return [s for s in self.screens.values() if s.root.winfo_exists()]

    def may_leave(self):return all(s.may_leave() for s in self.living())

    def dispose(self):
        for s in self.living():s.store.close()
        self.root.destroy()

    def close(self):
        if self.update_dialog and self.update_dialog.winfo_exists() and self.update_dialog.running:
            messagebox.showinfo('更新処理中','ダウンロードが完了するまでお待ちください',parent=self.root);return
        if self.may_leave():self.dispose()

    def show_updates(self):
        if self.update_dialog and self.update_dialog.winfo_exists():self.update_dialog.lift();return
        from update_window import UpdateWindow
        self.update_dialog=UpdateWindow(self.root,self.apply)

    def apply(self,directory):
        if not self.may_leave():return
        if not messagebox.askyesno('更新して再起動','保存済みのデータをバックアップし、更新して再起動しますか？',parent=self.root):return
        updates.request_apply(directory,list(self.profiles.values()));self.dispose()

def diagnostic():
    from desktop_diagnostic import run
    return run(os.environ.get('FORGEDOCUMENTS_DIAGNOSTIC_DIR'))


_instance_handle=None

def release_instance():
    global _instance_handle
    if _instance_handle is not None:
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle(_instance_handle);_instance_handle=None

def acquire_instance():
    global _instance_handle
    if not getattr(sys,'frozen',False):return True
    if _instance_handle is not None:return True
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    # One installation shares a mutex across routed versions. No reads or
    # writes to running.lock, which could itself cause Errno 13 on Windows.
    digest=hashlib.sha256(os.path.normcase(str(updates.install_root())).encode('utf-8')).hexdigest()
    handle=kernel.CreateMutexW(None,False,'Local\\ForgedocumentsGR-'+digest)
    error=ctypes.get_last_error()
    if not handle:raise OSError(error,'起動確認に失敗しました。Windowsのアクセス権を確認してください')
    if error==183:
        kernel.CloseHandle(handle)
        return False
    _instance_handle=handle;atexit.register(release_instance)
    return True

def main():
    if '--diagnostic' in sys.argv:diagnostic();return
    if '--apply-update' in sys.argv:updates.apply_transaction(sys.argv[sys.argv.index('--apply-update')+1]);return
    if updates.route_to_current():return
    if not acquire_instance():
        root=tk.Tk();root.withdraw()
        messagebox.showinfo('Forgedocuments GR','このアプリは既に起動しています。開いている画面をご利用ください',parent=root)
        root.destroy();return
    root=tk.Tk();home=Home(root)
    ready=os.environ.get('FORGEDOCUMENTS_READY_FILE')
    if ready:root.after_idle(lambda:Path(ready).write_text('ready',encoding='ascii'))
    if '--smoke-test' in sys.argv:root.withdraw();root.after(600,home.close)
    root.mainloop()

if __name__=='__main__':main()
