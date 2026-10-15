"""Stream A4 PNG pages to one PDF without retaining full raster pages in RAM."""
from pathlib import Path
from io import BytesIO
from PIL import Image

def combine_png_pages(image_paths,path,dpi=300):
    paths=list(image_paths)
    if not paths:raise ValueError('PDFにまとめる画像がありません')
    offsets={};count=2+3*len(paths)
    with Path(path).open('wb') as stream:
        stream.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        def obj(number,data):
            offsets[number]=stream.tell();stream.write(f'{number} 0 obj\n'.encode('ascii'))
            stream.write(data);stream.write(b'\nendobj\n')
        obj(1,b'<< /Type /Catalog /Pages 2 0 R >>')
        kids=' '.join(f'{3+3*i} 0 R' for i in range(len(paths)))
        obj(2,f'<< /Type /Pages /Count {len(paths)} /Kids [{kids}] >>'.encode('ascii'))
        for i,p in enumerate(paths):
            page,image_obj,content=3+3*i,4+3*i,5+3*i
            with Image.open(p) as im:
                w,h=im.size;points_w=w*72/dpi;points_h=h*72/dpi
                data=BytesIO();im.convert('RGB').save(data,format='JPEG',quality=100,subsampling=0)
                jpeg=data.getvalue()
            obj(page,f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {points_w:.5f} {points_h:.5f}] /Resources << /XObject << /Im0 {image_obj} 0 R >> >> /Contents {content} 0 R >>'.encode('ascii'))
            obj(image_obj,f'<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(jpeg)} >>\nstream\n'.encode('ascii')+jpeg+b'\nendstream')
            commands=f'q\n{points_w:.5f} 0 0 {points_h:.5f} 0 0 cm\n/Im0 Do\nQ\n'.encode('ascii')
            obj(content,f'<< /Length {len(commands)} >>\nstream\n'.encode('ascii')+commands+b'endstream')
        xref=stream.tell();stream.write(f'xref\n0 {count+1}\n'.encode('ascii'));stream.write(b'0000000000 65535 f \n')
        for i in range(1,count+1):stream.write(f'{offsets[i]:010d} 00000 n \n'.encode('ascii'))
        stream.write(f'trailer\n<< /Size {count+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode('ascii'))
