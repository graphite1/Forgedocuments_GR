"""Explicit font runs, with the same metrics for fitting and painting."""
from dataclasses import dataclass


@dataclass(frozen=True)
class InputFont:
    fallback: str
    primary: str
    supported: frozenset

    def runs(self, value):
        result=[]
        for char in value:
            font=self.primary if char in self.supported else self.fallback
            if result and result[-1][0]==font:result[-1]=(font,result[-1][1]+char)
            else:result.append((font,char))
        return result


def runs(font,value):
    return font.runs(value) if isinstance(font,InputFont) else [(font,value)]


def string_width(value,font,size):
    from reportlab.pdfbase import pdfmetrics
    return sum(pdfmetrics.stringWidth(text,name,size) for name,text in runs(font,value))


def draw_text(canvas,font,value,size,tracking=0,mode=0,x=0,y=0):
    """Place runs explicitly: tracking also applies across a font boundary."""
    for name,text in runs(font,value):
        obj=canvas.beginText(x,y)
        obj.setFont(name,size);obj.setCharSpace(tracking);obj.setTextRenderMode(mode)
        obj.textOut(text);canvas.drawText(obj)
        x+=string_width(text,name,size)+len(text)*tracking
