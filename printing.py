"""Windows GDI print job. Physical dimensions are preserved; no fit-to-page."""
import ctypes as C
from ctypes import wintypes as W

def print_pdf(path, owner=0):
    import sys
    if sys.platform!='win32': raise RuntimeError('直接印刷はWindows専用です')
    import pymupdf as fitz
    from PIL import Image, ImageWin
    class PRINTDLGW(C.Structure):
        _fields_=[('lStructSize',W.DWORD),('hwndOwner',W.HWND),('hDevMode',W.HGLOBAL),('hDevNames',W.HGLOBAL),('hDC',W.HDC),('Flags',W.DWORD),('nFromPage',W.WORD),('nToPage',W.WORD),('nMinPage',W.WORD),('nMaxPage',W.WORD),('nCopies',W.WORD),('hInstance',W.HINSTANCE),('lCustData',C.c_ssize_t),('lpfnPrintHook',C.c_void_p),('lpfnSetupHook',C.c_void_p),('lpPrintTemplateName',W.LPCWSTR),('lpSetupTemplateName',W.LPCWSTR),('hPrintTemplate',W.HGLOBAL),('hSetupTemplate',W.HGLOBAL)]
    class DOCINFOW(C.Structure):
        _fields_=[('cbSize',C.c_int),('lpszDocName',W.LPCWSTR),('lpszOutput',W.LPCWSTR),('lpszDatatype',W.LPCWSTR),('fwType',W.DWORD)]
    dlg=C.WinDLL('comdlg32',use_last_error=True);g=C.WinDLL('gdi32',use_last_error=True);k=C.WinDLL('kernel32',use_last_error=True)
    dlg.PrintDlgW.argtypes=[C.POINTER(PRINTDLGW)];dlg.PrintDlgW.restype=W.BOOL
    g.GetDeviceCaps.argtypes=[W.HDC,C.c_int];g.GetDeviceCaps.restype=C.c_int
    g.StartDocW.argtypes=[W.HDC,C.POINTER(DOCINFOW)];g.StartDocW.restype=C.c_int
    for name in ('StartPage','EndPage','EndDoc','AbortDoc','DeleteDC'):
        getattr(g,name).argtypes=[W.HDC];getattr(g,name).restype=C.c_int
    g.SetStretchBltMode.argtypes=[W.HDC,C.c_int]
    k.GlobalFree.argtypes=[W.HGLOBAL];k.GlobalFree.restype=W.HGLOBAL
    dlg.CommDlgExtendedError.restype=W.DWORD
    pd=PRINTDLGW();pd.lStructSize=C.sizeof(pd);pd.hwndOwner=owner;pd.Flags=0x100|0x4|0x8;pd.nMinPage=1;pd.nMaxPage=65535;pd.nCopies=1
    if not dlg.PrintDlgW(C.byref(pd)):
        error=dlg.CommDlgExtendedError()
        if error: raise RuntimeError(f'印刷ダイアログエラー: {error}')
        return False
    started=False
    try:
        cap=lambda n:g.GetDeviceCaps(pd.hDC,n)
        dx,dy=cap(88),cap(90)
        physical_w,physical_h=cap(110)/dx*25.4,cap(111)/dy*25.4
        with fitz.open(path) as doc:
            for pg in doc:
                w,h=pg.rect.width/72*25.4,pg.rect.height/72*25.4
                if abs(w-physical_w)>2 or abs(h-physical_h)>2:
                    raise ValueError(f'PDFは {w:.1f}×{h:.1f}mm、プリンターは {physical_w:.1f}×{physical_h:.1f}mmです。用紙と向きを合わせてください。自動拡縮は行いません')
            info=DOCINFOW(C.sizeof(DOCINFOW),'運搬明細書',None,None,0)
            if g.StartDocW(pd.hDC,C.byref(info))<=0: raise RuntimeError('印刷ジョブを開始できません')
            started=True
            for _ in range(max(1,pd.nCopies)):
                for pg in doc:
                    if g.StartPage(pd.hDC)<=0: raise RuntimeError('印刷ページを開始できません')
                    pix=pg.get_pixmap(dpi=300,alpha=False)
                    im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                    x,y=-cap(112),-cap(113)
                    pw,ph=round(pg.rect.width/72*dx),round(pg.rect.height/72*dy)
                    g.SetStretchBltMode(pd.hDC,4)
                    ImageWin.Dib(im).draw(pd.hDC,(x,y,x+pw,y+ph))
                    if g.EndPage(pd.hDC)<=0: raise RuntimeError('印刷ページを終了できません')
            if g.EndDoc(pd.hDC)<=0: raise RuntimeError('印刷ジョブを終了できません')
            started=False
        return True
    finally:
        if started:g.AbortDoc(pd.hDC)
        if pd.hDC:g.DeleteDC(pd.hDC)
        if pd.hDevMode:k.GlobalFree(pd.hDevMode)
        if pd.hDevNames:k.GlobalFree(pd.hDevNames)
