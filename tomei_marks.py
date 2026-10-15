"""Readable inferred check mark, distinct from source-observed print glyphs.

The supplied 46-character inventory excludes handwritten checks. No source
PDF check was available here; these strokes are a new inferred mark.
"""
PROVENANCE={'kind':'inferred','source_pdf_verified':False,
            'reason':'Source inventory excludes checks; original PDF unavailable',
            'style':'two connected strokes, rounded ends, no crossing diagonals'}


def draw_check(canvas,x,y,width,height):
    # PDF form coordinates increase downwards. Same ink/alpha as other inputs.
    canvas.setLineCap(1);canvas.setLineJoin(1)
    canvas.setLineWidth(max(.8,min(width,height)*.10))
    path=canvas.beginPath()
    path.moveTo(x+width*.16,y+height*.48)
    path.lineTo(x+width*.38,y+height*.78)
    path.lineTo(x+width*.87,y+height*.13)
    canvas.drawPath(path,stroke=1,fill=0)
