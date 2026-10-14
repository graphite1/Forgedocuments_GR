"""Shared PDF preview: right-drag pan and pointer-anchored Ctrl-wheel zoom."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import pymupdf
from PIL import Image, ImageTk

class PDFView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.doc=None; self.page=0; self.zoom=1.0; self.fit_mode=True
        self.offset=(0.0,0.0); self.photo=None; self.item=None; self.job=None
        self.last_size=None; self.pan_point=None
        bar=ttk.Frame(self);bar.pack(fill='x')
        for title,fn in [('全体表示',self.fit),('100％',self.actual),('−',lambda:self.change_zoom(.8)),('＋',lambda:self.change_zoom(1.25)),('前',lambda:self.turn(-1)),('次',lambda:self.turn(1))]:
            ttk.Button(bar,text=title,command=fn,width=7).pack(side='left',padx=2,pady=4)
        self.info=tk.StringVar(value='プレビュー');ttk.Label(bar,textvariable=self.info).pack(side='left',padx=5)
        self.canvas=tk.Canvas(self,background='#4a5058',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<ButtonPress-3>',self.pan_start)
        self.canvas.bind('<B3-Motion>',self.pan_move)
        self.canvas.bind('<ButtonRelease-3>',self.pan_end)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Configure>',self.resize)
        self.bind('<Destroy>',self.dispose)
        ttk.Label(self,text='右ドラッグ：移動　Ctrl＋ホイール：拡大・縮小',padding=4).pack(fill='x')

    def set_pdf(self,path):
        doc=pymupdf.open(str(Path(path)))
        if not len(doc):doc.close();raise ValueError('PDFにページがありません')
        if self.doc:self.doc.close()
        self.doc=doc;self.page=0;self.last_size=None;self.fit_mode=True
        self.update_idletasks();self.fit()

    def dimensions(self):
        return max(self.canvas.winfo_width(),100),max(self.canvas.winfo_height(),100)

    def fit(self):
        if not self.doc:return
        w,h=self.dimensions();r=self.doc[self.page].rect
        self.zoom=max(.1,min(4,min((w-20)/(r.width*4/3),(h-20)/(r.height*4/3))))
        self.fit_mode=True;self.center();self.render()

    def center(self):
        if not self.doc:return
        w,h=self.dimensions();r=self.doc[self.page].rect
        self.offset=((w-r.width*4/3*self.zoom)/2,(h-r.height*4/3*self.zoom)/2)

    def actual(self):
        self.zoom=1;self.fit_mode=False;self.center();self.render()

    def change_zoom(self,factor,point=None):
        if not self.doc:return
        if point is None:
            w,h=self.dimensions();point=(w/2,h/2)
        old=self.zoom;self.zoom=max(.1,min(4,old*factor));ratio=self.zoom/old
        px,py=point;ox,oy=self.offset
        self.offset=(px-(px-ox)*ratio,py-(py-oy)*ratio);self.fit_mode=False
        self.render()

    def render(self):
        if not self.doc:return
        p=self.doc[self.page];scale=self.zoom*4/3
        # Bound raster memory while retaining the user's display scale.
        raster_scale=min(scale,(16_000_000/(p.rect.width*p.rect.height))**.5)
        pix=p.get_pixmap(matrix=pymupdf.Matrix(raster_scale,raster_scale),alpha=False)
        im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        target=(round(p.rect.width*scale),round(p.rect.height*scale))
        if target!=im.size:im=im.resize(target,Image.Resampling.LANCZOS)
        self.photo=ImageTk.PhotoImage(im,master=self.canvas)
        if self.item:self.canvas.delete(self.item)
        self.item=self.canvas.create_image(*self.offset,image=self.photo,anchor='nw')
        self.info.set(f'{self.page+1}/{len(self.doc)}　{self.zoom:.0%}')

    def pan_start(self,e):
        self.pan_point=(e.x,e.y);self.canvas.configure(cursor='fleur');return 'break'

    def pan_move(self,e):
        if self.pan_point and self.item:
            dx=e.x-self.pan_point[0];dy=e.y-self.pan_point[1]
            self.offset=(self.offset[0]+dx,self.offset[1]+dy)
            self.canvas.move(self.item,dx,dy);self.pan_point=(e.x,e.y);self.fit_mode=False
        return 'break'

    def pan_end(self,e):
        self.pan_point=None;self.canvas.configure(cursor='');return 'break'

    def wheel(self,e):
        if e.state & 0x4:self.change_zoom(1.2 if e.delta>0 else 1/1.2,(e.x,e.y))
        elif self.item:
            dy=60 if e.delta>0 else -60;self.offset=(self.offset[0],self.offset[1]+dy);self.canvas.move(self.item,0,dy);self.fit_mode=False
        return 'break'

    def turn(self,step):
        if self.doc:
            self.page=max(0,min(len(self.doc)-1,self.page+step));self.fit()

    def resize(self,e):
        if self.fit_mode and self.doc:
            if self.job:self.after_cancel(self.job)
            self.job=self.after(100,self.delayed_fit)

    def delayed_fit(self):
        self.job=None;self.fit()

    def dispose(self,e):
        if e.widget is self:
            if self.job:self.after_cancel(self.job);self.job=None
            if self.doc:self.doc.close();self.doc=None

def preview_window(parent,path):
    win=tk.Toplevel(parent);win.title('帳票プレビュー');win.geometry('1000x850')
    view=PDFView(win);view.pack(fill='both',expand=True);view.set_pdf(path)
    return win
