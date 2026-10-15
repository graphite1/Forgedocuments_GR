"""Reusable paper layout and per-field input defaults for form screens."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk
from page_layout import PAPERS, defaults


class InputPrintSettings(ttk.LabelFrame):
    """Variable ink only. Fixed artwork and its font never use these settings."""
    def __init__(self,parent,template):
        super().__init__(parent,text='入力文字の印字（固定背景・固定住所は変えません）',padding=8)
        import os
        from pathlib import Path
        self.fonts={'帳票設定・Windows標準':''}
        for label,name in (('MS ゴシック','msgothic.ttc'),('メイリオ','meiryo.ttc')):
            path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
            if path.is_file():self.fonts[label]=str(path)
        self.font=tk.StringVar();self.style=tk.StringVar()
        from tomei_print_font import PROFILE,LABEL,validated_file
        self.sample_profile=PROFILE
        if template.get('form_id')=='tomei_taiheiyo' and (validated_file() or template.get('input_font_profile')==PROFILE):
            label=LABEL if validated_file() else LABEL+'（未同梱）'
            self.fonts[label]='@'+PROFILE
        ttk.Label(self,text='入力の書体').grid(row=0,column=0,sticky='w')
        self.font_selector=ttk.Combobox(self,textvariable=self.font,state='readonly',width=25)
        self.font_selector.grid(row=0,column=1,sticky='w')
        ttk.Label(self,text='印字').grid(row=0,column=2,sticky='w',padx=8)
        self.styles={'伝票印字':'printer','通常':'plain','従来の太字':'smooth','従来のドット':'impact'}
        ttk.Combobox(self,textvariable=self.style,values=list(self.styles),state='readonly',width=15).grid(row=0,column=3)
        self.vars={}
        self.defaults={'input_density':1,'input_transparency':0,'input_width_scale':1,'input_tracking_em':0,'input_weight_em':.018}
        for i,(key,label) in enumerate((('input_transparency','透過度 0〜100%'),('input_density','文字色の濃さ 35〜100%'),
                                       ('input_width_scale','字幅 80〜120%'),('input_tracking_em','字間 0〜20%'),('input_weight_em','線の太さ 0〜6%')),1):
            row,col=1+(i-1)//2,((i-1)%2)*2
            ttk.Label(self,text=label).grid(row=row,column=col,sticky='w',padx=4,pady=4)
            v=tk.StringVar();self.vars[key]=v;ttk.Entry(self,textvariable=v,width=10).grid(row=row,column=col+1,sticky='w')
        ttk.Label(self,text='透過度：0%=不透明、100%=透明。文字色の濃さはグレー色の調整です。\n字間・線の太さは文字サイズに対する割合です。背景・固定文字は変えません。').grid(row=4,column=0,columnspan=4,sticky='w')
        self.load(template)
        if '@'+self.sample_profile in self.fonts.values():
            ttk.Label(self,text='専用書体は数字・小数点・ハイフン・Bに適用し、他の文字は標準書体で印字します。').grid(row=5,column=0,columnspan=4,sticky='w')

    def load(self,template):
        path=template.get('input_font_path','')
        if path not in self.fonts.values():self.fonts['現在の指定']=path
        self.font_selector['values']=list(self.fonts)
        selected='@'+self.sample_profile if template.get('form_id')=='tomei_taiheiyo' and template.get('input_font_profile')==self.sample_profile else path
        self.font.set(next(label for label,value in self.fonts.items() if value==selected))
        self.style.set(next((label for label,value in self.styles.items() if value==template.get('input_print_style','plain')),'通常'))
        for key,v in self.vars.items():v.set(f"{float(template.get(key,self.defaults[key]))*100:g}")

    def apply(self,template):
        selected=self.fonts[self.font.get()]
        if selected=='@'+self.sample_profile:
            template['input_font_profile']=self.sample_profile
        else:
            template['input_font_path']=selected
            template.pop('input_font_profile',None)
        template['input_print_style']=self.styles[self.style.get()]
        for key,v in self.vars.items():template[key]=float(v.get())/100


class LayoutSettings(ttk.LabelFrame):
    def __init__(self,parent,template):
        super().__init__(parent,text='用紙・面付け（行＝縦、列＝横）',padding=8)
        self.vars={}
        self.maps={'paper':{'原本寸法':'original','任意サイズ':'custom'},'orientation':{'縦':'portrait','横':'landscape'},'scale':{'原寸を維持':'actual','枠に合わせて縮小':'fit'},'align_x':{'中央':'center','左':'start'},'align_y':{'中央':'center','上':'start'}}
        fields=[('paper','用紙',list(PAPERS)+['原本寸法','任意サイズ']),('orientation','向き',['縦','横']),('scale','倍率',['原寸を維持','枠に合わせて縮小']),
                ('rows','行数',None),('columns','列数',None),('margin_x_mm','左右余白 mm',None),('margin_y_mm','上下余白 mm',None),
                ('gap_x_mm','横の間隔 mm',None),('gap_y_mm','縦の間隔 mm',None),('custom_width_mm','任意用紙の幅 mm',None),('custom_height_mm','任意用紙の高さ mm',None),('align_x','横の配置',['中央','左']),('align_y','縦の配置',['中央','上'])]
        for i,(key,label,choices) in enumerate(fields):
            row,col=divmod(i,3);col*=2
            ttk.Label(self,text=label).grid(row=row,column=col,sticky='w',padx=4,pady=3)
            v=tk.StringVar();self.vars[key]=v
            w=ttk.Combobox(self,textvariable=v,values=choices,state='readonly',width=12) if choices else ttk.Entry(self,textvariable=v,width=12)
            w.grid(row=row,column=col+1,sticky='ew',padx=4,pady=3)
        ttk.Label(self,text='左上から右へ、次に下へ配置します。原寸で入らない場合は設定を変更してください。').grid(row=5,column=0,columnspan=6,sticky='w')
        self.load(template)

    def load(self,template):
        cfg=defaults(template);cfg.update(template.get('page_layout',{}))
        for k,v in self.vars.items():
            reverse={internal:label for label,internal in self.maps.get(k,{}).items()}
            v.set(str(reverse.get(cfg[k],cfg[k])))

    def apply(self,template):
        cfg={}
        for k,v in self.vars.items():
            cfg[k]=int(v.get()) if k in ('rows','columns') else self.maps[k].get(v.get(),v.get()) if k in self.maps else float(v.get())
        template['page_layout']=cfg


class FieldDefaultsSettings(ttk.LabelFrame):
    def __init__(self,parent,template):
        super().__init__(parent,text='項目の入力候補・既定値・固定値',padding=8)
        self.current=None;self.pending={};self.fields={}
        self.selected=tk.StringVar();self.default=tk.StringVar();self.fixed=tk.StringVar();self.locked=tk.BooleanVar()
        self.selector=ttk.Combobox(self,textvariable=self.selected,state='readonly',width=30);self.selector.grid(row=0,column=0,columnspan=2,sticky='w');self.selector.bind('<<ComboboxSelected>>',self.select)
        ttk.Label(self,text='既定値（新規入力の開始値・編集可）').grid(row=1,column=0,sticky='w')
        ttk.Entry(self,textvariable=self.default,width=45).grid(row=1,column=1,sticky='ew')
        self.fixed_toggle=ttk.Checkbutton(self,text='固定値を使う（新規入力で編集不可）',variable=self.locked);self.fixed_toggle.grid(row=2,column=0,sticky='w')
        self.fixed_entry=ttk.Entry(self,textvariable=self.fixed,width=45);self.fixed_entry.grid(row=2,column=1,sticky='ew')
        ttk.Label(self,text='候補（1行に1候補・文字や数値は候補外も入力可）').grid(row=3,column=0,sticky='nw')
        self.suggestions=tk.Text(self,height=3,width=45);self.suggestions.grid(row=3,column=1,sticky='ew')
        ttk.Label(self,text='既存記録は書き換えません。日付・時刻・画像は固定できません。配合の候補は確認済みの表記をそのまま登録してください。').grid(row=4,column=0,columnspan=2,sticky='w')
        self.columnconfigure(1,weight=1);self.load(template)

    def load(self,template):
        self.fields={f['id']:deepcopy(f) for f in template['fields'] if f['type'] not in ('image','layout_only','multi_choice') and f.get('input',True)}
        self.labels={f"{f['label']} [{f['id']}]":f['id'] for f in self.fields.values()}
        self.selector['values']=list(self.labels);self.pending={};self.current=None
        if self.labels:self.selected.set(next(iter(self.labels)));self.select()

    def stash(self):
        if self.current is None:return
        values={'default':self.default.get(),'suggestions':self.suggestions.get('1.0','end-1c').splitlines()}
        values['fixed_value']=self.fixed.get() if self.locked.get() else None
        self.pending[self.current]=values

    def select(self,event=None):
        self.stash();self.current=self.labels[self.selected.get()]
        f=self.fields[self.current];values=dict(f);values.update(self.pending.get(self.current,{}))
        self.default.set(values.get('default',''));self.fixed.set(values.get('fixed_value') or '');self.locked.set(values.get('fixed_value') is not None)
        enabled=f['type'] in ('text','decimal','integer','choice')
        self.fixed_toggle['state']='normal' if enabled else 'disabled';self.fixed_entry['state']='normal' if enabled else 'disabled'
        self.suggestions.delete('1.0','end');self.suggestions.insert('1.0','\n'.join(values.get('suggestions',[])))

    def apply(self,template):
        self.stash()
        for field in template['fields']:
            if field['id'] in self.pending:
                values=deepcopy(self.pending[field['id']]);fixed=values.pop('fixed_value')
                field.update(values)
                if fixed is None:field.pop('fixed_value',None)
                else:field['fixed_value']=fixed
