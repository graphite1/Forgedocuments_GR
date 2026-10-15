"""Composite filled/stroked variable ink once, avoiding dark overlap outlines."""
from reportlab.pdfbase import pdfdoc


def begin_ink(canvas,alpha,bounds,name):
    canvas.saveState()
    canvas.setFillAlpha(alpha);canvas.setStrokeAlpha(alpha)
    if not 0<alpha<1:return None
    canvas.beginForm(name,*bounds)
    canvas.setFillAlpha(1);canvas.setStrokeAlpha(1)
    return name


def end_ink(canvas,name):
    if name is not None:
        # ReportLab endForm accepts a prebuilt stream. Keep its standard
        # resources/filters, adding an isolated PDF transparency group only.
        group=pdfdoc.PDFDictionary({'S':pdfdoc.PDFName('Transparency'),
                                   'I':pdfdoc.PDFtrue,'CS':pdfdoc.PDFName('DeviceRGB')})
        stream=pdfdoc.PDFStream(dictionary=pdfdoc.PDFDictionary({'Group':group}),
                               content='\n'.join([canvas._preamble]+canvas._code))
        canvas.endForm(Contents=stream)
        canvas.doForm(name)
    canvas.restoreState()
