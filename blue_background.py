"""Extract existing blue pixels and correct rotation; no inpainting or OCR redraw."""
import hashlib
import io
import math
from pathlib import Path
from PIL import Image
from background_assets import encode_background, MAX_PIXELS


def blue_pixels(image, minimum_chroma=10, max_green_blue_difference=100):
    if image.mode in ('RGBA','LA') or 'transparency' in image.info:
        rgba=image.convert('RGBA');matte=Image.new('RGBA',image.size,'white');matte.alpha_composite(rgba);image=matte.convert('RGB')
    else:image = image.convert('RGB')
    result = Image.new('RGB', image.size, 'white')
    pixels = []
    for r, g, b in image.getdata():
        retain = min(g,b)-r >= minimum_chroma and abs(g-b) <= max_green_blue_difference
        pixels.append((r,g,b) if retain else (255,255,255))
    result.putdata(pixels)
    return result


def estimate_rotation(image, maximum_degrees=2, step=.1):
    """Projection of existing blue horizontal rules; a suggestion for review only."""
    if not 0<float(step)<=float(maximum_degrees)<=5:raise ValueError('傾き候補の範囲と刻みが不正です')
    ink = blue_pixels(image).convert('L')
    ink.thumbnail((600,600))
    ink = ink.point(lambda value: 255-value)
    def score(angle):
        rotated = ink.rotate(angle, resample=Image.Resampling.BILINEAR, expand=False, fillcolor=0)
        data = list(rotated.getdata());w,h=rotated.size
        return sum(sum(data[y*w:(y+1)*w])**2 for y in range(h))
    count=round(maximum_degrees/step)
    angles=[i*step for i in range(-count,count+1)]
    scores=[score(a) for a in angles];best=max(range(len(scores)),key=lambda i:scores[i])
    baseline=score(0)
    return {'suggested_degrees':round(angles[best],3),
            'score_gain':scores[best]/baseline if baseline else 1,
            'automatic_application':False}


def extract_background(source, crop_pixels_after_rotation, width_mm, height_mm,
                       *, deskew_degrees=0, pdf_page=0, reviewed=False):
    if not all(math.isfinite(float(v)) and 10<=float(v)<=1000 for v in (width_mm,height_mm)):
        raise ValueError('背景の実寸は10〜1000mmで指定してください')
    path=Path(source);raw=path.read_bytes()
    if not math.isfinite(float(deskew_degrees)) or abs(deskew_degrees)>5:
        raise ValueError('傾き補正は確認した±5度以内で指定してください')
    if path.suffix.lower()=='.pdf':
        import pymupdf
        with pymupdf.open(stream=raw,filetype='pdf') as doc:
            if not 0<=pdf_page<len(doc):raise ValueError('原票のページ番号が不正です')
            rect=doc[pdf_page].rect
            if rect.width*rect.height*(300/72)**2>MAX_PIXELS:raise ValueError('原票PDFのページが大きすぎます')
            pix=doc[pdf_page].get_pixmap(dpi=300,alpha=False)
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    else:
        with Image.open(io.BytesIO(raw)) as source_image:
            if source_image.width*source_image.height>MAX_PIXELS:raise ValueError('原票画像が大きすぎます')
            source_image.load();image=source_image.convert('RGB')
    # Remove non-blue ink before interpolation so black strokes cannot turn cyan.
    cleaned=blue_pixels(image)
    rotated=cleaned.rotate(float(deskew_degrees),resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white')
    x0,y0,x1,y1=map(int,crop_pixels_after_rotation)
    if not 0<=x0<x1<=rotated.width or not 0<=y0<y1<=rotated.height:
        raise ValueError('補正後の外枠切り出し座標が画像範囲を超えています')
    cropped=rotated.crop((x0,y0,x1,y1))
    if abs((cropped.width/cropped.height)/(width_mm/height_mm)-1)>.01:
        raise ValueError('外枠の縦横比が異なります。座標を確認し、画像を引き伸ばさないでください')
    return encode_background(cropped,width_mm,height_mm,source_sha256=hashlib.sha256(raw).hexdigest(),
        reviewed=reviewed,processing={'crop_pixels_after_rotation':[x0,y0,x1,y1],
        'deskew_degrees':deskew_degrees,'pdf_page':pdf_page,'blue_pixels_only':True,
        'missing_ink_synthesized':False})
