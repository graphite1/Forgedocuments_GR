"""Synthetic grid for pipeline tests and labelled diagnostics, never an original."""
import hashlib
from PIL import Image,ImageDraw
from background_assets import encode_background


def synthetic_background(template):
    px_per_mm=10
    image=Image.new('RGB',(round(template['width_mm']*px_per_mm),round(template['height_mm']*px_per_mm)),'white')
    draw=ImageDraw.Draw(image);cyan=(75,175,185)
    # Deliberately generic calibration grid: no issuer, certificate or title.
    draw.rectangle((0,0,image.width-1,image.height-1),outline=cyan,width=2)
    for x in range(100,image.width,100):draw.line((x,0,x,image.height),fill=(205,235,238))
    for y in range(100,image.height,100):draw.line((0,y,image.width,y),fill=(205,235,238))
    draw.text((25,20),'SYNTHETIC BACKGROUND / PIPELINE TEST',fill=cyan)
    for field in template['fields']:
        for option in field.get('options',[]):
            x,y,w,h=option['box'];sx=image.width/template['coordinate_width'];sy=image.height/template['coordinate_height']
            draw.rectangle((x*sx,y*sy,(x+w)*sx,(y+h)*sy),outline=cyan,width=2)
    return encode_background(image,template['width_mm'],template['height_mm'],source_sha256=hashlib.sha256(b'synthetic-calibration-grid-v1').hexdigest(),
        kind='synthetic_test',diagnostic_only=True,processing={'synthetic':True,'original_source_used':False})
