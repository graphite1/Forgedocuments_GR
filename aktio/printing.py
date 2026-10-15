"""Native Windows printer dialog and physical-size printing with one receipt per page.
References: Microsoft Learn PRINTDLGW, DEVMODEW, ResetDCW; Pillow ImageWin.Dib.
"""
import os,ctypes
from .receipt import render_receipt_image,receipt_layout

def print_rectangle(width_mm,height_mm,dpi_x,dpi_y,physical_w,physical_h,offset_x,offset_y):
    w=round(width_mm*dpi_x/25.4);h=round(height_mm*dpi_y/25.4)
    x=round((physical_w-w)/2)-offset_x;y=round((physical_h-h)/2)-offset_y
    return x,y,x+w,y+h

def print_records(records,owner=0,paper='a4'):
    if os.name!='nt':raise OSError('プリンターへの直接印刷はWindowsで使用してください')
    if not records:raise ValueError('印刷するレシートがありません')
    from ctypes import wintypes as w
    from PIL import ImageWin
    PTR=ctypes.c_void_p;WORD=ctypes.c_uint16;DWORD=ctypes.c_uint32
    class PRINTDLG(ctypes.Structure):
        _pack_=8 if ctypes.sizeof(PTR)==8 else 1
        _fields_=[('size',DWORD),('owner',PTR),('devmode',PTR),('devnames',PTR),('dc',PTR),('flags',DWORD),
          ('from_page',WORD),('to_page',WORD),('min_page',WORD),('max_page',WORD),('copies',WORD),
          ('instance',PTR),('custom',ctypes.c_ssize_t),('print_hook',PTR),('setup_hook',PTR),
          ('print_template',ctypes.c_wchar_p),('setup_template',ctypes.c_wchar_p),('template',PTR),('setup',PTR)]
    class DEVMODE_HEAD(ctypes.Structure):
        _fields_=[('name',WORD*32),('spec',WORD),('driver',WORD),('size',WORD),('extra',WORD),('fields',DWORD),
          ('orientation',ctypes.c_int16),('paper_size',ctypes.c_int16),('paper_length',ctypes.c_int16),
          ('paper_width',ctypes.c_int16),('scale',ctypes.c_int16),('copies',ctypes.c_int16),
          ('source',ctypes.c_int16),('quality',ctypes.c_int16)]
    class DOCINFO(ctypes.Structure):
        _fields_=[('size',ctypes.c_int),('name',ctypes.c_wchar_p),('output',ctypes.c_wchar_p),
                   ('datatype',ctypes.c_wchar_p),('flags',DWORD)]
    dlg=ctypes.WinDLL('comdlg32',use_last_error=True);gdi=ctypes.WinDLL('gdi32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    dlg.PrintDlgW.argtypes=[ctypes.POINTER(PRINTDLG)];dlg.PrintDlgW.restype=ctypes.c_int
    dlg.CommDlgExtendedError.restype=DWORD
    kernel.GlobalLock.argtypes=[PTR];kernel.GlobalLock.restype=PTR
    kernel.GlobalUnlock.argtypes=[PTR];kernel.GlobalFree.argtypes=[PTR];kernel.GlobalFree.restype=PTR
    gdi.GetDeviceCaps.argtypes=[PTR,ctypes.c_int];gdi.GetDeviceCaps.restype=ctypes.c_int
    gdi.ResetDCW.argtypes=[PTR,PTR];gdi.ResetDCW.restype=PTR
    gdi.DeleteDC.argtypes=[PTR];gdi.DeleteDC.restype=ctypes.c_int
    gdi.StartDocW.argtypes=[PTR,ctypes.POINTER(DOCINFO)];gdi.StartDocW.restype=ctypes.c_int
    for name in ('StartPage','EndPage','EndDoc','AbortDoc'):
        fn=getattr(gdi,name);fn.argtypes=[PTR];fn.restype=ctypes.c_int
    pd=PRINTDLG();pd.size=ctypes.sizeof(pd);pd.owner=owner
    pd.flags=0x100|0x4|0x8|0x40000;pd.min_page=1;pd.max_page=len(records);pd.copies=1
    started=False
    try:
        if not dlg.PrintDlgW(ctypes.byref(pd)):
            code=dlg.CommDlgExtendedError()
            if code:raise OSError(f'印刷画面を開けませんでした（Windowsコード {code}）')
            return False
        _,layout=receipt_layout();mm_w,mm_h=layout['receipt_size_mm']
        if not pd.devmode:raise OSError('プリンタードライバーから用紙設定を取得できません')
        addr=kernel.GlobalLock(pd.devmode)
        if not addr:raise OSError('プリンター用紙設定を開けません')
        try:
            mode=ctypes.cast(addr,ctypes.POINTER(DEVMODE_HEAD)).contents
            if mode.size<ctypes.sizeof(DEVMODE_HEAD):raise OSError('対応していないプリンター設定です')
            mode.orientation=1;mode.scale=100
            if paper=='a4':
                mode.fields=(mode.fields&~(0x4|0x8))|0x1|0x2|0x10;mode.paper_size=9
            elif paper=='receipt':
                mode.fields=(mode.fields&~0x2)|0x1|0x4|0x8|0x10
                mode.paper_size=0;mode.paper_width=round(mm_w*10);mode.paper_length=round(mm_h*10)
            else:raise ValueError('印刷用紙を確認してください')
            dc=gdi.ResetDCW(pd.dc,addr)
            if not dc:raise OSError('プリンターが指定の用紙サイズに対応していません')
            pd.dc=dc
        finally:kernel.GlobalUnlock(pd.devmode)
        cap=lambda n:gdi.GetDeviceCaps(pd.dc,n)
        dpi_x,dpi_y=cap(88),cap(90);pw,ph=cap(110),cap(111);ox,oy=cap(112),cap(113)
        if min(dpi_x,dpi_y,pw,ph)<=0:raise OSError('プリンターの解像度または用紙寸法を取得できません')
        expected=(210,297) if paper=='a4' else (mm_w,mm_h)
        actual=(pw*25.4/dpi_x,ph*25.4/dpi_y)
        tolerance=3 if paper=='a4' else 2
        if any(abs(a-b)>tolerance for a,b in zip(actual,expected)):
            raise OSError(f'指定した用紙サイズを適用できませんでした。プリンター側の用紙は約{actual[0]:.1f}×{actual[1]:.1f}mmです。A4中央または対応する用紙を選択してください')
        rect=print_rectangle(mm_w,mm_h,dpi_x,dpi_y,pw,ph,ox,oy)
        # Permit only the empty margin to cross the printer's nonprintable edge.
        for record in records:
            crop=render_receipt_image(record).crop(layout['receipt_crop_px'])
            ink=crop.convert('L').point(lambda p:255 if p<190 else 0).getbbox()
            if ink:
                x1=rect[0]+ink[0]/crop.width*(rect[2]-rect[0]);x2=rect[0]+ink[2]/crop.width*(rect[2]-rect[0])
                y1=rect[1]+ink[1]/crop.height*(rect[3]-rect[1]);y2=rect[1]+ink[3]/crop.height*(rect[3]-rect[1])
                if x1<0 or y1<0 or x2>cap(8) or y2>cap(10):raise OSError('文字がプリンターの印刷可能領域から外れます。A4中央または余白の小さい対応用紙を選んでください')
        info=DOCINFO();info.size=ctypes.sizeof(info);info.name=f'AKTIO_{len(records)}枚'
        if gdi.StartDocW(pd.dc,ctypes.byref(info))<=0:raise OSError('印刷ジョブを開始できませんでした')
        started=True
        for record in records:
            if gdi.StartPage(pd.dc)<=0:raise OSError('印刷ページを開始できませんでした')
            crop=render_receipt_image(record).crop(layout['receipt_crop_px'])
            ImageWin.Dib(crop).draw(ImageWin.HDC(pd.dc),rect)
            if gdi.EndPage(pd.dc)<=0:raise OSError('印刷ページを完了できませんでした')
        if gdi.EndDoc(pd.dc)<=0:raise OSError('印刷ジョブを完了できませんでした')
        started=False;return True
    finally:
        if started and pd.dc:gdi.AbortDoc(pd.dc)
        if pd.dc:gdi.DeleteDC(pd.dc)
        if pd.devmode:kernel.GlobalFree(pd.devmode)
        if pd.devnames:kernel.GlobalFree(pd.devnames)
