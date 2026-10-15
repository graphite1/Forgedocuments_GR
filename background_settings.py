"""Choose and store a background candidate without editing the selected source."""
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image
from background_assets import missing_background
from blue_background import extract_background


class BackgroundSettings(ttk.LabelFrame):
    def __init__(self,parent,template):
        super().__init__(parent,text='青い固定印字の背景画像',padding=8)
        self.template=template;self.source=None;self.file_label=tk.StringVar()
        ttk.Label(self,textvariable=self.file_label,wraplength=950).grid(row=0,column=0,columnspan=9,sticky='w')
        ttk.Button(self,text='背景画像を選択',command=self.choose).grid(row=1,column=0,sticky='w',pady=5)
        from tomei_preset import bundled_source
        preset=bundled_source() if template.get('form_id')=='tomei_taiheiyo' else None
        if preset:ttk.Button(self,text='同梱の修正背景を選択',command=lambda:self.select_source(preset)).grid(row=1,column=1,columnspan=5,sticky='w')
        self.crop=[]
        for index,label in enumerate(('左','上','右','下')):
            ttk.Label(self,text=label+' px').grid(row=2,column=index*2)
            value=tk.StringVar(value='0');self.crop.append(value);ttk.Entry(self,textvariable=value,width=9).grid(row=2,column=index*2+1)
        self.angle=tk.StringVar(value='0');ttk.Label(self,text='傾き補正（度）').grid(row=3,column=0,columnspan=2,sticky='w')
        ttk.Entry(self,textvariable=self.angle,width=9).grid(row=3,column=2)
        self.page=tk.StringVar(value='0');ttk.Label(self,text='PDFページ（0から）').grid(row=3,column=3,columnspan=2)
        ttk.Entry(self,textvariable=self.page,width=9).grid(row=3,column=5)
        self.reviewed=tk.BooleanVar(value=False)
        ttk.Checkbutton(self,text='住所・選択肢・細字・罫線・手書き除外・切り出しを画像で確認済み',variable=self.reviewed).grid(row=4,column=0,columnspan=9,sticky='w',pady=5)
        ttk.Label(self,text='未確認の候補も設定として保存できます。誤字や欠けは補わず、確認前は帳票を出力しません。予定値を黒文字で重ね、各伝票の下部に「納入書（計画）」を表示します。',wraplength=950).grid(row=5,column=0,columnspan=9,sticky='w')
        issues=template.get('source_confirmation',{}).get('known_new_background_issues',[])
        self.issue_label=tk.StringVar()
        ttk.Label(self,textvariable=self.issue_label,wraplength=950).grid(row=6,column=0,columnspan=9,sticky='w',pady=4)
        self.initial_issues=issues
        ttk.Label(self,text='未解決の誤字・欠け（修正画像を確認後に更新）').grid(row=7,column=0,columnspan=9,sticky='w')
        self.errors=tk.Text(self,height=3,width=100);self.errors.grid(row=8,column=0,columnspan=9,sticky='ew')
        self.load(template)

    def load(self,template):
        self.template=template;self.config=copy.deepcopy(template.get('background',missing_background()));self.source=None;self.source_profile=None
        self.file_label.set({'missing':'背景画像は未取得です','draft':'背景候補を保存済み・未確認','ready':'背景画像を保存済み'}.get(self.config['status'],'背景状態不明'))
        self.reviewed.set(self.config.get('reviewed',False))
        processing=self.config.get('processing',{})
        for var,value in zip(self.crop,processing.get('crop_pixels_after_rotation',[0,0,0,0])):var.set(str(value))
        self.angle.set(str(processing.get('deskew_degrees',0)));self.page.set(str(processing.get('pdf_page',0)))
        issues=self.config.get('unresolved_text_errors',self.initial_issues if self.config['status']=='missing' else [])
        self.issue_label.set('提供背景の未解決事項: '+' / '.join(issues) if issues else '')
        self.errors.delete('1.0','end');self.errors.insert('1.0','\n'.join(issues))

    def choose(self):
        filename=filedialog.askopenfilename(title='青い固定印字を含む背景資料',filetypes=[('画像・PDF','*.png *.jpg *.jpeg *.pdf')],parent=self.winfo_toplevel())
        if not filename:return
        try:self.select_source(filename)
        except Exception as error:messagebox.showerror('背景資料を開けません',str(error),parent=self.winfo_toplevel())

    def select_source(self,filename):
        source=Path(filename)
        if source.suffix.lower()=='.pdf':
            import pymupdf
            with pymupdf.open(source) as doc:
                if not len(doc):raise ValueError('PDFにページがありません')
                width=round(doc[0].rect.width*300/72);height=round(doc[0].rect.height*300/72)
        else:
            with Image.open(source) as image:width,height=image.size
        self.source=source;self.file_label.set('選択した背景候補: '+source.name+'（元画像は変更しません）')
        for var,value in zip(self.crop,[0,0,width,height]):var.set(str(value))
        self.reviewed.set(False);self.angle.set('0');self.page.set('0')
        if self.template.get('form_id')=='tomei_taiheiyo':
            from tomei_preset import recognize, ORIGINAL_ISSUES
            self.source_profile=recognize(source)
            if self.source_profile:
                from tomei_profiles import CROP
                for var,value in zip(self.crop,CROP):var.set(str(value))
                self.errors.delete('1.0','end')
                self.errors.insert('1.0','\n'.join(ORIGINAL_ISSUES if self.source_profile=='original_with_typos' else []))
                self.issue_label.set('提供背景の未解決事項: '+' / '.join(ORIGINAL_ISSUES) if self.source_profile=='original_with_typos' else '')
                self.file_label.set('専用の寸法・切り出し・入力位置を自動適用: '+source.name+'（適用・保存で確定）')

    def apply(self,template):
        candidate=copy.deepcopy(self.config)
        if self.source and self.source_profile:
            from tomei_preset import apply_preset
            errors=[line.strip() for line in self.errors.get('1.0','end').splitlines() if line.strip()]
            updated=apply_preset(template,self.source,reviewed=self.reviewed.get(),errors=errors)
            template.clear();template.update(updated)
            return
        if self.source:
            candidate=extract_background(self.source,[int(v.get()) for v in self.crop],template['width_mm'],template['height_mm'],deskew_degrees=float(self.angle.get()),pdf_page=int(self.page.get()),reviewed=self.reviewed.get())
            if candidate['source_sha256']==self.config.get('source_sha256') and self.config.get('unresolved_text_errors'):
                candidate['unresolved_text_errors']=copy.deepcopy(self.config['unresolved_text_errors'])
        elif candidate['status']!='missing' and candidate['kind'] in ('original_blue','corrected_blue'):
            candidate['reviewed']=self.reviewed.get();candidate['status']='ready' if self.reviewed.get() else 'draft'
        candidate['unresolved_text_errors']=[line.strip() for line in self.errors.get('1.0','end').splitlines() if line.strip()]
        template['background']=candidate

    def saved(self,template):
        self.load(template)
