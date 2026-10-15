"""Blue artwork controls, kept separate from variable black-ink settings."""
import tkinter as tk
from tkinter import ttk
from blue_ink import KEY,density


class BlueInkSettings(ttk.LabelFrame):
    def __init__(self,parent,template):
        super().__init__(parent,text='青い枠・固定文字の濃さ',padding=8)
        self.value=tk.StringVar()
        ttk.Label(self,text='青印字の濃さ 35～150%').grid(row=0,column=0,sticky='w')
        ttk.Entry(self,textvariable=self.value,width=10).grid(row=0,column=1,padx=8)
        ttk.Label(self,text='100%は現在の青色です。黒い入力文字とは別に調整します。\n枠外の「納入書（計画）」は読みやすい濃さを保ちます。元の背景画像は変更しません。').grid(row=1,column=0,columnspan=2,sticky='w',pady=4)
        self.load(template)

    def load(self,template):self.value.set(f'{density(template)*100:g}')

    def apply(self,template):
        candidate=dict(template,**{KEY:float(self.value.get())/100})
        template[KEY]=density(candidate)
