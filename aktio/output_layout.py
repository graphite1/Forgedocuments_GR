"""Outside-only specimen notice and physical output geometry for AKTIO."""
from functools import lru_cache

NOTICE_TEXT='出力見本'
NOTICE_SIZE=(160,48)
NOTICE_GAP=24
NOTICE_BOTTOM=24
NOTICE_COLORS={'charcoal':('濃いグレー',(64,64,64)),
               'black':('黒',(0,0,0)),
               'navy':('濃紺',(31,54,88)),
               'forest':('深緑',(29,75,59))}
DEFAULT_COLOR='charcoal'


def checked_color(value):
    if not isinstance(value,str) or value not in NOTICE_COLORS:
        raise ValueError('出力見本の文字色は、読める濃色の選択肢から指定してください')
    return value


def white_contrast(rgb):
    def linear(v):
        v=v/255
        return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
    light=sum(w*linear(v) for w,v in zip((.2126,.7152,.0722),rgb))
    return 1.05/(light+.05)


def footer_height(record):
    return NOTICE_GAP+NOTICE_SIZE[1]+NOTICE_BOTTOM if record.get('mode')=='simulation' else 0


def output_box(record,layout):
    x,y,right,bottom=layout['receipt_crop_px']
    return x,y,right,bottom+footer_height(record)


def notice_box(record,layout,*,paper='a4'):
    if not footer_height(record):return None
    x,y,right,bottom=layout['receipt_crop_px']
    left=x+(right-x-NOTICE_SIZE[0])//2;top=bottom+NOTICE_GAP
    if paper=='receipt':left-=x;top-=y
    elif paper!='a4':raise ValueError('出力用紙を確認してください')
    return left,top,left+NOTICE_SIZE[0],top+NOTICE_SIZE[1]


def output_size_mm(record,layout):
    width,height=layout['receipt_size_mm']
    return width,height+footer_height(record)*25.4/layout['dpi']


def notice_image(color=DEFAULT_COLOR):return _notice_image(checked_color(color)).copy()


@lru_cache(maxsize=len(NOTICE_COLORS))
def _notice_image(color):
    import io,pymupdf
    from PIL import Image
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen.canvas import Canvas
    rgb=NOTICE_COLORS[color][1]
    if white_contrast(rgb)<7:raise ValueError('出力見本の文字色のコントラストが不足しています')
    name='HeiseiKakuGo-W5'
    if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(UnicodeCIDFont(name))
    stream=io.BytesIO();canvas=Canvas(stream,pagesize=NOTICE_SIZE)
    canvas.setFillColorRGB(*(v/255 for v in rgb));canvas.setFont(name,36)
    canvas.drawCentredString(NOTICE_SIZE[0]/2,10,NOTICE_TEXT)
    # Draw text only: no outline, rectangle, fill panel or alpha adjustment.
    canvas.save()
    with pymupdf.open(stream=stream.getvalue(),filetype='pdf') as pdf:
        pix=pdf[0].get_pixmap(alpha=False)
        return Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
